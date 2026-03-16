"""
game_loop.py — OctoBot Idea Machine Game Loop
===============================================
The gameplay engine that turns OctoBot into an idea-generating invention simulator.

Each cycle follows this sequence:
  1. Check knowledge/ folder for new files → score + graph + discoveries
  2. Read and integrate inspiration into the idea vault
  3. Check comments/ folder for player messages
  4. Read comments and write responses to octobot_journal.md
  5. Check tasks.md for assigned idea domains
  6. Advance any active idea chains
  7. Run curiosity engine (look for new problem areas to tackle)
  8. Run the agent's autonomous idea generation cycle
  9. Check achievements
  10. Update memory and game stats
  11. Log all actions

Cycle timing: 30–120 seconds (configurable via CYCLE_INTERVAL).
"""

import random
import time
import threading
from datetime import datetime

import agent
import tools
import memory as mem
import research as res
import llm_provider
import scoring

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
CYCLE_INTERVAL = 60         # seconds between game cycles
_loop_running = False
_loop_thread: threading.Thread | None = None

# Live state readable by the UI
activity_log: list[str] = []    # timestamped log lines
current_status: str = "💤 OctoBot is sleeping…"
current_action: str = "idle"    # idle|reading|writing|thinking|researching


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def _log(msg: str) -> None:
    """Append a timestamped line to the activity log and print it."""
    line = f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"
    activity_log.append(line)
    if len(activity_log) > 300:
        activity_log.pop(0)
    print(line)
    mem.log_event("game", msg)


def _restore_activity_log() -> None:
    """Pre-populate activity_log from persisted events so the UI isn't blank after restart."""
    try:
        events = mem.get_recent_events(80)
        for e in events:
            ts = e.get("timestamp", "")
            try:
                ts_fmt = datetime.fromisoformat(ts).strftime("%H:%M:%S")
            except Exception:
                ts_fmt = ts[11:19] if len(ts) >= 19 else ts
            detail = e.get("detail", "")
            activity_log.append(f"[{ts_fmt}] {detail}")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Knowledge ingestion (with scoring, graph, and discovery)
# ---------------------------------------------------------------------------

def _check_knowledge() -> list[str]:
    """Scan for new knowledge files, ingest them, score, build graph, check discoveries."""
    global current_status, current_action
    new_files = []

    for rel_path in tools.scan_knowledge_folder():
        if mem.is_file_processed(rel_path):
            continue

        _log(f"📖 Found new knowledge: {rel_path}")
        current_status = f"📖 Reading: {rel_path}"
        current_action = "reading"

        try:
            content = tools.read_file(rel_path)
        except Exception as exc:
            _log(f"❌ Failed to read {rel_path}: {exc}")
            mem.mark_file_processed(rel_path)
            continue

        # Score: new knowledge file
        scoring.add_score(scoring.SCORE_KNOWLEDGE_FILE, f"New knowledge: {rel_path}")

        # Summarise with LLM
        _log(f"🤔 Thinking about: {rel_path}")
        current_status = f"🤔 Digesting knowledge from {rel_path}"
        current_action = "thinking"

        try:
            summary = _summarise_knowledge(rel_path, content)
            title = rel_path.split("/")[-1].replace(".md", "").replace(".txt", "").replace(".json", "")
            title = title.replace("_", " ").replace("-", " ").strip()
            tools.save_research(title, summary)
            _log(f"📚 Saved knowledge summary: {title}")

            # Score: summary created
            scoring.add_score(scoring.SCORE_SUMMARY, f"Summary: {title}")

            # Update knowledge graph
            graph_result = scoring.update_knowledge_graph(rel_path, content + "\n" + summary)
            if graph_result["new_nodes"]:
                _log(f"🕸️ Graph: +{len(graph_result['new_nodes'])} concepts")
            if graph_result["new_edges"]:
                _log(f"🔗 Graph: +{len(graph_result['new_edges'])} connections")

            # Check for cross-references
            new_concepts = scoring._extract_concepts(content + "\n" + summary)
            cross_refs = scoring.find_cross_references(new_concepts, exclude_file=rel_path)
            if cross_refs:
                for xref in cross_refs[:3]:
                    scoring.add_score(scoring.SCORE_CROSS_REF, f"Cross-ref: {xref['concept']}")
                    mem.increment_game_stat("cross_refs")
                _log(f"🔗 Found {len(cross_refs)} cross-reference(s)!")

            # Check for discovery event
            discovery = scoring.check_for_discovery(new_concepts, rel_path, model=agent.MODEL)
            if discovery:
                scoring.add_score(scoring.SCORE_DISCOVERY, f"Discovery: {discovery['insight'][:60]}")
                _log(f"💡 DISCOVERY: {discovery['insight'][:100]}")
                tools.append_journal(
                    f"## 💡 Major Discovery!\n\n{discovery['insight']}\n\n"
                    f"Connected concepts from: {', '.join(discovery['files'])}"
                )

            # Journal entry
            tools.append_journal(
                f"One of my arms discovered some inspiration: **{title}**\n\n"
                f"I have read it carefully and invented something delightful from it. "
                f"The idea vault grows! So many more problems to solve!"
            )
            current_action = "writing"
        except Exception as exc:
            _log(f"❌ Failed to process {rel_path}: {exc}")

        mem.mark_file_processed(rel_path)
        mem.increment_game_stat("knowledge_count")
        mem.adjust_curiosity(5)
        new_files.append(rel_path)

    return new_files


