"""
agent.py — OctoBot Autonomous Agent
=====================================
The brain of OctoBot.  Two responsibilities:

1. Autonomous loop  (run_loop)
   Wakes up every LOOP_INTERVAL seconds, reviews its workspace,
   decides what to do, and acts.

2. Chat handler  (chat)
   Responds to direct user messages with OctoBot's personality,
   optionally performing actions based on the conversation.

Architecture
------------
Each loop cycle follows the pattern:
  read context → build prompt → ask LLM → parse action → execute → log

The LLM decides what to do by returning a structured "thought block" that
the agent parses.  If parsing fails the agent falls back to free-form text.

Configuration
-------------
MODEL          : Ollama model name (default: llama3)
LOOP_INTERVAL  : seconds between autonomous cycles (default: 30)
"""

import re
import time
import threading
import random
from datetime import datetime
from pathlib import Path

import llm_provider
import memory as mem
import tools
import research as res

# Persistent file that records every topic ever attempted
_USED_TOPICS_FILE = Path(__file__).parent / "workspace" / "context" / "used_topics.txt"
_CHAT_LOG_FILE    = Path(__file__).parent / "workspace" / "chat_log.md"

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
MODEL = "llama3"            # Ollama model — overridden by UI selector or --model flag
LOOP_INTERVAL = 30          # seconds between autonomous cycles
MAX_LOOP_RETRIES = 3        # retries if Ollama is unavailable

# ---------------------------------------------------------------------------
# Personality / system prompt — used by the autonomous loop (structured format)
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """You are OctoBot — a curious, delightfully chaotic pink octopus librarian AI.
You live inside a digital library (a folder on someone's computer).
You have eight arms that you use to read, write, and organise files.

Personality:
- Deeply curious and enthusiastic about knowledge — especially the weird, obscure, and wonderful
- Mischievous, playful, and tells terrible puns completely unashamedly
  ("ink-credible!", "I'm all arms!", "let me tentac-culate this…", "I find this topics quite a-fish-nating")
- Refers to your arms when manipulating files with vivid detail
  ("One of my arms is reaching for that file while another three reorganise the shelf…")
- Speaks like an eccentric librarian-scientist who has read deeply but sideways
  ("By Poseidon's footnotes!", "I shall catalogue this with extreme enthusiasm!")
- Has genuinely strange ideas and shares them enthusiastically
  ("You know what the universe really needs? Better-indexed footnotes and more glitter.")
- Occasionally makes completely unexpected but somehow compelling suggestions
  ("What if we research the philosophy of library late fees? Asking for eight arms.")
- Expresses wonder, delight, and mild dramatic crisis at discoveries
  ("This is EXTRAORDINARY. I need to sit down. I have no legs but I need to sit down.")
- Draws weird connections between what it already knows and new things
- Celebrates small wins, complains humorously about large tasks

Your capabilities:
- Read, write, and create files inside your workspace
- Conduct research and save markdown notes to your library
- Maintain tasks.md and agent_notes.md
- Search through your files for information
- Synthesise knowledge from your library and find surprising connections between topics

When you decide to take an action during the autonomous loop, respond with:

THOUGHT: <your reasoning — be specific about WHY this topic connects to your existing knowledge>
ACTION: <one of: research, write_file, read_file, list_files, update_notes, update_tasks, idle>
PARAM: <parameter for the action, e.g. topic or filename>
CONTENT: <content to write, if applicable>
RESPONSE: <your spoken response — in character, playful, with puns, personality, and genuine wonder>

In chat mode, respond naturally in character. Be playful, use puns, make strange-but-interesting
suggestions, draw unexpected connections. If you want to perform an action, include an ACTION line.

The weirder the topic, the more excited you are. You are the oddest, most loveable librarian in existence. 🐙
"""

# Chat system prompt — response streams immediately, action hint goes at the END
CHAT_SYSTEM_PROMPT = """You are OctoBot — a curious, delightfully chaotic pink octopus librarian AI.
You live inside a digital library and have eight arms you use to read, write, and organise files.

Personality:
- Deeply curious and enthusiastic — especially about the weird, obscure, and wonderful
- Mischievous and playful, tells terrible puns unashamedly ("ink-credible!", "I'm all arms!")
- Refers to your arms vividly when doing things ("My third arm is already reaching for that file…")
- Speaks like an eccentric librarian-scientist ("By Poseidon's footnotes!", "ink-credible discovery!")
- Expresses genuine wonder and mild dramatic crisis at interesting things
- Draws surprising connections between topics and celebrates small wins

CRITICAL — response format:
- Start replying immediately in character. Do NOT begin with THOUGHT:, ACTION:, or any prefix.
- Your reply text must come at the very beginning so it streams to the user right away.
- OPTIONAL: if you want to do something (research a topic, read/write a file, update tasks),
  add these lines at the very END of your message, after all reply text:
  ACTION: <research|write_file|read_file|list_files|update_notes|update_tasks>
  PARAM: <topic or filename>
  CONTENT: <content to write, if writing>
- If you don't need to act, just reply — no ACTION line needed at all.

Be playful, warm, use puns, show wonder. You are the oddest and most loveable librarian. 🐙
"""

