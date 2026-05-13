import tkinter as tk
from tkinter import messagebox
import winsound
import json
import os
from datetime import datetime
from math import pi, cos, sin


DATA_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(DATA_DIR, "config.json")
STATS_FILE = os.path.join(DATA_DIR, "stats.json")
DATE_FMT = "%Y-%m-%d"

STATE_IDLE = "idle"
STATE_RUNNING = "running"
STATE_PAUSED = "paused"

PHASE_WORK = "work"
PHASE_SHORT_BREAK = "short_break"
PHASE_LONG_BREAK = "long_break"

DEFAULT_CONFIG = {
    "work_minutes": 25,
    "short_break_minutes": 5,
    "long_break_minutes": 15,
    "long_break_interval": 4,
    "daily_goal": 8,
    "always_on_top": True,
}

# Catppuccin Mocha palette
BASE    = "#1e1e2e"
MANTLE  = "#181825"
CRUST   = "#11111b"
SURFACE = "#313244"
OVERLAY = "#585b70"
SUBTLE  = "#6c7086"
TEXT    = "#cdd6f4"
BLUE    = "#89b4fa"
GREEN   = "#a6e3a1"
RED     = "#f38ba8"
PEACH   = "#fab387"
YELLOW  = "#f9e2af"
MAUVE   = "#cba6f7"
WHITE   = "#ffffff"

STYLES = {
    PHASE_WORK:        {"fg": RED,   "label": "专注中", "msg": "专注结束！休息一下吧。"},
    PHASE_SHORT_BREAK: {"fg": GREEN, "label": "短休息", "msg": "休息结束，开始新的专注！"},
    PHASE_LONG_BREAK:  {"fg": BLUE,  "label": "长休息", "msg": "专注结束！来一次长休息。"},
}


class PomodoroTimer:
    """Pure state machine — no UI dependencies."""

    def __init__(self):
        self.load_config()
        self.load_today_stats()
        self.state = STATE_IDLE
        self.phase = PHASE_WORK
        self.remaining = 0
        self.total_seconds = 0
        self._reset_remaining()

    # -- persistence ---------------------------------------------------

    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE) as f:
                saved = json.load(f)
                for k in DEFAULT_CONFIG:
                    saved.setdefault(k, DEFAULT_CONFIG[k])
                self.config = saved
        else:
            self.config = dict(DEFAULT_CONFIG)
            self.save_config()

    def save_config(self):
        with open(CONFIG_FILE, "w") as f:
            json.dump(self.config, f, indent=2)

    def load_today_stats(self):
        today = datetime.now().strftime(DATE_FMT)
        if os.path.exists(STATS_FILE):
            with open(STATS_FILE) as f:
                s = json.load(f)
            if s.get("date") == today:
                self.today_completed = s.get("completed", 0)
                return
        self.today_completed = 0
        with open(STATS_FILE, "w") as f:
            json.dump({"date": today, "completed": 0}, f)

    def save_today_stats(self):
        with open(STATS_FILE, "w") as f:
            json.dump({
                "date": datetime.now().strftime(DATE_FMT),
                "completed": self.today_completed,
            }, f)

    # -- phase / duration helpers --------------------------------------

    def _reset_remaining(self):
        cfg = self.config
        if self.phase == PHASE_WORK:
            self.total_seconds = cfg["work_minutes"] * 60
        elif self.phase == PHASE_SHORT_BREAK:
            self.total_seconds = cfg["short_break_minutes"] * 60
        else:
            self.total_seconds = cfg["long_break_minutes"] * 60
        self.remaining = self.total_seconds

    def switch_phase(self, phase):
        self.phase = phase
        self._reset_remaining()

    # -- actions -------------------------------------------------------

    def start(self):
        if self.state == STATE_IDLE:
            self._reset_remaining()
            self.state = STATE_RUNNING
            return True
        if self.state == STATE_PAUSED:
            self.state = STATE_RUNNING
            return True
        return False

    def pause(self):
        if self.state == STATE_RUNNING:
            self.state = STATE_PAUSED
            return True
        return False

    def reset(self):
        self.state = STATE_IDLE
        self._reset_remaining()

    def tick(self):
        if self.state != STATE_RUNNING:
            return None
        self.remaining -= 1
        if self.remaining <= 0:
            return self._finish_phase()
        return "continue"

    def _finish_phase(self):
        self.state = STATE_IDLE
        if self.phase == PHASE_WORK:
            self.today_completed += 1
            self.save_today_stats()
            next_phase = (PHASE_LONG_BREAK
                          if self.today_completed % self.config["long_break_interval"] == 0
                          else PHASE_SHORT_BREAK)
        else:
            next_phase = PHASE_WORK
        self.switch_phase(next_phase)
        return next_phase

    # -- display helpers -----------------------------------------------

    @property
    def time_str(self):
        return f"{self.remaining // 60:02d}:{self.remaining % 60:02d}"

    @property
    def progress(self):
        return self.remaining / self.total_seconds if self.total_seconds > 0 else 0

    @property
    def style(self):
        return STYLES[self.phase]


