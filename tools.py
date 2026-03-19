"""
tools.py — OctoBot File Tools
===============================
All the "arms" OctoBot uses to interact with its workspace.

Every tool enforces path safety: no operation can escape the
project's workspace directory.

Tools available
---------------
list_files()
read_file(filename)
write_file(filename, content)
append_file(filename, content)
delete_file(filename)
search_files(query)
create_markdown(title, content)
save_research(topic, summary)
"""

import os
import json
import fnmatch
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Workspace root — everything is anchored here
# ---------------------------------------------------------------------------
WORKSPACE_ROOT = Path(__file__).parent / "workspace"
LIBRARY_DIR = WORKSPACE_ROOT / "library"
CONTEXT_DIR = WORKSPACE_ROOT / "context"
KNOWLEDGE_DIR = WORKSPACE_ROOT / "knowledge"
COMMENTS_DIR = WORKSPACE_ROOT / "comments"
JOURNAL_FILE = WORKSPACE_ROOT / "octobot_journal.md"

# Ensure directories exist at import time
WORKSPACE_ROOT.mkdir(exist_ok=True)
LIBRARY_DIR.mkdir(exist_ok=True)
CONTEXT_DIR.mkdir(exist_ok=True)
KNOWLEDGE_DIR.mkdir(exist_ok=True)
COMMENTS_DIR.mkdir(exist_ok=True)


# ---------------------------------------------------------------------------
# Path safety
# ---------------------------------------------------------------------------

def _safe_path(filename: str, base: Path = WORKSPACE_ROOT) -> Path:
    """
    Resolve *filename* relative to *base* and confirm it stays inside *base*.
    Raises ValueError if the resolved path would escape the workspace.
    """
    # Strip leading slashes / drive letters that could escape the root
    clean = filename.lstrip("/\\")
    resolved = (base / clean).resolve()
    base_resolved = base.resolve()
    if not str(resolved).startswith(str(base_resolved)):
        raise ValueError(
            f"Path escape attempt blocked: '{filename}' resolves outside workspace."
        )
    return resolved


# ---------------------------------------------------------------------------
# Core file tools
# ---------------------------------------------------------------------------

def list_files(subdir: str = "") -> list[str]:
    """
    Return a list of relative file paths inside the workspace (or a subdir).
    Each path is relative to WORKSPACE_ROOT.
    """
    base = _safe_path(subdir) if subdir else WORKSPACE_ROOT.resolve()
    results = []
    for root, _dirs, files in os.walk(base):
        for fname in files:
            full = Path(root) / fname
            rel = full.relative_to(WORKSPACE_ROOT.resolve())
            results.append(str(rel).replace("\\", "/"))
    return results


def read_file(filename: str) -> str:
    """Read and return the text content of a file inside the workspace."""
    path = _safe_path(filename)
    if not path.exists():
        raise FileNotFoundError(f"File not found in workspace: '{filename}'")
    return path.read_text(encoding="utf-8")


def write_file(filename: str, content: str) -> str:
    """
    Write *content* to *filename* inside the workspace, creating parent dirs
    as needed.  Returns a status string.
    """
    path = _safe_path(filename)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return f"Written: {filename} ({len(content)} chars)"


def append_file(filename: str, content: str) -> str:
    """Append *content* to an existing file (or create it if absent)."""
    path = _safe_path(filename)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(content)
    return f"Appended {len(content)} chars to: {filename}"


def delete_file(filename: str) -> str:
    """Delete a file from the workspace.  Returns a status string."""
    path = _safe_path(filename)
    if not path.exists():
        raise FileNotFoundError(f"File not found: '{filename}'")
    path.unlink()
    return f"Deleted: {filename}"


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

