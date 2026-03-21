"""
generate_2000.py — Bulk idea generator for OctoBot
====================================================
Generates 2000 unique, richly detailed ideas influenced by the context library
and existing knowledge graph concepts. Uses the project's own save pipeline.

Usage:  python generate_2000.py
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

# Add project root to path so we can import project modules
sys.path.insert(0, str(Path(__file__).parent))

import tools
import scoring

# ---------------------------------------------------------------------------
# Vocabulary banks — drawn from context library & existing idea themes
# ---------------------------------------------------------------------------

# From "Ancient Life Forces and Otherworlds" context document
LIFE_FORCES = [
    "Awen", "Teotl", "Qi", "Prana", "Mana", "Pneuma", "Sunyata", "Mauri",
    "Tapu", "Logos", "Lung", "Tigle", "Chakra", "Songlines", "Everywhen",
    "Dreamtime", "Alcheringa", "Jukurrpa", "Nadi", "Meridian",
]

PHILOSOPHICAL_CONCEPTS = [
    "agonistic inamic unity", "constitutional monism", "dependent origination",
    "non-dual awareness", "sacred breath", "divine illumination",
    "cosmic consciousness", "tensility of being", "subtle body architecture",
    "shamanic transformation", "poetic frenzy", "karmic momentum",
    "ecological stewardship", "enchanted cosmos", "flowing spirit",
    "primordial energy", "vital life force", "spiritual resonance",
    "ontological indeterminacy", "relational authority",
]

# Technical domains drawn from existing library patterns
TECH_DOMAINS = [
    "bio-acoustic", "neuro-sensory", "micro-fluidic", "chrono-spatial",
    "geo-resonant", "bioluminescent", "haptic-feedback", "electro-dermal",
    "magneto-therapeutic", "sono-luminescent", "thermo-adaptive",
    "piezo-electric", "opto-genetic", "myco-electric", "quantum-entangled",
    "nano-fibrous", "cryo-kinetic", "hydro-dynamic", "aero-elastic",
    "ferro-fluid", "plasma-ionic", "photo-catalytic", "bio-mimetic",
    "neuro-plastic", "psycho-acoustic", "mechano-transductive",
    "chemo-luminescent", "radio-isotopic", "gyro-stabilized", "bio-photonic",
]

# Problem domains / human needs
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
]

# Invention archetypes
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
]

# Materials and mechanisms
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
]

# Catchy name components
NAME_PREFIXES = [
    "Chrono", "Echo", "Aura", "Soma", "Lyra", "Nova", "Flux", "Vox",
    "Lumen", "Cipher", "Helix", "Nexus", "Pulse", "Drift", "Bloom",
    "Ember", "Frost", "Tide", "Whisper", "Spark", "Phantom", "Reverie",
    "Nimbus", "Zenith", "Horizon", "Cascade", "Prism", "Muse", "Oracle",
    "Meridian", "Aurora", "Tessera", "Chimera", "Nebula", "Quartz",
    "Sable", "Coral", "Fathom", "Zephyr", "Vesper", "Mirage", "Arbor",
    "Crucible", "Pendulum", "Lattice", "Alchemy", "Symbiont", "Catalyst",
    "Resonance", "Entropy", "Kinesis", "Morphe", "Mythos", "Pneuma",
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
]

# Elevator pitch templates
PITCH_TEMPLATES = [
    "Imagine {archetype} that {action} — {punchline}.",
    "It's {comparison}, but for {domain} — and it actually works.",
    "What if your {object} could {ability}? {name} makes it happen.",
    "{name}: because {problem} shouldn't require {old_solution}.",
    "One part {thing1}, one part {thing2}, zero parts {bad_thing} — that's {name}.",
    "The world's first {archetype} that {unique_action}, powered by {tech}.",
    "{name} turns {input} into {output} — no {requirement} needed.",
    "Finally, {archetype} that understands {domain} better than you do.",
    "Why suffer {problem} when {name} can {solution} in under {time}?",
    "Part {thing1}, part {thing2}, entirely {quality} — meet {name}.",
]

# Action verbs for descriptions
ACTIONS = [
    "detects", "amplifies", "translates", "harmonizes", "crystallizes",
    "dissolves", "reconfigures", "weaves", "distills", "resonates with",
    "anticipates", "metabolizes", "cultivates", "channels", "refracts",
    "modulates", "synthesizes", "attenuates", "calibrates", "orchestrates",
    "transforms", "maps", "navigates", "sculpts", "ferments",
]

# Qualities and adjectives
QUALITIES = [
    "sublimely intuitive", "deceptively simple", "hauntingly beautiful",
    "absurdly practical", "quietly revolutionary", "elegantly chaotic",
    "profoundly personal", "delightfully weird", "unexpectedly soothing",
    "fiercely gentle", "impossibly precise", "beautifully unpredictable",
    "stubbornly optimistic", "gloriously unnecessary", "tenderly ruthless",
]


def _rng_seed(i: int) -> random.Random:
    """Deterministic but varied RNG per idea index."""
    return random.Random(hashlib.md5(f"octobot-idea-{i}".encode()).hexdigest())


def _pick(rng: random.Random, lst: list, n: int = 1):
    """Pick n unique items from a list."""
    return rng.sample(lst, min(n, len(lst)))


def generate_idea(idx: int) -> tuple[str, str]:
    """Generate a single idea. Returns (topic_slug, markdown_content)."""
    rng = _rng_seed(idx)

    # Pick components
    prefix = rng.choice(NAME_PREFIXES)
    suffix = rng.choice(NAME_SUFFIXES)
    idea_name = f"The {prefix}{suffix}"
    # Occasionally use two-word names
    if rng.random() < 0.3:
        idea_name = f"{prefix} {suffix}"
    if rng.random() < 0.2:
        idea_name = f"Project {prefix}"

    archetype = rng.choice(ARCHETYPES)
    problems = _pick(rng, PROBLEM_DOMAINS, 2)
    tech_terms = _pick(rng, TECH_DOMAINS, 3)
    materials = _pick(rng, MATERIALS, 2)
    mechanisms = _pick(rng, MECHANISMS, 2)
    life_force = rng.choice(LIFE_FORCES)
    philosophy = rng.choice(PHILOSOPHICAL_CONCEPTS)
    actions = _pick(rng, ACTIONS, 3)
    quality = rng.choice(QUALITIES)

    # Build the topic slug
    topic = f"{idea_name} — {archetype} for {problems[0]}"

    # Build content
    content = f"""## {idea_name}