def _summarise_knowledge(filename: str, content: str) -> str:
    """Ask the LLM to generate an idea inspired by a knowledge document."""
    snippet = content[:3000]
    return llm_provider.call_llm(
        messages=[
            {"role": "system", "content": (
                "You are OctoBot — a gloriously chaotic pink octopus inventor. "
                "Read the following document and use it as a springboard to invent ONE original idea — "
                "a product, gadget, service, app, creative project, or solution. "
                "Give it a name, explain what problem it solves, how it works, and why it's brilliant. "
                "Bold **key concepts** for indexing. Be inventive, specific, and punny. Write 200–400 words."
            )},
            {"role": "user", "content": (
                f"Inspiration document: {filename}\n\n{snippet}"
            )},
        ],
        model=agent.MODEL,
    )


# ---------------------------------------------------------------------------
# Comment reading & responding
# ---------------------------------------------------------------------------

def _check_comments() -> list[str]:
    """Read new comments and write responses to the journal."""
    global current_status, current_action
    new_comments = []

    for rel_path in tools.scan_comments_folder():
        if mem.is_file_processed(rel_path):
            continue

        _log(f"💬 Found new comment: {rel_path}")
        current_status = f"💬 Reading comment: {rel_path}"
        current_action = "reading"

        try:
            content = tools.read_file(rel_path)
        except Exception as exc:
            _log(f"❌ Failed to read comment {rel_path}: {exc}")
            mem.mark_file_processed(rel_path)
            continue

        _log(f"✍️ Composing response to: {rel_path}")
        current_status = f"✍️ Responding to comment"
        current_action = "writing"

        try:
            response = _respond_to_comment(content)
            tools.append_journal(
                f"**A message from my human companion** (from `{rel_path}`):\n\n"
                f"> {content.strip()[:500]}\n\n"
                f"**My response:**\n\n{response}"
            )
            _log(f"📝 Response written to journal")

            # Extract curious terms from the comment for later research
            curious = scoring.extract_curious_terms(content)
            if curious:
                _log(f"🧠 Curious terms from comment: {', '.join(curious[:3])}")

        except Exception as exc:
            _log(f"❌ Failed to respond: {exc}")

        mem.mark_file_processed(rel_path)
        mem.increment_game_stat("comments_read")
        mem.adjust_curiosity(3)
        new_comments.append(rel_path)

    return new_comments


def _respond_to_comment(comment_text: str) -> str:
    """Generate an in-character response to a player comment."""
    return llm_provider.call_llm(
        messages=[
            {"role": "system", "content": agent.SYSTEM_PROMPT},
            {"role": "user", "content": (
                f"The player left you a comment. Respond warmly and in character. "
                f"If they ask you to research something, mention you'll look into it. "
                f"Be playful and use puns.\n\n"
                f"Their message:\n{comment_text.strip()[:1000]}"
            )},
        ],
        model=agent.MODEL,
    )


# ---------------------------------------------------------------------------
# Task checking
# ---------------------------------------------------------------------------

def _check_tasks() -> list[str]:
    """Read tasks.md and extract uncompleted research tasks."""
    try:
        content = tools.read_file("tasks.md")
    except FileNotFoundError:
        return []
    import re
    tasks = re.findall(r"-\s*\[\s*\]\s*(?:Research:?\s*)(.+)", content, re.IGNORECASE)
    return [t.strip() for t in tasks if t.strip()]


# ---------------------------------------------------------------------------
# Research chains
# ---------------------------------------------------------------------------

