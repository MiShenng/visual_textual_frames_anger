from app.services.proxies import ProxyService
from app.storage.models import Account, Comment, CrawlEvent, CrawlJob, ProxyEndpoint, Video


def _comment_level_label(level: int) -> str:
    if level == 1:
        return "一级评论"
    if level == 2:
        return "二级评论"
    return f"{level}级评论"


def job_to_dict(job: CrawlJob) -> dict:
    return {
        "id": job.id,
        "job_type": job.job_type.value,
        "platform": job.platform.value,
        "query_type": job.query_type.value if job.query_type else None,
        "query": job.query,
        "status": job.status.value,
        "time_range": job.time_range,
        "limit": job.limit,
        "retry_count": job.retry_count,
        "cursor": job.cursor,
        "error_summary": job.error_summary,
        "requested_video_ids": job.requested_video_ids,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "updated_at": job.updated_at.isoformat() if job.updated_at else None,
    }


def video_to_dict(video: Video) -> dict:
    return {
        "id": video.id,
        "platform": video.platform.value,
        "platform_video_id": video.platform_video_id,
        "title": video.title,
        "description": video.description,
        "download_url": video.download_url,
        "share_url": video.share_url,
        "author_platform_id": video.author_platform_id,
        "author_name": video.author_name,
        "author_profile_url": video.author_profile_url,
        "author_signature": video.author_signature,
        "author_stats": video.author_stats,
        "tags": video.tags,
        "stats": video.stats,
        "published_at": video.published_at.isoformat() if video.published_at else None,
        "raw_json": video.raw_json,
    }


def comment_to_dict(comment: Comment) -> dict:
    return {
        "id": comment.id,
        "platform": comment.platform.value,
        "video_id": comment.video_id,
        "platform_comment_id": comment.platform_comment_id,
        "parent_comment_id": comment.parent_comment_id,
        "root_comment_platform_id": comment.root_comment_platform_id,
        "level": comment.level,
        "level_label": _comment_level_label(comment.level),
        "text": comment.text,
        "author_platform_id": comment.author_platform_id,
        "author_name": comment.author_name,
        "like_count": comment.like_count,
        "reply_count": comment.reply_count,
        "source": comment.source.value,
        "reply_to_comment_platform_id": (
            comment.root_comment_platform_id if comment.level == 2 else None
        ),
        "published_at": comment.published_at.isoformat() if comment.published_at else None,
        "raw_json": comment.raw_json,
    }


def account_to_dict(account: Account) -> dict:
    return {
        "id": account.id,
        "platform": account.platform.value,
        "label": account.label,
        "login_state_path": account.login_state_path,
        "status": account.status.value,
        "failure_count": account.failure_count,
        "cooldown_until": account.cooldown_until.isoformat()
        if account.cooldown_until
        else None,
        "notes": account.notes,
    }


def proxy_to_dict(proxy: ProxyEndpoint, source_name: str | None = None) -> dict:
    return {
        "id": proxy.id,
        "label": proxy.label,
        "source_name": source_name,
        "proxy_url": proxy.proxy_url,
        "status": proxy.status.value,
        "failure_count": proxy.failure_count,
        "cooldown_until": proxy.cooldown_until.isoformat()
        if proxy.cooldown_until
        else None,
        "last_checked_at": proxy.last_checked_at.isoformat()
        if proxy.last_checked_at
        else None,
        "last_success_at": proxy.last_success_at.isoformat()
        if proxy.last_success_at
        else None,
    }


def event_to_dict(event: CrawlEvent) -> dict:
    return {
        "id": event.id,
        "job_id": event.job_id,
        "platform": event.platform.value if event.platform else None,
        "level": event.level,
        "event_type": event.event_type,
        "message": event.message,
        "payload": event.payload,
        "created_at": event.created_at.isoformat() if event.created_at else None,
    }
