"""
Simulation runner — Phase 14.

Instantiates EcommerceEnv, runs the agent-based simulation for the requested
duration, and prints a JSON summary to stdout.

Usage:
    python scripts/run_simulation.py [--n-agents 1000]
                                     [--duration-minutes 60]
                                     [--seed 42]
                                     [--agent-mix browser:0.6,buyer:0.3,abandoner:0.1]
                                     [--dry-run]

Environment variables (override docker-compose defaults):
    CLICKHOUSE_HOST      default: localhost
    CLICKHOUSE_PORT      default: 8123
    CLICKHOUSE_USER      default: analytics
    CLICKHOUSE_PASSWORD  default: analytics_password
    REDPANDA_BROKERS     default: localhost:19092
    REDPANDA_TOPIC       default: rudder_events
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.simulation.ecommerce_env import EcommerceEnv

log = logging.getLogger(__name__)


def _parse_mix(raw: str) -> dict[str, float]:
    """Parse 'browser:0.6,buyer:0.3,abandoner:0.1' into a dict."""
    result: dict[str, float] = {}
    for part in raw.split(","):
        kind, _, frac = part.strip().partition(":")
        result[kind.strip()] = float(frac.strip())
    total = sum(result.values())
    if abs(total - 1.0) > 0.01:
        raise ValueError(
            f"Agent mix fractions must sum to 1.0, got {total:.3f} for '{raw}'"
        )
    return result


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the Phase 14 agent-based e-commerce traffic simulation."
    )
    parser.add_argument(
        "--n-agents", type=int, default=1_000,
        help="Total number of visitor agents (default: 1000).",
    )
    parser.add_argument(
        "--duration-minutes", type=int, default=60,
        help="Simulated duration in minutes — one step per minute (default: 60).",
    )
    parser.add_argument(
        "--seed", type=int, default=42,
        help="Random seed for reproducibility (default: 42).",
    )
    parser.add_argument(
        "--agent-mix", type=str, default="browser:0.6,buyer:0.3,abandoner:0.1",
        help="Comma-separated agent type fractions (must sum to 1.0).",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Count events but do not send to Redpanda.",
    )
    return parser.parse_args()


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    args = _parse_args()

    try:
        agent_mix = _parse_mix(args.agent_mix)
    except ValueError as exc:
        log.error("Invalid --agent-mix: %s", exc)
        return 1

    env = EcommerceEnv(
        n_agents=args.n_agents,
        agent_mix=agent_mix,
        duration_minutes=args.duration_minutes,
        seed=args.seed,
        dry_run=args.dry_run,
    )

    try:
        summary = env.run()
    except Exception as exc:
        log.exception("Simulation failed: %s", exc)
        return 1

    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
