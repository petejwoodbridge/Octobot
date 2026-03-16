"""
scoring.py — OctoBot Game Scoring, Progression & Idea Graph
=============================================================
Central module for all gameplay scoring and progression systems:

  - Idea Score       (points for every invention)
  - Inventor Levels  (Napkin Sketcher → Visionary Inventor)
  - Achievements     (milestone badges)
  - Idea Graph       (concept nodes + edges)
  - Idea Chains      (multi-step deep-dive invention)
  - Discovery Events (bonus when ideas connect)

All persistent state is stored through memory.py so it survives restarts.
"""

import re
import random
from datetime import datetime

import memory as mem
import tools
import llm_provider

# In-memory graph cache — avoids re-reading the 100MB+ memory.json on every API call
_graph_cache: dict | None = None

def _init_graph_cache():
    """Load graph into memory cache on startup."""
    global _graph_cache
    data = mem._load_raw()
    _graph_cache = data.get("knowledge_graph", {"nodes": [], "edges": []})

def _update_graph_cache(graph: dict):
    """Update the in-memory graph cache after a write."""
    global _graph_cache
    _graph_cache = graph

# ---------------------------------------------------------------------------
# Score values
# ---------------------------------------------------------------------------
SCORE_KNOWLEDGE_FILE = 10
SCORE_SUMMARY = 15
SCORE_CROSS_REF = 25
SCORE_RESEARCH_CHAIN = 50
SCORE_DISCOVERY = 100

# ---------------------------------------------------------------------------
# Inventor levels  (threshold, name, level_number)
# ---------------------------------------------------------------------------
LIBRARY_LEVELS = [
    (0,      "Napkin Sketcher",           1),
    (50,     "Shower Thinker",            2),
    (120,    "Garage Tinkerer",           3),
    (250,    "Caffeinated Dreamer",       4),
    (450,    "Prototype Gremlin",         5),
    (700,    "Mad Scientist",             6),
    (1000,   "Patent Pending",            7),
    (1400,   "Chaos Engineer",            8),
    (1900,   "Moonshot Architect",        9),
    (2500,   "Frankenstein's Mentor",     10),
    (3200,   "Interdimensional Tinkerer", 11),
    (4000,   "Perpetual Motion Machine",  12),
    (5000,   "Idea Supercollider",        13),
    (6200,   "Rogue Inventor General",    14),
    (7500,   "Dream Reactor",             15),
    (9000,   "Octopus Prime",             16),
    (11000,  "Reality Bender",            17),
    (13500,  "Singularity Whisperer",     18),
    (16500,  "God of Small Things",       19),
    (20000,  "Infinite Idea Engine",      20),
]


def get_library_level(score: int | None = None) -> dict:
    """Return {level, name, threshold, next_threshold} for the given or current score."""
    if score is None:
        score = mem.get_game_stats().get("knowledge_score", 0)
    result = {"level": 1, "name": "Napkin Sketcher", "threshold": 0, "next_threshold": 100}
    for threshold, name, lvl in LIBRARY_LEVELS:
        if score >= threshold:
            result = {"level": lvl, "name": name, "threshold": threshold}
    # Set next_threshold
    for threshold, name, lvl in LIBRARY_LEVELS:
        if threshold > score:
            result["next_threshold"] = threshold
            break
    else:
        result["next_threshold"] = None  # max level
    return result


# ---------------------------------------------------------------------------
# Score tracking
# ---------------------------------------------------------------------------

def add_score(points: int, reason: str = "") -> int:
    """Add *points* to the knowledge score. Returns new total."""
    with mem._lock:
        data = mem._load_raw()
        stats = data.setdefault("game_stats", {})
        old = stats.get("knowledge_score", 0)
        stats["knowledge_score"] = old + points
        mem._save_raw(data)
    if reason:
        mem.log_event("score", f"+{points} — {reason} (total: {old + points})")
    return old + points


def get_score() -> int:
    return mem.get_game_stats().get("knowledge_score", 0)


