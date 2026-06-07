import csv
import io
from pathlib import Path

from fastapi import Depends, FastAPI, Form, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.api.schemas import (
    AccountImport,
    CommentsJobCreate,
    IPProxyPoolImport,
    ProxyImport,
    ProxySourceImport,
    ProxyValidateRequest,
    SearchJobCreate,
)
from app.api.serializers import (
    account_to_dict,
    comment_to_dict,
    event_to_dict,
    job_to_dict,
    proxy_to_dict,
    video_to_dict,
)
from app.core.config import ensure_runtime_paths
from app.core.enums import Platform, QueryType
from app.core.logging import configure_logging
from app.services.accounts import AccountService
from app.services.jobs import JobService
from app.services.proxies import ProxyService
from app.services.proxy_sources import ProxySourceService, list_proxy_sources
from app.services.registry import AdapterRegistry
from app.storage.base import Base
from app.storage.session import engine, get_db


configure_logging()

app = FastAPI(title="Short Video Crawler")
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parents[2] / "templates"))
registry = AdapterRegistry()


@app.on_event("startup")
def startup() -> None:
    settings = ensure_runtime_paths()
    Base.metadata.create_all(bind=engine)
    app.state.runtime_settings = settings


def get_job_service(db: Session = Depends(get_db)) -> JobService:
    return JobService(db, registry)


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request, service: JobService = Depends(get_job_service)):
    db = next(get_db())
    try:
        settings = ensure_runtime_paths()
        account_service = AccountService(db)
        proxy_service = ProxyService(db)
        context = {
            "request": request,
            "stats": service.dashboard_stats(),
            "jobs": service.list_jobs()[:10],
            "videos": service.list_videos()[:12],
            "comments": service.list_comments()[:12],
            "events": service.list_events(12),
            "accounts": account_service.list_accounts()[:12],
            "proxies": [
                proxy_to_dict(item, proxy_service.infer_source(item))
                for item in proxy_service.list_proxies()[:12]
            ],
            "proxy_sources": list_proxy_sources(),
            "ipproxypool_defaults": {
                "base_url": settings.ipproxypool_base_url,
                "limit": 100,
                "types": settings.ipproxypool_types,
                "protocol": settings.ipproxypool_protocol,
                "country": settings.ipproxypool_country or "",
                "area": settings.ipproxypool_area or "",
            },
            "platforms": list(Platform),
            "query_types": list(QueryType),
        }
    finally:
        db.close()
    return templates.TemplateResponse("dashboard.html", context)


@app.post("/ui/jobs/search", response_class=HTMLResponse)
def create_search_job_form(
    request: Request,
    platform: Platform = Form(...),
    query_type: QueryType = Form(...),
    query: str = Form(...),
    time_range: str | None = Form(default=None),
    start_time: str | None = Form(default=None),
    end_time: str | None = Form(default=None),
    limit: int = Form(default=100),
    service: JobService = Depends(get_job_service),
):
    service.create_search_job(
        platform,
        query_type,
        query,
        _compose_time_range(time_range, start_time, end_time),
        limit,
        run_now=True,
    )
    return dashboard(request, service)


@app.post("/ui/jobs/comments", response_class=HTMLResponse)
def create_comments_job_form(
    request: Request,
    platform: Platform = Form(...),
    video_ids: str = Form(...),
    service: JobService = Depends(get_job_service),
):
    ids = [item.strip() for item in video_ids.split(",") if item.strip()]
    service.create_comments_job(platform, ids, run_now=True)
    return dashboard(request, service)


@app.post("/ui/accounts/import", response_class=HTMLResponse)
def import_account_form(
    request: Request,
    platform: Platform = Form(...),
    label: str = Form(...),
    state_file: str = Form(...),
    db: Session = Depends(get_db),
):
    AccountService(db).import_account(platform, label, state_file)
    return dashboard(request, JobService(db, registry))


@app.post("/ui/proxies/import", response_class=HTMLResponse)
def import_proxy_form(
    request: Request,
    label: str = Form(...),
    proxy_url: str = Form(...),
    db: Session = Depends(get_db),
):
    ProxyService(db).import_proxy(label, proxy_url)
    return dashboard(request, JobService(db, registry))


@app.post("/ui/proxies/import-source", response_class=HTMLResponse)
def import_proxy_source_form(
    request: Request,
    source_name: str = Form(...),
    limit: int = Form(default=100),
    db: Session = Depends(get_db),
):
    ProxySourceService(ProxyService(db)).import_from_source(source_name, limit)
    return dashboard(request, JobService(db, registry))


@app.post("/ui/proxies/import-ipproxypool", response_class=HTMLResponse)
def import_ipproxypool_form(
    request: Request,
    base_url: str | None = Form(default=None),
    limit: int = Form(default=100),
    types: int | None = Form(default=None),
    protocol: int | None = Form(default=None),
    country: str | None = Form(default=None),
    area: str | None = Form(default=None),
    db: Session = Depends(get_db),
):
    ProxySourceService(ProxyService(db)).import_from_ipproxypool(
        limit=limit,
        base_url=base_url,
        types=types,
        protocol=protocol,
        country=country,
        area=area,
    )
    return dashboard(request, JobService(db, registry))


@app.post("/ui/proxies/validate", response_class=HTMLResponse)
def validate_proxy_form(
    request: Request,
    limit: int = Form(default=50),
    db: Session = Depends(get_db),
):
    ProxyService(db).validate_proxies(limit)
    return dashboard(request, JobService(db, registry))


