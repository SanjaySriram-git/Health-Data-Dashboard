import csv
import os
import random
import threading
import time
import tkinter as tk
from datetime import datetime
from tkinter import filedialog, messagebox

import pandas as pd


SOURCE = "serial"

SERIAL_PORT = "COM3"
BAUD_RATE = 9600
COLUMNS = ["heart_rate", "steps", "distance", "sleep", "activity_duration"]
UNITS = {"heart_rate": "bpm", "steps": "steps", "distance": "km",
         "sleep": "hours", "activity_duration": "min"}
LOG_FILE = "watch_log.csv"
REFRESH_SECONDS = 5
SUM_KEYWORDS = ("step", "distance", "sleep", "activ", "duration")


BG, CARD, LINE = "#0f172a", "#1e293b", "#334155"
TEXT, MUTED = "#f8fafc", "#94a3b8"
ACCENT, GREEN, AMBER = "#6366f1", "#34d399", "#fbbf24"
COLORS = ["#fb7185", "#38bdf8", "#34d399", "#fbbf24", "#c084fc"]
FONT = "Segoe UI"

STATUS = {"msg": "Starting..."}
_lock = threading.Lock()


def save_row(values):
    with _lock:
        is_new = not os.path.exists(LOG_FILE)
        with open(LOG_FILE, "a", newline="") as f:
            w = csv.writer(f)
            if is_new:
                w.writerow(["timestamp"] + COLUMNS)
            w.writerow([datetime.now().isoformat(timespec="seconds")] + values)


def serial_worker():
    import serial
    while True:
        try:
            with serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=2) as ser:
                STATUS["msg"] = f"Connected to {SERIAL_PORT}"
                while True:
                    line = ser.readline().decode(errors="ignore").strip()
                    parts = line.split(",")
                    if len(parts) != len(COLUMNS):
                        continue
                    try:
                        save_row([float(p) for p in parts])
                    except ValueError:
                        continue
        except Exception:
            STATUS["msg"] = f"Waiting for watch on {SERIAL_PORT}"
            time.sleep(3)


def load() -> pd.DataFrame:
    if not os.path.exists(LOG_FILE):
        return pd.DataFrame()
    try:
        with _lock:
            df = pd.read_csv(LOG_FILE)
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
        return df.dropna(subset=["timestamp"]).sort_values("timestamp")
    except Exception:
        return pd.DataFrame()


def demo_data() -> pd.DataFrame:
    random.seed(7)
    idx = pd.date_range(end=pd.Timestamp.now().floor("h"), periods=24 * 10, freq="h")
    ranges = {"heart_rate": (62, 95), "steps": (50, 700), "distance": (0.05, 0.5),
              "activity_duration": (0, 8)}
    data = {"timestamp": idx}
    for c in COLUMNS:
        vals = []
        for t in idx:
            asleep = t.hour < 7
            if c == "sleep":
                v = random.uniform(0.8, 1.0) if asleep else 0
            elif asleep and c != "heart_rate":
                v = 0
            else:
                lo, hi = ranges.get(c, (0, 100))
                v = random.uniform(lo, hi)
            vals.append(round(v, 2))
        data[c] = vals
    return pd.DataFrame(data)


def summarize(df: pd.DataFrame, freq: str) -> pd.DataFrame:
    data = df.set_index("timestamp").select_dtypes("number")
    sum_cols = [c for c in data.columns if any(k in c.lower() for k in SUM_KEYWORDS)]
    avg_cols = [c for c in data.columns if c not in sum_cols]

    agg = {c: "sum" for c in sum_cols}
    agg.update({c: ["mean", "min", "max"] for c in avg_cols})

    out = data.resample(freq).agg(agg)
    out.columns = [c if isinstance(c, str) else
                   (c[0] if c[1] == "sum" else f"{c[0]}_{c[1]}") for c in out.columns]
    out["readings"] = data.resample(freq).size()
    out = out[out["readings"] > 0].round(1)
    if freq == "D":
        out.index = [d.strftime("%A, %d %b %Y") for d in out.index]
        out.index.name = "Day"
    else:
        out.index = [f"{(d - pd.Timedelta(days=6)):%d %b} - {d:%d %b %Y}" for d in out.index]
        out.index.name = "Week"
    return out.iloc[::-1]


def pretty(name: str) -> str:
    return name.replace("_", " ").title()


def fmt(v) -> str:
    return f"{v:,.0f}" if abs(v) >= 100 else f"{v:,.1f}"


