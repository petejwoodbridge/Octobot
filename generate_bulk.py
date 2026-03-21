"""
generate_bulk.py — Bulk idea generator for OctoBot (30k scale)
===============================================================
Generates tens of thousands of unique, richly detailed ideas influenced by
the context library and existing knowledge graph concepts.

Usage:  python generate_bulk.py [count]     (default: 30000)
"""

import os
import sys
import random
import hashlib
import time
from pathlib import Path

# Fix Windows console encoding
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).parent))

import tools
import scoring

# ---------------------------------------------------------------------------
# Massive vocabulary banks for 30k+ unique ideas
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
    "interoceptive wisdom", "apophatic knowing",
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
    "foot numbness from standing desks", "jaw clenching from stress",
    "shallow breathing pattern", "chronic dehydration unawareness",
    "meal timing chaos", "snack guilt spiraling",
    "caffeine dependency cycling", "sugar crash oscillation",
    "hydration tracking fatigue", "vitamin deficiency anxiety",
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
    "soy protein isolate film", "whey protein nanofiber", "eggshell calcium carbonate coating",
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
    "homomorphic encryption processing", "zero-knowledge proof verification",
    "consensus mechanism validation", "distributed ledger synchronization",
    "edge computing inference", "neuromorphic spike processing",
    "optical computing interference", "quantum annealing optimization",
    "adiabatic state preparation", "variational quantum eigensolver",
    "tensor network contraction", "matrix product state compression",
    "reservoir computing echo state", "liquid state machine processing",
    "spiking neural network temporal coding", "Hebbian learning plasticity",
    "neuromodulated gating", "attention-gated memory retrieval",
    "episodic memory replay", "semantic memory consolidation",
    "working memory buffer management", "cognitive load distribution",
    "salience detection filtering", "novelty detection flagging",
    "habituation decay scheduling", "sensitization amplification",
    "classical conditioning association", "operant reinforcement shaping",
    "social learning imitation", "observational modeling transfer",
    "analogical reasoning mapping", "causal inference extraction",
    "counterfactual simulation generation", "abductive hypothesis ranking",
]

NAME_PREFIXES = [
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
    "Basilisk", "Ouroboros", "Mandala", "Fractal", "Möbius", "Klein",
    "Euclid", "Riemann", "Gauss", "Euler", "Fermat", "Gödel",
    "Turing", "Shannon", "Wiener", "Fourier", "Laplace", "Boltzmann",
    "Carnot", "Faraday", "Maxwell", "Planck", "Bohr", "Dirac",
    "Feynman", "Hawking", "Penrose", "Mandelbrot", "Lorenz", "Prigogine",
    "Kauffman", "Wolfram", "Conway", "Hofstadter", "Maturana", "Varela",
    "Lovelock", "Margulis", "McClintock", "Curie", "Lovelace", "Noether",
    "Hypatia", "Hildegard", "Kwan", "Sagan", "Tesla", "Babbage",
    "Archimedes", "Democritus", "Thales", "Empedocles", "Lucretius",
    "Avicenna", "Paracelsus", "Kepler", "Galileo", "Copernicus",
    "Vesalius", "Harvey", "Hooke", "Leibniz", "Huygens", "Lavoisier",
    "Dalton", "Darwin", "Mendel", "Pasteur", "Koch", "Cajal",
]

NAME_SUFFIXES = [
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
    "Frequency", "Wavelength", "Amplitude", "Pulse", "Signal",
    "Channel", "Stream", "River", "Delta", "Estuary", "Confluence",
    "Wellspring", "Aquifer", "Geyser", "Spring", "Fountain", "Cascade",
    "Torrent", "Eddy", "Vortex", "Whirlpool", "Maelstrom", "Current",
    "Undertow", "Riptide", "Breaker", "Swell", "Crest", "Trough",
    "Root", "Stem", "Canopy", "Grove", "Thicket", "Copse",
    "Understory", "Rhizome", "Mycelium", "Spore", "Seed", "Pollen",
    "Nectar", "Sap", "Resin", "Bark", "Heartwood", "Sapwood",
    "Ember", "Flame", "Spark", "Flint", "Tinder", "Kindling",
    "Furnace", "Kiln", "Crucible", "Retort", "Alembic", "Still",
]

