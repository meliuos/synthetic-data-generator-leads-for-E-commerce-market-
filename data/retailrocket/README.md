# Retailrocket Raw Dataset

This directory stores the four Kaggle CSV files used for Phase 7 import:

- events.csv
- item_properties_part1.csv
- item_properties_part2.csv
- category_tree.csv

## Notes

- These raw CSV files are ignored by git and must not be committed.
- Download with `make retailrocket-download`.
- Retailrocket has event types `view`, `addtocart`, `transaction` only.
- It does not provide direct `search` or `remove_from_cart` signals.