class Card(tk.Canvas):
    def __init__(self, parent, color):
        super().__init__(parent, bg=BG, highlightthickness=0, height=200)
        self.color = color
        self.content = ("", "--", "", [])
        self.bind("<Configure>", lambda e: self.draw())

    def set(self, title, value, unit, stats):
        self.content = (title, value, unit, stats)
        self.draw()

    def rounded(self, x1, y1, x2, y2, r, **kw):
        pts = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
               x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
        return self.create_polygon(pts, smooth=True, **kw)

    def draw(self):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if w < 50:
            return
        title, value, unit, stats = self.content
        self.rounded(2, 2, w - 2, h - 2, 28, fill=CARD, outline="")
        self.create_oval(26, 28, 40, 42, fill=self.color, outline="")
        self.create_text(52, 35, text=title.upper(), anchor="w", fill=MUTED,
                         font=(FONT, 11, "bold"))
        size = int(max(24, min(54, w / 5.5, h * 0.22)))
        self.create_text(w / 2, h * 0.37, text=value, fill=TEXT, font=(FONT, size, "bold"))
        self.create_text(w / 2, h * 0.37 + size * 0.85, text=unit, fill=self.color,
                         font=(FONT, 11, "bold"))
        self.create_line(28, h - 70, w - 28, h - 70, fill=LINE)
        for i, (cap, val) in enumerate(stats):
            x = w * (i + 1) / (len(stats) + 1)
            self.create_text(x, h - 52, text=cap, fill=MUTED, font=(FONT, 9, "bold"))
            self.create_text(x, h - 28, text=val, fill=TEXT, font=(FONT, 16, "bold"))


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Watch Summary")
        self.geometry("1100x860")
        self.minsize(900, 720)
        self.configure(bg=BG)
        self.mode, self.idx = "D", 0
        self.daily = self.weekly = None
        self.last_ts, self.live, self.latest_base = None, False, ""

        foot = tk.Frame(self, bg=BG)
        foot.pack(side="bottom", fill="x", padx=34, pady=(0, 22))
        self.pill = tk.Label(foot, text="", font=(FONT, 9, "bold"), padx=12, pady=5)
        self.pill.pack(side="left")
        self.latest = tk.Label(foot, text="", font=(FONT, 10), bg=BG, fg=MUTED)
        self.latest.pack(side="left", padx=14)
        export = tk.Label(foot, text="Export CSV", font=(FONT, 10, "bold"), bg=BG,
                          fg=ACCENT, cursor="hand2")
        export.pack(side="right")
        export.bind("<Button-1>", lambda e: self.export())

        top = tk.Frame(self, bg=BG)
        top.pack(fill="x", padx=34, pady=(26, 0))
        tk.Label(top, text="⌚  Watch Summary", font=(FONT, 24, "bold"),
                 bg=BG, fg=TEXT).pack(side="left")
        switch = tk.Frame(top, bg=CARD)
        switch.pack(side="right")
        self.btn = {"D": self.pill_button(switch, "Daily", "D"),
                    "W": self.pill_button(switch, "Weekly", "W")}

        self.banner = tk.Label(self, text="", font=(FONT, 10, "bold"), pady=9)
        self.banner.pack(fill="x", padx=34, pady=(18, 0))

        nav = tk.Frame(self, bg=BG)
        nav.pack(pady=(16, 12))
        self.prev = tk.Label(nav, text="‹", font=(FONT, 30), bg=BG, fg=TEXT,
                             cursor="hand2", padx=22)
        self.prev.pack(side="left")
        mid = tk.Frame(nav, bg=BG, width=360)
        mid.pack(side="left")
        mid.pack_propagate(False)
        mid.configure(height=62)
        self.period = tk.Label(mid, text="", font=(FONT, 20, "bold"), bg=BG, fg=TEXT)
        self.period.pack(pady=(2, 0))
        self.period_sub = tk.Label(mid, text="", font=(FONT, 11), bg=BG, fg=MUTED)
        self.period_sub.pack()
        self.next = tk.Label(nav, text="›", font=(FONT, 30), bg=BG, fg=TEXT,
                             cursor="hand2", padx=22)
        self.next.pack(side="left")
        self.prev.bind("<Button-1>", lambda e: self.step(+1))
        self.next.bind("<Button-1>", lambda e: self.step(-1))

        grid = tk.Frame(self, bg=BG)
        grid.pack(fill="both", expand=True, padx=26)
        n = len(COLUMNS)
        per_row = n if n <= 3 else (2 if n == 4 else 3)
        for c in range(6):
            grid.columnconfigure(c, weight=1, uniform="c")
        self.cards = []
        for i in range(n):
            r, pos = divmod(i, per_row)
            in_row = min(per_row, n - r * per_row)
            span = 6 // in_row
            card = Card(grid, COLORS[i % len(COLORS)])
            card.grid(row=r, column=pos * span, columnspan=span, padx=8, pady=8, sticky="nsew")
            grid.rowconfigure(r, weight=1)
            self.cards.append(card)

        self.style_switch()
        self.tick()
        self.refresh()

    def pill_button(self, parent, text, mode):
        b = tk.Label(parent, text=text, font=(FONT, 11, "bold"), padx=24, pady=9, cursor="hand2")
        b.pack(side="left", padx=3, pady=3)
        b.bind("<Button-1>", lambda e: self.set_mode(mode))
        return b

    def style_switch(self):
        for m, b in self.btn.items():
            b.config(bg=ACCENT if m == self.mode else CARD,
                     fg="white" if m == self.mode else MUTED)

    def set_mode(self, mode):
        self.mode, self.idx = mode, 0
        self.style_switch()
        self.show()

    def step(self, d):
        self.idx += d
        self.show()

    def show(self):
        if self.daily is None:
            return
        s = self.daily if self.mode == "D" else self.weekly
        self.idx = max(0, min(self.idx, len(s) - 1))
        row = s.iloc[self.idx]

        names = ("Today", "Yesterday") if self.mode == "D" else ("This week", "Last week")
        self.period.config(text=names[self.idx] if self.idx < 2 else s.index[self.idx])
        count = f"{int(row['readings'])} readings"
        self.period_sub.config(text=f"{s.index[self.idx]}  ·  {count}" if self.idx < 2 else count)
        self.prev.config(fg=TEXT if self.idx < len(s) - 1 else LINE)
        self.next.config(fg=TEXT if self.idx > 0 else LINE)

        prev = s.iloc[self.idx + 1] if self.idx + 1 < len(s) else None
        prev_name = "PREVIOUS DAY" if self.mode == "D" else "PREVIOUS WEEK"
        for card, col in zip(self.cards, COLUMNS):
            unit = UNITS.get(col, "")
            if col in row.index:
                before = fmt(prev[col]) if prev is not None else "-"
                card.set(pretty(col), fmt(row[col]), f"{unit} total".strip(),
                         [(prev_name, before)])
            else:
                card.set(pretty(col), f"{row[col + '_mean']:g}", f"{unit} average".strip(),
                         [("LOWEST", f"{row[col + '_min']:g}"),
                          ("HIGHEST", f"{row[col + '_max']:g}")])

    def export(self):
        if self.daily is None:
            return
        folder = filedialog.askdirectory(title="Choose a folder to save the summaries")
        if not folder:
            return
        self.daily.to_csv(os.path.join(folder, "daily_summary.csv"))
        self.weekly.to_csv(os.path.join(folder, "weekly_summary.csv"))
        messagebox.showinfo("Exported", f"Saved daily_summary.csv and weekly_summary.csv in:\n{folder}")

    def tick(self):
        text = self.latest_base
        if self.live and self.last_ts is not None:
            secs = max(0, int((datetime.now() - self.last_ts).total_seconds()))
            text += f"   ·   {secs} s ago" if secs < 120 else f"   ·   {secs // 60} min ago"
        self.latest.config(text=text)
        self.after(1000, self.tick)

    def refresh(self):
        df = load()
        self.live = not df.empty
        if not self.live:
            df = demo_data()
            self.pill.config(text="●  SAMPLE DATA", bg="#3b2f12", fg=AMBER)
            self.banner.config(bg="#3b2f12", fg=AMBER,
                               text="SAMPLE DATA (demo)  -  switches to live watch data "
                                    "automatically when the first reading arrives")
        else:
            self.pill.config(text="●  LIVE", bg="#12372a", fg=GREEN)
            self.banner.config(bg="#12372a", fg=GREEN, text="●  LIVE DATA FROM THE WATCH")

        last = df.iloc[-1]
        self.last_ts = last["timestamp"].to_pydatetime()
        vals = "   ".join(f"{last[c]:g} {UNITS.get(c, '')}".strip() for c in COLUMNS)
        self.latest_base = f"Latest reading:  {vals}   ·   {STATUS['msg']}"

        self.daily, self.weekly = summarize(df, "D"), summarize(df, "W")
        self.show()
        self.after(REFRESH_SECONDS * 1000, self.refresh)


if __name__ == "__main__":
    if SOURCE == "serial":
        threading.Thread(target=serial_worker, daemon=True).start()
    else:
        STATUS["msg"] = f"Reading {LOG_FILE}"
    App().mainloop()
