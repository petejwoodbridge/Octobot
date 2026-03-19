"""
OctoBot Progress Monitor
A small desktop window showing live progress of background tasks.
Updates every 20 seconds. Run: python progress_monitor.py
"""
import tkinter as tk
from tkinter import ttk
import re, time, json, os, threading
from pathlib import Path

BASE = Path(__file__).parent
LOG  = BASE / "expand_log.txt"
MEM  = BASE / "workspace" / "memory.json"

# Colour palette
BG      = "#0d0020"
FG      = "#e0e0ff"
PINK    = "#ff2d9b"
CYAN    = "#00f7ff"
PURPLE  = "#bf00ff"
GREEN   = "#00ff88"
YELLOW  = "#ffd700"
GREY    = "#554477"

REFRESH_MS = 20_000   # 20 seconds

# ── helpers ────────────────────────────────────────────────────────
def _read_locked_file(path):
    """Read a file that may be locked by another process (Windows-safe)."""
    import subprocess
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             f"Get-Content -LiteralPath '{path}' -Raw -Encoding UTF8"],
            capture_output=True, text=True, timeout=8
        )
        return r.stdout
    except Exception:
        return ""


def read_expand_log():
    """Parse expand_log.txt for progress info."""
    if not LOG.exists():
        return {"done": 0, "total": 0, "current": "", "finished": False,
                "ok": 0, "skipped": 0, "rate": 0}
    text = _read_locked_file(LOG)
    if not text:
        return {"done": 0, "total": 0, "current": "", "finished": False,
                "ok": 0, "skipped": 0, "rate": 0}

    total_m = re.search(r"Found (\d+) files", text)
    total   = int(total_m.group(1)) if total_m else 0

    done_lines = re.findall(r"\[(\d+)/\d+\]", text)
    done  = int(done_lines[-1]) if done_lines else 0

    cur_lines = re.findall(r"\[(\d+)/\d+\]\s+(.+)", text)
    current   = cur_lines[-1][1].strip() if cur_lines else ""

    ok      = text.count("    OK ")
    skipped = text.count("    SKIP") + text.count("    ERROR")

    finished = "Done. Fixed:" in text or "Nothing to do" in text

    return {"done": done, "total": total, "current": current,
            "finished": finished, "ok": ok, "skipped": skipped}


