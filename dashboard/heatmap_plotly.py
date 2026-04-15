"""Plotly helpers for screenshot-backed heatmap overlays.

The dashboard passes in a cached screenshot path and ClickHouse aggregate data.
This module turns those inputs into a single Plotly figure that Streamlit can
render directly with ``st.plotly_chart``.
"""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any, Iterable, Sequence

import plotly.graph_objects as go


BIN_STEP_PCT = 5


def _image_to_data_uri(image_path: Path) -> str:
    image_bytes = image_path.read_bytes()
    encoded_bytes = base64.b64encode(image_bytes).decode("ascii")
    return f"data:image/png;base64,{encoded_bytes}"


def _coerce_bins(values: Iterable[Any]) -> list[int]:
    bins = {int(round(float(value))) for value in values}
    return sorted(bin_value for bin_value in bins if 0 <= bin_value <= 100)


def _viewport_dimension(actual_dimension: int | None, fallback_dimension: int) -> int:
    if actual_dimension and actual_dimension > 0:
        return int(actual_dimension)
    return int(fallback_dimension)


def _resolve_grid_dimensions(dataframe: Any) -> tuple[list[int], list[int]]:
    if getattr(dataframe, "empty", True):
        bins = list(range(0, 101, BIN_STEP_PCT))
        return bins, bins

    x_values = dataframe["x_bin_pct"].tolist() if "x_bin_pct" in dataframe else []
    y_values = dataframe["y_bin_pct"].tolist() if "y_bin_pct" in dataframe else []

    x_bins = _coerce_bins(x_values) if x_values else list(range(0, 101, BIN_STEP_PCT))
    y_bins = _coerce_bins(y_values) if y_values else list(range(0, 101, BIN_STEP_PCT))

    if not x_bins:
        x_bins = list(range(0, 101, BIN_STEP_PCT))
    if not y_bins:
        y_bins = list(range(0, 101, BIN_STEP_PCT))

    return x_bins, y_bins


def _build_density_matrix(dataframe: Any, x_bins: Sequence[int], y_bins: Sequence[int]) -> list[list[float]]:
    density_matrix = [[0.0 for _ in x_bins] for _ in y_bins]
    if getattr(dataframe, "empty", True):
        return density_matrix

    x_index = {bin_value: index for index, bin_value in enumerate(x_bins)}
    y_index = {bin_value: index for index, bin_value in enumerate(y_bins)}

    for row in dataframe.itertuples(index=False):
        x_value = int(round(float(getattr(row, "x_bin_pct", 0))))
        y_value = int(round(float(getattr(row, "y_bin_pct", 0))))
        if x_value not in x_index or y_value not in y_index:
            continue

        count_value = float(getattr(row, "event_count", 0) or 0)
        density_matrix[y_index[y_value]][x_index[x_value]] = count_value

    return density_matrix


def build_heatmap_overlay_figure(
    screenshot_path: str | Path,
    dataframe: Any,
    viewport_width: int,
    viewport_height: int,
    *,
    title: str = "Click heatmap",
) -> go.Figure:
    """Build a Plotly overlay figure from a cached screenshot and heatmap bins."""

    screenshot_file = Path(screenshot_path)
    if not screenshot_file.exists():
        raise FileNotFoundError(f"Screenshot not found: {screenshot_file}")

    image_source = _image_to_data_uri(screenshot_file)
    image_width = _viewport_dimension(None, viewport_width)
    image_height = _viewport_dimension(None, viewport_height)

    try:
        from PIL import Image

        with Image.open(screenshot_file) as screenshot_image:
            image_width, image_height = screenshot_image.size
    except Exception:
        pass

    x_bins, y_bins = _resolve_grid_dimensions(dataframe)
    density_matrix = _build_density_matrix(dataframe, x_bins, y_bins)

    x_positions = [bin_value * image_width / 100 for bin_value in x_bins]
    y_positions = [bin_value * image_height / 100 for bin_value in y_bins]

    figure = go.Figure(
        data=[
            go.Heatmap(
                x=x_positions,
                y=y_positions,
                z=density_matrix,
                zsmooth=False,
                colorscale="Turbo",
                opacity=0.65,
                hoverongaps=False,
                showscale=True,
                colorbar=dict(title="events"),
                hovertemplate="x=%{x:.0f}px<br>y=%{y:.0f}px<br>count=%{z}<extra></extra>",
            )
        ]
    )

    figure.add_layout_image(
        dict(
            source=image_source,
            xref="x",
            yref="y",
            x=0,
            y=0,
            sizex=image_width,
            sizey=image_height,
            xanchor="left",
            yanchor="top",
            sizing="stretch",
            layer="below",
        )
    )
    figure.update_layout(
        title=title,
        margin=dict(l=0, r=0, t=48, b=0),
        template="plotly_white",
        height=max(420, int(image_height * 0.78)),
        showlegend=False,
    )
    figure.update_xaxes(range=[0, image_width], visible=False, fixedrange=True, constrain="domain")
    figure.update_yaxes(
        range=[image_height, 0],
        visible=False,
        fixedrange=True,
        scaleanchor="x",
        scaleratio=1,
        constrain="domain",
    )
    return figure


__all__ = ["build_heatmap_overlay_figure"]