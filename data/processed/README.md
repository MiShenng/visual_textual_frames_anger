# Processed Data

`video_level_master_449.csv` is the final video-level table used by `scripts/analysis/run_analysis.R`.

It contains 449 unique Douyin videos and 19 columns:

| Columns | Content |
|---|---|
| `case_id`, `platform_video_id`, `video_url` | Repository case number, original platform ID, and canonical video link |
| `platform`, `author_name`, `title`, `published_at` | Original video metadata |
| `like_count`, `follower_count` | Engagement controls used in the controlled OLS model |
| `comment_count` | Collected platform comment count |
| `visual_main_arousal_label`, `visual_main_arousal_share` | Dominant visual frame and its time share |
| `text_arousal_label`, `text_arousal_confidence` | Dominant textual frame and coding confidence |
| `comment_count_effective`, `anger_count`, `anger_mean_score`, `anger_rate`, `high_anger_flag` | Comment-level anger measures aggregated to the video level |

The two frame-label columns use the manuscript terminology: `Intensifying`, `Informational`, and `Mitigating`.

The 449-row three-category frame table is the base source. `like_count` and `follower_count` were joined from the retained 449-row control table by unique `platform_video_id`. The source `share_url` field was empty for all retained videos, so `video_url` uses the canonical form `https://www.douyin.com/video/{platform_video_id}`.

All 449 rows contain a unique platform video ID, canonical video URL, author name, and publication time. Titles are available for 448 videos; the remaining source record had an empty title and is retained without imputation.
