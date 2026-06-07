from __future__ import annotations

import csv
import json
import re
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.enums import Platform
from app.services.video_downloads import pick_video_url, target_video_path
from app.storage.models import Comment, Video, VideoHit


@dataclass(frozen=True)
class TopicCurationRules:
    strong_terms: tuple[str, ...] = (
        "吸毒记录封存",
        "吸毒记录",
        "吸毒封存",
        "吸毒人员",
        "吸食、注射毒品",
        "吸食、注射",
        "哪位少爷吸了",
        "法工委回应",
        "人大法工委",
        "娱乐场所",
        "不得进娱乐场所",
        "不得进入娱乐场所",
        "封存不是删除",
    )
    support_terms: tuple[str, ...] = (
        "违法记录封存",
        "治安违法记录封存",
        "记录封存",
        "毒品犯罪",
        "官方回应吸毒记录封存",
    )
    context_terms: tuple[str, ...] = (
        "禁毒",
        "涉毒",
        "毒品",
        "缉毒",
        "戒毒",
        "入刑",
        "封存",
        "吸毒",
        "拘留",
    )
    negative_terms: tuple[str, ...] = (
        "校园霸凌",
        "校园欺凌",
        "犬只伤人",
        "烈性犬",
        "养犬",
        "网暴",
        "骂人",
        "诽谤",
        "造谣",
        "寻衅滋事",
        "卖淫",
        "未成年人",
        "孩子",
        "正当防卫",
        "网络暴力",
        "犯罪记录封存",
        "轻微犯罪记录封存",
    )
    strong_queries: tuple[str, ...] = (
        "吸毒记录封存",
        "吸毒记录",
        "哪位少爷吸了",
        "吸毒入刑",
        "吸毒记录封存政策",
    )
    broad_queries: tuple[str, ...] = (
        "记录封存",
        "治安管理处罚法",
    )


DEFAULT_TOPIC_RULES = TopicCurationRules()


@dataclass
class TopicCurationDecision:
    platform: str
    platform_video_id: str
    author_name: str
    title: str
    description: str
    share_url: str
    published_at: str
    matched_queries: list[str]
    matched_strong_terms: list[str]
    matched_support_terms: list[str]
    matched_negative_terms: list[str]
    comment_count: int
    downloadable: bool
    comment_file_exists: bool
    comment_complete_exists: bool
    video_file_exists: bool
    decision: str
    reason: str


def _safe_video_id(platform_video_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "_", platform_video_id)


