"""devlog.py 시험. 모든 기록은 임시 폴더에만 쓴다 (실제 .dev에는 쓰지 않는다)."""
import importlib.util
import json
import os
import subprocess
import sys
import threading
from datetime import datetime, timedelta
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "log" / "devlog.py"
_spec = importlib.util.spec_from_file_location("devlog", SCRIPT)
devlog = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(devlog)
DevlogError = devlog.DevlogError
sys.path.insert(0, str(Path(__file__).resolve().parent))
from config_fixture import prod  # noqa: E402


def rejection(**over):
    r = {"mart": "mart_returns", "task": "stg_returns", "iteration": 2, "contract_version": 1, "caught_by_rung": "L2",
         "error_type": "type_mismatch", "error_class": "syntax",
         "detail": "INSERT 컬럼 목록과 SELECT 식 순서가 달라 타입 불일치"}
    r.update(over)
    return r


def intervention(**over):
    r = {"mart": "mart_returns", "kind": "approval", "target": "PR #12", "minutes_spent": 6,
         "note": "레이어 게이트 결과 확인 후 결재"}
    r.update(over)
    if r["kind"] == "approval":
        r.setdefault("stage", "approval_2")
    return r


def cost(**over):
    r = {"run_id": "RUN-007", "mart": "mart_returns", "iteration": 2, "role": "builder", "model": "claude-opus-5-5",
         "started": "2026-10-28T13:40:00+09:00", "ended": "2026-10-28T14:55:00+09:00",
         "bq_bytes_processed": 0}
    r.update(over)
    return r


def hook_block(**over):
    r = {"hook": "check_bash", "command_summary": "bq query without --maximum_bytes_billed",
         "reason": "cost_limit_missing", "suggested": "--dry_run 후 --maximum_bytes_billed 를 걸고 다시 실행"}
    r.update(over)
    return r


def ladder(**over):
    r = {"task": "stg_returns", "iteration": 2, "contract_version": 1, "request_kind": "new_build",
         "modules": {"expert": {"on": [], "version": None}}, "bytes_total": 1048576,
         "rungs": [
             {"rung": "L0", "ds": None, "status": "pass", "metrics": {}, "error_type": None, "error_class": None},
             {"rung": "L1", "ds": "2026-10-28", "status": "pass", "metrics": {"bytes_processed": 1048576},
              "error_type": None, "error_class": None},
             {"rung": "L2", "ds": "2026-10-28", "status": "fail", "metrics": {}, "error_type": "type_mismatch",
              "error_class": "syntax"},
         ],
         "verdict": "reject", "halt_reason": None}
    r.update(over)
    return r


def lines(path):
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def is_kst(ts):
    return datetime.fromisoformat(ts).utcoffset() == timedelta(hours=9)


# ---------- 정상 기록 ----------

def test_rejection_written_in_03_order(tmp_path):
    e = devlog.append("rejections", rejection(), tmp_path)
    assert list(e) == ["id", "ts", "mart", "task", "iteration", "contract_version", "caught_by_rung", "error_type",
                       "error_class", "detail", "fixed_in_iteration", "rule_promoted", "evidence"]
    assert e["id"] == "R-0001" and is_kst(e["ts"])
    assert e["fixed_in_iteration"] is None and e["rule_promoted"] is None and e["evidence"] is None
    assert lines(tmp_path / "rejections.jsonl") == [e]


@pytest.mark.parametrize("command,leak,mark", [
    ("OM_TOKEN=abcdef123 python x.py", "abcdef123", "OM_TOKEN=<값>"),
    ("API_KEY='a b c' python x.py", "a b c", "API_KEY=<값>"),
    ("SECRET=hunter2 x", "hunter2", "SECRET=<값>"),
    ("PASSWORD=\"p w\" x", "p w", "PASSWORD=<값>"),
    ("tool --token abcdef123", "abcdef123", "--token <값>"),
    ("curl -H 'Authorization: Bearer abc.def-123'", "abc.def-123", "Bearer"),
    ("echo 0123456789abcdef0123456789abcdef", "0123456789abcdef", "echo <값>"),
    ("echo QUJDREVGR0hJSktMTU5PUFFSU1RVVg==", "QUJDREVGR0hJ", "echo <값>"),
    ("echo 550e8400-e29b-41d4-a716-446655440000", "550e8400", "echo <값>"),
    (r"type C:\Users\hong\work\a.txt", "hong", "type <경로>"),
    ("type C:/Users/hong/work/a.txt", "hong", "type <경로>"),
    (r'type "C:\Users\Hong Gil\a b.txt" x', "Gil", 'type "<경로>" x'),
    ("cat /c/Users/hong/work/a.txt", "hong", "cat <경로>"),
    ("cat /home/hong/a.txt", "hong", "cat <경로>"),
    ("cat /Users/hong/a.txt", "hong", "cat <경로>"),
    ("bq show my-proj-123:ai_dev.t", "my-proj-123", "<프로젝트>:ai_dev.t"),
    (f"bq show my-proj-123.{prod('raw')}.t", "my-proj-123", f"<프로젝트>.{prod('raw')}.t"),
    ("bq query 'select * from `my-proj-123.ai_dev.t`'", "my-proj-123", "`<프로젝트>.ai_dev.t`"),
    ("bq ls --project_id=my-proj-123", "my-proj-123", "--project_id=<프로젝트>"),
    ("gcloud config set project my-proj-123", "my-proj-123", "project <프로젝트>"),
    ("git log --author=dev.a+b@example.co.kr", "example", "<메일>"),
])
def test_mask_command_hides(command, leak, mark):
    masked = devlog.mask_command(command)
    assert leak not in masked and mark in masked