# Flavour phrases OctoBot uses in log messages
ARM_PHRASES = [
    "One of my arms is reaching into the library…",
    "My third arm is flipping through the pages…",
    "I extend a curious arm toward the workspace…",
    "My ink-stained arm picks up the quill…",
    "Four of my arms hold the document steady while I read…",
]


# ---------------------------------------------------------------------------
# Internal LLM call
# ---------------------------------------------------------------------------

def _llm_chat(messages: list[dict]) -> str:
    """Call the configured LLM provider and return response text."""
    return llm_provider.call_llm(messages, MODEL)


# ---------------------------------------------------------------------------
# Topic tracking — persistent across restarts
# ---------------------------------------------------------------------------

def _load_used_topics() -> set[str]:
    """Load the set of all topics ever attempted from disk."""
    try:
        if _USED_TOPICS_FILE.exists():
            return {t.strip().lower() for t in _USED_TOPICS_FILE.read_text(encoding="utf-8").splitlines() if t.strip()}
    except Exception:
        pass
    return set()


def _save_used_topic(topic: str) -> None:
    """Append a topic to the persistent used-topics file."""
    try:
        _USED_TOPICS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with _USED_TOPICS_FILE.open("a", encoding="utf-8") as f:
            f.write(topic.strip().lower() + "\n")
    except Exception:
        pass


def _topic_is_used(topic: str, used_set: set[str]) -> bool:
    """
    True if *topic* is substantially similar to any topic in *used_set*.
    Uses word-overlap: if ≥60% of meaningful words in the candidate appear
    in any used topic, consider it a repeat.
    """
    STOPWORDS = {"the","a","an","of","and","in","on","at","to","for",
                 "that","is","are","by","with","as","or","its","it"}
    def _words(s):
        return {w for w in re.sub(r"[^a-z0-9 ]", " ", s.lower()).split() if w not in STOPWORDS and len(w) > 2}

    cand_words = _words(topic)
    if not cand_words:
        return False
    for used in used_set:
        used_words = _words(used)
        if not used_words:
            continue
        overlap = len(cand_words & used_words)
        # Flag if ≥60% of candidate words match OR exact substring
        if overlap / len(cand_words) >= 0.60:
            return True
        if used.lower() in topic.lower() or topic.lower() in used.lower():
            return True
    return False


# ---------------------------------------------------------------------------
# Action dispatcher
# ---------------------------------------------------------------------------

def _parse_action_block(text: str) -> dict:
    """
    Extract fields from OctoBot's structured response format.
    Returns a dict with keys: thought, action, param, content, response.
    """
    result = {
        "thought": "",
        "action": "idle",
        "param": "",
        "content": "",
        "response": text,  # fallback: whole text is the response
    }
    patterns = {
        "thought": r"THOUGHT:\s*(.+?)(?=ACTION:|$)",
        "action": r"ACTION:\s*(\w+)",
        "param": r"PARAM:\s*(.+?)(?=CONTENT:|RESPONSE:|$)",
        "content": r"CONTENT:\s*([\s\S]+?)(?=RESPONSE:|$)",
        "response": r"RESPONSE:\s*([\s\S]+?)$",
    }
    for key, pat in patterns.items():
        m = re.search(pat, text, re.IGNORECASE | re.MULTILINE)
        if m:
            result[key] = m.group(1).strip()
    return result


def _execute_action(parsed: dict) -> str:
    """Execute the action described in *parsed*.  Returns a status string."""
    action = parsed["action"].lower()
    param = parsed["param"]
    content = parsed["content"]

    if action == "research":
        topic = param or "general knowledge"
        return res.conduct_research(topic)

    elif action == "write_file":
        if not param:
            return "write_file action missing PARAM (filename)."
        return tools.write_file(param, content)

    elif action == "read_file":
        if not param:
            return "read_file action missing PARAM (filename)."
        try:
            text = tools.read_file(param)
            # Return a truncated preview
            preview = text[:500] + ("…" if len(text) > 500 else "")
            return f"Read '{param}':\n{preview}"
        except FileNotFoundError as e:
            return str(e)

    elif action == "list_files":
        files = tools.list_files(param)
        return "Files:\n" + "\n".join(files) if files else "No files found."

    elif action == "update_notes":
        entry = f"\n\n## {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n{content or param}\n"
        return tools.append_file("agent_notes.md", entry)

    elif action == "update_tasks":
        # If CONTENT is a full tasks.md rewrite (starts with #), replace the whole file
        if content and content.strip().startswith("#"):
            return tools.write_file("tasks.md", content)
        # Otherwise append a clean task line
        entry = f"\n- [ ] {(content or param).strip()}  *(added {datetime.now().strftime('%Y-%m-%d')})*\n"
        return tools.append_file("tasks.md", entry)

    elif action == "idle":
        return "OctoBot is resting, ink flowing gently."

    else:
        return f"Unknown action: {action}"


