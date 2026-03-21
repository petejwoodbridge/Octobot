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
    """Serve the main game interface (no-cache to ensure fresh JS)."""
    resp = send_file(_STATIC_DIR / "index.html")
    resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    resp.headers['Pragma'] = 'no-cache'
    return resp


@app.route("/loading")
def loading():
    """Loading screen shown while server starts up."""
    return send_file(_STATIC_DIR / "loading.html")


@app.route("/api/ping")
def api_ping():
    """Lightweight health check — instant response."""
    return "ok"


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

_state_lib_count = 0
_state_lib_time = 0

@app.route("/api/state")
def api_state():
    """Return the current game state as JSON for frontend polling."""
    global _state_lib_count, _state_lib_time
    stats = mem.get_game_stats()
    log_lines = list(game_loop.activity_log)[-30:]
    agent_log = list(agent.loop_log)[-20:]

    # Cache library count for 15s — update time first to prevent concurrent rescans
    now = time.time()
    if now - _state_lib_time > 15:
        _state_lib_time = now
        _state_lib_count = tools.get_knowledge_count()

    # Use real library count if stats haven't synced yet
    lib_count = _state_lib_count
    research_count = max(stats.get("research_count", 0), lib_count)
    knowledge_count = max(stats.get("knowledge_count", 0), lib_count)
    score = stats.get("knowledge_score", 0)
    level_info = scoring.get_library_level(max(score, lib_count * 5))

    return jsonify({
        "action": game_loop.current_action,
        "status": game_loop.current_status,
        "thought": agent.last_thought[:200] if agent.last_thought else "",
        "last_action": agent.last_action or "idle",
        "stats": {
            "knowledge_score": max(score, lib_count * 5),
            "knowledge_count": knowledge_count,
            "curiosity_level": stats.get("curiosity_level", 50),
            "comments_read": stats.get("comments_read", 0),
            "research_count": research_count,
            "total_cycles": stats.get("total_cycles", 0),
            "discoveries": stats.get("discoveries", 0),
            "cross_refs": stats.get("cross_refs", 0),
            "chains_completed": stats.get("chains_completed", 0),
        },
        "level": level_info,
        "log": log_lines + agent_log,
        "library_count": lib_count,
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

_lib_cache = None
_lib_cache_time = 0
_lib_cache_json = None

_lib_scan_running = False

def _scan_library_bg():
    """Background scan of library files sorted by mtime (newest first).
    For very large libraries, does a fast scan (no mtime) and sorts by
    directory/filename instead — batch dirs are numbered so this approximates
    newest-first without expensive stat() calls on 1M+ files."""
    global _lib_cache, _lib_cache_time, _lib_scan_running
    _lib_scan_running = True
    try:
        lib_root = tools.LIBRARY_DIR.resolve()
        ws_root = tools.WORKSPACE_ROOT.resolve()
        all_files = []
        for root, _dirs, fnames in os.walk(lib_root):
            for fn in fnames:
                if fn.endswith(".md"):
                    full = os.path.join(root, fn)
                    rel = os.path.relpath(full, ws_root).replace("\\", "/")
                    all_files.append(rel)

        total = len(all_files)

        if total > 10000:
            # For huge libraries: sort by path descending (batch_0999 > batch_0000)
            # This gives newest-first without expensive stat() calls
            all_files.sort(reverse=True)
        else:
            # For smaller libraries: sort by mtime (accurate newest-first)
            def _mtime(rel):
                try:
                    return os.path.getmtime(os.path.join(str(ws_root), rel.replace("/", os.sep)))
                except OSError:
                    return 0
            all_files.sort(key=_mtime, reverse=True)

        _lib_cache = all_files
        _lib_cache_time = time.time()
        print(f"  Library scan complete: {len(_lib_cache):,} files indexed")
    except Exception as exc:
        print(f"  Library scan error: {exc}")
    finally:
        _lib_scan_running = False

def _ensure_lib_cache():
    """Trigger a background scan if cache is stale or missing."""
    import threading
    if _lib_scan_running:
        return
    if _lib_cache is not None and time.time() - _lib_cache_time < 120:
        return
    threading.Thread(target=_scan_library_bg, daemon=True).start()

@app.route("/api/library")
def api_library():
    """List library files, newest first. Paginated.
    Query params:
      ?limit=N   — return at most N files (default 100)
      ?offset=N  — skip first N files (for pagination)
    """
    import json as _json

    limit = min(int(request.args.get("limit", 100)), 500)
    offset = int(request.args.get("offset", 0))

    # Trigger background scan if needed (non-blocking)
    _ensure_lib_cache()

    # Return whatever we have (empty list if scan hasn't finished yet)
    files = _lib_cache or []
    total = len(files)
    page = files[offset:offset + limit]

    resp = _json.dumps({
        "files": page,
        "total_count": total,
        "offset": offset,
        "limit": limit,
    })
    return app.response_class(resp, mimetype="application/json")


_file_cache = {}   # filename -> (resp_json, content, cache_time)
_FILE_CACHE_TTL = 600  # 10-minute TTL — no per-request stat() needed


def _cache_library_file(safe_name: str):
    """Read a library file, store in cache, return (resp_json, content) or (None, None)."""
    import json as _json
    try:
        content = tools.read_file(safe_name)
        resp = _json.dumps({"filename": safe_name, "content": content})
        _file_cache[safe_name] = (resp, content, time.time())
        return resp, content
    except Exception:
        return None, None


@app.route("/api/library/<path:filename>")
def api_library_file(filename):
    """Read a specific library file. Cached with TTL — no stat() per request."""
    safe_name = filename.lstrip("/\\")
    if not safe_name.startswith("library/"):
        safe_name = "library/" + safe_name
    try:
        tools._safe_path(safe_name)  # security check only
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 403
    cached = _file_cache.get(safe_name)
    if cached and time.time() - cached[2] < _FILE_CACHE_TTL:
        return app.response_class(cached[0], mimetype="application/json")
    resp, _ = _cache_library_file(safe_name)
    if resp is None:
        return jsonify({"error": "File not found"}), 404
    return app.response_class(resp, mimetype="application/json")


@app.route("/api/library_batch", methods=["POST"])
def api_library_batch():
    """Fetch up to 150 library files in one shot. Body: {\"files\": [\"library/a.md\", ...]}"""
    import json as _json
    body = request.get_json(force=True, silent=True) or {}
    filenames = body.get("files", [])[:150]
    result = {}
    now = time.time()
    for filename in filenames:
        safe_name = filename.lstrip("/\\")
        if not safe_name.startswith("library/"):
            safe_name = "library/" + safe_name
        try:
            tools._safe_path(safe_name)  # security check
        except ValueError:
            continue
        cached = _file_cache.get(safe_name)
        if cached and now - cached[2] < _FILE_CACHE_TTL:
            result[filename] = cached[1]
            continue
        _, content = _cache_library_file(safe_name)
        if content is not None:
            result[filename] = content
    return app.response_class(_json.dumps(result), mimetype="application/json")


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
_graph_resp_json  = None   # pre-serialised JSON bytes
_graph_resp_ncount = 0     # node count at cache time (invalidation key)

_MAX_GRAPH_EDGES = 3000
_MAX_GRAPH_NODES = 300  # Cap visible nodes for performance


def _build_graph_response():
    """Pre-compute an idea-centric graph: nodes=library ideas, edges=shared concepts."""
    global _graph_resp_cache, _graph_resp_json, _graph_resp_ncount
    import time as _t
    _t0 = _t.time()

    # Use file_concepts directly from cache (compact format)
    if scoring._graph_cache and "file_concepts" in scoring._graph_cache:
        raw_fc = scoring._graph_cache["file_concepts"]
        file_concepts = {f: set(cs) for f, cs in raw_fc.items()}
    else:
        file_concepts = {}

    print(f"  [graph] step1: {len(file_concepts)} files loaded in {_t.time()-_t0:.1f}s")

    # Skip listing all library files — file_concepts from the backfill already covers them
    # Build concept->files inverted index
    concept_files = {}
    for fname, concepts in file_concepts.items():
        for c in concepts:
            concept_files.setdefault(c, set()).add(fname)

    # Keep only concepts shared by 2-50 files
    max_cf = min(50, max(10, len(file_concepts) * 0.02))
    selective = {c: fset for c, fset in concept_files.items()
                 if 2 <= len(fset) <= max_cf}

    # Score each file by how many selective concepts it has (= connectivity)
    file_score = {}
    for fname, concepts in file_concepts.items():
        file_score[fname] = sum(1 for c in concepts if c in selective)

    # Keep only the top N most-connected files for the graph
    top_files = sorted(file_score, key=lambda f: file_score[f], reverse=True)[:_MAX_GRAPH_NODES]
    top_set = set(top_files)

    print(f"  [graph] {len(file_concepts)} files -> top {len(top_set)} nodes, {len(selective)} selective concepts in {_t.time()-_t0:.1f}s")

    # Build idea nodes (only top files)
    idea_nodes = []
    for fname in sorted(top_files):
        title = fname.split("/")[-1].replace(".md", "").replace("_", " ").replace("-", " ").strip()
        if _concept_titles and fname in _concept_titles:
            title = _concept_titles[fname]
        if len(title) > 60:
            title = title[:57] + "..."
        idea_nodes.append({
            "id": fname,
            "title": title,
            "concepts": sorted(file_concepts.get(fname, set()))[:15],
        })

    # Find pairs among top files only
    pair_shared = {}
    for fname in top_files:
        file_selective = [c for c in file_concepts.get(fname, set()) if c in selective]
        for c in file_selective:
            for neighbor in selective[c]:
                if neighbor not in top_set or neighbor <= fname:
                    continue
                pair = (fname, neighbor)
                if pair not in pair_shared:
                    pair_shared[pair] = set()
                pair_shared[pair].add(c)

    # Build edges sorted by weight
    raw_edges = sorted(pair_shared.items(), key=lambda x: len(x[1]), reverse=True)
    idea_edges = []
    edge_count = {}
    for (f1, f2), shared in raw_edges:
        ca = edge_count.get(f1, 0)
        cb = edge_count.get(f2, 0)
        if ca < 12 and cb < 12:
            idea_edges.append({
                "from": f1,
                "to": f2,
                "shared": sorted(shared)[:5],
                "weight": len(shared),
            })
            edge_count[f1] = ca + 1
            edge_count[f2] = cb + 1
            if len(idea_edges) >= _MAX_GRAPH_EDGES:
                break

    print(f"  [graph] {len(idea_nodes)} nodes, {len(idea_edges)} edges in {_t.time()-_t0:.1f}s")

    result = {
        "nodes": idea_nodes,
        "edges": idea_edges,
        "total_nodes": len(idea_nodes),
        "total_edges": len(idea_edges),
    }
    _graph_resp_cache = result
    _graph_resp_json = json.dumps(result)
    # Track file count for cache invalidation
    if scoring._graph_cache and "file_concepts" in scoring._graph_cache:
        _graph_resp_ncount = len(scoring._graph_cache["file_concepts"])
    else:
        _graph_resp_ncount = len(file_concepts)


@app.route("/api/graph")
def api_graph():
    """Return an idea-centric knowledge graph for visualization.
    Pass ?rebuild=1 to force a cache refresh.
    Auto-rebuilds when the scoring graph cache has grown since last build."""
    rebuild = request.args.get("rebuild", "0") == "1"
    # Auto-rebuild if graph cache has been populated since we last built
    current_fc_count = len(scoring._graph_cache.get("file_concepts", {})) if scoring._graph_cache else 0
    if current_fc_count > 0 and current_fc_count != _graph_resp_ncount:
        rebuild = True
    if _graph_resp_json is None or rebuild:
        _build_graph_response()
    return app.response_class(_graph_resp_json, mimetype="application/json")


_concept_index = {}  # word -> set of filenames
_concept_index_time = 0
_concept_titles = {}  # filename -> title

def _build_concept_index():
    """Build a word->files index for fast concept search."""
    global _concept_index, _concept_index_time, _concept_titles
    _concept_index = {}
    _concept_titles = {}
    files = _lib_cache if _lib_cache else sorted(f for f in tools.list_files("library") if f.endswith(".md"))
    # Cap to 5000 files for index building performance
    if len(files) > 5000:
        files = files[:5000]
    for rel in files:
        fname_lower = rel.lower().replace("_", " ").replace("-", " ")
        title = rel.split("/")[-1].replace(".md", "").replace("_", " ").replace("-", " ").strip()
        try:
            content = tools.read_file(rel)
            for line in content.splitlines():
                if line.startswith("# "):
                    title = line[2:].strip()
                    break
            text = fname_lower + " " + content.lower()
        except Exception:
            text = fname_lower
        _concept_titles[rel] = title
        for word in set(text.split()):
            if len(word) >= 3:
                _concept_index.setdefault(word, set()).add(rel)
    _concept_index_time = time.time()


@app.route("/api/concept")
def api_concept():
    """Search library files for ideas related to a concept node."""
    query = request.args.get("q", "").strip().lower()
    if not query:
        return jsonify({"matches": []})

    # Rebuild index every 60s
    if not _concept_index or time.time() - _concept_index_time > 60:
        _build_concept_index()

    words = [w for w in query.split() if len(w) >= 3]
    if not words:
        return jsonify({"matches": []})

    # Score files by how many query words they contain
    file_scores = {}
    for w in words:
        for rel in _concept_index.get(w, []):
            file_scores[rel] = file_scores.get(rel, 0) + 1

    top = sorted(file_scores.items(), key=lambda x: x[1], reverse=True)[:5]

    matches = []
    for rel, _ in top:
        try:
            content = tools.read_file(rel)
            title = _concept_titles.get(rel, rel.split("/")[-1].replace(".md", ""))
            body_lines = [l for l in content.splitlines() if not l.startswith("#") and not l.startswith("*Created")]
            snippet = " ".join(" ".join(body_lines).split())[:800]
            matches.append({"title": title, "file": rel, "snippet": snippet})
        except Exception:
            continue

    return jsonify({"concept": query, "matches": matches})


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

def _start_library_cache_warmer() -> None:
    """Background thread: pre-load all library files into _file_cache so first clicks are instant."""
    import threading

    def _warm():
        time.sleep(3)  # let server finish starting first
        _WARM_CAP = 500  # only pre-cache a small number for fast first-click experience
        try:
            files = [f for f in tools.list_files("library") if f.endswith(".md")]
            to_warm = files[:_WARM_CAP]
            print(f"  Library cache warmer: pre-loading {len(to_warm)} of {len(files)} files...")
            for f in to_warm:
                if f not in _file_cache:
                    _cache_library_file(f)
            print(f"  Library cache warmer: done ({len(to_warm)} files ready).")
        except Exception as exc:
            print(f"  Library cache warmer error: {exc}")

    threading.Thread(target=_warm, daemon=True).start()


def _background_warmup():
    """Background thread: warm up graph visualization, concept index, and file cache.
    Note: The graph backfill is done synchronously in main.py before loops start."""
    import threading, traceback
    print("  [warmup] Starting background warmup thread...")
    def _warm():
        print("  [warmup] Thread started")
        # Start library file scan immediately (runs in background)
        _scan_library_bg()
        print(f"  [warmup] Library file index ready: {len(_lib_cache or []):,} files")
        # Build graph visualization (waits for scoring graph cache, may be empty initially)
        try:
            fc_count = len(scoring._graph_cache.get('file_concepts', {})) if scoring._graph_cache else 0
            print(f"  [warmup] Graph cache: {fc_count} files")
            if fc_count > 0:
                _build_graph_response()
                if _graph_resp_cache:
                    c = _graph_resp_cache
                    print(f"  Graph ready: {len(c['nodes'])} ideas, {len(c['edges'])} connections")
        except Exception as exc:
            print(f"  Graph pre-build failed: {exc}")
            traceback.print_exc()
        try:
            _build_concept_index()
            print(f"  Concept index ready: {len(_concept_index)} terms")
        except Exception:
            pass
        _start_library_cache_warmer()
    threading.Thread(target=_warm, daemon=True).start()


def launch(port: int = 7860) -> None:
    """Start the Flask web server."""
    # Pre-warm library count (fast) so first /api/state isn't zeros
    global _state_lib_count, _state_lib_time
    _state_lib_count = tools.get_knowledge_count()
    _state_lib_time = time.time()
    print(f"  Library: {_state_lib_count} ideas in vault")
    # Heavy warmup in background so server starts immediately
    _background_warmup()
    print(f"\n  OctoBot Game Server running at http://localhost:{port}\n")
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False, threaded=True)
