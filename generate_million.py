"""
generate_million.py — Generate 1,000,000 ideas for OctoBot
=============================================================
Writes directly to sharded directories for maximum throughput.
Files are written to workspace/library/batch_XXXX/ (1000 files per batch).

The knowledge graph rebuilds from library files at startup via
backfill_graph_from_library() which now samples up to 5000 files,
so 1M files won't slow down the graph build.

Usage:  python generate_million.py [count]    (default: 1000000)
"""

import os
import sys
import random
import hashlib
import time
from pathlib import Path
from datetime import datetime

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

WORKSPACE = Path(__file__).parent / "workspace"
LIBRARY = WORKSPACE / "library"

# ---------------------------------------------------------------------------
# All vocabulary banks (same as generate_bulk.py, massively expanded)
# ---------------------------------------------------------------------------

LIFE_FORCES = [
    "Awen", "Teotl", "Qi", "Prana", "Mana", "Pneuma", "Sunyata", "Mauri",
    "Tapu", "Logos", "Lung", "Tigle", "Chakra", "Songlines", "Everywhen",
    "Dreamtime", "Alcheringa", "Jukurrpa", "Nadi", "Meridian", "Kundalini",
    "Shakti", "Ruach", "Ka", "Ba", "Ankh", "Baraka", "Orenda", "Wakan",
    "Manitou", "Ase", "Nyama", "Heka", "Sekhem", "Vril", "Od", "Orgone",
    "Elan Vital", "Entelechy", "Anima Mundi",
]

PHILOSOPHICAL_CONCEPTS = [
    "agonistic inamic unity", "constitutional monism", "dependent origination",
    "non-dual awareness", "sacred breath", "divine illumination",
    "cosmic consciousness", "tensility of being", "subtle body architecture",
    "shamanic transformation", "poetic frenzy", "karmic momentum",
    "ecological stewardship", "enchanted cosmos", "flowing spirit",
    "primordial energy", "vital life force", "spiritual resonance",
    "ontological indeterminacy", "relational authority", "radical interconnectedness",
    "process metaphysics", "participatory epistemology", "animistic reciprocity",
    "phenomenological embodiment", "liminal threshold crossing", "emergent complexity",
    "rhizomatic knowledge", "sympoietic becoming", "autopoietic self-creation",
    "deep ecological entanglement", "quantum coherence of mind", "morphic resonance",
    "collective unconscious", "archetypal emergence", "dialectical synthesis",
    "hermeneutic circularity", "somatic intelligence", "proprioceptive awareness",
    "interoceptive wisdom", "apophatic knowing", "cosmological reciprocity",
    "animistic kinship", "sacred ecology", "biophilic resonance",
    "techno-shamanism", "digital animism", "algorithmic divination",
    "cybernetic ecology", "post-human empathy", "trans-species communication",
]

TECH_DOMAINS = [
    "bio-acoustic", "neuro-sensory", "micro-fluidic", "chrono-spatial",
    "geo-resonant", "bioluminescent", "haptic-feedback", "electro-dermal",
    "magneto-therapeutic", "sono-luminescent", "thermo-adaptive",
    "piezo-electric", "opto-genetic", "myco-electric", "quantum-entangled",
    "nano-fibrous", "cryo-kinetic", "hydro-dynamic", "aero-elastic",
    "ferro-fluid", "plasma-ionic", "photo-catalytic", "bio-mimetic",
    "neuro-plastic", "psycho-acoustic", "mechano-transductive",
    "chemo-luminescent", "radio-isotopic", "gyro-stabilized", "bio-photonic",
    "electro-rheological", "magneto-caloric", "tribo-electric",
    "sono-chemical", "photo-thermal", "electro-chromic", "thermo-electric",
    "piezo-resistive", "magneto-strictive", "opto-mechanical",
    "bio-galvanic", "neuro-morphic", "chemo-tactic", "photo-acoustic",
    "electro-osmotic", "magneto-hydrodynamic", "thermo-chromic",
    "sono-phoretic", "electro-kinetic", "bio-electrochemical",
    "nano-photonic", "quantum-acoustic", "cryo-electronic", "plasma-catalytic",
    "ferro-electric", "magneto-optical", "bio-tribological", "neuro-chemical",
    "sono-genetic", "photo-electrochemical", "electro-spun", "bio-fermentative",
    "geo-thermal", "hydro-acoustic", "aero-acoustic", "cryo-preservative",
    "nano-mechanical", "quantum-magnetic", "plasma-acoustic", "bio-polymeric",
    "electro-luminescent", "magneto-plasmonic", "opto-fluidic", "thermo-plasmonic",
    "bio-piezoelectric", "neuro-fluidic", "chemo-mechanical", "photo-magnetic",
    "sono-thermal", "electro-catalytic", "magneto-acoustic", "bio-optical",
    "nano-acoustic", "quantum-optical", "cryo-magnetic", "plasma-thermal",
    "ferro-acoustic", "opto-thermal", "bio-magnetic", "neuro-optical",
]

