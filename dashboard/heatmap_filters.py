"""Shared URL filter helpers for Phase 4 heatmap queries."""

from __future__ import annotations

from typing import Any, Dict, Tuple


def normalize_url_filter(selected_url: str, wildcard_filter: str | None = None) -> str:
    """Return the active URL filter used by the dashboard and query layer."""

    wildcard_value = (wildcard_filter or "").strip()
    if wildcard_value:
        return wildcard_value
    return (selected_url or "").strip()


def _escape_like_value(value: str) -> str:
    escaped = value.replace("\\", "\\\\")
    escaped = escaped.replace("%", r"\%")
    escaped = escaped.replace("_", r"\_")
    return escaped


def build_url_predicate(url_filter: str) -> Tuple[str, Dict[str, Any]]:
    """Translate a URL filter into a ClickHouse predicate and parameters."""

    normalized = (url_filter or "").strip()
    if not normalized:
        raise ValueError("url_filter is required")

    if "*" in normalized:
        like_pattern = _escape_like_value(normalized).replace("*", "%")
        return "page_url LIKE %(page_url_like)s ESCAPE '\\\\'", {"page_url_like": like_pattern}

    return "page_url = %(page_url_exact)s", {"page_url_exact": normalized}


__all__ = ["build_url_predicate", "normalize_url_filter"]