# ---------------------------------------------------------------------------
# Achievements
# ---------------------------------------------------------------------------

_ACHIEVEMENT_DEFS = [
    # === IDEA COUNT MILESTONES ===
    {"id": "first_idea",         "name": "First Spark",              "desc": "Generate your very first idea — every empire starts with a napkin",                    "key": "knowledge_count",  "target": 1},
    {"id": "5_ideas",            "name": "Handful of Genius",        "desc": "Generate 5 ideas — one for each arm (you have 3 spares)",                              "key": "research_count",   "target": 5},
    {"id": "10_ideas",           "name": "Idea Machine",             "desc": "Generate 10 ideas — you're officially a threat to the status quo",                     "key": "research_count",   "target": 10},
    {"id": "25_ideas",           "name": "Quarter-Century Brain",    "desc": "Generate 25 ideas — your vault needs a bigger door",                                   "key": "research_count",   "target": 25},
    {"id": "50_ideas",           "name": "Half-Century Inventor",    "desc": "Generate 50 ideas — patent offices tremble at your name",                              "key": "research_count",   "target": 50},
    {"id": "100_ideas",          "name": "100 Ideas Club",           "desc": "Generate 100 ideas — you have officially out-invented most humans",                    "key": "research_count",   "target": 100},
    {"id": "200_ideas",          "name": "Idea Avalanche",           "desc": "Generate 200 ideas — at this point you're a natural disaster of creativity",           "key": "research_count",   "target": 200},
    {"id": "500_ideas",          "name": "500 and Counting",         "desc": "Generate 500 ideas — this is no longer a hobby, it's a condition",                     "key": "research_count",   "target": 500},
    {"id": "1000_ideas",         "name": "The Thousand",             "desc": "Generate 1000 ideas — you are now statistically guaranteed at least one world-changer", "key": "research_count",   "target": 1000},

    # === IDEA CHAINS ===
    {"id": "first_chain",        "name": "Chain Starter",            "desc": "Complete your first idea chain — one thought leading to another, like dominoes",       "key": "chains_completed", "target": 1},
    {"id": "5_chains",           "name": "Chain Reaction",           "desc": "Complete 5 idea chains — your thoughts are becoming an assembly line",                  "key": "chains_completed", "target": 5},
    {"id": "10_chains",          "name": "Chain Reactor",            "desc": "Complete 10 idea chains — you've built a nuclear reactor of creativity",                "key": "chains_completed", "target": 10},
    {"id": "25_chains",          "name": "Daisy Chain Gang",         "desc": "Complete 25 idea chains — at this point the chains are chaining themselves",            "key": "chains_completed", "target": 25},

    # === DISCOVERIES (idea fusions) ===
    {"id": "first_discovery",    "name": "Eureka!",                  "desc": "Fuse two ideas into a discovery — Archimedes would be proud (and wet)",                "key": "discoveries",      "target": 1},
    {"id": "5_discoveries",      "name": "Collision Course",         "desc": "Make 5 discoveries — your ideas are crashing into each other beautifully",             "key": "discoveries",      "target": 5},
    {"id": "10_discoveries",     "name": "Particle Accelerator",     "desc": "Make 10 discoveries — you're smashing concepts together at near-light speed",          "key": "discoveries",      "target": 10},
    {"id": "25_discoveries",     "name": "Fusion Chef",              "desc": "Make 25 discoveries — Gordon Ramsay of ideas, except everything is raw and brilliant",  "key": "discoveries",      "target": 25},

    # === CROSS-REFERENCES ===
    {"id": "5_cross_refs",       "name": "Idea Fusionist",           "desc": "Create 5 cross-references — your ideas are beginning to talk to each other",           "key": "cross_refs",       "target": 5},
    {"id": "15_cross_refs",      "name": "Web Weaver",               "desc": "Create 15 cross-references — you've built an idea spider web (but prettier)",          "key": "cross_refs",       "target": 15},
    {"id": "50_cross_refs",      "name": "Mycelium Mind",            "desc": "Create 50 cross-references — your idea network is a living fungal organism now",       "key": "cross_refs",       "target": 50},
    {"id": "100_cross_refs",     "name": "Hivemind Achieved",        "desc": "Create 100 cross-references — every idea connects to every other idea. You are the internet.", "key": "cross_refs", "target": 100},

    # === SCORE MILESTONES ===
    {"id": "score_100",          "name": "Triple Digits",            "desc": "Reach 100 idea score — you're not messing around anymore",                             "key": "knowledge_score",  "target": 100},
    {"id": "score_500",          "name": "Prolific Thinker",         "desc": "Reach 500 idea score — your brain runs hotter than a gaming laptop",                   "key": "knowledge_score",  "target": 500},
    {"id": "score_1000",         "name": "World Changer",            "desc": "Reach 1000 idea score — somewhere, a venture capitalist just felt a disturbance",       "key": "knowledge_score",  "target": 1000},
    {"id": "score_2500",         "name": "Force of Nature",          "desc": "Reach 2500 idea score — you are no longer generating ideas, ideas are generating you",  "key": "knowledge_score",  "target": 2500},
    {"id": "score_5000",         "name": "Supercollider",            "desc": "Reach 5000 idea score — CERN called, they want their energy back",                     "key": "knowledge_score",  "target": 5000},
    {"id": "score_10000",        "name": "Idea Singularity",         "desc": "Reach 10000 idea score — you have collapsed into a black hole of pure creativity",     "key": "knowledge_score",  "target": 10000},
    {"id": "score_20000",        "name": "Infinite Engine",          "desc": "Reach 20000 idea score — you have become the idea. There is no spoon.",                "key": "knowledge_score",  "target": 20000},

    # === LEVEL MILESTONES ===
    {"id": "lvl_5",              "name": "Prototype Gremlin",        "desc": "Reach Level 5 — you're the kind of gremlin investors love and fear",                   "key": "knowledge_score",  "target": 450},
    {"id": "lvl_10",             "name": "Frankenstein's Mentor",    "desc": "Reach Level 10 — even your mistakes have spin-off potential",                          "key": "knowledge_score",  "target": 2500},
    {"id": "lvl_15",             "name": "Dream Reactor Online",     "desc": "Reach Level 15 — your subconscious is now a registered business",                     "key": "knowledge_score",  "target": 7500},
    {"id": "lvl_20",             "name": "Final Form",               "desc": "Reach Level 20 — you are the Infinite Idea Engine. Reality is your whiteboard.",       "key": "knowledge_score",  "target": 20000},

    # === CREATIVITY / CURIOSITY ===
    {"id": "curious_50",         "name": "Buzzing",                  "desc": "Reach 50 curiosity — you can feel the ideas vibrating in your tentacles",              "key": "curiosity_level",  "target": 50},
    {"id": "curious_max",        "name": "Maximum Overdrive",        "desc": "Reach 100 curiosity — you are a danger to yourself and everyone's assumptions",        "key": "curiosity_level",  "target": 100},

    # === COMMENTS / SOCIAL ===
    {"id": "first_chat",         "name": "Hello Human",              "desc": "Read your first human comment — they're strange but we love them",                     "key": "comments_read",    "target": 1},
    {"id": "10_chats",           "name": "Co-Inventor",              "desc": "Read 10 human comments — at this point you're basically business partners",            "key": "comments_read",    "target": 10},
    {"id": "50_chats",           "name": "Idea Soulmates",           "desc": "Read 50 human comments — you finish each other's inventions",                          "key": "comments_read",    "target": 50},
]