ACTIONS = [
    "detects", "amplifies", "translates", "harmonizes", "crystallizes",
    "dissolves", "reconfigures", "weaves", "distills", "resonates with",
    "anticipates", "metabolizes", "cultivates", "channels", "refracts",
    "modulates", "synthesizes", "attenuates", "calibrates", "orchestrates",
    "transforms", "maps", "navigates", "sculpts", "ferments",
    "decants", "precipitates", "sublimes", "transmutes", "catalyzes",
    "inoculates", "grafts", "pollinates", "propagates", "germinates",
    "incubates", "hatches", "nurtures", "prunes", "composts",
    "distills", "infuses", "steeps", "brews", "extracts",
    "filters", "clarifies", "concentrates", "dilutes", "emulsifies",
    "suspends", "precipitates", "crystallizes", "vitrifies", "anneals",
    "tempers", "quenches", "forges", "hammers", "folds",
    "braids", "knits", "felts", "spins", "warps",
]

QUALITIES = [
    "sublimely intuitive", "deceptively simple", "hauntingly beautiful",
    "absurdly practical", "quietly revolutionary", "elegantly chaotic",
    "profoundly personal", "delightfully weird", "unexpectedly soothing",
    "fiercely gentle", "impossibly precise", "beautifully unpredictable",
    "stubbornly optimistic", "gloriously unnecessary", "tenderly ruthless",
    "radically soft", "strategically whimsical", "methodically wild",
    "precisely messy", "carefully reckless", "thoughtfully absurd",
    "rigorously playful", "disciplined in its chaos", "gently relentless",
    "warmly analytical", "coolly passionate", "lucidly dreamy",
    "pragmatically magical", "scientifically mystical", "technically poetic",
    "engineered for wonder", "optimized for awe", "calibrated for joy",
    "tuned to tenderness", "designed for delight", "built for belonging",
    "crafted for curiosity", "shaped by serendipity", "forged in empathy",
    "tempered by patience", "polished by persistence", "refined through failure",
]

FORM_FACTORS = [
    "river stone", "nautilus shell", "seed pod", "coral fragment",
    "obsidian pebble", "amber droplet", "lotus bud", "geode cross-section",
    "origami crane", "blown glass orb", "ceramic tile", "bronze amulet",
    "wooden toggle", "leather cuff", "silk ribbon", "copper ring",
    "pewter brooch", "crystal pendant", "bone dice", "horn button",
    "felted wool sphere", "woven grass basket", "clay whistle",
    "carved antler", "polished driftwood", "sea glass fragment",
    "pressed flower locket", "resin-encased insect", "fossil imprint",
    "meteorite sliver", "volcanic glass shard", "sandstone disc",
    "marble egg", "alabaster vial", "soapstone figurine",
    "porcelain thimble", "enamel pin", "lacquered box",
    "bamboo tube", "gourd rattle", "coconut shell cup",
]

# Idea structure templates — 6 different formats for variety
TEMPLATES = [
    # Template 0: Standard (used in original)
    "standard",
    # Template 1: Problem-first
    "problem_first",
    # Template 2: Story-driven
    "story_driven",
    # Template 3: Technical deep-dive
    "technical",
    # Template 4: Philosophical
    "philosophical",
    # Template 5: Whimsical
    "whimsical",
]


def _rng_seed(i: int) -> random.Random:
    return random.Random(hashlib.md5(f"octobot-bulk-{i}-v2".encode()).hexdigest())


def _pick(rng, lst, n=1):
    return rng.sample(lst, min(n, len(lst)))


def _name(rng):
    prefix = rng.choice(NAME_PREFIXES)
    suffix = rng.choice(NAME_SUFFIXES)
    r = rng.random()
    if r < 0.25:
        return f"The {prefix}{suffix}"
    elif r < 0.45:
        return f"{prefix} {suffix}"
    elif r < 0.6:
        return f"Project {prefix}"
    elif r < 0.72:
        return f"The {prefix} {suffix}"
    elif r < 0.82:
        return f"{prefix}{suffix} {rng.choice(['Mark', 'Gen', 'Rev', 'Mk', 'v'])}.{rng.randint(1,9)}"
    elif r < 0.9:
        p2 = rng.choice(NAME_PREFIXES)
        return f"{prefix}-{p2}"
    else:
        return f"{prefix}{suffix}"


