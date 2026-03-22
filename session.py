"""
FocusFlow — session.py
Tracks all time buckets for one work session.
"""

import time
from datetime import datetime


class Session:

    def __init__(self, task: str, mode: str, planned_minutes: int):
        self.task            = task
        self.mode            = mode
        self.planned_minutes = planned_minutes
        self.start_time      = time.time()
        self.date            = datetime.now().strftime("%Y-%m-%d")
        self.start_str       = datetime.now().strftime("%H:%M:%S")

        self.present_seconds = 0.0
        self.away_seconds    = 0.0
        self.phone_seconds   = 0.0
        self.break_seconds   = 0.0
        self.break_count     = 0

        self.in_break        = False
        self.break_end_time  = 0.0
        self._last_tick      = time.time()

    def tick(self, face_present: bool, phone_present: bool):
        now     = time.time()
        elapsed = now - self._last_tick
        self._last_tick = now

        if self.in_break:
            if now >= self.break_end_time:
                self.in_break = False
            else:
                self.break_seconds += elapsed
                return

        if not face_present:
            self.away_seconds += elapsed
        elif phone_present:
            self.phone_seconds += elapsed
        else:
            self.present_seconds += elapsed

    def start_break(self, minutes: int):
        if self.in_break:
            return
        self.in_break       = True
        self.break_end_time = time.time() + (minutes * 60)
        self.break_count   += 1

    def end_break_early(self):
        """Immediately end an active break."""
        if self.in_break:
            self.in_break = False
            self.break_end_time = time.time()

    def is_on_break(self) -> bool:
        return self.in_break

    def break_remaining(self) -> float:
        if not self.in_break:
            return 0.0
        return max(0.0, self.break_end_time - time.time())

    def summary(self) -> dict:
        total  = (time.time() - self.start_time) / 60
        eff    = self.present_seconds / 60
        brk    = self.break_seconds   / 60
        away   = self.away_seconds    / 60
        phone  = self.phone_seconds   / 60
        score  = min((eff / self.planned_minutes * 100) if self.planned_minutes else 0, 100)

        return {
            "date":              self.date,
            "start_time":        self.start_str,
            "task":              self.task,
            "mode":              self.mode,
            "planned_minutes":   round(self.planned_minutes, 1),
            "total_minutes":     round(total, 1),
            "effective_minutes": round(eff,   1),
            "break_minutes":     round(brk,   1),
            "break_count":       self.break_count,
            "away_minutes":      round(away,  1),
            "phone_minutes":     round(phone, 1),
            "focus_score":       round(score, 1),
        }