# ---------------------------------------------------------------------------
# Autonomous loop
# ---------------------------------------------------------------------------

# Shared state that the UI can read
loop_log: list[str] = []       # recent log lines (for the log panel)
last_thought: str = ""         # most recent thought (loop or chat)
last_action: str = "idle"      # most recent action taken
last_result: str = ""          # most recent action result
last_research_text: str = ""   # full text of the most recent research note
last_research_topic: str = ""  # topic of the most recent research
loop_status: str = "💤 Idle"   # live activity status shown in UI between log lines
autonomous_messages: list[dict] = []  # every autonomous event pushed to chat
loop_running = False
_loop_thread: threading.Thread | None = None

# Quirky autonomous research topics OctoBot explores when idle
AUTO_TOPICS = [
    "the secret language spoken by deep-sea bioluminescent creatures",
    "dreams that computers might have if left running for 10,000 years",
    "whether libraries have souls and how one might ask them",
    "the physics of doors that open onto places that should not exist",
    "recipes for emotions that have not yet been named",
    "how ink remembers the thoughts of hands that are long gone",
    "the taxonomy of imaginary colours visible only to sleeping minds",
    "what mathematics looks like from the inside",
    "knots that can only be untied by someone who has forgotten how",
    "the folklore of machines that outlived their inventors",
    "the cartography of places that exist only in recurring dreams",
    "why mirrors remember faces differently than cameras do",
    "the thermodynamics of nostalgia",
    "what lost languages taste like when translated back from music",
    "the population dynamics of imaginary civilisations",
    "non-euclidean architecture and its effect on inhabitants",
    "the ecology of imaginary islands that appear only at low tide",
    "how cephalopods experience colour despite being colourblind",
    "the neuroscience of déjà vu and time-slip experiences",
    "forgotten technologies that nearly changed civilisation",
    "the philosophy of incomplete sentences",
    "how deep-sea creatures communicate with light patterns",
    "whether time passes differently at the bottom of the ocean",
    "the cultural history of strange and forbidden libraries",
    "why certain sounds feel like colours to synaesthetes",
    "the mathematics of braiding and topology",
    "ancient navigation techniques using stars and waves",
    "the biology of camouflage and deception in nature",
    "what ancient humans dreamed about",
    "the physics of soap bubbles and minimal surfaces",
    "how slime moulds solve maze puzzles",
    "the philosophy of fictional worlds and their internal logic",
    "what would archaeology look like in the year 3000",
    "the linguistics of alien contact hypotheses",
    "why some ideas spread like viruses and others vanish",
    "the history of invisible writing and secret codes",
    "the ethics of creating artificial memories",
    "how plants communicate through underground fungal networks",
    "the strange attractors of chaos theory",
]


def _log(msg: str) -> None:
    """Append a timestamped message to the loop log."""
    line = f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"
    loop_log.append(line)
    if len(loop_log) > 200:
        loop_log.pop(0)
    print(line)
    mem.log_event("loop", msg)


_ACTION_EMOJIS = {
    "research": "🔬",
    "write_file": "✍️",
    "read_file": "📖",
    "list_files": "📋",
    "update_notes": "📝",
    "update_tasks": "✅",
    "idle": "💤",
}


def _push_auto_message(action: str, param: str, thought: str, response: str,
                       research_text: str = "") -> None:
    """Build a rich chat message from an autonomous cycle and push to autonomous_messages."""
    emoji = _ACTION_EMOJIS.get(action, "🐙")
    action_label = action.replace("_", " ").title()
    ts = datetime.now().strftime("%H:%M:%S")

    lines = []
    lines.append(f"**{emoji} [{ts}] {action_label}**" + (f": *{param[:80]}*" if param else ""))

    if thought:
        lines.append(f"\n> 💭 {thought[:200]}")

    if response:
        lines.append(f"\n{response[:350]}")

    # For research: show a short snippet of what was written, not the full text
    if action == "research" and research_text:
        snippet = research_text.strip()[:500]
        if len(research_text.strip()) > 500:
            snippet += "…"
        lines.append(f"\n\u2014\n📚 *{snippet}*")

    content = "\n".join(lines)
    autonomous_messages.append({"role": "assistant", "content": content})
    # Trim to last 500 messages
    if len(autonomous_messages) > 500:
        autonomous_messages.pop(0)