def generate_idea(idx: int) -> tuple[str, str]:
    rng = _rng_seed(idx)

    idea_name = _name(rng)
    archetype = rng.choice(ARCHETYPES)
    problems = _pick(rng, PROBLEM_DOMAINS, 3)
    tech = _pick(rng, TECH_DOMAINS, 4)
    mats = _pick(rng, MATERIALS, 3)
    mechs = _pick(rng, MECHANISMS, 3)
    life_force = rng.choice(LIFE_FORCES)
    philosophy = rng.choice(PHILOSOPHICAL_CONCEPTS)
    acts = _pick(rng, ACTIONS, 4)
    quality = rng.choice(QUALITIES)
    form = rng.choice(FORM_FACTORS)
    template = rng.choice(TEMPLATES)

    topic = f"{idea_name} — {archetype} for {problems[0]}"

    if template == "standard":
        content = f"""## {idea_name}

## Overview

{idea_name} is a **{quality}** {archetype} that {acts[0]} the invisible patterns of {problems[0]} and {acts[1]} them into tangible experiences of relief and wonder. Drawing on the ancient concept of *{life_force}* and the principle of *{philosophy}*, it bridges the measurable and the felt — a device that transforms the relationship between a person and their inner landscape.

## The Problem It Solves

{problems[0].capitalize()} affects millions, yet most solutions treat symptoms rather than causes. Existing approaches ignore the **{tech[0]}** dimension of human experience. Meanwhile, {problems[1]} compounds the issue, creating feedback loops that conventional tools cannot break. People need something that meets them where they are — not a prescription, but a living, adaptive presence that understands the rhythms of their struggle.

## How It Works

At its core, {idea_name} employs a **{tech[1]} {mechs[0]}** system embedded within a matrix of {mats[0]}. The device monitors subtle physiological signals — galvanic skin response, micro-expressions, respiratory cadence, and **{tech[2]}** fluctuations — feeding them into a {mechs[1]} engine that builds an evolving model of the user's emotional topology.

When the system detects the onset of {problems[0]}, it activates a layered response:

1. **Immediate Layer**: A gentle {tech[0]} pulse delivered through {mats[1]}, calibrated to the user's arousal state
2. **Adaptive Layer**: The {mechs[0]} module adjusts environmental parameters — light spectrum, ambient frequency, haptic patterns — creating a personalized micro-environment
3. **Deep Layer**: Over time, the system learns to {acts[2]} patterns before conscious awareness, offering preemptive interventions inspired by the *{life_force}* principle of energy flowing through natural channels

The entire system is housed in a form factor reminiscent of a {form}, designed to be held, worn, or placed in a personal space.

## Why It's Brilliant

What makes {idea_name} extraordinary is its refusal to separate the technical from the poetic. The **{tech[1]}** sensing array doesn't just measure — it listens. The {mechs[1]} engine doesn't just compute — it composes. Every intervention is simultaneously a scientific response and an aesthetic experience, honoring the ancient insight that healing and beauty are inseparable.

The system develops what its creators call a "**Sympathetic Resonance Profile**" — a living map of the user's emotional architecture that grows richer with every interaction.

## Elevator Pitch

{idea_name} is the world's first {archetype} that turns {problems[0]} into a doorway for self-discovery — part {life_force.lower()}-channel, part {tech[0]} intelligence, entirely {quality.split()[-1]}.
"""

    elif template == "problem_first":
        content = f"""## {idea_name}

## Overview

Born from the frustration of {problems[0]} and the silent epidemic of {problems[1]}, {idea_name} is a **{quality}** {archetype} that doesn't just address the symptom — it {acts[0]} the root cause and {acts[1]} it into something generative. Inspired by the *{life_force}* tradition of channeling invisible forces through physical vessels.

## The Problem It Solves

Consider this: {problems[0]} costs the average person 2.3 hours of genuine presence every single day. Combined with {problems[1]}, it creates a compound deficit that no productivity app or meditation timer can touch. The issue isn't willpower — it's that existing solutions operate at the wrong scale, addressing conscious behavior while ignoring the **{tech[0]}** substrate of embodied experience. {problems[2].capitalize()} makes everything worse, creating a triple-bind that leaves people feeling broken rather than stuck.

## How It Works

{idea_name} operates through three interlocking subsystems built on {mats[0]}:

**The {tech[1].title()} Sensing Mesh**: A {mats[1]} substrate woven with {tech[2]} filaments that continuously reads the user's physiological state without requiring conscious input. It detects micro-shifts in autonomic arousal, postural tension, and ambient environmental factors.

**The {mechs[0].title()} Core**: Raw sensor data flows into a {mechs[1]} processor that maintains a living model of the user's baseline patterns. Rather than applying generic interventions, it learns the specific signatures that precede episodes of {problems[0]} for this particular person.

**The Response Lattice**: When intervention is warranted, the system {acts[2]} a response through {mats[2]}, delivering precisely calibrated **{tech[3]}** stimulation. The response adapts in real-time, using {mechs[2]} to track effectiveness and adjust within seconds.

The entire device takes the form of a {form} — unobtrusive enough for daily carry, beautiful enough to invite touch.

## Why It's Brilliant

{idea_name} embodies the principle of *{philosophy}* — it doesn't fight against {problems[0]} but works with its inherent patterns, redirecting energy rather than suppressing it. The system becomes more effective over time, not through brute data accumulation, but through deepening its resonance with the user's unique psychophysiological signature.

## Elevator Pitch

Stop managing {problems[0]} — let {idea_name} {acts[3]} it into fuel for the life you actually want to live.
"""

    elif template == "story_driven":
        content = f"""## {idea_name}

## Overview

{idea_name} began as a thought experiment: what if we could build a {archetype} that treats {problems[0]} not as a bug in human cognition but as a signal waiting to be decoded? The result is **{quality}** — a device that {acts[0]} the language of the body and {acts[1]} it into experiences that feel less like treatment and more like conversation.

## The Problem It Solves

Imagine this scenario: you're sitting in a meeting, and somewhere beneath your professional composure, {problems[0]} is building like static electricity. You don't notice it — not consciously — but your {tech[0]} signature shifts, your breathing changes, and your capacity for {problems[1]} begins to erode. By the time you're aware of the problem, you've lost the thread. Every existing tool requires you to notice first, then act. {idea_name} flips this sequence entirely.

## How It Works

The device is built around a core of {mats[0]}, shaped like a {form}. Inside, three systems work in concert:

First, a **{tech[1]} detection array** made from {mats[1]} monitors your physiological state through {mechs[0]}. It reads what you can't articulate — the difference between creative tension and destructive stress, between productive focus and anxious fixation.

Second, a **{mechs[1]} interpretation layer** draws on principles from *{philosophy}* to contextualize these signals. Rather than reducing your experience to a stress score, it maps the full topology of your emotional state, recognizing that {problems[0]} and creative insight often share the same neurological neighborhood.

Third, a **{tech[2]} response network** embedded in {mats[2]} delivers interventions so subtle they feel like your own idea: a shift in breathing rhythm, a change in the quality of your attention, a gentle redirection that {acts[2]} the anxious energy into something useful.

The system uses {mechs[2]} to continuously refine its model of you, drawing on the ancient concept of *{life_force}* — the idea that vital energy flows through channels that can be gently guided but never forced.

## Why It's Brilliant

Most wellness technology treats you like a problem to be solved. {idea_name} treats you like a complex system to be understood. The difference is everything. It's **{quality}** because it honors the paradox at the heart of human experience: our greatest vulnerabilities and our greatest capacities share the same root.

## Elevator Pitch

{idea_name}: the {archetype} that listens to what your body already knows and {acts[3]} it into clarity.
"""

    elif template == "technical":
        content = f"""## {idea_name}

## Overview

{idea_name} is a precision-engineered {archetype} that applies **{tech[0]} {mechs[0]}** principles to the challenge of {problems[0]}. Built on a substrate of {mats[0]}, it represents a fundamental rethinking of how technology can interface with the **{tech[1]}** dimensions of human experience, drawing on insights from the *{life_force}* tradition.

## The Problem It Solves

Current approaches to {problems[0]} fail at the instrumentation level. Consumer wearables measure gross physiological metrics — heart rate, step count, sleep duration — while the actual mechanism of {problems[0]} operates at the **{tech[2]}** scale. The gap between what we measure and what matters creates a false sense of understanding. {problems[1]} compounds this by introducing noise that masks the signal. What's needed is a sensing modality that can {acts[0]} the subtle precursors of distress with sufficient temporal and spatial resolution to enable preemptive intervention.

## How It Works

**Sensing Architecture**: The primary transduction layer uses {mats[1]} arranged in a {tech[0]} configuration. Each sensing element operates at the **{tech[3]}** frequency band, providing {rng.randint(50, 500)}x greater sensitivity than conventional approaches. The array geometry is optimized through {mechs[1]} to maximize spatial coverage while minimizing cross-talk.

**Signal Processing Pipeline**: Raw sensor data passes through a three-stage {mechs[0]} pipeline:
- **Stage 1**: {tech[1].title()} feature extraction using {mechs[2]} to identify spectral signatures correlated with {problems[0]}
- **Stage 2**: Temporal pattern recognition via a {rng.randint(4, 16)}-layer recurrent architecture trained on {rng.randint(10, 100)}k annotated physiological episodes
- **Stage 3**: Causal inference engine that distinguishes genuine precursors from coincidental correlations

**Intervention Delivery**: The actuation system uses {mats[2]} to deliver precisely dosed **{tech[2]}** stimulation. Dosing follows a modified {life_force.lower()}-inspired protocol where intervention intensity scales inversely with detection confidence — the more certain the system is, the gentler the response needed.

**Calibration**: Initial personalization requires a {rng.randint(3, 14)}-day baseline period during which the {mechs[1]} model adapts to the user's individual {tech[0]} signature. After calibration, the system achieves {rng.randint(85, 97)}% sensitivity with <{rng.randint(2, 8)}% false positive rate.

## Why It's Brilliant

The breakthrough is in the transduction physics. By operating at the **{tech[3]}** interface — a regime previously accessible only in laboratory settings — {idea_name} captures signals that encode the pre-conscious genesis of {problems[0]}. This isn't wellness technology dressed in better packaging; it's a genuinely new sensing modality applied to the oldest human challenge: understanding ourselves.

## Elevator Pitch

{idea_name}: laboratory-grade {tech[0]} sensing in a {form}, making the invisible architecture of {problems[0]} visible — and addressable — for the first time.
"""

    elif template == "philosophical":
        content = f"""## {idea_name}

## Overview

In the tradition of *{philosophy}*, {idea_name} begins with a radical premise: {problems[0]} is not a malfunction but a form of intelligence — the body's way of {acts[0]}ing information that the conscious mind has yet to process. This **{quality}** {archetype} doesn't silence that intelligence; it {acts[1]} it into a language both body and mind can share.

## The Problem It Solves

The modern approach to {problems[0]} is fundamentally Cartesian — it treats the mind as a pilot and the body as a vehicle, and assumes that discomfort signals a mechanical failure requiring repair. But the *{life_force}* tradition tells a different story: that vital energy flows through us in patterns that carry meaning, and that {problems[0]} occurs precisely when those patterns encounter blockages, contradictions, or unresolved tensions. {problems[1]} is not a separate problem but the same pattern expressing itself at a different scale.

What's missing isn't a better fix but a better framework — one that honors the **{tech[0]}** complexity of lived experience while still offering practical relief.

## How It Works

{idea_name} embodies the principle that understanding precedes intervention. The device — shaped like a {form}, crafted from {mats[0]} — operates in three modes:

**Listening Mode**: Through a {tech[1]} sensor array embedded in {mats[1]}, the system {acts[0]} the user's physiological patterns using {mechs[0]}. But rather than categorizing these patterns as "stressed" or "calm," it maps them as unique emotional topographies — landscapes with valleys, ridges, and rivers of sensation.

**Dialogue Mode**: When the system detects a pattern associated with {problems[0]}, it responds not with a correction but with a question — a carefully calibrated **{tech[2]}** stimulus delivered through {mats[2]} that {acts[2]} the user's attention toward the pattern itself. Inspired by *{philosophy}*, the intervention is designed to create awareness, not compliance.

**Integration Mode**: Over time, the {mechs[1]} core learns which patterns precede insight, creativity, or resolution — and which precede escalation. It gradually {acts[3]} the boundary between productive discomfort and genuine distress, helping the user develop what the *{life_force}* traditions call embodied wisdom.

## Why It's Brilliant

{idea_name} is one of the first technological artifacts to take ancient somatic traditions seriously as engineering specifications. The **{tech[1]} {mechs[0]}** system is rigorous enough for clinical validation, yet the interaction paradigm honors the irreducible mystery of human experience. It doesn't promise to eliminate {problems[0]} — it promises to make it meaningful.

## Elevator Pitch

{idea_name}: the {archetype} that asks what your {problems[0]} is trying to tell you — and helps you listen.
"""

    else:  # whimsical
        content = f"""## {idea_name}

## Overview

Picture this: a {form} that hums when you're about to make a terrible decision, glows when you're accidentally brilliant, and gently vibrates when you've been doing {problems[0]} for longer than is strictly advisable. {idea_name} is a **{quality}** {archetype} that treats the human condition with the seriousness it deserves — which is to say, not very much, but with tremendous affection.

## The Problem It Solves

{problems[0].capitalize()} is the common cold of the modern psyche — everyone gets it, nobody has cured it, and the remedies are either boring or suspicious. Meanwhile, {problems[1]} lurks in the background like a passive-aggressive coworker, making everything subtly worse. The real problem isn't that solutions don't exist — it's that existing solutions have the personality of a spreadsheet. {idea_name} takes a radically different approach: what if addressing {problems[0]} was actually... fun?

## How It Works

{idea_name} is built on what its creators (somewhat grandly) call the **{life_force.capitalize()} Protocol** — an engineering philosophy inspired by *{philosophy}* that prioritizes delight over efficiency and surprise over optimization.

The device uses a {tech[0]} sensor array hidden inside {mats[0]} to detect when {problems[0]} is creeping up. But instead of issuing stern warnings or suggesting breathing exercises, it responds with what can only be described as creative mischief:

- **The {tech[1].title()} Tickle**: A barely perceptible {tech[1]} sensation through {mats[1]} that feels like your favorite memory trying to get your attention
- **The {mechs[0].title()} Shuffle**: The device subtly {acts[0]} your ambient environment — shifting light, redirecting sound, introducing a {tech[2]} micro-pattern — creating tiny moments of wonder that interrupt the doom spiral
- **The {rng.choice(["Octopus", "Chameleon", "Firefly", "Pangolin", "Axolotl", "Tardigrade", "Platypus"])} Gambit**: When all else fails, the {mechs[1]} core generates a completely unexpected {tech[3]} experience — a micro-adventure calibrated to your specific brand of {problems[0]}

The whole thing runs on {mechs[2]} and is housed in {mats[2]}, because even the components should be interesting.

## Why It's Brilliant

Most wellness tech assumes you need to be fixed. {idea_name} assumes you need to be surprised. It's built on the counterintuitive but well-supported insight that {problems[0]} loses its grip the moment something genuinely interesting happens. By using **{tech[0]}** precision to deliver **{quality.split()[0]}** moments of delight, it achieves what meditation apps have been promising and failing to deliver since 2014.

Also, it looks like a {form}, which is objectively wonderful.

## Elevator Pitch

{idea_name}: because the cure for {problems[0]} isn't another app telling you to breathe — it's a {form} that {acts[1]} your day into an adventure.
"""

    return topic, content


