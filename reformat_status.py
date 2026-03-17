"""
reformat_status.py — Check library reformat progress
=====================================================
Usage:
    python reformat_status.py          Show progress
    python reformat_status.py --run    Reformat next batch (50 files via LLM)
    python reformat_status.py --all    Reformat ALL remaining files via LLM
"""

import sys
import os
import time

# Fix Windows console encoding for emoji/unicode
if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

import tools
import research

def get_stats():
    files = [f for f in tools.list_files("library") if f.endswith(".md")]
    total = len(files)
    good = 0
    bad_local = 0
    bad_llm = 0
    empty = 0

    for f in files:
        try:
            c = tools.read_file(f)
            stripped = c.strip().strip('"').strip('\u201c').strip('\u201d').strip()
            if len(stripped) < 50:
                empty += 1
            elif research._is_well_structured(c):
                good += 1
            elif "\n## " in c or c.startswith("## ") or (c.startswith("# ") and "## " in c):
                bad_local += 1
            else:
                bad_llm += 1
        except Exception:
            empty += 1

    return total, good, bad_local, bad_llm, empty


def bar(done, total, width=40):
    pct = done / total if total else 0
    filled = int(width * pct)
    return f"[{'█' * filled}{'░' * (width - filled)}] {done}/{total} ({pct:.0%})"


def show():
    total, good, bad_local, bad_llm, empty = get_stats()
    structured = good
    remaining = bad_local + bad_llm

    print()
    print("  🐙  OctoBot Library Reformat Status")
    print("  ════════════════════════════════════")
    print()
    print(f"  Total files:       {total}")
    print(f"  Well-structured:   {bar(structured, total)}")
    print(f"  Needs local fix:   {bad_local}")
    print(f"  Needs LLM fix:     {bad_llm}")
    print(f"  Empty/tiny:        {empty}")
    print()

    if remaining == 0:
        print("  ✅ All ideas are properly structured!")
    else:
        print(f"  📝 {remaining} file(s) still need reformatting")
        print()
        print("  Run:  python reformat_status.py --run    (next 50 via LLM)")
        print("  Run:  python reformat_status.py --all    (all remaining)")
    print()


def run_batch(batch_size):
    total, good, _, bad_llm, _ = get_stats()
    target = bad_llm if batch_size == 0 else min(batch_size, bad_llm)

    if target == 0:
        print("\n  ✅ Nothing to reformat!\n")
        return

    print(f"\n  🐙 Reformatting up to {target} files using Ollama...\n")

    files = [f for f in tools.list_files("library") if f.endswith(".md")]
    done = 0
    failed = 0
    start = time.time()

    for f in files:
        if done >= target:
            break
        try:
            c = tools.read_file(f)
        except Exception:
            continue

        if research._is_well_structured(c):
            continue

        stripped = c.strip().strip('"').strip('\u201c').strip('\u201d').strip()
        if len(stripped) < 50:
            continue

        title = research._title_from_filename(f)
        elapsed = time.time() - start
        rate = done / elapsed if elapsed > 0 and done > 0 else 0
        eta = f" | ~{int((target - done) / rate)}s left" if rate > 0 else ""

        print(f"  [{done + 1}/{target}] {title[:50]}...{eta}", end="", flush=True)

        # Try local first
        if "\n## " in c or c.startswith("## ") or (c.startswith("# ") and "## " in c):
            result = research._local_reformat_with_headings(title, c)
            if result:
                tools.write_file(f, result)
                done += 1
                print(" ✓ (local)")
                continue

        # LLM reformat
        ok = research._llm_reformat(f, title, stripped)
        if ok:
            done += 1
            print(" ✓")
        else:
            failed += 1
            print(" ✗")

    elapsed = time.time() - start
    print()
    print(f"  Done: {done} reformatted, {failed} failed, {elapsed:.0f}s elapsed")

    # Show updated stats
    show()


if __name__ == "__main__":
    if "--run" in sys.argv:
        run_batch(50)
    elif "--all" in sys.argv:
        run_batch(0)
    else:
        show()