## Overview

{idea_name} is a **{quality}** {archetype} that {actions[0]} the invisible patterns of {problems[0]} and {actions[1]} them into tangible experiences of relief and wonder. Drawing on the ancient concept of *{life_force}* and the principle of *{philosophy}*, it creates a bridge between the measurable and the felt — a device that doesn't just solve a problem but transforms the relationship between a person and their inner landscape.

## The Problem It Solves

{problems[0].capitalize()} affects millions, yet most solutions treat symptoms rather than causes. Existing approaches rely on rigid protocols that ignore the **{tech_terms[0]}** dimension of human experience. Meanwhile, {problems[1]} compounds the issue, creating feedback loops that conventional tools cannot break. People need something that meets them where they are — not a prescription, but a living, adaptive presence that understands the rhythms of their specific struggle.

## How It Works

At its core, {idea_name} employs a **{tech_terms[1]} {mechanisms[0]}** system embedded within a matrix of {materials[0]}. The device continuously monitors subtle physiological signals — galvanic skin response, micro-expressions, respiratory cadence, and **{tech_terms[2]}** fluctuations — feeding them into a {mechanisms[1]} engine that builds an evolving model of the user's emotional topology.

When the system detects the onset of {problems[0]}, it activates a layered response protocol:

1. **Immediate Layer**: A gentle {tech_terms[0]} pulse delivered through {materials[1]}, calibrated to the user's current arousal state
2. **Adaptive Layer**: The {mechanisms[0]} module adjusts environmental parameters — light spectrum, ambient sound frequency, and subtle haptic patterns — creating a personalized micro-environment
3. **Deep Layer**: Over time, the system learns to {actions[2]} the user's patterns before conscious awareness, offering preemptive interventions inspired by the *{life_force}* principle of flowing energy through natural channels