def read_memory():
    """Return score, level name, idea count, event count from memory.json."""
    if not MEM.exists():
        return {}
    try:
        data = json.loads(MEM.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return {}
    events = data.get("events", [])
    last_events = [e.get("detail", "") for e in events[-5:]][::-1]
    return {
        "score":       data.get("score", 0),
        "ideas":       data.get("total_ideas", 0),
        "research":    data.get("total_research", 0),
        "level":       data.get("level_name", ""),
        "last_events": last_events,
    }


def server_running():
    """Quick check if the Flask server is up."""
    try:
        import urllib.request
        urllib.request.urlopen("http://localhost:7860/api/score", timeout=1)
        return True
    except Exception:
        return False


# ── UI ─────────────────────────────────────────────────────────────
class MonitorApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("OctoBot Progress Monitor")
        self.configure(bg=BG)
        self.resizable(False, False)
        self.geometry("520x580+60+60")   # initial safe position
        self.after(200, self._reposition)  # move after window is rendered

        self._start_time = time.time()
        self._last_done  = 0
        self._rates      = []

        self._build_ui()
        self._refresh()

    def _reposition(self):
        sw = self.winfo_screenwidth()
        x  = sw - 540
        self.geometry(f"520x580+{x}+40")

    def _build_ui(self):
        pad = {"padx": 14, "pady": 4}

        # Title
        tk.Label(self, text="OctoBot  Monitor", font=("Segoe UI", 14, "bold"),
                 bg=BG, fg=PINK).pack(pady=(12, 2))

        # Server status
        self.server_var = tk.StringVar(value="Checking...")
        tk.Label(self, textvariable=self.server_var, font=("Segoe UI", 9),
                 bg=BG, fg=CYAN).pack()

        self._divider()

        # Library fix progress section
        tk.Label(self, text="Library Structure Fix", font=("Segoe UI", 10, "bold"),
                 bg=BG, fg=YELLOW).pack(**pad)

        self.progress_var = tk.StringVar(value="Loading...")
        tk.Label(self, textvariable=self.progress_var, font=("Consolas", 11),
                 bg=BG, fg=FG).pack()

        # Progress bar
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("pink.Horizontal.TProgressbar",
                        troughcolor=GREY, background=PINK,
                        darkcolor=PINK, lightcolor=PINK, bordercolor=BG)
        self.pbar = ttk.Progressbar(self, style="pink.Horizontal.TProgressbar",
                                    length=480, mode="determinate")
        self.pbar.pack(pady=4)

        self.eta_var = tk.StringVar(value="")
        tk.Label(self, textvariable=self.eta_var, font=("Segoe UI", 9),
                 bg=BG, fg=PURPLE).pack()

        self.cur_var = tk.StringVar(value="")
        tk.Label(self, textvariable=self.cur_var, font=("Consolas", 8),
                 bg=BG, fg=GREY, wraplength=490, justify="left").pack(padx=14)

        self._divider()

        # OctoBot stats
        tk.Label(self, text="OctoBot Stats", font=("Segoe UI", 10, "bold"),
                 bg=BG, fg=YELLOW).pack(**pad)

        self.stats_var = tk.StringVar(value="")
        tk.Label(self, textvariable=self.stats_var, font=("Consolas", 10),
                 bg=BG, fg=CYAN).pack()

        self._divider()

        # Recent activity
        tk.Label(self, text="Recent Activity", font=("Segoe UI", 10, "bold"),
                 bg=BG, fg=YELLOW).pack(**pad)

        self.events_frame = tk.Frame(self, bg=BG)
        self.events_frame.pack(fill="x", padx=14)
        self.event_labels = []
        for _ in range(5):
            lbl = tk.Label(self.events_frame, text="", font=("Segoe UI", 8),
                           bg=BG, fg=FG, anchor="w", wraplength=490, justify="left")
            lbl.pack(fill="x")
            self.event_labels.append(lbl)

        self._divider()

        # Last updated
        self.updated_var = tk.StringVar(value="")
        tk.Label(self, textvariable=self.updated_var, font=("Segoe UI", 8),
                 bg=BG, fg=GREY).pack(pady=(0, 8))

    def _divider(self):
        tk.Frame(self, bg=GREY, height=1).pack(fill="x", padx=12, pady=6)

    def _refresh(self):
        threading.Thread(target=self._fetch_and_update, daemon=True).start()
        self.after(REFRESH_MS, self._refresh)

    def _fetch_and_update(self):
        exp  = read_expand_log()
        mem  = read_memory()
        srv  = server_running()
        self.after(0, self._update_ui, exp, mem, srv)

    def _update_ui(self, exp, mem, srv):
        # Server
        self.server_var.set(
            f"Server: {'ONLINE  http://localhost:7860' if srv else 'OFFLINE'}"
        )

        # Progress
        done  = exp["done"]
        total = exp["total"]
        pct   = (done / total * 100) if total else 0

        if exp["finished"]:
            self.progress_var.set(f"COMPLETE!  {done} files fixed")
            self.pbar["value"] = 100
            self.eta_var.set("All done!")
        elif total == 0:
            self.progress_var.set("Waiting for expander to start...")
            self.pbar["value"] = 0
            self.eta_var.set("")
        else:
            self.progress_var.set(
                f"{done} / {total}  ({pct:.1f}%)    OK: {exp['ok']}   Skipped: {exp['skipped']}"
            )
            self.pbar["maximum"] = total
            self.pbar["value"]   = done

            # Rate & ETA
            elapsed = time.time() - self._start_time
            if done > 0 and elapsed > 10:
                rate = done / elapsed  # files/sec
                remaining = total - done
                eta_sec = remaining / rate if rate > 0 else 0
                if eta_sec > 3600:
                    eta_str = f"ETA ~{eta_sec/3600:.1f} hrs"
                elif eta_sec > 60:
                    eta_str = f"ETA ~{eta_sec/60:.0f} min"
                else:
                    eta_str = f"ETA ~{eta_sec:.0f} sec"
                self.eta_var.set(f"{rate*60:.0f} files/min  |  {eta_str}")
            else:
                self.eta_var.set("Calculating rate...")

        cur = exp.get("current", "")
        self.cur_var.set(f"Current: {cur[:80]}" if cur else "")

        # Stats
        if mem:
            self.stats_var.set(
                f"Score: {mem.get('score', 0):,}    "
                f"Ideas: {mem.get('ideas', 0):,}    "
                f"Research: {mem.get('research', 0):,}\n"
                f"Level: {mem.get('level', '?')}"
            )
        else:
            self.stats_var.set("(memory.json not found)")

        # Events
        events = mem.get("last_events", [])
        for i, lbl in enumerate(self.event_labels):
            if i < len(events):
                lbl.config(text=f"• {events[i][:90]}", fg=FG)
            else:
                lbl.config(text="", fg=FG)

        self.updated_var.set(
            f"Last updated: {time.strftime('%I:%M:%S %p')}   (refreshes every 20s)"
        )


if __name__ == "__main__":
    app = MonitorApp()
    app.mainloop()
