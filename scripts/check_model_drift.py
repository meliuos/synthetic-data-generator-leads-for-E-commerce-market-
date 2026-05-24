"""
Phase 20-01 — CLI for model drift detection.

Computes Jensen-Shannon divergence between real and synthetic session
distributions and prints a JSON drift report to stdout.  Exits 1 if
any feature exceeds the fail threshold.

Usage:
    python scripts/check_model_drift.py [--threshold 0.15]
    make check-drift
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.monitoring.drift_detector import check_drift


def main() -> None:
    parser = argparse.ArgumentParser(description="Check model drift (JSD per feature).")
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.15,
        help="JSD above which a feature is flagged as 'fail' (default: 0.15)",
    )
    args = parser.parse_args()

    report = check_drift(threshold=args.threshold)

    output = {
        "checked_at": report.checked_at,
        "features_checked": report.features_checked,
        "status": report.status,
        "max_jsd": report.max_jsd,
        "features_drifted": report.features_drifted,
        "all_feature_jsd": report.all_feature_jsd,
    }
    print(json.dumps(output, indent=2))

    if report.status == "fail":
        sys.exit(1)


if __name__ == "__main__":
    main()