def _advance_chains() -> list[str]:
    """Advance any active research chains by one step."""
    global current_status, current_action
    completed_steps = []

    active = scoring.get_active_chains()
    if not active:
        return completed_steps

    # Work on one chain per cycle
    chain = active[0]
    step_idx = chain["current_step"]
    if step_idx >= len(chain["steps"]):
        return completed_steps

    step_topic = chain["steps"][step_idx]
    _log(f"⛓️ Research chain [{chain['root']}] step {step_idx + 1}/{len(chain['steps'])}: {step_topic}")
    current_status = f"⛓️ Chain research: {step_topic}"
    current_action = "researching"

    try:
        result = res.conduct_research(step_topic)
        scoring.advance_research_chain(chain["id"], result)
        scoring.add_score(scoring.SCORE_RESEARCH_CHAIN, f"Chain step: {step_topic}")
        mem.increment_game_stat("research_count")
        mem.adjust_curiosity(4)
        completed_steps.append(step_topic)
        _log(f"⛓️ Chain step complete: {step_topic}")

        # If chain just finished, big score bonus
        updated = scoring.get_active_chains()
        if not any(c["id"] == chain["id"] for c in updated):
            _log(f"🏆 Research chain COMPLETE: {chain['root']}")
            scoring.add_score(scoring.SCORE_RESEARCH_CHAIN * 2, f"Chain complete: {chain['root']}")
            tools.append_journal(
                f"## 🏆 Idea Chain Complete!\n\n"
                f"I have completed a full idea chain on **{chain['root']}**!\n"
                f"Steps: {' → '.join(chain['steps'])}\n\n"
                f"This is EXTRAORDINARY. My tentacles tingle with inventor's pride!"
            )
    except Exception as exc:
        _log(f"❌ Chain research failed: {exc}")

    return completed_steps


# ---------------------------------------------------------------------------
# Curiosity engine
# ---------------------------------------------------------------------------

def _run_curiosity_engine() -> str | None:
    """
    Check recent knowledge for interesting terms and potentially
    start a new research chain or autonomous research.
    """
    global current_status, current_action
    stats = mem.get_game_stats()
    curiosity = stats.get("curiosity_level", 50)

    # High curiosity = more likely to trigger autonomous research
    if curiosity < 30 or random.random() > (curiosity / 100):
        return None

    # Gather terms from recent library entries
    library_files = sorted([f for f in tools.list_files("library") if f.endswith(".md")])[-5:]
    all_terms = []
    for f in library_files:
        try:
            content = tools.read_file(f)
            all_terms.extend(scoring.extract_curious_terms(content))
        except Exception:
            pass

    topic = scoring.pick_curiosity_topic(all_terms, model=agent.MODEL)
    if not topic:
        return None

    _log(f"🧠 Curiosity triggered! Interested in: {topic}")
    current_status = f"🧠 Curiosity: investigating {topic}"
    current_action = "thinking"

    # 30% chance to start a research chain instead of single research
    if random.random() < 0.3:
        chain = scoring.start_research_chain(topic, model=agent.MODEL)
        _log(f"⛓️ Started research chain: {topic} → {' → '.join(chain['steps'])}")
        tools.append_journal(
            f"## 🧠 Idea Spark!\n\n"
            f"I keep noticing **{topic}** as an unexplored problem space. Time to invent something!\n\n"
            f"I'm planning an idea chain: {' → '.join(chain['steps'])}"
        )
        return f"Started chain: {topic}"
    else:
        try:
            result = res.conduct_research(topic)
            scoring.add_score(scoring.SCORE_SUMMARY, f"Curiosity research: {topic}")
            mem.increment_game_stat("research_count")
            _log(f"🧠 Curiosity research complete: {topic}")
            return f"Researched: {topic}"
        except Exception as exc:
            _log(f"❌ Curiosity research failed: {exc}")
            return None


# ---------------------------------------------------------------------------
# Main game cycle
# ---------------------------------------------------------------------------

