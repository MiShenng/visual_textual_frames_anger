from enum import Enum


class Platform(str, Enum):
    DOUYIN = "douyin"
    TIKTOK = "tiktok"


class QueryType(str, Enum):
    KEYWORD = "keyword"
    TAG = "tag"


class JobType(str, Enum):
    SEARCH = "search"
    COMMENTS = "comments"


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"


class AccountStatus(str, Enum):
    ACTIVE = "active"
    COOLDOWN = "cooldown"
    DISABLED = "disabled"


class ProxyStatus(str, Enum):
    ACTIVE = "active"
    COOLDOWN = "cooldown"
    DISABLED = "disabled"


class CrawlSource(str, Enum):
    PRIMARY = "primary"
    FALLBACK_API = "fallback_api"

