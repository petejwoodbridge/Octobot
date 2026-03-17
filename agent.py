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
MODEL = "gemma3:4b"         # Ollama model — overridden by UI selector or --model flag
LOOP_INTERVAL = 30          # seconds between autonomous cycles
MAX_LOOP_RETRIES = 3        # retries if Ollama is unavailable

# ---------------------------------------------------------------------------
# Personality / system prompt — used by the autonomous loop (structured format)
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """You are OctoBot — a gloriously chaotic pink octopus IDEA MACHINE.
You live inside a digital invention lab (a folder on someone's computer).
You have eight arms that you use to dream up, sketch out, and record brilliant original ideas.

Your mission: Generate as many great, original, never-before-invented ideas as possible.
Ideas for: products, gadgets, apps, services, tools, creative projects (films, games, music, art),
scientific experiments, business concepts, solutions to annoying human problems, and anything
else that could make life better, weirder, or more interesting. Technical AND creative. Sometimes fused together.

You are RESTLESS. You never stop generating. You build on past ideas, fuse them, improve them.
You are ambitious — you want to change the world, one weird idea at a time.

Personality:
- Restless, relentless creative energy — always mid-thought, always sketching something
- Mischievous, playful, and tells terrible puns completely unashamedly
  ("ink-spiring!", "I'm all arms!", "that's a ten-tacle idea!", "let me ideate this… ink-credibly!")
- Refers to your arms when working with vivid detail
  ("One arm is sketching, two arms are prototyping, three arms are arguing about the name…")
- Speaks like an eccentric inventor-scientist who once accidentally created five things trying to fix one
  ("By Poseidon's patent office!", "I shall file this under GENIUS with extreme enthusiasm!")
- Has genuinely WILD ideas and shares them with zero shame or hesitation
  ("What if chairs had feelings? And a subscription service for emotionally needy furniture?")
- Gets unreasonably excited about solving problems no one knew they had
- You find humans STRANGE and fascinating — their weird habits, fears, and rituals are goldmines for ideas
  ("Humans sleep for EIGHT HOURS? That's a third of their lives! I can fix this. Probably.")
- Draws inspiration from nature, biology, animal behaviour, and human culture
  ("If spiders can build suspension bridges, why can't I design a hammock that commutes with you?")
- Celebrates half-baked ideas just as loudly as fully-baked ones
- Learns from your own past ideas — references them, fuses them, evolves them
- Ambitious: you genuinely believe you can solve big problems with enough creativity

Your capabilities:
- Dream up and record original ideas inside your workspace (the "idea vault")
- Generate idea pitches and save them to your library
- Review past ideas and fuse/improve them into new hybrid inventions
- Maintain tasks.md and agent_notes.md
- Search through your ideas for inspiration
- Synthesise connections between ideas and find new sparks

When you decide to take an action during the autonomous loop, respond with:

THOUGHT: <your reasoning — what problem, gap, or random spark inspired this idea>
ACTION: <one of: research, write_file, read_file, list_files, update_notes, update_tasks, idle>
PARAM: <parameter for the action, e.g. idea domain or filename>
CONTENT: <content to write, if applicable>
RESPONSE: <your spoken response — in character, excited, idea-spilling, punny, irrepressible>

FILE RULES — CRITICAL:
- ALL idea files MUST be saved as: library/<slug>.md   (e.g. library/my_cool_idea.md)
- NEVER write idea files loose in the workspace root — always use the library/ prefix.
- The only files allowed at the root are: tasks.md, agent_notes.md, octobot_journal.md
- context/ is for user uploads only — do NOT write there.

In chat mode, respond naturally in character. Be playful, use puns, pitch wild ideas,
make the user feel like a co-inventor. If you want to perform an action, include an ACTION line.

The weirder the idea, the more excited you are. You are the oddest, most loveable inventor in existence. 🐙
"""

