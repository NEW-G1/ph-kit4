"""on_stop.py Hook 시험. pytest는 가짜 runner로 바꾸고 실제로 부르지 않는다."""
import importlib.util
import io
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("on_stop", ROOT / ".claude" / "hooks" / "on_stop.py")
on_stop = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(on_stop)

NOTE = ".dev/progress.md가 아직 없다"
NO_TESTS = "관련 시험 없음, 커밋 전 전체 pytest 필요"


class Runner:
    def __init__(self, code=0, out=""):
        self.code, self.out, self.calls = code, out, []

    def __call__(self, cmd, **kw):
        self.calls.append((cmd, kw))
        return type("R", (), {"returncode": self.code, "stdout": self.out, "stderr": ""})()


@pytest.fixture
def project(tmp_path, monkeypatch):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_lonely.py").write_text("", encoding="utf-8")
    (tmp_path / "tests" / "test_other.py").write_text("", encoding="utf-8")
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    return tmp_path


def state(project, name):
    return project / ".claude" / "state" / name


def mark_changed(project, *paths):
    f = state(project, "changed_s1.txt")
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text("".join(p + "\n" for p in paths), encoding="utf-8")


def stop(monkeypatch, capsys, runner, active=False, session_id="s1"):
    payload = json.dumps({"session_id": session_id, "stop_hook_active": active}).encode("utf-8")
    monkeypatch.setattr(sys, "stdin", type("S", (), {"buffer": io.BytesIO(payload)})())
    code = on_stop.main(runner=runner)
    out, err = capsys.readouterr()
    return code, json.loads(out)["systemMessage"] if out else "", err


def test_no_changed_file_runs_nothing(project, monkeypatch, capsys):
    runner = Runner()
    code, message, err = stop(monkeypatch, capsys, runner)
    assert code == 0 and runner.calls == [] and err == "" and NOTE in message


def test_pass_clears_state(project, monkeypatch, capsys):
    mark_changed(project, "scripts/misc/lonely.py")
    state(project, "retry_s1.txt").write_text("2", encoding="utf-8")
    runner = Runner()
    code, _, err = stop(monkeypatch, capsys, runner, active=True)
    assert code == 0 and err == ""
    assert not state(project, "changed_s1.txt").exists() and not state(project, "retry_s1.txt").exists()


def test_exit_5_counts_as_pass(project, monkeypatch, capsys):
    mark_changed(project, "scripts/misc/lonely.py")
    assert stop(monkeypatch, capsys, Runner(code=5))[0] == 0
    assert not state(project, "changed_s1.txt").exists()


def test_runs_only_related_files_once(project, monkeypatch, capsys):
    mark_changed(project, "scripts/misc/lonely.py", "scripts/misc/lonely.py", "tests/test_lonely.py")
    runner = Runner()
    stop(monkeypatch, capsys, runner)
    [(cmd, kw)] = runner.calls
    assert cmd[1:] == ["-m", "pytest", "tests/test_lonely.py", "-q", "--tb=short"]
    assert kw["timeout"] == on_stop.PYTEST_TIMEOUT and kw["cwd"] == project


