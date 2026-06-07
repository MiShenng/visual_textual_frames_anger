from __future__ import annotations

import argparse
import csv
import json
import math
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

CAT_STATE = "state_interest"
CAT_FREEDOM = "freedom_rights"
CAT_POPULISM = "populism"

SEED_LEXICON: dict[str, tuple[str, ...]] = {
    CAT_STATE: (
        "国家利益",
        "法治",
        "法律",
        "禁毒",
        "治理",
        "秩序",
        "公共安全",
        "零容忍",
        "严惩",
        "执法",
        "司法",
    ),
    CAT_FREEDOM: (
        "自由权利",
        "权利",
        "人权",
        "平等",
        "隐私",
        "机会",
        "复归",
        "歧视",
        "改过自新",
        "前科封存",
        "记录封存",
    ),
    CAT_POPULISM: (
        "老百姓",
        "特权",
        "权贵",
        "双标",
        "资本",
        "阶层",
        "普通人",
        "民意",
        "网友",
        "愤怒",
        "不公平",
    ),
}

POSITIVE_WORDS = (
    "支持",
    "赞成",
    "同意",
    "合理",
    "公平",
    "有必要",
    "应该",
    "应当",
    "机会",
    "改过自新",
    "进步",
    "理性",
)

NEGATIVE_WORDS = (
    "反对",
    "不同意",
    "不该",
    "不能",
    "不应",
    "纵容",
    "洗白",
    "离谱",
    "荒唐",
    "愤怒",
    "恶心",
    "严惩",
    "零容忍",
)

NEGATORS = ("不", "没", "无", "别", "未", "并不")
URL_RE = re.compile(r"https?://\S+|www\.\S+", re.I)
ZH_ONLY_RE = re.compile(r"[\u4e00-\u9fff]+")


@dataclass
class CommentRow:
    video_id: str
    platform_video_id: str
    comment_row_id: str
    parent_comment_id: str
    level: str
    text_raw: str
    text_clean: str
    row: dict[str, str]
    polarity: float = 0.5
    intensity: float = 0.0
    transmissibility: float | None = None
    stance_state: float = 0.0
    stance_freedom: float = 0.0
    stance_populism: float = 0.0
    stance_label: str = "neutral"
    stance_strength: float = 0.0
    stance_gap: float = 0.0
    stance_entropy_polarization: float = 0.0


def _sigmoid(x: float) -> float:
    if x >= 0:
        z = math.exp(-x)
        return 1 / (1 + z)
    z = math.exp(x)
    return z / (1 + z)


