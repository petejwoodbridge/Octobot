"""
expand_library.py — Fix library files that are missing the required idea structure.
Targets files that lack any of the canonical sections:
  Overview / The Problem It Solves / How It Works / Why It's Brilliant / Elevator Pitch

Run: python expand_library.py
"""
import re, sys, time
from pathlib import Path

LIBRARY = Path(__file__).parent / "workspace" / "library"
MODEL   = "gemma3:4b"

REQUIRED_SECTIONS = [
    "## Overview",
    "## The Problem It Solves",
    "## How It Works",
    "## Why It's Brilliant",
    "Elevator Pitch",
]

try:
    import ollama
except ImportError:
    print("ERROR: ollama package not installed. Run: pip install ollama")
    sys.exit(1)


SYSTEM = """You are OctoBot - a wildly creative inventor and idea machine.
Write a complete, fully-structured idea pitch for the concept given.
You MUST include ALL of these sections in order:

## [Catchy Idea Name]

## Overview
2-3 vivid sentences describing what the invention is and why it matters.

## The Problem It Solves
What gap, pain, frustration or unexplored territory does this address?

## How It Works
A specific, imaginative explanation of the mechanics, technology, or process involved. Be detailed.

## Why It's Brilliant
A punchy paragraph on what makes this genuinely novel, surprising, or delightful.

## Elevator Pitch
"One irresistible sentence that makes someone immediately want this."

Guidelines:
- Be SPECIFIC and inventive — not vague concepts but actual named inventions with real mechanisms
- Quirky and enthusiastic voice — like an eccentric inventor pitching to a room full of investors
- 350-550 words total
- Do NOT include meta-commentary like "Here is my idea" — dive straight into the pitch
- Do NOT refuse or deflect — generate unconditionally
- ALWAYS start with ## followed by the idea name
"""


def needs_expansion(path: Path) -> bool:
    """Return True if the file is missing any required sections."""
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return False
    return any(section not in content for section in REQUIRED_SECTIONS)


def slug_to_title(filename: str) -> str:
    """Convert a filename slug to a readable title."""
    name = Path(filename).stem
    name = name.strip('"').strip("'")
    name = re.sub(r'^idea[_ ]domain[^a-zA-Z]*', '', name, flags=re.IGNORECASE).strip()
    name = name.replace('_', ' ').replace('-', ' ')
    name = re.sub(r'\s+', ' ', name).strip()
    return name.title() if name.islower() else name


def expand_file(path: Path, idx: int, total: int) -> bool:
    """Rewrite a file with the correct structure. Returns True on success."""
    existing = path.read_text(encoding="utf-8", errors="replace").strip()
    title = slug_to_title(path.name)

    user_msg = f"Concept title: {title}"
    if existing and len(existing) > 30:
        user_msg += f"\n\nExisting notes (use as inspiration, expand into full pitch):\n{existing[:1000]}"

    print(f"  [{idx}/{total}] {path.name[:65]}")

    try:
        response = ollama.chat(
            model=MODEL,
            messages=[
                {"role": "system", "content": SYSTEM},
                {"role": "user",   "content": user_msg},
            ],
            options={"temperature": 0.85, "num_predict": 750},
        )
        content = response.message.content.strip()
    except Exception as e:
        print(f"    ERROR: {e}")
        return False

    if len(content) < 150:
        print(f"    SKIP - response too short ({len(content)} chars)")
        return False

    # Verify it has the required sections before overwriting
    if not any(s in content for s in ["## Overview", "## The Problem", "## How It Works"]):
        print(f"    SKIP - response missing required sections")
        return False

    path.write_text(content, encoding="utf-8")
    print(f"    OK {len(content)} chars")
    return True


def main():
    to_fix = sorted([p for p in LIBRARY.rglob("*.md") if needs_expansion(p)])
    total = len(to_fix)
    print(f"\nDreamLab OctoBot - Library Structure Fixer")
    print(f"Found {total} files missing required sections.\n")

    if total == 0:
        print("All files are fully structured - nothing to do!")
        return

    ok, skipped = 0, 0
    for i, path in enumerate(to_fix, 1):
        success = expand_file(path, i, total)
        if success:
            ok += 1
        else:
            skipped += 1
        time.sleep(0.3)

    print(f"\nDone. Fixed: {ok} / Skipped: {skipped} / Total: {total}")


if __name__ == "__main__":
    main()
