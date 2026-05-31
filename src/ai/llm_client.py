"""
LLM client — OpenRouter backend.

Uses the OpenRouter OpenAI-compatible API for free-tier inference.
No local GPU or Ollama required — just an API key from openrouter.ai.

Configuration (environment variables):
    OPENROUTER_API_KEY   OpenRouter API key (required — get one free at openrouter.ai/keys)
    LLM_MODEL            Model ID  (default: meta-llama/llama-3.1-8b-instruct:free)
    LLM_TIMEOUT          Request timeout in seconds (default: 60)

Free models available on OpenRouter (verified May 2026):
    meta-llama/llama-3.3-70b-instruct:free   ← default
    meta-llama/llama-3.2-3b-instruct:free
    google/gemma-4-27b-it:free
    nvidia/nemotron-3-super-120b-a12b:free
    deepseek/deepseek-v4-flash:free
    qwen/qwen3-coder:free
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass

_OPENROUTER_BASE = "https://openrouter.ai/api/v1"
_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
_LLM_MODEL = os.getenv("LLM_MODEL", "nvidia/nemotron-nano-9b-v2:free")
_TIMEOUT_S = int(os.getenv("LLM_TIMEOUT", "60"))


class LLMTimeoutError(Exception):
    """Raised when the OpenRouter inference call exceeds LLM_TIMEOUT seconds."""


@dataclass
class ScriptResult:
    text: str
    model: str
    latency_ms: int
    prompt_length: int
    response_length: int


def generate_script(system_prompt: str, user_prompt: str) -> ScriptResult:
    """
    Generate a sales script via the OpenRouter API (OpenAI-compatible).

    Raises
    ------
    RuntimeError
        When OPENROUTER_API_KEY is not set, or when the API returns an error.
    LLMTimeoutError
        When the request exceeds LLM_TIMEOUT seconds.
    ImportError
        When httpx is not installed.
    """
    try:
        import httpx
    except ImportError as exc:
        raise ImportError(
            "httpx is required. Install it with: pip install -r requirements-ai.txt"
        ) from exc

    if not _API_KEY:
        raise RuntimeError(
            "OPENROUTER_API_KEY environment variable is not set. "
            "Get a free key at https://openrouter.ai/keys"
        )

    payload = {
        "model": _LLM_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "max_tokens": 512,
        "temperature": 0.7,
    }

    headers = {
        "Authorization": f"Bearer {_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/pfa-lead-intelligence",
        "X-Title": "PFA Lead Intelligence",
    }

    t0 = time.monotonic()
    try:
        with httpx.Client(timeout=_TIMEOUT_S) as client:
            response = client.post(
                f"{_OPENROUTER_BASE}/chat/completions",
                json=payload,
                headers=headers,
            )
    except httpx.TimeoutException as exc:
        raise LLMTimeoutError(
            f"OpenRouter inference timed out after {_TIMEOUT_S}s."
        ) from exc

    if response.status_code != 200:
        raise RuntimeError(
            f"OpenRouter returned HTTP {response.status_code}: {response.text[:300]}"
        )

    latency_ms = int((time.monotonic() - t0) * 1000)
    data = response.json()

    choices = data.get("choices", [])
    if not choices:
        raise RuntimeError(f"OpenRouter returned no choices: {data}")

    text = choices[0].get("message", {}).get("content", "").strip()
    actual_model = data.get("model", _LLM_MODEL)

    return ScriptResult(
        text=text,
        model=actual_model,
        latency_ms=latency_ms,
        prompt_length=len(system_prompt) + len(user_prompt),
        response_length=len(text),
    )


def check_openrouter_health() -> dict:
    """
    Ping OpenRouter and return a status dict.
    Used by the health-check script and dashboard panels.
    """
    if not _API_KEY:
        return {
            "status": "error",
            "error": "OPENROUTER_API_KEY is not set",
            "target_model": _LLM_MODEL,
            "model_ready": False,
        }

    try:
        import httpx
        with httpx.Client(timeout=10) as client:
            r = client.get(
                f"{_OPENROUTER_BASE}/models",
                headers={"Authorization": f"Bearer {_API_KEY}"},
            )
        if r.status_code == 200:
            model_ids = {m["id"] for m in r.json().get("data", [])}
            return {
                "status": "ok",
                "target_model": _LLM_MODEL,
                "model_ready": _LLM_MODEL in model_ids,
                "available_count": len(model_ids),
            }
        return {
            "status": "error",
            "error": f"HTTP {r.status_code}: {r.text[:100]}",
            "target_model": _LLM_MODEL,
            "model_ready": False,
        }
    except Exception as exc:
        return {
            "status": "error",
            "error": str(exc),
            "target_model": _LLM_MODEL,
            "model_ready": False,
        }


# Backward-compatible alias kept for any code that imported check_ollama_health
check_ollama_health = check_openrouter_health