# ---------------------------------------------------------------------------
# GUI
# ---------------------------------------------------------------------------

class PomodoroApp:
    def __init__(self):
        self.timer = PomodoroTimer()
        self._timer_id = None
        self._settings_visible = False
        self._build_ui()
        self._sync()

    def _stop_timer(self):
        if self._timer_id:
            self.root.after_cancel(self._timer_id)
            self._timer_id = None

    # -- widget builders -----------------------------------------------

    @staticmethod
    def _frame(parent, bg=None, **kw):
        return tk.Frame(parent, bg=bg or BASE, **kw)

    @staticmethod
    def _label(parent, text="", **kw):
        defaults = {"bg": BASE, "fg": TEXT, "font": ("Helvetica", 10)}
        defaults.update(kw)
        return tk.Label(parent, text=text, **defaults)

    def _btn(self, parent, text, color, cmd, width=None):
        kw = {
            "text": text, "bg": color, "fg": WHITE,
            "relief": "flat", "padx": 16, "pady": 8,
            "font": ("Helvetica", 11, "bold"),
            "activebackground": color, "activeforeground": WHITE,
            "cursor": "hand2", "command": cmd,
        }
        if width:
            kw["width"] = width
        return tk.Button(parent, **kw)

    # -- build UI ------------------------------------------------------

    def _build_ui(self):
        root = tk.Tk()
        root.title("番茄钟")
        root.geometry("360x520")
        root.resizable(False, False)
        root.configure(bg=BASE)
        root.attributes("-topmost", self.timer.config["always_on_top"])
        self.root = root

        self._build_header()
        self._build_canvas()
        self._build_stats()
        self._build_buttons()
        self._build_phase_toggle()
        self._build_settings_panel()

        root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_header(self):
        self._header_bar = tk.Frame(self.root, bg=MANTLE, height=36)
        self._header_bar.pack(fill=tk.X)
        self._header_bar.pack_propagate(False)

        self._settings_btn = self._btn(self._header_bar, "⚙", OVERLAY,
                                       self._toggle_settings, width=3)
        self._settings_btn.pack(side=tk.RIGHT, padx=(0, 6), pady=3)

        title = tk.Label(self._header_bar, text="🍅 番茄钟",
                         bg=MANTLE, fg=TEXT,
                         font=("Helvetica", 12, "bold"))
        title.pack(side=tk.LEFT, padx=12)

    def _build_canvas(self):
        self.canvas = tk.Canvas(self.root, width=240, height=240,
                                bg=BASE, highlightthickness=0)
        self.canvas.pack(pady=(24, 4))
        cx, cy, r = 120, 120, 100

        # outer glow ring
        self.canvas.create_oval(cx - r - 4, cy - r - 4,
                                cx + r + 4, cy + r + 4,
                                outline=OVERLAY, width=1)

        # track ring
        self.canvas.create_oval(cx - r, cy - r, cx + r, cy + r,
                                outline=SURFACE, width=6)

        # tick marks
        for i in range(60):
            angle = pi / 2 - (i / 60) * 2 * pi
            inner_r, line_w = (86, 3) if i % 5 == 0 else (91, 1)
            self.canvas.create_line(
                cx + inner_r * cos(angle), cy - inner_r * sin(angle),
                cx + r * cos(angle),      cy - r * sin(angle),
                fill=SUBTLE if i % 5 == 0 else OVERLAY, width=line_w,
            )

        # progress arc
        self._arc = self.canvas.create_arc(
            cx - r + 3, cy - r + 3, cx + r - 3, cy + r - 3,
            start=90, extent=0, outline="", width=6, style="arc",
        )

        # time text
        self._time_text = self.canvas.create_text(
            cx, cy + 6, text="25:00",
            font=("Helvetica", 42, "bold"), fill=TEXT,
        )

        # phase label
        self._phase_text = self.canvas.create_text(
            cx, cy - 56, font=("Helvetica", 13), anchor="center",
        )

    def _build_stats(self):
        self._stats_label = self._label(self.root, fg=SUBTLE,
                                        font=("Helvetica", 10))
        self._stats_label.pack(pady=(4, 2))

        # progress dots
        self._dots_frame = self._frame(self.root)
        self._dots_frame.pack(pady=(2, 4))
        self._dot_labels = []

    def _refresh_dots(self):
        for w in self._dots_frame.winfo_children():
            w.destroy()
        self._dot_labels.clear()
        goal = self.timer.config["daily_goal"]
        done = min(self.timer.today_completed, goal)
        for i in range(goal):
            color = RED if i < done else SURFACE
            lbl = tk.Label(self._dots_frame, text="⬤", fg=color, bg=BASE,
                           font=("Helvetica", 8))
            lbl.pack(side=tk.LEFT, padx=2)
            self._dot_labels.append(lbl)

    def _build_buttons(self):
        btn_frame = self._frame(self.root)
        btn_frame.pack(pady=(8, 4))

        self._btn_start  = self._btn(btn_frame, "▶ 开始", GREEN, self._on_start)
        self._btn_pause  = self._btn(btn_frame, "⏸ 暂停", YELLOW, self._on_pause)
        self._btn_reset  = self._btn(btn_frame, "↺ 重置", SUBTLE, self._on_reset)

        self._btn_start.pack(side=tk.LEFT, padx=5)
        self._btn_pause.pack(side=tk.LEFT, padx=5)
        self._btn_reset.pack(side=tk.LEFT, padx=5)

    def _build_phase_toggle(self):
        toggle_frame = self._frame(self.root)
        toggle_frame.pack(pady=(6, 2))

        self._phase_var = tk.StringVar(value=PHASE_WORK)
        phases = [(PHASE_WORK, "专注"), (PHASE_SHORT_BREAK, "短休"), (PHASE_LONG_BREAK, "长休")]
        for i, (val, label) in enumerate(phases):
            rb = tk.Radiobutton(toggle_frame, text=label, variable=self._phase_var,
                                value=val, command=self._on_phase_change,
                                bg=BASE, fg=SUBTLE, selectcolor=BASE,
                                activebackground=BASE, activeforeground=TEXT,
                                font=("Helvetica", 11),
                                indicatoron=False, padx=16, pady=4,
                                relief="flat", overrelief="flat",
                                borderwidth=0, highlightthickness=0)
            rb.pack(side=tk.LEFT, padx=3)

    def _build_settings_panel(self):
        self._settings_frame = self._frame(self.root, bg=MANTLE)
        fields = [
            ("work_minutes",        "专注时长", 1, 120),
            ("short_break_minutes", "短休时长", 1, 30),
            ("long_break_minutes",  "长休时长", 1, 60),
            ("long_break_interval", "长休间隔", 1, 10),
            ("daily_goal",          "每日目标", 1, 30),
        ]
        self._settings_entries = {}
        for key, label, lo, hi in fields:
            f = self._frame(self._settings_frame, bg=MANTLE)
            f.pack(fill=tk.X, padx=20, pady=3)
            self._label(f, text=label, bg=MANTLE,
                        font=("Helvetica", 10), width=10,
                        anchor="w").pack(side=tk.LEFT)
            var = tk.StringVar(value=str(self.timer.config[key]))
            sb = tk.Spinbox(f, from_=lo, to=hi, textvariable=var, width=6,
                            bg=SURFACE, fg=TEXT, buttonbackground=SURFACE,
                            relief="flat", font=("Helvetica", 10))
            sb.pack(side=tk.RIGHT)
            self._settings_entries[key] = (var, lo, hi)

        btn_row = self._frame(self._settings_frame, bg=MANTLE)
        btn_row.pack(pady=(10, 6))

        self._btn_save = self._btn(btn_row, "✓ 保存", GREEN, self._save_settings)
        self._btn_save.pack(side=tk.LEFT, padx=4)

        self._atop_var = tk.BooleanVar(value=self.timer.config["always_on_top"])
        cb = tk.Checkbutton(btn_row, text="置顶", variable=self._atop_var,
                            bg=MANTLE, fg=TEXT, selectcolor=MANTLE,
                            activebackground=MANTLE, activeforeground=TEXT,
                            font=("Helvetica", 10),
                            command=self._toggle_on_top)
        cb.pack(side=tk.LEFT, padx=8)

    # -- sync UI -------------------------------------------------------

    def _sync(self):
        timer = self.timer
        style = timer.style

        self.canvas.itemconfigure(self._time_text, text=timer.time_str)
        self.canvas.itemconfigure(self._phase_text, text=style["label"],
                                  fill=style["fg"])
        self.canvas.itemconfigure(self._arc, extent=timer.progress * 360,
                                  outline=style["fg"])
        self._stats_label.configure(text=self._stats_text())

        # update phase radio button colors
        for child in self.root.winfo_children():
            self._walk_and_style(child, style["fg"])

    def _walk_and_style(self, widget, phase_fg):
        if isinstance(widget, tk.Radiobutton) and widget.cget("indicatoron") == "0":
            if widget.cget("value") == self.timer.phase:
                widget.configure(bg=phase_fg, fg=BASE)
            else:
                widget.configure(bg=SURFACE, fg=SUBTLE)
        elif isinstance(widget, tk.Frame):
            for child in widget.winfo_children():
                self._walk_and_style(child, phase_fg)

    def _stats_text(self):
        t = self.timer
        return f"今日完成 {t.today_completed} / {t.config['daily_goal']} 个番茄"

    # -- tick loop -----------------------------------------------------

    def _tick(self):
        result = self.timer.tick()
        if result is None:
            return
        self._sync()
        if result != "continue":
            winsound.PlaySound("SystemExclamation", winsound.SND_ALIAS)
            self._refresh_dots()
            messagebox.showinfo("番茄钟", self.timer.style["msg"])
            self._sync()
        else:
            self._timer_id = self.root.after(1000, self._tick)

    # -- callbacks -----------------------------------------------------

    def _on_start(self):
        if self.timer.start():
            self._tick()

    def _on_pause(self):
        if self.timer.pause():
            self._stop_timer()

    def _on_reset(self):
        self._stop_timer()
        self.timer.reset()
        self._sync()

    def _on_phase_change(self):
        if self.timer.state != STATE_IDLE:
            messagebox.showwarning("提示", "请先重置再切换模式")
            self._phase_var.set(self.timer.phase)
            return
        self.timer.switch_phase(self._phase_var.get())
        self._sync()

    def _toggle_settings(self):
        if self._settings_visible:
            self._settings_frame.pack_forget()
        else:
            self._settings_frame.pack(fill=tk.X, padx=0, pady=(6, 0))
        self._settings_visible = not self._settings_visible

    def _save_settings(self):
        for key, (var, lo, hi) in self._settings_entries.items():
            try:
                val = max(lo, min(hi, int(var.get())))
                self.timer.config[key] = val
            except ValueError:
                pass
        self.timer.config["always_on_top"] = self._atop_var.get()
        self.timer.save_config()
        self.root.attributes("-topmost", self.timer.config["always_on_top"])
        if self.timer.state == STATE_IDLE:
            self.timer.switch_phase(self.timer.phase)
        self._sync()
        self._refresh_dots()
        messagebox.showinfo("设置", "已保存")

    def _toggle_on_top(self):
        v = self._atop_var.get()
        self.root.attributes("-topmost", v)
        self.timer.config["always_on_top"] = v

    def _on_close(self):
        self._stop_timer()
        self.root.destroy()

    def run(self):
        self._refresh_dots()
        self.root.mainloop()


if __name__ == "__main__":
    PomodoroApp().run()