PROBLEM_DOMAINS = [
    "loneliness in cities", "creative block", "decision fatigue",
    "sleep disruption", "information overload", "emotional numbness",
    "chronic procrastination", "social anxiety", "grief processing",
    "memory preservation", "skill acquisition", "habit formation",
    "environmental awareness", "conflict resolution", "pain management",
    "attention restoration", "sensory deprivation", "temporal disorientation",
    "compassion fatigue", "existential dread", "perfectionism paralysis",
    "nostalgia addiction", "screen fatigue", "taste monotony",
    "creative jealousy", "imposter syndrome", "burnout recovery",
    "morning dread", "meeting exhaustion", "email overwhelm",
    "friendship drift", "hobby abandonment", "book guilt",
    "wardrobe paralysis", "kitchen intimidation", "fitness boredom",
    "travel anxiety", "pet separation", "plant neglect",
    "music discovery fatigue", "podcast overload", "notification numbness",
    "digital identity fragmentation", "algorithmic echo chambers",
    "parasocial relationship dependency", "doom scrolling compulsion",
    "context switching overhead", "zoom fatigue syndrome",
    "ambient noise pollution", "light pollution disruption",
    "microplastic anxiety", "climate grief overwhelm",
    "intergenerational communication gaps", "cultural displacement stress",
    "language attrition anxiety", "skill obsolescence fear",
    "chronic comparison syndrome", "productivity guilt",
    "rest deficit accumulation", "boundary erosion in remote work",
    "cognitive load from choice abundance", "sensory overwhelm in retail",
    "analysis paralysis in dating", "decision regret rumination",
    "phantom vibration syndrome", "email apnea",
    "continuous partial attention", "tab bankruptcy",
    "subscription fatigue", "password exhaustion",
    "update notification overload", "cloud storage anxiety",
    "digital hoarding", "inbox zero obsession",
    "social media withdrawal", "FOMO paralysis",
    "reply debt accumulation", "voice message avoidance",
    "calendar tetris", "meeting recovery syndrome",
    "open office sensory assault", "commute rage transformation",
    "Sunday night dread", "Monday morning inertia",
    "mid-afternoon energy collapse", "post-lunch cognitive fog",
    "seasonal affective disruption", "weather mood coupling",
    "barometric pressure sensitivity", "electromagnetic hypersensitivity",
    "urban heat island discomfort", "acoustic privacy erosion",
    "olfactory fatigue in workspaces", "ergonomic neglect syndrome",
    "sedentary metabolism slowdown", "repetitive strain accumulation",
    "eye strain from blue light", "neck tension from screen posture",
    "wrist compression from typing", "back pain from sitting",
    "shallow breathing pattern", "chronic dehydration unawareness",
    "meal timing chaos", "snack guilt spiraling",
    "caffeine dependency cycling", "sugar crash oscillation",
    "sleep onset insomnia", "middle-of-night awakening",
    "dream anxiety carryover", "alarm clock trauma response",
    "jet lag disorientation", "shift work circadian disruption",
    "weekend sleep schedule drift", "nap guilt in adults",
    "micro-grief accumulation", "ambiguous loss processing",
    "anticipatory anxiety spiraling", "rumination loop entrenchment",
    "emotional labor depletion", "empathy fatigue in caregivers",
    "vicarious trauma absorption", "moral injury processing",
    "identity foreclosure in careers", "purpose deficit syndrome",
    "meaning-making after loss", "legacy anxiety",
    "death awareness avoidance", "aging denial stress",
    "body image distortion", "movement shame",
    "voice insecurity", "handwriting deterioration anxiety",
    "spatial navigation decline", "face recognition difficulty",
    "name recall failure", "tip-of-tongue frustration",
    "taste bud atrophy from processed food", "smell blindness from urban living",
    "touch deprivation in digital age", "proprioceptive confusion from VR",
    "vestibular mismatch from screens", "interoceptive alexithymia",
    "emotional granularity deficit", "affective forecasting errors",
    "hedonic adaptation treadmill", "satisfaction plateau syndrome",
    "novelty seeking burnout", "routine suffocation",
    "spontaneity deficit", "play deprivation in adults",
    "wonder atrophy", "curiosity suppression",
    "imagination calcification", "metaphor blindness",
    "narrative identity fragmentation", "coherence anxiety",
    "authenticity performance", "vulnerability avoidance",
    "intimacy scaling problems", "trust calibration errors",
    "attachment style mismatch", "love language incompatibility",
    "friendship maintenance overhead", "community dissolution",
    "belonging homelessness", "tribal identity crisis",
    "civic disengagement", "political despair syndrome",
    "justice fatigue", "activism burnout",
    "hope depletion", "future anxiety",
    "retrospective distortion", "present moment blindness",
]