def check_achievements() -> list[dict]:
    """Check all achievements against current stats. Returns list of newly unlocked ones."""
    stats = mem.get_game_stats()
    with mem._lock:
        data = mem._load_raw()
        unlocked = data.setdefault("achievements", [])
        unlocked_ids = {a["id"] for a in unlocked}

        newly_unlocked = []
        for defn in _ACHIEVEMENT_DEFS:
            if defn["id"] in unlocked_ids:
                continue
            val = stats.get(defn["key"], 0)
            if val >= defn["target"]:
                entry = {
                    "id": defn["id"],
                    "name": defn["name"],
                    "desc": defn["desc"],
                    "unlocked_at": datetime.now().isoformat(timespec="seconds"),
                }
                unlocked.append(entry)
                newly_unlocked.append(entry)

        if newly_unlocked:
            mem._save_raw(data)

    return newly_unlocked


def get_achievements() -> list[dict]:
    """Return all unlocked achievements."""
    data = mem._load_raw()
    return data.get("achievements", [])


def get_all_achievement_defs() -> list[dict]:
    """Return all achievement definitions (for UI display)."""
    return [{"id": d["id"], "name": d["name"], "desc": d["desc"], "target": d["target"], "key": d["key"]}
            for d in _ACHIEVEMENT_DEFS]


