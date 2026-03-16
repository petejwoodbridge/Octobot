"""
llm_provider.py — Unified LLM Backend for OctoBot
====================================================
Supports three providers:

  ollama    — local models via Ollama (default)
  openai    — OpenAI Chat Completions API
  anthropic — Anthropic Claude Messages API

Configuration is mutated at runtime by the UI.
Set PROVIDER / API_KEY / API_MODEL before calling call_llm() / stream_llm().
"""

import os

# ---------------------------------------------------------------------------
# Runtime configuration — updated by the UI
# ---------------------------------------------------------------------------
PROVIDER: str  = "ollama"    # "ollama" | "openai" | "anthropic"
API_KEY: str   = ""          # API key for cloud providers
API_MODEL: str = ""          # Model override – blank = fall back to caller's model


def _eff_model(fallback_model: str) -> str:
    """Return API_MODEL if set, otherwise the caller-supplied fallback."""
    return API_MODEL.strip() if API_MODEL.strip() else fallback_model


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

def call_llm(messages: list[dict], model: str) -> str:
    """Synchronous LLM call.  Returns the full response text."""
    if PROVIDER == "openai":
        return _openai_call(messages, model)
    if PROVIDER == "anthropic":
        return _anthropic_call(messages, model)
    return _ollama_call(messages, model)


def stream_llm(messages: list[dict], model: str):
    """Streaming LLM call.  Yields text tokens one at a time."""
    if PROVIDER == "openai":
        yield from _openai_stream(messages, model)
    elif PROVIDER == "anthropic":
        yield from _anthropic_stream(messages, model)
    else:
        yield from _ollama_stream(messages, model)


def get_ollama_models() -> list[str]:
    """Return locally available Ollama model names, or [] on error."""
    try:
        import ollama
        result = ollama.list()
        # Newer ollama library returns a ListResponse object with .models attribute
        # Each item is a Model object with a .model attribute (not a dict)
        models_list = getattr(result, "models", None)
        if models_list is None:
            # Fallback: treat as dict for older library versions
            models_list = result.get("models", [])
        names = []
        for m in models_list:
            # Model object: m.model  (new API)
            name = getattr(m, "model", None) or getattr(m, "name", None)
            if name is None:
                # Last resort: dict-style access
                try:
                    name = m.get("model") or m.get("name")
                except Exception:
                    pass
            if name:
                names.append(name)
        return names
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Ollama
# ---------------------------------------------------------------------------

def _ollama_call(messages, model):
    import ollama
    resp = ollama.chat(model=model, messages=messages)
    return resp["message"]["content"].strip()


def _ollama_stream(messages, model):
    import ollama
    for chunk in ollama.chat(model=model, messages=messages, stream=True):
        token = chunk.get("message", {}).get("content", "")
        if token:
            yield token


# ---------------------------------------------------------------------------
# OpenAI
# ---------------------------------------------------------------------------

def _openai_call(messages, model):
    from openai import OpenAI
    client = OpenAI(api_key=API_KEY or os.getenv("OPENAI_API_KEY", ""))
    resp = client.chat.completions.create(
        model=_eff_model(model) or "gpt-4o-mini",
        messages=messages,
    )
    return resp.choices[0].message.content.strip()


def _openai_stream(messages, model):
    from openai import OpenAI
    client = OpenAI(api_key=API_KEY or os.getenv("OPENAI_API_KEY", ""))
    stream = client.chat.completions.create(
        model=_eff_model(model) or "gpt-4o-mini",
        messages=messages,
        stream=True,
    )
    for chunk in stream:
        delta = chunk.choices[0].delta.content or ""
        if delta:
            yield delta


# ---------------------------------------------------------------------------
# Anthropic (Claude)
# ---------------------------------------------------------------------------

def _anthropic_call(messages, model):
    import anthropic
    client = anthropic.Anthropic(api_key=API_KEY or os.getenv("ANTHROPIC_API_KEY", ""))
    system_msg, filtered = _split_system(messages)
    resp = client.messages.create(
        model=_eff_model(model) or "claude-3-haiku-20240307",
        max_tokens=2048,
        system=system_msg,
        messages=filtered,
    )
    return resp.content[0].text.strip()


def _anthropic_stream(messages, model):
    import anthropic
    client = anthropic.Anthropic(api_key=API_KEY or os.getenv("ANTHROPIC_API_KEY", ""))
    system_msg, filtered = _split_system(messages)
    with client.messages.stream(
        model=_eff_model(model) or "claude-3-haiku-20240307",
        max_tokens=2048,
        system=system_msg,
        messages=filtered,
    ) as stream:
        for text in stream.text_stream:
            yield text


def _split_system(messages: list[dict]) -> tuple[str, list[dict]]:
    """Separate system message from the rest (Anthropic format)."""
    system = ""
    rest = []
    for m in messages:
        if m.get("role") == "system":
            system = m["content"]
        else:
            rest.append(m)
    return system, rest
