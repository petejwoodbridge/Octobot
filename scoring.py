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

# In-memory graph cache — avoids re-reading memory.json on every API call
# New format: {"nodes": [...], "file_concepts": {filename: [concepts]}}
# Edges are computed on-the-fly from shared concepts between files.
_graph_cache: dict | None = None

def _init_graph_cache():
    """Initialize an empty graph cache. The actual data is populated
    by backfill_graph_from_library() called from main.py at startup."""
    global _graph_cache
    if _graph_cache is None:
        _graph_cache = {"nodes": [], "file_concepts": {}}

def _update_graph_cache(graph: dict):
    """Update the in-memory graph cache after a write."""
    global _graph_cache
    _graph_cache = graph

def _derive_edges_from_cache() -> list[dict]:
    """Compute edges on-the-fly from the file_concepts index."""
    if not _graph_cache:
        return []
    fc = _graph_cache.get("file_concepts", {})
    edges = []
    for filename, concepts in fc.items():
        for i, c1 in enumerate(concepts):
            for c2 in concepts[i+1:]:
                pair = tuple(sorted([c1, c2]))
                edges.append({"from": pair[0], "to": pair[1], "source": filename})
    return edges

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
# Calibrated for ~60 hours of gameplay at the typical scoring pace.
# Levels 1-20  : 0   → 20,000  (~12 hrs)   early & mid game
# Levels 21-35 : 20,000 → 57,000  (~19 hrs)   late-mid game   [gaps ~2,500]
# Levels 36-50 : 57,000 → 110,000 (~29 hrs)   endgame         [gaps ~3,500]
# ---------------------------------------------------------------------------
LIBRARY_LEVELS = [
    # ── Early game (1–10) ──────────────────────────────────────────────────
    (0,       "Napkin Sketcher",                     1),
    (50,      "Shower Thinker",                      2),
    (120,     "Garage Tinkerer",                     3),
    (250,     "Caffeinated Dreamer",                 4),
    (450,     "Prototype Gremlin",                   5),
    (700,     "Mad Scientist",                       6),
    (1000,    "Patent Pending",                      7),
    (1400,    "Chaos Engineer",                      8),
    (1900,    "Moonshot Architect",                  9),
    (2500,    "Frankenstein's Mentor",               10),
    # ── Mid game (11–20) ─────────────────────────────────────────────────
    (3200,    "Interdimensional Tinkerer",           11),
    (4000,    "Perpetual Motion Machine",            12),
    (5000,    "Idea Supercollider",                  13),
    (6200,    "Rogue Inventor General",              14),
    (7500,    "Dream Reactor",                       15),
    (9000,    "Octopus Prime",                       16),
    (11000,   "Reality Bender",                      17),
    (13500,   "Singularity Whisperer",               18),
    (16500,   "God of Small Things",                 19),
    (20000,   "Infinite Idea Engine",                20),
    # ── Late-mid game (21–35) — gaps ~2,500 ────────────────────────────
    (22000,   "Temporal Patent Troll",               21),
    (24500,   "Chaos Theory Barista",                22),
    (27000,   "Professor of Impractical Solutions",  23),
    (29500,   "Reverse Engineer of the Soul",        24),
    (32000,   "Unsolicited Visionary",               25),
    (34500,   "Eight-Armed Architect",               26),
    (37000,   "Reality's Most Wanted",               27),
    (39500,   "Sentient Whiteboard",                 28),
    (42000,   "Wizard of Unnecessary Things",        29),
    (44500,   "Quantum Daydreamer",                  30),
    (47000,   "Accidental Paradigm Shift",           31),
    (49500,   "Self-Aware Hypothesis",               32),
    (52000,   "The Unpatentable",                    33),
    (54500,   "Bureau of Impossible Standards",      34),
    (57000,   "Feral Futurist",                      35),
    # ── Endgame (36–50) — gaps ~3,500 ─────────────────────────────────
    (60500,   "Architect of Magnificent Nonsense",   36),
    (64000,   "Chronic Eureka Syndrome",             37),
    (67500,   "Pantheon of Peculiar Inventions",     38),
    (71000,   "Unsanctioned Oracle",                 39),
    (74500,   "The Universe's Most Chaotic Asset",   40),
    (78000,   "Cosmic Patent Thief",                 41),
    (81500,   "The Unstoppable Hypothesis",          42),
    (85000,   "Invention Incarnate",                 43),
    (88500,   "OctoGod of the Ideaverse",            44),
    (92000,   "Dimension-Hopping Prototype",         45),
    (95500,   "The Last Known Inventor",             46),
    (99000,   "Transcendent Patent Overlord",        47),
    (102500,  "Primordial Inventor",                 48),
    (106000,  "The Idea Before Ideas",               49),
    (110000,  "Genesis Engine",                      50),
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
    {"id": "lvl_5",  "name": "Prototype Gremlin",                   "desc": "Reach Level 5 — you're the kind of gremlin investors love and fear",                                          "key": "knowledge_score", "target": 450},
    {"id": "lvl_10", "name": "Frankenstein's Mentor",               "desc": "Reach Level 10 — even your mistakes have spin-off potential",                                              "key": "knowledge_score", "target": 2500},
    {"id": "lvl_15", "name": "Dream Reactor Online",               "desc": "Reach Level 15 — your subconscious is now a registered business",                                           "key": "knowledge_score", "target": 7500},
    {"id": "lvl_20", "name": "Infinite Idea Engine",               "desc": "Reach Level 20 — Reality is your whiteboard. You are unstoppable. (For now.)",                             "key": "knowledge_score", "target": 20000},
    {"id": "lvl_25", "name": "Unsolicited Visionary",              "desc": "Reach Level 25 — nobody asked for these ideas, but somehow everyone needed them",                           "key": "knowledge_score", "target": 32000},
    {"id": "lvl_30", "name": "Quantum Daydreamer",                 "desc": "Reach Level 30 — simultaneously solving problems that don't exist yet in six dimensions",                  "key": "knowledge_score", "target": 44500},
    {"id": "lvl_35", "name": "Feral Futurist",                     "desc": "Reach Level 35 — untamed, uncertified, and absolutely unstoppable",                                        "key": "knowledge_score", "target": 57000},
    {"id": "lvl_40", "name": "The Universe's Most Chaotic Asset",  "desc": "Reach Level 40 — even entropy takes notes. You are the universe's most valuable liability.",             "key": "knowledge_score", "target": 74500},
    {"id": "lvl_45", "name": "Dimension-Hopping Prototype",        "desc": "Reach Level 45 — you exist in seventeen conceptual dimensions simultaneously",                           "key": "knowledge_score", "target": 92000},
    {"id": "lvl_50", "name": "Genesis Engine",                     "desc": "Reach Level 50 — you are the source. The original spark. The reason ideas exist at all. You win.",       "key": "knowledge_score", "target": 110000},

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

_GENERIC_TERMS = {
    # Section headings
    "overview", "the idea", "the problem it solves", "how it works",
    "why it's brilliant", "why it\u2019s brilliant", "elevator pitch",
    "related ideas", "update", "the problem", "the solution",
    "created by octobot", "key concepts", "summary", "details",
    "introduction", "conclusion", "notes", "references",
    "key features", "potential applications", "original notes",
    # Partial heading artifacts
    "pitch:", "how it works:", "the problem it solves:", "why it's brilliant:",
    "why it\u2019s brilliant:", "the idea:", "the problem it solves the",
    "how it works the", "brilliant the", "why it",
}

# Regex for strings that are clearly not concept names
_JUNK_PATTERN = re.compile(
    r"^(the |a |an |this |that |it |why |how |what |when |where |who )"
    r".{0,5}$"  # very short phrases starting with filler words
)


def _clean_concept(c: str) -> str | None:
    """Sanitize and validate a concept string. Returns None if invalid."""
    # Strip whitespace, markdown artifacts, quotes
    c = c.strip().strip("*#\"'\u201c\u201d:").strip()
    # Remove newlines — concepts must be single-line
    c = c.replace("\n", " ").replace("\r", "")
    # Collapse multiple spaces
    c = re.sub(r"\s+", " ", c).strip().lower()
    # Strip trailing colons/punctuation
    c = c.rstrip(":;,.")
    # Reject if contains commas, periods, colons, or semicolons (sentence fragments)
    if "," in c or "." in c or ":" in c or ";" in c:
        return None
    # Reject markdown artifacts
    if c.startswith("---") or c.startswith("concept "):
        return None
    # Reject concepts starting with articles (fragments like "a-chip devices")
    if re.match(r"^(a |an |the |but |yet |nor )", c):
        return None
    # Reject if too short, too long, or generic
    if len(c) < 4 or len(c) > 60:
        return None
    if c in _GENERIC_TERMS:
        return None
    # Reject partial heading artifacts (contain "the problem", "how it works", etc.)
    for generic in ("the problem it solves", "how it works", "why it", "elevator pitch",
                     "key features", "potential applications", "original notes"):
        if c.startswith(generic) or c == generic:
            return None
    # Reject concepts that are just markdown formatting artifacts
    if c.startswith(("created by", "updated by", "reformatted", "expanded by")):
        return None
    # Reject if it's just a common English word/phrase with no specificity
    if _JUNK_PATTERN.match(c):
        return None
    # Reject ALL single words (no spaces, no hyphens) — concepts should be phrases
    if " " not in c and "-" not in c:
        return None
    # For hyphenated-only terms (no spaces), require both parts to be 3+ chars
    if " " not in c and "-" in c:
        parts = c.split("-")
        if any(len(p) < 3 for p in parts):
            return None
    # Legacy single-word filter (kept for hyphenated combos that include these)
    _single_check = c.replace("-", " ").split()
    if len(_single_check) == 1 and len(c) < 7:
        return None  # Too short for a meaningful concept
        _COMMON_SINGLE_WORDS = {
            "feeling", "feel", "feels", "real", "time", "data", "system", "device",
            "user", "users", "idea", "concept", "design", "project", "pitch",
            "technology", "application", "solution", "problem", "feature",
            "before", "after", "directly", "actively", "what", "brilliant",
            "imagine", "think", "using", "simply", "truly", "actually",
            "within", "exactly", "source", "perception", "doesn\u2019t",
            "doesn't", "really", "experience", "allows", "creates",
            "extremely", "incredibly", "essentially", "completely",
            "naturally", "already", "specific", "unique", "entire",
            "monitor", "analyze", "generate", "measure", "detect",
            "adjust", "respond", "process", "create", "provide",
            "reading", "tracking", "learning", "growing", "living",
            "imagine", "imagine", "describe", "between", "through",
            "because", "however", "without", "another", "several",
            "current", "different", "important", "approach", "various",
            "potential", "possible", "existing", "recently", "becoming",
            "material", "materials", "surface", "surfaces", "control",
            "controlled", "environment", "physical", "digital", "network",
            "patterns", "pattern", "similar", "changes", "change",
            "contains", "contain", "surrounding", "precisely", "utilizing",
            "cultivating", "genetically", "modified", "colonies", "devices",
            "translating", "stimulating", "attracting", "addresses",
            "consists", "delivers", "provides", "response", "becomes",
            "invisible", "contained", "converts", "movement", "movement",
            "approximately", "researchers", "personnel", "furthermore",
            "integrated", "crucially", "mimicking", "distribution",
            "spectrum", "algorithms", "influence", "constantly",
            "bacterial", "inspiring", "massive", "educates", "intuitive",
            "predictive", "reconstructs", "combining", "considers",
            "captures", "connects", "explores", "enhances", "enables",
            "optimizes", "generates", "imagine", "prepare", "combine",
            "requires", "operates", "supports", "maintains", "measures",
            "produces", "receives", "releases", "responds", "searches",
            "suggests", "triggers", "vibrates", "utilizes", "combines",
            "invented", "designed", "features", "includes", "involves",
            "integrates", "describes", "combined", "inspired", "invented",
            "developed", "brilliant", "challenge", "innovation", "consider",
            "problems", "solution", "something", "products", "services",
            "interest", "technique", "possible", "platform", "standard",
            "proposed", "presence", "discover", "function",
        }
        if c in _COMMON_SINGLE_WORDS:
            return None
    # Reject hyphenated common adjectives/phrases that aren't technical concepts
    _COMMON_HYPHENATED = {
        "self-contained", "pre-programmed", "custom-designed", "real-time to",
        "well-being", "built-in", "long-term", "short-term", "high-quality",
        "low-cost", "full-body", "non-invasive", "self-sustaining",
        "hand-held", "self-aware", "battery-powered", "solar-powered",
        "head-on", "real-time", "palm-sized", "wrist-worn",
        "real-time visual", "real-time data",
    }
    if c in _COMMON_HYPHENATED:
        return None
    # Reject fragments with "the" that aren't proper names
    if c.startswith("the ") and len(c.split()) <= 2:
        return None
    if "brilliant " in c:
        return None
    # Reject concepts ending with conjunctions/prepositions (broken extractions)
    if c.endswith((" and", " or", " the", " a", " an", " to", " of", " in", " on", " for", " with", " is", " it")):
        return None
    # Reject concepts starting with common verbs/articles/prepositions (sentence fragments)
    _FRAG_STARTS = (
        "become ", "becomes ", "convert ", "approach ", "consist ", "consists ",
        "address ", "addresses ", "deliver ", "delivers ", "provide ", "provides ",
        "design ", "between ", "containing ", "almost ", "layer ",
    )
    if c.startswith(_FRAG_STARTS):
        return None
    # Reject concepts ending with verbs/filler (sentence fragments from bold/heading extraction)
    _FRAG_ENDS = (
        " then", " isn't", " isn\u2019t", " doesn't", " doesn\u2019t",
        " offers", " ensures", " generates", " eliminates",
        " consists", " unlocks", " analyzes", " activates",
        " shared", " within", " directly", " instantly",
    )
    if any(c.endswith(e) for e in _FRAG_ENDS):
        return None
    # Reject concepts containing smart quotes or special unicode
    if "\u2019" in c or "\u201c" in c or "\u201d" in c or "\u2014" in c or "\ufffd" in c:
        return None
    # Reject concepts starting with "overview", "idea domain", "this ", "the "
    if c.startswith(("overview ", "idea domain", "this ", "related ")):
        return None
    # Reject concepts that are just a hyphenated prefix + junk word
    if re.match(r"^[a-z]+-[a-z]+\s+(isn|doesn|won|can|woven|filled|containing|fluid|core|micro|stuff|feed|battle)$", c):
        return None
    # Reject purely temporal/generic hyphenated terms
    _GENERIC_HYPH = {
        "mid-afternoon", "mid-morning", "mid-range", "mid-century",
        "long-lasting", "short-term boost", "self-conscious battle",
        "pain-free", "ultra-low", "one-of-a-kind",
    }
    if c in _GENERIC_HYPH:
        return None
    # Reject generic 2-word phrases where both words are very common
    words = c.split()
    if len(words) == 2 and "-" not in c:
        _GENERIC_WORDS_2 = {
            "system", "control", "based", "level", "effect", "within",
            "using", "allows", "creates", "broadly", "roughly",
            "constant", "subtle", "broader", "truly", "seamless",
            "unparalleled", "think", "focused", "arm", "color",
            "surrounding", "light", "contained", "100", "microns",
        }
        if words[0] in _GENERIC_WORDS_2 or words[1] in _GENERIC_WORDS_2:
            return None
    return c


def _extract_concepts(text: str) -> list[str]:
    """Extract key concept phrases from text using simple heuristics."""
    raw_concepts = set()

    # ## headings (skip generic section headings)
    for m in re.finditer(r"^#{1,3}\s+(.+)$", text, re.MULTILINE):
        c = _clean_concept(m.group(1))
        if c:
            raw_concepts.add(c)

    # **bold terms**
    for m in re.finditer(r"\*\*(.+?)\*\*", text):
        c = _clean_concept(m.group(1))
        if c:
            raw_concepts.add(c)

    # Capitalized proper noun phrases (2+ words, each capitalized)
    for m in re.finditer(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b", text):
        c = _clean_concept(m.group(1))
        if c:
            raw_concepts.add(c)

    # Technical compound terms (e.g., "bio-acoustic", "micro-fluidic")
    for m in re.finditer(r"\b([a-z]+-[a-z]+(?:\s+[a-z]+)?)\b", text, re.IGNORECASE):
        c = _clean_concept(m.group(1))
        if c:
            raw_concepts.add(c)

    # Terms in *italics* that look like names (not too short, not a sentence)
    for m in re.finditer(r"(?<!\*)\*([^*\n]{4,40})\*(?!\*)", text):
        c = _clean_concept(m.group(1))
        if c:
            raw_concepts.add(c)

    return list(raw_concepts)


_MAX_CONCEPTS_PER_FILE = 15  # Cap to prevent edge explosion (n^2 edges)


def update_knowledge_graph(filename: str, text: str) -> dict:
    """
    Extract concepts from *text* and update the in-memory knowledge graph.
    The graph is NOT persisted to disk — it's rebuilt from library files on startup.
    Returns {"new_nodes": [...], "new_edges": [...]} for this file.
    """
    global _graph_cache
    new_concepts = _extract_concepts(text)[:_MAX_CONCEPTS_PER_FILE]
    new_nodes = []

    if _graph_cache is None:
        _graph_cache = {"nodes": [], "file_concepts": {}}

    nodes = set(_graph_cache.get("nodes", []))
    for concept in new_concepts:
        if concept not in nodes:
            nodes.add(concept)
            new_nodes.append(concept)

    _graph_cache["nodes"] = sorted(nodes)
    _graph_cache.setdefault("file_concepts", {})[filename] = new_concepts

    return {"new_nodes": new_nodes, "new_edges": []}


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
    """Return the knowledge graph in {nodes: [...], edges: [...]} format.
    Edges are derived on-the-fly from the file_concepts index."""
    if _graph_cache is None:
        _init_graph_cache()
    return {
        "nodes": _graph_cache.get("nodes", []),
        "edges": _derive_edges_from_cache(),
    }


def backfill_graph_from_library(clean: bool = False) -> dict:
    """Scan every library .md file and build the in-memory knowledge graph.
    If clean=True, wipe the existing graph first and rebuild from scratch.
    The graph is NOT persisted to disk — it's purely in-memory.
    Returns {"total_nodes": int, "total_files": int, "files_processed": int}."""
    global _graph_cache

    if clean or _graph_cache is None:
        _graph_cache = {"nodes": [], "file_concepts": {}}

    nodes = set(_graph_cache.get("nodes", []))
    file_concepts = _graph_cache.get("file_concepts", {})

    library_files = [f for f in tools.list_files("library") if f.endswith(".md")]
    files_done = 0

    for lib_file in library_files:
        try:
            content = tools.read_file(lib_file)
            if not content.strip():
                continue
        except Exception:
            continue

        new_concepts = _extract_concepts(content)[:_MAX_CONCEPTS_PER_FILE]
        for concept in new_concepts:
            nodes.add(concept)
        file_concepts[lib_file] = new_concepts
        files_done += 1

    _graph_cache["nodes"] = sorted(nodes)
    _graph_cache["file_concepts"] = file_concepts
    return {
        "total_nodes": len(_graph_cache["nodes"]),
        "total_files": len(file_concepts),
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