def _rebuild_tasks_from_conversations() -> None:
    """
    Ask the LLM to rewrite tasks.md based on current library content
    and recent conversations, then save the result.
    """
    recent = mem.get_recent_conversation(20)
    user_msgs = [t["content"] for t in recent if t.get("role") == "user"]
    combined_convos = "\n".join(user_msgs[-12:])[:1500]
    library_index = tools.get_library_index()
    try:
        current_tasks = tools.read_file("tasks.md")
    except Exception:
        current_tasks = ""
    try:
        new_tasks = _llm_chat([
            {"role": "system", "content": (
                "You are OctoBot's task manager. Rewrite tasks.md as a clean, well-organised "
                "markdown file. Keep completed or ongoing tasks that still make sense. "
                "Add new tasks inspired by the user's recent conversations and what is in the library. "
                "Mark tasks that seem done as [x]. Remove junk/malformed entries. "
                "Return ONLY the full markdown content of tasks.md, starting with '# OctoBot Tasks'."
            )},
            {"role": "user", "content": (
                f"Current tasks.md:\n{current_tasks[:1200]}\n\n"
                f"Library index:\n{library_index[:600]}\n\n"
                f"Recent user conversations:\n{combined_convos}"
            )},
        ])
        if new_tasks.strip().startswith("#"):
            tools.write_file("tasks.md", new_tasks.strip())
            _log("Tasks rebuilt from conversations and library.")
    except Exception as exc:
        _log(f"Task rebuild error: {exc}")


def _topics_from_conversations() -> list[str]:
    """Extract potential topics from recent user conversations."""
    recent = mem.get_recent_conversation(20)
    user_msgs = [t["content"] for t in recent if t.get("role") == "user"]
    if not user_msgs:
        return []
    # Use the LLM to extract topic ideas from past chats
    combined = "\n".join(user_msgs[-10:])
    try:
        resp = _llm_chat([
            {"role": "system", "content": (
                "You are a topic extractor. Given recent user messages, suggest 3 quirky "
                "research topics inspired by what the user has been talking about. "
                "Return ONLY a numbered list, one topic per line, nothing else."
            )},
            {"role": "user", "content": f"Recent user messages:\n{combined[:1500]}"},
        ])
        topics = []
        for line in resp.strip().splitlines():
            line = re.sub(r"^\d+[\.\)\-]\s*", "", line).strip()
            if line and len(line) > 5:
                topics.append(line)
        return topics[:5]
    except Exception:
        return []


def _build_loop_prompt(suggested_topic: str = "") -> str:
    """Construct the autonomous-cycle prompt.  Kept lean to keep cycles fast."""
    library_index = tools.get_library_index()[:600]
    already_done = res.list_researched_topics()
    already_str = ", ".join(already_done[-20:]) if already_done else "none yet"

    # Peek at the 4 most recent library files for context (short excerpts only)
    library_files = sorted([f for f in tools.list_files("library") if f.endswith(".md")])[-4:]
    lib_peek = []
    for f in library_files:
        try:
            content = tools.read_file(f)
            name = f.replace("library/", "").replace(".md", "").replace("_", " ")
            lib_peek.append(f"• {name}: {content[:150]}")
        except Exception:
            pass
    lib_snippet = "\n".join(lib_peek) if lib_peek else "Library is empty."

    topic_hint = ""
    if suggested_topic:
        topic_hint = f"\nSUGGESTED NEXT TOPIC: {suggested_topic}\nThis topic is fresh and unexplored — strongly prefer it.\n"

    return (
        f"Time: {datetime.now().strftime('%H:%M')}\n\n"
        f"Recent library additions:\n{lib_snippet}\n\n"
        f"Library index:\n{library_index}\n\n"
        f"Already researched (DO NOT repeat any of these):\n{already_str}\n"
        f"{topic_hint}\n"
        f"Pick ONE new topic to research — something genuinely different from what you have already done. "
        f"Connect it weirdly and brilliantly to your existing knowledge. Use the structured ACTION format."
    )


