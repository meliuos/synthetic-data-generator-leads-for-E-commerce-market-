"""
AI script generation — Phase 15 public API.

Single entry point: build_script(anonymous_user_id) -> str

Orchestrates: fetch_lead_context → build_prompt → generate_script → log to ClickHouse.
Never raises — returns a user-facing error string on any recoverable failure so the
Streamlit dashboard cannot crash from a missing lead or inference error.

Backend: Ollama (local inference, zero API cost).
Configure via OLLAMA_HOST and LLM_MODEL environment variables.
"""

from __future__ import annotations

import logging
import os

from src.ai.lead_profiler import LeadNotFoundError, fetch_lead_context
from src.ai.llm_client import LLMTimeoutError, generate_script
from src.ai.prompt_builder import build_prompt

log = logging.getLogger(__name__)


def build_script(anonymous_user_id: str) -> str:
    """
    Generate an outreach script for the given lead.

    Returns the script text on success, or a descriptive error string on
    recoverable failure (missing lead, Ollama timeout, inference error).
    """
    try:
        context = fetch_lead_context(anonymous_user_id)
    except LeadNotFoundError:
        return (
            "No behavioral data found for this lead. "
            "Run 'make score-sessions' to populate scores."
        )
    except Exception as exc:
        log.exception("fetch_lead_context failed for %s", anonymous_user_id)
        return f"Could not load lead context: {exc}"

    try:
        system_prompt, user_prompt = build_prompt(context)
        result = generate_script(system_prompt, user_prompt)
    except LLMTimeoutError as exc:
        log.warning("LLM timeout for %s: %s", anonymous_user_id, exc)
        return (
            "Script generation timed out. "
            "Ensure Ollama is running: ollama serve && ollama pull qwen2.5:7b"
        )
    except Exception as exc:
        log.exception("generate_script failed for %s", anonymous_user_id)
        return f"Script generation failed: {exc}"

    _log_to_clickhouse(anonymous_user_id, context["score_tier"], result)
    return result.text


def _log_to_clickhouse(anonymous_user_id: str, tier: str, result) -> None:
    try:
        import clickhouse_connect

        ch = clickhouse_connect.get_client(
            host=os.getenv("CLICKHOUSE_HOST", "localhost"),
            port=int(os.getenv("CLICKHOUSE_PORT", "8123")),
            username=os.getenv("CLICKHOUSE_USER", "analytics"),
            password=os.getenv("CLICKHOUSE_PASSWORD", "analytics_password"),
            database=os.getenv("CLICKHOUSE_DATABASE", "analytics"),
        )
        ch.insert(
            "analytics.ai_script_log",
            [[
                anonymous_user_id,
                tier,
                result.model,
                result.prompt_length,
                0,  # cache_creation_tokens — N/A for local inference
                0,  # cache_read_tokens     — N/A for local inference
                result.response_length,
                0.0,  # cost_usd — always 0 for local inference
            ]],
            column_names=[
                "lead_id", "tier", "model",
                "prompt_tokens", "cache_creation_tokens", "cache_read_tokens",
                "output_tokens", "cost_usd",
            ],
        )
        log.debug(
            "Logged AI call: tier=%s model=%s latency=%dms prompt=%d chars response=%d chars",
            tier, result.model, result.latency_ms,
            result.prompt_length, result.response_length,
        )
    except Exception as exc:
        log.warning("Failed to log AI call to ClickHouse: %s", exc)
