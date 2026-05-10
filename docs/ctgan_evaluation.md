# CTGAN Evaluation Summary

**Generated:** 2026-05-10 00:02 UTC
**Training corpus:** 199,999 Retailrocket sessions
**Epochs:** 100
**Batch size:** 500
**Evaluation sample:** 5,000 synthetic rows
**JSD threshold:** < 0.1

## Jensen-Shannon Divergence per Feature

| Feature | JSD | Status |
|---------|-----|--------|
| `add_to_cart_count` | 0.3096 | FAIL |
| `score_tier` | 0.3069 | FAIL |
| `cart_abandoned` | 0.2509 | FAIL |
| `session_duration_seconds` | 0.2301 | FAIL |
| `product_views` | 0.1982 | FAIL |
| `distinct_products_viewed` | 0.1755 | FAIL |
| `primary_category` | 0.1606 | FAIL |
| `purchase_count` | 0.1460 | FAIL |
| `page_views` | 0.0000 | PASS |
| `search_count` | 0.0000 | PASS |
| `max_scroll_pct` | nan | FAIL |

## Conditional Sampling

Tested top-5 categories. All returned rows: YES.

## Files

- `models/ctgan_sessions.pkl` — trained CTGANSynthesizer (gitignored)
- `data/session_features.parquet` — training corpus (gitignored)
- `docs/ctgan_kde_plots.png` — marginal distribution plots

## Regeneration

```bash
make synth-setup
make ctgan-train
```