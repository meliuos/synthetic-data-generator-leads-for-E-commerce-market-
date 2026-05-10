"""
Ollama health check — Phase 15.

Verifies that Ollama is reachable, the target model is pulled, and that
a short inference round-trip succeeds. Run this before using any AI features.

Usage:
    python scripts/test_llm.py

Setup (if Ollama is not running):
    1. Install Ollama:  https://ollama.com/download
    2. Start server:    ollama serve
    3. Pull model:      ollama pull qwen2.5:7b
    4. Re-run this script.

Environment variables:
    OLLAMA_HOST   default: http://localhost:11434
    LLM_MODEL     default: qwen2.5:7b
"""

from __future__ import annotations

import sys
import os
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.ai.llm_client import check_ollama_health, generate_script, _OLLAMA_HOST, _LLM_MODEL


def main() -> int:
    print(f"Ollama host : {_OLLAMA_HOST}")
    print(f"Target model: {_LLM_MODEL}")
    print()

    # --- connectivity check -----------------------------------------------
    print("Checking Ollama connectivity …")
    health = check_ollama_health()

    if health["status"] != "ok":
        print(f"  ERROR: {health['error']}")
        print()
        print("Fix: start Ollama with  ollama serve")
        return 1

    print(f"  OK — Ollama reachable. Available models: {health['available_models']}")

    if not health["model_ready"]:
        print(f"  WARNING: model '{_LLM_MODEL}' not found locally.")
        print(f"  Run:  ollama pull {_LLM_MODEL}")
        return 1

    print(f"  OK — model '{_LLM_MODEL}' is ready.")
    print()

    # --- inference round-trip ----------------------------------------------
    print("Running inference smoke test (short prompt) …")
    system_prompt = "You are a concise assistant. Reply in one sentence only."
    user_prompt = "What is the capital of France?"

    try:
        result = generate_script(system_prompt, user_prompt)
    except Exception as exc:
        print(f"  ERROR: {exc}")
        return 1

    print(f"  OK — response received in {result.latency_ms}ms")
    print(f"  Model    : {result.model}")
    print(f"  Response : {result.text[:120]}")
    print(f"  Lengths  : prompt={result.prompt_length} chars, response={result.response_length} chars")
    print()
    print("All checks passed. Ollama + Qwen2.5:7b is ready for AI script generation.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
