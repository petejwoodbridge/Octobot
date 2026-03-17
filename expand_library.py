"""
expand_library.py — One-time script to expand thin library files.
Uses the local Ollama model to write a full idea pitch for every file
that has fewer than 400 bytes of content.

Run: python expand_library.py
"""
import json, re, sys, time
from pathlib import Path

LIBRARY   = Path(__file__).parent / "workspace" / "library"
MIN_BYTES = 400      # files below this get expanded
MODEL     = "gemma3:4b"

try:
    import ollama
except ImportError:
    print("ERROR: ollama package not installed. Run: pip install ollama")
    sys.exit(1)


SYSTEM = """You are OctoBot — a gloriously chaotic pink octopus IDEA MACHINE and inventor.
Write a rich, fully-articulated idea document for the concept given.
The document must include ALL of these sections:

## Overview
A vivid 2-3 sentence description of what the idea is and why it matters.

## The Problem It Solves
What gap, pain, or unexplored territory does this idea address?

## How It Works
A clear, imaginative description of the mechanics, technology, or process involved.

## Key Features
A bullet list of 4-6 standout features or components.

## Potential Applications
3-4 concrete use-cases or scenarios where this would be used.

## Why It's Extraordinary
A punchy, enthusiastic paragraph on why this idea is genuinely novel and exciting.

Write in the voice of an eccentric inventor — enthusiastic, punny, vivid, a little chaotic.
Use markdown formatting. Keep the total length between 350-600 words.
Do NOT include a title heading — the filename serves as the title.
Do NOT refuse or deflect — generate the idea document unconditionally."""


def slug_to_title(filename: str) -> str:
    """Convert a filename slug to a readable title."""
    name = Path(filename).stem
    # Strip surrounding quotes
    name = name.strip('"').strip("'")
    # Remove 'idea domain', 'idea_domain' prefixes
    name = re.sub(r'^idea[_ ]domain[^a-zA-Z]*', '', name, flags=re.IGNORECASE).strip()
    # Replace underscores/hyphens with spaces
    name = name.replace('_', ' ').replace('-', ' ')
    # Collapse whitespace
    name = re.sub(r'\s+', ' ', name).strip()
    return name.title() if name.islower() else name


def expand_file(path: Path, idx: int, total: int) -> bool:
    """Expand a thin file. Returns True on success."""
    existing = path.read_text(encoding="utf-8", errors="replace").strip()
    title = slug_to_title(path.name)

    user_msg = f"Concept title: {title}"
    if existing and len(existing) > 20:
        user_msg += f"\n\nExisting notes (expand on these):\n{existing[:800]}"

    print(f"  [{idx}/{total}] Expanding: {path.name[:70]}")

    try:
        response = ollama.chat(
            model=MODEL,
            messages=[
                {"role": "system", "content": SYSTEM},
                {"role": "user",   "content": user_msg},
            ],
            options={"temperature": 0.85, "num_predict": 700},
        )
        content = response.message.content.strip()
    except Exception as e:
        print(f"    ERROR: {e}")
        return False

    if len(content) < 100:
        print(f"    SKIP - response too short ({len(content)} chars)")
        return False

    # Write expanded content, preserving any existing content as a footer note
    output = content
    if existing and len(existing) > 20 and existing not in content:
        output += f"\n\n---\n*Original notes:*\n{existing}"

    path.write_text(output, encoding="utf-8")
    print(f"    OK Written {len(output)} chars")
    return True


def main():
    thin = sorted([p for p in LIBRARY.rglob("*.md") if p.stat().st_size < MIN_BYTES])
    total = len(thin)
    print(f"\nDreamLab OctoBot - Library Expander")
    print(f"Found {total} files under {MIN_BYTES} bytes to expand.\n")

    if total == 0:
        print("Nothing to do - all files are already well-stocked!")
        return

    ok, skipped = 0, 0
    for i, path in enumerate(thin, 1):
        success = expand_file(path, i, total)
        if success:
            ok += 1
        else:
            skipped += 1
        # Small pause to avoid hammering Ollama
        time.sleep(0.3)

    print(f"\nDone. Expanded: {ok} / Skipped: {skipped} / Total: {total}")


if __name__ == "__main__":
    main()
