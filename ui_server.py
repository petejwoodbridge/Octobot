"""
ui_server.py — OctoBot Lightweight Web Server
================================================
A Flask-based web server that serves the game interface and exposes
JSON API endpoints for the frontend to poll.

Endpoints
---------
GET  /              → Game HTML page (static/index.html)
GET  /api/state     → Current game state (action, stats, log, thought)
POST /api/chat      → Send a chat message, get OctoBot's response
GET  /api/library   → List library files
GET  /api/library/<path>  → Read a library file
GET  /api/journal   → Read the journal
POST /api/cycle     → Trigger one game cycle manually
GET  /api/score     → Knowledge score + library level
GET  /api/graph     → Knowledge graph (nodes + edges)
GET  /api/achievements → All achievement definitions + unlocked status
GET  /api/chains    → Research chains
GET  /api/discoveries → Discovery events
GET  /assets/<path> → Static asset files
"""

import json
import os
import time
from pathlib import Path

from flask import Flask, request, jsonify, send_from_directory, send_file

import agent
import tools
import memory as mem
import game_loop
import research
import scoring
import llm_provider

# ---------------------------------------------------------------------------
# Flask app
# ---------------------------------------------------------------------------

_BASE_DIR = Path(__file__).parent
_STATIC_DIR = _BASE_DIR / "static"
_ASSETS_DIR = _BASE_DIR / "assets"

app = Flask(__name__, static_folder=None)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16 MB upload limit


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    """Serve the main game interface."""
    return send_file(_STATIC_DIR / "index.html")


@app.route("/static/<path:filename>")
def static_files(filename):
    """Serve static files (CSS, JS, images)."""
    return send_from_directory(_STATIC_DIR, filename)


@app.route("/assets/<path:filename>")
def asset_files(filename):
    """Serve asset files (sprites, tiles)."""
    return send_from_directory(_ASSETS_DIR, filename)


# ---------------------------------------------------------------------------
# API — Game State
# ---------------------------------------------------------------------------

@app.route("/api/state")
def api_state():
    """Return the current game state as JSON for frontend polling."""
    stats = mem.get_game_stats()
    log_lines = list(game_loop.activity_log)[-30:]
    agent_log = list(agent.loop_log)[-20:]
    level_info = scoring.get_library_level()

    return jsonify({
        "action": game_loop.current_action,
        "status": game_loop.current_status,
        "thought": agent.last_thought[:200] if agent.last_thought else "",
        "last_action": agent.last_action or "idle",
        "stats": {
            "knowledge_score": stats.get("knowledge_score", 0),
            "knowledge_count": stats.get("knowledge_count", 0),
            "curiosity_level": stats.get("curiosity_level", 50),
            "comments_read": stats.get("comments_read", 0),
            "research_count": stats.get("research_count", 0),
            "total_cycles": stats.get("total_cycles", 0),
            "discoveries": stats.get("discoveries", 0),
            "cross_refs": stats.get("cross_refs", 0),
            "chains_completed": stats.get("chains_completed", 0),
        },
        "level": level_info,
        "log": log_lines + agent_log,
        "library_count": tools.get_knowledge_count(),
        "last_idea_topic": agent.last_research_topic or "",
        "loop_status": agent.loop_status or "",
    })


# ---------------------------------------------------------------------------
# API — Chat
# ---------------------------------------------------------------------------

@app.route("/api/chat", methods=["POST"])
def api_chat():
    """Handle a chat message from the player."""
    data = request.get_json(silent=True) or {}
    message = data.get("message", "").strip()
    if not message:
        return jsonify({"error": "Empty message"}), 400

    try:
        response = agent.chat(message)
        return jsonify({
            "response": response,
            "action": agent.last_action or "idle",
            "thought": agent.last_thought[:200] if agent.last_thought else "",
        })
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


# ---------------------------------------------------------------------------
# API — Library
# ---------------------------------------------------------------------------

@app.route("/api/library")
def api_library():
    """List library files."""
    files = [f for f in tools.list_files("library") if f.endswith(".md")]
    topics = research.list_researched_topics()
    return jsonify({"files": sorted(files), "topics": topics})


