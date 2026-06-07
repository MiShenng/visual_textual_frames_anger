import typer
import uvicorn
from sqlalchemy.orm import Session

from app.core.config import ensure_runtime_paths
from app.core.enums import Platform, QueryType
from app.services.accounts import AccountService
from app.services.jobs import JobService
from app.services.login_state import capture_douyin_login_state
from app.services.proxies import ProxyService
from app.services.proxy_sources import ProxySourceService
from app.services.registry import AdapterRegistry
from app.services.video_downloads import VideoDownloadService
from app.storage.base import Base
from app.storage.session import SessionLocal, engine


Base.metadata.create_all(bind=engine)
cli = typer.Typer(help="Short video crawler CLI")
jobs_app = typer.Typer(help="Job commands")
accounts_app = typer.Typer(help="Account commands")
proxies_app = typer.Typer(help="Proxy commands")
videos_app = typer.Typer(help="Video file commands")
cli.add_typer(jobs_app, name="jobs")
cli.add_typer(accounts_app, name="accounts")
cli.add_typer(proxies_app, name="proxies")
cli.add_typer(videos_app, name="videos")
registry = AdapterRegistry()


@cli.command("init-db")
def init_db():
    ensure_runtime_paths()
    Base.metadata.create_all(bind=engine)
    typer.echo("database_initialized=true")


@cli.command("serve")
def serve(
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8080, "--port"),
):
    ensure_runtime_paths()
    uvicorn.run("app.api.main:app", host=host, port=port, reload=False)


def _job_service() -> tuple[Session, JobService]:
    db = SessionLocal()
    return db, JobService(db, registry)


@jobs_app.command("search")
def jobs_search(
    platform: Platform,
    mode: QueryType = typer.Option(..., "--mode"),
    query: str = typer.Option(..., "--query"),
    limit: int | None = typer.Option(None, "--limit"),
    time_range: str | None = typer.Option(None, "--time-range"),
):
    db, service = _job_service()
    try:
        job = service.create_search_job(platform, mode, query, time_range, limit, run_now=True)
        typer.echo(f"job_id={job.id} status={job.status.value}")
    finally:
        db.close()


@jobs_app.command("comments")
def jobs_comments(
    platform: Platform,
    video_id: list[str] = typer.Option(..., "--video-id"),
    force: bool = typer.Option(False, "--force"),
):
    db, service = _job_service()
    try:
        job = service.create_comments_job(platform, video_id, force=force, run_now=True)
        typer.echo(f"job_id={job.id} status={job.status.value}")
    finally:
        db.close()


@accounts_app.command("import")
def accounts_import(
    platform: Platform,
    label: str = typer.Option(..., "--label"),
    state_file: str = typer.Option(..., "--state-file"),
):
    db = SessionLocal()
    try:
        account = AccountService(db).import_account(platform, label, state_file)
        typer.echo(f"account_id={account.id} label={account.label}")
    finally:
        db.close()


@accounts_app.command("capture-douyin")
def accounts_capture_douyin(
    label: str = typer.Option(..., "--label"),
    import_after_capture: bool = typer.Option(
        True, "--import/--no-import", help="保存后自动写入账号表"
    ),
):
    db = SessionLocal()
    try:
        state_path = capture_douyin_login_state(
            label=label,
            import_account=import_after_capture,
            db_session=db,
        )
        typer.echo(f"state_file={state_path}")
    finally:
        db.close()


@proxies_app.command("import")
def proxies_import(
    file: str = typer.Option(..., "--file"),
):
    db = SessionLocal()
    service = ProxyService(db)
    try:
        created = 0
        with open(file, "r", encoding="utf-8") as handle:
            for index, line in enumerate(handle, start=1):
                proxy_url = line.strip()
                if not proxy_url:
                    continue
                service.import_proxy(f"proxy-{index}", proxy_url)
                created += 1
        typer.echo(f"created={created}")
    finally:
        db.close()


@proxies_app.command("import-source")
def proxies_import_source(
    source_name: str = typer.Option(..., "--source-name"),
    limit: int = typer.Option(100, "--limit"),
):
    db = SessionLocal()
    try:
        created = ProxySourceService(ProxyService(db)).import_from_source(source_name, limit)
        typer.echo(f"created={created} source_name={source_name}")
    finally:
        db.close()


@proxies_app.command("import-ipproxypool")
def proxies_import_ipproxypool(
    limit: int = typer.Option(100, "--limit"),
    base_url: str | None = typer.Option(None, "--base-url"),
    types: int | None = typer.Option(None, "--types"),
    protocol: int | None = typer.Option(None, "--protocol"),
    country: str | None = typer.Option(None, "--country"),
    area: str | None = typer.Option(None, "--area"),
):
    db = SessionLocal()
    try:
        created = ProxySourceService(ProxyService(db)).import_from_ipproxypool(
            limit=limit,
            base_url=base_url,
            types=types,
            protocol=protocol,
            country=country,
            area=area,
        )
        typer.echo(f"created={created} source_name=ipproxypool_api")
    finally:
        db.close()


@proxies_app.command("validate")
def proxies_validate(
    limit: int = typer.Option(50, "--limit"),
):
    db = SessionLocal()
    try:
        result = ProxyService(db).validate_proxies(limit)
        typer.echo(
            f"checked={result['checked']} passed={result['passed']} failed={result['failed']}"
        )
    finally:
        db.close()


@proxies_app.command("cleanup")
def proxies_cleanup():
    db = SessionLocal()
    try:
        removed = ProxyService(db).cleanup_invalid_proxies()
        typer.echo(f"removed={removed}")
    finally:
        db.close()


@videos_app.command("download")
def videos_download(
    platform: Platform | None = typer.Option(None, "--platform"),
    query: str | None = typer.Option(None, "--query"),
    query_type: QueryType | None = typer.Option(None, "--query-type"),
    limit: int | None = typer.Option(None, "--limit"),
    overwrite: bool = typer.Option(False, "--overwrite"),
):
    db = SessionLocal()
    try:
        result = VideoDownloadService(db).download_videos(
            platform=platform,
            query=query,
            query_type=query_type,
            limit=limit,
            overwrite=overwrite,
        )
        typer.echo(
            "selected={selected} downloaded={downloaded} skipped={skipped} failed={failed}".format(
                **result
            )
        )
    finally:
        db.close()


if __name__ == "__main__":
    cli()
