from pydantic import BaseModel, Field

from app.core.enums import Platform, QueryType


class SearchJobCreate(BaseModel):
    platform: Platform
    query_type: QueryType
    query: str = Field(min_length=1)
    time_range: str | None = None
    start_time: str | None = None
    end_time: str | None = None
    limit: int | None = Field(default=100, ge=1, le=10000)
    run_now: bool = True


class CommentsJobCreate(BaseModel):
    platform: Platform
    video_ids: list[str]
    run_now: bool = True


class AccountImport(BaseModel):
    platform: Platform
    label: str = Field(min_length=1)
    state_file: str = Field(min_length=1)


class ProxyImport(BaseModel):
    label: str = Field(min_length=1)
    proxy_url: str = Field(min_length=1)


class ProxySourceImport(BaseModel):
    source_name: str = Field(min_length=1)
    limit: int | None = Field(default=100, ge=1, le=5000)


class IPProxyPoolImport(BaseModel):
    base_url: str | None = None
    limit: int | None = Field(default=100, ge=1, le=5000)
    types: int | None = Field(default=None, ge=0, le=2)
    protocol: int | None = Field(default=None, ge=0, le=2)
    country: str | None = None
    area: str | None = None


class ProxyValidateRequest(BaseModel):
    limit: int | None = Field(default=50, ge=1, le=5000)
