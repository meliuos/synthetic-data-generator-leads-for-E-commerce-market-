"""
Model registry — Phase 18.

Single source of truth for which model files exist and which one is
currently active. MLScorer reads get_active_model_path() at construction
time; make select-model writes ACTIVE_MODEL to swap the active version
without touching any Python code.

File layout:
    models/lead_scorer_lgbm.pkl      — v1 (Phase 11 baseline)
    models/lead_scorer_lgbm_v2.pkl   — v2 (Phase 18 augmented)
    models/ACTIVE_MODEL              — plain-text file: "v1" or "v2"
"""

from __future__ import annotations

from pathlib import Path

# Map version string → relative pkl path (relative to repo root).
MODELS: dict[str, str] = {
    "v1": "models/lead_scorer_lgbm.pkl",
    "v2": "models/lead_scorer_lgbm_v2.pkl",
}

_ACTIVE_MODEL_FILE = Path("models/ACTIVE_MODEL")
_FALLBACK_VERSION = "v1"


def get_active_version() -> str:
    """
    Return the currently active model version string ("v1" or "v2").

    Reads models/ACTIVE_MODEL; falls back to "v1" if the file is missing
    or contains an unrecognised value.
    """
    try:
        text = _ACTIVE_MODEL_FILE.read_text(encoding="utf-8").strip()
        if text in MODELS:
            return text
    except FileNotFoundError:
        pass
    return _FALLBACK_VERSION


def get_active_model_path() -> str:
    """Return the filesystem path string for the currently active model."""
    return MODELS[get_active_version()]


def set_active_model(version: str) -> None:
    """
    Write *version* to models/ACTIVE_MODEL, making it the active scorer.

    Raises
    ------
    ValueError
        If *version* is not a key in MODELS.
    FileNotFoundError
        If the corresponding .pkl file does not yet exist on disk.
    """
    if version not in MODELS:
        raise ValueError(
            f"Unknown model version '{version}'. Available: {sorted(MODELS)}"
        )
    model_path = Path(MODELS[version])
    if not model_path.exists():
        raise FileNotFoundError(
            f"Model file not found at {model_path}. "
            f"Run 'make train-augmented' to build the v2 model, "
            f"or 'make score-sessions' to build the v1 model."
        )
    _ACTIVE_MODEL_FILE.parent.mkdir(parents=True, exist_ok=True)
    _ACTIVE_MODEL_FILE.write_text(version + "\n", encoding="utf-8")
    print(f"Active model set to '{version}' → {model_path}")