def search_files(query: str) -> list[dict]:
    """
    Search all text files in the workspace for lines containing *query*
    (case-insensitive).

    Returns a list of dicts: {file, line_number, line_text}
    """
    query_lower = query.lower()
    results = []
    for rel in list_files():
        path = _safe_path(rel)
        # Only search text-like files
        if path.suffix.lower() not in {".md", ".txt", ".json", ".py", ".csv", ""}:
            continue
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for i, line in enumerate(lines, start=1):
            if query_lower in line.lower():
                results.append(
                    {"file": rel, "line_number": i, "line_text": line.strip()}
                )
    return results


# ---------------------------------------------------------------------------
# Markdown helpers
# ---------------------------------------------------------------------------

def create_markdown(title: str, content: str, subdir: str = "library") -> str:
    """
    Create a markdown file titled *title* inside workspace/<subdir>/.
    The filename is derived from the title (slug-ified).
    Returns the relative filename.
    """
    slug = title.lower().replace(" ", "_").replace("/", "-")
    slug = "".join(c for c in slug if c.isalnum() or c in "_-")
    slug = slug[:120]  # cap to avoid Windows MAX_PATH errors
    filename = f"{subdir}/{slug}.md"
    full_content = f"# {title}\n\n*Created by OctoBot on {datetime.now().strftime('%Y-%m-%d %H:%M')}*\n\n{content}\n"
    write_file(filename, full_content)
    return filename


def save_research(topic: str, summary: str) -> str:
    """
    Save a research summary to workspace/library/<topic_slug>.md.
    Appends to the file if it already exists.
    Returns the relative filename (e.g. "library/my_topic.md").
    Rejects empty or structureless content.
    """
    # Strip leading/trailing quotes the LLM sometimes wraps output in
    summary = summary.strip().strip('"').strip('\u201c').strip('\u201d').strip()

    # Reject if content is too short or has no real substance
    if len(summary) < 100:
        raise ValueError(f"Research content too short ({len(summary)} chars) — not saving")
    if "## " not in summary:
        raise ValueError("Research content lacks heading structure — not saving")

    slug = topic.lower().replace(" ", "_").replace("/", "-")
    slug = "".join(c for c in slug if c.isalnum() or c in "_-")
    slug = slug[:120]  # cap to avoid Windows MAX_PATH errors
    filename = f"library/{slug}.md"

    if _safe_path(filename).exists():
        append_file(
            filename,
            f"\n---\n\n## Update — {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n{summary}\n",
        )
    else:
        create_markdown(topic, summary, subdir="library")
    return filename


# ---------------------------------------------------------------------------
# Utility: load all context for the agent
# ---------------------------------------------------------------------------

def load_context_snapshot() -> str:
    """
    Return a single string containing the content of key workspace files
    (tasks.md, agent_notes.md, and all context/ files).
    Used to prime the LLM with current state.
    """
    snippets = []

    priority_files = ["tasks.md", "agent_notes.md"]
    for pf in priority_files:
        try:
            txt = read_file(pf)
            snippets.append(f"### {pf}\n{txt}")
        except FileNotFoundError:
            pass

    # Context directory
    try:
        for rel in list_files("context"):
            try:
                txt = read_file(rel)
                snippets.append(f"### context/{rel}\n{txt}")
            except (FileNotFoundError, OSError):
                pass
    except Exception:
        pass

    return "\n\n".join(snippets) if snippets else "(No workspace context yet.)"


# ---------------------------------------------------------------------------
# Knowledge & Comments scanning (game input systems)
# ---------------------------------------------------------------------------

_SUPPORTED_KNOWLEDGE_EXT = {".md", ".txt", ".json"}


def scan_knowledge_folder() -> list[str]:
    """Return relative paths of all supported files in workspace/knowledge/."""
    results = []
    if not KNOWLEDGE_DIR.exists():
        return results
    for f in KNOWLEDGE_DIR.iterdir():
        if f.is_file() and f.suffix.lower() in _SUPPORTED_KNOWLEDGE_EXT:
            results.append("knowledge/" + f.name)
    return sorted(results)


def scan_comments_folder() -> list[str]:
    """Return relative paths of all files in workspace/comments/."""
    results = []
    if not COMMENTS_DIR.exists():
        return results
    for f in COMMENTS_DIR.iterdir():
        if f.is_file() and f.suffix.lower() in _SUPPORTED_KNOWLEDGE_EXT:
            results.append("comments/" + f.name)
    return sorted(results)