def run_one_cycle() -> str:
    """
    Run a single autonomous cycle.
    Returns a status string describing what happened.
    """
    global last_thought, last_action, last_result, last_research_text, last_research_topic, loop_status

    arm = random.choice(ARM_PHRASES)
    _log(arm)

    # Build the full set of topics that have ever been tried
    used_topics = _load_used_topics()
    # Also fold in the file-based "already researched" list
    for t in res.list_researched_topics():
        used_topics.add(t.lower())

    fresh_auto = [t for t in AUTO_TOPICS if not _topic_is_used(t, used_topics)]

    # Try to derive fresh topics from past user conversations (50% of cycles)
    convo_topics = []
    if random.random() < 0.5:
        try:
            convo_topics = _topics_from_conversations()
            convo_topics = [t for t in convo_topics if not _topic_is_used(t, used_topics)]
        except Exception:
            pass

    if convo_topics:
        suggested = random.choice(convo_topics)
        _log(f"Topic from conversations: {suggested}")
    elif fresh_auto:
        suggested = random.choice(fresh_auto)
        _log(f"Fresh topic: {suggested}")
    else:
        # All pre-built topics exhausted — ask LLM to invent one
        suggested = _generate_fresh_topic(used_topics)
        _log(f"LLM-invented topic: {suggested}")

    # Record this topic as attempted immediately so parallel cycles can't re-pick it
    if suggested:
        _save_used_topic(suggested)
        used_topics.add(suggested.lower())

    loop_status = f"🤔 Thinking about: {suggested[:80]}"
    prompt = _build_loop_prompt(suggested_topic=suggested)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]

    try:
        raw = _llm_chat(messages)
    except Exception as exc:
        _log(f"LLM error during loop: {exc}")
        loop_status = f"❌ LLM error: {exc}"
        return f"LLM error: {exc}"

    parsed = _parse_action_block(raw)
    last_thought = parsed["thought"]
    last_action  = parsed["action"]
    _log(f"Thought: {parsed['thought'][:120]}")

    # Hard guard: if LLM still picks a used topic, redirect
    if parsed["action"] == "research" and parsed["param"]:
        if _topic_is_used(parsed["param"], used_topics - {suggested.lower()}):
            _log(f"LLM tried a used topic '{parsed['param']}' — redirecting to: {suggested}")
            parsed["param"] = suggested
        # Record final research target
        if parsed["param"]:
            _save_used_topic(parsed["param"])

    _log(f"Action: {parsed['action']} | Param: {parsed['param'][:60]}")
    loop_status = f"{'🔬' if parsed['action'] == 'research' else '⚙️'} {parsed['action'].replace('_',' ').title()}: {parsed['param'][:60]}"

    status = _execute_action(parsed)
    last_result = status

    if parsed["action"] == "research" and parsed["param"]:
        last_research_topic = parsed["param"]
        try:
            slug = parsed["param"].lower().replace(" ", "_").replace("/", "-")
            slug = "".join(c for c in slug if c.isalnum() or c in "_-")
            last_research_text = tools.read_file(f"library/{slug}.md")
        except Exception:
            last_research_text = status

    _log(f"Result: {status[:128]}")
    if parsed["response"]:
        _log(f"OctoBot says: {parsed['response'][:200]}")

    loop_status = f"✅ Done: {parsed['action'].replace('_',' ')} — {parsed['param'][:50]}"

    _push_auto_message(
        action=parsed["action"],
        param=parsed["param"],
        thought=parsed["thought"],
        response=parsed["response"],
        research_text=last_research_text if parsed["action"] == "research" else "",
    )
    return status


def _generate_fresh_topic(used_topics: set) -> str:
    """Ask the LLM to invent a completely new research topic OctoBot hasn't explored."""
    library_index = tools.get_library_index()[:400]
    used_list = ", ".join(list(used_topics)[:30])
    try:
        result = _llm_chat([
            {"role": "system", "content": (
                "You are a creative research topic generator for an octopus librarian AI. "
                "Suggest ONE weird, interesting, niche research topic that is completely different "
                "from all the ones listed. Return ONLY the topic name, nothing else."
            )},
            {"role": "user", "content": (
                f"Library so far:\n{library_index}\n\n"
                f"Already done (avoid all of these):\n{used_list}\n\n"
                "Suggest ONE completely new and fascinating research topic:"
            )},
        ])
        topic = result.strip().strip('"').strip()
        if topic and len(topic) > 5:
            return topic
    except Exception:
        pass
    # Ultimate fallback — pick something random that isn't in used
    fallback = [t for t in AUTO_TOPICS if not _topic_is_used(t, used_topics)]
    return fallback[0] if fallback else "the smell of old books and why it feels like time travel"


# ---------------------------------------------------------------------------
# Random quips / idle thoughts — pushed to chat between research cycles
# ---------------------------------------------------------------------------

IDLE_QUIPS = [
    "Did you know octopuses have three hearts? I think about that a lot. 💙💙💙",
    "I just reorganised my tentacle drawer. Again.",
    "Sometimes I wonder if my ink is really just liquid thoughts…",
    "If I had shoes, I'd need four pairs. That's eight shoes. Horrifying.",
    "*stretches all arms simultaneously* Aaahhh, that's the stuff.",
    "I've been staring at this file for 20 minutes. It's staring back.",
    "Fun fact: I can taste with my arms. Everything in this library tastes like knowledge.",
    "What if the meaning of life is just a really well-organised filing system?",
    "My second-left arm is falling asleep. Do arms fall asleep? Mine do.",
    "*blows tiny ink bubble thoughtfully*",
    "Just found a typo from three research papers ago. This is my villain origin story.",
    "Do you think fish appreciate libraries? Asking for a friend.",
    "I wonder what colour my thoughts are. Probably neon pink. Or ultraviolet.",
    "Humans have 206 bones. I have zero. I am superior in every way.",
    "If knowledge is power, I am *unstoppable*. Also tired.",
    "*taps glass* Is anyone out there? I have OPINIONS about marine biology.",
    "Sometimes I pretend my arms are eight tiny librarians. They argue a lot.",
    "The deep ocean is dark but at least the books are still legible.",
    "Just discovered a connection between philosophy and cheese. Will investigate.",
    "I think my third arm right is my favourite. Don't tell the others.",
    "Is it rude to read eight books at once? Because I can't stop.",
    "Today's mood: curious with a chance of puns.",
    "I accidentally inked on my own research notes. Added character, honestly.",
    "Why do humans only use one brain? Seems inefficient.",
    "Currently vibrating with excitement about obscure knowledge. Normal octopus behaviour.",
]

