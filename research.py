"""
research.py — OctoBot Idea Generation Module
=============================================
Handles OctoBot's self-directed idea generation capability.

Idea generation workflow
------------------------
1. The agent picks an idea domain or problem area to tackle.
2. conduct_research() prompts the LLM to generate an original idea pitch.
3. The idea is saved to workspace/library/<topic>.md via save_research().
4. A log entry is written to memory.

The module also provides helpers to:
- list idea domains already explored
- expand on an existing idea
- synthesise connections across multiple ideas
"""

from datetime import datetime

import llm_provider
import memory as mem
import tools
import scoring

# ---------------------------------------------------------------------------
# LLM helper — delegates to the shared provider (Ollama / OpenAI / Anthropic)
# ---------------------------------------------------------------------------

MODEL = "gemma3:4b"  # synced with agent.MODEL at startup via main.py

RESEARCH_SYSTEM_PROMPT = """You are OctoBot's idea generation arm — a wildly creative inventor with eight tentacles full of original concepts.
When given a problem area, domain, or spark of inspiration, you invent ONE specific, original, never-before-invented idea.

You MUST use this exact markdown structure every time:

## [Catchy Idea Name]

## Overview
[2-3 sentence hook describing the invention]

## The Problem It Solves
[What frustration, gap, or opportunity does this address?]

## How It Works
[Specific technical or practical explanation — be detailed and inventive]

## Why It's Brilliant
[What makes this special, surprising, or delightful?]

## Elevator Pitch
[One punchy sentence — the line you'd say in a lift to make someone immediately want this]

Guidelines:
- Be SPECIFIC — not "an app for health" but "a fork that vibrates SOS when you're stress-eating at 2am"
- It's okay to be quirky, funny, or mildly absurd — the best ideas often are
- Draw unexpected connections between domains to make truly original combinations
- Keep the total length between 300 and 500 words.
- Do NOT include meta-commentary like "Here is my idea…" — just dive straight into the idea pitch.
- Do NOT wrap your output in quotes. Write raw markdown directly.
- ALWAYS start with ## followed by the idea name. Never start with a quote mark.
"""


def _llm(system: str, user: str) -> str:
    """Call the configured LLM provider and return the response text."""
    return llm_provider.call_llm(
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        model=MODEL,
    )


# ---------------------------------------------------------------------------
# Core research functions
# ---------------------------------------------------------------------------

def conduct_research(topic: str) -> str:
    """
    Ask the LLM to research *topic* and save the result to the library.
    Returns a status message.
    """
    mem.log_event("research", f"Starting research on: {topic}")

    prompt = (
        f"Generate a brilliant, original, never-before-invented idea for the following domain or challenge:\n\n"
        f"**{topic}**\n\n"
        f"Invent something specific, creative, and genuinely useful (or usefully absurd). "
        f"Name it, explain the problem it solves, how it works, and why it's brilliant. "
        f"Format as clean markdown with a punchy lift-pitch at the end."
    )

    try:
        notes = _llm(RESEARCH_SYSTEM_PROMPT, prompt)
    except Exception as exc:
        mem.log_event("error", f"Research LLM call failed for '{topic}': {exc}")
        return f"Research failed: {exc}"

    # Strip leading/trailing quotes the LLM sometimes wraps output in
    notes = notes.strip().strip('"').strip()

    filename = tools.save_research(topic, notes)
    mem.log_event("action", f"Research saved to {filename}")

    # Update knowledge graph with the new research
    try:
        graph_result = scoring.update_knowledge_graph(filename, notes)
    except Exception:
        graph_result = {"new_nodes": [], "new_edges": []}

    # Write cross-reference links into the idea file
    try:
        new_concepts = scoring._extract_concepts(notes)
        cross_refs = scoring.find_cross_references(new_concepts, exclude_file=filename)
        if cross_refs:
            seen = set()
            links = []
            for xref in cross_refs:
                ref_file = xref["found_in"]
                if ref_file not in seen:
                    seen.add(ref_file)
                    readable = ref_file.replace("library/", "").replace(".md", "").replace("_", " ")
                    links.append(f"- **{readable}** (shared concept: *{xref['concept']}*)")
            if links:
                links_section = "\n\n---\n\n## Related Ideas\n\n" + "\n".join(links[:5]) + "\n"
                tools.append_file(filename, links_section)
                mem.increment_game_stat("cross_refs", len(links))
    except Exception:
        pass

    return f"Research on '{topic}' saved to {filename}."


def save_research_slug(topic: str) -> str:
    """Return the canonical slug for a research topic (shared helper)."""
    slug = topic.lower().replace(" ", "_").replace("/", "-")
    slug = "".join(c for c in slug if c.isalnum() or c in "_-")
    return slug[:120]  # cap to avoid Windows MAX_PATH errors


