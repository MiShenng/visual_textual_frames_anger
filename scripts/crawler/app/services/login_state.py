from pathlib import Path
import re

from app.core.config import ensure_runtime_paths, get_settings
from app.core.enums import Platform
from app.services.accounts import AccountService


def build_state_path(platform: Platform, label: str) -> Path:
    settings = ensure_runtime_paths()
    safe_label = re.sub(r"[^a-zA-Z0-9_-]+", "_", label.strip()).strip("_") or "default"
    return settings.playwright_state_dir / f"{platform.value}_{safe_label}.json"


def capture_douyin_login_state(label: str, import_account: bool, db_session) -> Path:
    try:
        from playwright.sync_api import sync_playwright
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "playwright 未安装。先执行: .venv/bin/pip install playwright && .venv/bin/python -m playwright install chromium"
        ) from exc

    target_path = build_state_path(Platform.DOUYIN, label)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    settings = get_settings()

    with sync_playwright() as playwright:
        launch_kwargs = {
            "headless": False,
            "args": ["--disable-blink-features=AutomationControlled"],
        }
        if settings.playwright_channel:
            launch_kwargs["channel"] = settings.playwright_channel
        browser = playwright.chromium.launch(**launch_kwargs)
        context_kwargs = {
            "ignore_https_errors": True,
            "locale": settings.playwright_locale,
            "viewport": {"width": 1440, "height": 900},
        }
        if settings.playwright_timezone_id:
            context_kwargs["timezone_id"] = settings.playwright_timezone_id
        if settings.playwright_user_agent:
            context_kwargs["user_agent"] = settings.playwright_user_agent
        context = browser.new_context(**context_kwargs)
        page = context.new_page()
        page.goto("https://www.douyin.com", wait_until="domcontentloaded")
        print("")
        print("已打开抖音登录页。请在浏览器里手动完成登录。")
        print("登录成功后，回到当前终端按回车，程序会保存登录态。")
        input()
        context.storage_state(path=str(target_path))
        browser.close()

    if import_account:
        AccountService(db_session).import_account(
            platform=Platform.DOUYIN,
            label=label,
            state_file=str(target_path),
        )

    return target_path
