"""
FocusFlow — logger.py
Saves sessions to CSV and generates analysis charts.
"""

import os
import csv
import json

FIELDNAMES = [
    "date","start_time","task","mode",
    "planned_minutes","total_minutes","effective_minutes",
    "break_minutes","break_count","away_minutes","phone_minutes","focus_score",
]
CSV_FILE   = "sessions.csv"
CHARTS_DIR = "static/charts"

# palette
C_ROSE     = "#e8827a"
C_PEACH    = "#f0a882"
C_LAVENDER = "#9b8ec4"
C_SAGE     = "#7aab8e"
C_WARM3    = "#e8d9c4"
C_BG       = "#fdf8f2"
C_WARM1    = "#f9f1e7"
C_TEXT     = "#2d2318"
C_TEXT2    = "#7a6455"


class SessionLogger:

    def save(self, summary: dict):
        exists = os.path.isfile(CSV_FILE)
        with open(CSV_FILE, "a", newline="") as f:
            w = csv.DictWriter(f, fieldnames=FIELDNAMES)
            if not exists:
                w.writeheader()
            w.writerow({k: summary.get(k, "") for k in FIELDNAMES})
        self._generate_charts()

    def load_all(self) -> list:
        if not os.path.isfile(CSV_FILE):
            return []
        rows = []
        with open(CSV_FILE, newline="") as f:
            for r in csv.DictReader(f):
                rows.append(r)
        return rows

    def _generate_charts(self):
        try:
            import pandas as pd
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
        except ImportError:
            return

        os.makedirs(CHARTS_DIR, exist_ok=True)
        try:
            df = pd.read_csv(CSV_FILE)
        except Exception:
            return
        if df.empty:
            return

        df["planned_minutes"]   = pd.to_numeric(df["planned_minutes"],   errors="coerce")
        df["effective_minutes"] = pd.to_numeric(df["effective_minutes"], errors="coerce")
        df["break_minutes"]     = pd.to_numeric(df["break_minutes"],     errors="coerce")
        df["phone_minutes"]     = pd.to_numeric(df["phone_minutes"],     errors="coerce")
        df["away_minutes"]      = pd.to_numeric(df["away_minutes"],      errors="coerce")
        df["focus_score"]       = pd.to_numeric(df["focus_score"],       errors="coerce")
        df = df.dropna(subset=["effective_minutes"])

        labels = [f"{r['date']}\n{str(r['task'])[:14]}" for _, r in df.iterrows()]
        x = list(range(len(labels)))

        def base(fs=(11,4)):
            fig, ax = plt.subplots(figsize=fs)
            fig.patch.set_facecolor(C_BG)
            ax.set_facecolor(C_WARM1)
            for sp in ax.spines.values():
                sp.set_edgecolor(C_WARM3)
            ax.tick_params(colors=C_TEXT2, labelsize=8)
            ax.yaxis.label.set_color(C_TEXT2)
            ax.title.set_color(C_TEXT)
            return fig, ax

        # 1 — planned vs effective
        fig, ax = base((12,4))
        w = 0.35
        ax.bar([i-w/2 for i in x], df["planned_minutes"],   width=w, color=C_WARM3, label="Planned",   zorder=2)
        ax.bar([i+w/2 for i in x], df["effective_minutes"], width=w, color=C_ROSE,  label="Effective", zorder=2)
        ax.set_xticks(x); ax.set_xticklabels(labels, fontsize=7)
        ax.set_ylabel("Minutes"); ax.set_title("Planned vs Effective Time", fontsize=12, fontweight="bold", pad=10)
        ax.legend(facecolor=C_BG, edgecolor=C_WARM3, labelcolor=C_TEXT2)
        ax.grid(axis="y", color=C_WARM3, linewidth=0.6, zorder=1)
        fig.tight_layout(); fig.savefig(f"{CHARTS_DIR}/planned_vs_effective.png", dpi=140, bbox_inches="tight"); plt.close(fig)

        # 2 — stacked breakdown
        fig, ax = base((12,4))
        ax.bar(x, df["effective_minutes"], color=C_SAGE,     label="Effective", zorder=2)
        ax.bar(x, df["break_minutes"],     color=C_PEACH,    label="Break",     bottom=df["effective_minutes"], zorder=2)
        ax.bar(x, df["phone_minutes"],     color=C_ROSE,     label="Phone",     bottom=df["effective_minutes"]+df["break_minutes"], zorder=2)
        ax.bar(x, df["away_minutes"],      color=C_LAVENDER, label="Away",      bottom=df["effective_minutes"]+df["break_minutes"]+df["phone_minutes"], zorder=2)
        ax.set_xticks(x); ax.set_xticklabels(labels, fontsize=7)
        ax.set_ylabel("Minutes"); ax.set_title("Session Time Breakdown", fontsize=12, fontweight="bold", pad=10)
        ax.legend(facecolor=C_BG, edgecolor=C_WARM3, labelcolor=C_TEXT2)
        ax.grid(axis="y", color=C_WARM3, linewidth=0.6, zorder=1)
        fig.tight_layout(); fig.savefig(f"{CHARTS_DIR}/time_breakdown.png", dpi=140, bbox_inches="tight"); plt.close(fig)

        # 3 — focus trend
        fig, ax = base((10,4))
        ax.plot(x, df["focus_score"], color=C_ROSE, linewidth=2.2, marker="o",
                markersize=6, markerfacecolor=C_BG, markeredgecolor=C_ROSE, zorder=3)
        ax.fill_between(x, df["focus_score"], alpha=0.12, color=C_ROSE)
        ax.axhline(80, color=C_SAGE, linewidth=1, linestyle="--", zorder=2)
        if len(df) > 0:
            ax.text(len(df)-1, 82, "80% target", color=C_SAGE, fontsize=8, ha="right")
        ax.set_xticks(x); ax.set_xticklabels(labels, fontsize=7)
        ax.set_ylabel("Focus score (%)"); ax.set_ylim(0,105)
        ax.set_title("Focus Score Trend", fontsize=12, fontweight="bold", pad=10)
        ax.grid(axis="y", color=C_WARM3, linewidth=0.6, zorder=1)
        fig.tight_layout(); fig.savefig(f"{CHARTS_DIR}/focus_trend.png", dpi=140, bbox_inches="tight"); plt.close(fig)
