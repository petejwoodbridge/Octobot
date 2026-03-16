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

Guidelines:
- Give the idea a catchy, memorable name.
- Use ## headings to structure it: ## The Idea, ## The Problem It Solves, ## How It Works, ## Why It's Brilliant
- Be SPECIFIC — not "an app for health" but "a fork that vibrates SOS when you're stress-eating at 2am"
- It's okay to be quirky, funny, or mildly absurd — the best ideas often are
- Draw unexpected connections between domains to make truly original combinations
- End with a one-line "pitch" — the sentence you'd say in a lift to make someone immediately want this
- Keep the total length between 250 and 500 words.
- Do NOT include meta-commentary like "Here is my idea…" — just dive straight into the idea pitch.
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

    filename = tools.save_research(topic, notes)
    mem.log_event("action", f"Research saved to {filename}")

    # Update knowledge graph with the new research
    try:
        scoring.update_knowledge_graph(filename, notes)
    except Exception:
        pass

    return f"Research on '{topic}' saved to {filename}."


def expand_research(topic: str) -> str:
    """
    If a file for *topic* already exists in the library, read it and ask
    the LLM to expand it with additional details or a new angle.
    """
    slug = topic.lower().replace(" ", "_").replace("/", "-")
    slug = "".join(c for c in slug if c.isalnum() or c in "_-")
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
    slug = topic.lower().replace(" ", "_").replace("/", "-")
    slug = "".join(c for c in slug if c.isalnum() or c in "_-")
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
