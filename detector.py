"""
HocusFocus — detector.py
Webcam loop. Background thread.
Gesture breaks: show N fingers for 1.5s to trigger N-minute break.
"""

import cv2
import time
import numpy as np
import mediapipe as mp
from session import Session

# finger landmark indices
TIPS = [4, 8, 12, 16, 20]
PIPS = [3, 6, 10, 14, 18]
MCPS = [2, 5, 9, 13, 17]

# BGR overlay colours
ROSE     = (122, 130, 232)
SAGE     = (142, 171, 122)
LAVENDER = (196, 142, 155)
CREAM    = (210, 225, 240)
DARK     = ( 30,  25,  20)
AMBER    = ( 80, 166, 245)


def _count_fingers(lm) -> int:
    """
    Simple, reliable finger counter.
    Each of the 4 fingers: tip y < pip y means extended.
    Thumb: tip x further from palm centre than mcp x.
    No palm-facing check — works at any reasonable angle.
    """
    count = 0

    # Thumb — compare x distance from palm centre
    palm_x = (lm[5].x + lm[17].x) / 2
    if abs(lm[4].x - palm_x) > abs(lm[3].x - palm_x):
        count += 1

    # Index, Middle, Ring, Pinky
    for tip, pip in zip(TIPS[1:], PIPS[1:]):
        if lm[tip].y < lm[pip].y:
            count += 1

    return count


def _hand_visible(lm) -> bool:
    """
    Returns True if the hand is large enough to be reliable.
    Filters out tiny/distant hands.
    """
    xs = [l.x for l in lm]
    ys = [l.y for l in lm]
    spread = (max(xs) - min(xs)) + (max(ys) - min(ys))
    return spread > 0.08   # hand must span at least 8% of frame


