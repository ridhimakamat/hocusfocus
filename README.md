# HocusFocus 🌸

**Behavior-based productivity tracking using computer vision.**

HocusFocus measures your real productive time — not your intentions. Your webcam quietly tracks presence and breaks so you always know where your day really went.

## Features

- **Automatic effective time calculation** — subtracts absence and breaks from total session time
- **Presence detection** — knows when you step away from your desk
- **Gesture-based breaks** — hold 1–5 fingers to the camera to take a 1–5 minute break. No buttons needed.
- **Screen and offline modes** — works for laptop work or reading/writing offline
- **Session analytics** — charts showing planned vs effective time, focus score trends, and break patterns
- **User accounts** — sign up, log in, view full session history

---

## Tech stack

- **Python** — core backend
- **Flask + SocketIO** — web server and real-time communication
- **OpenCV** — webcam capture
- **MediaPipe** — face mesh and hand landmark detection
- **Pandas + Matplotlib** — session data analysis and chart generation
- **Google Sheets API** — optional session sync

---

## Running locally

**Requirements:** Python 3.9+

```bash
git clone https://github.com/ridhimakamat/hocusfocus
cd hocusfocus
pip install -r requirements.txt
python app.py
```

Open `http://localhost:5000` in your browser.

---

## How gesture breaks work

Hold your hand up to the webcam with fingers extended. The number of fingers you show sets your break duration in minutes (1–5). HocusFocus detects the gesture, pauses your session timer, and resumes automatically when the break ends.

---

## Live demo

[hocusfocus.up.railway.app](hocusfocus.up.railway.app)

> Note: The live demo hosts the landing page, sign up, login and session history. The webcam tracker runs locally.
  Note: Copy and paste link in browser to use.
---

## Built by

Ridhima Kamat