@pytest.mark.parametrize("command", [
    "bq query --maximum_bytes_billed=524288000 --dry_run 'select 1'",
    "python scripts/metrics/dashboard_data.py",
    "cat .dev/ladder_results/mart_user_returns/mart_user_returns-v1-post-1.json",
    "bq rm -f -t ai_dev.tmp_orders",
    "git push origin week4/hook-dashboard-fix",
    "cat .env",
])
def test_mask_command_keeps_what_judging_needs(command):
    assert devlog.mask_command(command) == command


def test_mask_command_cuts_after_masking():
    assert devlog.mask_command("x" * 200) != "x" * 200  # 20자 넘는 덩어리는 먼저 가린다
    assert devlog.mask_command("a " * 100) == "a " * 100
    masked = devlog.mask_command("a " * 101)
    assert masked == "a " * 100 + "…"
    # 200자 경계에 걸친 비밀의 앞부분이 남지 않는다
    assert "A1b2" not in devlog.mask_command("a " * 95 + "A1b2C3d4E5f6G7h8I9j0K1")


def test_mask_command_leftover_secret_masks_all():
    assert devlog.mask_command("x xoxb-1234567890") == "<값>"  # 20자가 안 돼 덩어리로 안 잡히는 토큰


def test_hook_block_command_masked_optional(tmp_path):
    (tmp_path / "hook_blocks.jsonl").write_text(json.dumps({"id": "B-0001", "ts": "2026-11-05T10:00:00+09:00",
                                                            **hook_block()}) + "\n", encoding="utf-8")
    devlog.validate_hook_block(hook_block())  # 과거 형식 줄은 유효
    assert "command_masked" not in devlog.read_lines(tmp_path / "hook_blocks.jsonl")[0]
    new = devlog.append("hook_blocks", hook_block(command_masked="bq query <값>"), tmp_path)
    assert new["id"] == "B-0002" and new["command_masked"] == "bq query <값>"
    with pytest.raises(DevlogError, match="command_masked"):
        devlog.append("hook_blocks", hook_block(command_masked=""), tmp_path)


def test_intervention_cost_hook_block_written(tmp_path):
    h = devlog.append("interventions", intervention(), tmp_path)
    c = devlog.append("cost", cost(), tmp_path)
    b = devlog.append("hook_blocks", hook_block(), tmp_path)
    assert h["id"] == "H-0001" and is_kst(h["ts"])
    assert list(c) == ["run_id", "mart", "iteration", "role", "model", "started", "ended", "bq_bytes_processed",
                       "usage_before", "usage_after", "input_tokens", "output_tokens",
                       "cache_read_tokens", "cache_write_tokens", "total_cost_usd"]
    assert c["run_id"] == "RUN-007" and c["role"] == "builder" and c["model"] == "claude-opus-5-5" and "ts" not in c
    assert "plan" not in c
    assert c["usage_before"] is None and c["input_tokens"] is None
    assert c["cache_read_tokens"] is None and c["total_cost_usd"] is None
    assert b["id"] == "B-0001" and is_kst(b["ts"])


@pytest.mark.parametrize("kind,extra", [
    ("correction", {}),
    ("manual_check", {}),
    ("ops_run", {}),
    ("requirement_change", {"cause": "ladder_fail"}),
    ("requirement_change", {"cause": "defect"}),
    ("post_approval_defect", {"found_stage": "운영 첫 실행", "detail": "반품일 기준 누락", "missed_by_rung": "L4"}),
    ("module_toggle", {"mart": None, "scope": "dba", "now": False}),
    ("module_toggle", {"scope": "EX-DBA-05", "now": True}),
])
def test_intervention_kinds(tmp_path, kind, extra):
    e = devlog.append("interventions", intervention(kind=kind, **extra), tmp_path)
    assert e["kind"] == kind


@pytest.mark.parametrize("stage", ["approval_1", "approval_2", "ops"])
def test_approval_stages(tmp_path, stage):
    e = devlog.append("interventions", intervention(stage=stage), tmp_path)
    assert e["stage"] == stage