ARCHETYPES = [
    "wearable device", "ambient intelligence system", "robotic companion",
    "neural interface", "augmented reality overlay", "smart textile",
    "bio-reactive garment", "sonic sculpture", "living architecture",
    "edible technology", "olfactory engine", "kinetic installation",
    "dream machine", "memory capsule", "emotional barometer",
    "empathy amplifier", "serendipity engine", "wonder generator",
    "silence cultivator", "boredom transmuter", "fear metabolizer",
    "joy synthesizer", "grief vessel", "curiosity compass",
    "attention garden", "patience trainer", "awe inducer",
    "comfort cocoon", "adventure simulator", "wisdom distillery",
    "micro-ecosystem", "symbiotic implant", "holographic companion",
    "temporal anchor", "spatial harmonizer", "resonance chamber",
    "biofeedback mirror", "emotional thermostat", "cognitive scaffold",
    "sensory translator", "mood architect", "thought crystallizer",
    "portable sanctuary", "social lubricant device", "intimacy calibrator",
    "belonging beacon", "vulnerability shield", "trust accelerator",
    "forgiveness engine", "gratitude amplifier", "resilience forge",
    "nostalgia distillery", "hope generator", "meaning synthesizer",
    "play catalyst", "flow state inducer", "creative defibrillator",
    "inspiration antenna", "motivation compass", "discipline exoskeleton",
    "focus funnel", "procrastination dissolvent", "perfectionism antidote",
    "rest permission device", "boundary projection field", "energy audit tool",
    "decision crystallizer", "priority illuminator", "values compass",
    "conflict transformation chamber", "dialogue accelerator",
    "perspective rotation device", "assumption shattering lens",
    "bias detection visor", "empathy translation earpiece",
    "cultural bridge generator", "language feeling translator",
    "gesture interpretation glove", "microexpression decoder ring",
    "tone calibration pendant", "intention clarification beacon",
    "apology composition assistant", "compliment precision tool",
    "small talk elimination device", "deep conversation catalyst",
    "shared silence generator", "collective effervescence amplifier",
    "communitas crystallizer", "ritual design engine",
    "ceremony automation system", "celebration amplification array",
    "mourning support lattice", "transition navigation device",
    "threshold crossing detector", "liminal space generator",
    "in-between state cultivator", "paradox holding container",
    "ambiguity tolerance trainer", "uncertainty surfboard",
    "chaos navigation compass", "emergence detection sensor",
    "pattern recognition enhancer", "synchronicity catcher",
    "coincidence amplifier", "luck surface area expander",
    "opportunity antenna array", "readiness cultivation system",
    "micro-adventure dispenser", "wonder subscription service",
    "awe-on-demand projector", "delight calibration system",
    "spontaneity injection device", "routine disruption engine",
    "comfort zone expansion tool", "growth edge detector",
    "learning acceleration harness", "skill transfer bridge",
    "knowledge fermentation vessel", "insight crystallization chamber",
    "wisdom extraction apparatus", "understanding deepening lens",
]

MATERIALS = [
    "graphene-laced silk", "bio-gel composite", "shape-memory alloy mesh",
    "ferrofluid reservoir", "piezoelectric ceramic array", "mycelium substrate",
    "aerogel insulation matrix", "phase-change microcapsules",
    "conductive polymer weave", "quantum dot array", "cellulose nanocrystal",
    "magnetorheological fluid", "electrochromic glass", "photonic crystal fiber",
    "hydrogel scaffold", "carbon nanotube lattice", "bismuth telluride thermoelectric",
    "barium titanate sensor", "polyvinylidene fluoride membrane",
    "liquid crystal elastomer", "metamaterial lens array", "acoustic metamaterial shell",
    "bioprinted collagen scaffold", "self-healing polymer matrix",
    "thermochromic ink layer", "electroluminescent panel", "triboelectric nanogenerator",
    "perovskite solar cell", "molecularly imprinted polymer", "supercapacitor textile",
    "spider silk protein fiber", "bacterial cellulose film", "chitin nanowhisker composite",
    "lignin-based carbon foam", "keratin microfiber mesh", "silk fibroin hydrogel",
    "alginate bead matrix", "chitosan membrane filter", "collagen-elastin hybrid",
    "fibrin network scaffold", "hyaluronic acid gel pad", "gelatin methacryloyl substrate",
    "polycaprolactone framework", "polylactic acid lattice", "polyhydroxybutyrate shell",
    "zein protein coating", "casein-based adhesive layer", "shellac encapsulation",
    "beeswax phase-change core", "cork cellular composite", "bamboo fiber reinforcement",
    "hemp-graphene hybrid textile", "flax-carbon blend weave", "wool-copper antimicrobial mesh",
    "seaweed-derived bioplastic", "mushroom leather substitute", "pineapple leaf fiber fabric",
    "coconut coir acoustic panel", "rice husk silica aerogel", "corn starch biopolymer",
    "mussel-inspired adhesive polymer", "gecko-foot microstructure array",
    "lotus-effect superhydrophobic surface", "shark-skin riblet pattern",
    "butterfly-wing photonic structure", "beetle-carapace moisture collector",
    "cactus-spine fog harvester", "pine-cone hygroscopic actuator",
    "venus-flytrap snap-through mechanism", "mimosa pudica touch-responsive element",
]

