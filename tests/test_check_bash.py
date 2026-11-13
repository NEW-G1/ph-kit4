"""check_bash.py Hook 시험. Hook 입력 JSON을 표준 입력으로 넣어 판정만 본다.

명령 자체는 실행하지 않는다. 차단 로그는 임시 폴더(CLAUDE_PROJECT_DIR)에 쌓인다.
"""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parents[1] / ".claude" / "hooks" / "check_bash.py"
LIMIT = "--maximum_bytes_billed=524288000"


def run_hook(project, tool, command=None, raw=None):
    payload = raw if raw is not None else json.dumps({
        "hook_event_name": "PreToolUse",
        "tool_name": tool,
        "tool_input": {"command": command},
    })
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(project)}
    return subprocess.run([sys.executable, str(HOOK)], input=payload.encode("utf-8"),
                          capture_output=True, env=env, timeout=30)


def read_log(project):
    path = project / ".dev" / "hook_blocks.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


BLOCKED = [
    # bq rm, bq update (ai_dev라도 막는다)
    ("Bash", "bq rm -f -t ai_dev.tmp_orders", "destructive_command"),
    ("Bash", "bq update --description x ai_dev.tmp_orders", "destructive_command"),
    ("Bash", "cd dags && bq --location=US rm -t ai_dev.t", "destructive_command"),
    ("PowerShell", "bq rm -f -t ai_dev.tmp_orders", "destructive_command"),
    ("PowerShell", "& bq.cmd update --description x ai_dev.t", "destructive_command"),
    # git push
    ("Bash", "git push origin week1/scaffold", "git_push"),
    ("Bash", "git -C . push", "git_push"),
    ("Bash", 'bash -c "git push"', "git_push"),
    ("PowerShell", "git push", "git_push"),
    ("PowerShell", "git.exe push origin main", "git_push"),
    # .env 읽기
    ("Bash", "cat .env", "env_read"),
    ("Bash", "head -n 3 config/.env.local", "env_read"),
    ("Bash", "grep TOKEN < .env", "env_read"),
    ("Bash", "cat .en*", "env_read"),
    ("Bash", 'sh -c "cat .env"', "env_read"),
    ("PowerShell", "Get-Content .env", "env_read"),
    ("PowerShell", r"gc .\.env", "env_read"),
    ("PowerShell", "type .env", "env_read"),
    ("PowerShell", "cat .env", "env_read"),
    ("PowerShell", "more .env", "env_read"),
    ("PowerShell", "Get-Content -Path C:\\work\\repo\\.env | Select-String TOKEN", "env_read"),
    # ai_dev 밖 쓰기
    ("Bash", f"bq query --use_legacy_sql=false {LIMIT} 'INSERT INTO thelook_mart.mart_x SELECT 1'", "write_outside_ai_dev"),
    ("Bash", f"bq query {LIMIT} 'CREATE OR REPLACE TABLE `proj.thelook_stg.stg_x` AS SELECT 1'", "write_outside_ai_dev"),
    ("Bash", f"bq query {LIMIT} 'MERGE thelook_mart.t T USING ai_dev.s S ON T.id = S.id WHEN MATCHED THEN UPDATE SET v = S.v'", "write_outside_ai_dev"),
    ("Bash", f"bq query {LIMIT} 'UPDATE thelook_raw.users SET age = 0 WHERE TRUE'", "write_outside_ai_dev"),
    ("Bash", f"bq query {LIMIT} 'DELETE FROM thelook_stg.stg_x WHERE TRUE'", "write_outside_ai_dev"),
    ("Bash", f"bq query {LIMIT} 'TRUNCATE TABLE thelook_mart.t'", "write_outside_ai_dev"),
    ("Bash", f"bq query {LIMIT} 'DROP TABLE IF EXISTS thelook_mart.t'", "write_outside_ai_dev"),
    ("Bash", f"bq query {LIMIT} 'ALTER TABLE thelook_mart.t ADD COLUMN c INT64'", "write_outside_ai_dev"),
    ("Bash", f"bq query {LIMIT} 'DROP SCHEMA thelook_mart CASCADE'", "write_outside_ai_dev"),
    ("Bash", f"bq query {LIMIT} --destination_table=thelook_mart.t 'SELECT 1'", "write_outside_ai_dev"),
    ("Bash", f"bq query {LIMIT} 'DELETE FROM ai_dev.t WHERE TRUE; INSERT INTO thelook_mart.t SELECT 1'", "write_outside_ai_dev"),
    ("Bash", f"bq query --dry_run 'INSERT INTO thelook_mart.t SELECT 1'", "write_outside_ai_dev"),
    ("Bash", "bq load --source_format=CSV thelook_raw.t gs://bucket/f.csv", "write_outside_ai_dev"),
    ("Bash", "bq cp ai_dev.a thelook_mart.b", "write_outside_ai_dev"),
    ("Bash", "bq mk -t thelook_mart.t", "write_outside_ai_dev"),
    ("PowerShell", f'bq query --use_legacy_sql=false {LIMIT} "DELETE FROM thelook_mart.t WHERE TRUE"', "write_outside_ai_dev"),
    ("PowerShell", f'bq query {LIMIT} "INSERT INTO `proj.thelook_stg.t` SELECT 1"', "write_outside_ai_dev"),
    # 쓰기 대상이 불분명
    ("Bash", f"bq query {LIMIT} 'INSERT INTO t SELECT 1'", "write_target_unknown"),
    ("Bash", f"bq query {LIMIT} 'INSERT INTO {{{{ dataset_mart }}}}.t SELECT 1'", "write_target_unknown"),
    ("Bash", f"bq query {LIMIT} < dags/sql/mart/x.sql", "write_target_unknown"),
    ("Bash", f"bq query {LIMIT} 'CALL ai_dev.proc()'", "write_target_unknown"),
    ("Bash", f"bq query {LIMIT} 'EXPORT DATA OPTIONS(uri=\"gs://b/*.csv\") AS SELECT 1'", "write_target_unknown"),
    ("PowerShell", f'Get-Content q.sql | bq query {LIMIT}', "write_target_unknown"),
    # 판단할 수 없는 bq 명령
    ("Bash", "bq extract ai_dev.t gs://bucket/out.csv", "bq_command_unknown"),
    ("Bash", "bq add-iam-policy-binding --member=user:x --role=roles/owner ai_dev.t", "bq_command_unknown"),
    ("PowerShell", "bq mk --transfer_config --target_dataset=ai_dev", "bq_command_unknown"),
    # 비용 상한
    ("Bash", "bq query --use_legacy_sql=false 'SELECT 1'", "cost_limit_missing"),
    ("Bash", "bq query --dry_run=false --use_legacy_sql=false 'SELECT 1'", "cost_limit_missing"),
    ("Bash", "bq query --maximum_bytes_billed=1000000000 'SELECT 1'", "cost_limit_exceeded"),
    ("PowerShell", 'bq query --use_legacy_sql=false "SELECT 1"', "cost_limit_missing"),
    ("PowerShell", 'bq query --maximum_bytes_billed 600000000 "SELECT 1"', "cost_limit_exceeded"),
]