@app.route("/api/library/<path:filename>")
def api_library_file(filename):
    """Read a specific library file."""
    safe_name = filename.lstrip("/\\")
    if not safe_name.startswith("library/"):
        safe_name = "library/" + safe_name
    try:
        content = tools.read_file(safe_name)
        return jsonify({"filename": safe_name, "content": content})
    except FileNotFoundError:
        return jsonify({"error": "File not found"}), 404
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 403


# ---------------------------------------------------------------------------
# API — Journal
# ---------------------------------------------------------------------------

@app.route("/api/journal")
def api_journal():
    """Read OctoBot's journal."""
    content = tools.read_journal()
    return jsonify({"content": content})


# ---------------------------------------------------------------------------
# API — Score & Level
# ---------------------------------------------------------------------------

@app.route("/api/score")
def api_score():
    """Return knowledge score and library level info."""
    score = scoring.get_score()
    level = scoring.get_library_level(score)
    return jsonify({"score": score, "level": level})


# ---------------------------------------------------------------------------
# API — Knowledge Graph
# ---------------------------------------------------------------------------

_graph_resp_cache = None   # cached JSON-serialisable dict
_graph_resp_time  = 0      # time.time() of last computation
_graph_resp_ncount = 0     # node count at cache time (invalidation key)

@app.route("/api/graph")
def api_graph():
    """Return a filtered knowledge graph for visualization.
    Caches the result for 30s to avoid expensive recomputation."""
    global _graph_resp_cache, _graph_resp_time, _graph_resp_ncount

    max_nodes = request.args.get("max", 120, type=int)
    max_nodes = min(max_nodes, 2000)  # hard cap

    graph = scoring.get_knowledge_graph()
    all_nodes = graph.get("nodes", [])
    all_edges = graph.get("edges", [])
    now = time.time()

    # Return cache if fresh (same node count and < 30s old)
    if (_graph_resp_cache is not None
            and now - _graph_resp_time < 30
            and len(all_nodes) == _graph_resp_ncount):
        return jsonify(_graph_resp_cache)

    if len(all_nodes) <= max_nodes:
        # Cap edges to 5000 for response size — frontend draws 4000 max anyway
        edges_to_send = all_edges
        if len(edges_to_send) > 5000:
            degree = {}
            for e in edges_to_send:
                degree[e["from"]] = degree.get(e["from"], 0) + 1
                degree[e["to"]] = degree.get(e["to"], 0) + 1
            edges_to_send = sorted(edges_to_send, key=lambda e: degree.get(e["from"], 0) + degree.get(e["to"], 0), reverse=True)[:5000]
        result = {"nodes": all_nodes, "edges": edges_to_send,
                  "total_nodes": len(all_nodes), "total_edges": len(all_edges)}
    else:
        # Rank nodes by edge count (degree)
        degree = {}
        for e in all_edges:
            degree[e["from"]] = degree.get(e["from"], 0) + 1
            degree[e["to"]] = degree.get(e["to"], 0) + 1

        top = sorted(all_nodes, key=lambda n: degree.get(n, 0), reverse=True)[:max_nodes]
        top_set = set(top)
        filtered_edges = [e for e in all_edges if e["from"] in top_set and e["to"] in top_set]

        # Cap edges to 5000 — frontend only draws 4000 max anyway
        if len(filtered_edges) > 5000:
            # Keep edges connecting highest-degree nodes
            filtered_edges.sort(key=lambda e: degree.get(e["from"], 0) + degree.get(e["to"], 0), reverse=True)
            filtered_edges = filtered_edges[:5000]

        result = {"nodes": top, "edges": filtered_edges,
                  "total_nodes": len(all_nodes), "total_edges": len(all_edges)}

    _graph_resp_cache = result
    _graph_resp_time = now
    _graph_resp_ncount = len(all_nodes)
    return jsonify(result)


@app.route("/api/auto-messages")
def api_auto_messages():
    """Return autonomous messages for the chat feed.
    ?since=<index> returns only messages after that index."""
    since = request.args.get("since", 0, type=int)
    msgs = agent.autonomous_messages[since:]
    return jsonify({"messages": msgs, "next_index": len(agent.autonomous_messages)})


# ---------------------------------------------------------------------------
# API — Achievements
# ---------------------------------------------------------------------------