MECHANISMS = [
    "resonant frequency matching", "adaptive impedance tuning",
    "closed-loop biofeedback", "machine learning preference model",
    "swarm intelligence coordination", "biomimetic chemotaxis",
    "stochastic resonance amplification", "entrainment synchronization",
    "gradient descent optimization", "evolutionary algorithm breeding",
    "attention-weighted filtering", "predictive anticipation engine",
    "emotional valence scoring", "semantic similarity mapping",
    "spectral decomposition analysis", "wavelet transform processing",
    "Bayesian belief updating", "reinforcement learning reward shaping",
    "generative adversarial synthesis", "diffusion model hallucination",
    "topological data analysis", "persistent homology detection",
    "chaos theory bifurcation", "fractal dimension scaling",
    "cellular automaton emergence", "agent-based social simulation",
    "graph neural network traversal", "transformer attention routing",
    "variational autoencoder compression", "contrastive learning alignment",
    "self-supervised representation building", "few-shot transfer adaptation",
    "meta-learning rapid calibration", "continual learning memory consolidation",
    "federated learning privacy preservation", "differential privacy noise injection",
    "reservoir computing echo state", "liquid state machine processing",
    "spiking neural network temporal coding", "Hebbian learning plasticity",
    "neuromodulated gating", "attention-gated memory retrieval",
    "episodic memory replay", "semantic memory consolidation",
    "working memory buffer management", "cognitive load distribution",
    "salience detection filtering", "novelty detection flagging",
    "habituation decay scheduling", "sensitization amplification",
    "classical conditioning association", "operant reinforcement shaping",
    "analogical reasoning mapping", "causal inference extraction",
    "counterfactual simulation generation", "abductive hypothesis ranking",
]

NAME_P = [
    "Chrono", "Echo", "Aura", "Soma", "Lyra", "Nova", "Flux", "Vox",
    "Lumen", "Cipher", "Helix", "Nexus", "Pulse", "Drift", "Bloom",
    "Ember", "Frost", "Tide", "Whisper", "Spark", "Phantom", "Reverie",
    "Nimbus", "Zenith", "Horizon", "Cascade", "Prism", "Muse", "Oracle",
    "Meridian", "Aurora", "Tessera", "Chimera", "Nebula", "Quartz",
    "Sable", "Coral", "Fathom", "Zephyr", "Vesper", "Mirage", "Arbor",
    "Crucible", "Pendulum", "Lattice", "Alchemy", "Symbiont", "Catalyst",
    "Resonance", "Entropy", "Kinesis", "Morphe", "Mythos", "Pneuma",
    "Solace", "Verdant", "Obsidian", "Amber", "Indigo", "Crimson",
    "Cobalt", "Opal", "Jade", "Onyx", "Ivory", "Scarlet", "Slate",
    "Umber", "Ochre", "Sienna", "Azure", "Cerulean", "Viridian",
    "Seraph", "Golem", "Djinn", "Nymph", "Sylph", "Undine", "Salamander",
    "Phoenix", "Griffin", "Sphinx", "Hydra", "Kraken", "Leviathan",
    "Basilisk", "Ouroboros", "Mandala", "Fractal", "Mobius", "Klein",
    "Euclid", "Riemann", "Gauss", "Euler", "Fermat", "Godel",
    "Turing", "Shannon", "Wiener", "Fourier", "Laplace", "Boltzmann",
    "Carnot", "Faraday", "Maxwell", "Planck", "Bohr", "Dirac",
    "Feynman", "Hawking", "Penrose", "Mandelbrot", "Lorenz", "Prigogine",
    "Kauffman", "Wolfram", "Conway", "Maturana", "Varela",
    "Lovelock", "Margulis", "Curie", "Lovelace", "Noether",
    "Hypatia", "Hildegard", "Sagan", "Tesla", "Babbage",
    "Archimedes", "Democritus", "Thales", "Empedocles", "Lucretius",
    "Avicenna", "Paracelsus", "Kepler", "Galileo", "Copernicus",
    "Vesalius", "Hooke", "Leibniz", "Huygens", "Lavoisier",
    "Dalton", "Darwin", "Mendel", "Pasteur", "Cajal",
    "Ether", "Void", "Abyss", "Zenith", "Nadir", "Apogee", "Perigee",
    "Vertex", "Vortex", "Axis", "Arc", "Chord", "Tangent", "Secant",
]

NAME_S = [
    "Weaver", "Forge", "Lens", "Shell", "Nest", "Loom", "Garden",
    "Engine", "Mirror", "Bridge", "Key", "Gate", "Thread", "Beacon",
    "Compass", "Anvil", "Chalice", "Crucible", "Vessel", "Prism",
    "Chamber", "Cocoon", "Lattice", "Spiral", "Membrane", "Conduit",
    "Harmonic", "Node", "Filament", "Chrysalis", "Catalyst", "Oscillator",
    "Synthesizer", "Resonator", "Amplifier", "Dampener", "Calibrator",
    "Navigator", "Cartographer", "Alchemist", "Distillery", "Apparatus",
    "Mechanism", "Interface", "Protocol", "Matrix", "Topology", "Manifold",
    "Field", "Wave", "Particle", "Tensor", "Vector", "Gradient",
    "Attractor", "Basin", "Orbit", "Trajectory", "Phase", "Spectrum",
    "Channel", "Stream", "River", "Delta", "Confluence",
    "Wellspring", "Aquifer", "Geyser", "Spring", "Fountain", "Cascade",
    "Eddy", "Vortex", "Whirlpool", "Maelstrom", "Current",
    "Root", "Stem", "Canopy", "Grove", "Thicket",
    "Rhizome", "Mycelium", "Spore", "Seed", "Pollen",
    "Nectar", "Sap", "Resin", "Bark", "Heartwood",
    "Ember", "Flame", "Spark", "Flint", "Tinder",
    "Furnace", "Kiln", "Crucible", "Retort", "Alembic", "Still",
    "Pendulum", "Gyroscope", "Sextant", "Astrolabe", "Orrery",
    "Telescope", "Microscope", "Kaleidoscope", "Periscope", "Stethoscope",
]