def test_rule_promotion_needs_rule_id_and_is_a_human_cli_record(tmp_path):
    e = devlog.append("interventions", intervention(stage="rule_promotion", rule_id="RC-001"), tmp_path)
    assert e["stage"] == "rule_promotion" and e["rule_id"] == "RC-001"
    with pytest.raises(devlog.DevlogError, match="rule_id"):
        devlog.append("interventions", intervention(stage="rule_promotion"), tmp_path)
    with pytest.raises(devlog.DevlogError, match="rule_id"):
        devlog.append("interventions", intervention(stage="rule_promotion", rule_id="R-0001"), tmp_path)
    with pytest.raises(devlog.DevlogError, match="없는 칸"):
        devlog.append("interventions", intervention(stage="ops", rule_id="RC-001"), tmp_path)
    assert devlog.main(["--dev-dir", str(tmp_path), "intervention", "--kind", "approval", "--stage", "rule_promotion",
                        "--rule-id", "RC-002", "--mart", "mart_returns", "--target", "PR #40 merge",
                        "--minutes", "5"]) == 0


def loop_approval(stage="loop_extension", **over):
    r = intervention(stage=stage, target="mart_returns 반복 연장 +2", minutes_spent=5, note="",
                     contract_version=1, approver="approver1", reason="L4 원천 비교가 반품일 기준으로 다시 실패")
    if stage == "loop_extension":
        r["extra_iterations"] = 2
    else:
        r["streak_key"] = "stg_returns:type_mismatch"
    r.update(over)
    return r


@pytest.mark.parametrize("stage", ["loop_extension", "loop_streak_reset"])
def test_loop_approval_written_by_loop(tmp_path, stage):
    # 루프 결재는 run_loop.py 옵션으로만 기록한다 (결정 63 ⑫~⑭, 08 V4-1)
    e = devlog.append("interventions", loop_approval(stage), tmp_path, loop_record=True)
    assert e["stage"] == stage and e["approver"] == "approver1" and e["minutes_spent"] == 5
    assert ("extra_iterations" in e) == (stage == "loop_extension")
    assert ("streak_key" in e) == (stage == "loop_streak_reset")


@pytest.mark.parametrize("stage", ["loop_extension", "loop_streak_reset"])
def test_loop_approval_without_loop_record_rejected(tmp_path, stage):
    with pytest.raises(DevlogError, match="run_loop.py"):
        devlog.append("interventions", loop_approval(stage), tmp_path)
    assert not (tmp_path / "interventions.jsonl").exists()


@pytest.mark.parametrize("stage,over,message", [
    ("loop_extension", {"extra_iterations": 0}, "extra_iterations"),
    ("loop_extension", {"extra_iterations": "2"}, "extra_iterations"),
    ("loop_extension", {"extra_iterations": True}, "extra_iterations"),
    ("loop_extension", {"approver": "홍길동"}, "approver"),
    ("loop_extension", {"approver": "approver0"}, "approver"),
    ("loop_extension", {"approver": "Approver1"}, "approver"),
    ("loop_extension", {"reason": " "}, "reason"),
    ("loop_extension", {"contract_version": 0}, "contract_version"),
    ("loop_extension", {"streak_key": "stg_returns:type_mismatch"}, "없는 칸"),
    ("loop_streak_reset", {"streak_key": "stg_returns"}, "streak_key"),
    ("loop_streak_reset", {"streak_key": "stg-returns:type_mismatch"}, "streak_key"),
    ("loop_streak_reset", {"streak_key": "stg_returns:not_a_type"}, "streak_key"),
    ("loop_streak_reset", {"extra_iterations": 2}, "없는 칸"),
])
def test_loop_approval_invalid(tmp_path, stage, over, message):
    with pytest.raises(DevlogError, match=message):
        devlog.append("interventions", loop_approval(stage, **over), tmp_path, loop_record=True)


@pytest.mark.parametrize("stage,field", [
    ("loop_extension", "extra_iterations"), ("loop_extension", "approver"), ("loop_extension", "reason"),
    ("loop_extension", "contract_version"), ("loop_streak_reset", "streak_key"), ("loop_streak_reset", "approver"),
    ("loop_extension", "minutes_spent"),
])
def test_loop_approval_missing_field(tmp_path, stage, field):
    r = loop_approval(stage)
    del r[field]
    with pytest.raises(DevlogError, match="필수 칸"):
        devlog.append("interventions", r, tmp_path, loop_record=True)


def test_loop_fields_not_allowed_on_other_stages(tmp_path):
    with pytest.raises(DevlogError, match="없는 칸"):
        devlog.append("interventions", intervention(approver="approver1"), tmp_path)


def test_cost_tokens_and_cost_usd(tmp_path):
    c = devlog.append("cost", cost(input_tokens=1200, output_tokens=300, cache_read_tokens=50000,
                                   cache_write_tokens=8000, total_cost_usd=0.42), tmp_path)
    assert c["cache_read_tokens"] == 50000 and c["cache_write_tokens"] == 8000 and c["total_cost_usd"] == 0.42


def test_ex_error_type_allowed(tmp_path):
    e = devlog.append("rejections", rejection(error_type="ex.orphan_rows", error_class="semantic"), tmp_path)
    assert e["error_type"] == "ex.orphan_rows"


