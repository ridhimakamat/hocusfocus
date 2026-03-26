"""
HocusFocus — app.py
Run:  python app.py
Open: http://localhost:5000
"""

import time, threading, os, sys
from flask import Flask, render_template, Response, request, jsonify, session, redirect, url_for
from flask_socketio import SocketIO, emit
from session import Session
from logger import SessionLogger
from auth import register, login as auth_login

# Detector only works locally (needs webcam + OpenCV)
try:
    from detector import FocusDetector
    DETECTOR_AVAILABLE = True
except ImportError:
    DETECTOR_AVAILABLE = False
    print("[HocusFocus] Running in web-only mode (no webcam detection)")

USE_SHEETS = False
IS_RAILWAY = os.environ.get("RAILWAY_ENVIRONMENT") is not None

def resource_path(relative):
    """Get absolute path — works for dev and PyInstaller .exe"""
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative)
    return os.path.join(os.path.abspath("."), relative)

# Point Flask to bundled templates and static folders
app_dir = resource_path('.')
app = Flask(__name__,
    template_folder=resource_path('templates'),
    static_folder=resource_path('static')
)
app.config["SECRET_KEY"] = "hocusfocus-secret-2024"
app.config["SESSION_COOKIE_SAMESITE"] = "None"
app.config["SESSION_COOKIE_SECURE"] = True

# Allow Cloudflare proxy headers
from werkzeug.middleware.proxy_fix import ProxyFix
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    async_mode="threading",
    allow_upgrades=True,
    transports=["websocket", "polling"]
)

_session  = None
_detector = None
_thread   = None
_active   = False
_lock     = threading.Lock()


# ── auth helpers ──────────────────────────────────────────────────────────────
def logged_in():
    return "user_email" in session

def current_user():
    return {"email": session.get("user_email",""), "name": session.get("user_name","")}


# ── pages ─────────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return render_template("index.html", user=current_user() if logged_in() else None)

@app.route("/tracker")
def tracker():
    if not logged_in():
        return redirect(url_for("login_page"))
    return render_template("tracker.html", user=current_user(), is_railway=IS_RAILWAY)

@app.route("/history")
def history():
    if not logged_in():
        return redirect(url_for("login_page"))
    rows         = SessionLogger().load_all()
    charts_exist = os.path.isfile("static/charts/planned_vs_effective.png")
    return render_template("history.html", sessions=rows, charts_exist=charts_exist, user=current_user())

@app.route("/login")
def login_page():
    if logged_in():
        return redirect(url_for("tracker"))
    return render_template("login.html")

