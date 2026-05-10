"""
Prompt builder — Phase 15.

Renders per-tier Jinja2 templates into (system_prompt, user_prompt) pairs
ready for the Claude API. The system prompt is static per tier and eligible
for prompt caching; the user prompt carries the dynamic lead context.
"""

from __future__ import annotations

import json
from pathlib import Path

_TEMPLATES_DIR = Path(__file__).parent / "templates"
_MAX_PRODUCTS = 10
_VALID_TIERS = {"hot", "warm", "cold"}


def _load_template(tier: str) -> str:
    path = _TEMPLATES_DIR / f"{tier}.j2"
    if not path.exists():
        raise FileNotFoundError(f"Template not found: {path}")
    return path.read_text(encoding="utf-8").strip()


def build_prompt(lead_context: dict) -> tuple[str, str]:
    """
    Build (system_prompt, user_prompt) from a lead context dict.

    The system prompt is the full static tier instruction (cached by Claude).
    The user prompt is the dynamic lead context as structured JSON.

    Parameters
    ----------
    lead_context : dict
        Output of ``fetch_lead_context``. Must contain a ``score_tier`` key.

    Returns
    -------
    (system_prompt, user_prompt) : tuple[str, str]
    """
    tier = str(lead_context.get("score_tier", "cold")).lower()
    if tier not in _VALID_TIERS:
        tier = "cold"

    system_prompt = _load_template(tier)

    # Truncate viewed_products to guard against oversized prompts
    ctx = dict(lead_context)
    products = list(ctx.get("viewed_products") or [])
    if len(products) > _MAX_PRODUCTS:
        ctx["viewed_products"] = products[:_MAX_PRODUCTS]

    user_prompt = (
        "Write an outreach script for the following lead:\n\n"
        + json.dumps(ctx, indent=2, default=str)
    )

    return system_prompt, user_prompt