The entire system is housed in a form factor reminiscent of a {rng.choice(["river stone", "nautilus shell", "seed pod", "coral fragment", "obsidian pebble", "amber droplet", "lotus bud", "geode cross-section"])}, designed to be held, worn, or placed in a personal space.

## Why It's Brilliant

What makes {idea_name} extraordinary is its refusal to separate the technical from the poetic. The **{tech_terms[1]}** sensing array doesn't just measure — it listens. The {mechanisms[1]} engine doesn't just compute — it composes. Every intervention is simultaneously a scientific response and an aesthetic experience, honoring the ancient insight that healing and beauty are inseparable.

The system becomes more attuned over time, developing what its creators call a "**Sympathetic Resonance Profile**" — a living map of the user's emotional architecture that grows richer with every interaction. Unlike clinical tools that flatten experience into data points, {idea_name} preserves the texture and complexity of human feeling while still providing measurable outcomes.

## Elevator Pitch

{idea_name} is the world's first {archetype} that turns {problems[0]} into a doorway for self-discovery — part {life_force.lower()}-channel, part {tech_terms[0]} intelligence, entirely {quality.split()[-1]}.
"""

    return topic, content


def main():
    TOTAL = 2000
    start_time = time.time()
    success = 0
    errors = 0

    print(f"\n{'='*60}")
    print(f"  OctoBot Bulk Idea Generator — {TOTAL} ideas")
    print(f"{'='*60}\n")

    for i in range(TOTAL):
        try:
            topic, content = generate_idea(i)

            # Save through the project pipeline
            filename = tools.save_research(topic, content)

            # Update knowledge graph
            scoring.update_knowledge_graph(filename, content)

            success += 1

            # Progress display
            if (i + 1) % 10 == 0:
                elapsed = time.time() - start_time
                rate = (i + 1) / elapsed
                eta = (TOTAL - i - 1) / rate if rate > 0 else 0
                bar_len = 40
                filled = int(bar_len * (i + 1) / TOTAL)
                bar = '█' * filled + '░' * (bar_len - filled)
                print(f"\r  [{bar}] {i+1}/{TOTAL}  "
                      f"({success} saved, {errors} errors)  "
                      f"{rate:.1f}/s  ETA {eta:.0f}s", end="", flush=True)

            if (i + 1) % 200 == 0:
                elapsed = time.time() - start_time
                print(f"\n  ✨ Milestone: {i+1} ideas generated in {elapsed:.1f}s")

        except Exception as e:
            errors += 1
            if errors <= 5:
                print(f"\n  ⚠ Error on idea {i}: {e}")

    elapsed = time.time() - start_time
    print(f"\n\n{'='*60}")
    print(f"  ✅ DONE — {success} ideas saved, {errors} errors")
    print(f"  ⏱  Total time: {elapsed:.1f}s ({success/elapsed:.1f} ideas/sec)")
    print(f"{'='*60}\n")

    # Show graph stats
    graph = scoring.get_knowledge_graph()
    nodes = graph.get("nodes", [])
    print(f"  📊 Knowledge graph: {len(nodes)} concept nodes")
    fc = scoring._graph_cache.get("file_concepts", {}) if scoring._graph_cache else {}
    print(f"  📁 Files in graph: {len(fc)}")
    print()


if __name__ == "__main__":
    main()
