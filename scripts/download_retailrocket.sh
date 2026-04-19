#!/usr/bin/env bash
set -euo pipefail

DATA_DIR=${RETAILROCKET_DATA_DIR:-data/retailrocket}
DATASET=${RETAILROCKET_KAGGLE_DATASET:-retailrocket/ecommerce-dataset}

if ! command -v kaggle >/dev/null 2>&1; then
  echo "kaggle CLI not found. Install with: python3 -m pip install kaggle" >&2
  exit 1
fi

if [[ ! -f "$HOME/.kaggle/kaggle.json" ]]; then
  echo "Missing Kaggle credentials at ~/.kaggle/kaggle.json" >&2
  exit 1
fi

mkdir -p "$DATA_DIR"
find "$DATA_DIR" -mindepth 1 -maxdepth 1 -type f ! -name "README.md" -delete

echo "Downloading Retailrocket dataset from Kaggle..."
kaggle datasets download -d "$DATASET" -p "$DATA_DIR" --force --unzip

# Keep only the four CSV files required by this phase.
EXPECTED=(
  "events.csv"
  "item_properties_part1.csv"
  "item_properties_part2.csv"
  "category_tree.csv"
)

for file in "${EXPECTED[@]}"; do
  if [[ ! -f "$DATA_DIR/$file" ]]; then
    echo "Missing expected file after download: $file" >&2
    exit 1
  fi
done

find "$DATA_DIR" -mindepth 1 -maxdepth 1 -type f \
  ! -name "events.csv" \
  ! -name "item_properties_part1.csv" \
  ! -name "item_properties_part2.csv" \
  ! -name "category_tree.csv" \
  ! -name "README.md" -delete

extra_count=$(find "$DATA_DIR" -mindepth 1 -maxdepth 1 -type f \
  ! -name "events.csv" \
  ! -name "item_properties_part1.csv" \
  ! -name "item_properties_part2.csv" \
  ! -name "category_tree.csv" \
  ! -name "README.md" | wc -l | tr -d '[:space:]')

if [[ "$extra_count" != "0" ]]; then
  echo "Unexpected extra files found in $DATA_DIR" >&2
  exit 1
fi

echo "Retailrocket CSV files downloaded to $DATA_DIR"
ls -1 "$DATA_DIR" | sed '/^README.md$/d'