ACTIONS = [
    "detects", "amplifies", "translates", "harmonizes", "crystallizes",
    "dissolves", "reconfigures", "weaves", "distills", "resonates with",
    "anticipates", "metabolizes", "cultivates", "channels", "refracts",
    "modulates", "synthesizes", "attenuates", "calibrates", "orchestrates",
    "transforms", "maps", "navigates", "sculpts", "ferments",
    "decants", "precipitates", "sublimes", "transmutes", "catalyzes",
    "inoculates", "grafts", "pollinates", "propagates", "germinates",
    "incubates", "nurtures", "prunes", "composts", "infuses",
    "steeps", "brews", "extracts", "filters", "clarifies",
    "concentrates", "emulsifies", "suspends", "vitrifies", "anneals",
    "tempers", "quenches", "forges", "braids", "knits",
    "felts", "spins", "warps", "etches", "engraves",
]

QUALITIES = [
    "sublimely intuitive", "deceptively simple", "hauntingly beautiful",
    "absurdly practical", "quietly revolutionary", "elegantly chaotic",
    "profoundly personal", "delightfully weird", "unexpectedly soothing",
    "fiercely gentle", "impossibly precise", "beautifully unpredictable",
    "stubbornly optimistic", "gloriously unnecessary", "tenderly ruthless",
    "radically soft", "strategically whimsical", "methodically wild",
    "precisely messy", "carefully reckless", "thoughtfully absurd",
    "rigorously playful", "gently relentless", "warmly analytical",
    "coolly passionate", "lucidly dreamy", "pragmatically magical",
    "scientifically mystical", "technically poetic", "engineered for wonder",
    "optimized for awe", "calibrated for joy", "tuned to tenderness",
    "designed for delight", "built for belonging", "crafted for curiosity",
    "shaped by serendipity", "forged in empathy", "tempered by patience",
    "polished by persistence", "refined through failure",
    "cosmically irreverent", "tenderly precise", "wildly disciplined",
]

FORMS = [
    "river stone", "nautilus shell", "seed pod", "coral fragment",
    "obsidian pebble", "amber droplet", "lotus bud", "geode cross-section",
    "origami crane", "blown glass orb", "ceramic tile", "bronze amulet",
    "wooden toggle", "leather cuff", "silk ribbon", "copper ring",
    "pewter brooch", "crystal pendant", "bone dice", "horn button",
    "felted wool sphere", "woven grass basket", "clay whistle",
    "carved antler", "polished driftwood", "sea glass fragment",
    "pressed flower locket", "fossil imprint", "meteorite sliver",
    "volcanic glass shard", "sandstone disc", "marble egg",
    "alabaster vial", "soapstone figurine", "porcelain thimble",
    "enamel pin", "lacquered box", "bamboo tube", "gourd rattle",
    "coconut shell cup", "terracotta medallion", "jade bead",
    "lapis lazuli tablet", "turquoise mosaic", "carnelian seal",
]


# ---------------------------------------------------------------------------
# Fast name + content generation
# ---------------------------------------------------------------------------

def _rng(i: int) -> random.Random:
    return random.Random(hashlib.md5(f"million-{i}".encode()).hexdigest())


def _name(r):
    p = r.choice(NAME_P)
    s = r.choice(NAME_S)
    v = r.random()
    if v < 0.2: return f"The {p}{s}"
    if v < 0.35: return f"{p} {s}"
    if v < 0.48: return f"Project {p}"
    if v < 0.58: return f"The {p} {s}"
    if v < 0.68: return f"{p}{s} v{r.randint(1,9)}.{r.randint(0,9)}"
    if v < 0.78: return f"{p}-{r.choice(NAME_P)}"
    if v < 0.88: return f"{p}{s}"
    return f"The {r.choice(NAME_P)} {p}{s}"