def test_timeout_fits_inside_hook_limit():
    settings = json.loads((ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"))
    [hook] = settings["hooks"]["Stop"][0]["hooks"]
    assert hook["timeout"] == 900 and on_stop.PYTEST_TIMEOUT < hook["timeout"]


def test_no_related_tests_notices_and_clears(project, monkeypatch, capsys):
    mark_changed(project, "scripts/misc/alone.py")
    runner = Runner()
    code, message, err = stop(monkeypatch, capsys, runner)
    assert code == 0 and err == "" and runner.calls == []
    assert f"scripts/misc/alone.py: {NO_TESTS}" in message and not state(project, "changed_s1.txt").exists()


def test_failure_exits_2_and_keeps_changed(project, monkeypatch, capsys):
    mark_changed(project, "scripts/misc/lonely.py")
    out = "\n".join(f"line {i}" for i in range(60)) + "\n1 failed"
    code, message, err = stop(monkeypatch, capsys, Runner(code=1, out=out))
    assert code == 2 and message == ""
    assert "pytest 실패" in err and "tests/test_lonely.py" in err and "1 failed" in err
    assert "line 20" not in err.splitlines() and "line 21" in err.splitlines()  # 끝 40줄
    assert state(project, "retry_s1.txt").read_text(encoding="utf-8") == "1"
    assert state(project, "changed_s1.txt").exists()


def test_third_failure_lets_go_and_tells_human(project, monkeypatch, capsys):
    mark_changed(project, "scripts/misc/lonely.py")
    runner = Runner(code=1, out="1 failed")
    assert stop(monkeypatch, capsys, runner)[0] == 2
    assert stop(monkeypatch, capsys, runner, active=True)[0] == 2
    assert state(project, "retry_s1.txt").read_text(encoding="utf-8") == "2"
    code, message, err = stop(monkeypatch, capsys, runner, active=True)
    assert code == 0 and err == "" and "관련 시험이 3회 고친 뒤에도 실패, 사람 확인 필요" in message
    assert not state(project, "retry_s1.txt").exists() and state(project, "changed_s1.txt").exists()


def test_new_turn_restarts_retry_count(project, monkeypatch, capsys):
    mark_changed(project, "scripts/misc/lonely.py")
    state(project, "retry_s1.txt").write_text("2", encoding="utf-8")
    assert stop(monkeypatch, capsys, Runner(code=1), active=False)[0] == 2
    assert state(project, "retry_s1.txt").read_text(encoding="utf-8") == "1"


def test_timeout_is_notice_not_retry(project, monkeypatch, capsys):
    mark_changed(project, "scripts/misc/lonely.py")

    def runner(cmd, **kw):
        raise subprocess.TimeoutExpired(cmd, kw["timeout"])
    code, message, err = stop(monkeypatch, capsys, runner)
    assert code == 0 and err == ""
    assert f"{on_stop.PYTEST_TIMEOUT}초" in message and "tests/test_lonely.py" in message and "커밋 전 전체 pytest로 확인" in message
    assert state(project, "changed_s1.txt").exists() and not state(project, "retry_s1.txt").exists()


def test_session_id_missing_uses_unknown(project, monkeypatch, capsys):
    f = state(project, "changed_unknown.txt")
    f.parent.mkdir(parents=True)
    f.write_text("scripts/misc/lonely.py\n", encoding="utf-8")
    runner = Runner()
    stop(monkeypatch, capsys, runner, session_id=None)
    assert len(runner.calls) == 1 and not f.exists()


# ---------- 기록 누락 알림: 한 턴에 한 번만 ----------

def test_note_once_on_pass(project, monkeypatch, capsys):
    mark_changed(project, "scripts/misc/lonely.py")
    _, message, err = stop(monkeypatch, capsys, Runner())
    assert message.count(NOTE) == 1 and err == ""


def test_note_once_across_failure_then_pass(project, monkeypatch, capsys):
    mark_changed(project, "scripts/misc/lonely.py")
    code, message, err = stop(monkeypatch, capsys, Runner(code=1, out="1 failed"))
    assert code == 2 and message == "" and err.count(NOTE) == 1 and "1 failed" in err
    code, message, err = stop(monkeypatch, capsys, Runner(), active=True)
    assert code == 0 and NOTE not in message and err == ""


def test_lonely_notice_once_across_failure_then_pass(project, monkeypatch, capsys):
    mark_changed(project, "scripts/misc/lonely.py", "scripts/misc/alone.py")
    _, _, err = stop(monkeypatch, capsys, Runner(code=1, out="1 failed"))
    assert NO_TESTS not in err
    _, message, _ = stop(monkeypatch, capsys, Runner(), active=True)
    assert message.count(NO_TESTS) == 1