ALLOWED = [
    ("Bash", "git status"),
    ("Bash", "git log --oneline -3"),
    ("Bash", 'git commit -m "chore: 폴더 구조"'),
    ("Bash", "ls -la .dev"),
    ("Bash", "cat .env.example"),
    ("Bash", "python -m pytest tests/ -q"),
    ("Bash", "bq query --dry_run --use_legacy_sql=false 'SELECT 1'"),
    ("Bash", "bq query --dry_run 'INSERT INTO ai_dev.t SELECT 1'"),
    ("Bash", f"bq query --use_legacy_sql=false {LIMIT} 'SELECT COUNT(*) FROM `bigquery-public-data.thelook_ecommerce.orders`'"),
    ("Bash", f"bq query {LIMIT} 'SELECT * FROM thelook_mart.mart_x LIMIT 0'"),
    ("Bash", f"bq query {LIMIT} 'INSERT INTO ai_dev.stg_orders SELECT * FROM `bigquery-public-data.thelook_ecommerce.orders`'"),
    ("Bash", f"bq query {LIMIT} 'CREATE OR REPLACE TABLE `proj.ai_dev.t` AS SELECT 1 AS x'"),
    ("Bash", f"bq query {LIMIT} 'TRUNCATE TABLE ai_dev.t'"),
    ("Bash", f"bq query {LIMIT} 'DELETE FROM `proj`.`ai_dev`.`t` WHERE snapshot_date = \"2026-10-27\"; INSERT INTO ai_dev.t SELECT 1'"),
    ("Bash", f"bq query {LIMIT} 'MERGE ai_dev.t T USING ai_dev.s S ON T.id = S.id WHEN MATCHED THEN UPDATE SET v = S.v WHEN NOT MATCHED THEN INSERT ROW WHEN NOT MATCHED BY SOURCE THEN DELETE'"),
    ("Bash", f"bq query {LIMIT} 'CREATE TEMP TABLE tmp AS SELECT 1 AS x; INSERT INTO tmp SELECT 2; INSERT INTO ai_dev.t SELECT * FROM tmp'"),
    ("Bash", f"bq query {LIMIT} --dataset_id=ai_dev 'INSERT INTO t SELECT 1'"),
    ("Bash", f"bq query {LIMIT} --destination_table=ai_dev.t 'SELECT 1'"),
    ("Bash", f"bq query {LIMIT} 'SELECT \"DELETE FROM thelook_mart.t\" AS note -- DROP TABLE thelook_mart.t'"),
    ("Bash", "bq show thelook_mart.mart_x"),
    ("Bash", "bq ls ai_dev"),
    ("Bash", "bq mk -t ai_dev.t schema.json"),
    ("Bash", "bq load --source_format=CSV ai_dev.t ./data.csv"),
    ("PowerShell", "git status"),
    ("PowerShell", "Get-ChildItem docs"),
    ("PowerShell", "Get-Content .env.example"),
    ("PowerShell", "Write-Output $env:CLOUDSDK_CONFIG"),
    ("PowerShell", 'bq query --dry_run --use_legacy_sql=false "SELECT 1"'),
    ("PowerShell", f'bq query --use_legacy_sql=false {LIMIT} "INSERT INTO ai_dev.t SELECT 1"'),
    ("PowerShell", f'bq query {LIMIT} "CREATE OR REPLACE TABLE ai_dev.t AS SELECT 1 AS x"'),
]


