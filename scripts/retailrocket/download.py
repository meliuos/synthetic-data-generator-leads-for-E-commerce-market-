#!/usr/bin/env python3
import os
import sys
import logging
from pathlib import Path
from kaggle.api.kaggle_api_extended import KaggleApi

DATA_DIR = os.getenv("RETAILROCKET_DATA_DIR", "data/retailrocket")
DATASET = os.getenv("RETAILROCKET_KAGGLE_DATASET", "retailrocket/ecommerce-dataset")

EXPECTED_FILES = {
    "events.csv",
    "item_properties_part1.csv",
    "item_properties_part2.csv",
    "category_tree.csv",
}

def main():
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    
    kaggle_json = Path.home() / ".kaggle" / "kaggle.json"
    if kaggle_json.exists():
        logging.info(f"Using Kaggle credentials from {kaggle_json}")
    else:
        logging.info("No ~/.kaggle/kaggle.json found; attempting public dataset download via Kaggle CLI.")
        
    data_dir = Path(DATA_DIR)
    data_dir.mkdir(parents=True, exist_ok=True)
    
    # Clean up existing non-README files
    for p in data_dir.iterdir():
        if p.is_file() and p.name != "README.md":
            p.unlink()

    logging.info("Downloading Retailrocket dataset from Kaggle...")
    try:
        api = KaggleApi()
        api.authenticate()
        api.dataset_download_files(DATASET, path=str(data_dir), force=True, unzip=True)
    except Exception as e:
        logging.error(f"Failed to download dataset: {e}")
        sys.exit(1)

    # Verify and clean up
    found_files = set()
    for p in data_dir.iterdir():
        if p.is_file() and p.name != "README.md":
            if p.name in EXPECTED_FILES:
                found_files.add(p.name)
            else:
                p.unlink()

    missing = EXPECTED_FILES - found_files
    if missing:
        logging.error(f"Missing expected files after download: {', '.join(missing)}")
        sys.exit(1)

    logging.info(f"Retailrocket CSV files downloaded to {data_dir}:")
    for f in EXPECTED_FILES:
        logging.info(f" - {f}")

if __name__ == "__main__":
    main()
