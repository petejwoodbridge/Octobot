"""
Watches expand_log.txt until the expander finishes, then commits and pushes.
Run: python push_when_done.py
"""
import subprocess, time, sys
from pathlib import Path

LOG  = Path(__file__).parent / "expand_log.txt"
REPO = Path(__file__).parent

print("Watching for expander to finish...")

while True:
    try:
        text = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             f"Get-Content -LiteralPath '{LOG}' -Raw -Encoding UTF8"],
            capture_output=True, text=True, timeout=8
        ).stdout
    except Exception:
        text = ""

    if "Done. Fixed:" in text or "Nothing to do" in text:
        print("Expander finished! Committing and pushing...")
        break

    # Show progress
    import re
    nums = re.findall(r"\[(\d+)/(\d+)\]", text)
    if nums:
        done, total = nums[-1]
        pct = int(done) / int(total) * 100
        print(f"  Progress: {done}/{total} ({pct:.1f}%) — waiting...", flush=True)

    time.sleep(30)

# Git add, commit, push
def run(cmd):
    r = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True)
    print(r.stdout)
    if r.returncode != 0:
        print("STDERR:", r.stderr)
    return r.returncode

run(["git", "add", "-A"])
rc = run(["git", "commit", "-m", "Fix structure of all library files - add required sections"])
if rc == 0:
    run(["git", "push"])
    print("Done - repo pushed!")
else:
    print("Nothing new to commit, or commit failed.")
