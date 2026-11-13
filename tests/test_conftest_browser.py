"""tests/conftest.py의 브라우저 판단 시험 (D-54). 진짜 브라우저 없이 monkeypatch로 돈다.
REQUIRE_BROWSER(없음·0·1) × 브라우저(있음·import 실패·chromium 실행 실패)."""
import importlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import conftest  # noqa: E402


class FakeChromium:
    def __init__(self, ok):
        self.ok = ok

    def launch(self):
        if not self.ok:
            raise RuntimeError("Executable doesn't exist")
        return "browser"


class FakePlaywright:
    def __init__(self, ok):
        self.chromium = FakeChromium(ok)


def set_env(monkeypatch, value):
    if value is None:
        monkeypatch.delenv("REQUIRE_BROWSER", raising=False)
    else:
        monkeypatch.setenv("REQUIRE_BROWSER", value)


def get_browser(monkeypatch, state):
    """state: ok · no_import · no_launch. playwright_api()와 launch_chromium()을 차례로 부른다."""
    real = importlib.import_module

    def fake_import(name, *a, **kw):
        if name == "playwright.sync_api":
            if state == "no_import":
                raise ModuleNotFoundError("No module named 'playwright'")
            return "api"
        return real(name, *a, **kw)
    monkeypatch.setattr(conftest.importlib, "import_module", fake_import)
    assert conftest.playwright_api() == "api"
    return conftest.launch_chromium(FakePlaywright(state != "no_launch"))


@pytest.mark.parametrize("env", [None, "0", "1"])
def test_browser_present_runs(monkeypatch, env):
    set_env(monkeypatch, env)
    assert get_browser(monkeypatch, "ok") == "browser"


@pytest.mark.parametrize("state", ["no_import", "no_launch"])
@pytest.mark.parametrize("env", [None, "0", "true"])
def test_browser_absent_skips_without_require(monkeypatch, env, state):
    set_env(monkeypatch, env)
    with pytest.raises(pytest.skip.Exception) as exc:
        get_browser(monkeypatch, state)
    assert conftest.INSTALL_HINT in str(exc.value)


@pytest.mark.parametrize("state,cause", [("no_import", "import"), ("no_launch", "chromium")])
def test_browser_absent_fails_with_require(monkeypatch, state, cause):
    set_env(monkeypatch, "1")
    with pytest.raises(pytest.fail.Exception) as exc:
        get_browser(monkeypatch, state)
    msg = str(exc.value)
    assert "REQUIRE_BROWSER=1" in msg and cause in msg and "python -m playwright install chromium" in msg


def test_browser_test_files_use_the_shared_fixture_only():
    """브라우저 시험 파일이 판단을 복사하지 않고 conftest를 쓴다."""
    tests = Path(__file__).resolve().parent
    users = [f.name for f in tests.glob("test_*.py") if "playwright" in f.read_text(encoding="utf-8")
             and f.name != Path(__file__).name]
    if (tests / "test_dashboard_render.py").exists():  # 키트 사본에는 이 파일이 없다(make_kit TESTS_LEFT_OUT)
        assert "test_dashboard_render.py" in users
    for name in users:
        text = (tests / name).read_text(encoding="utf-8")
        assert "importorskip" not in text and "pytest.skip(" not in text and ".launch(" not in text