@app.post("/ui/proxies/cleanup", response_class=HTMLResponse)
def cleanup_proxy_form(
    request: Request,
    db: Session = Depends(get_db),
):
    ProxyService(db).cleanup_invalid_proxies()
    return dashboard(request, JobService(db, registry))


@app.get("/jobs")
def list_jobs(service: JobService = Depends(get_job_service)):
    return [job_to_dict(job) for job in service.list_jobs()]


@app.get("/jobs/{job_id}")
def get_job(job_id: int, service: JobService = Depends(get_job_service)):
    return job_to_dict(service.get_job(job_id))


@app.post("/jobs/search")
def create_search_job(payload: SearchJobCreate, service: JobService = Depends(get_job_service)):
    job = service.create_search_job(
        platform=payload.platform,
        query_type=payload.query_type,
        query=payload.query,
        time_range=_compose_time_range(payload.time_range, payload.start_time, payload.end_time),
        limit=payload.limit,
        run_now=payload.run_now,
    )
    return job_to_dict(job)


@app.post("/jobs/comments")
def create_comments_job(
    payload: CommentsJobCreate, service: JobService = Depends(get_job_service)
):
    job = service.create_comments_job(
        platform=payload.platform,
        platform_video_ids=payload.video_ids,
        run_now=payload.run_now,
    )
    return job_to_dict(job)


@app.post("/jobs/{job_id}/retry")
def retry_job(job_id: int, service: JobService = Depends(get_job_service)):
    return job_to_dict(service.retry_job(job_id))


@app.get("/videos")
def list_videos(
    platform: Platform | None = None,
    query: str | None = None,
    query_type: QueryType | None = None,
    service: JobService = Depends(get_job_service),
):
    return [
        video_to_dict(video)
        for video in service.list_videos(platform=platform, query=query, query_type=query_type)
    ]


@app.get("/comments")
def list_comments(
    video_id: int | None = None,
    level: int | None = None,
    service: JobService = Depends(get_job_service),
):
    return [
        comment_to_dict(comment)
        for comment in service.list_comments(video_id=video_id, level=level)
    ]


@app.get("/accounts")
def list_accounts(db: Session = Depends(get_db)):
    return [account_to_dict(item) for item in AccountService(db).list_accounts()]


@app.get("/proxies")
def list_proxies(db: Session = Depends(get_db)):
    proxy_service = ProxyService(db)
    return [
        proxy_to_dict(item, proxy_service.infer_source(item))
        for item in proxy_service.list_proxies()
    ]


@app.get("/events")
def list_events(limit: int = 50, service: JobService = Depends(get_job_service)):
    return [event_to_dict(event) for event in service.list_events(limit)]


@app.get("/system/status")
def system_status(service: JobService = Depends(get_job_service), db: Session = Depends(get_db)):
    settings = ensure_runtime_paths()
    return {
        "stats": service.dashboard_stats(),
        "accounts": len(AccountService(db).list_accounts()),
        "proxies": len(ProxyService(db).list_proxies()),
        "database_url": engine.url.render_as_string(hide_password=True),
        "data_dir": str(settings.data_dir),
        "video_store_dir": str(settings.video_store_dir),
        "playwright_state_dir": str(settings.playwright_state_dir),
        "snapshot_dir": str(settings.snapshot_dir),
    }


@app.post("/accounts/import")
def import_account(payload: AccountImport, db: Session = Depends(get_db)):
    return account_to_dict(
        AccountService(db).import_account(payload.platform, payload.label, payload.state_file)
    )


@app.post("/proxies/import")
def import_proxy(payload: ProxyImport, db: Session = Depends(get_db)):
    return proxy_to_dict(ProxyService(db).import_proxy(payload.label, payload.proxy_url))


@app.post("/proxies/import-source")
def import_proxy_source(payload: ProxySourceImport, db: Session = Depends(get_db)):
    created = ProxySourceService(ProxyService(db)).import_from_source(
        payload.source_name,
        payload.limit,
    )
    return {"created": created, "source_name": payload.source_name}


@app.post("/proxies/import-ipproxypool")
def import_ipproxypool(payload: IPProxyPoolImport, db: Session = Depends(get_db)):
    created = ProxySourceService(ProxyService(db)).import_from_ipproxypool(
        limit=payload.limit,
        base_url=payload.base_url,
        types=payload.types,
        protocol=payload.protocol,
        country=payload.country,
        area=payload.area,
    )
    return {"created": created, "source_name": "ipproxypool_api"}


@app.post("/proxies/validate")
def validate_proxy(payload: ProxyValidateRequest, db: Session = Depends(get_db)):
    return ProxyService(db).validate_proxies(payload.limit)


@app.post("/proxies/cleanup")
def cleanup_proxy(db: Session = Depends(get_db)):
    removed = ProxyService(db).cleanup_invalid_proxies()
    return {"removed": removed}


@app.get("/export/videos.csv")
def export_videos_csv(service: JobService = Depends(get_job_service)):
    rows = [video_to_dict(video) for video in service.list_videos()]
    return _csv_response("videos.csv", rows)


@app.get("/export/comments.csv")
def export_comments_csv(service: JobService = Depends(get_job_service)):
    rows = [comment_to_dict(comment) for comment in service.list_comments()]
    return _csv_response("comments.csv", rows)


def _csv_response(filename: str, rows: list[dict]) -> StreamingResponse:
    fieldnames = sorted({key for row in rows for key in row.keys()}) if rows else ["empty"]
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    buffer.seek(0)
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _compose_time_range(
    time_range: str | None,
    start_time: str | None,
    end_time: str | None,
) -> str | None:
    if time_range:
        return time_range
    if start_time or end_time:
        return f"{start_time or ''}:{end_time or ''}"
    return None