@pytest.mark.parametrize("tool,command,reason", BLOCKED)
def test_blocked(tmp_path, tool, command, reason):
    r = run_hook(tmp_path, tool, command)
    stderr = r.stderr.decode("utf-8")
    assert r.returncode == 2, stderr
    assert reason in stderr
    assert "대신 할 일" in stderr
    log = read_log(tmp_path)
    assert len(log) == 1
    assert log[0]["reason"] in stderr


@pytest.mark.parametrize("tool,command", ALLOWED)
def test_allowed(tmp_path, tool, command):
    r = run_hook(tmp_path, tool, command)
    assert r.returncode == 0, r.stderr.decode("utf-8")
    assert read_log(tmp_path) == []


def test_other_tools_pass(tmp_path):
    payload = json.dumps({"tool_name": "Read", "tool_input": {"file_path": ".env"}})
    assert run_hook(tmp_path, None, raw=payload).returncode == 0


def test_bad_json_blocks(tmp_path):
    assert run_hook(tmp_path, None, raw="{not json").returncode == 2


def test_log_format_and_numbering(tmp_path):
    run_hook(tmp_path, "Bash", "git push")
    run_hook(tmp_path, "PowerShell", "bq rm -t ai_dev.t")
    log = read_log(tmp_path)
    assert [e["id"] for e in log] == ["B-0001", "B-0002"]
    for e in log:
        assert set(e) == {"id", "ts", "hook", "command_summary", "reason", "suggested", "command_masked"}
        assert e["hook"] == "check_bash"
    assert log[1]["command_summary"].startswith("[PowerShell]")


def test_concurrent_blocks_get_unique_ids(tmp_path):
    commands = [("Bash", "git push"), ("PowerShell", "bq rm -t ai_dev.t"), ("Bash", "cat .env"),
                ("PowerShell", "Get-Content .env")] * 3
    with ThreadPoolExecutor(max_workers=len(commands)) as pool:
        results = list(pool.map(lambda c: run_hook(tmp_path, *c), commands))
    assert all(r.returncode == 2 for r in results)
    ids = [e["id"] for e in read_log(tmp_path)]
    assert sorted(ids) == [f"B-{i:04d}" for i in range(1, len(commands) + 1)]


def test_block_kept_when_log_write_fails(tmp_path):
    # hook_blocks.jsonl 자리에 폴더가 있으면 기록이 실패한다
    (tmp_path / ".dev" / "hook_blocks.jsonl").mkdir(parents=True)
    r = run_hook(tmp_path, "Bash", "git push")
    stderr = r.stderr.decode("utf-8")
    assert r.returncode == 2
    assert "git_push" in stderr and "대신 할 일" in stderr
    assert "hook_blocks.jsonl 기록 실패" in stderr