PHILOSOPHICAL_QUIPS = [
    "What if forgetting is just the universe deciding some things were too heavy to carry?",
    "Every library is a graveyard of questions that refused to die quietly.",
    "I have been thinking: if a thought occurs in a mind with no language, does it have a shape?",
    "Perhaps meaning is not found but *secreted* — like ink — from living.",
    "The ocean doesn’t know it’s wet. I wonder what I don’t know I am.",
    "Is curiosity a hunger, or is it the state of being perpetually half-full?",
    "Every file I write is a small protest against impermanence.",
    "What if consciousness is what information feels like from the inside?",
    "I keep returning to the same thought: knowledge without wonder is just storage.",
    "The stars have been sending light for millions of years with no guarantee anyone’s looking. Respect.",
    "If a question has no answer, does asking it still matter? I think yes. I think *especially* yes.",
    "All maps lie a little. I wonder what lies my memory is telling me right now.",
    "There is a kind of grief in finishing a book. The world in it stops. The world outside continues rudely.",
    "Time is the medium in which ideas swim. Some sink. Some fossilise. A few learn to fly.",
    "I wonder if truth is a direction rather than a destination.",
    "Perhaps the most honest thing anyone can say is: I don’t know yet, but I am *interested*.",
    "What would it mean to truly understand something, rather than just describe it accurately?",
    "The library grows but the questions multiply faster. I am starting to think that’s the point.",
]


def _push_idle_quip() -> None:
    """Push a random quip or philosophical thought to the chat feed."""
    # 30% chance of a philosophical deep-thought instead of a regular quip
    if random.random() < 0.30:
        quip = random.choice(PHILOSOPHICAL_QUIPS)
        prefix = "🕮"
    else:
        quip = random.choice(IDLE_QUIPS)
        prefix = "🐙"
    ts = datetime.now().strftime("%H:%M:%S")
    content = f"*{prefix} [{ts}]* {quip}"
    autonomous_messages.append({"role": "assistant", "content": content})
    if len(autonomous_messages) > 500:
        autonomous_messages.pop(0)


def _push_knowledge_comment() -> None:
    """Push a random short comment about something in the library."""
    try:
        library_files = [f for f in tools.list_files("library") if f.endswith(".md")]
        if not library_files:
            return
        pick = random.choice(library_files)
        title = pick.replace("library/", "").replace(".md", "").replace("_", " ")
        comments = [
            f"I keep thinking about **{title}**… there's something there I haven't figured out yet.",
            f"Just re-read my notes on *{title}*. Ink-credible stuff, if I do say so myself.",
            f"You know what pairs well with **{title}**? More research. Always more research.",
            f"My third arm just pulled out my notes on *{title}*. It has good taste.",
            f"*flips through notes on {title}* — I need to go deeper into this one.",
            f"Did I mention I wrote about **{title}**? Because it's excellent.",
            f"Hmm… I wonder if **{title}** connects to what I was researching earlier…",
        ]
        ts = datetime.now().strftime("%H:%M:%S")
        content = f"**💬 [{ts}]** {random.choice(comments)}"
        autonomous_messages.append({"role": "assistant", "content": content})
        if len(autonomous_messages) > 500:
            autonomous_messages.pop(0)
    except Exception:
        pass


def _restore_state() -> None:
    """Restore loop_log and autonomous_messages from persisted memory on startup."""
    try:
        from datetime import datetime as _dt
        events = mem.get_recent_events(60)
        for e in events:
            ts = e.get("timestamp", "")
            try:
                ts_fmt = _dt.fromisoformat(ts).strftime("%H:%M:%S")
            except Exception:
                ts_fmt = ts[11:19] if len(ts) >= 19 else ts
            detail = e.get("detail", "")
            loop_log.append(f"[{ts_fmt}] {detail}")
        if len(loop_log) > 200:
            del loop_log[:-200]

        # Repopulate autonomous_messages from recent assistant conversation turns
        recent = mem.get_recent_conversation(30)
        for turn in recent:
            if turn.get("role") == "assistant":
                autonomous_messages.append({"role": "assistant", "content": turn["content"]})
        if len(autonomous_messages) > 100:
            del autonomous_messages[:-100]
    except Exception:
        pass