# 6 template functions for variety
def _t0(n, r):
    a = r.choice(ARCHETYPES); p = r.sample(PROBLEM_DOMAINS, 2)
    t = r.sample(TECH_DOMAINS, 3); m = r.sample(MATERIALS, 2)
    mc = r.sample(MECHANISMS, 2); lf = r.choice(LIFE_FORCES)
    ph = r.choice(PHILOSOPHICAL_CONCEPTS); ac = r.sample(ACTIONS, 3)
    q = r.choice(QUALITIES); f = r.choice(FORMS)
    return f"""## {n}

## Overview

{n} is a **{q}** {a} that {ac[0]} the invisible patterns of {p[0]} and {ac[1]} them into tangible experiences of relief and wonder. Drawing on the concept of *{lf}* and *{ph}*, it bridges the measurable and the felt.

## The Problem It Solves

{p[0].capitalize()} affects millions, yet most solutions ignore the **{t[0]}** dimension of human experience. {p[1].capitalize()} compounds it, creating loops no conventional tool can break. People need a living, adaptive presence that understands the rhythms of their specific struggle.

## How It Works

{n} employs a **{t[1]} {mc[0]}** system embedded in {m[0]}. It monitors galvanic skin response, micro-expressions, respiratory cadence, and **{t[2]}** fluctuations via a {mc[1]} engine.

1. **Immediate Layer**: A {t[0]} pulse through {m[1]} calibrated to arousal state
2. **Adaptive Layer**: {mc[0].capitalize()} adjusts light spectrum, sound frequency, and haptic patterns
3. **Deep Layer**: Learns to {ac[2]} patterns preemptively, inspired by *{lf}* energy flow

Housed in a form reminiscent of a {f}.

## Why It's Brilliant

The **{t[1]}** array doesn't just measure — it listens. The {mc[1]} engine doesn't compute — it composes. It develops a "**Sympathetic Resonance Profile**" — a living map of emotional architecture.

## Elevator Pitch

{n}: the first {a} that turns {p[0]} into self-discovery — part {lf.lower()}-channel, part {t[0]} intelligence, entirely {q.split()[-1]}.
"""

def _t1(n, r):
    a = r.choice(ARCHETYPES); p = r.sample(PROBLEM_DOMAINS, 3)
    t = r.sample(TECH_DOMAINS, 4); m = r.sample(MATERIALS, 3)
    mc = r.sample(MECHANISMS, 3); lf = r.choice(LIFE_FORCES)
    ph = r.choice(PHILOSOPHICAL_CONCEPTS); ac = r.sample(ACTIONS, 4)
    q = r.choice(QUALITIES); f = r.choice(FORMS)
    return f"""## {n}

## Overview

Born from the frustration of {p[0]} and the epidemic of {p[1]}, {n} is a **{q}** {a} that {ac[0]} root causes and {ac[1]} them into generative force. Inspired by *{lf}*.

## The Problem It Solves

{p[0].capitalize()} costs hours of genuine presence daily. Combined with {p[1]}, it creates compound deficits no app can touch. The issue isn't willpower — existing solutions operate at the wrong scale, ignoring the **{t[0]}** substrate. {p[2].capitalize()} makes everything worse.

## How It Works

Three interlocking subsystems on {m[0]}:

**{t[1].title()} Sensing Mesh**: {m[1]} substrate with {t[2]} filaments reading autonomic arousal without conscious input.

**{mc[0].title()} Core**: {mc[1]} processor maintaining a living baseline model, learning signatures that precede episodes of {p[0]}.

**Response Lattice**: {ac[2]}s through {m[2]}, delivering **{t[3]}** stimulation via {mc[2]}.

Form factor: a {f} — unobtrusive and beautiful.

## Why It's Brilliant

Embodies *{ph}* — works with {p[0]}'s patterns, redirecting energy rather than suppressing it. Deepening resonance over time.

## Elevator Pitch

Stop managing {p[0]} — let {n} {ac[3]} it into fuel for the life you want.
"""

def _t2(n, r):
    a = r.choice(ARCHETYPES); p = r.sample(PROBLEM_DOMAINS, 2)
    t = r.sample(TECH_DOMAINS, 3); m = r.sample(MATERIALS, 3)
    mc = r.sample(MECHANISMS, 3); lf = r.choice(LIFE_FORCES)
    ph = r.choice(PHILOSOPHICAL_CONCEPTS); ac = r.sample(ACTIONS, 4)
    q = r.choice(QUALITIES); f = r.choice(FORMS)
    return f"""## {n}

## Overview

{n} began as a thought experiment: what if a {a} treated {p[0]} as a signal waiting to be decoded? The result is **{q}** — it {ac[0]} the body's language and {ac[1]} it into conversation, not treatment.

## The Problem It Solves

You're in a meeting, composure intact, but {p[0]} builds like static. Your {t[0]} signature shifts, breathing changes, capacity for {p[1]} erodes. Every tool requires noticing first. {n} flips the sequence.

## How It Works

Built around {m[0]}, shaped like a {f}:

First, a **{t[1]} detection array** in {m[1]} via {mc[0]} reads what you can't articulate — creative tension vs. destructive stress.

Second, a **{mc[1]} interpretation layer** drawing on *{ph}* maps full emotional topology, not just a stress score.

Third, a **{t[2]} response network** in {m[2]} delivers interventions so subtle they feel like your own idea: breathing shifts, attention redirection, energy {ac[2]}ing.

Uses {mc[2]} and *{lf}* — vital energy that flows through channels gently guided, never forced.

## Why It's Brilliant

Most wellness tech treats you as a problem. {n} treats you as a complex system to understand. **{q.capitalize()}** because it honors the paradox: vulnerabilities and capacities share the same root.

## Elevator Pitch

{n}: listens to what your body knows and {ac[3]} it into clarity.
"""