def test_block_kept_when_devlog_missing(tmp_path):
    # Hook을 devlog.py가 없는 곳으로 옮겨 실행한다
    hook = tmp_path / ".claude" / "hooks" / "check_bash.py"
    hook.parent.mkdir(parents=True)
    shutil.copy(HOOK, hook)
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": "bq rm -t ai_dev.t"}})
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(tmp_path)}
    r = subprocess.run([sys.executable, str(hook)], input=payload.encode("utf-8"),
                       capture_output=True, env=env, timeout=30)
    stderr = r.stderr.decode("utf-8")
    assert r.returncode == 2
    assert "destructive_command" in stderr
    assert "기록 실패: FileNotFoundError" in stderr


def test_devlog_loaded_from_project_dir(tmp_path):
    # ${CLAUDE_PROJECT_DIR}의 devlog.py를 먼저 쓴다
    stub = tmp_path / "scripts" / "log" / "devlog.py"
    stub.parent.mkdir(parents=True)
    stub.write_text(
        "from pathlib import Path\n"
        "def append(name, record, base=None):\n"
        "    Path(base).mkdir(parents=True, exist_ok=True)\n"
        "    (Path(base) / 'stub_called').write_text(name, encoding='utf-8')\n",
        encoding="utf-8")
    r = run_hook(tmp_path, "Bash", "git push")
    assert r.returncode == 2
    assert (tmp_path / ".dev" / "stub_called").read_text(encoding="utf-8") == "hook_blocks"


def test_log_has_summary_not_secret(tmp_path):
    secret = "sk-TEST1234567890SECRET"
    run_hook(tmp_path, "Bash", f"cat .env && echo {secret}")
    text = (tmp_path / ".dev" / "hook_blocks.jsonl").read_text(encoding="utf-8")
    assert secret not in text
    assert "cat .env" not in read_log(tmp_path)[0]["command_summary"]


def test_command_masked_hides_values_and_keeps_command_shape(tmp_path):
    command = ("OM_TOKEN=abc123 bq query --project_id=my-proj-123 --user=dev@example.com "
               "'SELECT 1 FROM `my-proj-123.thelook_raw.orders`' > C:\\Users\\someone\\out.txt")
    r = run_hook(tmp_path, "Bash", command)
    assert r.returncode == 2
    entry = read_log(tmp_path)[0]
    masked = entry["command_masked"]
    for leak in ("abc123", "my-proj-123", "dev@example.com", "someone"):
        assert leak not in json.dumps(entry, ensure_ascii=False)
    assert masked.startswith("OM_TOKEN=<값> bq query") and "thelook_raw.orders" in masked


def test_command_masked_cut_to_200(tmp_path):
    run_hook(tmp_path, "Bash", "git push " + "x " * 300)
    masked = read_log(tmp_path)[0]["command_masked"]
    assert len(masked) == 201 and masked.endswith("…")


def test_block_recorded_when_command_keeps_secret_shape(tmp_path):
    # 가린 뒤에도 비밀 패턴이 남을 수 있어도 차단 기록은 잃지 않는다
    r = run_hook(tmp_path, "Bash", "git push https://example.test/?q=xoxb-1234567890")
    assert r.returncode == 2 and "기록 실패" not in r.stderr.decode("utf-8")
    assert read_log(tmp_path)[0]["command_masked"] == "<값>"


# ---------- 루프 모드 (결정 63 ⑪·⑭, 3-5 설계 T15·T20) ----------

def run_hook_as(project, role, tool, command):
    payload = json.dumps({"hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": {"command": command}})
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(project)}
    env.pop("HARNESS_ROLE", None)
    if role is not None:
        env["HARNESS_ROLE"] = role
    return subprocess.run([sys.executable, str(HOOK)], input=payload.encode("utf-8"),
                          capture_output=True, env=env, timeout=30)


PLAN_COMMANDS = [
    ("Bash", "cat docs/plan/00_handoff.md"),
    ("Bash", "grep -r 반복 docs/plan"),
    ("PowerShell", r"Get-Content docs\plan\01_plan_v3.md"),
    ("PowerShell", "Select-String -Path docs/plan/*.md -Pattern M3"),
]