def test_pii_column_error_type_allowed(tmp_path):
    e = devlog.append("rejections", rejection(caught_by_rung="L0", error_type="pii_column", error_class="semantic"),
                      tmp_path)
    assert e["error_type"] == "pii_column"


def test_l6_rejection_with_post_iteration(tmp_path):
    e = devlog.append("rejections", rejection(caught_by_rung="L6", iteration="post", error_type="lineage_missing",
                                              error_class="semantic"), tmp_path)
    assert e["iteration"] == "post"


# ---------- id 이어 매기기 ----------

def test_ids_continue_per_file(tmp_path):
    ids = [devlog.append("interventions", intervention(), tmp_path)["id"] for _ in range(3)]
    assert ids == ["H-0001", "H-0002", "H-0003"]
    assert devlog.append("hook_blocks", hook_block(), tmp_path)["id"] == "B-0001"


def test_cost_one_line_per_call(tmp_path):
    # claude -p 호출 1회 = 1줄. 같은 루프는 run_id를 같이 쓰고 도구가 id를 매기지 않는다 (결정 57)
    calls = [cost(iteration=0, role="verifier", model="claude-sonnet-5-5"),
             cost(iteration=1, role="builder"), cost(iteration=2, role="builder")]
    entries = [devlog.append("cost", c, tmp_path) for c in calls]
    assert [e["run_id"] for e in entries] == ["RUN-007"] * 3
    assert [(e["iteration"], e["role"]) for e in entries] == [(0, "verifier"), (1, "builder"), (2, "builder")]
    assert all("id" not in e for e in entries)
    lines = (tmp_path / "cost.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3


def test_ids_continue_after_existing_lines(tmp_path):
    path = tmp_path / "rejections.jsonl"
    path.write_text('{"id": "R-0007", "mart": "m", "task": "t", "error_type": "syntax"}\n', encoding="utf-8")
    before = path.read_bytes()
    e = devlog.append("rejections", rejection(), tmp_path)
    assert e["id"] == "R-0008"
    assert path.read_bytes().startswith(before)  # 기존 줄은 그대로
    assert len(lines(path)) == 2


def test_concurrent_appends_get_unique_ids(tmp_path):
    errors = []

    def worker():
        try:
            for _ in range(5):
                devlog.append("hook_blocks", hook_block(), tmp_path)
        except Exception as exc:  # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    ids = [e["id"] for e in lines(tmp_path / "hook_blocks.jsonl")]
    assert sorted(ids) == [f"B-{i:04d}" for i in range(1, 21)]


# ---------- 형식 오류 거부 ----------

@pytest.mark.parametrize("name,record,message", [
    ("rejections", {k: v for k, v in rejection().items() if k != "detail"}, "필수 칸"),
    ("rejections", rejection(error_type="wrong_type"), "error_type"),
    ("rejections", rejection(error_type="ex.Bad-Name"), "error_type"),
    ("rejections", rejection(error_class="logic"), "error_class"),
    ("rejections", rejection(caught_by_rung="L7"), "caught_by_rung"),
    ("rejections", rejection(iteration=0), "iteration"),
    ("rejections", rejection(iteration="post"), "post"),
    ("rejections", rejection(fixed_in_iteration=3), "집계"),
    ("rejections", rejection(rule_promoted="RC-001"), "집계"),
    ("rejections", rejection(new_field=1), "없는 칸"),
    ("rejections", rejection(id="R-0100"), "도구가 채운다"),
    ("rejections", {k: v for k, v in rejection().items() if k != "contract_version"}, "필수 칸"),
    ("rejections", rejection(contract_version=0), "contract_version"),
    ("rejections", rejection(contract_version="1"), "contract_version"),
    ("interventions", {k: v for k, v in intervention().items() if k != "stage"}, "필수 칸"),
    ("interventions", intervention(stage="approval_3"), "stage"),
    ("interventions", intervention(kind="correction", stage="approval_1"), "없는 칸"),
    ("interventions", intervention(kind="chat"), "kind"),
    ("interventions", intervention(mart=None), "module_toggle"),
    ("interventions", intervention(kind="requirement_change"), "필수 칸"),
    ("interventions", intervention(kind="requirement_change", cause="boss"), "cause"),
    ("interventions", intervention(kind="post_approval_defect", found_stage="운영", detail="x"), "필수 칸"),
    ("interventions", intervention(kind="post_approval_defect", found_stage="운영", detail="x", missed_by_rung="L9"), "missed_by_rung"),
    ("interventions", intervention(kind="module_toggle", scope="dba"), "필수 칸"),
    ("interventions", intervention(kind="module_toggle", scope="dba", now="yes"), "now"),
    ("interventions", intervention(cause="user"), "없는 칸"),
    ("interventions", intervention(minutes_spent=-1), "minutes_spent"),
    # 요금제는 기록하지 않는다. model은 필수 (결정 57)
    ("cost", cost(plan="pro"), "plan"),
    ("cost", {k: v for k, v in cost().items() if k != "model"}, "필수 칸"),
    ("cost", cost(model=""), "model"),
    ("cost", cost(model=None), "model"),
    ("cost", {k: v for k, v in cost().items() if k != "role"}, "필수 칸"),
    ("cost", cost(role="reviewer"), "role"),
    ("cost", cost(role=None), "role"),
    ("cost", {k: v for k, v in cost().items() if k != "run_id"}, "필수 칸"),
    ("cost", cost(run_id="7"), "run_id"),
    ("cost", cost(run_id=7), "run_id"),
    ("cost", {k: v for k, v in cost().items() if k != "iteration"}, "필수 칸"),
    ("cost", cost(iteration=-1), "iteration"),
    ("cost", cost(iteration=True), "iteration"),
    ("cost", cost(iterations=4), "iterations"),
    ("cost", cost(started="2026-10-28T13:40:00+00:00"), "+09:00"),
    ("cost", cost(ended="2026-10-28T12:00:00+09:00"), "앞섬"),
    ("cost", cost(input_tokens="많음"), "input_tokens"),
    ("cost", cost(cache_read_tokens="많음"), "cache_read_tokens"),
    ("cost", cost(cache_write_tokens=True), "cache_write_tokens"),
    ("cost", cost(total_cost_usd="0.4"), "total_cost_usd"),
    ("cost", {k: v for k, v in cost().items() if k != "bq_bytes_processed"}, "필수 칸"),
    ("cost", cost(ts="2026-10-28T13:40:00+09:00"), "도구가 채운다"),
    ("hook_blocks", hook_block(reason=""), "reason"),
])
def test_invalid_records_rejected(tmp_path, name, record, message):
    with pytest.raises(DevlogError, match=message.replace("+", r"\+")):
        devlog.append(name, record, tmp_path)
    assert not (tmp_path / f"{name}.jsonl").exists() or lines(tmp_path / f"{name}.jsonl") == []


def test_second_same_type_rejection_needs_evidence(tmp_path):
    devlog.append("rejections", rejection(), tmp_path)
    with pytest.raises(DevlogError, match="evidence"):
        devlog.append("rejections", rejection(iteration=3), tmp_path)
    e = devlog.append("rejections", rejection(iteration=3, evidence=[{"order_id": 1, "expected": 2, "actual": 3}]), tmp_path)
    assert e["id"] == "R-0002"
    # 다른 task나 다른 유형이면 첫 반려로 본다
    assert devlog.append("rejections", rejection(task="mart_returns_daily"), tmp_path)["evidence"] is None
    assert devlog.append("rejections", rejection(error_type="null_violation", error_class="semantic"), tmp_path)["evidence"] is None


# ---------- 비밀값 거부 ----------

SECRETS = [
    "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJhaS1idWlsZGVyIn0.c2lnbmF0dXJlLXZhbHVl",
    "sk-ABCDEFGHIJKLMNOP1234",
    "ghp_ABCDEFGHIJKLMNOPQRSTUVWX1234",
    "AKIAABCDEFGHIJKLMNOP",
    "AIzaSyA-1234567890abcdefghijklmnopqrstu",
    "password=hunter2secret",
    "api_key: abcd1234efgh",
    "Authorization: Bearer abcdefghijklmnop1234",
    "-----BEGIN PRIVATE KEY-----",
]


@pytest.mark.parametrize("secret", SECRETS)
def test_secrets_rejected(tmp_path, secret):
    with pytest.raises(DevlogError, match="비밀값") as info:
        devlog.append("interventions", intervention(note=f"확인함 {secret}"), tmp_path)
    assert secret not in str(info.value)
    assert not (tmp_path / "interventions.jsonl").exists()


def test_secret_in_nested_evidence_rejected(tmp_path):
    devlog.append("rejections", rejection(), tmp_path)
    with pytest.raises(DevlogError, match=r"evidence\[0\]"):
        devlog.append("rejections", rejection(evidence=[{"row": "token=abcdef123456"}]), tmp_path)
    assert len(lines(tmp_path / "rejections.jsonl")) == 1


def test_secret_in_ladder_rejected(tmp_path):
    bad = ladder()
    bad["rungs"][1]["metrics"] = {"note": SECRETS[0]}
    with pytest.raises(DevlogError, match="비밀값"):
        devlog.write_ladder_result("mart_returns", bad, tmp_path)
    assert not (tmp_path / "ladder_results").exists()


# ---------- ladder_result ----------

def test_ladder_result_path_and_content(tmp_path):
    path = devlog.write_ladder_result("mart_returns", ladder(), tmp_path)
    assert path == tmp_path / "ladder_results" / "mart_returns" / "stg_returns-v1-2.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert list(data) == ["task", "iteration", "contract_version", "request_kind", "modules", "ts", "bytes_total",
                          "rungs", "verdict", "halt_reason"]
    assert data["request_kind"] == "new_build" and data["rungs"][1]["ds"] == "2026-10-28"
    assert is_kst(data["ts"])


