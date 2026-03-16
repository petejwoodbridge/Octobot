"""
memory.py — OctoBot Persistent Memory
=======================================
Handles reading and writing OctoBot's memory:

  workspace/memory.json     — structured action/decision/goal log
  workspace/agent_notes.md  — free-form notes OctoBot keeps for itself
  workspace/tasks.md        — task list OctoBot works through

Architecture
------------
Memory is split into two layers:

1. Structured (JSON)
   A rolling log of events: actions taken, decisions made, conversation
   history, and current goals.  Kept to MAX_EVENTS entries to avoid
   unbounded growth.

2. Narrative (markdown)
   agent_notes.md and tasks.md are plain text files OctoBot reads and
   updates directly through the tools layer.
"""

import json
import threading
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
WORKSPACE_ROOT = Path(__file__).parent / "workspace"
MEMORY_FILE = WORKSPACE_ROOT / "memory.json"

# How many events to retain in the rolling JSON log
MAX_EVENTS = 200

# Global lock — all read-modify-write operations on memory.json must hold this
# to prevent race conditions between the game loop, agent, and heartbeat threads.
# RLock allows the same thread to re-acquire (needed when public functions call _load_raw/_save_raw)
_lock = threading.RLock()

# Default memory structure
_EMPTY_MEMORY: dict = {
    "version": 3,
    "created_at": "",
    "goals": [],
    "events": [],           # rolling log (actions, decisions, tool calls)
    "conversation": [],     # chat history [{role, content, timestamp}]
    "processed_files": [],  # knowledge/comment files already ingested
    "game_stats": {
        "curiosity_level": 50,    # 0–100
        "knowledge_count": 0,
        "knowledge_score": 0,     # cumulative game score
        "comments_read": 0,
        "research_count": 0,
        "total_cycles": 0,
        "discoveries": 0,
        "cross_refs": 0,
        "chains_completed": 0,
        # Tamagotchi stats
        "happiness": 70,          # 0–100
        "hunger": 0,              # 0–100 (100 = starving for knowledge)
        "last_fed_at": "",        # ISO timestamp of last knowledge feed
        "last_chat_at": "",       # ISO timestamp of last player chat
        "mood": "content",        # happy/content/sad/lonely/hungry/excited/thinking
    },
    "achievements": [],         # [{id, name, desc, unlocked_at}]
    "knowledge_graph": {        # concept network
        "nodes": [],
        "edges": [],            # [{from, to, source}]
    },
    "research_chains": [],      # [{id, root, steps, current_step, completed, ...}]
    "discovery_log": [],        # [{concepts, files, insight, timestamp}]
}


# ---------------------------------------------------------------------------
# Load / save
# ---------------------------------------------------------------------------

def _load_raw() -> dict:
    """Load raw memory dict from disk, returning an empty structure if absent."""
    if MEMORY_FILE.exists():
        try:
            data = json.loads(MEMORY_FILE.read_text(encoding="utf-8"))
            # Ensure all expected keys exist (backwards-compat)
            for k, v in _EMPTY_MEMORY.items():
                data.setdefault(k, v)
            return data
        except (json.JSONDecodeError, OSError):
            pass
    fresh = dict(_EMPTY_MEMORY)
    fresh["created_at"] = datetime.now().isoformat()
    return fresh


def _save_raw(data: dict) -> None:
    """Persist *data* to disk."""
    WORKSPACE_ROOT.mkdir(exist_ok=True)
    MEMORY_FILE.write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_memory() -> dict:
    """Return the full memory dict (safe public wrapper)."""
    return _load_raw()


def log_event(event_type: str, detail: str) -> None:
    """
    Append an event to the rolling event log.

    Parameters
    ----------
    event_type : str
        Short category label, e.g. "action", "decision", "tool", "error".
    detail : str
        Human-readable description of what happened.
    """
    with _lock:
        data = _load_raw()
        entry = {
            "type": event_type,
            "detail": detail,
            "timestamp": datetime.now().isoformat(timespec="seconds"),
        }
        data["events"].append(entry)
        # Trim to the most recent MAX_EVENTS
        if len(data["events"]) > MAX_EVENTS:
            data["events"] = data["events"][-MAX_EVENTS:]
        _save_raw(data)


def add_conversation_turn(role: str, content: str) -> None:
    """
    Record a conversation turn.

    Parameters
    ----------
    role : str
        "user" or "assistant"
    content : str
        Message text.
    """
    with _lock:
        data = _load_raw()
        data["conversation"].append(
            {
                "role": role,
                "content": content,
                "timestamp": datetime.now().isoformat(timespec="seconds"),
            }
        )
        # Keep last 100 turns
        if len(data["conversation"]) > 100:
            data["conversation"] = data["conversation"][-100:]
        _save_raw(data)


def get_recent_conversation(n: int = 10) -> list[dict]:
    """Return the last *n* conversation turns."""
    data = _load_raw()
    return data["conversation"][-n:]


def set_goals(goals: list[str]) -> None:
    """Replace OctoBot's goal list."""
    with _lock:
        data = _load_raw()
        data["goals"] = goals
        _save_raw(data)


def get_goals() -> list[str]:
    """Return the current goal list."""
    return _load_raw().get("goals", [])


def get_recent_events(n: int = 20) -> list[dict]:
    """Return the last *n* events from the rolling log."""
    return _load_raw()["events"][-n:]


def get_event_log_text(n: int = 30) -> str:
    """
    Return recent events formatted as a human-readable string,
    suitable for inclusion in the agent's context window.
    """
    events = get_recent_events(n)
    if not events:
        return "(No events logged yet.)"
    lines = []
    for e in events:
        ts = e.get("timestamp", "?")
        etype = e.get("type", "?")
        detail = e.get("detail", "")
        lines.append(f"[{ts}] [{etype.upper()}] {detail}")
    return "\n".join(lines)


