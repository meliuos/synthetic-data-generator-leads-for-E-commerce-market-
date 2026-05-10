"""
Simulation agents — Phase 14.

Three Mesa 3.x agent types model distinct visitor archetypes:
  BrowserAgent   — page browsing only, no cart/purchase
  BuyerAgent     — browses → adds to cart → purchases (probabilistic)
  AbandonerAgent — adds to cart then exits without purchasing

Each agent is seeded with a behavioral profile sampled from
analytics.synthetic_sessions at init time via EcommerceEnv.
"""

from __future__ import annotations

import math
import random
import uuid
from typing import TYPE_CHECKING

import mesa
import numpy as np

if TYPE_CHECKING:
    from src.simulation.ecommerce_env import EcommerceEnv


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _dwell_seconds(profile: dict) -> float:
    """Draw page dwell from log-normal parameterised by session mean duration."""
    mean_s = max(profile.get("session_duration_seconds", 60), 1)
    sigma = 0.8
    mu = math.log(mean_s) - 0.5 * sigma ** 2
    return float(np.clip(np.random.lognormal(mu, sigma), 1.0, 600.0))


def _synthetic_product_id() -> str:
    return f"prod_{random.randint(1, 50_000)}"


# ---------------------------------------------------------------------------
# BrowserAgent
# ---------------------------------------------------------------------------

class BrowserAgent(mesa.Agent):
    """Pure browsing agent — never adds to cart or purchases."""

    conversion_probability = 0.0

    def __init__(self, model: "EcommerceEnv", profile: dict) -> None:
        super().__init__(model)
        self.profile = profile
        self.session_id = f"sim_{uuid.uuid4().hex[:8]}"
        self.anonymous_user_id = f"sim_user_{self.unique_id}"
        self._remaining_steps = max(int(profile.get("page_views", 3)), 1)

    def step(self) -> None:
        if self._remaining_steps <= 0:
            return

        self.model.emitter.emit(
            "page_view",
            {"session_id": self.session_id, "dwell_seconds": round(_dwell_seconds(self.profile), 2), "simulated": True},
            anonymous_id=self.anonymous_user_id,
            session_id=self.session_id,
        )

        if random.random() < 0.6:
            self.model.emitter.emit(
                "product_view",
                {"session_id": self.session_id, "product_id": _synthetic_product_id(), "simulated": True},
                anonymous_id=self.anonymous_user_id,
                session_id=self.session_id,
            )

        if random.random() < 0.4:
            self.model.emitter.emit(
                "scroll",
                {"session_id": self.session_id, "scroll_pct": round(random.uniform(10, 90), 1), "simulated": True},
                anonymous_id=self.anonymous_user_id,
                session_id=self.session_id,
            )

        self._remaining_steps -= 1


# ---------------------------------------------------------------------------
# BuyerAgent
# ---------------------------------------------------------------------------

class BuyerAgent(mesa.Agent):
    """High-intent visitor that converts with ML-scored probability."""

    def __init__(self, model: "EcommerceEnv", profile: dict) -> None:
        super().__init__(model)
        self.profile = profile
        self.session_id = f"sim_{uuid.uuid4().hex[:8]}"
        self.anonymous_user_id = f"sim_user_{self.unique_id}"
        self.conversion_probability = float(profile.get("ml_lead_score", 0.5) or 0.5)
        self._purchased = False
        self._cart_items: set[str] = set()
        self._remaining_steps = max(int(profile.get("page_views", 5)), 2)

    def step(self) -> None:
        if self._remaining_steps <= 0:
            return

        product_id = _synthetic_product_id()

        self.model.emitter.emit(
            "page_view",
            {"session_id": self.session_id, "dwell_seconds": round(_dwell_seconds(self.profile), 2), "simulated": True},
            anonymous_id=self.anonymous_user_id,
            session_id=self.session_id,
        )
        self.model.emitter.emit(
            "product_view",
            {"session_id": self.session_id, "product_id": product_id, "simulated": True},
            anonymous_id=self.anonymous_user_id,
            session_id=self.session_id,
        )

        if not self._cart_items or random.random() < 0.4:
            self._cart_items.add(product_id)
            self.model.emitter.emit(
                "add_to_cart",
                {"session_id": self.session_id, "product_id": product_id, "quantity": random.randint(1, 3), "simulated": True},
                anonymous_id=self.anonymous_user_id,
                session_id=self.session_id,
            )

        if not self._purchased and self._cart_items and random.random() < self.conversion_probability:
            self._purchased = True
            order_id = f"sim_order_{uuid.uuid4().hex[:8]}"
            for pid in list(self._cart_items):
                self.model.emitter.emit(
                    "purchase",
                    {"session_id": self.session_id, "product_id": pid, "order_id": order_id, "quantity": 1, "simulated": True},
                    anonymous_id=self.anonymous_user_id,
                    session_id=self.session_id,
                )

        self._remaining_steps -= 1


# ---------------------------------------------------------------------------
# AbandonerAgent
# ---------------------------------------------------------------------------

class AbandonerAgent(mesa.Agent):
    """Cart abandoner: views a product, adds to cart once, then exits."""

    conversion_probability = 0.0

    def __init__(self, model: "EcommerceEnv", profile: dict) -> None:
        super().__init__(model)
        self.profile = profile
        self.session_id = f"sim_{uuid.uuid4().hex[:8]}"
        self.anonymous_user_id = f"sim_user_{self.unique_id}"
        self._added_to_cart = False
        self._done = False

    def step(self) -> None:
        if self._done:
            return

        product_id = _synthetic_product_id()

        self.model.emitter.emit(
            "page_view",
            {"session_id": self.session_id, "dwell_seconds": round(_dwell_seconds(self.profile), 2), "simulated": True},
            anonymous_id=self.anonymous_user_id,
            session_id=self.session_id,
        )
        self.model.emitter.emit(
            "product_view",
            {"session_id": self.session_id, "product_id": product_id, "simulated": True},
            anonymous_id=self.anonymous_user_id,
            session_id=self.session_id,
        )

        if not self._added_to_cart:
            self._added_to_cart = True
            self.model.emitter.emit(
                "add_to_cart",
                {"session_id": self.session_id, "product_id": product_id, "quantity": 1, "simulated": True},
                anonymous_id=self.anonymous_user_id,
                session_id=self.session_id,
            )
            self._done = True
