"""
OpenRouter health check — Phase 15.

Verifies that the OpenRouter API is reachable, the target model is available,
and that a short inference round-trip succeeds.

Usage:
    python scripts/test_llm.py

Setup:
    1. Create a free account at https://openrouter.ai
    2. Generate an API key at https://openrouter.ai/keys
    3. Set OPENROUTER_API_KEY in your environment or .env file
    4. Re-run this script.

Environment variables:
    OPENROUTER_API_KEY   required
    LLM_MODEL            default: meta-llama/llama-3.1-8b-instruct:free
    LLM_TIMEOUT          default: 60 (seconds)
"""

from __future__ import annotations

import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.ai.llm_client import check_openrouter_health, generate_script, _LLM_MODEL


def main() -> int:
    api_key_set = bool(os.getenv("OPENROUTER_API_KEY", ""))
    print(f"OPENROUTER_API_KEY : {'set' if api_key_set else 'NOT SET'}")
    print(f"Target model       : {_LLM_MODEL}")
    print()

    if not api_key_set:
        print("ERROR: OPENROUTER_API_KEY is not set.")
        print("Get a free key at https://openrouter.ai/keys and export it:")
        print("  export OPENROUTER_API_KEY=sk-or-v1-...")
        return 1

    # --- connectivity + model check -----------------------------------------
    print("Checking OpenRouter connectivity …")
    health = check_openrouter_health()

    if health["status"] != "ok":
        print(f"  ERROR: {health['error']}")
        return 1

    print(f"  OK — OpenRouter reachable. {health['available_count']} models listed.")

    if not health["model_ready"]:
        print(f"  WARNING: model '{_LLM_MODEL}' not found in model list.")
        print("  It may still work — proceeding to inference test.")
    else:
        print(f"  OK — model '{_LLM_MODEL}' is available.")

    print()

    # --- inference round-trip -----------------------------------------------
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
    print(f"All checks passed. OpenRouter + {_LLM_MODEL} is ready for AI script generation.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
