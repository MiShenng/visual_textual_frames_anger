# Source Inventory

This folder was assembled from local project files to match the repository structure for `MiShenng/visual_textual_frames_anger`.

## Included for Public Upload

- `data/processed/README.md`: note explaining why row-level processed CSV files are not included.
- `data/raw/README.md`: note explaining that raw materials remain local-only.
- `scripts/`: crawler, transcription/preprocessing, frame extraction, visual/textual frame classification, anger detection, and analysis scripts.
- `results/tables/`: aggregate descriptive, crosstab, ANOVA/regression, robustness, and model-result tables.
- `results/figures/`: frame distribution, crosstab heatmap, anger-rate, regression, and BERT classifier figures.
- `docs/`: analysis reports and manuscript draft materials.
- `docs/manuscript/`: paper PDF and LaTeX source for the visual/textual frames and anger study.

## Local Only

- `data/raw/`: symlinks to raw videos, raw comments, comment-level prediction files, extracted frames, and sample materials. This directory is ignored by Git.
- `data/processed/*.csv`: row-level processed files containing video IDs, author names, titles, local paths, or other platform-level identifiers.
- `results/tables/top30_videos_by_anger_rate.csv`: ranked row-level table containing platform video IDs, author names, and titles.
- `scripts/crawler/` runtime files: `.env`, login states, SQLite databases, raw JSON exports, videos, logs, browser profiles, and snapshots are excluded from the public package.

## Notes

Raw videos, user comments, extracted frames, local paths, and row-level video records should not be published in the public repository. The public materials document the workflow and aggregate results.