def get_knowledge_count() -> int:
    """Return the total number of library markdown files (fast, non-recursive)."""
    try:
        return sum(1 for e in os.scandir(LIBRARY_DIR) if e.is_file() and e.name.endswith(".md"))
    except OSError:
        return len([f for f in list_files("library") if f.endswith(".md")])


def append_journal(entry: str) -> str:
    """Append an entry to octobot_journal.md with a timestamp."""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    text = f"\n\n---\n\n## {ts}\n\n{entry}\n"
    return append_file("octobot_journal.md", text)


def read_journal() -> str:
    """Read the full octobot_journal.md content."""
    try:
        return read_file("octobot_journal.md")
    except FileNotFoundError:
        return "(No journal yet.)"


# ---------------------------------------------------------------------------
# Ollama model discovery
# ---------------------------------------------------------------------------

def get_local_models() -> list[str]:
    """
    Return a list of model names currently available in the local Ollama installation.
    Falls back to a sensible default list if Ollama is unreachable.
    """
    try:
        import ollama
        result = ollama.list()          # returns a ListResponse
        models = [m.model for m in result.models if m.model]
        return sorted(models) if models else ["llama3.2:3b"]
    except Exception:
        return ["llama3.2:3b", "llama3", "mistral", "gemma3:4b"]


def get_library_index() -> str:
    """Return a markdown-formatted list of library files."""
    files = [f for f in list_files("library") if f.endswith(".md")]
    if not files:
        return "(Library is empty — no markdown files yet.)"
    lines = ["## Library Index", ""]
    for f in sorted(files):
        lines.append(f"- `{f}`")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# File upload ingestion
# ---------------------------------------------------------------------------

def ingest_uploaded_file(tmp_path: str, original_name: str) -> tuple[str, str]:
    """
    Read an uploaded file and save it into workspace/context/.

    Supports: .md, .txt, .py, .json, .csv, .html, .xml, .yaml, .yml, .pdf

    Parameters
    ----------
    tmp_path : str
        Temporary path Gradio wrote the upload to.
    original_name : str
        The user's original filename (used to pick the destination name).

    Returns
    -------
    (dest_rel, text_content)
        dest_rel   — relative path inside workspace where the file was saved
        text_content — extracted plain text (for the agent to read)
    """
    import shutil
    src = Path(tmp_path)
    suffix = Path(original_name).suffix.lower()
    safe_name = "".join(
        c if (c.isalnum() or c in "._- ") else "_" for c in original_name
    ).strip()
    dest_rel = f"context/{safe_name}"
    dest = _safe_path(dest_rel)
    dest.parent.mkdir(parents=True, exist_ok=True)

    if suffix == ".pdf":
        text_content = _extract_pdf_text(src)
        # Save extracted text as .txt alongside
        txt_rel = dest_rel.replace(".pdf", "_extracted.txt")
        write_file(txt_rel, text_content)
        # Also copy the original pdf
        shutil.copy2(src, dest)
    else:
        # Plain text-like file — copy and read
        shutil.copy2(src, dest)
        try:
            text_content = dest.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            text_content = f"(Could not read file: {e})"

    return dest_rel, text_content


def _extract_pdf_text(path: Path) -> str:
    """Extract text from a PDF using pypdf (optional dependency)."""
    try:
        from pypdf import PdfReader  # type: ignore
        reader = PdfReader(str(path))
        pages = []
        for page in reader.pages:
            t = page.extract_text()
            if t:
                pages.append(t)
        return "\n\n".join(pages) if pages else "(PDF contained no extractable text.)"
    except ImportError:
        return (
            "(pypdf not installed — install it with 'pip install pypdf' to enable "
            "PDF text extraction.  The raw file has been saved to context/.)"
        )
    except Exception as exc:
        return f"(PDF extraction failed: {exc})"