class FocusDetector:

    def __init__(self, session: Session, socketio=None, camera_index: int = 0):
        self.session      = session
        self.socketio     = socketio
        self.camera_index = camera_index
        self.latest_frame = None
        self._stop_flag   = False

        mp_face  = mp.solutions.face_mesh
        mp_hands = mp.solutions.hands
        self._mp_draw = mp.solutions.drawing_utils
        self._mp_hc   = mp_hands.HAND_CONNECTIONS

        self._face_mesh = mp_face.FaceMesh(
            max_num_faces=1, refine_landmarks=True,
            min_detection_confidence=0.5, min_tracking_confidence=0.5)

        self._hands = mp_hands.Hands(
            max_num_hands=1,
            min_detection_confidence=0.4,
            min_tracking_confidence=0.4)

        # face state
        self._face_box  = None
        self._face_full = False

        # gesture state
        self._last_fingers      = 0
        self._hold_start        = None
        self._hold_required     = 1.0   # seconds to hold before triggering
        self._gesture_triggered = False
        self._stable_count      = 0     # consecutive frames with same count

        self._last_emit = 0

    def stop(self):
        self._stop_flag = True

    def end_break_early(self):
        self.session.end_break_early()

    def run_loop(self, keep_running):
        cap = cv2.VideoCapture(self.camera_index, cv2.CAP_DSHOW)
        if not cap.isOpened():
            cap = cv2.VideoCapture(self.camera_index)
        if not cap.isOpened():
            print("[HocusFocus] Could not open webcam.")
            return

        cap.set(cv2.CAP_PROP_FRAME_WIDTH,  640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        cap.set(cv2.CAP_PROP_FPS, 30)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        while keep_running() and not self._stop_flag:
            ret, frame = cap.read()
            if not ret:
                time.sleep(0.05)
                continue

            frame = cv2.flip(frame, 1)
            rgb   = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

            face_present = self._detect_face(rgb, frame)
            fingers      = self._detect_hands(rgb, frame)

            self._handle_gesture(fingers)
            self.session.tick(face_present=face_present, phone_present=False)
            self._draw(frame, face_present, fingers)
            self.latest_frame = frame

            now = time.time()
            if self.socketio and (now - self._last_emit) > 0.25:
                self._last_emit = now
                s = self.session.summary()
                s.update({
                    "face_present":    face_present,
                    "face_full":       self._face_full,
                    "phone_present":   False,
                    "fingers":         fingers,
                    "on_break":        self.session.is_on_break(),
                    "break_remaining": round(self.session.break_remaining(), 1),
                })
                self.socketio.emit("stats_update", s)

        cap.release()

    # ── detections ────────────────────────────────────────────────────────────

    def _detect_face(self, rgb, frame) -> bool:
        r = self._face_mesh.process(rgb)
        if not r.multi_face_landmarks:
            self._face_box  = None
            self._face_full = False
            return False

        lm   = r.multi_face_landmarks[0].landmark
        h, w = frame.shape[:2]
        xs   = [l.x * w for l in lm]
        ys   = [l.y * h for l in lm]
        self._face_box = (int(min(xs)), int(min(ys)),
                          int(max(xs) - min(xs)), int(max(ys) - min(ys)))
        margin = 0.04
        self._face_full = (
            min(xs) > w * margin and max(xs) < w * (1 - margin) and
            min(ys) > h * margin and max(ys) < h * (1 - margin)
        )
        return True

    def _detect_hands(self, rgb, frame) -> int:
        r = self._hands.process(rgb)
        if not r.multi_hand_landmarks:
            return 0

        total = 0
        for hand in r.multi_hand_landmarks:
            lm = hand.landmark

            # draw skeleton
            self._mp_draw.draw_landmarks(
                frame, hand, self._mp_hc,
                self._mp_draw.DrawingSpec(color=ROSE,     thickness=2, circle_radius=3),
                self._mp_draw.DrawingSpec(color=LAVENDER, thickness=2))

            # reject tiny/distant hands
            if not _hand_visible(lm):
                continue

            total += _count_fingers(lm)

        return min(total, 10)

    # ── gesture handling ──────────────────────────────────────────────────────

    def _handle_gesture(self, fingers: int):
        if self.session.is_on_break():
            # reset everything during break
            self._hold_start        = None
            self._gesture_triggered = False
            self._last_fingers      = 0
            self._stable_count      = 0
            return

        if fingers > 0:
            if fingers == self._last_fingers:
                self._stable_count += 1
                # only start timer after 3 stable frames (avoids flicker)
                if self._stable_count >= 2:
                    if self._hold_start is None:
                        self._hold_start = time.time()
                    elif (not self._gesture_triggered and
                          time.time() - self._hold_start >= self._hold_required):
                        self.session.start_break(minutes=fingers)
                        self._gesture_triggered = True
                        if self.socketio:
                            self.socketio.emit("break_started", {"minutes": fingers})
            else:
                # finger count changed — reset
                self._last_fingers      = fingers
                self._stable_count      = 1
                self._hold_start        = None
                self._gesture_triggered = False
        else:
            self._last_fingers      = 0
            self._stable_count      = 0
            self._hold_start        = None
            self._gesture_triggered = False

    # ── overlay ───────────────────────────────────────────────────────────────

    def _draw(self, frame, face_present, fingers):
        h, w = frame.shape[:2]
        s    = self.session.summary()

        # semi-transparent info panel
        ov = frame.copy()
        cv2.rectangle(ov, (10, 10), (310, 190), DARK, -1)
        cv2.addWeighted(ov, 0.72, frame, 0.28, 0, frame)

        def txt(t, y, col=CREAM, sc=0.48):
            cv2.putText(frame, t, (18, y), cv2.FONT_HERSHEY_SIMPLEX,
                        sc, col, 1, cv2.LINE_AA)

        txt("HocusFocus", 32, ROSE, 0.6)
        txt(f"Task      : {s['task'][:22]}",              52)
        txt(f"Effective : {s['effective_minutes']:.1f} min", 74, SAGE)
        txt(f"Breaks    : {s['break_minutes']:.1f} min ({s['break_count']})", 94)
        txt(f"Away      : {s['away_minutes']:.1f} min",   114)
        txt(f"Focus     : {s['focus_score']:.0f}%",       140, LAVENDER)

        # status badge top-right
        if self.session.is_on_break():
            label = f"BREAK  {self.session.break_remaining():.0f}s"
            col   = SAGE
        elif not face_present:
            label, col = "AWAY", AMBER
        elif not self._face_full:
            label, col = "MOVE CLOSER", AMBER
        elif fingers > 0:
            pct = 0
            if self._hold_start and self._stable_count >= 3:
                pct = min(100, int((time.time() - self._hold_start)
                                   / self._hold_required * 100))
            label = f"{fingers} finger{'s' if fingers > 1 else ''}  {pct}%"
            col   = LAVENDER
        else:
            label, col = "FOCUSED", SAGE

        (tw, _), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 2)
        sx = w - tw - 28
        cv2.rectangle(frame, (sx - 8, 10), (w - 10, 42), DARK, -1)
        cv2.putText(frame, label, (sx, 32),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, col, 2, cv2.LINE_AA)

        # face warning bar
        if face_present and not self._face_full:
            cv2.rectangle(frame, (0, h - 34), (w, h), DARK, -1)
            cv2.putText(frame, "Move your face fully into frame",
                        (10, h - 10), cv2.FONT_HERSHEY_SIMPLEX,
                        0.52, AMBER, 1, cv2.LINE_AA)