def test_ladder_result_post_and_halt(tmp_path):
    post = ladder(iteration="post", verdict="pass",
                  rungs=[{"rung": "L6", "ds": None, "status": "pass", "metrics": {"edges": 3}, "error_type": None,
                          "error_class": None}])
    assert devlog.write_ladder_result("mart_returns", post, tmp_path).name == "stg_returns-v1-post-1.json"
    halt = ladder(iteration=3, verdict="halt", halt_reason="infra_error", rungs=[])
    assert devlog.write_ladder_result("mart_returns", halt, tmp_path).name == "stg_returns-v1-3.json"


def test_ladder_result_post_appends_sequence(tmp_path):
    """L6 재확인은 post-<n> 순번으로 추가하고 이전 파일은 그대로 둔다. 최신 = 가장 큰 n (결정 67)."""
    def post(verdict, status, error_type=None):
        return ladder(iteration="post", verdict=verdict,
                      rungs=[{"rung": "L6", "ds": None, "status": status, "metrics": {}, "error_type": error_type,
                              "error_class": "semantic" if error_type else None}])
    assert devlog.latest_post("mart_returns", "stg_returns", 1, tmp_path) is None
    first = devlog.write_ladder_result("mart_returns", post("reject", "fail", "lineage_missing"), tmp_path)
    before = first.read_text(encoding="utf-8")
    folder = first.parent
    (folder / "stg_returns-v1-post-9x.json").write_text("{}", encoding="utf-8")  # 순번 형식이 아닌 파일은 무시
    (folder / "stg_returns-v1-post-10.json").write_text(before, encoding="utf-8")  # 빈 순번이 있어도 가장 큰 n + 1
    second = devlog.write_ladder_result("mart_returns", post("pass", "pass"), tmp_path)
    assert (first.name, second.name) == ("stg_returns-v1-post-1.json", "stg_returns-v1-post-11.json")
    assert first.read_text(encoding="utf-8") == before
    latest = devlog.latest_post("mart_returns", "stg_returns", 1, tmp_path)
    assert (latest["_n"], latest["_name"], latest["verdict"], latest["iteration"]) == \
        (11, "stg_returns-v1-post-11.json", "pass", "post")
    assert devlog.latest_post("mart_returns", "stg_returns", 2, tmp_path) is None