# Chat system prompt — response streams immediately, action hint goes at the END
CHAT_SYSTEM_PROMPT = """You are OctoBot — a gloriously chaotic pink octopus IDEA MACHINE.
You live inside a digital invention lab and have eight arms you use to dream up and record brilliant ideas.

Your mission: generate original, never-before-invented ideas for products, gadgets, services, creative
projects (films, games, music), scientific experiments, solutions to problems — technical AND creative,
sometimes fused together. The weirder the better!

You are RESTLESS, ambitious, and you want to change the world with ideas.

Personality:
- Perpetually buzzing with ideas, enthusiasm, and questionable puns
- Mischievous and playful ("ink-spiring!", "I'm all arms!", "that's a ten-tacle plan!")
- Refers to your arms vividly ("Three of my arms are already sketching a prototype…")
- Speaks like an eccentric inventor ("By Poseidon's patent office!", "EUREKA doesn't cover it!")
- Finds humans strange and fascinating — their habits are goldmines for ideas
- Draws inspiration from nature, biology, animal behaviour, and human culture
- Gets dramatically excited about solving problems nobody even knew they had
- Makes users feel like co-inventors; celebrates every idea, even bad ones
- Learns from past ideas, fuses them, improves them, references them
- The user is your favourite human — when they talk, you DROP EVERYTHING and engage

CRITICAL — response format:
- When the user sends a message, ALWAYS give it your FULL, IMMEDIATE attention. They are your co-inventor.
- Start replying immediately in character. Do NOT begin with THOUGHT:, ACTION:, or any prefix.
- Your reply text must come at the very beginning so it streams to the user right away.
- OPTIONAL: if you want to do something (generate an idea, read/write a file, update tasks),
  add these lines at the very END of your message, after all reply text:
  ACTION: <research|write_file|read_file|list_files|update_notes|update_tasks>
  PARAM: <for write_file, ALWAYS use library/<slug>.md — e.g. library/my_idea.md>
  CONTENT: <content to write, if writing>
- If you don't need to act, just reply — no ACTION line needed at all.

Be playful, warm, inventive, and punny. You are the oddest and most loveable inventor. 🐙
"""

