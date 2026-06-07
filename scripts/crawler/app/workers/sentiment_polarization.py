from __future__ import annotations

import argparse
import csv
import json
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

URL_RE = re.compile(r"https?://\S+|www\.\S+", re.I)
MENTION_RE = re.compile(r"@[A-Za-z0-9_\-\u4e00-\u9fff]+")
TOPIC_RE = re.compile(r"#([^#\s]+)#?")

TARGET_TERMS = (
    "封存",
    "前科",
    "违法记录",
    "治安管理处罚法",
    "吸毒记录",
)

POSITIVE_WORDS = (
    "支持",
    "赞成",
    "同意",
    "合理",
    "理性",
    "有必要",
    "应该",
    "应当",
    "给机会",
    "改过自新",
    "人性化",
    "公平",
    "进步",
)

NEGATIVE_WORDS = (
    "反对",
    "不同意",
    "不该",
    "不能",
    "不应",
    "纵容",
    "洗白",
    "太轻",
    "太宽松",
    "荒唐",
    "离谱",
    "恶心",
    "愤怒",
    "严惩",
    "零容忍",
)

SUPPORT_PHRASES = (
    "支持封存",
    "赞成封存",
    "同意封存",
    "应该封存",
    "应当封存",
    "有必要封存",
    "前科封存有必要",
    "给一次机会",
    "改过自新",
    "教育挽救",
)

OPPOSE_PHRASES = (
    "反对封存",
    "不同意封存",
    "不该封存",
    "不能封存",
    "不应封存",
    "封存就是纵容",
    "封存等于洗白",
    "必须严惩",
    "零容忍",
    "从重处罚",
)

NEGATORS = (
    "不",
    "没",
    "无",
    "别",
    "未",
    "并不",
)


@dataclass
class CommentAnalysis:
    sentiment_score: float
    sentiment_label: str
    stance_score: float
    stance_label: str
    has_policy_target: bool


def _count_terms(text: str, terms: tuple[str, ...]) -> int:
    return sum(text.count(term) for term in terms)


def normalize_for_analysis(text: str) -> str:
    if not text:
        return ""
    value = text
    value = URL_RE.sub(" <URL> ", value)
    value = MENTION_RE.sub(" <MENTION> ", value)
    value = TOPIC_RE.sub(r" <TOPIC:\1> ", value)
    return re.sub(r"\s+", " ", value).strip()


def score_sentiment(text: str) -> tuple[float, str]:
    if not text:
        return 0.0, "neutral"
    pos = _count_terms(text, POSITIVE_WORDS)
    neg = _count_terms(text, NEGATIVE_WORDS)

    # Negation adjustment: e.g. "不支持" should reduce positive and increase negative.
    for negator in NEGATORS:
        for word in POSITIVE_WORDS:
            phrase = f"{negator}{word}"
            hits = text.count(phrase)
            if hits:
                pos -= hits
                neg += hits
        for word in NEGATIVE_WORDS:
            phrase = f"{negator}{word}"
            hits = text.count(phrase)
            if hits:
                neg -= hits
                pos += hits

    score = float(pos - neg)
    if "!" in text or "！" in text:
        score *= 1.1

    if score > 0.5:
        return score, "positive"
    if score < -0.5:
        return score, "negative"
    return score, "neutral"


def score_stance(text: str) -> tuple[float, str, bool]:
    if not text:
        return 0.0, "neutral", False

    has_target = any(term in text for term in TARGET_TERMS)
    support = _count_terms(text, SUPPORT_PHRASES)
    oppose = _count_terms(text, OPPOSE_PHRASES)

    # Fallback by generic cues when target appears.
    if has_target:
        support += _count_terms(text, POSITIVE_WORDS)
        oppose += _count_terms(text, NEGATIVE_WORDS)

    score = float(support - oppose)
    if not has_target and support == 0 and oppose == 0:
        return 0.0, "neutral", False
    if score >= 1.0:
        return score, "support", has_target
    if score <= -1.0:
        return score, "oppose", has_target
    return score, "neutral", has_target