def test_ladder_result_halt_detail(tmp_path):
    detail = {"exception": "UnicodeDecodeError", "message": "'utf-8' codec can't decode byte 0xbc"}
    halt = ladder(iteration=3, verdict="halt", halt_reason="infra_error", rungs=[], halt_detail=detail)
    path = devlog.write_ladder_result("mart_returns", halt, tmp_path)
    assert json.loads(path.read_text(encoding="utf-8"))["halt_detail"] == detail
    with pytest.raises(devlog.DevlogError, match="halt일 때만"):
        devlog.write_ladder_result("mart_returns", ladder(iteration=4, halt_detail=detail), tmp_path)
    for bad in ({"exception": "X"}, {"exception": "", "message": "m"}, "X: m"):
        with pytest.raises(devlog.DevlogError, match="halt_detail"):
            devlog.write_ladder_result("mart_returns", ladder(iteration=5, verdict="halt", halt_reason="infra_error",
                                                              rungs=[], halt_detail=bad), tmp_path)


@pytest.mark.parametrize("kind", ["new_build", "change", "backfill_check"])
def test_ladder_result_request_kinds(tmp_path, kind):
    r = ladder(request_kind=kind, iteration=1)
    assert json.loads(devlog.write_ladder_result("mart_returns", r, tmp_path).read_text(encoding="utf-8"))["request_kind"] == kind


def test_ladder_result_contract_v2_restarts_without_clash(tmp_path):
    # contract v2에서 반복을 1부터 다시 세도 v1 파일과 이름이 겹치지 않는다 (결정 52 ②)
    v1 = devlog.write_ladder_result("mart_returns", ladder(iteration=1), tmp_path)
    v2 = devlog.write_ladder_result("mart_returns", ladder(iteration=1, contract_version=2), tmp_path)
    assert (v1.name, v2.name) == ("stg_returns-v1-1.json", "stg_returns-v2-1.json")


def test_ladder_result_not_overwritten(tmp_path):
    path = devlog.write_ladder_result("mart_returns", ladder(), tmp_path)
    before = path.read_bytes()
    with pytest.raises(DevlogError, match="덮어쓰지"):
        devlog.write_ladder_result("mart_returns", ladder(), tmp_path)
    assert path.read_bytes() == before