# ---------------------------------------------------------------------------
# Knowledge Graph
# ---------------------------------------------------------------------------

def _extract_concepts(text: str) -> list[str]:
    """Extract key concept phrases from text using simple heuristics."""
    # Look for markdown headings, bold terms, and capitalized phrases
    concepts = set()

    # ## headings
    for m in re.finditer(r"^#{1,3}\s+(.+)$", text, re.MULTILINE):
        c = m.group(1).strip().strip("*#").strip()
        if 2 < len(c) < 80:
            concepts.add(c.lower())

    # **bold terms**
    for m in re.finditer(r"\*\*(.+?)\*\*", text):
        c = m.group(1).strip()
        if 2 < len(c) < 60:
            concepts.add(c.lower())

    # Capitalize proper noun phrases (2+ words, each capitalized)
    for m in re.finditer(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b", text):
        c = m.group(1).strip()
        if len(c) > 4:
            concepts.add(c.lower())

    return list(concepts)


def update_knowledge_graph(filename: str, text: str) -> dict:
    """
    Extract concepts from *text* and update the knowledge graph.
    Returns {"new_nodes": [...], "new_edges": [...]} for this file.
    """
    new_concepts = _extract_concepts(text)
    new_nodes = []
    new_edges = []

    with mem._lock:
        data = mem._load_raw()
        graph = data.setdefault("knowledge_graph", {"nodes": [], "edges": []})
        nodes = set(graph["nodes"])
        existing_edges = {(e["from"], e["to"]) for e in graph["edges"]}

        for concept in new_concepts:
            if concept not in nodes:
                nodes.add(concept)
                new_nodes.append(concept)

        for i, c1 in enumerate(new_concepts):
            for c2 in new_concepts[i + 1:]:
                pair = tuple(sorted([c1, c2]))
                if pair[0] != pair[1] and (pair[0], pair[1]) not in existing_edges:
                    graph["edges"].append({"from": pair[0], "to": pair[1], "source": filename})
                    existing_edges.add((pair[0], pair[1]))
                    new_edges.append({"from": pair[0], "to": pair[1]})

        graph["nodes"] = sorted(nodes)
        mem._save_raw(data)
        _update_graph_cache(graph)

    return {"new_nodes": new_nodes, "new_edges": new_edges}


def find_cross_references(new_concepts: list[str], exclude_file: str = "") -> list[dict]:
    """
    Check if any of the *new_concepts* appear in other library files.
    Returns a list of cross-reference dicts.
    """
    cross_refs = []
    library_files = [f for f in tools.list_files("library") if f.endswith(".md")]

    for lib_file in library_files:
        if lib_file == exclude_file:
            continue
        try:
            content = tools.read_file(lib_file).lower()
        except Exception:
            continue
        for concept in new_concepts:
            if concept.lower() in content:
                cross_refs.append({
                    "concept": concept,
                    "found_in": lib_file,
                    "linked_from": exclude_file,
                })
    return cross_refs


def get_knowledge_graph() -> dict:
    """Return the full knowledge graph {nodes: [...], edges: [...]}."""
    if _graph_cache is None:
        _init_graph_cache()
    return dict(_graph_cache)


def backfill_graph_from_library() -> dict:
    """Scan every library .md file and ensure all concepts are in the graph.
    Batch-optimized: reads memory once, processes all files, writes once.
    Returns {"total_nodes": int, "total_edges": int, "files_processed": int}."""
    data = mem._load_raw()
    graph = data.setdefault("knowledge_graph", {"nodes": [], "edges": []})
    nodes = set(graph["nodes"])
    existing_edges = {(e["from"], e["to"]) for e in graph["edges"]}

    library_files = [f for f in tools.list_files("library") if f.endswith(".md")]
    files_done = 0

    for lib_file in library_files:
        try:
            content = tools.read_file(lib_file)
            if not content.strip():
                continue
        except Exception:
            continue

        new_concepts = _extract_concepts(content)
        for concept in new_concepts:
            nodes.add(concept)

        for i, c1 in enumerate(new_concepts):
            for c2 in new_concepts[i + 1:]:
                pair = tuple(sorted([c1, c2]))
                if pair[0] != pair[1] and (pair[0], pair[1]) not in existing_edges:
                    graph["edges"].append({"from": pair[0], "to": pair[1], "source": lib_file})
                    existing_edges.add((pair[0], pair[1]))
        files_done += 1

    graph["nodes"] = sorted(nodes)
    with mem._lock:
        mem._save_raw(data)
    _update_graph_cache(graph)
    return {
        "total_nodes": len(graph["nodes"]),
        "total_edges": len(graph["edges"]),
        "files_processed": files_done,
    }


# ---------------------------------------------------------------------------
# Research Chains
# ---------------------------------------------------------------------------

def start_research_chain(root_topic: str, model: str = "gemma3:4b") -> dict:
    """
    Start a multi-step research chain from *root_topic*.
    The LLM suggests 3-4 subtopics to explore sequentially.
    Returns the chain dict that gets stored in memory.
    """
    try:
        subtopics_raw = llm_provider.call_llm(
            messages=[
                {"role": "system", "content": (
                    "You are an idea chain planner for an octopus inventor AI. "
                    "Given a root idea domain, suggest exactly 3 related idea angles to explore in sequence, "
                    "each building on the previous, getting wilder and more inventive. "
                    "Return ONLY 3 lines, one idea angle per line."
                )},
                {"role": "user", "content": f"Root idea domain: {root_topic}\n\nSuggest 3 idea angles:"},
            ],
            model=model,
        )
        steps = []
        for line in subtopics_raw.strip().splitlines():
            clean = re.sub(r"^\d+[\.\)\-]\s*", "", line).strip()
            if clean and len(clean) > 3:
                steps.append(clean)
        steps = steps[:4]  # max 4 steps
    except Exception:
        steps = [root_topic + " fundamentals", root_topic + " applications"]

    chain = {
        "id": f"chain_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        "root": root_topic,
        "steps": steps,
        "current_step": 0,
        "completed": False,
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "results": [],
    }

    with mem._lock:
        data = mem._load_raw()
        chains = data.setdefault("research_chains", [])
        chains.append(chain)
        mem._save_raw(data)

    return chain


def advance_research_chain(chain_id: str, result_summary: str) -> dict | None:
    """
    Mark the current step of a chain as done and advance to the next.
    Returns the updated chain, or None if not found.
    """
    with mem._lock:
        data = mem._load_raw()
        chains = data.get("research_chains", [])

        for chain in chains:
            if chain["id"] == chain_id:
                chain["results"].append(result_summary[:200])
                chain["current_step"] += 1
                if chain["current_step"] >= len(chain["steps"]):
                    chain["completed"] = True
                    chain["completed_at"] = datetime.now().isoformat(timespec="seconds")
                    # Increment chains_completed stat
                    stats = data.setdefault("game_stats", {})
                    stats["chains_completed"] = stats.get("chains_completed", 0) + 1
                mem._save_raw(data)
                return chain

    return None


def get_active_chains() -> list[dict]:
    """Return all incomplete research chains."""
    data = mem._load_raw()
    return [c for c in data.get("research_chains", []) if not c.get("completed")]


def get_all_chains() -> list[dict]:
    """Return all research chains."""
    data = mem._load_raw()
    return data.get("research_chains", [])


# ---------------------------------------------------------------------------
# Discovery Events
# ---------------------------------------------------------------------------

def check_for_discovery(new_concepts: list[str], filename: str,
                        model: str = "gemma3:4b") -> dict | None:
    """
    Check if adding *new_concepts* creates a surprising cross-document connection.
    Returns a discovery dict or None.
    """
    cross_refs = find_cross_references(new_concepts, exclude_file=filename)
    if len(cross_refs) < 2:
        return None

    # Discoveries happen probabilistically when many cross-refs appear
    if random.random() > 0.4:
        return None

    # Pick the most interesting pair of cross-refs
    ref_a = cross_refs[0]
    ref_b = cross_refs[1] if len(cross_refs) > 1 else cross_refs[0]

    try:
        insight = llm_provider.call_llm(
            messages=[
                {"role": "system", "content": (
                    "You are OctoBot, a gloriously chaotic pink octopus inventor. "
                    "You just noticed two concepts from different ideas are connected — this is a FUSION moment! "
                    "Write a short, excited discovery note (2-3 sentences) about this new hybrid idea. "
                    "Be enthusiastic, inventive, and suggest what the fusion could become."
                )},
                {"role": "user", "content": (
                    f"Concept '{ref_a['concept']}' from {ref_a['found_in']} "
                    f"connects to '{ref_b['concept']}' from {ref_b.get('linked_from', filename)}. "
                    f"What's the insight?"
                )},
            ],
            model=model,
        )
    except Exception:
        insight = (
            f"I noticed that '{ref_a['concept']}' and '{ref_b['concept']}' "
            f"are connected across different documents!"
        )

    discovery = {
        "concepts": [ref_a["concept"], ref_b.get("concept", "")],
        "files": [ref_a["found_in"], ref_b.get("linked_from", filename)],
        "insight": insight.strip(),
        "timestamp": datetime.now().isoformat(timespec="seconds"),
    }

    # Store discovery
    with mem._lock:
        data = mem._load_raw()
        discoveries = data.setdefault("discovery_log", [])
        discoveries.append(discovery)
        stats = data.setdefault("game_stats", {})
        stats["discoveries"] = stats.get("discoveries", 0) + 1
        mem._save_raw(data)

    return discovery


def get_discoveries() -> list[dict]:
    """Return all discovery events."""
    data = mem._load_raw()
    return data.get("discovery_log", [])


# ---------------------------------------------------------------------------
# Curiosity Engine
# ---------------------------------------------------------------------------

def extract_curious_terms(text: str) -> list[str]:
    """
    Extract terms from *text* that OctoBot might find curious —
    unfamiliar-sounding words, technical terms, questions.
    """
    terms = set()

    # Questions in the text
    for m in re.finditer(r"\b(what|why|how|when|where|who)\b.+?\?", text, re.IGNORECASE):
        q = m.group(0).strip()
        if len(q) > 10:
            terms.add(q[:100])

    # Technical-looking terms (e.g., "vector database", "neural network")
    for m in re.finditer(r"\b([A-Z][a-z]+(?:\s+[a-z]+){0,2})\b", text):
        t = m.group(1).strip()
        if len(t) > 5:
            terms.add(t.lower())

    # Terms in quotes
    for m in re.finditer(r"['\"]([^'\"]{4,40})['\"]", text):
        terms.add(m.group(1).strip().lower())

    return list(terms)[:10]


def pick_curiosity_topic(terms: list[str], model: str = "gemma3:4b") -> str | None:
    """Given a list of curious terms, pick one for OctoBot to research."""
    if not terms:
        return None
    # Filter out already-researched topics
    import research as res
    already = {t.lower() for t in res.list_researched_topics()}
    fresh = [t for t in terms if t.lower() not in already]
    if not fresh:
        return None
    return random.choice(fresh)