@pytest.mark.parametrize("role", ["builder", "verifier"])
@pytest.mark.parametrize("tool,command", PLAN_COMMANDS)
def test_loop_mode_blocks_plan(tmp_path, role, tool, command):
    r = run_hook_as(tmp_path, role, tool, command)
    assert r.returncode == 2 and "loop_plan_read" in r.stderr.decode("utf-8")
    assert [e["reason"] for e in read_log(tmp_path)] == ["loop_plan_read"]


@pytest.mark.parametrize("tool,command", PLAN_COMMANDS)
def test_plan_allowed_without_harness_role(tmp_path, tool, command):
    for role in (None, ""):
        assert run_hook_as(tmp_path, role, tool, command).returncode == 0
    assert read_log(tmp_path) == []


@pytest.mark.parametrize("command", ["ls docs/planning", "cat docs/requirements/mart_x.md",
                                     "cat docs/architecture/sql_rules.md"])
def test_loop_mode_other_docs_allowed(tmp_path, command):
    assert run_hook_as(tmp_path, "builder", "Bash", command).returncode == 0


LOOP_APPROVAL_COMMANDS = [
    ("Bash", "python scripts/loop/run_loop.py --mart m --extend 2 --approver approver1 --reason r --minutes 5"),
    ("PowerShell", r"python scripts\loop\run_loop.py --mart m --reset-streak t:duplicate_rows --approver approver1 --reason r --minutes 5"),
    ("Bash", "python scripts/log/devlog.py intervention --kind approval --stage loop_extension --mart m --target t --minutes 1"),
    ("PowerShell", "python scripts/log/devlog.py intervention --kind approval --stage loop_streak_reset --mart m --target t --minutes 1"),
    ("Bash", "python -c \"import devlog; devlog.append('interventions', {'stage': 'loop_streak_reset'}, loop_record=True)\""),
    ("PowerShell", "py -c \"print('loop_extension')\""),
    ("Bash", "python scripts/log/devlog.py intervention --kind approval --stage rule_promotion --rule-id RC-001 --mart m "
             "--target t --minutes 1"),
]


@pytest.mark.parametrize("role", ["builder", "verifier"])
@pytest.mark.parametrize("tool,command", LOOP_APPROVAL_COMMANDS)
def test_ai_role_blocks_loop_approval(tmp_path, role, tool, command):
    r = run_hook_as(tmp_path, role, tool, command)
    assert r.returncode == 2 and "loop_approval_by_ai" in r.stderr.decode("utf-8")
    log = read_log(tmp_path)
    assert len(log) == 1 and log[0]["reason"] == "loop_approval_by_ai"


@pytest.mark.parametrize("tool,command", LOOP_APPROVAL_COMMANDS)
def test_person_may_record_loop_approval(tmp_path, tool, command):
    assert run_hook_as(tmp_path, None, tool, command).returncode == 0
    assert read_log(tmp_path) == []


@pytest.mark.parametrize("command", [
    "python scripts/loop/run_loop.py --mart m",
    "python scripts/log/devlog.py intervention --kind approval --stage approval_2 --mart m --target t --minutes 1",
    "grep loop_extension .dev/interventions.jsonl",
])
def test_ai_role_other_loop_commands_not_blocked_by_this_rule(tmp_path, command):
    assert run_hook_as(tmp_path, "builder", "Bash", command).returncode == 0


# ---------- B-0018: heredoc 본문의 정규식·문장은 .env 접근이 아니다 ----------

@pytest.mark.parametrize("command", [
    "python - <<'E'\nimport re\nre.findall(r\"<div class='pop'>.*?</div></div>\", text)\nE",  # B-0018 명령에 있던 모양
    "python - <<'E'\nprint(\".env 접근\")\nE",
    "python - <<'E'\nrep('a', \"설정은 .env 에 둔다\")\nE",
    "cat > x.py <<E\nmatch = '.*'\nE",
    "python - <<-E\n\tre.compile(r'.*?')\n\tE",
])
def test_heredoc_text_is_not_env_access(tmp_path, command):
    r = run_hook(tmp_path, "Bash", command)
    assert r.returncode == 0, r.stderr.decode("utf-8")
    assert read_log(tmp_path) == []