def normalize_text_for_scoring(text: str) -> str:
    if not text:
        return ""
    value = text
    value = URL_RE.sub(" <URL> ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def sentiment_polarity_score(text: str) -> float:
    value = normalize_text_for_scoring(text)
    if not value:
        return 0.5

    pos = sum(value.count(w) for w in POSITIVE_WORDS)
    neg = sum(value.count(w) for w in NEGATIVE_WORDS)

    for negator in NEGATORS:
        for word in POSITIVE_WORDS:
            hits = value.count(f"{negator}{word}")
            if hits:
                pos -= hits
                neg += hits
        for word in NEGATIVE_WORDS:
            hits = value.count(f"{negator}{word}")
            if hits:
                neg -= hits
                pos += hits

    raw = float(pos - neg)
    if "!" in value or "！" in value:
        raw *= 1.1
    return _sigmoid(raw)


def sentiment_intensity(polarity: float, mean_polarity: float) -> float:
    return abs(polarity - mean_polarity)


def extract_zh_ngrams(text: str, min_n: int = 2, max_n: int = 4) -> set[str]:
    grams: set[str] = set()
    for chunk in ZH_ONLY_RE.findall(text):
        if len(chunk) < min_n:
            continue
        upper = min(max_n, len(chunk))
        for n in range(min_n, upper + 1):
            for idx in range(0, len(chunk) - n + 1):
                grams.add(chunk[idx : idx + n])
    return grams


def expand_lexicon_by_cooccurrence(
    texts: list[str],
    base_lexicon: dict[str, set[str]],
    sample_size: int = 50000,
    min_df: int = 50,
    max_candidates: int = 2500,
    topk_per_category: int = 80,
) -> dict[str, set[str]]:
    if not texts:
        return base_lexicon

    sample = texts[:sample_size]
    df_counter: Counter[str] = Counter()
    for text in sample:
        df_counter.update(extract_zh_ngrams(text))

    all_seed_terms = {term for terms in base_lexicon.values() for term in terms}
    candidates = [
        term
        for term, freq in df_counter.most_common(max_candidates * 2)
        if freq >= min_df and term not in all_seed_terms and 2 <= len(term) <= 4
    ][:max_candidates]
    candidate_set = set(candidates)
    if not candidate_set:
        return base_lexicon

    category_seed_hits: Counter[str] = Counter()
    co_counter: dict[str, Counter[str]] = {key: Counter() for key in base_lexicon}

    for text in sample:
        categories_hit = {
            category
            for category, terms in base_lexicon.items()
            if any(seed in text for seed in terms)
        }
        if not categories_hit:
            continue
        grams = extract_zh_ngrams(text) & candidate_set
        if not grams:
            for category in categories_hit:
                category_seed_hits[category] += 1
            continue
        for category in categories_hit:
            category_seed_hits[category] += 1
            co_counter[category].update(grams)

    expanded = {category: set(terms) for category, terms in base_lexicon.items()}
    for category, terms in expanded.items():
        seed_docs = category_seed_hits[category]
        if not seed_docs:
            continue
        scored: list[tuple[float, str]] = []
        for term, co in co_counter[category].items():
            denom = math.sqrt(float(df_counter[term]) * float(seed_docs))
            if denom <= 0:
                continue
            similarity = co / denom
            if similarity > 0.08:
                scored.append((similarity, term))
        scored.sort(reverse=True)
        for _, term in scored[:topk_per_category]:
            terms.add(term)

    return expanded


def _cosine_similarity_by_term_counts(text: str, category_terms: set[str], all_terms: set[str]) -> float:
    if not text or not category_terms:
        return 0.0
    counts: dict[str, int] = {}
    for term in all_terms:
        c = text.count(term)
        if c > 0:
            counts[term] = c
    if not counts:
        return 0.0

    dot = float(sum(counts.get(term, 0) for term in category_terms))
    norm_text = math.sqrt(sum(v * v for v in counts.values()))
    norm_cat = math.sqrt(float(len(category_terms)))
    if norm_text <= 0 or norm_cat <= 0:
        return 0.0
    return dot / (norm_text * norm_cat)


def stance_scores(text: str, lexicon: dict[str, set[str]]) -> tuple[float, float, float]:
    all_terms = set().union(*lexicon.values()) if lexicon else set()
    state_sim = _cosine_similarity_by_term_counts(text, lexicon.get(CAT_STATE, set()), all_terms)
    freedom_sim = _cosine_similarity_by_term_counts(text, lexicon.get(CAT_FREEDOM, set()), all_terms)
    populism_sim = _cosine_similarity_by_term_counts(text, lexicon.get(CAT_POPULISM, set()), all_terms)
    return state_sim, freedom_sim, populism_sim


def stance_label_and_strength(state: float, freedom: float, populism: float) -> tuple[str, float, float, float]:
    scored = [
        (CAT_STATE, state),
        (CAT_FREEDOM, freedom),
        (CAT_POPULISM, populism),
    ]
    scored.sort(key=lambda x: x[1], reverse=True)
    label, top = scored[0]
    second = scored[1][1]
    total = top + second + scored[2][1]
    if top < 0.05:
        return "neutral", top, max(0.0, top - second), 0.0
    probs = [s / total for _, s in scored] if total > 0 else [1 / 3, 1 / 3, 1 / 3]
    entropy = -sum(p * math.log(p + 1e-12) for p in probs)
    entropy_norm = entropy / math.log(3)
    polarization = 1 - entropy_norm
    return label, top, max(0.0, top - second), polarization


def transmissibility(parent_polarity: float, reply_polarity: float) -> float:
    return 1 - abs(parent_polarity - reply_polarity)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Paper-style sentiment/stance polarization metrics.")
    parser.add_argument(
        "--input-master",
        required=True,
        help="Path to comments_cleaned_60_master.csv",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Output directory (default: sibling folder with timestamp)",
    )
    parser.add_argument("--expansion-sample-size", type=int, default=50000)
    parser.add_argument("--expansion-min-df", type=int, default=50)
    parser.add_argument("--expansion-max-candidates", type=int, default=2500)
    parser.add_argument("--expansion-topk-per-category", type=int, default=80)
    parser.add_argument(
        "--sentiment-source",
        choices=["proxy", "senta_api"],
        default="proxy",
        help="proxy=local rule score; senta_api=call Baidu Senta-compatible API endpoint",
    )
    parser.add_argument(
        "--senta-endpoint",
        default=os.getenv("SENTA_ENDPOINT", ""),
        help="Senta API endpoint URL",
    )
    parser.add_argument(
        "--senta-token",
        default=os.getenv("SENTA_ACCESS_TOKEN", ""),
        help="Senta API access token",
    )
    return parser.parse_args()


def load_comments(master_path: Path) -> list[CommentRow]:
    comments: list[CommentRow] = []
    with master_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            comments.append(
                CommentRow(
                    video_id=row.get("video_id", ""),
                    platform_video_id=row.get("platform_video_id", ""),
                    comment_row_id=row.get("comment_row_id", ""),
                    parent_comment_id=row.get("parent_comment_id", ""),
                    level=row.get("level", ""),
                    text_raw=row.get("text_raw", ""),
                    text_clean=row.get("text_clean", ""),
                    row=row,
                )
            )
    return comments


def run_analysis(
    comments: list[CommentRow],
    output_dir: Path,
    expansion_sample_size: int,
    expansion_min_df: int,
    expansion_max_candidates: int,
    expansion_topk_per_category: int,
    sentiment_source: str,
    senta_endpoint: str,
    senta_token: str,
) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    comment_out = output_dir / "comments_paper_metrics.csv"
    video_out = output_dir / "video_paper_metrics.csv"
    overview_out = output_dir / "paper_method_overview.json"

    # 1) Sentiment polarity.
    scorer = build_sentiment_scorer(
        source=sentiment_source,
        endpoint=senta_endpoint,
        access_token=senta_token,
    )
    for item in comments:
        source_text = item.text_clean or item.text_raw
        item.polarity = scorer(source_text)

    mean_polarity = sum(x.polarity for x in comments) / len(comments) if comments else 0.5
    for item in comments:
        item.intensity = sentiment_intensity(item.polarity, mean_polarity)

    # 2) Transmissibility based on parent->reply relation.
    by_comment_id = {x.comment_row_id: x for x in comments if x.comment_row_id}
    for item in comments:
        if not item.parent_comment_id:
            continue
        parent = by_comment_id.get(item.parent_comment_id)
        if parent is None:
            continue
        item.transmissibility = transmissibility(parent.polarity, item.polarity)

    # 3) Stance lexicon expansion and stance scoring.
    texts = [x.text_clean or x.text_raw for x in comments]
    base_lexicon = {cat: set(terms) for cat, terms in SEED_LEXICON.items()}
    lexicon = expand_lexicon_by_cooccurrence(
        texts=texts,
        base_lexicon=base_lexicon,
        sample_size=expansion_sample_size,
        min_df=expansion_min_df,
        max_candidates=expansion_max_candidates,
        topk_per_category=expansion_topk_per_category,
    )
    for item in comments:
        source_text = item.text_clean or item.text_raw
        s1, s2, s3 = stance_scores(source_text, lexicon)
        item.stance_state = s1
        item.stance_freedom = s2
        item.stance_populism = s3
        label, strength, gap, entropy_pol = stance_label_and_strength(s1, s2, s3)
        item.stance_label = label
        item.stance_strength = strength
        item.stance_gap = gap
        item.stance_entropy_polarization = entropy_pol

    # Write comment-level output.
    with comment_out.open("w", encoding="utf-8", newline="") as handle:
        fieldnames = list((comments[0].row.keys() if comments else [])) + [
            "paper_sentiment_polarity",
            "paper_sentiment_intensity",
            "paper_sentiment_mean",
            "paper_transmissibility",
            "paper_stance_state_sim",
            "paper_stance_freedom_sim",
            "paper_stance_populism_sim",
            "paper_stance_label",
            "paper_stance_strength",
            "paper_stance_gap",
            "paper_stance_entropy_polarization",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for item in comments:
            row = dict(item.row)
            row["paper_sentiment_polarity"] = f"{item.polarity:.6f}"
            row["paper_sentiment_intensity"] = f"{item.intensity:.6f}"
            row["paper_sentiment_mean"] = f"{mean_polarity:.6f}"
            row["paper_transmissibility"] = (
                f"{item.transmissibility:.6f}" if item.transmissibility is not None else ""
            )
            row["paper_stance_state_sim"] = f"{item.stance_state:.6f}"
            row["paper_stance_freedom_sim"] = f"{item.stance_freedom:.6f}"
            row["paper_stance_populism_sim"] = f"{item.stance_populism:.6f}"
            row["paper_stance_label"] = item.stance_label
            row["paper_stance_strength"] = f"{item.stance_strength:.6f}"
            row["paper_stance_gap"] = f"{item.stance_gap:.6f}"
            row["paper_stance_entropy_polarization"] = f"{item.stance_entropy_polarization:.6f}"
            writer.writerow(row)

    # Aggregate to video-level.
    by_video: dict[str, list[CommentRow]] = defaultdict(list)
    for item in comments:
        by_video[item.platform_video_id].append(item)

    with video_out.open("w", encoding="utf-8", newline="") as handle:
        fieldnames = [
            "platform_video_id",
            "total_comments",
            "level1_comments",
            "level2_comments",
            "sentiment_mean",
            "sentiment_intensity_mean",
            "sentiment_intensity_std",
            "transmissibility_pair_count",
            "transmissibility_mean",
            "stance_state_mean",
            "stance_freedom_mean",
            "stance_populism_mean",
            "stance_top_label",
            "stance_strength_mean",
            "stance_gap_mean",
            "stance_entropy_polarization_mean",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for video_id, items in sorted(by_video.items()):
            total = len(items)
            lv1 = sum(1 for x in items if x.level == "1")
            lv2 = sum(1 for x in items if x.level == "2")
            sent_values = [x.polarity for x in items]
            sent_mean = sum(sent_values) / total if total else 0.5
            intensities = [x.intensity for x in items]
            intensity_mean = sum(intensities) / total if total else 0.0
            intensity_var = (
                sum((x - intensity_mean) ** 2 for x in intensities) / total if total else 0.0
            )
            intensity_std = math.sqrt(intensity_var)

            trans = [x.transmissibility for x in items if x.transmissibility is not None]
            trans_mean = sum(trans) / len(trans) if trans else 0.0

            state_mean = sum(x.stance_state for x in items) / total if total else 0.0
            freedom_mean = sum(x.stance_freedom for x in items) / total if total else 0.0
            populism_mean = sum(x.stance_populism for x in items) / total if total else 0.0

            label_counter = Counter(x.stance_label for x in items)
            top_label = label_counter.most_common(1)[0][0] if label_counter else "neutral"
            strength_mean = sum(x.stance_strength for x in items) / total if total else 0.0
            gap_mean = sum(x.stance_gap for x in items) / total if total else 0.0
            entropy_pol_mean = (
                sum(x.stance_entropy_polarization for x in items) / total if total else 0.0
            )

            writer.writerow(
                {
                    "platform_video_id": video_id,
                    "total_comments": total,
                    "level1_comments": lv1,
                    "level2_comments": lv2,
                    "sentiment_mean": f"{sent_mean:.6f}",
                    "sentiment_intensity_mean": f"{intensity_mean:.6f}",
                    "sentiment_intensity_std": f"{intensity_std:.6f}",
                    "transmissibility_pair_count": len(trans),
                    "transmissibility_mean": f"{trans_mean:.6f}",
                    "stance_state_mean": f"{state_mean:.6f}",
                    "stance_freedom_mean": f"{freedom_mean:.6f}",
                    "stance_populism_mean": f"{populism_mean:.6f}",
                    "stance_top_label": top_label,
                    "stance_strength_mean": f"{strength_mean:.6f}",
                    "stance_gap_mean": f"{gap_mean:.6f}",
                    "stance_entropy_polarization_mean": f"{entropy_pol_mean:.6f}",
                }
            )

    overview = {
        "input_comments": len(comments),
        "input_videos": len(by_video),
        "sentiment_mean": mean_polarity,
        "formulas": {
            "sentiment_polarity": "0~1 score (paper-style proxy; API/Senta-compatible slot)",
            "sentiment_intensity": "|sentiment_polarity - global_sentiment_mean|",
            "transmissibility": "1 - |parent_comment_sentiment - reply_comment_sentiment|",
            "stance_similarity": "cosine(text_term_vector, category_lexicon_vector)",
        },
        "lexicon": {
            "state_interest_size": len(lexicon.get(CAT_STATE, set())),
            "freedom_rights_size": len(lexicon.get(CAT_FREEDOM, set())),
            "populism_size": len(lexicon.get(CAT_POPULISM, set())),
        },
        "params": {
            "expansion_sample_size": expansion_sample_size,
            "expansion_min_df": expansion_min_df,
            "expansion_max_candidates": expansion_max_candidates,
            "expansion_topk_per_category": expansion_topk_per_category,
            "sentiment_source": sentiment_source,
        },
        "created_at": datetime.now().isoformat(),
        "outputs": {
            "comments_csv": str(comment_out),
            "videos_csv": str(video_out),
        },
    }
    overview_out.write_text(json.dumps(overview, ensure_ascii=False, indent=2), encoding="utf-8")
    return overview


def _call_senta_api(text: str, endpoint: str, access_token: str) -> float:
    if not endpoint or not access_token:
        raise ValueError("missing senta endpoint/token")
    payload = urllib.parse.urlencode(
        {
            "text": text,
            "access_token": access_token,
        }
    ).encode("utf-8")
    req = urllib.request.Request(endpoint, data=payload, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    with urllib.request.urlopen(req, timeout=10) as resp:
        body = resp.read().decode("utf-8", errors="ignore")
    data = json.loads(body)

    # Compatible with common response schema:
    # {"items":[{"positive_prob":0.83,"negative_prob":0.17}]}
    if isinstance(data, dict):
        items = data.get("items")
        if isinstance(items, list) and items:
            item0 = items[0]
            if isinstance(item0, dict) and "positive_prob" in item0:
                value = float(item0["positive_prob"])
                return min(1.0, max(0.0, value))
        if "positive_prob" in data:
            value = float(data["positive_prob"])
            return min(1.0, max(0.0, value))
    raise ValueError("unexpected senta response schema")


def build_sentiment_scorer(source: str, endpoint: str, access_token: str):
    cache: dict[str, float] = {}

    def local_proxy(text: str) -> float:
        return sentiment_polarity_score(text)

    if source != "senta_api" or not endpoint or not access_token:
        return local_proxy

    def scorer(text: str) -> float:
        key = text or ""
        if key in cache:
            return cache[key]
        try:
            value = _call_senta_api(key, endpoint, access_token)
        except (urllib.error.URLError, ValueError, TimeoutError, json.JSONDecodeError):
            value = local_proxy(key)
        cache[key] = value
        return value

    return scorer


def main() -> None:
    args = parse_args()
    input_master = Path(args.input_master).expanduser().resolve()
    if not input_master.exists():
        raise SystemExit(f"missing input file: {input_master}")
    if args.output_dir:
        output_dir = Path(args.output_dir).expanduser().resolve()
    else:
        output_dir = input_master.parent / f"paper_style_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    comments = load_comments(input_master)
    overview = run_analysis(
        comments=comments,
        output_dir=output_dir,
        expansion_sample_size=args.expansion_sample_size,
        expansion_min_df=args.expansion_min_df,
        expansion_max_candidates=args.expansion_max_candidates,
        expansion_topk_per_category=args.expansion_topk_per_category,
        sentiment_source=args.sentiment_source,
        senta_endpoint=args.senta_endpoint,
        senta_token=args.senta_token,
    )
    print(f"input_master={input_master}")
    print(f"output_dir={output_dir}")
    print(f"input_comments={overview['input_comments']}")
    print(f"input_videos={overview['input_videos']}")
    print(f"sentiment_mean={overview['sentiment_mean']:.6f}")
    print(f"lexicon={overview['lexicon']}")


if __name__ == "__main__":
    main()
