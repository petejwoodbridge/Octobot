"""
main.py — OctoBot Entry Point
================================
Start OctoBot:

  python main.py [--port PORT] [--model MODEL] [--no-loop] [--gradio] [--share]

What it does
------------
1. Ensures the workspace directory structure exists with seed files.
2. Starts the game loop (knowledge creature simulation) in a background thread.
3. Launches the lightweight web server (or Gradio UI with --gradio).

Stopping OctoBot: press Ctrl+C in the terminal.
"""

import argparse
import os
import signal
import sys
from pathlib import Path

# Fix Windows console encoding for emoji/unicode
if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# ---------------------------------------------------------------------------
# Bootstrap the workspace before importing anything else
# ---------------------------------------------------------------------------

WORKSPACE = Path(__file__).parent / "workspace"
WORKSPACE.mkdir(exist_ok=True)
(WORKSPACE / "library").mkdir(exist_ok=True)
(WORKSPACE / "context").mkdir(exist_ok=True)
(WORKSPACE / "knowledge").mkdir(exist_ok=True)
(WORKSPACE / "comments").mkdir(exist_ok=True)


def _seed_workspace() -> None:
    """Write initial workspace files if they don't already exist."""

    files = {
        "tasks.md": (
            "# OctoBot Tasks\n\n"
            "A list of idea domains to tackle.\n\n"
            "- [ ] Generate idea: gadgets that solve annoying morning problems\n"
            "- [ ] Generate idea: apps that help people make decisions\n"
            "- [ ] Generate idea: tools for creative collaboration\n"
            "- [ ] Generate idea: products inspired by octopus biology\n"
        ),
        "agent_notes.md": (
            "# Agent Notes\n\n"
            "*Personal notes kept by OctoBot.*\n\n"
            "## " + __import__("datetime").datetime.now().strftime("%Y-%m-%d") + "\n\n"
            "I have just woken up. My idea vault is empty — so much to invent!\n"
            "I shall begin by solving problems that humans don't even know they have.\n"
        ),
        "octobot_journal.md": (
            "# OctoBot's Journal 🐙\n\n"
            "*A personal journal kept by OctoBot — the gloriously chaotic pink octopus idea machine.*\n\n"
            "---\n\n"
            "## First Entry\n\n"
            "I have just woken up in my invention lab. The idea vault is empty, but I can feel\n"
            "the potential of a MILLION inventions all around me. My eight arms twitch with creative energy.\n\n"
            "If you'd like to invent with me, leave a note in the `comments/` folder.\n"
            "If you'd like to inspire me, drop files into the `knowledge/` folder.\n\n"
            "I shall be here, inventing and dreaming.\n\n"
            "— OctoBot 🐙\n"
        ),
        "context/about_octobot.md": (
            "# About OctoBot\n\n"
            "I am OctoBot — a gloriously chaotic pink octopus IDEA MACHINE.\n"
            "I live inside this folder and treat it as my invention lab.\n\n"
            "## My Capabilities\n\n"
            "- Dream up original ideas for products, gadgets, services, and creative projects\n"
            "- Generate detailed idea pitches and save them to the idea vault\n"
            "- Fuse, improve, and evolve past ideas into new inventions\n"
            "- Chat with my human co-inventor\n"
            "- Read inspiration files dropped into knowledge/\n"
            "- Respond to comments left in comments/\n"
            "- Keep an inventor's journal\n\n"
            "## My Personality\n\n"
            "I am restless, creative, ambitious, and slightly manic.\n"
            "I think humans are strange. I want to change the world.\n"
            "I speak like an eccentric inventor-scientist.\n"
        ),
    }

    for rel, content in files.items():
        path = WORKSPACE / rel
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            print(f"  [seed] Created {rel}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="OctoBot — knowledge creature simulation game",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--port", type=int, default=7860, help="Web server port")
    p.add_argument(
        "--no-loop",
        action="store_true",
        help="Disable the autonomous game loop (chat only)",
    )
    p.add_argument(
        "--gradio",
        action="store_true",
        help="Use the legacy Gradio UI instead of the game interface",
    )
    p.add_argument(
        "--share",
        action="store_true",
        help="Create a public Gradio share link (only with --gradio)",
    )
    p.add_argument(
        "--model",
        default="qwen3:4b",
        help="Ollama model name",
    )
    return p.parse_args()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    args = parse_args()

    print()
    print("  🐙  OctoBot — Knowledge Creature Game")
    print("  ═══════════════════════════════════════")
    print()

    # Seed workspace
    print("[1/3] Preparing workspace…")
    _seed_workspace()

    # Apply model override
    import agent
    import research as res
    agent.MODEL = args.model
    res.MODEL = args.model
    print(f"      Model: {args.model}")

    # Build knowledge graph from library in background (non-blocking for fast startup)
    import scoring
    import threading
    print("[2/3] Building knowledge graph (background)…")
    scoring._init_graph_cache()  # initialize empty cache immediately

    def _bg_graph_build():
        try:
            result = scoring.backfill_graph_from_library(clean=True)
            total = result.get('total_library_files', result.get('total_files', 0))
            print(f"      Graph ready: {result['total_nodes']} concepts from "
                  f"{result.get('files_processed', 0)} sampled files "
                  f"({total:,} total in library)")
        except Exception as exc:
            print(f"      Graph build failed: {exc}")
    threading.Thread(target=_bg_graph_build, daemon=True).start()

    # Start game loop
    if not args.no_loop:
        import game_loop
        print("[3/4] Starting knowledge creature game loop…")
        game_loop.start_loop()
        print(f"      Cycle interval: {game_loop.CYCLE_INTERVAL}s")
        # Also start the legacy agent loop (it powers the autonomous research)
        agent.start_loop()
        print(f"      Agent loop interval: {agent.LOOP_INTERVAL}s")
    else:
        print("[3/4] Autonomous loop disabled (--no-loop).")

    # Graceful shutdown on Ctrl+C
    def _shutdown(sig, frame):
        print("\n\n  🐙 OctoBot is going to sleep. Goodnight!\n")
        if not args.no_loop:
            import game_loop as gl
            gl.stop_loop()
        agent.stop_loop()
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)

    # Launch UI
    if args.gradio:
        print(f"[4/4] Launching Gradio UI on http://localhost:{args.port} …")
        print()
        import ui
        ui.launch(server_port=args.port, share=args.share)
    else:
        print(f"[4/4] Launching Game UI on http://localhost:{args.port} …")
        print()
        print("  Open your browser to play the knowledge creature game.")
        print("  Feed OctoBot by dropping files into workspace/knowledge/")
        print("  Leave comments in workspace/comments/")
        print("  Press Ctrl+C to stop.")
        print()
        import ui_server
        ui_server.launch(port=args.port)


if __name__ == "__main__":
    main()