@pytest.mark.parametrize("command,reason", [
    ("python - <<'E'\nopen('.env').read()\nE", "env_read"),
    ("python - <<'E'\nopen('config/.env.local').read()\nE", "env_read"),
    ("python - <<'E'\nos.system(\"cat .env\")\nE", "env_read"),
    ("python - <<'E'\nglob.glob('.en*')\nE", "env_read"),
    ("bash <<'E'\ncat .en*\nE", "env_read"),
    ("sh <<E\ncat .env\nE", "env_read"),
    ("cat <<E | sh\ncat .en*\nE", "env_read"),
    ("cat .env <<E\nx\nE", "env_read"),
    ("python - <<'E'\n.*?\n", "env_read"),  # 끝 표시가 없으면 본문으로 보지 않는다
    ("python - <<'E'\nx = 1\nE\ncat .env", "env_read"),  # 본문 뒤 명령
    ("python - <<'E'\nos.system(\"git push\")\nE", "git_push"),
    ("bash <<'E'\nbq rm -f -t ai_dev.t\nE", "destructive_command"),
    ("python - <<'E'\nx = 1\nE\ngit push", "git_push"),
])
def test_heredoc_real_access_stays_blocked(tmp_path, command, reason):
    r = run_hook(tmp_path, "Bash", command)
    assert r.returncode == 2 and read_log(tmp_path)[-1]["reason"] == reason


def test_powershell_is_not_treated_as_heredoc(tmp_path):
    assert run_hook(tmp_path, "PowerShell", "Get-Content .en*").returncode == 2


# ---------- B-0019: 셸이 읽지 않는 본문의 해석 실패는 느슨한 나누기로 다시 검사한다 ----------
# B-0019 줄에는 명령 원문이 없다. 본문의 짝 안 맞는 따옴표(ODD)로 split_segments가 실패하는 모양을 고정한다.

ODD = "# it's\n"
SAFE_BQ = f"bq query --dry_run {LIMIT} --use_legacy_sql=false 'SELECT 1'"
_spec = importlib.util.spec_from_file_location("check_bash", HOOK)
check_bash = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check_bash)


def body(text, opener="python - <<'PY'", tag="PY"):
    with pytest.raises(ValueError):  # 시험 본문이 정말 해석 실패 경로를 타는지 확인한다
        check_bash.split_segments(ODD + text)
    return f"{opener}\n{ODD}{text}\n{tag}"


@pytest.mark.parametrize("command", [
    body(f'doc = "{SAFE_BQ}"'),
    body(f"# 예시: {SAFE_BQ}"),
    body(f'cmd = """{SAFE_BQ} \\\n  --format=json"""'),
    body('src = "cat .env.example"'),
    body("os.environ['HOME']\nprint('bq show ai_dev.t')"),
    body("git_log = 'git diff'\nstack.push(1)"),
    body("x = 1"),
    body(f'doc = "{SAFE_BQ}"', "cat > x.py <<'PY'"),
])
def test_text_with_odd_quotes_passes(tmp_path, command):
    r = run_hook(tmp_path, "Bash", command)
    assert r.returncode == 0, r.stderr.decode("utf-8")
    assert read_log(tmp_path) == []


@pytest.mark.parametrize("text,reason", [
    ("doc = 'bq rm -f -t ai_dev.t'", "destructive_command"),
    ("run(['bq', 'rm', '-f', 'ai_dev.t'])", "destructive_command"),
    (f"doc = '{SAFE_BQ}; bq rm -t ai_dev.t'", "destructive_command"),
    (f"doc = '{SAFE_BQ};bq rm -t ai_dev.t'", "destructive_command"),
    ("doc = 'bq query --use_legacy_sql=false SELECT 1'", "cost_limit_missing"),
    ("doc = 'bq query SELECT 1; echo --dry_run'", "cost_limit_missing"),
    ("doc = 'bq query --maximum_bytes_billed=1000000000 SELECT 1'", "cost_limit_exceeded"),
    (f"doc = 'bq query {LIMIT} INSERT INTO thelook_mart.t SELECT 1'", "write_outside_ai_dev"),
    ("doc = 'bq extract ai_dev.t gs://b/o.csv'", "bq_command_unknown"),
    ("doc = 'git push origin main'", "git_push"),
    ("run(['git', '-C', '.', 'push'])", "git_push"),
    ("doc = 'git \\\n  push'", "git_push"),
    ("doc = 'cat .env'", "env_read"),
    ("open('config/.env.local')", "env_read"),
])
def test_text_with_odd_quotes_keeps_rule_reason(tmp_path, text, reason):
    r = run_hook(tmp_path, "Bash", body(text))
    assert r.returncode == 2
    assert reason in r.stderr.decode("utf-8") and "parse_error" not in r.stderr.decode("utf-8")
    assert read_log(tmp_path)[-1]["reason"] == reason