def expand_research(topic: str) -> str:
    """
    If a file for *topic* already exists in the library, read it and ask
    the LLM to expand it with additional details or a new angle.
    """
    slug = save_research_slug(topic)
    filename = f"library/{slug}.md"
    try:
        existing = tools.read_file(filename)
    except FileNotFoundError:
        return conduct_research(topic)  # Start fresh if not found

    mem.log_event("research", f"Expanding research on: {topic}")

    prompt = (
        f"Here is my existing idea for **{topic}**:\n\n"
        f"{existing}\n\n"
        f"Please write a new section that extends this idea — a spin-off product, "
        f"an unexpected use case, a wacky upgrade, or a companion invention. "
        f"Output only the new section (starting with '## ...')."
    )

    try:
        addition = _llm(RESEARCH_SYSTEM_PROMPT, prompt)
    except Exception as exc:
        mem.log_event("error", f"Expand research LLM call failed: {exc}")
        return f"Expansion failed: {exc}"

    tools.append_file(
        filename,
        f"\n\n---\n\n*Expanded by OctoBot on {datetime.now().strftime('%Y-%m-%d %H:%M')}*\n\n{addition}\n",
    )
    mem.log_event("action", f"Research expanded: {filename}")
    return f"Research on '{topic}' expanded."


def list_researched_topics() -> list[str]:
    """Return a list of idea domains that have been explored (library .md files)."""
    files = [f for f in tools.list_files("library") if f.endswith(".md")]
    topics = []
    for f in sorted(files):
        # Convert slug back to a readable name
        name = f.replace("library/", "").replace(".md", "").replace("_", " ")
        topics.append(name)
    return topics


def already_researched(topic: str) -> bool:
    """Return True if a library file already exists for this topic."""
    slug = save_research_slug(topic)
    try:
        tools.read_file(f"library/{slug}.md")
        return True
    except FileNotFoundError:
        return False


def synthesise_knowledge(question: str) -> str:
    """
    Read all library files and ask the LLM to answer *question* using
    accumulated knowledge.  Returns the LLM's answer as a string.
    """
    files = [f for f in tools.list_files("library") if f.endswith(".md")]
    if not files:
        return "The library is empty — no knowledge to synthesise yet."

    context_parts = []
    for f in files[:10]:  # Limit to avoid context overflow
        try:
            txt = tools.read_file(f)
            context_parts.append(f"### {f}\n{txt[:800]}")  # Truncate long files
        except Exception:
            pass

    context = "\n\n".join(context_parts)

    system = (
        "You are OctoBot, a wildly creative inventor AI. You have access to your idea vault. "
        "Answer the user's question by drawing on the ideas already generated. "
        "Make surprising connections between ideas. Be inventive, specific, and charming."
    )
    user = (
        f"Using the following ideas from the vault, answer this question:\n\n"
        f"**{question}**\n\n"
        f"---\n\n{context}"
    )

    try:
        answer = _llm(system, user)
    except Exception as exc:
        mem.log_event("error", f"Synthesise LLM call failed: {exc}")
        return f"Synthesis failed: {exc}"

    mem.log_event("action", f"Knowledge synthesis: '{question[:60]}'")
    return answer


def suggest_research_topics(n: int = 3) -> list[str]:
    """
    Ask the LLM to suggest *n* new research topics based on what is
    already in the library.  Returns a list of topic strings.
    """
    existing = list_researched_topics()
    existing_str = ", ".join(existing) if existing else "nothing yet"

    system = (
        "You are OctoBot's idea spark engine. "
        "Suggest fresh idea domains or problem areas for an inventor AI to generate original inventions for."
    )
    user = (
        f"I have already generated ideas for: {existing_str}.\n"
        f"Suggest {n} new, specific idea domains I should explore next — "
        f"focus on unsolved problems, annoying daily frustrations, or delightfully niche situations. "
        f"Return only the domain descriptions, one per line, no numbers or bullets."
    )

    try:
        raw = _llm(system, user)
    except Exception as exc:
        mem.log_event("error", f"Topic suggestion failed: {exc}")
        return ["python patterns", "ai agents", "knowledge graphs"]

    topics = [line.strip() for line in raw.splitlines() if line.strip()]
    return topics[:n]


def _is_well_structured(content: str) -> bool:
    """Check if content has the required heading structure."""
    return ("\n## " in content and
            ("## Overview" in content or "## The Problem" in content or "## How It Works" in content))


def _title_from_filename(filename: str) -> str:
    """Extract a readable title from a library filename."""
    raw = filename.replace("library/", "").replace(".md", "")
    return raw.replace("_", " ").replace("-", " ").strip().title()


def reformat_library_file(filename: str, use_llm: bool = True) -> bool:
    """
    Check if a library file lacks proper heading structure and reformat it.
    Tries local text reformatting first; falls back to LLM if use_llm=True.
    Returns True if the file was reformatted.
    """
    try:
        content = tools.read_file(filename)
    except Exception:
        return False

    if _is_well_structured(content):
        return False

    stripped = content.strip().strip('"').strip('\u201c').strip('\u201d').strip()
    if len(stripped) < 50:
        return False

    title = _title_from_filename(filename)

    # --- Try local reformat first ---
    # Files that already have ## headings but not the standard ones
    if "\n## " in content or content.startswith("## "):
        result = _local_reformat_with_headings(title, content)
        if result:
            tools.write_file(filename, result)
            return True

    # Files with # H1 + ## headings — just need standard sections added
    if content.startswith("# ") and "## " in content:
        result = _local_reformat_with_headings(title, content)
        if result:
            tools.write_file(filename, result)
            return True

    # Quoted or flat text — needs LLM to restructure
    if use_llm:
        return _llm_reformat(filename, title, stripped)

    return False