def _t3(n, r):
    a = r.choice(ARCHETYPES); p = r.sample(PROBLEM_DOMAINS, 2)
    t = r.sample(TECH_DOMAINS, 4); m = r.sample(MATERIALS, 3)
    mc = r.sample(MECHANISMS, 3); lf = r.choice(LIFE_FORCES)
    ac = r.sample(ACTIONS, 2); f = r.choice(FORMS)
    sens = r.randint(50,500); layers = r.randint(4,16)
    acc = r.randint(85,97); fp = r.randint(2,8); cal = r.randint(3,14)
    return f"""## {n}

## Overview

{n} applies **{t[0]} {mc[0]}** principles to {p[0]}. Built on {m[0]}, it rethinks how technology interfaces with **{t[1]}** dimensions of experience, drawing on *{lf}*.

## The Problem It Solves

Current approaches fail at instrumentation. Consumer wearables measure gross metrics while {p[0]} operates at the **{t[2]}** scale. {p[1].capitalize()} introduces masking noise. What's needed: a modality that {ac[0]}s subtle precursors with sufficient resolution for preemptive intervention.

## How It Works

**Sensing Architecture**: {m[1]} in a {t[0]} configuration at the **{t[3]}** band — {sens}x greater sensitivity than conventional approaches. Geometry optimized through {mc[1]}.

**Signal Processing Pipeline**:
- **Stage 1**: {t[1].title()} feature extraction via {mc[2]}
- **Stage 2**: Temporal pattern recognition via {layers}-layer recurrent architecture
- **Stage 3**: Causal inference distinguishing genuine precursors from coincidence

**Intervention Delivery**: {m[2]} delivers **{t[2]}** stimulation following a modified {lf.lower()}-inspired protocol — intensity scales inversely with detection confidence.

**Calibration**: {cal}-day baseline period. After: {acc}% sensitivity, <{fp}% false positive rate.

## Why It's Brilliant

The breakthrough is transduction physics. Operating at the **{t[3]}** interface captures signals encoding pre-conscious genesis of {p[0]}. A genuinely new sensing modality for the oldest challenge: understanding ourselves.

## Elevator Pitch

{n}: laboratory-grade {t[0]} sensing in a {f}, making {p[0]}'s invisible architecture visible and addressable.
"""

def _t4(n, r):
    a = r.choice(ARCHETYPES); p = r.sample(PROBLEM_DOMAINS, 2)
    t = r.sample(TECH_DOMAINS, 3); m = r.sample(MATERIALS, 3)
    mc = r.sample(MECHANISMS, 2); lf = r.choice(LIFE_FORCES)
    ph = r.choice(PHILOSOPHICAL_CONCEPTS); ac = r.sample(ACTIONS, 4)
    q = r.choice(QUALITIES); f = r.choice(FORMS)
    return f"""## {n}

## Overview

In the tradition of *{ph}*, {n} begins with a radical premise: {p[0]} is not malfunction but intelligence — the body {ac[0]}ing information the conscious mind hasn't processed. This **{q}** {a} doesn't silence that intelligence; it {ac[1]} it into shared language.

## The Problem It Solves

The modern approach is Cartesian — mind as pilot, body as vehicle, discomfort as mechanical failure. But *{lf}* tells a different story: vital energy flows in meaningful patterns, and {p[0]} occurs when those patterns encounter blockages. {p[1].capitalize()} is the same pattern at different scale.

## How It Works

Shaped like a {f}, crafted from {m[0]}:

**Listening Mode**: {t[0]} sensors in {m[1]} via {mc[0]} map physiological patterns as emotional topographies — landscapes with valleys, ridges, rivers of sensation.

**Dialogue Mode**: Responds to {p[0]} patterns not with correction but with a question — a **{t[1]}** stimulus through {m[2]} that {ac[2]} attention toward the pattern itself. Inspired by *{ph}*.

**Integration Mode**: The {mc[1]} core learns which patterns precede insight vs. escalation, gradually {ac[3]}ing the boundary between productive discomfort and genuine distress — what *{lf}* traditions call embodied wisdom.

## Why It's Brilliant

The **{t[1]} {mc[0]}** system is rigorous enough for clinical validation, yet the paradigm honors irreducible mystery. It doesn't eliminate {p[0]} — it makes it meaningful.

## Elevator Pitch

{n}: asks what your {p[0]} is trying to tell you — and helps you listen.
"""

