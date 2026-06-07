import csv
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.enums import Platform, QueryType
from app.services.topic_curation import TopicCurationService
from app.storage.base import Base
from app.storage.models import Comment, Video, VideoHit


def make_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def add_video(db, *, video_id: str, title: str, query: str, author_name: str = "媒体") -> Video:
    video = Video(
        platform=Platform.DOUYIN,
        platform_video_id=video_id,
        author_name=author_name,
        title=title,
        description=title,
        raw_json={"video": {"play_addr": {"url_list": [f"https://example.com/{video_id}.mp4"]}}},
    )
    db.add(video)
    db.commit()
    db.add(
        VideoHit(
            job_id=1,
            video_id=video.id,
            matched_query=query,
            query_type=QueryType.KEYWORD,
        )
    )
    db.commit()
    return video


def test_classify_relevant_video_as_keep(tmp_path):
    db = make_session()
    video = add_video(
        db,
        video_id="keep-v1",
        query="治安管理处罚法",
        author_name="荔枝新闻",
        title="明年起吸毒人员至少半年不得进入娱乐场所",
    )
    service = TopicCurationService(
        db,
        comment_root=tmp_path / "comments",
        video_root=tmp_path / "videos",
    )

    decision = service.classify_video(
        video,
        matched_queries=["治安管理处罚法"],
        comment_count=0,
    )

    assert decision.decision == "keep"
    assert "吸毒人员" in decision.matched_strong_terms


def test_classify_general_law_noise_as_drop(tmp_path):
    db = make_session()
    video = add_video(
        db,
        video_id="drop-v1",
        query="治安管理处罚法",
        title="新规来了！校园霸凌不再是护身符",
    )
    service = TopicCurationService(
        db,
        comment_root=tmp_path / "comments",
        video_root=tmp_path / "videos",
    )

    decision = service.classify_video(
        video,
        matched_queries=["治安管理处罚法"],
        comment_count=0,
    )

    assert decision.decision == "drop"
    assert "校园霸凌" in decision.matched_negative_terms


def test_classify_generic_sealing_video_as_review(tmp_path):
    db = make_session()
    video = add_video(
        db,
        video_id="review-v1",
        query="记录封存",
        title="官方回应记录封存说了些啥",
    )
    service = TopicCurationService(
        db,
        comment_root=tmp_path / "comments",
        video_root=tmp_path / "videos",
    )

    decision = service.classify_video(
        video,
        matched_queries=["记录封存"],
        comment_count=0,
    )

    assert decision.decision == "keep"
    assert "记录封存" in decision.matched_support_terms


def test_classify_query_only_video_as_drop(tmp_path):
    db = make_session()
    video = add_video(
        db,
        video_id="drop-v3",
        query="吸毒记录封存",
        title="今天继续聊法律常识",
    )
    service = TopicCurationService(
        db,
        comment_root=tmp_path / "comments",
        video_root=tmp_path / "videos",
    )

    decision = service.classify_video(
        video,
        matched_queries=["吸毒记录封存"],
        comment_count=0,
    )

    assert decision.decision == "drop"
    assert decision.reason == "仅命中搜索关键词，正文主题信号不足"


def test_classify_query_with_drug_context_as_keep(tmp_path):
    db = make_session()
    video = add_video(
        db,
        video_id="keep-v3",
        query="吸毒记录封存",
        title="涉毒案件从严从重 #禁毒 #涉毒",
    )
    service = TopicCurationService(
        db,
        comment_root=tmp_path / "comments",
        video_root=tmp_path / "videos",
    )

    decision = service.classify_video(
        video,
        matched_queries=["吸毒记录封存"],
        comment_count=0,
    )

    assert decision.decision == "keep"
    assert decision.reason == "命中搜索主题且正文存在涉毒语境"


def test_export_writes_keep_review_drop_files(tmp_path):
    db = make_session()
    keep_video = add_video(
        db,
        video_id="keep-v2",
        query="吸毒记录封存",
        title="吸毒记录封存不是删除记录",
    )
    add_video(
        db,
        video_id="review-v2",
        query="记录封存",
        title="违法记录封存如何理解",
    )
    add_video(
        db,
        video_id="drop-v2",
        query="治安管理处罚法",
        title="烈性犬伤人要担责",
    )
    db.add(
        Comment(
            platform=Platform.DOUYIN,
            video_id=keep_video.id,
            platform_comment_id="c-1",
            text="一级评论",
            level=1,
        )
    )
    db.commit()

    comment_root = tmp_path / "comments"
    video_root = tmp_path / "videos"
    (comment_root / "douyin").mkdir(parents=True)
    (comment_root / "douyin" / "keep-v2.json").write_text("{}", encoding="utf-8")
    (comment_root / "douyin" / "keep-v2.complete").write_text("", encoding="utf-8")
    (video_root / "douyin").mkdir(parents=True)
    (video_root / "douyin" / "keep-v2.mp4").write_text("x", encoding="utf-8")

    service = TopicCurationService(db, comment_root=comment_root, video_root=video_root)
    summary = service.export(tmp_path / "out", platform=Platform.DOUYIN)

    assert summary["keep"] == 2
    assert summary["review"] == 0
    assert summary["drop"] == 1

    with (tmp_path / "out" / "keep_videos.csv").open(encoding="utf-8", newline="") as handle:
        keep_rows = list(csv.DictReader(handle))
    keep_ids = {row["platform_video_id"] for row in keep_rows}
    assert keep_ids == {"keep-v2", "review-v2"}
    keep_row = next(row for row in keep_rows if row["platform_video_id"] == "keep-v2")
    assert keep_row["comment_file_exists"] == "True"
    assert keep_row["video_file_exists"] == "True"
