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

STYLES = {
    PHASE_WORK:        {"fg": "#e74c3c", "bg": "#2c3e50", "label": "专注中", "msg": "专注结束！休息一下吧。"},
    PHASE_SHORT_BREAK: {"fg": "#2ecc71", "bg": "#2c3e50", "label": "短休息", "msg": "休息结束，开始新的专注！"},
    PHASE_LONG_BREAK:  {"fg": "#3498db", "bg": "#2c3e50", "label": "长休息", "msg": "专注结束！来一次长休息。"},
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

    def _build_ui(self):
        root = tk.Tk()
        root.title("番茄钟")
        root.geometry("340x490")
        root.resizable(False, False)
        root.attributes("-topmost", self.timer.config["always_on_top"])
        self.root = root

        self._build_canvas()
        self._build_stats()
        self._build_buttons()
        self._build_phase_toggle()
        self._build_settings_panel()

        root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_canvas(self):
        self.canvas = tk.Canvas(self.root, width=240, height=240,
                                highlightthickness=0)
        self.canvas.pack(pady=(30, 5))
        cx, cy, r = 120, 120, 100

        self.canvas.create_oval(cx - r, cy - r, cx + r, cy + r,
                                outline="#34495e", width=4)
        for i in range(60):
            angle = pi / 2 - (i / 60) * 2 * pi
            inner_r, line_w = (85, 3) if i % 5 == 0 else (90, 1)
            self.canvas.create_line(
                cx + inner_r * cos(angle), cy - inner_r * sin(angle),
                cx + r * cos(angle),      cy - r * sin(angle),
                fill="#7f8c8d", width=line_w,
            )

        self._arc = self.canvas.create_arc(
            cx - r + 5, cy - r + 5, cx + r - 5, cy + r - 5,
            start=90, extent=0, outline="", width=6, style="arc",
        )
        self._time_text = self.canvas.create_text(
            cx, cy + 5, text="25:00",
            font=("Helvetica", 40, "bold"), fill="white",
        )
        self._phase_text = self.canvas.create_text(
            cx, cy - 60, font=("Helvetica", 14), anchor="center",
        )

    def _build_stats(self):
        self._stats_label = tk.Label(self.root, font=("Helvetica", 11), fg="#bdc3c7")
        self._stats_label.pack(pady=(0, 8))

    def _build_buttons(self):
        btn_frame = tk.Frame(self.root)
        btn_frame.pack(pady=5)
        self._btn_start = self._mkbtn(btn_frame, "▶ 开始", "#27ae60", self._on_start)
        self._btn_start.pack(side=tk.LEFT, padx=4)
        self._btn_pause = self._mkbtn(btn_frame, "⏸ 暂停", "#f39c12", self._on_pause)
        self._btn_pause.pack(side=tk.LEFT, padx=4)
        self._btn_reset = self._mkbtn(btn_frame, "↺ 重置", "#e74c3c", self._on_reset)
        self._btn_reset.pack(side=tk.LEFT, padx=4)

    def _build_phase_toggle(self):
        toggle_frame = tk.Frame(self.root)
        toggle_frame.pack(pady=12)
        tk.Label(toggle_frame, text="模式:", font=("Helvetica", 10),
                 fg="#bdc3c7").pack(side=tk.LEFT, padx=(0, 8))
        self._phase_var = tk.StringVar(value=PHASE_WORK)
        for phase, label in [(PHASE_WORK, "专注"), (PHASE_SHORT_BREAK, "短休"), (PHASE_LONG_BREAK, "长休")]:
            tk.Radiobutton(toggle_frame, text=label, variable=self._phase_var, value=phase,
                           command=self._on_phase_change,
                           fg="#ecf0f1", selectcolor="#34495e",
                           activebackground="#34495e",
                           font=("Helvetica", 10)).pack(side=tk.LEFT, padx=4)

    def _build_settings_panel(self):
        self._settings_frame = tk.Frame(self.root, bg="#34495e")
        fields = [
            ("work_minutes",        "专注 (分钟)", 1, 120),
            ("short_break_minutes", "短休 (分钟)", 1, 30),
            ("long_break_minutes",  "长休 (分钟)", 1, 60),
            ("long_break_interval", "长休间隔 (个)", 1, 10),
            ("daily_goal",          "每日目标 (个)", 1, 30),
        ]
        self._settings_entries = {}
        for key, label, lo, hi in fields:
            f = tk.Frame(self._settings_frame, bg="#34495e")
            f.pack(fill=tk.X, padx=15, pady=3)
            tk.Label(f, text=label, bg="#34495e", fg="#ecf0f1",
                     font=("Helvetica", 10), width=14, anchor="w").pack(side=tk.LEFT)
            var = tk.StringVar(value=str(self.timer.config[key]))
            tk.Spinbox(f, from_=lo, to=hi, textvariable=var, width=8,
                       font=("Helvetica", 10)).pack(side=tk.RIGHT)
            self._settings_entries[key] = (var, lo, hi)

        tk.Button(self._settings_frame, text="保存设置", bg="#27ae60",
                  fg="white", relief="flat", padx=20, pady=4,
                  command=self._save_settings).pack(pady=(10, 5))

        self._atop_var = tk.BooleanVar(value=self.timer.config["always_on_top"])
        tk.Checkbutton(self._settings_frame, text="窗口置顶",
                       variable=self._atop_var, bg="#34495e", fg="#ecf0f1",
                       selectcolor="#34495e", activebackground="#34495e",
                       command=self._toggle_on_top).pack(pady=(0, 10))

        self._settings_btn = tk.Button(self.root, text="⚙ 设置", bg="#7f8c8d",
                                       fg="white", relief="flat", padx=15,
                                       command=self._toggle_settings)
        self._settings_btn.pack(pady=(5, 10))

    @staticmethod
    def _mkbtn(parent, text, color, cmd):
        return tk.Button(parent, text=text, bg=color, fg="white",
                         relief="flat", padx=12, pady=6, font=("Helvetica", 11),
                         activebackground=color, activeforeground="white",
                         cursor="hand2", command=cmd)

    def _sync(self):
        timer = self.timer
        style = timer.style
        self.canvas.itemconfigure(self._time_text, text=timer.time_str)
        self.canvas.itemconfigure(self._phase_text, text=style["label"], fill=style["fg"])
        self.canvas.itemconfigure(self._arc, extent=timer.progress * 360, outline=style["fg"])
        self.root.configure(bg=style["bg"])
        self.canvas.configure(bg=style["bg"])
        self._stats_label.configure(bg=style["bg"], text=self._stats_text())

    def _stats_text(self):
        timer = self.timer
        return f"今日已完成: {timer.today_completed} 个番茄  |  目标: {timer.config['daily_goal']} 个"

    # -- tick loop -----------------------------------------------------

    def _tick(self):
        result = self.timer.tick()
        if result is None:
            return
        self._sync()
        if result != "continue":
            winsound.PlaySound("SystemExclamation", winsound.SND_ALIAS)
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
            self._settings_frame.pack(fill=tk.X, padx=10, pady=(0, 10))
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
        messagebox.showinfo("设置", "已保存")

    def _toggle_on_top(self):
        v = self._atop_var.get()
        self.root.attributes("-topmost", v)
        self.timer.config["always_on_top"] = v

    def _on_close(self):
        self._stop_timer()
        self.root.destroy()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    PomodoroApp().run()
