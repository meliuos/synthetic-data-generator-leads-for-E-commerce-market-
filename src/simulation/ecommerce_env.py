"""
EcommerceEnv — Phase 14.

Mesa 3.x Model that orchestrates BrowserAgent, BuyerAgent, and AbandonerAgent
instances, samples their behavioral profiles from analytics.synthetic_sessions,
and drives the simulation forward one step per simulated minute.
"""

from __future__ import annotations

import logging
import os
import random
from typing import Any

import mesa
import numpy as np

from src.simulation.agents import AbandonerAgent, BrowserAgent, BuyerAgent
from src.simulation.event_emitter import EventEmitter

log = logging.getLogger(__name__)

_DEFAULT_MIX: dict[str, float] = {"browser": 0.6, "buyer": 0.3, "abandoner": 0.1}

_AGENT_CLASSES = {
    "browser": BrowserAgent,
    "buyer": BuyerAgent,
    "abandoner": AbandonerAgent,
}


def _ch_client():
    try:
        import clickhouse_connect
    except ImportError as exc:
        raise ImportError(
            "clickhouse-connect is required. "
            "Install it with: pip install -r requirements-sim.txt"
        ) from exc

    return clickhouse_connect.get_client(
        host=os.getenv("CLICKHOUSE_HOST", "localhost"),
        port=int(os.getenv("CLICKHOUSE_PORT", "8123")),
        username=os.getenv("CLICKHOUSE_USER", "analytics"),
        password=os.getenv("CLICKHOUSE_PASSWORD", "analytics_password"),
        database=os.getenv("CLICKHOUSE_DATABASE", "analytics"),
    )


def _sample_profiles(n: int) -> list[dict]:
    """
    Pull n random rows from analytics.synthetic_sessions.
    Falls back to minimal default profiles if the table is empty or unreachable.
    """
    try:
        ch = _ch_client()
        result = ch.query(
            f"""
            SELECT
                session_id, page_views, product_views, add_to_cart_count,
                purchase_count, search_count, max_scroll_pct,
                session_duration_seconds, distinct_products_viewed,
                cart_abandoned, primary_category,
                coalesce(ml_lead_score, 0.3) AS ml_lead_score
            FROM analytics.synthetic_sessions
            ORDER BY rand()
            LIMIT {n}
            """
        )
        cols = result.column_names
        profiles = [dict(zip(cols, row)) for row in result.result_rows]
        if not profiles:
            raise ValueError("analytics.synthetic_sessions is empty — run make generate-synthetic first")
        while len(profiles) < n:
            profiles += profiles
        return profiles[:n]
    except Exception as exc:
        log.warning("Could not sample profiles from ClickHouse (%s). Using defaults.", exc)
        return [{"session_duration_seconds": 60, "page_views": 3, "ml_lead_score": 0.3}] * n


class EcommerceEnv(mesa.Model):
    """
    Agent-based e-commerce traffic simulator (Mesa 3.x API).

    Parameters
    ----------
    n_agents : int
        Total number of visitor agents to create.
    agent_mix : dict[str, float]
        Fraction of each agent type. Values must sum to 1.
        Keys: "browser", "buyer", "abandoner".
    duration_minutes : int
        Number of simulated minutes to run (one Mesa step = one minute).
    seed : int
        Random seed for reproducibility.
    dry_run : bool
        If True, events are counted but not sent to Redpanda.
    """

    def __init__(
        self,
        n_agents: int = 1_000,
        agent_mix: dict[str, float] | None = None,
        duration_minutes: int = 60,
        seed: int = 42,
        dry_run: bool = False,
    ) -> None:
        super().__init__(seed=seed)
        self.n_agents = n_agents
        self.agent_mix = agent_mix or _DEFAULT_MIX
        self.duration_minutes = duration_minutes
        self.dry_run = dry_run

        random.seed(seed)
        np.random.seed(seed)

        self.emitter = EventEmitter(dry_run=dry_run)

        log.info("Sampling %d behavioral profiles from analytics.synthetic_sessions …", n_agents)
        profiles = _sample_profiles(n_agents)

        self._create_agents(profiles)
        log.info(
            "Initialised %d agents (%s)",
            n_agents,
            ", ".join(f"{k}={v:.0%}" for k, v in self.agent_mix.items()),
        )

    # ------------------------------------------------------------------
    # Mesa 3.x interface
    # ------------------------------------------------------------------

    def step(self) -> None:
        self.agents.shuffle_do("step")

    def run(self, duration_minutes: int | None = None) -> dict[str, Any]:
        steps = duration_minutes if duration_minutes is not None else self.duration_minutes
        log.info("Running simulation for %d simulated minutes …", steps)
        for _ in range(steps):
            self.step()

        self.emitter.flush()
        self.emitter.close()

        buyers = list(self.agents_by_type[BuyerAgent])
        converters = [a for a in buyers if a._purchased]
        conv_rate = len(converters) / len(buyers) if buyers else 0.0

        summary = {
            "total_events": self.emitter.total_emitted,
            "n_agents": self.n_agents,
            "simulated_minutes": steps,
            "conversion_rate": round(conv_rate, 4),
            "dry_run": self.dry_run,
        }
        log.info("Simulation complete: %s", summary)
        return summary

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _create_agents(self, profiles: list[dict]) -> None:
        mix_cumulative: list[tuple[float, str]] = []
        cumsum = 0.0
        for kind, frac in self.agent_mix.items():
            cumsum += frac
            mix_cumulative.append((cumsum, kind))

        for profile in profiles:
            r = random.random()
            kind = next(k for threshold, k in mix_cumulative if r <= threshold)
            cls = _AGENT_CLASSES[kind]
            cls(model=self, profile=profile)
