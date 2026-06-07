## Overview

This repository contains the materials for the study:

**Should I Stay Calm: How Does the Combination of Visual and Textual Frames Influence Expressions of Anger in Short Video Comment Sections?**

Accepted by **AEJMC 2026, Visual Communication Division**.

## Abstract

This study examines how visual and textual frames in short videos are associated with expressions of anger in comment sections. Using a dataset of 449 Douyin videos related to China’s drug record sealing controversy and 419,126 user comments, the project combines computational visual frame identification, textual frame classification, and comment-level anger detection.

The analysis focuses on whether visual and textual frames tend to align within the same video, how different frame combinations correspond to levels of anger in comments, and whether the two modalities interact or contribute independently to emotional expression.

## Research Questions

This study asks:

1. How are visual and textual frames combined in short videos?
2. Do different combinations of visual and textual frames correspond to different levels of anger in comment sections?
3. Do visual and textual frames interact in shaping anger, or do they contribute independently?

## Data

The dataset includes:

- 449 Douyin videos
- 419,126 user comments
- Video-level visual frame labels
- Video-level textual frame labels
- Comment-level anger classification results

Due to platform policies and research ethics, raw video files and user comments are not publicly released in this repository.
Row-level processed files containing video IDs, author names, titles, local frame paths, or other platform-level identifiers are also excluded. This repository publishes aggregate result tables and figures for methodological transparency.

## Method

The study uses a computational mixed-method workflow:

- Representative frames were extracted from short videos.
- Visual frames were classified into intensifying, informational, and mitigating categories.
- Textual content was classified using the same frame categories.
- A fine-tuned BERT classifier was used to identify anger in user comments.
- Video-level anger rates were analyzed using two-way ANOVA and robustness checks.

## Main Findings

The study finds that visual and textual frames within individual videos tend to align rather than diverge. Different frame combinations are associated with significantly different levels of anger in comment sections. Two-way ANOVA shows that both visual and textual frames contribute independently to anger, while their interaction effect is not statistically significant.

These findings suggest that emotional responses in short video comment sections are jointly organized across visual and textual modalities, rather than being driven by a single channel.

## Repository Structure

```text
.
├── README.md
├── data/
│   ├── raw/
│   └── processed/
├── scripts/
│   ├── crawler/
│   ├── preprocessing/
│   ├── frame_extraction/
│   ├── frame_classification/
│   ├── anger_detection/
│   └── analysis/
├── results/
│   ├── tables/
│   └── figures/
└── docs/
    └── manuscript/
        ├── visual_textual_frames_anger_manuscript.pdf
        └── latex/
```

## Notes

Raw videos, comments, extracted frames, local paths, and row-level video records are not included. The public-facing materials are the preprocessing and analysis scripts, aggregate tables, figures, reports, manuscript PDF, and LaTeX source generated from the full paper text.
