"""Mode-specific heatmap helpers for the Streamlit dashboard."""

from __future__ import annotations

from typing import Any

import pandas as pd

from heatmap_plotly import build_heatmap_overlay_figure


BIN_STEP_PCT = 5


def _full_width_bins() -> list[int]:
    return list(range(0, 101, BIN_STEP_PCT))


def _expand_scroll_dataframe(dataframe: Any) -> Any:
    """Expand scroll bins across the full screenshot width to form bands."""

    if getattr(dataframe, "empty", True):
        return dataframe

    if not {"y_bin_pct", "event_count"}.issubset(set(getattr(dataframe, "columns", []))):
        return dataframe

    aggregated_rows = (
        dataframe.groupby("y_bin_pct", as_index=False)["event_count"].max().sort_values("y_bin_pct")
    )
    full_width_rows: list[dict[str, float]] = []
    for row in aggregated_rows.itertuples(index=False):
        for x_bin in _full_width_bins():
            full_width_rows.append(
                {
                    "x_bin_pct": float(x_bin),
                    "y_bin_pct": float(getattr(row, "y_bin_pct")),
                    "event_count": float(getattr(row, "event_count")),
                }
            )

    return pd.DataFrame(full_width_rows)


def build_click_heatmap_figure(screenshot_path: str, dataframe: Any, viewport_width: int, viewport_height: int, *, title: str) -> Any:
    return build_heatmap_overlay_figure(
        screenshot_path,
        dataframe,
        viewport_width,
        viewport_height,
        title=title,
    )


def build_hover_heatmap_figure(screenshot_path: str, dataframe: Any, viewport_width: int, viewport_height: int, *, title: str) -> Any:
    return build_heatmap_overlay_figure(
        screenshot_path,
        dataframe,
        viewport_width,
        viewport_height,
        title=title,
    )


def build_scroll_heatmap_figure(screenshot_path: str, dataframe: Any, viewport_width: int, viewport_height: int, *, title: str) -> Any:
    scroll_dataframe = _expand_scroll_dataframe(dataframe)
    return build_heatmap_overlay_figure(
        screenshot_path,
        scroll_dataframe,
        viewport_width,
        viewport_height,
        title=title,
    )


def build_heatmap_figure_for_mode(
    mode: str,
    screenshot_path: str,
    dataframe: Any,
    viewport_width: int,
    viewport_height: int,
    *,
    title: str,
) -> Any:
    normalized_mode = mode.strip().lower()
    if normalized_mode == "scroll":
        return build_scroll_heatmap_figure(screenshot_path, dataframe, viewport_width, viewport_height, title=title)
    if normalized_mode in {"mousemove", "hover"}:
        return build_hover_heatmap_figure(screenshot_path, dataframe, viewport_width, viewport_height, title=title)
    return build_click_heatmap_figure(screenshot_path, dataframe, viewport_width, viewport_height, title=title)


__all__ = [
    "build_click_heatmap_figure",
    "build_heatmap_figure_for_mode",
    "build_hover_heatmap_figure",
    "build_scroll_heatmap_figure",
]