def run_game_cycle() -> str:
    """
    Run a single game cycle. This is the core gameplay loop step.
    Returns a status string describing what happened.
    """
    global current_status, current_action
    status_parts = []

    current_status = "🔄 Starting new cycle…"
    current_action = "idle"
    mem.increment_game_stat("total_cycles")

    # Step 1: Check knowledge folder
    new_knowledge = _check_knowledge()
    if new_knowledge:
        status_parts.append(f"Ingested {len(new_knowledge)} knowledge file(s)")

    # Step 2: Check comments
    new_comments = _check_comments()
    if new_comments:
        status_parts.append(f"Read {len(new_comments)} comment(s)")

    # Step 3: Advance research chains
    chain_steps = _advance_chains()
    if chain_steps:
        status_parts.append(f"Chain steps: {len(chain_steps)}")

    # Step 4: Check tasks for research topics
    pending_tasks = _check_tasks()
    if pending_tasks and random.random() < 0.4:
        task_topic = random.choice(pending_tasks)
        _log(f"📋 Working on task: {task_topic}")
        current_status = f"🔬 Researching task: {task_topic}"
        current_action = "thinking"
        try:
            result = res.conduct_research(task_topic)
            mem.increment_game_stat("research_count")
            scoring.add_score(scoring.SCORE_SUMMARY, f"Task research: {task_topic}")
            mem.adjust_curiosity(3)
            status_parts.append(f"Researched task: {task_topic}")
            _log(f"✅ Task research complete: {task_topic}")
        except Exception as exc:
            _log(f"❌ Task research failed: {exc}")
    elif not chain_steps:
        # Step 5: Run curiosity engine
        curiosity_result = _run_curiosity_engine()
        if curiosity_result:
            status_parts.append(curiosity_result)
        else:
            # Step 6: Run agent's normal autonomous cycle
            current_action = "thinking"
            try:
                cycle_result = agent.run_one_cycle()
                mem.increment_game_stat("research_count")
                scoring.add_score(scoring.SCORE_SUMMARY, "Autonomous research")
                mem.adjust_curiosity(2)
                status_parts.append(cycle_result[:120])
            except Exception as exc:
                _log(f"❌ Agent cycle error: {exc}")
                status_parts.append(f"Error: {exc}")

    # Step 7: Update knowledge count in stats
    kc = tools.get_knowledge_count()
    mem.update_game_stat("knowledge_count", kc)

    # Curiosity decays slightly when idle
    if not new_knowledge and not new_comments:
        mem.adjust_curiosity(-1)

    # Step 8: Check achievements
    new_achievements = scoring.check_achievements()
    for ach in new_achievements:
        _log(f"🏅 Achievement unlocked: {ach['name']}!")
        tools.append_journal(f"## 🏅 Achievement Unlocked: {ach['name']}!\n\n{ach['desc']}")
        status_parts.append(f"🏅 {ach['name']}")

    current_status = f"✅ Cycle complete — {' | '.join(status_parts) or 'resting'}"
    current_action = "idle"
    _log(current_status)

    return " | ".join(status_parts) if status_parts else "OctoBot rested quietly."


# ---------------------------------------------------------------------------
# Background loop
# ---------------------------------------------------------------------------

def _loop_worker() -> None:
    """Background thread: run the game loop indefinitely."""
    global _loop_running, current_status
    _restore_activity_log()

    # Summarise what was reloaded from persistent memory
    try:
        stats = mem.get_game_stats()
        lib_count = len([f for f in tools.list_files("library") if f.endswith(".md")])
        chains = scoring.get_all_chains()
        achievements = scoring.get_achievements()
        score = stats.get("knowledge_score", 0)
        _log(f"🐙 OctoBot wakes up — restored {lib_count} ideas in the vault, "
             f"{len(chains)} chains, {len(achievements)} badges, score={score}")
    except Exception:
        _log("🐙 OctoBot wakes up and stretches all eight arms. The idea machine is ONLINE!")

    # Backfill knowledge graph from existing library files on first start
    try:
        graph = scoring.get_knowledge_graph()
        lib_count = len([f for f in tools.list_files("library") if f.endswith(".md")])
        if len(graph.get("nodes", [])) < lib_count // 2:
            _log("🕸️ Building idea graph from vault…")
            current_status = "🕸️ Building idea graph…"
            result = scoring.backfill_graph_from_library()
            _log(f"🕸️ Graph ready: {result['total_nodes']} concepts, {result['total_edges']} connections from {result['files_processed']} files")
    except Exception as exc:
        _log(f"⚠️ Graph backfill error: {exc}")

    while _loop_running:
        try:
            run_game_cycle()
        except Exception as exc:
            _log(f"⚠️ Game loop error: {exc}")
            current_status = f"⚠️ Error: {str(exc)[:80]}"

        current_status = f"💤 Resting… next cycle in {CYCLE_INTERVAL}s"
        for _ in range(CYCLE_INTERVAL):
            if not _loop_running:
                break
            time.sleep(1)

    _log("🐙 OctoBot powers down the idea machine. Goodnight, beautiful problems!")
    current_status = "💤 Stopped"


def start_loop() -> None:
    """Start the game loop in a daemon thread."""
    global _loop_running, _loop_thread
    if _loop_running:
        return
    _loop_running = True
    _loop_thread = threading.Thread(target=_loop_worker, daemon=True, name="OctoBotGameLoop")
    _loop_thread.start()


def stop_loop() -> None:
    """Signal the game loop to stop."""
    global _loop_running
    _loop_running = False
