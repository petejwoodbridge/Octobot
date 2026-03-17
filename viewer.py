"""
DreamLab OctoBot — Live Viewer
Displays a refreshing dashboard in a separate CMD window.
Run via start_octobot.bat or:  python viewer.py
"""
import json, os, time, sys, shutil, textwrap
from pathlib import Path
from datetime import datetime

MEMORY_FILE = Path(__file__).parent / "workspace" / "memory.json"
REFRESH_SEC = 4

PINK   = "\033[95m"
CYAN   = "\033[96m"
GREEN  = "\033[92m"
YELLOW = "\033[93m"
WHITE  = "\033[97m"
DIM    = "\033[90m"
RESET  = "\033[0m"
BOLD   = "\033[1m"

def enable_ansi():
    """Enable ANSI codes on Windows CMD."""
    if sys.platform == "win32":
        import ctypes
        kernel32 = ctypes.windll.kernel32
        kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)

def clear():
    os.system("cls" if sys.platform == "win32" else "clear")

def load():
    try:
        return json.loads(MEMORY_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}

def bar(value, maximum, width=28):
    if not maximum:
        return "[" + "-" * width + "]"
    filled = int(width * min(value, maximum) / maximum)
    return "[" + "█" * filled + "░" * (width - filled) + "]"

def fmt_score(n):
    return f"{n:,}"

LEVELS = [
    (0,"Napkin Sketcher",1),(50,"Shower Thinker",2),(120,"Garage Tinkerer",3),
    (250,"Caffeinated Dreamer",4),(450,"Prototype Gremlin",5),(700,"Mad Scientist",6),
    (1000,"Patent Pending",7),(1400,"Chaos Engineer",8),(1900,"Moonshot Architect",9),
    (2500,"Frankenstein's Mentor",10),(3200,"Interdimensional Tinkerer",11),
    (4000,"Perpetual Motion Machine",12),(5000,"Idea Supercollider",13),
    (6200,"Rogue Inventor General",14),(7500,"Dream Reactor",15),(9000,"Octopus Prime",16),
    (11000,"Reality Bender",17),(13500,"Singularity Whisperer",18),
    (16500,"God of Small Things",19),(20000,"Infinite Idea Engine",20),
    (22000,"Temporal Patent Troll",21),(24500,"Chaos Theory Barista",22),
    (27000,"Professor of Impractical Solutions",23),(29500,"Reverse Engineer of the Soul",24),
    (32000,"Unsolicited Visionary",25),(34500,"Eight-Armed Architect",26),
    (37000,"Reality's Most Wanted",27),(39500,"Sentient Whiteboard",28),
    (42000,"Wizard of Unnecessary Things",29),(44500,"Quantum Daydreamer",30),
    (47000,"Accidental Paradigm Shift",31),(49500,"Self-Aware Hypothesis",32),
    (52000,"The Unpatentable",33),(54500,"Bureau of Impossible Standards",34),
    (57000,"Feral Futurist",35),(60500,"Architect of Magnificent Nonsense",36),
    (64000,"Chronic Eureka Syndrome",37),(67500,"Pantheon of Peculiar Inventions",38),
    (71000,"Unsanctioned Oracle",39),(74500,"The Universe's Most Chaotic Asset",40),
    (78000,"Cosmic Patent Thief",41),(81500,"The Unstoppable Hypothesis",42),
    (85000,"Invention Incarnate",43),(88500,"OctoGod of the Ideaverse",44),
    (92000,"Dimension-Hopping Prototype",45),(95500,"The Last Known Inventor",46),
    (99000,"Transcendent Patent Overlord",47),(102500,"Primordial Inventor",48),
    (106000,"The Idea Before Ideas",49),(110000,"Genesis Engine",50),
]

def get_level(score):
    lvl_name, lvl_num, nxt = "Napkin Sketcher", 1, 50
    for i, (thresh, name, num) in enumerate(LEVELS):
        if score >= thresh:
            lvl_name, lvl_num = name, num
            nxt = LEVELS[i + 1][0] if i + 1 < len(LEVELS) else None
    return lvl_num, lvl_name, nxt

def render():
    data  = load()
    stats = data.get("game_stats", {})
    events = data.get("events", [])[-18:]  # show more events

    score   = stats.get("knowledge_score", 0)
    ideas   = stats.get("knowledge_count", 0)
    res     = stats.get("research_count", 0)
    curious = stats.get("curiosity_level", 50)
    lvl_num, lvl_name, nxt = get_level(score)

    # Use actual terminal width, minimum 72, maximum 120
    W = max(72, min(120, shutil.get_terminal_size((100, 40)).columns - 2))
    INDENT = "    "  # indent for wrapped continuation lines

    clear()
    print(PINK + BOLD + "=" * W + RESET)
    print(PINK + BOLD + "  🐙  DreamLab OctoBot  —  Live Viewer" + RESET)
    print(PINK + BOLD + "=" * W + RESET)
    print()

    # Score & level
    print(CYAN + BOLD + f"  SCORE   {WHITE}{fmt_score(score)}" + RESET)
    nxt_str = f"  (next level at {fmt_score(nxt)})" if nxt else "  ← MAX LEVEL 🏆"
    print(CYAN + f"  LEVEL   {YELLOW}{lvl_num:>2} — {lvl_name}{DIM}{nxt_str}" + RESET)

    if nxt:
        prev_thresh = LEVELS[lvl_num - 1][0]
        progress = score - prev_thresh
        span = nxt - prev_thresh
        pct = int(100 * progress / span) if span else 100
        bar_w = W - 12
        print(f"  {GREEN}{bar(progress, span, bar_w)}  {pct}%{RESET}")
    print()

    # Stats row
    print(CYAN + f"  💡 Ideas: {WHITE}{ideas:<6}{CYAN}  🔬 Research: {WHITE}{res:<6}{CYAN}  🧠 Curiosity: {WHITE}{curious}" + RESET)
    print()

    # Recent events — full text, wrapped
    print(CYAN + BOLD + "  Recent Activity:" + RESET)
    print(DIM + "  " + "─" * (W - 2) + RESET)
    if events:
        wrap_width = W - len("  HH:MM:SS  RESEARCH  ") - 2
        for e in reversed(events):
            ts   = e.get("timestamp", "")[-8:]  # HH:MM:SS
            typ  = e.get("type", "").upper()[:8]
            det  = e.get("detail", "")
            col  = YELLOW if typ in ("SCORE", "ACTION") else GREEN if typ == "RESEARCH" else WHITE
            # Wrap the full detail text
            lines = textwrap.wrap(det, width=wrap_width) or [""]
            print(f"  {DIM}{ts}  {col}{typ:<8}{RESET}  {WHITE}{lines[0]}{RESET}")
            for continuation in lines[1:]:
                print(f"  {' ' * 8}  {' ' * 8}  {DIM}{continuation}{RESET}")
            print()  # blank line between entries for readability
    else:
        print(f"  {DIM}(no events yet — waiting for OctoBot to wake up…){RESET}")

    print(DIM + f"  Refreshing every {REFRESH_SEC}s  |  Ctrl+C to close  |  {datetime.now().strftime('%H:%M:%S')}" + RESET)
    print(PINK + "=" * W + RESET)

if __name__ == "__main__":
    enable_ansi()
    try:
        while True:
            render()
            time.sleep(REFRESH_SEC)
    except KeyboardInterrupt:
        print("\n  Viewer closed. OctoBot keeps running in the other window.\n")