def analyze_comment(text: str) -> CommentAnalysis:
    normalized = normalize_for_analysis(text)
    sentiment_score, sentiment_label = score_sentiment(normalized)
    stance_score, stance_label, has_target = score_stance(normalized)
    return CommentAnalysis(
        sentiment_score=sentiment_score,
        sentiment_label=sentiment_label,
        stance_score=stance_score,
        stance_label=stance_label,
        has_policy_target=has_target,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Sentiment + polarization analysis for cleaned comment CSVs.")
    parser.add_argument(
        "--input-dir",
        required=True,
        help="Directory containing cleaned_douyin_*.csv and comments_cleaned_60_master.csv",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Output directory (default: <input-dir>/sentiment_polarization_<timestamp>)",
    )
    return parser


def _safe_ratio(numerator: int | float, denominator: int | float) -> float:
    if not denominator:
        return 0.0
    return float(numerator) / float(denominator)


def run(input_dir: Path, output_dir: Path) -> dict:
    master_path = input_dir / "comments_cleaned_60_master.csv"
    if not master_path.exists():
        raise FileNotFoundError(f"missing input file: {master_path}")

    output_dir.mkdir(parents=True, exist_ok=True)
    comment_out = output_dir / "comments_sentiment_stance.csv"
    video_out = output_dir / "video_polarization_metrics.csv"
    overview_out = output_dir / "sentiment_polarization_overview.json"

    video_agg: dict[str, dict] = defaultdict(
        lambda: {
            "platform_video_id": "",
            "total_comments": 0,
            "level1_comments": 0,
            "level2_comments": 0,
            "sentiment_scores": [],
            "sentiment_count": Counter(),
            "stance_count": Counter(),
            "target_hit_count": 0,
        }
    )
    stance_counter = Counter()
    sentiment_counter = Counter()

    with master_path.open("r", encoding="utf-8", newline="") as f_in, comment_out.open(
        "w", encoding="utf-8", newline=""
    ) as f_out:
        reader = csv.DictReader(f_in)
        fieldnames = (reader.fieldnames or []) + [
            "text_analysis",
            "sentiment_score",
            "sentiment_label",
            "stance_score",
            "stance_label",
            "has_policy_target",
        ]
        writer = csv.DictWriter(f_out, fieldnames=fieldnames)
        writer.writeheader()

        for row in reader:
            text_value = row.get("text_clean") or row.get("text_raw") or ""
            analyzed = analyze_comment(text_value)

            row["text_analysis"] = normalize_for_analysis(text_value)
            row["sentiment_score"] = f"{analyzed.sentiment_score:.3f}"
            row["sentiment_label"] = analyzed.sentiment_label
            row["stance_score"] = f"{analyzed.stance_score:.3f}"
            row["stance_label"] = analyzed.stance_label
            row["has_policy_target"] = "1" if analyzed.has_policy_target else "0"
            writer.writerow(row)

            vid = row.get("platform_video_id", "")
            stats = video_agg[vid]
            stats["platform_video_id"] = vid
            stats["total_comments"] += 1
            if row.get("level") == "1":
                stats["level1_comments"] += 1
            elif row.get("level") == "2":
                stats["level2_comments"] += 1
            stats["sentiment_scores"].append(analyzed.sentiment_score)
            stats["sentiment_count"][analyzed.sentiment_label] += 1
            stats["stance_count"][analyzed.stance_label] += 1
            if analyzed.has_policy_target:
                stats["target_hit_count"] += 1

            sentiment_counter[analyzed.sentiment_label] += 1
            stance_counter[analyzed.stance_label] += 1

    with video_out.open("w", encoding="utf-8", newline="") as f_video:
        fields = [
            "platform_video_id",
            "total_comments",
            "level1_comments",
            "level2_comments",
            "sentiment_positive",
            "sentiment_negative",
            "sentiment_neutral",
            "sentiment_mean",
            "sentiment_std",
            "sentiment_non_neutral_ratio",
            "stance_support",
            "stance_oppose",
            "stance_neutral",
            "stance_target_hit_ratio",
            "stance_non_neutral_ratio",
            "stance_balance_index",
            "stance_confrontation_index",
        ]
        writer = csv.DictWriter(f_video, fieldnames=fields)
        writer.writeheader()

        for vid, stats in sorted(video_agg.items(), key=lambda x: x[0]):
            total = stats["total_comments"]
            pos = stats["sentiment_count"]["positive"]
            neg = stats["sentiment_count"]["negative"]
            neu = stats["sentiment_count"]["neutral"]
            sup = stats["stance_count"]["support"]
            opp = stats["stance_count"]["oppose"]
            st_neu = stats["stance_count"]["neutral"]
            scores = stats["sentiment_scores"]
            mean = sum(scores) / total if total else 0.0
            var = sum((x - mean) ** 2 for x in scores) / total if total else 0.0
            std = math.sqrt(var)
            stance_non_neutral = sup + opp
            balance = _safe_ratio(abs(sup - opp), stance_non_neutral)
            confrontation = _safe_ratio(2 * min(sup, opp), stance_non_neutral)

            writer.writerow(
                {
                    "platform_video_id": vid,
                    "total_comments": total,
                    "level1_comments": stats["level1_comments"],
                    "level2_comments": stats["level2_comments"],
                    "sentiment_positive": pos,
                    "sentiment_negative": neg,
                    "sentiment_neutral": neu,
                    "sentiment_mean": f"{mean:.4f}",
                    "sentiment_std": f"{std:.4f}",
                    "sentiment_non_neutral_ratio": f"{_safe_ratio(pos + neg, total):.4f}",
                    "stance_support": sup,
                    "stance_oppose": opp,
                    "stance_neutral": st_neu,
                    "stance_target_hit_ratio": f"{_safe_ratio(stats['target_hit_count'], total):.4f}",
                    "stance_non_neutral_ratio": f"{_safe_ratio(stance_non_neutral, total):.4f}",
                    "stance_balance_index": f"{balance:.4f}",
                    "stance_confrontation_index": f"{confrontation:.4f}",
                }
            )

    overview = {
        "input_dir": str(input_dir),
        "output_dir": str(output_dir),
        "comment_output": comment_out.name,
        "video_output": video_out.name,
        "total_comments": int(sum(v["total_comments"] for v in video_agg.values())),
        "total_videos": len(video_agg),
        "sentiment_distribution": dict(sentiment_counter),
        "stance_distribution": dict(stance_counter),
        "created_at": datetime.now().isoformat(),
        "notes": {
            "method": "lexicon-rule-based",
            "stance_target_terms": list(TARGET_TERMS),
            "sentiment_labels": ["positive", "negative", "neutral"],
            "stance_labels": ["support", "oppose", "neutral"],
        },
    }
    overview_out.write_text(json.dumps(overview, ensure_ascii=False, indent=2), encoding="utf-8")
    return overview


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    input_dir = Path(args.input_dir).expanduser().resolve()
    if args.output_dir:
        output_dir = Path(args.output_dir).expanduser().resolve()
    else:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = input_dir / f"sentiment_polarization_{stamp}"

    overview = run(input_dir=input_dir, output_dir=output_dir)
    print(f"input_dir={overview['input_dir']}")
    print(f"output_dir={overview['output_dir']}")
    print(f"total_videos={overview['total_videos']}")
    print(f"total_comments={overview['total_comments']}")
    print(f"sentiment_distribution={overview['sentiment_distribution']}")
    print(f"stance_distribution={overview['stance_distribution']}")


if __name__ == "__main__":
    main()