class TopicCurationService:
    def __init__(
        self,
        db: Session,
        *,
        comment_root: Path | None = None,
        video_root: Path | None = None,
        rules: TopicCurationRules = DEFAULT_TOPIC_RULES,
    ):
        self.db = db
        settings = get_settings()
        self.comment_root = comment_root or settings.comment_store_dir
        self.video_root = video_root or settings.video_store_dir
        self.rules = rules

    def classify_videos(self, platform: Platform | None = None) -> list[TopicCurationDecision]:
        stmt = select(Video).order_by(Video.created_at.asc(), Video.id.asc())
        if platform is not None:
            stmt = stmt.where(Video.platform == platform)
        videos = list(self.db.scalars(stmt))
        query_map = self._query_map()
        comment_counts = self._comment_count_map()

        decisions: list[TopicCurationDecision] = []
        for video in videos:
            matched_queries = sorted(query_map.get(video.id, set()))
            decisions.append(
                self.classify_video(
                    video,
                    matched_queries=matched_queries,
                    comment_count=comment_counts.get(video.id, 0),
                )
            )
        return decisions

    def classify_video(
        self,
        video: Video,
        *,
        matched_queries: list[str],
        comment_count: int,
    ) -> TopicCurationDecision:
        search_text = " ".join(
            part.strip()
            for part in (video.author_name or "", video.title or "", video.description or "")
            if part and part.strip()
        )
        strong_matches = self._match_terms(search_text, self.rules.strong_terms)
        support_matches = self._match_terms(search_text, self.rules.support_terms)
        context_matches = self._match_terms(search_text, self.rules.context_terms)
        negative_matches = self._match_terms(search_text, self.rules.negative_terms)
        strong_query_matches = sorted(query for query in matched_queries if query in self.rules.strong_queries)
        broad_query_matches = sorted(query for query in matched_queries if query in self.rules.broad_queries)

        has_drug_context = "吸毒" in search_text or "毒品" in search_text
        has_topic_action = any(
            marker in search_text for marker in ("封存", "娱乐场所", "法工委", "少爷", "拘留")
        )
        has_strong_signal = bool(strong_matches) or (has_drug_context and has_topic_action)
        has_context_signal = bool(context_matches)

        if negative_matches and not (
            has_strong_signal or support_matches or (strong_query_matches and has_context_signal)
        ):
            decision = "drop"
            reason = "命中明显无关主题词"
        elif has_strong_signal:
            if negative_matches:
                decision = "review"
                reason = "同时命中核心主题和噪音词"
            else:
                decision = "keep"
                reason = "命中核心主题信号"
        elif support_matches:
            if negative_matches:
                decision = "review"
                reason = "同时命中延展主题和噪音词"
            else:
                decision = "keep"
                reason = "命中延展主题信号"
        elif strong_query_matches and has_context_signal:
            if negative_matches:
                decision = "review"
                reason = "命中搜索主题且伴随噪音词"
            else:
                decision = "keep"
                reason = "命中搜索主题且正文存在涉毒语境"
        elif strong_query_matches:
            decision = "drop"
            reason = "仅命中搜索关键词，正文主题信号不足"
        elif broad_query_matches:
            decision = "drop"
            reason = "仅命中宽泛法条关键词"
        else:
            decision = "drop"
            reason = "缺少主题信号"

        comment_file = self._comment_file_path(video.platform, video.platform_video_id)
        comment_complete = comment_file.with_suffix(".complete")
        video_file = target_video_path(self.video_root, video.platform, video.platform_video_id)
        published_at = video.published_at.astimezone(UTC).isoformat() if video.published_at else ""

        return TopicCurationDecision(
            platform=video.platform.value,
            platform_video_id=video.platform_video_id,
            author_name=video.author_name or "",
            title=video.title or "",
            description=video.description or "",
            share_url=video.share_url or "",
            published_at=published_at,
            matched_queries=matched_queries,
            matched_strong_terms=strong_matches + strong_query_matches,
            matched_support_terms=support_matches + broad_query_matches,
            matched_negative_terms=negative_matches,
            comment_count=comment_count,
            downloadable=pick_video_url(video) is not None,
            comment_file_exists=comment_file.exists(),
            comment_complete_exists=comment_complete.exists(),
            video_file_exists=video_file.exists(),
            decision=decision,
            reason=reason,
        )

    def export(self, output_dir: Path, platform: Platform | None = None) -> dict[str, int | str]:
        output_dir.mkdir(parents=True, exist_ok=True)
        decisions = self.classify_videos(platform=platform)
        grouped: dict[str, list[TopicCurationDecision]] = defaultdict(list)
        for decision in decisions:
            grouped[decision.decision].append(decision)

        files = {
            "keep": output_dir / "keep_videos.csv",
            "review": output_dir / "review_videos.csv",
            "drop": output_dir / "drop_videos.csv",
        }
        for key, path in files.items():
            self._write_csv(path, grouped.get(key, []))

        summary = {
            "generated_at": datetime.now(UTC).isoformat(),
            "platform": platform.value if platform is not None else "all",
            "counts": {key: len(grouped.get(key, [])) for key in ("keep", "review", "drop")},
            "rules": asdict(self.rules),
        }
        (output_dir / "summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return {
            "keep": len(grouped.get("keep", [])),
            "review": len(grouped.get("review", [])),
            "drop": len(grouped.get("drop", [])),
            "total": len(decisions),
            "output_dir": str(output_dir),
        }

    def _query_map(self) -> dict[int, set[str]]:
        query_map: dict[int, set[str]] = defaultdict(set)
        rows = self.db.execute(select(VideoHit.video_id, VideoHit.matched_query)).all()
        for video_id, matched_query in rows:
            if matched_query:
                query_map[int(video_id)].add(str(matched_query))
        return query_map

    def _comment_count_map(self) -> dict[int, int]:
        rows = self.db.execute(
            select(Comment.video_id, func.count(Comment.id)).group_by(Comment.video_id)
        ).all()
        return {int(video_id): int(count) for video_id, count in rows}

    def _comment_file_path(self, platform: Platform, platform_video_id: str) -> Path:
        return self.comment_root / platform.value / f"{_safe_video_id(platform_video_id)}.json"

    def _match_terms(self, text: str, terms: tuple[str, ...]) -> list[str]:
        seen: list[str] = []
        for term in terms:
            if term in text:
                seen.append(term)
        return seen

    def _write_csv(self, path: Path, rows: list[TopicCurationDecision]) -> None:
        fieldnames = [
            "platform",
            "platform_video_id",
            "author_name",
            "title",
            "description",
            "share_url",
            "published_at",
            "matched_queries",
            "matched_strong_terms",
            "matched_support_terms",
            "matched_negative_terms",
            "comment_count",
            "downloadable",
            "comment_file_exists",
            "comment_complete_exists",
            "video_file_exists",
            "decision",
            "reason",
        ]
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                payload = asdict(row)
                payload["matched_queries"] = " | ".join(row.matched_queries)
                payload["matched_strong_terms"] = " | ".join(row.matched_strong_terms)
                payload["matched_support_terms"] = " | ".join(row.matched_support_terms)
                payload["matched_negative_terms"] = " | ".join(row.matched_negative_terms)
                writer.writerow(payload)