def main():
    TOTAL = int(sys.argv[1]) if len(sys.argv) > 1 else 30000
    start_time = time.time()
    success = 0
    errors = 0

    print(f"\n{'='*60}")
    print(f"  OctoBot Bulk Idea Generator -- {TOTAL:,} ideas")
    print(f"{'='*60}\n")

    for i in range(TOTAL):
        try:
            topic, content = generate_idea(i)
            filename = tools.save_research(topic, content)
            scoring.update_knowledge_graph(filename, content)
            success += 1
        except Exception as e:
            errors += 1
            if errors <= 5:
                print(f"\n  [!] Error on idea {i}: {e}")

        # Progress every 50 ideas
        if (i + 1) % 50 == 0:
            elapsed = time.time() - start_time
            rate = (i + 1) / elapsed
            eta = (TOTAL - i - 1) / rate if rate > 0 else 0
            bar_len = 40
            filled = int(bar_len * (i + 1) / TOTAL)
            bar = '#' * filled + '-' * (bar_len - filled)
            pct = 100 * (i + 1) / TOTAL
            print(f"\r  [{bar}] {pct:5.1f}%  {i+1:>6,}/{TOTAL:,}  "
                  f"ok={success:,} err={errors}  "
                  f"{rate:.0f}/s  ETA {eta:.0f}s   ", end="", flush=True)

        if (i + 1) % 5000 == 0:
            elapsed = time.time() - start_time
            graph = scoring.get_knowledge_graph()
            nodes = graph.get("nodes", [])
            print(f"\n  -- Milestone: {i+1:,} ideas | {elapsed:.0f}s | "
                  f"{len(nodes):,} concepts in graph")

    elapsed = time.time() - start_time
    print(f"\n\n{'='*60}")
    print(f"  DONE -- {success:,} ideas saved, {errors} errors")
    print(f"  Time: {elapsed:.1f}s ({success/max(1,elapsed):.0f} ideas/sec)")
    print(f"{'='*60}\n")

    graph = scoring.get_knowledge_graph()
    nodes = graph.get("nodes", [])
    fc = scoring._graph_cache.get("file_concepts", {}) if scoring._graph_cache else {}
    print(f"  Knowledge graph: {len(nodes):,} concept nodes")
    print(f"  Files in graph:  {len(fc):,}")
    print()


if __name__ == "__main__":
    main()
