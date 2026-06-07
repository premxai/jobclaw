"""Known ATS slug repairs for high-priority companies."""

from __future__ import annotations


_ALIASES: dict[tuple[str, str, str], list[tuple[str, str]]] = {
    ("greenhouse", "openai", "openai"): [("ashby", "OpenAI")],
    ("lever", "anthropic", "anthropic"): [("ashby", "Anthropic")],
    ("lever", "cohere", "cohere"): [("ashby", "Cohere")],
    ("greenhouse", "perplexity ai", "perplexity"): [("ashby", "Perplexity")],
    ("greenhouse", "perplexity ai", "perplexityai"): [("ashby", "Perplexity")],
    ("greenhouse", "runway ml", "runwayml"): [("ashby", "Runway")],
    ("greenhouse", "runway ml", "runway"): [("ashby", "Runway")],
    ("greenhouse", "together ai", "together-ai"): [("greenhouse", "togetherai")],
    ("lever", "stability ai", "stability-ai"): [("greenhouse", "stabilityai")],
    ("lever", "ramp", "ramp"): [("ashby", "Ramp")],
}


def _norm(value: str | None) -> str:
    return (value or "").strip().lower()


def get_ats_slug_aliases(company: str, ats: str, slug: str) -> list[tuple[str, str]]:
    """Return fallback `(ats, slug)` candidates for known stale ATS targets."""
    key = (_norm(ats), _norm(company), _norm(slug))
    candidates = list(_ALIASES.get(key, []))
    original = (_norm(ats), slug)
    return [(cand_ats, cand_slug) for cand_ats, cand_slug in candidates if (_norm(cand_ats), cand_slug) != original]