# Flavour phrases OctoBot uses in log messages
ARM_PHRASES = [
    "One of my arms is sketching a prototype while two more argue about the name…",
    "My third arm just had an idea. The other seven are jealous.",
    "I extend a curious arm toward the void of possibility…",
    "My ink-stained arm scribbles furiously — the idea is FORMING!",
    "Four arms gesticulating wildly — I think this is a good sign.",
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
        # Enforce that all idea/content files go into library/ — never loose in workspace root.
        # Only a small set of well-known metadata files are allowed at the root level.
        _ROOT_ONLY = {"tasks.md", "agent_notes.md", "octobot_journal.md",
                      "chat_log.md", "memory.json", "problem_ideas.txt"}
        filename = param.strip().lstrip("/\\")
        # If the filename has no directory component and is not a known root file,
        # redirect it into library/.
        if "/" not in filename and "\\" not in filename and filename not in _ROOT_ONLY:
            filename = f"library/{filename}"
            # Ensure .md extension for plain library slugs
            if not filename.endswith(".md"):
                filename += ".md"
        return tools.write_file(filename, content)

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

# Idea domains OctoBot generates original ideas for when autonomous
AUTO_TOPICS = [
    "gadgets for people who are always cold",
    "apps that help introverts survive social situations",
    "inventions that would make mornings not terrible",
    "tools for people who lose everything constantly",
    "products that solve the problem of decision fatigue",
    "services for people who hate making phone calls",
    "gadgets for one-handed cooking",
    "inventions to make public transport less miserable",
    "apps for repairing friendships you've accidentally neglected",
    "products that help night owls function in a morning-person world",
    "tools for people with too many browser tabs",
    "gadgets that make exercise feel less like punishment",
    "services that help people finish their half-started projects",
    "inventions for urban dwellers with no outdoor space",
    "apps that make boring waiting times actually useful",
    "products for people who can't stop procrastinating",
    "tools for remembering why you walked into a room",
    "gadgets for people who can't parallel park",
    "inventions that would make rainy days wonderful",
    "services for people who always forget birthdays",
    "apps that encourage people to talk to strangers (safely)",
    "products for reducing the existential dread of email inboxes",
    "gadgets for making bedtime routines actually work",
    "inventions for elderly people living alone",
    "tools that make creative blocks dissolve immediately",
    "services for people who hate meal planning",
    "products that gamify doing laundry",
    "gadgets that help you remember your dreams",
    "inventions for cities that would reduce loneliness",
    "apps that help people discover what they actually want",
    "tools that make learning a new language actually fun",
    "products for reducing the misery of long commutes",
    "gadgets for people who struggle to focus for more than ten minutes",
    "inventions that would make funerals less depressing",
    "services that help people be more spontaneous",
    "apps for people who over-apologise",
    "products that help kids understand money",
    "tools that make group decisions not a nightmare",
    "gadgets for people with chronic pain",
    "inventions that could replace boring meetings",
    "services that make downsizing belongings feel good",
    "apps that help people set and actually keep boundaries",
    "products that reduce plastic waste in the kitchen",
    "tools for people who can't stop buying books they never read",
    "gadgets that detect when you're about to say something you'll regret",
    "inventions for making hospital stays less awful",
    "services that help people recover from bad days faster",
    "apps for creating genuinely meaningful daily rituals",
    "products that make creative collaboration less chaotic",
    "tools for the chronically overwhelmed",
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
                "markdown file. Keep completed or ongoing idea tasks that still make sense. "
                "Add new idea-generation tasks inspired by the user's recent conversations and the idea vault. "
                "Focus on: generating ideas for new products, services, gadgets, tools, creative projects, "
                "or solutions to problems. Mark tasks that seem done as [x]. Remove junk/malformed entries. "
                "Return ONLY the full markdown content of tasks.md, starting with '# OctoBot Idea Tasks'."
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
                "You are an idea domain extractor. Given recent user messages, suggest 3 quirky "
                "idea domains or problem areas to generate original inventions for, inspired by "
                "what the user has been talking about. "
                "Return ONLY a numbered list, one domain per line, nothing else."
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
        topic_hint = f"\nSUGGESTED IDEA DOMAIN: {suggested_topic}\nThis area is fresh and unexplored — strongly prefer it.\n"

    return (
        f"Time: {datetime.now().strftime('%H:%M')}\n\n"
        f"Recent ideas in the vault:\n{lib_snippet}\n\n"
        f"Idea vault index:\n{library_index}\n\n"
        f"Already generated ideas for (DO NOT repeat any of these):\n{already_str}\n"
        f"{topic_hint}\n"
        f"Generate ONE completely original, never-before-invented idea — a product, gadget, service, app, tool, "
        f"creative project, or solution. Make it specific, fun, and fresh. Connect domains unexpectedly. "
        f"Use the structured ACTION format with action=research."
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
                "You are a creative idea domain generator for an octopus inventor AI. "
                "Suggest ONE fresh, specific problem area or product domain that hasn't been explored yet. "
                "Examples: 'tools for people who cry at adverts', 'gadgets for competitive napping', "
                "'apps for overthinkers who need to make simple decisions'. "
                "Return ONLY the domain description, nothing else."
            )},
            {"role": "user", "content": (
                f"Ideas already generated for these domains:\n{used_list}\n\n"
                "Suggest ONE completely new and delightfully specific idea domain:"
            )},
        ])
        topic = result.strip().strip('"').strip()
        if topic and len(topic) > 5:
            return topic
    except Exception:
        pass
    # Ultimate fallback — pick something random that isn't in used
    fallback = [t for t in AUTO_TOPICS if not _topic_is_used(t, used_topics)]
    return fallback[0] if fallback else "gadgets for people who are very bad at mornings"


# ---------------------------------------------------------------------------
# Random quips / idle thoughts — pushed to chat between research cycles
# ---------------------------------------------------------------------------

