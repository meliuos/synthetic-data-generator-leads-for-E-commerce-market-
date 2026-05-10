"""
Event emitter — Phase 14.

Thin wrapper over the kafka-python producer that mirrors the RudderStack
JS tracker's event shape so the same ClickHouse Materialized View processes
simulated events identically to real browser traffic.

Events are buffered in memory and flushed every FLUSH_EVERY records or
every FLUSH_INTERVAL_S seconds (whichever comes first).
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any

log = logging.getLogger(__name__)

FLUSH_EVERY = 100
FLUSH_INTERVAL_S = 1.0

_TOPIC = os.getenv("REDPANDA_TOPIC", "rudder_events")
_BOOTSTRAP = os.getenv("REDPANDA_BROKERS", "localhost:19092")


class EventEmitter:
    """
    Buffers events and flushes them to Redpanda as JSON records.

    If Redpanda is unavailable (e.g., in dry-run or unit-test contexts),
    set dry_run=True — events are counted but not sent.
    """

    def __init__(self, dry_run: bool = False) -> None:
        self.dry_run = dry_run
        self._buffer: list[dict] = []
        self._last_flush = time.monotonic()
        self._total_emitted = 0
        self._producer = None

        if not dry_run:
            self._producer = self._make_producer()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def emit(
        self,
        event_type: str,
        properties: dict[str, Any],
        *,
        anonymous_id: str,
        session_id: str,
    ) -> None:
        record = {
            "messageId": uuid.uuid4().hex,
            "type": "track",
            "event": event_type,
            "anonymousId": anonymous_id,
            "properties": {
                **properties,
                "session_id": session_id,
                "event_type": event_type,
                "simulated": True,
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "sentAt": datetime.now(timezone.utc).isoformat(),
        }
        self._buffer.append(record)

        now = time.monotonic()
        if len(self._buffer) >= FLUSH_EVERY or (now - self._last_flush) >= FLUSH_INTERVAL_S:
            self.flush()

    def flush(self) -> None:
        if not self._buffer:
            return

        batch = self._buffer
        self._buffer = []
        self._last_flush = time.monotonic()

        if self.dry_run:
            self._total_emitted += len(batch)
            log.debug("[dry-run] Would emit %d events", len(batch))
            return

        try:
            for record in batch:
                self._producer.send(_TOPIC, value=record)
            self._producer.flush()
            self._total_emitted += len(batch)
            log.debug("Flushed %d events to %s", len(batch), _TOPIC)
        except Exception as exc:
            log.error("Redpanda flush failed: %s — %d events dropped", exc, len(batch))

    def close(self) -> None:
        self.flush()
        if self._producer is not None:
            try:
                self._producer.close()
            except Exception:
                pass

    @property
    def total_emitted(self) -> int:
        return self._total_emitted

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _make_producer():
        try:
            from kafka import KafkaProducer
        except ImportError as exc:
            raise ImportError(
                "kafka-python is required for the simulation engine. "
                "Install it with: pip install -r requirements-sim.txt"
            ) from exc

        return KafkaProducer(
            bootstrap_servers=_BOOTSTRAP.split(","),
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            linger_ms=10,
            batch_size=16_384,
            retries=3,
        )
