"""after_edit.py Hook 시험. bq·gcloud는 가짜 runner로 바꾸고 BigQuery는 부르지 않는다.

after_edit는 사다리 L1과 같은 부품(common.render, common.Bq)을 쓴다: {{ project }} 포함 렌더링,
UTC ds, ai-builder 인증 확인, SQL은 stdin (3-3 스모크 1차·2차 후속).
"""
import importlib.util
import io
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("after_edit", ROOT / ".claude" / "hooks" / "after_edit.py")
after_edit = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(after_edit)
common = after_edit.common

TODAY = date(2026, 10, 30)
# sql_rules.md §1 멱등 3문장 패턴과 같은 모양: {{ project }}를 쓴다
SQL = """CREATE TABLE IF NOT EXISTS `{{ project }}.{{ dataset_raw }}.raw_x`
(
  snapshot_date DATE
);
DELETE FROM `{{ project }}.{{ dataset_raw }}.raw_x` WHERE snapshot_date = DATE('{{ ds }}');
INSERT INTO `{{ project }}.{{ dataset_raw }}.raw_x` (snapshot_date) SELECT DATE('{{ ds }}');
"""


class FakeRunner:
    def __init__(self, account="ai-builder@proj-x.iam.gserviceaccount.com", dry=None):
        self.account, self.calls = account, []
        self.dry = dry or (0, json.dumps({"statistics": {"totalBytesProcessed": "0"}}), "")

    def __call__(self, args, env, stdin=None):
        self.calls.append((args, stdin))
        if args[0] == "gcloud":
            if args[-1] == "auth/impersonate_service_account":
                return 0, "", ""
            return (0, self.account + "\n", "") if args[1] == "auth" else (0, "proj-x\n", "")
        return self.dry


def check(tmp_path, sql=SQL, runner=None, env=None, today=TODAY):
    f = tmp_path / "raw_x.sql"
    f.write_text(sql, encoding="utf-8")
    runner = runner or FakeRunner()
    bq = common.Bq(runner=runner, env={"CLOUDSDK_CONFIG": "C:/cfg"} if env is None else env)
    return after_edit.check_sql(f, bq=bq, today=today), runner


def bq_calls(runner):
    return [(a, s) for a, s in runner.calls if a[0] == "bq"]


def test_renders_project_and_dry_runs_via_stdin(tmp_path):
    problem, runner = check(tmp_path)
    assert problem is None
    [(args, stdin)] = bq_calls(runner)
    assert "--dry_run" in args and "--maximum_bytes_billed=524288000" in args and all("\n" not in a for a in args)
    assert "`proj-x.ai_dev.raw_x`" in stdin and "DATE('2026-10-30')" in stdin and "{{" not in stdin
    assert stdin.count("\n") >= 6  # 여러 줄 SQL이 통째로 간다


def test_ds_default_is_utc_today(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "utc_today", lambda: date(2026, 10, 29))
    problem, runner = check(tmp_path, today=None)
    assert problem is None and "DATE('2026-10-29')" in bq_calls(runner)[0][1]


def test_no_cloudsdk_config_skips_without_calls(tmp_path):
    problem, runner = check(tmp_path, env={})
    assert "건너뛰었다" in problem and "CLOUDSDK_CONFIG" in problem and runner.calls == []


def test_wrong_account_skips_without_bq(tmp_path):
    problem, runner = check(tmp_path, runner=FakeRunner(account="me@example.com"))
    assert "건너뛰었다" in problem and "ai-builder" in problem and bq_calls(runner) == []


def test_undefined_placeholder_is_syntax_failure(tmp_path):
    problem, runner = check(tmp_path, sql=SQL.replace("{{ ds }}", "{{ run_date }}", 1))
    assert "dry-run 실패" in problem and "syntax" in problem and bq_calls(runner) == []


def test_dry_run_error_reported(tmp_path):
    runner = FakeRunner(dry=(1, "", "Error in query string: Syntax error: Unexpected keyword"))
    problem, _ = check(tmp_path, runner=runner)
    assert "dry-run 실패" in problem and "Unexpected keyword" in problem


def test_gate_file_renders_force_fail(tmp_path):
    problem, runner = check(tmp_path, sql="ASSERT NOT {{ params.force_fail }} AS 'x';\n")
    assert problem is None and "ASSERT NOT False" in bq_calls(runner)[0][1]


# ---------- *.py: 시험을 돌리지 않고 고친 경로만 기록한다 (시험은 on_stop) ----------

def edit_py(tmp_path, monkeypatch, name="lonely.py", **fields):
    (tmp_path / "scripts").mkdir(exist_ok=True)
    (tmp_path / "scripts" / name).write_text("", encoding="utf-8")
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    payload = json.dumps({"tool_input": {"file_path": str(tmp_path / "scripts" / name)}, **fields}).encode("utf-8")
    monkeypatch.setattr(sys, "stdin", type("S", (), {"buffer": io.BytesIO(payload)})())
    return after_edit.main()


def test_py_edit_records_path_without_pytest(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(AssertionError("실행하면 안 됨")))
    assert edit_py(tmp_path, monkeypatch, session_id="s1") == 0
    assert edit_py(tmp_path, monkeypatch, name="other.py", session_id="s1") == 0
    state = tmp_path / ".claude" / "state" / "changed_s1.txt"
    assert state.read_text(encoding="utf-8").splitlines() == ["scripts/lonely.py", "scripts/other.py"]
    assert capsys.readouterr().out == ""


def test_py_edit_without_session_id_uses_unknown(tmp_path, monkeypatch):
    assert edit_py(tmp_path, monkeypatch) == 0
    assert (tmp_path / ".claude" / "state" / "changed_unknown.txt").exists()


def test_non_py_edit_records_nothing(tmp_path, monkeypatch):
    (tmp_path / "notes.md").write_text("", encoding="utf-8")
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    payload = json.dumps({"tool_input": {"file_path": str(tmp_path / "notes.md")}}).encode("utf-8")
    monkeypatch.setattr(sys, "stdin", type("S", (), {"buffer": io.BytesIO(payload)})())
    assert after_edit.main() == 0 and not (tmp_path / ".claude").exists()
