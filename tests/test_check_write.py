"""check_write.py Hook 시험. Hook 입력 JSON을 표준 입력으로 넣어 판정만 본다 (결정 55, 결정 56 ①·③).

파일은 쓰지 않는다. 차단 로그는 임시 폴더(CLAUDE_PROJECT_DIR)에 쌓인다.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parents[1] / ".claude" / "hooks" / "check_write.py"


def run_hook(project, agent, rel_path, tool="Write", raw=None, role=None):
    data = {"hook_event_name": "PreToolUse", "tool_name": tool,
            "tool_input": {"file_path": str(project / rel_path)}}
    if agent is not None:
        data["agent_type"] = agent
    payload = raw if raw is not None else json.dumps(data)
    env = {k: v for k, v in os.environ.items() if k != "HARNESS_ROLE"}
    env["CLAUDE_PROJECT_DIR"] = str(project)
    if role is not None:
        env["HARNESS_ROLE"] = role
    return subprocess.run([sys.executable, str(HOOK)], input=payload.encode("utf-8"),
                          capture_output=True, env=env, timeout=30)


def read_log(project):
    path = project / ".dev" / "hook_blocks.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


CHECK = "docs/requirements/mart_sales_checks/l4/C-01.sql"
GATE = "docs/requirements/mart_sales_checks/l3/G-01.sql"
IDEM = "docs/requirements/mart_sales_checks/l5/I-01.sql"

ALLOWED = [
    ("verifier", CHECK, "Write"),
    ("verifier", CHECK, "Edit"),
    ("verifier", GATE, "Write"),
    ("verifier", IDEM, "Write"),
    ("verifier", "docs/requirements/mart_sales_checks/L4/sub/C-02.sql", "Write"),
    ("verifier", "docs/requirements/mart_sales.contract.json", "Read"),
    ("verifier", CHECK, "Read"),
    ("builder", GATE, "Read"),
    ("builder", "docs/requirements/mart_sales.md", "Read"),
    ("builder", "dags/sql/stg/stg_orders.sql", "Read"),
    ("builder", "docs/contest/claim_decisions.md", "Read"),
    ("verifier", "docs/contest/claim_decisions.md", "Read"),
    ("builder", "docs/contest/measurement_report.md", "Write"),
    (None, "docs/contest/claim_decisions.md", "Edit"),
    ("builder", "dags/sql/dq/gate_stg.sql", "Read"),
    # 대시보드에는 l4·l5 검사 SQL이 들어가 builder만 읽지 못한다
    ("verifier", "out/dashboard.html", "Read"),
    ("verifier", "out/dashboard.json", "Read"),
    (None, "out/dashboard.html", "Read"),
    ("builder", "out/cards/mart_sales/mart_sales.md", "Read"),
    ("builder", "dags/sql/stg/stg_orders.sql", "Edit"),
    ("builder", "docs/requirements/mart_sales.md", "Edit"),
    # 주 세션과 다른 에이전트는 검사하지 않는다
    (None, CHECK, "Write"),
    (None, "dags/sql/dq/gate_stg.sql", "Edit"),
    (None, CHECK, "Read"),
    ("Explore", CHECK, "Write"),
    ("Explore", CHECK, "Read"),
]

BLOCKED = [
    ("verifier", "dags/sql/dq/gate_stg.sql", "Write", "verifier_write_outside_checks"),
    ("verifier", "dags/sql/stg/stg_orders.sql", "Edit", "verifier_write_outside_checks"),
    ("verifier", "docs/requirements/mart_sales.md", "Edit", "verifier_write_outside_checks"),
    ("verifier", "docs/requirements/mart_sales.contract.json", "Write", "verifier_write_outside_checks"),
    ("verifier", ".dev/progress.md", "Write", "verifier_write_outside_checks"),
    # 단계 하위 폴더(l3·l4·l5) 밖은 builder가 읽을 수 있으므로 verifier도 쓰지 않는다 (결정 56 ③)
    ("verifier", "docs/requirements/mart_sales_checks/C-01.sql", "Write", "verifier_write_outside_checks"),
    ("verifier", "docs/requirements/mart_sales_checks/l6/C-01.sql", "Write", "verifier_write_outside_checks"),
    ("verifier", "docs/requirements/mart_sales_checks/../mart_sales.md", "Write", "verifier_write_outside_checks"),
    ("verifier", "../outside_checks/C-01.sql", "Write", "verifier_write_outside_checks"),
    ("builder", CHECK, "Write", "builder_write_checks"),
    ("builder", CHECK, "Edit", "builder_write_checks"),
    ("builder", "Docs/Requirements/mart_sales_checks/C-01.sql", "Write", "builder_write_checks"),
    ("builder", "dags/../docs/requirements/mart_sales_checks/C-01.sql", "Edit", "builder_write_checks"),
    ("builder", GATE, "Edit", "builder_write_checks"),
    # 게이트 파일은 gen_dq.py가 생성한다 (결정 60)
    ("builder", ".claude/rules/learned/x.md", "Write", "builder_write_rules"),
    ("builder", ".claude/rules/learned/x.md", "Edit", "builder_write_rules"),
    ("builder", "docs/ai/rule_candidate_exclusions.md", "Write", "builder_write_rules"),
    ("builder", "docs/ai/rule_candidate_exclusions.md", "Edit", "builder_write_rules"),
    ("verifier", ".claude/rules/learned/x.md", "Write", "verifier_write_outside_checks"),
    ("verifier", "docs/ai/rule_candidate_exclusions.md", "Edit", "verifier_write_outside_checks"),
    # 사람이 정한 08 밖 결정 표 (보고서가 읽는다)
    ("builder", "docs/contest/claim_decisions.md", "Write", "builder_write_rules"),
    ("builder", "docs/contest/claim_decisions.md", "Edit", "builder_write_rules"),
    ("builder", "Docs/Contest/Claim_Decisions.md", "Write", "builder_write_rules"),
    ("verifier", "docs/contest/claim_decisions.md", "Write", "verifier_write_outside_checks"),
    ("verifier", "docs/contest/claim_decisions.md", "Edit", "verifier_write_outside_checks"),
    ("builder", "dags/harness_config.json", "Write", "builder_write_config"),
    ("builder", "dags/harness_config.json", "Edit", "builder_write_config"),
    ("builder", "Dags/Harness_Config.json", "Write", "builder_write_config"),
    ("verifier", "dags/harness_config.json", "Write", "verifier_write_outside_checks"),
    ("verifier", "dags/harness_config.json", "Edit", "verifier_write_outside_checks"),
    ("builder", "dags/sql/dq/gate_stg.sql", "Write", "builder_write_dq"),
    ("builder", "dags/sql/dq/gate_stg.sql", "Edit", "builder_write_dq"),
    ("builder", "Dags/SQL/DQ/gate_raw.sql", "Write", "builder_write_dq"),
    ("builder", CHECK, "Read", "builder_read_hidden_checks"),
    ("builder", IDEM, "Read", "builder_read_hidden_checks"),
    ("builder", "Docs/Requirements/mart_sales_checks/L5/I-01.sql", "Read", "builder_read_hidden_checks"),
    ("builder", "dags/../docs/requirements/mart_sales_checks/l4/C-01.sql", "Read", "builder_read_hidden_checks"),
    ("builder", "out/dashboard.html", "Read", "builder_read_dashboard"),
    ("builder", "out/dashboard.json", "Read", "builder_read_dashboard"),
    ("builder", "Out/Dashboard.HTML", "Read", "builder_read_dashboard"),
    ("builder", "dags/../out/dashboard.html", "Read", "builder_read_dashboard"),
]


@pytest.mark.parametrize("agent,rel,tool", ALLOWED)
def test_allowed(tmp_path, agent, rel, tool):
    r = run_hook(tmp_path, agent, rel, tool)
    assert r.returncode == 0, r.stderr.decode("utf-8")
    assert read_log(tmp_path) == []


@pytest.mark.parametrize("agent,rel,tool,reason", BLOCKED)
def test_blocked(tmp_path, agent, rel, tool, reason):
    r = run_hook(tmp_path, agent, rel, tool)
    stderr = r.stderr.decode("utf-8")
    assert r.returncode == 2
    assert reason in stderr and "대신 할 일" in stderr
    log = read_log(tmp_path)
    assert len(log) == 1
    assert log[0]["hook"] == "check_write" and log[0]["reason"] == reason
    assert log[0]["command_summary"].startswith(f"[{tool}] {agent} -> ")
    assert log[0]["command_masked"].startswith(f"[{tool}] {agent} -> ")
    assert str(tmp_path) not in log[0]["command_masked"]


def test_command_masked_is_repo_relative(tmp_path):
    run_hook(tmp_path, "builder", CHECK)
    entry = read_log(tmp_path)[0]
    assert entry["command_masked"] == f"[Write] builder -> {CHECK}"
    assert entry["command_summary"] == entry["command_masked"]


@pytest.mark.parametrize("path", ["C:\\Users\\someone\\notes.md", "/home/someone/notes.md", "/Users/someone/notes.md"])
def test_user_path_not_in_summary(tmp_path, path):
    raw = json.dumps({"tool_name": "Write", "agent_type": "verifier", "tool_input": {"file_path": path}})
    assert run_hook(tmp_path, "verifier", "", raw=raw).returncode == 2
    entry = read_log(tmp_path)[0]
    assert entry["command_summary"] == "[Write] verifier -> <repo 밖 경로>"
    assert "someone" not in json.dumps(entry, ensure_ascii=False)


def test_command_masked_hides_path_outside_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    outside = tmp_path / "someone" / "secret_notes.md"
    raw = json.dumps({"tool_name": "Write", "agent_type": "verifier", "tool_input": {"file_path": str(outside)}})
    assert run_hook(repo, "verifier", "", raw=raw).returncode == 2
    assert read_log(repo)[0]["command_masked"] == "[Write] verifier -> <repo 밖 경로>"


# 역할 환경변수 HARNESS_ROLE을 agent_type보다 먼저 본다 (결정 56 ①)
ROLE_CASES = [
    # (HARNESS_ROLE, agent_type, 경로, 도구, 기대 이유 또는 None)
    ("builder", None, CHECK, "Read", "builder_read_hidden_checks"),
    ("builder", None, GATE, "Write", "builder_write_checks"),
    ("verifier", None, "dags/sql/dq/gate_stg.sql", "Write", "verifier_write_outside_checks"),
    ("verifier", None, CHECK, "Write", None),
    ("builder", "verifier", CHECK, "Read", "builder_read_hidden_checks"),
    ("verifier", "builder", CHECK, "Write", None),
    # 모르는 값이면 agent_type으로 넘어간다
    ("tester", "builder", CHECK, "Read", "builder_read_hidden_checks"),
    ("tester", None, CHECK, "Read", None),
    ("", None, CHECK, "Write", None),
]


@pytest.mark.parametrize("role,agent,rel,tool,reason", ROLE_CASES)
def test_harness_role(tmp_path, role, agent, rel, tool, reason):
    r = run_hook(tmp_path, agent, rel, tool, role=role)
    if reason is None:
        assert r.returncode == 0, r.stderr.decode("utf-8")
        assert read_log(tmp_path) == []
    else:
        assert r.returncode == 2 and reason in r.stderr.decode("utf-8")
        resolved = role if role in ("builder", "verifier") else agent
        assert read_log(tmp_path)[0]["command_summary"].startswith(f"[{tool}] {resolved} -> ")


def test_verifier_without_file_path_blocked(tmp_path):
    raw = json.dumps({"tool_name": "Write", "agent_type": "verifier", "tool_input": {}})
    r = run_hook(tmp_path, None, "", raw=raw)
    assert r.returncode == 2


def test_other_tools_ignored(tmp_path):
    raw = json.dumps({"tool_name": "Bash", "agent_type": "verifier", "tool_input": {"command": "echo x > a.sql"}})
    assert run_hook(tmp_path, None, "", raw=raw).returncode == 0


def test_bad_json_blocked(tmp_path):
    r = run_hook(tmp_path, None, "", raw="{not json")
    assert r.returncode == 2 and "JSON" in r.stderr.decode("utf-8")


def test_block_kept_when_log_write_fails(tmp_path):
    (tmp_path / ".dev" / "hook_blocks.jsonl").mkdir(parents=True)
    r = run_hook(tmp_path, "builder", CHECK)
    assert r.returncode == 2
    assert "hook_blocks.jsonl 기록 실패" in r.stderr.decode("utf-8")


def test_registered_in_settings():
    settings = json.loads((HOOK.parents[1] / "settings.json").read_text(encoding="utf-8"))
    entries = [e for e in settings["hooks"]["PreToolUse"] if e["matcher"] == "Write|Edit|Read"]
    assert any("check_write.py" in h["command"] for e in entries for h in e["hooks"])