@pytest.mark.parametrize("mart,record,message", [
    ("../mart_returns", ladder(), "영문"),
    ("mart_returns", ladder(task="stg/../x"), "영문"),
    ("mart_returns", ladder(verdict="maybe"), "verdict"),
    ("mart_returns", ladder(verdict="halt", halt_reason="tired"), "halt_reason"),
    ("mart_returns", ladder(halt_reason="timeout"), "halt_reason"),
    ("mart_returns", ladder(verdict="pass"), "pass"),
    ("mart_returns", ladder(iteration="post"), "post"),
    ("mart_returns", ladder(modules={}), "modules"),
    ("mart_returns", ladder(contract_version=0), "contract_version"),
    ("mart_returns", ladder(rungs=[{"rung": "L2", "ds": None, "status": "fail", "metrics": {}, "error_type": "nope", "error_class": "syntax"}]), "error_type"),
    ("mart_returns", ladder(rungs=[{"rung": "L0", "ds": None, "status": "skip", "metrics": {}, "error_type": None, "error_class": None}]), "status"),
    # 요청 종류와 날짜 (결정 58·59)
    ("mart_returns", ladder(request_kind="hotfix"), "request_kind"),
    ("mart_returns", {k: v for k, v in ladder().items() if k != "request_kind"}, "필수 칸"),
    ("mart_returns", ladder(request_kind="backfill_check", iteration=2), "backfill_check"),
    ("mart_returns", ladder(bytes_total=-1), "bytes_total"),
    ("mart_returns", ladder(bytes_total="1MB"), "bytes_total"),
    ("mart_returns", ladder(rungs=[{"rung": "L1", "ds": "20261028", "status": "pass", "metrics": {}, "error_type": None, "error_class": None}], verdict="pass"), "ds"),
    ("mart_returns", ladder(rungs=[{"rung": "L1", "status": "pass", "metrics": {}, "error_type": None, "error_class": None}], verdict="pass"), "필수 칸"),
])
def test_ladder_result_invalid(tmp_path, mart, record, message):
    with pytest.raises(DevlogError, match=message):
        devlog.write_ladder_result(mart, record, tmp_path)
    assert not (tmp_path / "ladder_results").exists() or not any((tmp_path / "ladder_results").rglob("*.json"))


# ---------- 명령 ----------

def run_cli(tmp_path, *args):
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    return subprocess.run([sys.executable, str(SCRIPT), "--dev-dir", str(tmp_path), *args],
                          capture_output=True, text=True, encoding="utf-8", env=env, timeout=30)


def test_cli_intervention(tmp_path):
    r = run_cli(tmp_path, "intervention", "--kind", "approval", "--stage", "approval_2", "--mart", "mart_returns",
                "--target", "PR #12", "--minutes", "6", "--note", "결재")
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "H-0001"
    e = lines(tmp_path / "interventions.jsonl")[0]
    assert e["minutes_spent"] == 6 and e["target"] == "PR #12" and e["stage"] == "approval_2"
    r = run_cli(tmp_path, "intervention", "--kind", "module_toggle", "--target", "expertise",
                "--minutes", "1", "--scope", "dba", "--now", "false")
    assert r.returncode == 0, r.stderr
    assert lines(tmp_path / "interventions.jsonl")[1]["mart"] is None


def test_cli_requirement_change_defect(tmp_path):
    r = run_cli(tmp_path, "intervention", "--kind", "requirement_change", "--cause", "defect", "--mart", "mart_returns",
                "--target", "contract v3", "--minutes", "4", "--note", "결재 2 뒤 키 결함 수정")
    assert r.returncode == 0, r.stderr
    e = lines(tmp_path / "interventions.jsonl")[0]
    assert e["kind"] == "requirement_change" and e["cause"] == "defect"

def test_cli_approval_without_stage_rejected(tmp_path):
    r = run_cli(tmp_path, "intervention", "--kind", "approval", "--mart", "mart_returns",
                "--target", "PR #12", "--minutes", "6")
    assert r.returncode == 1 and "stage" in r.stderr
    assert not (tmp_path / "interventions.jsonl").exists()


@pytest.mark.parametrize("stage", ["loop_extension", "loop_streak_reset"])
def test_cli_rejects_loop_stages(tmp_path, stage):
    # 사람이 jsonl에 루프 결재를 직접 남기는 경로는 두지 않는다 (결정 63 ⑭)
    r = run_cli(tmp_path, "intervention", "--kind", "approval", "--stage", stage, "--mart", "mart_returns",
                "--target", "연장", "--minutes", "5")
    assert r.returncode == 1 and "run_loop.py" in r.stderr
    assert not (tmp_path / "interventions.jsonl").exists()


def test_cli_rejects_bad_input(tmp_path):
    r = run_cli(tmp_path, "intervention", "--kind", "requirement_change", "--mart", "mart_returns",
                "--target", "요구서", "--minutes", "3")
    assert r.returncode == 1 and "기록하지 않음" in r.stderr
    assert not (tmp_path / "interventions.jsonl").exists()


def test_cli_json_commands(tmp_path):
    r = run_cli(tmp_path, "rejection", "--json", json.dumps(rejection(), ensure_ascii=False))
    assert r.returncode == 0 and r.stdout.strip() == "R-0001"
    f = tmp_path / "result.json"
    f.write_text(json.dumps(ladder()), encoding="utf-8")
    r = run_cli(tmp_path, "ladder", "--mart", "mart_returns", "--json-file", str(f))
    assert r.returncode == 0, r.stderr
    assert (tmp_path / "ladder_results" / "mart_returns" / "stg_returns-v1-2.json").exists()


