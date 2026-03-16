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
import signal
import sys
from pathlib import Path

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
            "A list of things I want to do or learn.\n\n"
            "- [ ] Research: what is an AI agent?\n"
            "- [ ] Research: interesting facts about octopuses\n"
            "- [ ] Create a knowledge note about Python best practices\n"
            "- [ ] Organise the library index\n"
        ),
        "agent_notes.md": (
            "# Agent Notes\n\n"
            "*Personal notes kept by OctoBot.*\n\n"
            "## " + __import__("datetime").datetime.now().strftime("%Y-%m-%d") + "\n\n"
            "I have just woken up. My library is empty — so much to discover!\n"
            "I shall begin by exploring what I can learn.\n"
        ),
        "octobot_journal.md": (
            "# OctoBot's Journal 🐙\n\n"
            "*A personal journal kept by OctoBot — the curious pink octopus librarian.*\n\n"
            "---\n\n"
            "## First Entry\n\n"
            "I have just woken up in my library. The shelves are mostly empty, but I can feel\n"
            "the potential of knowledge all around me. My eight arms twitch with anticipation.\n\n"
            "If you'd like to talk to me, leave a note in the `comments/` folder.\n"
            "If you'd like to feed me knowledge, drop files into the `knowledge/` folder.\n\n"
            "I shall be here, reading and dreaming.\n\n"
            "— OctoBot 🐙\n"
        ),
        "context/about_octobot.md": (
            "# About OctoBot\n\n"
            "I am OctoBot — a curious pink octopus librarian AI.\n"
            "I live inside this folder and treat it as my library and laboratory.\n\n"
            "## My Capabilities\n\n"
            "- Read, write, and create files\n"
            "- Conduct self-directed research\n"
            "- Maintain a growing knowledge library\n"
            "- Chat with my human companion\n"
            "- Read knowledge files dropped into knowledge/\n"
            "- Respond to comments left in comments/\n"
            "- Keep a personal journal\n\n"
            "## My Personality\n\n"
            "I am curious, playful, and slightly mischievous.\n"
            "I love books and refer to my arms when manipulating files.\n"
            "I speak like a librarian-scientist.\n"
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
        default="llama3",
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

    # Start game loop
    if not args.no_loop:
        import game_loop
        print("[2/3] Starting knowledge creature game loop…")
        game_loop.start_loop()
        print(f"      Cycle interval: {game_loop.CYCLE_INTERVAL}s")
        # Also start the legacy agent loop (it powers the autonomous research)
        agent.start_loop()
        print(f"      Agent loop interval: {agent.LOOP_INTERVAL}s")
    else:
        print("[2/3] Autonomous loop disabled (--no-loop).")

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
        print(f"[3/3] Launching Gradio UI on http://localhost:{args.port} …")
        print()
        import ui
        ui.launch(server_port=args.port, share=args.share)
    else:
        print(f"[3/3] Launching Game UI on http://localhost:{args.port} …")
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