def _local_reformat_with_headings(title: str, content: str) -> str | None:
    """
    Reformat a file that already has some ## headings but not the standard structure.
    Wraps existing content with missing standard sections.
    """
    lines = content.strip().split("\n")

    # Extract the idea name from first ## heading or # heading
    idea_name = title
    for line in lines:
        if line.startswith("## ") and len(line) > 4:
            idea_name = line.lstrip("#").strip().strip("*").strip()
            break
        elif line.startswith("# ") and len(line) > 3:
            idea_name = line.lstrip("#").strip().strip("*").strip()
            break

    # Find existing body content (everything after the first heading)
    body_start = 0
    for i, line in enumerate(lines):
        if line.startswith("#"):
            body_start = i + 1
            break

    # Collect remaining content, skip the created-by line
    body_lines = []
    for line in lines[body_start:]:
        if line.startswith("*Created by OctoBot"):
            continue
        body_lines.append(line)
    body = "\n".join(body_lines).strip()

    if not body:
        return None

    # Check which standard sections already exist
    has_overview = "## Overview" in content or "**Overview**" in content
    has_problem = "## The Problem" in content
    has_how = "## How It Works" in content
    has_why = "## Why It's Brilliant" in content
    has_pitch = "## Elevator Pitch" in content

    # If it already has most sections, just ensure header
    if sum([has_overview, has_problem, has_how, has_why]) >= 2:
        header = f"# {idea_name}\n\n*Created by OctoBot*\n\n"
        # Replace **Overview** with ## Overview if needed
        body = body.replace("**Overview**", "## Overview")
        return header + body + "\n"

    # Otherwise wrap existing content under Overview and add placeholder sections
    result = f"# {idea_name}\n\n*Created by OctoBot*\n\n"
    result += f"## Overview\n\n{body}\n"

    return result


def _llm_reformat(filename: str, title: str, stripped: str) -> bool:
    """Use the LLM to reformat a file that has no usable heading structure."""
    prompt = (
        f"Here is a raw, unstructured idea that needs to be reformatted into a proper pitch document.\n\n"
        f"Original content:\n{stripped[:2000]}\n\n"
        f"Rewrite this idea using this EXACT markdown structure:\n\n"
        f"## [Catchy Idea Name]\n\n"
        f"## Overview\n[2-3 sentence hook]\n\n"
        f"## The Problem It Solves\n[What frustration or gap does this address?]\n\n"
        f"## How It Works\n[Specific technical or practical explanation]\n\n"
        f"## Why It's Brilliant\n[What makes this special or delightful?]\n\n"
        f"## Elevator Pitch\n[One punchy sentence]\n\n"
        f"Keep the original idea and details — just restructure them into this format. "
        f"Do NOT wrap output in quotes. Write raw markdown directly. 300-500 words."
    )

    try:
        reformatted = _llm(RESEARCH_SYSTEM_PROMPT, prompt)
        reformatted = reformatted.strip().strip('"').strip()
        if "## " in reformatted and len(reformatted) > 100:
            header = f"# {title}\n\n*Created by OctoBot*\n\n"
            tools.write_file(filename, header + reformatted + "\n")
            mem.log_event("action", f"Reformatted library file: {filename}")
            return True
    except Exception:
        pass

    return False


def reformat_all_unstructured(use_llm: bool = True, llm_batch_size: int = 20) -> int:
    """
    Scan the library for files that lack proper heading structure and reformat them.
    Local reformatting is done for all files. LLM reformatting is limited to llm_batch_size
    files per call to avoid blocking startup forever.
    Returns count of files reformatted.
    """
    files = [f for f in tools.list_files("library") if f.endswith(".md")]
    count = 0
    llm_count = 0

    for f in files:
        try:
            content = tools.read_file(f)
        except Exception:
            continue

        if _is_well_structured(content):
            continue

        stripped = content.strip().strip('"').strip('\u201c').strip('\u201d').strip()
        if len(stripped) < 50:
            continue

        title = _title_from_filename(f)

        # Try local reformat first (fast, no LLM needed)
        if "\n## " in content or content.startswith("## ") or (content.startswith("# ") and "## " in content):
            result = _local_reformat_with_headings(title, content)
            if result:
                tools.write_file(f, result)
                count += 1
                continue

        # LLM reformat for flat/quoted content
        if use_llm and llm_count < llm_batch_size:
            if _llm_reformat(f, title, stripped):
                count += 1
                llm_count += 1

    return count