def summarise_memory_for_prompt() -> str:
    """
    Return a compact summary of memory suitable for injecting into the
    LLM system prompt — recent events + current goals.
    """
    goals = get_goals()
    events = get_recent_events(10)

    parts = []
    if goals:
        parts.append("Current goals:\n" + "\n".join(f"- {g}" for g in goals))
    if events:
        recent = "\n".join(
            f"- [{e['type']}] {e['detail']}" for e in events[-10:]
        )
        parts.append(f"Recent activity:\n{recent}")

    return "\n\n".join(parts) if parts else "(No memory yet.)"


# ---------------------------------------------------------------------------
# Game state tracking
# ---------------------------------------------------------------------------

def get_game_stats() -> dict:
    """Return the game stats dict."""
    data = _load_raw()
    return dict(data.get("game_stats", _EMPTY_MEMORY["game_stats"]))


def update_game_stat(key: str, value) -> None:
    """Set a single game stat field."""
    with _lock:
        data = _load_raw()
        stats = data.setdefault("game_stats", dict(_EMPTY_MEMORY["game_stats"]))
        stats[key] = value
        _save_raw(data)


def increment_game_stat(key: str, delta: int = 1) -> None:
    """Increment a numeric game stat by *delta*."""
    with _lock:
        data = _load_raw()
        stats = data.setdefault("game_stats", dict(_EMPTY_MEMORY["game_stats"]))
        stats[key] = stats.get(key, 0) + delta
        _save_raw(data)


def adjust_curiosity(delta: int) -> int:
    """Adjust curiosity level by *delta*, clamped 0–100. Returns new value."""
    with _lock:
        data = _load_raw()
        stats = data.setdefault("game_stats", dict(_EMPTY_MEMORY["game_stats"]))
        level = max(0, min(100, stats.get("curiosity_level", 50) + delta))
        stats["curiosity_level"] = level
        _save_raw(data)
    return level


# ---------------------------------------------------------------------------
# Tamagotchi helpers
# ---------------------------------------------------------------------------

def get_happiness() -> int:
    """Return current happiness 0–100."""
    return get_game_stats().get("happiness", 70)


def adjust_happiness(delta: int) -> int:
    """Adjust happiness by delta, clamped 0–100. Returns new value."""
    with _lock:
        data = _load_raw()
        stats = data.setdefault("game_stats", dict(_EMPTY_MEMORY["game_stats"]))
        val = max(0, min(100, stats.get("happiness", 70) + delta))
        stats["happiness"] = val
        _save_raw(data)
    return val


def get_hunger() -> int:
    """Return current hunger 0–100."""
    return get_game_stats().get("hunger", 0)


def adjust_hunger(delta: int) -> int:
    """Adjust hunger by delta, clamped 0–100. Returns new value."""
    with _lock:
        data = _load_raw()
        stats = data.setdefault("game_stats", dict(_EMPTY_MEMORY["game_stats"]))
        val = max(0, min(100, stats.get("hunger", 0) + delta))
        stats["hunger"] = val
        _save_raw(data)
    return val


def record_feed() -> None:
    """Record that OctoBot was just fed knowledge."""
    with _lock:
        data = _load_raw()
        stats = data.setdefault("game_stats", dict(_EMPTY_MEMORY["game_stats"]))
        stats["last_fed_at"] = datetime.now().isoformat(timespec="seconds")
        _save_raw(data)


def record_chat() -> None:
    """Record that the player just chatted."""
    with _lock:
        data = _load_raw()
        stats = data.setdefault("game_stats", dict(_EMPTY_MEMORY["game_stats"]))
        stats["last_chat_at"] = datetime.now().isoformat(timespec="seconds")
        _save_raw(data)


def compute_mood() -> str:
    """Compute OctoBot's mood based on happiness and hunger."""
    stats = get_game_stats()
    happiness = stats.get("happiness", 70)
    hunger = stats.get("hunger", 0)

    if happiness >= 85:
        return "excited"
    if happiness >= 65:
        if hunger > 60:
            return "hungry"
        return "happy"
    if happiness >= 40:
        if hunger > 70:
            return "hungry"
        return "content"
    if happiness >= 20:
        return "sad"
    return "lonely"


def update_mood() -> str:
    """Compute and store current mood. Returns the mood string."""
    mood = compute_mood()
    update_game_stat("mood", mood)
    return mood


def seconds_since_last_chat() -> float:
    """Seconds since last player chat, or 9999 if never."""
    stats = get_game_stats()
    ts = stats.get("last_chat_at", "")
    if not ts:
        return 9999.0
    try:
        last = datetime.fromisoformat(ts)
        return (datetime.now() - last).total_seconds()
    except Exception:
        return 9999.0


def seconds_since_last_feed() -> float:
    """Seconds since last knowledge feed, or 9999 if never."""
    stats = get_game_stats()
    ts = stats.get("last_fed_at", "")
    if not ts:
        return 9999.0
    try:
        last = datetime.fromisoformat(ts)
        return (datetime.now() - last).total_seconds()
    except Exception:
        return 9999.0


def is_file_processed(filename: str) -> bool:
    """Check if a knowledge/comment file has already been processed."""
    data = _load_raw()
    return filename in data.get("processed_files", [])


def mark_file_processed(filename: str) -> None:
    """Mark a file as processed so it won't be re-ingested."""
    with _lock:
        data = _load_raw()
        processed = data.setdefault("processed_files", [])
        if filename not in processed:
            processed.append(filename)
        _save_raw(data)
