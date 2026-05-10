"""
LLM client — Phase 15 (Ollama backend).

Fully local, zero-cost inference via Ollama HTTP API. No vendor lock-in —
swap OLLAMA_HOST / LLM_MODEL env vars to point at any compatible endpoint.

Configuration (environment variables):
    OLLAMA_HOST   Ollama base URL  (default: http://localhost:11434)
    LLM_MODEL     Model tag        (default: qwen2.5:7b)
    LLM_TIMEOUT   Request timeout in seconds (default: 30)
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass

_OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
_LLM_MODEL = os.getenv("LLM_MODEL", "qwen2.5:7b")
_TIMEOUT_S = int(os.getenv("LLM_TIMEOUT", "30"))


class LLMTimeoutError(Exception):
    """Raised when the Ollama inference call exceeds LLM_TIMEOUT seconds."""


@dataclass
class ScriptResult:
    text: str
    model: str
    latency_ms: int
    prompt_length: int
    response_length: int


def generate_script(system_prompt: str, user_prompt: str) -> ScriptResult:
    """
    Generate a sales script using local Ollama inference.

    Combines system_prompt and user_prompt into a single chat request.
    Uses the /api/chat endpoint (supports system role natively).

    Raises
    ------
    LLMTimeoutError
        When the request exceeds LLM_TIMEOUT seconds.
    ImportError
        When httpx is not installed.
    RuntimeError
        When Ollama returns a non-200 response.
    """
    try:
        import httpx
    except ImportError as exc:
        raise ImportError(
            "httpx is required. Install it with: pip install -r requirements-ai.txt"
        ) from exc

    payload = {
        "model": _LLM_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "stream": False,
        "options": {
            "temperature": 0.7,
            "num_predict": 512,
        },
    }

    t0 = time.monotonic()
    try:
        with httpx.Client(timeout=_TIMEOUT_S) as client:
            response = client.post(
                f"{_OLLAMA_HOST}/api/chat",
                json=payload,
            )
    except httpx.TimeoutException as exc:
        raise LLMTimeoutError(
            f"Ollama inference timed out after {_TIMEOUT_S}s. "
            "Is Ollama running? Try: ollama serve"
        ) from exc

    if response.status_code != 200:
        raise RuntimeError(
            f"Ollama returned HTTP {response.status_code}: {response.text[:200]}"
        )

    latency_ms = int((time.monotonic() - t0) * 1000)
    data = response.json()
    text = data.get("message", {}).get("content", "").strip()

    return ScriptResult(
        text=text,
        model=data.get("model", _LLM_MODEL),
        latency_ms=latency_ms,
        prompt_length=len(system_prompt) + len(user_prompt),
        response_length=len(text),
    )


def check_ollama_health() -> dict:
    """
    Ping Ollama and return a status dict.
    Useful for the health-check script and FastAPI /health endpoint.
    """
    try:
        import httpx
        with httpx.Client(timeout=5) as client:
            r = client.get(f"{_OLLAMA_HOST}/api/tags")
        models = [m["name"] for m in r.json().get("models", [])]
        return {
            "status": "ok",
            "ollama_host": _OLLAMA_HOST,
            "available_models": models,
            "target_model": _LLM_MODEL,
            "model_ready": _LLM_MODEL in models,
        }
    except Exception as exc:
        return {
            "status": "error",
            "ollama_host": _OLLAMA_HOST,
            "error": str(exc),
            "model_ready": False,
        }