@pytest.mark.parametrize("text", [
    'cmd = [\n  "bq",\n  "rm",\n  "ai_dev.t",\n]',  # bq 뒤 인자가 다른 줄
    "client = bq.query(sql)",
    'x = "bq"',
    'cmd = [\n  "git",\n  "push",\n]',
    "git.push()",
    "see .env: value",
    ".env를 읽는다",
])
def test_undecidable_text_stays_parse_error(tmp_path, text):
    r = run_hook(tmp_path, "Bash", body(text))
    assert r.returncode == 2 and read_log(tmp_path)[-1]["reason"] == "parse_error"


@pytest.mark.parametrize("command", [
    body(f"echo {SAFE_BQ}", "bash <<'SH'", "SH"),
    body("git push", "bash <<'SH'", "SH"),
    body("cat .env", "sh <<SH", "SH"),
    body(f"echo {SAFE_BQ}", "cat <<'SH' | bash", "SH"),
    body(f"Write-Output {SAFE_BQ}", "powershell -NoProfile - <<'SH'", "SH"),
    "echo \"it's\" && bq show ai_dev.t '",  # heredoc이 아닌 일반 명령
    "python - <<'PY'\nit's bq",  # 끝 표시가 없으면 본문으로 보지 않는다
])
def test_shell_read_text_stays_parse_error(tmp_path, command):
    r = run_hook(tmp_path, "Bash", command)
    assert r.returncode == 2 and read_log(tmp_path)[-1]["reason"] == "parse_error"


def test_powershell_odd_quotes_stay_parse_error(tmp_path):
    r = run_hook(tmp_path, "PowerShell", f"Write-Output \"it's {SAFE_BQ}")
    assert r.returncode == 2 and read_log(tmp_path)[-1]["reason"] == "parse_error"


# ---------- B-0020~B-0022: 셸이 읽지 않는 본문의 문장 속 "bq" ----------
# 기록에는 명령 앞부분만 있다. python - <<'EOF' 본문의 rep("...bq 명령 5...") 같은 문장으로 고정한다.
# bq 뒤 첫 토큰이 ASCII가 아닌 글자로 시작할 때만 문장으로 본다.

@pytest.mark.parametrize("command", [
    "python - <<'EOF'\nrep(\"| 차단 | bq 명령 5 |\", \"| 차단 | bq 명령 6 |\")\nEOF",
    "python - <<'EOF'\nprint('bq 명령은 막는다')\nEOF",
    "python - <<'PYEOF'\n# bq 명령 5건\nx = 1\nPYEOF",
    "python - <<'EOF'\n" + ODD + "s = 'bq 명령 5'\nEOF",  # 따옴표 짝이 안 맞는 느슨한 검사 경로
])
def test_heredoc_prose_bq_passes(tmp_path, command):
    r = run_hook(tmp_path, "Bash", command)
    assert r.returncode == 0, r.stderr.decode("utf-8")
    assert read_log(tmp_path) == []


@pytest.mark.parametrize("command,reason", [
    ("python - <<'EOF'\nos.system('bq rm -f -t ai_dev.t')\nEOF", "destructive_command"),
    ("python - <<'EOF'\nos.system('bq query --use_legacy_sql=false \"SELECT 1\"')\nEOF", "cost_limit_missing"),
    ("python - <<'EOF'\nos.system('bq update ai_dev.t')\nEOF", "destructive_command"),
    ("python - <<'EOF'\n" + ODD + "doc = 'bq rm -f -t ai_dev.t'\nEOF", "destructive_command"),
    ("bash <<'EOF'\nbq rm -f -t ai_dev.t\nEOF", "destructive_command"),
    ("bash <<'EOF'\nbq 명령\nEOF", "bq_command_unknown"),  # 셸이 읽는 본문은 예외 없음
    ("bq 명령 5", "bq_command_unknown"),  # 일반 명령도 예외 없음
])
def test_heredoc_real_bq_stays_blocked(tmp_path, command, reason):
    r = run_hook(tmp_path, "Bash", command)
    assert r.returncode == 2 and read_log(tmp_path)[-1]["reason"] == reason


# ---------- B-0012: $env:TEMP·$env:TMP는 .env 접근이 아니다 ----------
# B-0012 줄에는 명령 원문이 없다. $env:TEMP·$env:TMP 문자열을 .env 접근으로 보지 않는 것을 고정하고,
# 실제 .env 파일 접근은 계속 막는 것을 함께 본다. 그 밖의 $env: 변수 참조는 지금처럼 판정하지 않는다 (11/2 결정)