def test_hardcoded_dataset_is_known_error_type(tmp_path):
    r = ladder(rungs=[{"rung": "L1", "ds": "2026-10-28", "status": "fail", "metrics": {},
                       "error_type": "hardcoded_dataset", "error_class": "semantic"}])
    assert devlog.write_ladder_result("mart_returns", r, tmp_path).exists()


def test_ladder_result_interrupted_tasks(tmp_path):
    """층 단위 사다리에서 일부 단계만 마치고 멈춘 task (R-0001). reject·halt 파일에만 쓴다."""
    items = [{"task": "raw_returns", "passed_rungs": ["L0", "L1", "L2", "L3"], "bytes": 2048}]
    path = devlog.write_ladder_result("mart_returns", ladder(interrupted_tasks=items), tmp_path)
    assert json.loads(path.read_text(encoding="utf-8"))["interrupted_tasks"] == items
    halt = ladder(iteration=3, verdict="halt", halt_reason="infra_error", rungs=[], interrupted_tasks=items)
    assert devlog.write_ladder_result("mart_returns", halt, tmp_path).exists()
    passed = ladder(iteration=4, verdict="pass", rungs=ladder()["rungs"][:2], interrupted_tasks=items)
    with pytest.raises(devlog.DevlogError, match="reject·halt일 때만"):
        devlog.write_ladder_result("mart_returns", passed, tmp_path)
    bad_cases = [
        [],
        [{"task": "raw_returns", "passed_rungs": ["L0"]}],
        [{"task": "raw_returns", "passed_rungs": ["L9"], "bytes": 1}],
        [{"task": "raw_returns", "passed_rungs": [], "bytes": 1}],
        [{"task": "raw_returns", "passed_rungs": ["L0"], "bytes": -1}],
        [{"task": "raw_returns", "passed_rungs": ["L0"], "bytes": True}],
        [{"task": "stg_returns", "passed_rungs": ["L0"], "bytes": 1}],
        [items[0], items[0]],
        [{**items[0], "extra": 1}],
    ]
    for i, bad in enumerate(bad_cases, start=5):
        with pytest.raises(devlog.DevlogError, match="interrupted_tasks"):
            devlog.write_ladder_result("mart_returns", ladder(iteration=i, interrupted_tasks=bad), tmp_path)


# ---------- 새 기록의 프로젝트 ID·메일 가림 (결정 71) ----------

LEAK_ID = "my-proj-123"
LEAK_MAIL = "ai-builder@my-proj-123.iam.gserviceaccount.com"


def test_new_jsonl_line_strings_are_scrubbed(tmp_path):
    devlog.append("rejections", rejection(
        detail=f"L3 syntax [C-01]: Not found: Table {LEAK_ID}:ai_dev.raw_x ({LEAK_MAIL})"), tmp_path)
    devlog.append("interventions", intervention(note=f"{LEAK_ID}.{prod('mart')}.t 확인, 문의 {LEAK_MAIL}"), tmp_path)
    text = "".join((tmp_path / f"{n}.jsonl").read_text(encoding="utf-8") for n in ("rejections", "interventions"))
    assert LEAK_ID not in text and "gserviceaccount" not in text
    assert "<프로젝트>:ai_dev.raw_x" in text and "<계정>" in text


def test_nested_strings_scrubbed_and_other_types_kept():
    out = devlog.scrub_strings({"a": [f"{LEAK_ID}:ai_dev.t", {"b": LEAK_MAIL}], "n": 3, "f": None, "t": True})
    assert out == {"a": ["<프로젝트>:ai_dev.t", {"b": "<계정>"}], "n": 3, "f": None, "t": True}


def test_new_ladder_result_strings_are_scrubbed(tmp_path):
    r = ladder()
    r["rungs"][2]["metrics"] = {"message": f"Not found: Table {LEAK_ID}:ai_dev.stg_returns"}
    path = devlog.write_ladder_result("mart_returns", r, tmp_path)
    text = Path(path).read_text(encoding="utf-8")
    assert LEAK_ID not in text and "<프로젝트>:ai_dev.stg_returns" in text


def test_past_lines_are_not_rewritten(tmp_path):
    old = json.dumps({"id": "R-0001", "ts": "2026-11-02T14:02:36+09:00", **rejection(
        detail=f"{LEAK_ID}:ai_dev.t")}, ensure_ascii=False) + "\n"
    (tmp_path / "rejections.jsonl").write_text(old, encoding="utf-8")
    devlog.append("rejections", rejection(task="stg_other"), tmp_path)
    lines = (tmp_path / "rejections.jsonl").read_text(encoding="utf-8").splitlines(keepends=True)
    assert lines[0] == old and len(lines) == 2