@app.route("/api/achievements")
def api_achievements():
    """Return all achievement definitions and which are unlocked."""
    all_defs = scoring.get_all_achievement_defs()
    unlocked = scoring.get_achievements()
    unlocked_ids = {a["id"] for a in unlocked}

    result = []
    for d in all_defs:
        result.append({
            "id": d["id"],
            "name": d["name"],
            "desc": d["desc"],
            "unlocked": d["id"] in unlocked_ids,
            "unlocked_at": next((a["unlocked_at"] for a in unlocked if a["id"] == d["id"]), None),
        })
    return jsonify({"achievements": result})


# ---------------------------------------------------------------------------
# API — Research Chains
# ---------------------------------------------------------------------------

@app.route("/api/chains")
def api_chains():
    """Return all research chains."""
    chains = scoring.get_all_chains()
    active = scoring.get_active_chains()
    return jsonify({
        "chains": chains,
        "active_count": len(active),
    })


# ---------------------------------------------------------------------------
# API — Discovery Events
# ---------------------------------------------------------------------------

@app.route("/api/discoveries")
def api_discoveries():
    """Return all discovery events."""
    discoveries = scoring.get_discoveries()
    return jsonify({"discoveries": discoveries})


# ---------------------------------------------------------------------------
# API — Manual cycle trigger
# ---------------------------------------------------------------------------

@app.route("/api/cycle", methods=["POST"])
def api_cycle():
    """Trigger one game cycle manually."""
    try:
        result = game_loop.run_game_cycle()
        return jsonify({"result": result})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


# ---------------------------------------------------------------------------
# API — Models (local Ollama)
# ---------------------------------------------------------------------------

@app.route("/api/models")
def api_models():
    """Return available local Ollama models and the currently selected one."""
    models = llm_provider.get_ollama_models()
    return jsonify({"models": models, "current": agent.MODEL})


@app.route("/api/models/select", methods=["POST"])
def api_models_select():
    """Switch the active Ollama model."""
    data = request.get_json(silent=True) or {}
    model = data.get("model", "").strip()
    if not model:
        return jsonify({"error": "No model specified"}), 400
    agent.MODEL = model
    llm_provider.API_MODEL = model
    return jsonify({"ok": True, "model": model})


# ---------------------------------------------------------------------------
# API — File Upload
# ---------------------------------------------------------------------------

ALLOWED_EXTENSIONS = {".pdf", ".md", ".txt", ".csv", ".json"}
MAX_UPLOAD_SIZE = 10 * 1024 * 1024  # 10 MB


def _extract_text(filepath: Path, ext: str) -> str:
    """Extract plain text from an uploaded file."""
    if ext == ".pdf":
        try:
            from pypdf import PdfReader
            reader = PdfReader(str(filepath))
            pages = [page.extract_text() or "" for page in reader.pages]
            return "\n\n".join(pages)
        except Exception as exc:
            return f"[PDF extraction failed: {exc}]"
    else:
        return filepath.read_text(encoding="utf-8", errors="replace")


@app.route("/api/upload", methods=["POST"])
def api_upload():
    """Upload a file, extract text, return it for chat context injection."""
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    f = request.files["file"]
    if not f.filename:
        return jsonify({"error": "Empty filename"}), 400

    ext = os.path.splitext(f.filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        return jsonify({"error": f"Unsupported file type: {ext}"}), 400

    # Use mkstemp for reliable cross-platform temp files (avoids Windows locking)
    import tempfile
    fd, tmp_path_str = tempfile.mkstemp(suffix=ext)
    tmp_path = Path(tmp_path_str)
    try:
        with os.fdopen(fd, 'wb') as tmp_f:
            f.save(tmp_f)
        text = _extract_text(tmp_path, ext)
        if len(text) > 50000:
            text = text[:50000] + "\n\n[…truncated at 50 000 chars]"
        return jsonify({
            "filename": f.filename,
            "text": text,
            "chars": len(text),
        })
    except Exception as exc:
        return jsonify({"error": f"Processing failed: {exc}"}), 500
    finally:
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Launch
# ---------------------------------------------------------------------------

def launch(port: int = 7860) -> None:
    """Start the Flask web server."""
    print(f"\n  🐙 OctoBot Game Server running at http://localhost:{port}\n")
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