def _t5(n, r):
    a = r.choice(ARCHETYPES); p = r.sample(PROBLEM_DOMAINS, 2)
    t = r.sample(TECH_DOMAINS, 4); m = r.sample(MATERIALS, 3)
    mc = r.sample(MECHANISMS, 3); lf = r.choice(LIFE_FORCES)
    ac = r.sample(ACTIONS, 4); q = r.choice(QUALITIES); f = r.choice(FORMS)
    animal = r.choice(["Octopus","Chameleon","Firefly","Pangolin","Axolotl","Tardigrade","Platypus","Mantis Shrimp","Cuttlefish","Nautilus"])
    return f"""## {n}

## Overview

Picture this: a {f} that hums when you're about to make a terrible decision, glows when you're accidentally brilliant, and vibrates when you've been doing {p[0]} too long. {n} is a **{q}** {a} that treats the human condition with tremendous affection.

## The Problem It Solves

{p[0].capitalize()} is the common cold of the modern psyche — everyone gets it, nobody's cured it. {p[1].capitalize()} lurks in the background like a passive-aggressive coworker. The real problem? Existing solutions have the personality of a spreadsheet. What if addressing {p[0]} was actually fun?

## How It Works

Built on the **{lf.capitalize()} Protocol** — engineering that prioritizes delight over efficiency:

- **The {t[0].title()} Tickle**: A barely perceptible {t[0]} sensation through {m[0]} that feels like your favorite memory trying to get your attention
- **The {mc[0].title()} Shuffle**: Subtly {ac[0]} your environment — shifting light, redirecting sound, introducing {t[1]} micro-patterns — creating tiny moments of wonder
- **The {animal} Gambit**: When all else fails, the {mc[1]} core generates a completely unexpected {t[2]} experience — a micro-adventure calibrated to your specific brand of {p[0]}

The whole thing uses {mc[2]} inside {m[1]} wrapped in {m[2]}, because even components should be interesting.

## Why It's Brilliant

Most wellness tech assumes you need fixing. {n} assumes you need surprise. {p[0].capitalize()} loses its grip the moment something genuinely interesting happens. **{t[3]}** precision delivering **{q.split()[0]}** delight.

Also, it looks like a {f}. Objectively wonderful.

## Elevator Pitch

{n}: because the cure for {p[0]} isn't another app telling you to breathe — it's a {f} that {ac[1]} your day into an adventure.
"""

TEMPLATES = [_t0, _t1, _t2, _t3, _t4, _t5]

FILES_PER_BATCH = 1000


def slugify(s: str) -> str:
    s = s.lower().replace(" ", "_").replace("/", "-").replace("—", "_")
    s = "".join(c for c in s if c.isalnum() or c in "_-")
    return s[:110]


def main():
    TOTAL = int(sys.argv[1]) if len(sys.argv) > 1 else 1_000_000
    start = time.time()
    success = 0
    errors = 0
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    print(f"\n{'='*60}")
    print(f"  OctoBot Million Idea Generator -- {TOTAL:,} ideas")
    print(f"  Sharding: {FILES_PER_BATCH} files per batch directory")
    print(f"{'='*60}\n")

    # Pre-create batch directories
    num_batches = (TOTAL + FILES_PER_BATCH - 1) // FILES_PER_BATCH
    for b in range(num_batches):
        (LIBRARY / f"batch_{b:04d}").mkdir(parents=True, exist_ok=True)

    print(f"  Created {num_batches} batch directories\n")

    for i in range(TOTAL):
        try:
            r = _rng(i)
            name = _name(r)
            archetype = r.choice(ARCHETYPES)
            topic = f"{name} -- {archetype} for {r.choice(PROBLEM_DOMAINS)}"
            slug = slugify(topic)

            # Pick template
            template_fn = r.choice(TEMPLATES)
            body = template_fn(name, r)

            # Build full file content
            content = f"# {topic}\n\n*Created by OctoBot on {now_str}*\n\n{body}\n"

            # Write directly to sharded directory
            batch_idx = i // FILES_PER_BATCH
            filepath = LIBRARY / f"batch_{batch_idx:04d}" / f"{slug}.md"
            filepath.write_text(content, encoding="utf-8")

            success += 1

        except Exception as e:
            errors += 1
            if errors <= 10:
                print(f"\n  [!] Error #{errors} on idea {i}: {e}")

        # Progress every 500
        if (i + 1) % 500 == 0:
            el = time.time() - start
            rate = (i + 1) / el
            eta = (TOTAL - i - 1) / rate if rate > 0 else 0
            bar_len = 50
            filled = int(bar_len * (i + 1) / TOTAL)
            bar = '#' * filled + '-' * (bar_len - filled)
            pct = 100 * (i + 1) / TOTAL

            # ETA formatting
            if eta > 3600:
                eta_s = f"{eta/3600:.1f}h"
            elif eta > 60:
                eta_s = f"{eta/60:.1f}m"
            else:
                eta_s = f"{eta:.0f}s"

            print(f"\r  [{bar}] {pct:5.1f}%  {i+1:>9,}/{TOTAL:,}  "
                  f"ok={success:,} err={errors}  "
                  f"{rate:,.0f}/s  ETA {eta_s}   ", end="", flush=True)

        if (i + 1) % 100_000 == 0:
            el = time.time() - start
            print(f"\n  -- Milestone: {i+1:,} ideas in {el:.0f}s "
                  f"({(i+1)/el:,.0f}/s avg)")

    elapsed = time.time() - start
    if elapsed > 3600:
        time_s = f"{elapsed/3600:.1f} hours"
    elif elapsed > 60:
        time_s = f"{elapsed/60:.1f} minutes"
    else:
        time_s = f"{elapsed:.1f} seconds"

    print(f"\n\n{'='*60}")
    print(f"  DONE -- {success:,} ideas saved, {errors} errors")
    print(f"  Time: {time_s} ({success/max(1,elapsed):,.0f} ideas/sec)")
    print(f"  Location: workspace/library/batch_0000/ .. batch_{num_batches-1:04d}/")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