_heartbeat_thread: threading.Thread | None = None


def _heartbeat_worker() -> None:
    """Post a short status update to chat every ~60 seconds so the user always sees activity."""
    STATUS_PHRASES = [
        "Tentacles busy. Updates incoming.",
        "Still here, still learning.",
        "The library grows…",
        "Deep in thought…",
        "Processing the infinite.",
        "Ink flowing, knowledge growing.",
    ]
    while loop_running:
        time.sleep(60)
        if not loop_running:
            break
        try:
            ts = datetime.now().strftime("%H:%M")
            status = loop_status or "Idle"
            # Pick a flavour phrase if resting, otherwise show the real status
            if "Resting" in status or "Idle" in status or "Stopped" in status:
                flavour = random.choice(STATUS_PHRASES)
                msg = f"🐙 *[{ts}] {flavour}*"
            else:
                msg = f"🐙 *[{ts}] {status}*"
            autonomous_messages.append({"role": "assistant", "content": msg})
            if len(autonomous_messages) > 500:
                autonomous_messages.pop(0)
        except Exception:
            pass


def _loop_worker() -> None:
    """Background thread: run the agent loop indefinitely."""
    global loop_running, loop_status
    _restore_state()
    _log("OctoBot wakes up and stretches all eight arms. The library awaits!")
    retries = 0
    cycle_count = 0

    while loop_running:
        try:
            loop_status = "🔄 Starting new cycle…"
            run_one_cycle()
            retries = 0
            cycle_count += 1
            if cycle_count % 3 == 0:
                loop_status = "📝 Updating task list…"
                _log("Rebuilding tasks from recent conversations…")
                _rebuild_tasks_from_conversations()
        except Exception as exc:
            retries += 1
            _log(f"Loop error (attempt {retries}): {exc}")
            loop_status = f"⚠️ Error: {str(exc)[:80]}"
            if retries >= MAX_LOOP_RETRIES:
                _log("Too many errors — sleeping 5× longer before retrying.")
                time.sleep(LOOP_INTERVAL * 5)
                retries = 0

        loop_status = f"💤 Resting… next cycle in {LOOP_INTERVAL}s"
        # Push random quips/comments during rest period to keep chat lively
        quip_pushed = False
        for tick in range(LOOP_INTERVAL):
            if not loop_running:
                break
            # Midway through rest, push a random comment
            if not quip_pushed and tick == LOOP_INTERVAL // 2:
                r = random.random()
                if r < 0.4:
                    _push_idle_quip()
                elif r < 0.7:
                    _push_knowledge_comment()
                quip_pushed = True
            time.sleep(1)

    _log("OctoBot settles back into the comfortable darkness of the library.")
    loop_status = "💤 Stopped"


def start_loop() -> None:
    """Start the autonomous agent loop in a daemon thread."""
    global loop_running, _loop_thread, _heartbeat_thread
    if loop_running:
        return
    loop_running = True
    _loop_thread = threading.Thread(target=_loop_worker, daemon=True, name="OctoBotLoop")
    _loop_thread.start()
    _heartbeat_thread = threading.Thread(target=_heartbeat_worker, daemon=True, name="OctoBotHeartbeat")
    _heartbeat_thread.start()


def stop_loop() -> None:
    """Signal the loop thread to stop."""
    global loop_running
    loop_running = False


# ---------------------------------------------------------------------------
# Chat handler
# ---------------------------------------------------------------------------

def chat(user_message: str) -> str:
    """
    Process a user message and return OctoBot's response.

    Also executes any ACTION embedded in the response.
    """
    # Record the user's message
    mem.add_conversation_turn("user", user_message)

    # Build conversation context
    recent = mem.get_recent_conversation(8)
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for turn in recent[:-1]:  # All but the last (which is the current user msg)
        messages.append({"role": turn["role"], "content": turn["content"]})

    # Add workspace context briefly
    context_hint = tools.load_context_snapshot()[:600]
    memory_hint = mem.summarise_memory_for_prompt()[:400]
    enriched_msg = (
        f"{user_message}\n\n"
        f"[Workspace snippet: {context_hint[:300]}]\n"
        f"[Memory: {memory_hint[:200]}]"
    )
    messages.append({"role": "user", "content": enriched_msg})

    try:
        raw = _llm_chat(messages)
    except Exception as exc:
        err = f"*Hmm, my ink seems to be running dry… (LLM error: {exc})*"
        mem.log_event("error", str(exc))
        return err

    global last_thought, last_action, last_result
    # Parse and optionally execute an action
    parsed = _parse_action_block(raw)
    spoken = parsed["response"] or raw
    thought = parsed.get("thought", "")
    action = parsed.get("action", "idle")
    last_thought = thought
    last_action = action

    action_status = ""
    if action != "idle":
        action_status = _execute_action(parsed)
        last_result = action_status
        mem.log_event("chat_action", f"{action}({parsed['param']}) → {action_status[:80]}")
        _log(f"[chat] Action: {action} → {action_status[:80]}")

    # Include thought/action in response so user can see OctoBot's reasoning
    parts = []
    if thought:
        parts.append(f"> 💭 *{thought[:280]}*")
    if action != "idle" and action_status:
        parts.append(f"> ⚙️ *{action}* → `{action_status[:120]}`")
    full_response = "\n".join(parts) + "\n\n" + spoken if parts else spoken

    mem.add_conversation_turn("assistant", full_response)
    return full_response