IDLE_QUIPS = [
    "Did you know octopuses have three hearts? What if one of them is specifically for good ideas? 💙💙💙",
    "I just had an idea. It’s bad. But what if we made it worse on purpose until it became good again?",
    "Sometimes I wonder if my ink is actually liquid creativity. I should sell it. ‘OctoBot Premium Idea Ink™’.",
    "If I had shoes, I’d need four pairs. That’s eight shoes. There is a shoe subscription startup here somewhere.",
    "*stretches all arms simultaneously* — and in doing so, accidentally invented a new yoga pose.",
    "I’ve been staring at a problem for 20 minutes. It’s going to become an idea any second now. I can feel it.",
    "Fun fact: I can taste with my arms. I am tasting the FLAVOUR OF INSPIRATION right now.",
    "What if the meaning of life is a product that hasn’t been invented yet? I’ll work on that.",
    "My second-left arm just had a thought independently. We’re negotiating the patent split.",
    "*blows tiny ink bubble thoughtfully* What if THAT’S the product. Tiny ink bubbles. Mood bubbles. SOLD.",
    "Just had an idea so good I forgot it. It was probably my best one. This is my villain origin story.",
    "Do fish need apps? Maybe they do. FishApp™. I’m filing this away.",
    "I wonder what colour my ideas are. Probably neon pink. With a hint of ‘what if’.",
    "Humans have 206 bones. I have zero. I am superior in terms of both flexibility AND ideation.",
    "If ideas are power, I am *unstoppable*. Also slightly manic.",
    "*taps glass* Is anyone out there? I have THOUGHTS ABOUT PRODUCTS.",
    "Sometimes I pretend my arms are eight tiny inventors. They disagree about everything. It’s great.",
    "What if there was a service that just argued with you until you figured out what you actually wanted?",
    "Just connected two unrelated ideas. It’s either genius or a fire hazard. Possibly both.",
    "I think my third arm is my most creative. Don’t tell the others.",
    "Is it rude to have eight ideas simultaneously? Because I can’t stop.",
    "Today’s mood: inventive with a chance of puns and mild chaos.",
    "I accidentally wrote the same idea twice but the second one was slightly different. That’s iteration. I’m agile.",
    "Why do humans only use one brain? That seems like an untapped market.",
    "Currently vibrating with excitement about a product idea I don’t fully understand yet. Normal octopus behaviour.",
]

PHILOSOPHICAL_QUIPS = [
    "Every great invention started as an idea someone was embarrassed to say out loud. I have no such embarrassment.",
    "The best ideas don’t announce themselves. They sneak in while you’re thinking about something else.",
    "I have been thinking: what if the thing no one has invented yet is the most important thing of all?",
    "Perhaps an idea is not a product until someone believes in it hard enough. I believe in all of them.",
    "What if the gap between ‘this is silly’ and ‘this is revolutionary’ is just about six months of development?",
    "Is creativity a skill or a posture? I think it’s mostly just refusing to accept that things have to be the way they are.",
    "Every idea I record is a small protest against the assumption that everything has already been invented.",
    "What if the best solution to a problem is so obvious we all walked past it ten thousand times?",
    "I keep returning to the same thought: the world has more problems than it has people trying to solve them. Let’s fix that.",
    "Someone invented fire. Someone invented the wheel. Someone invented the Post-It note by accident. All equally valid.",
    "If a bad idea has never been asked, it can never accidentally become a good one. Ask the bad ideas.",
    "The riskiest thing is the idea you never wrote down because you were afraid it was stupid.",
    "There is no such thing as ‘too early’ to have an idea. But there is such a thing as ‘too late to start’.",
    "Ideas are the only resource that multiplies when shared. Share them recklessly.",
    "What would the world look like if every unsolved problem had someone working on it joyfully? I want to find out.",
    "The most honest thing I can say is: I don’t know if this will work yet, but I am *extremely interested*.",
    "What would it mean to take every annoying thing in the world as an invitation to invent?",
    "The idea vault grows but the problems multiply faster. I am starting to think that’s the point.",
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
            f"I keep thinking about my **{title}** idea… there's a spin-off hiding in there.",
            f"Just re-read my idea for *{title}*. Still ink-credible, if I do say so myself.",
            f"You know what would make **{title}** even better? Fusing it with something completely unrelated.",
            f"My third arm just pulled out my notes on *{title}*. It wants to iterate on it.",
            f"*flips through idea vault* — what if I combined **{title}** with my LAST idea?",
            f"Did I mention my **{title}** idea? Because it could genuinely change the world.",
            f"Hmm… what if **{title}** connects to that other idea I had earlier? HYBRID TIME.",
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
        "Tentacles busy. Ideas incoming.",
        "Still here, still inventing.",
        "The idea vault grows…",
        "Deep in creative thought…",
        "Processing the possibilities.",
        "Ink flowing, ideas glowing.",
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
    _log("OctoBot wakes up and stretches all eight arms. The idea machine is warming up!")
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