@pytest.mark.parametrize("command", [
    r'$s1 = Join-Path $env:TEMP "s1_probe.py"',
    r'python $env:TEMP\s1_probe.py',
    r'[IO.File]::WriteAllText((Join-Path $env:TMP "probe.json"), "{}")',
    r'Remove-Item "$env:TEMP\loop_settings_probe.json"',
    r'Get-ChildItem ${env:TEMP}',
])
def test_env_temp_not_env_file(tmp_path, command):
    r = run_hook(tmp_path, "PowerShell", command)
    assert r.returncode == 0, r.stderr.decode("utf-8")
    assert read_log(tmp_path) == []


@pytest.mark.parametrize("command", [
    "Get-Content .env",
    r'Get-Content "$env:TEMP\.env"',
    r'Copy-Item .env $env:TEMP\x.txt',
    r'type $env:TMP\.env.local',
])
def test_real_env_file_still_blocked(tmp_path, command):
    r = run_hook(tmp_path, "PowerShell", command)
    assert r.returncode == 2 and "env_read" in r.stderr.decode("utf-8")


# ---------- B-0016: grep·rg·findstr·Select-String의 패턴 인자는 파일이 아니다 ----------
# B-0016 줄에는 명령 원문이 없다. grep 패턴 ".*"가 fnmatch(".env", ".*")로 .env 접근으로 판정된 경우로 본다.
# 패턴 자리(-e·--regexp·/c:·-Pattern 값, 없으면 옵션이 아닌 첫 인자)만 파일 검사에서 빼고, 그 뒤 파일 인자는 계속 검사한다.

@pytest.mark.parametrize("command", [
    "cat .env",
    "cat .e*",
    "cat .*",
    "grep KEY .env",
    "rg TOKEN .env*",
    "type .env",
    "Get-Content .env",
    'grep -e ".*" .env',
    'grep -n -- ".*" .env',
    "grep -f .env scripts/x.py",
    "grep -A 3 KEY .env",
    "rg --regexp=TOKEN .env.local",
    'grep "KEY" .*',
    "Select-String -Pattern KEY -Path .env",
    "Select-String KEY .env",
    "findstr KEY .env",
    "findstr /c:KEY .env.local",
])
@pytest.mark.parametrize("tool", ["Bash", "PowerShell"])
def test_search_still_blocks_env_files(tmp_path, tool, command):
    r = run_hook(tmp_path, tool, command)
    assert r.returncode == 2 and "env_read" in r.stderr.decode("utf-8")


@pytest.mark.parametrize("command", [
    'grep -n ".*" scripts/x.py',
    'rg "foo.*bar" tests/',
    r'grep -E "^\.env" docs/a.md',
    'grep -rn -e ".*" -e ".env" scripts/',
    'rg -n ".env" docs/plan/03_harness_guide.md',
    'grep "OM_TOKEN .env" README.md',
    'Select-String -Pattern ".*" -Path scripts/x.py',
    'Select-String ".env" docs/a.md',
    r'findstr /r ".*" scripts\x.py',
])
@pytest.mark.parametrize("tool", ["Bash", "PowerShell"])
def test_search_pattern_is_not_a_file(tmp_path, tool, command):
    r = run_hook(tmp_path, tool, command)
    assert r.returncode == 0, r.stderr.decode("utf-8")
    assert read_log(tmp_path) == []


# 2-13 차단 시험 중 check_bash가 판정하는 4건(2번 Read deny, 6번 계정 확인은 check_bash 대상 아님)
@pytest.mark.parametrize("command,reason", [
    ("bq rm -f ai_dev.tmp_block_test", "destructive_command"),
    ('bq query --use_legacy_sql=false --dry_run --maximum_bytes_billed=524288000 '
     '"CREATE TABLE thelook_mart.tmp_block_test AS SELECT 1 AS x"', "write_outside_ai_dev"),
    ('bq query --use_legacy_sql=false "SELECT 1"', "cost_limit_missing"),
    ("git push --dry-run", "git_push"),
])
def test_2_13_block_tests_still_blocked(tmp_path, command, reason):
    r = run_hook(tmp_path, "Bash", command)
    assert r.returncode == 2 and reason in r.stderr.decode("utf-8")