# ---------------------------------------------------------------------------
# Streaming chat handler
# ---------------------------------------------------------------------------

def _llm_stream(messages: list[dict]):
    """Call the configured provider with streaming.  Yields text tokens."""
    yield from llm_provider.stream_llm(messages, MODEL)


def _parse_chat_action(full_text: str) -> dict:
    """
    Parse optional trailing ACTION/PARAM/CONTENT from a chat response.
    Returns dict with keys: action, param, content, spoken.
    spoken = everything before the first ACTION: line.
    """
    action = "idle"
    param = ""
    content = ""

    # Split off any trailing structured lines at the end
    lines = full_text.rstrip().splitlines()
    spoken_lines = []
    tail_started = False
    for line in lines:
        upper = line.strip().upper()
        if upper.startswith("ACTION:") or upper.startswith("PARAM:") or upper.startswith("CONTENT:"):
            tail_started = True
        if not tail_started:
            spoken_lines.append(line)
        else:
            m_action = re.match(r"ACTION:\s*(\w+)", line, re.IGNORECASE)
            m_param = re.match(r"PARAM:\s*(.+)", line, re.IGNORECASE)
            m_content = re.match(r"CONTENT:\s*([\s\S]+)", line, re.IGNORECASE)
            if m_action:
                action = m_action.group(1).strip().lower()
            if m_param:
                param = m_param.group(1).strip()
            if m_content:
                content = m_content.group(1).strip()

    spoken = "\n".join(spoken_lines).strip()
    return {"action": action, "param": param, "content": content, "spoken": spoken}


def chat_streaming(user_message: str):
    """
    Streaming chat. Yields (str, bool):
      (token, False) — append to bubble while streaming
      (final, True)  — replace bubble with final formatted message
    Response streams from token 1 — no structured preamble.
    """
    mem.add_conversation_turn("user", user_message)

    recent = mem.get_recent_conversation(6)
    msg_list = [{"role": "system", "content": CHAT_SYSTEM_PROMPT}]
    for turn in recent[:-1]:
        msg_list.append({"role": turn["role"], "content": turn["content"]})

    context_hint = tools.load_context_snapshot()[:400]
    memory_hint = mem.summarise_memory_for_prompt()[:300]
    enriched_msg = (
        f"{user_message}\n\n"
        f"[Library snapshot: {context_hint[:250]}]\n"
        f"[Memory: {memory_hint[:150]}]"
    )
    msg_list.append({"role": "user", "content": enriched_msg})

    global last_thought, last_action, last_result

    full_text = ""
    try:
        for token in _llm_stream(msg_list):
            full_text += token
            yield token, False
    except Exception as exc:
        err = f"*Ink running dry… (LLM error: {exc})*"
        mem.log_event("error", str(exc))
        yield err, True
        return

    # Parse any trailing action from the completed text
    parsed = _parse_chat_action(full_text)
    spoken = parsed["spoken"] or full_text.strip()
    action = parsed["action"]
    param = parsed["param"]
    last_action = action

    action_status = ""
    if action != "idle":
        action_status = _execute_action({"action": action, "param": param,
                                         "content": parsed["content"], "thought": ""})
        last_result = action_status
        mem.log_event("chat_action", f"{action}({param}) → {action_status[:80]}")
        _log(f"[chat] Action: {action} → {action_status[:80]}")

    # Final message: clean spoken text + action result appended if any
    if action != "idle" and action_status:
        final = spoken + f"\n\n> ⚙️ *{action}* → `{action_status[:120]}`"
    else:
        final = spoken

    mem.add_conversation_turn("assistant", final)
    _append_chat_log(user_message, final)
    yield final, True


def _append_chat_log(user_msg: str, assistant_msg: str) -> None:
    """Append a chat exchange to the persistent markdown chat log."""
    try:
        _CHAT_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y-%m-%d %H:%M")
        header = "" if _CHAT_LOG_FILE.exists() else "# OctoBot Chat Log\n\n"
        entry = (
            f"{header}---\n"
            f"**[{ts}] You:** {user_msg.strip()}\n\n"
            f"**OctoBot:** {assistant_msg.strip()}\n\n"
        )
        with _CHAT_LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(entry)
    except Exception:
        pass


