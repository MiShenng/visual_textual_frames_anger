from app.core.enums import Platform
from app.services.login_state import build_state_path


def test_build_state_path_sanitizes_label():
    path = build_state_path(Platform.DOUYIN, "main account@2026")

    assert path.name == "douyin_main_account_2026.json"