@app.route("/signup")
def signup_page():
    if logged_in():
        return redirect(url_for("tracker"))
    return render_template("signup.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


# ── auth API ──────────────────────────────────────────────────────────────────
@app.route("/api/signup", methods=["POST"])
def api_signup():
    data     = request.json or {}
    name     = data.get("name", "").strip()
    email    = data.get("email", "").strip()
    password = data.get("password", "")
    if not name or not email or not password:
        return jsonify({"error": "All fields are required."}), 400
    if len(password) < 6:
        return jsonify({"error": "Password must be at least 6 characters."}), 400
    ok, msg = register(name, email, password)
    if not ok:
        return jsonify({"error": msg}), 400
    return jsonify({"status": "ok", "message": msg})

@app.route("/api/login", methods=["POST"])
def api_login():
    data     = request.json or {}
    email    = data.get("email", "")
    password = data.get("password", "")
    ok, msg, user = auth_login(email, password)
    if not ok:
        return jsonify({"error": msg}), 401
    session["user_email"] = user["email"]
    session["user_name"]  = user["name"]
    return jsonify({"status": "ok", "name": user["name"]})


# ── session API ───────────────────────────────────────────────────────────────
@app.route("/api/start", methods=["POST"])
def api_start():
    global _session, _detector, _thread, _active
    if not logged_in():
        return jsonify({"error": "Not logged in"}), 401
    with _lock:
        if _active:
            return jsonify({"error": "Session already running"}), 400
        data    = request.json or {}
        _session  = Session(task=data.get("task","Work session"), mode=data.get("mode","screen"), planned_minutes=int(data.get("planned",60)))
        if DETECTOR_AVAILABLE:
            _detector = FocusDetector(session=_session, socketio=socketio)
            _thread = threading.Thread(target=_run, daemon=True)
            _thread.start()
        _active   = True
    if not DETECTOR_AVAILABLE:
        # Web mode: start a simple timer thread that emits stats
        _thread = threading.Thread(target=_run_web, daemon=True)
        _thread.start()
    return jsonify({"status": "started"})

@app.route("/api/stop", methods=["POST"])
def api_stop():
    global _active, _detector
    with _lock:
        if not _active:
            return jsonify({"error": "No active session"}), 400
        _active = False
        if _detector: _detector.stop()
    if _thread: _thread.join(timeout=4)
    summary = _session.summary()
    SessionLogger().save(summary)
    return jsonify({"status": "stopped", "summary": summary})

@app.route("/api/end_break", methods=["POST"])
def api_end_break():
    if not _active or not _session:
        return jsonify({"error": "No active session"}), 400
    _session.end_break_early()
    socketio.emit("break_ended", {})
    return jsonify({"status": "break_ended"})

@app.route("/api/status")
def api_status():
    if not _active or not _session:
        return jsonify({"active": False})
    s = _session.summary()
    s["active"]          = True
    s["on_break"]        = _session.is_on_break()
    s["break_remaining"] = round(_session.break_remaining(), 1)
    return jsonify(s)

@app.route("/api/save_summary", methods=["POST"])
def api_save_summary():
    if not logged_in():
        return jsonify({"error": "Not logged in"}), 401
    data = request.json or {}
    if not _session:
        return jsonify({"error": "No session"}), 400
    # Update session with browser-computed values
    _session.present_seconds = data.get("effective_minutes", 0) * 60
    _session.away_seconds    = data.get("away_minutes",     0) * 60
    _session.break_seconds   = data.get("break_minutes",    0) * 60
    _session.break_count     = data.get("break_count",      0)
    summary = _session.summary()
    SessionLogger().save(summary)
    return jsonify({"status": "saved"})

@app.route("/api/history")
def api_history():
    return jsonify(SessionLogger().load_all())


# ── MJPEG stream ──────────────────────────────────────────────────────────────
def _frames():
    while True:
        if _detector and _detector.latest_frame is not None:
            ok, buf = cv2.imencode(".jpg", _detector.latest_frame, [cv2.IMWRITE_JPEG_QUALITY, 78])
            if ok:
                yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + buf.tobytes() + b"\r\n"
        time.sleep(0.033)

@app.route("/video_feed")
def video_feed():
    if not DETECTOR_AVAILABLE:
        return "", 204
    return Response(_frames(), mimetype="multipart/x-mixed-replace; boundary=frame")


# ── background thread ─────────────────────────────────────────────────────────
def _run():
    global _active
    try:
        if _detector:
            _detector.run_loop(lambda: _active)
        else:
            # Web-only mode: just tick the session timer
            while _active:
                _session.tick(face_present=True, phone_present=False)
                time.sleep(0.5)
                now = time.time()
                s = _session.summary()
                s.update({"face_present": True, "face_full": True,
                          "phone_present": False, "fingers": 0,
                          "on_break": _session.is_on_break(),
                          "break_remaining": round(_session.break_remaining(), 1)})
                socketio.emit("stats_update", s)
                time.sleep(0.25)
    except Exception as e:
        print(f"[Detector] {e}")
    finally:
        _active = False
        if _session: socketio.emit("session_ended", _session.summary())

def _run_web():
    """Web mode — no webcam, just emit timer stats every second."""
    global _active
    import time as _time
    while _active:
        _time.sleep(0.5)
        if _session and _active:
            _session.tick(face_present=True, phone_present=False)
            s = _session.summary()
            s.update({
                "face_present": True, "face_full": True,
                "phone_present": False, "fingers": 0,
                "on_break": _session.is_on_break(),
                "break_remaining": round(_session.break_remaining(), 1),
            })
            socketio.emit("stats_update", s)
    if _session:
        socketio.emit("session_ended", _session.summary())

@socketio.on("connect")
def on_connect():
    emit("connected", {"ok": True})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    is_local = port == 5000
    print(f"\n🌸  HocusFocus  →  http://localhost:{port}\n")

    socketio.run(app, host="0.0.0.0", port=port, debug=False, allow_unsafe_werkzeug=True)


