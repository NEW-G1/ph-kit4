"""scripts/loop/run_loop.py 시험 (3-5 설계 12-1 T1~T3, T5~T7, T9~T13, T16~T18, T20의 run_loop.main() 부분, T21).

가짜 call_agent(verifier·builder)와 가짜 사다리 runner, 임시 git 저장소(origin 역할의 로컬 bare 저장소)로 돈다.
claude·bq는 부르지 않는다.
"""
import copy
import json
from datetime import date
from itertools import count

import pytest

from loop_fixture import MART, commit_all, git, make_repo, ts
from test_ladder import CHECKS, VALID, FakeBq

import agent  # noqa: E402
import common  # noqa: E402
import devlog  # noqa: E402
import l5_idem  # noqa: E402
import run_loop  # noqa: E402
import state  # noqa: E402

LOADS = ["raw_example", "stg_example", "mart_example_daily"]
MODEL = "claude-opus-5-5"


@pytest.fixture(autouse=True)
def clock(monkeypatch):
    """기록 시각이 1초씩 늘어나게 한다 (연장분·초기화 시각 비교가 같은 초에 겹치지 않게)."""
    tick = count(1)
    monkeypatch.setattr(devlog, "now_ts", lambda: ts(next(tick)))
    monkeypatch.delenv("HARNESS_ROLE", raising=False)


@pytest.fixture
def repo(tmp_path):
    root, _ = make_repo(tmp_path, checks={})
    return root


def result(text="", contract_change=False, status=True, timed_out=False, is_error=False):
    if status and not text:
        text = "작업했다.\nSTATUS: done"
    now = agent.now_ts()
    usage = [agent.ModelUsage(MODEL, 10, 20, 30, 40, 0.1)]
    return agent.AgentResult(text, contract_change, status, [] if timed_out else usage, None if timed_out else 0.1,
                             now, now, is_error or timed_out, timed_out, None if timed_out else 0)


class Agents:
    """verifier는 CHECKS를 쓴다. builder는 반복마다 actions[i](root, prompt)를 부르고 AgentResult를 돌려준다."""

    def __init__(self, builder=(), verifier=None):
        self.builder_actions, self.verifier_action = list(builder), verifier
        self.calls = []

    def __call__(self, role, prompt, *, iteration, timeout, root):
        self.calls.append({"role": role, "prompt": prompt, "iteration": iteration, "timeout": timeout})
        if role == "verifier":
            return (self.verifier_action or write_checks)(root, prompt)
        i = sum(1 for c in self.calls if c["role"] == "builder") - 1
        action = self.builder_actions[i] if i < len(self.builder_actions) else None
        return action(root, prompt) if action else result()

    def builder_calls(self):
        return [c for c in self.calls if c["role"] == "builder"]


def write_checks(root, prompt, checks=CHECKS):
    for rel, text in checks.items():
        f = root / "docs" / "requirements" / f"{MART}_checks" / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(text, encoding="utf-8")
    return result("검증 쿼리를 썼다.", status=False)


def rung(name, error_type=None, metrics=None):
    return common.rung(name, None if name == "L0" else "2026-11-03", metrics, error_type)


class Ladder:
    """반복마다 outcomes에서 하나를 꺼낸다: "pass", ("reject", task, error_type[, 실패 rung]), ("halt", reason),
    "none"(파일 없이 2). 실패 rung을 안 주면 L3 C-01 위반 1행."""

    def __init__(self, outcomes):
        self.outcomes, self.calls = list(outcomes), []

    def __call__(self, argv, timeout):
        self.calls.append({"argv": argv, "timeout": timeout})
        n = int(argv[argv.index("--iteration") + 1])
        dev = argv[argv.index("--dev-dir") + 1]
        outcome = self.outcomes.pop(0)
        if outcome == "none":
            return 2
        kind = outcome if isinstance(outcome, str) else outcome[0]
        for task in LOADS:
            entry = {"task": task, "iteration": n, "contract_version": 1, "request_kind": "new_build",
                     "modules": {"expert": {"on": [], "version": None}}, "bytes_total": 100}
            if kind == "reject" and task == outcome[1]:
                fail = outcome[3] if len(outcome) > 3 else rung("L3", outcome[2], {
                    "check": "C-01", "violations_shown": 1, "evidence": [{"example_id": 1, "n": 2}]})
                devlog.write_ladder_result(MART, {**entry, "rungs": [rung("L0"), fail], "verdict": "reject",
                                                  "halt_reason": None}, dev)
                return 1
            if kind == "halt":
                devlog.write_ladder_result(MART, {**entry, "rungs": [rung("L0")], "verdict": "halt",
                                                  "halt_reason": outcome[1],
                                                  "halt_detail": {"exception": "InfraError", "message": "bq 끊김"}},
                                           dev)
                return 2
            devlog.write_ladder_result(MART, {**entry, "rungs": [rung(n) for n in ("L0", "L1", "L2", "L3", "L4", "L5")],
                                              "verdict": "pass", "halt_reason": None}, dev)
        return 0


def run(root, *extra, agents=None, ladder=None, bq=None, environ=None):
    agents = agents if agents is not None else Agents()
    ladder = ladder if ladder is not None else Ladder(["pass"])
    bq = bq or common.Bq(runner=FakeBq(), env={"CLOUDSDK_CONFIG": "C:/cfg"})
    code = run_loop.main(["--mart", MART, "--root", str(root), *extra], agent_fn=agents, ladder_fn=ladder, bq=bq,
                         environ={} if environ is None else environ)
    return code, agents, ladder


def dev(root):
    return root / ".dev"


def lines(root, name):
    return devlog.read_lines(dev(root) / f"{name}.jsonl")


def results(root):
    return state.load_results(dev(root), MART, 1)


def progress(root):
    return (dev(root) / "progress.md").read_text(encoding="utf-8")


def no_records(root):
    return not dev(root).exists() or not any(dev(root).iterdir())


def loop_commits(root):
    return [line for line in git(root, "log", "--format=%s").splitlines() if line.startswith("loop:")]


def assert_clean(root):
    assert git(root, "status", "--porcelain", "--untracked-files=all") == ""


R = ("reject", "stg_example", "duplicate_rows")
R2 = ("reject", "mart_example_daily", "range_violation")


# ---------- T1: 시작 전 확인 ----------

def test_refuse_without_auth(repo, capsys):
    code, agents, _ = run(repo, bq=common.Bq(runner=FakeBq(), env={}))
    assert code == 2 and agents.calls == [] and no_records(repo)
    assert "CLOUDSDK_CONFIG" in capsys.readouterr().err


def test_refuse_on_main(repo, capsys):
    git(repo, "checkout", "-q", "main")
    code, agents, _ = run(repo)
    assert code == 2 and agents.calls == [] and no_records(repo)
    assert "main 브랜치" in capsys.readouterr().err


def test_refuse_detached_head(repo):
    git(repo, "checkout", "-q", "--detach")
    assert run(repo)[0] == 2 and no_records(repo)


def test_refuse_dirty_tree(repo, capsys):
    (repo / "memo.txt").write_text("x", encoding="utf-8")
    code, agents, _ = run(repo)
    assert code == 2 and agents.calls == []
    assert "깨끗하지 않다" in capsys.readouterr().err
    assert not (dev(repo) / "cost.jsonl").exists()


def test_refuse_contract_not_approved(repo, capsys):
    f = repo / "docs" / "requirements" / f"{MART}.contract.json"
    c = json.loads(f.read_text(encoding="utf-8"))
    c["requirements"][0]["text"] = "결재 뒤에 바꿈"
    f.write_text(json.dumps(c, ensure_ascii=False), encoding="utf-8")
    commit_all(repo, "contract change")
    code, agents, _ = run(repo)
    assert code == 2 and agents.calls == [] and no_records(repo)
    assert "origin/main과 다르다" in capsys.readouterr().err


def test_refuse_contract_failing_l0_before_any_agent(tmp_path, capsys):
    """결재된 contract라도 L0를 통과하지 못하면 AI를 부르기 전에 시작을 거절한다 (결정 80, 실사용자 테스트 2차 사례)."""
    contract = copy.deepcopy(VALID)
    contract["requirements"][0]["section"] = "§3"
    root, _ = make_repo(tmp_path, contract=contract, checks={})
    code, agents, ladder = run(root)
    assert code == 2 and agents.calls == [] and ladder.calls == [] and no_records(root)
    err = capsys.readouterr().err
    assert "형식 검사(L0)를 통과하지 못함" in err and "requirements[0].section" in err and "START.md" in err


def test_refuse_dirty_tree_lists_files(repo, capsys):
    (repo / "memo.txt").write_text("x", encoding="utf-8")
    assert run(repo)[0] == 2
    assert "memo.txt" in capsys.readouterr().err


def test_refuse_two_iteration0_commits(repo, capsys):
    for i in range(2):
        (repo / f"x{i}.txt").write_text(str(i), encoding="utf-8")
        commit_all(repo, f"x\n\nLoop-Iteration-0: {MART} v1")
    code, agents, _ = run(repo)
    assert code == 2 and agents.calls == [] and no_records(repo)
    assert "iteration 0 커밋이 2개" in capsys.readouterr().err


# ---------- T2·T3: iteration 0 ----------

def test_iteration0_verifier_outside_checks(repo, capsys):
    def verifier(root, prompt):
        write_checks(root, prompt)
        (root / "dags" / "sql" / "stg" / "stg_example.sql").write_text("SELECT 1\n", encoding="utf-8")
        return result(status=False)

    code, agents, ladder = run(repo, agents=Agents(verifier=verifier))
    assert code == 2 and agents.builder_calls() == [] and ladder.calls == []
    assert "멈춤 input_invalid" in progress(repo) and "dags/sql/stg/stg_example.sql" in capsys.readouterr().err
    assert not (dev(repo) / "ladder_results").exists()
    # .dev 기록만 커밋하고 verifier의 허용 밖 수정과 미완성 검증 쿼리는 되돌린다 (결정 80)
    assert loop_commits(repo) == [f"loop: {MART} v1 멈춤 기록 (iteration 0, input_invalid)"]
    assert_clean(repo)
    assert "SELECT 1" not in (repo / "dags" / "sql" / "stg" / "stg_example.sql").read_text(encoding="utf-8")
    assert not (repo / "docs" / "requirements" / f"{MART}_checks").exists()


@pytest.mark.parametrize("checks,message", [
    ({**CHECKS, "l3/C-01.sql": "-- error_type: nope\n-- task: stg_example\nSELECT 1\n"}, "error_type"),
    ({k: v for k, v in CHECKS.items() if k != "l4/I-01.sql"}, "I-01"),
])
def test_iteration0_precheck_fails(repo, checks, message):
    agents = Agents(verifier=lambda root, prompt: write_checks(root, prompt, checks))
    code, agents, ladder = run(repo, agents=agents)
    assert code == 2 and agents.builder_calls() == [] and ladder.calls == []
    assert "검증 쿼리 사전 검사" in progress(repo) and message in progress(repo)
    assert loop_commits(repo) == [f"loop: {MART} v1 멈춤 기록 (iteration 0, input_invalid)"]
    assert_clean(repo)


def test_iteration0_gen_dq_fails(repo, monkeypatch):
    monkeypatch.setattr(run_loop.gen_dq, "main", lambda argv: 2)
    code, agents, _ = run(repo)
    assert code == 2 and agents.builder_calls() == [] and "gen_dq.py" in progress(repo)


def test_iteration0_commit_paths_and_trailer(repo):
    code, agents, _ = run(repo)
    assert code == 0
    sha = state.iteration0_commits(repo, MART, 1)[0]
    files = set(git(repo, "show", "--name-only", "--format=", sha).split())
    assert files == {f"docs/requirements/{MART}_checks/{rel}" for rel in CHECKS} | {
        "dags/sql/dq/gate_raw_mart_example.sql", "dags/sql/dq/gate_stg_mart_example.sql",
        f".dev/checks_hash/{MART}-v1.json", ".dev/progress.md", ".dev/cost.jsonl",
        f".dev/agent_responses/{MART}/RUN-001-i0-verifier.md"} - {
        "dags/sql/dq/gate_raw_mart_example.sql"}  # raw 층에는 l3 검사가 없어 게이트가 그대로다
    message = git(repo, "show", "-s", "--format=%B", sha)
    assert message.rstrip().endswith(f"Loop-Iteration-0: {MART} v1")
    saved = json.loads((dev(repo) / "checks_hash" / f"{MART}-v1.json").read_text(encoding="utf-8"))
    assert f"docs/requirements/{MART}_checks/l4/C-02.sql" in saved and "dags/sql/dq/gate_stg_mart_example.sql" in saved
    assert agents.calls[0]["role"] == "verifier" and agents.calls[0]["iteration"] == 0


# ---------- T5: 사다리 종료 코드 ----------

def test_ladder_pass_commits(repo, capsys):
    code, agents, ladder = run(repo)
    assert code == 0 and len(agents.builder_calls()) == 1
    assert loop_commits(repo)[0] == f"loop: {MART} v1 통과 (iteration 1)"
    assert git(repo, "status", "--porcelain").strip() == ""
    assert f"인수인계 초안: python scripts/handover/make_facts.py --mart {MART} 실행 뒤 설명 칸(1·6·7)을 채운다" \
        in capsys.readouterr().out
    assert "| 3 | mart_example_daily (mart) | 통과 | 0 | — |" in progress(repo)


def test_ladder_reject_then_pass(repo):
    code, agents, _ = run(repo, ladder=Ladder([R, "pass"]))
    assert code == 0 and len(agents.builder_calls()) == 2
    rej = lines(repo, "rejections")
    assert len(rej) == 1 and rej[0]["task"] == "stg_example" and rej[0]["iteration"] == 1
    assert rej[0]["caught_by_rung"] == "L3" and rej[0]["contract_version"] == 1


def test_builder_editing_other_mart_sql_halts_like_outside_path(repo):
    other = repo / "dags" / "sql" / "raw" / "raw_other_mart.sql"
    other.write_text("SELECT 1\n", encoding="utf-8")
    commit_all(repo, "다른 마트 SQL")

    def edit(root, prompt):
        (root / "dags" / "sql" / "raw" / "raw_other_mart.sql").write_text("SELECT 2\n", encoding="utf-8")
        return result()
    ladder = Ladder(["pass"])
    code, _, _ = run(repo, agents=Agents(builder=[edit]), ladder=ladder)
    assert code == 2 and ladder.calls == []
    stop = json.loads(next((dev(repo) / "ladder_results" / MART).glob("*.json")).read_text(encoding="utf-8"))
    assert stop["halt_reason"] == "input_invalid" and "변경 검사 1" in stop["halt_detail"]["message"]
    assert "raw_other_mart.sql" in stop["halt_detail"]["message"]


def test_builder_editing_own_sql_and_dag_passes(repo):
    def edit(root, prompt):
        for rel in ("dags/sql/stg/stg_example.sql", "dags/harness_daily.py"):
            f = root / rel
            f.write_text(f.read_text(encoding="utf-8") + "\n# 수정\n", encoding="utf-8")
        return result()
    code, _, ladder = run(repo, agents=Agents(builder=[edit]))
    assert code == 0 and len(ladder.calls) == 1


def test_repeat_rejection_makes_rule_candidate(repo):
    f = repo / "docs" / "ai" / "rule_candidate_exclusions.md"
    f.parent.mkdir(parents=True)
    f.write_text("| 반려 id | 이유 | 근거 |\n|---|---|---|\n", encoding="utf-8")
    commit_all(repo, "제외 목록")
    code, _, _ = run(repo, ladder=Ladder([R, R, "pass"]))
    assert code == 0
    text = (repo / ".dev" / "rule_candidates.md").read_text(encoding="utf-8")
    assert "## RC-001" in text and "R-0001, R-0002" in text and "- 상태: 결재 대기" in text


def test_rule_candidate_failure_does_not_change_verdict(repo, monkeypatch, capsys):
    def boom(*a):
        raise RuntimeError("boom")
    monkeypatch.setattr(run_loop.rule_candidates, "update", boom)
    code, agents, _ = run(repo, ladder=Ladder([R, "pass"]))
    assert code == 0 and len(agents.builder_calls()) == 2 and len(lines(repo, "rejections")) == 1
    assert "규칙 후보 갱신 실패" in capsys.readouterr().err


def test_ladder_halt_is_not_rejection(repo, capsys):
    code, agents, _ = run(repo, ladder=Ladder([R, ("halt", "infra_error")]))
    assert code == 2 and len(lines(repo, "rejections")) == 1
    c = state.counts(state.iterations(results(repo)), [], MART, 1)
    assert c.judged == 1
    assert "사다리 멈춤 infra_error" in progress(repo)
    assert loop_commits(repo) == [f"loop: {MART} v1 멈춤 기록 (iteration 2, 사다리 infra_error)",
                                  f"loop: {MART} v1 iteration 0 (검증 쿼리·게이트)"]
    assert_clean(repo)


def test_ladder_exit2_without_file_stops(repo):
    code, _, _ = run(repo, ladder=Ladder(["none"]))
    assert code == 2
    stop = [r for r in results(repo) if r["verdict"] == "halt"][0]
    assert stop["halt_reason"] == "infra_error" and stop["halt_detail"]["exception"] == "LoopStop"


# ---------- T6·T7: 상한·연속 ----------

def test_five_judged_then_max_iterations(repo):
    code, agents, ladder = run(repo, ladder=Ladder([R, R2, R, R2, R]))
    assert code == 2 and len(agents.builder_calls()) == 5 and len(ladder.calls) == 5
    stop = [r for r in results(repo) if r["iteration"] == 6]
    assert len(stop) == 1 and stop[0]["halt_reason"] == "max_iterations"


def test_halt_iteration_not_in_five(repo):
    code, *_ = run(repo, ladder=Ladder([R, R2, ("halt", "infra_error")]))
    assert code == 2
    assert_clean(repo)  # 멈추면 루프가 정리한다(결정 80). 사람 커밋 없이 같은 명령으로 다시 시작
    code, agents, _ = run(repo, ladder=Ladder([R, R2, R, "pass"]))
    assert code == 2 and len(agents.builder_calls()) == 3  # 판정 2 + 3 = 5에서 멈춤
    assert results(repo)[-1]["halt_reason"] == "max_iterations"


def test_same_pair_three_times(repo):
    code, agents, _ = run(repo, ladder=Ladder([R, R, R]))
    assert code == 2 and len(agents.builder_calls()) == 3
    stop = results(repo)[-1]
    assert (stop["iteration"], stop["halt_reason"], stop["task"]) == (4, "same_type_3x", "stg_example")


def test_same_error_type_on_other_task_keeps_going(repo):
    other = ("reject", "raw_example", "duplicate_rows")
    code, agents, _ = run(repo, ladder=Ladder([other, R, R, "pass"]))
    assert code == 0 and len(agents.builder_calls()) == 4


# ---------- T9: STATUS ----------

def test_contract_change_halts_before_ladder(repo):
    agents = Agents(builder=[lambda root, p: result("contract를 바꿔야 한다.\nSTATUS: contract_change",
                                                    contract_change=True)])
    code, agents, ladder = run(repo, agents=agents)
    assert code == 2 and ladder.calls == []
    stop = results(repo)[-1]
    assert stop["halt_reason"] == "contract_change" and stop["task"] == "raw_example"


def test_no_status_line_is_recorded_not_rejected(repo):
    agents = Agents(builder=[lambda root, p: result("고쳤다.", status=False)])
    code, agents, ladder = run(repo, agents=agents)
    assert code == 0 and len(ladder.calls) == 1
    assert "신호 없음" in progress(repo) and lines(repo, "rejections") == []


# ---------- 반려 기록 detail: L5 idempotency_break (결정 49) ----------

def l5_break(first, second):
    """실제 l5_idem.run이 남기는 반려 rung과 같은 모양 (metrics 구성은 l5_idem.break_message를 그대로 쓴다)."""
    return rung("L5", "idempotency_break", {"first": first, "second": second,
                                            "message": l5_idem.break_message(first, second),
                                            "evidence": [{"run": 1, **first}, {"run": 2, **second}]})


@pytest.mark.parametrize("first, second, expected", [
    ({"row_count": "1234", "checksum": "-7001"}, {"row_count": "1234", "checksum": "8812"},
     "L5 idempotency_break: 같은 ds로 2번 실행한 결과가 다름 (행 수 1,234 → 1,234, 체크섬 다름)"),
    ({"row_count": "1234", "checksum": "-7001"}, {"row_count": "2468", "checksum": "8812"},
     "L5 idempotency_break: 같은 ds로 2번 실행한 결과가 다름 (행 수 1,234 → 2,468, 체크섬 다름)"),
])
def test_l5_break_detail_names_rows_and_checksum_state(repo, first, second, expected):
    reject = ("reject", "stg_example", "idempotency_break", l5_break(first, second))
    code, agents, _ = run(repo, ladder=Ladder([reject, "pass"]))
    assert code == 0
    rej = lines(repo, "rejections")
    assert len(rej) == 1 and rej[0]["caught_by_rung"] == "L5" and rej[0]["error_type"] == "idempotency_break"
    assert rej[0]["detail"] == expected and "?" not in rej[0]["detail"]
    assert "-7001" not in rej[0]["detail"] and "8812" not in rej[0]["detail"]  # 체크섬 값은 쓰지 않는다
    assert rej[0]["evidence"] is None  # 첫 반려 (결정 49)
    prompts = [c["prompt"] for c in agents.builder_calls()]
    assert "직전 반려 R-0001: task stg_example, 단계 L5, 유형 idempotency_break(semantic), 검사 —, "         f"메시지 {expected}" in prompts[1]


# ---------- T10: 같은 쌍 2번째 ----------

def test_second_same_pair_gets_evidence_and_three_lines(repo):
    code, agents, _ = run(repo, ladder=Ladder([R, R, "pass"]))
    assert code == 0
    rej = lines(repo, "rejections")
    assert rej[0]["evidence"] is None and rej[1]["evidence"] == [{"example_id": 1, "n": 2}]
    prompts = [c["prompt"] for c in agents.builder_calls()]
    assert "직전 반려" not in prompts[0]
    assert "직전 반려 R-0001: task stg_example, 단계 L3, 유형 duplicate_rows(semantic), 검사 C-01" in prompts[1]
    assert "3줄" not in prompts[1]
    assert '### R-0002 원인' in prompts[2] and '{"example_id": 1, "n": 2}' in prompts[2]
    assert "3줄 없음 (R-0002" in progress(repo)


def test_three_lines_written_not_flagged(repo):
    def builder(root, prompt):
        f = root / ".dev" / "progress.md"
        f.write_text(f.read_text(encoding="utf-8") + "\n### R-0002 원인\n왜\n무엇\n어떻게\n", encoding="utf-8")
        return result()

    code, *_ = run(repo, agents=Agents(builder=[None, None, builder]), ladder=Ladder([R, R, "pass"]))
    assert code == 0 and "3줄 없음" not in progress(repo)


def test_loop_leaves_other_marts_section_alone(repo):
    head = "# 진행 기록\n\n## 요구서 — mart_daily_sales\ndocs/requirements/mart_daily_sales.md\n\n"
    other = ("## 작업 목록 — mart_daily_sales\n\n마트 실행 반복 2/5, 연속 없음 0/3\n\n"
             "| 1 | raw_orders (raw) | 통과 | 1 | R-0001 (L3 syntax) |\n\n")
    f = dev(repo) / "progress.md"
    f.parent.mkdir(exist_ok=True)
    f.write_text(head + other + "## 직전 반복 인계\n- 마트 1 인계\n", encoding="utf-8", newline="\n")
    git(repo, "add", "-f", ".dev/progress.md")
    git(repo, "commit", "-m", "마트 1 기록")
    code, *_ = run(repo, ladder=Ladder([R, "pass"]))
    text = progress(repo)
    mine = f"## 요구서 — {MART}\ndocs/requirements/{MART}.md\n\n## 작업 목록 — {MART}\n\n마트 실행 반복 2/5"
    assert code == 0 and text.startswith(head + other + mine)
    assert f"## 직전 반복 인계\n- 마트 1 인계\n- [루프 {MART}] " in text and "- [루프] " not in text


# ---------- T11: cost ----------

def test_cost_line_per_call(repo):
    run(repo, ladder=Ladder([R, "pass"]))
    cost = lines(repo, "cost")
    assert [(c["role"], c["iteration"]) for c in cost] == [("verifier", 0), ("builder", 1), ("builder", 2)]
    assert {c["run_id"] for c in cost} == {"RUN-001"}
    assert all(c["model"] == MODEL and c["input_tokens"] == 10 and c["total_cost_usd"] == 0.1 for c in cost)
    assert cost[0]["bq_bytes_processed"] == 0
    assert cost[1]["bq_bytes_processed"] == 200  # 반려 반복: raw pass 100 + stg reject 100
    assert cost[2]["bq_bytes_processed"] == 300


def test_cost_bytes_include_interrupted_tasks(repo):
    """사다리가 층 단위로 돌아 일부 단계만 마친 task는 파일 없이 실패 파일의 interrupted_tasks에 바이트를 남긴다."""
    def ladder(argv, timeout):
        n = int(argv[argv.index("--iteration") + 1])
        d = argv[argv.index("--dev-dir") + 1]
        entry = {"iteration": n, "contract_version": 1, "request_kind": "new_build",
                 "modules": {"expert": {"on": [], "version": None}}}
        if n == 1:
            fail = rung("L1", "syntax", {"message": "Syntax error"})
            devlog.write_ladder_result(MART, {**entry, "task": "stg_example", "bytes_total": 30,
                                              "rungs": [rung("L0"), fail], "verdict": "reject", "halt_reason": None,
                                              "interrupted_tasks": [{"task": "raw_example",
                                                                     "passed_rungs": ["L0", "L1", "L2", "L3"],
                                                                     "bytes": 70}]}, d)
            return 1
        for task in LOADS:
            devlog.write_ladder_result(MART, {**entry, "task": task, "bytes_total": 100, "verdict": "pass",
                                              "rungs": [rung(x) for x in ("L0", "L1", "L2", "L3", "L4", "L5")],
                                              "halt_reason": None}, d)
        return 0

    code, *_ = run(repo, ladder=ladder)
    assert code == 0
    assert [c["bq_bytes_processed"] for c in lines(repo, "cost")] == [0, 100, 300]  # 30 + 70, 100 × 3


def test_agent_responses_saved_and_committed(repo):
    """호출마다 응답 파일 1개, 내용 = 응답 텍스트, 변경 검사에 걸리지 않음, 루프 커밋에 들어감 (11/2 보완)."""
    first = "1차 응답\r\n두 줄째\nSTATUS: done"
    second = "2차 응답\nSTATUS: done"
    texts = iter([first, second])
    agents = Agents(builder=[lambda root, p: result(next(texts))] * 2)
    code, _, ladder = run(repo, agents=agents, ladder=Ladder([R, "pass"]))
    assert code == 0 and len(ladder.calls) == 2  # 1·2회 모두 변경 검사를 지나 사다리까지 감
    folder = dev(repo) / "agent_responses" / MART
    assert sorted(f.name for f in folder.iterdir()) == ["RUN-001-i0-verifier.md", "RUN-001-i1-builder.md",
                                                        "RUN-001-i2-builder.md"]
    assert (folder / "RUN-001-i0-verifier.md").read_bytes().decode("utf-8") == "검증 쿼리를 썼다."
    assert (folder / "RUN-001-i1-builder.md").read_bytes().decode("utf-8") == first
    assert (folder / "RUN-001-i2-builder.md").read_bytes().decode("utf-8") == second
    assert git(repo, "status", "--porcelain", "--untracked-files=all").strip() == ""
    passed = git(repo, "log", "-1", "--name-only", "--format=").split()
    assert f".dev/agent_responses/{MART}/RUN-001-i2-builder.md" in passed


def test_agent_response_written_on_halt_and_committed(repo):
    agents = Agents(builder=[lambda root, p: result("끝나지 않음", is_error=True)])
    code, _, ladder = run(repo, agents=agents)
    assert code == 2 and ladder.calls == []
    f = dev(repo) / "agent_responses" / MART / "RUN-001-i1-builder.md"
    assert f.read_text(encoding="utf-8") == "끝나지 않음"
    assert git(repo, "ls-files", f".dev/agent_responses/{MART}/RUN-001-i1-builder.md").strip()
    assert_clean(repo)


def test_halt_commits_builder_work_and_reverts_outside(repo, capsys):
    """멈추면 builder 허용 경로의 작업은 커밋해 다음 실행이 이어 받고, 허용 밖 변경은 되돌린다 (결정 80)."""
    def builder(root, prompt):
        (root / "dags" / "sql" / "stg" / "stg_example.sql").write_text("SELECT kept\n", encoding="utf-8")
        (root / "memo.txt").write_text("x", encoding="utf-8")
        return result()

    code, _, _ = run(repo, agents=Agents(builder=[builder]))
    assert code == 2 and "memo.txt" in capsys.readouterr().err
    assert_clean(repo) and not (repo / "memo.txt").exists()
    assert (repo / "dags" / "sql" / "stg" / "stg_example.sql").read_text(encoding="utf-8") == "SELECT kept\n"
    assert loop_commits(repo)[0] == f"loop: {MART} v1 멈춤 기록 (iteration 1, input_invalid)"


def test_next_run_id(repo):
    run(repo, ladder=Ladder([("halt", "infra_error")]))
    assert_clean(repo)  # 멈추면 루프가 정리한다(결정 80). 사람 커밋 없이 같은 명령으로 다시 시작
    run(repo, ladder=Ladder(["pass"]))
    assert [c["run_id"] for c in lines(repo, "cost")] == ["RUN-001", "RUN-001", "RUN-002"]


def test_timeout_records_cost_and_halts(repo):
    agents = Agents(builder=[lambda root, p: result(timed_out=True)])
    code, agents, ladder = run(repo, agents=agents)
    assert code == 2 and ladder.calls == []
    builder_cost = lines(repo, "cost")[-1]
    assert builder_cost["model"] == "unknown" and builder_cost["bq_bytes_processed"] == 0
    assert results(repo)[-1]["halt_reason"] == "timeout"
    assert state.counts(state.iterations(results(repo)), [], MART, 1).judged == 0


def test_ladder_timeout_halts(repo):
    code, *_ = run(repo, ladder=lambda argv, timeout: None)
    assert code == 2 and results(repo)[-1]["halt_reason"] == "timeout"


# ---------- T12: 멈춤 파일 ----------

def test_loop_stop_file_format(repo):
    run(repo, ladder=Ladder([R, R2, R, R2, R]))
    stop = results(repo)[-1]
    assert stop["verdict"] == "halt" and stop["rungs"] == [] and stop["halt_detail"]["exception"] == "LoopStop"
    assert stop["task"] == "stg_example"  # 직전 반려의 task
    assert stop["bytes_total"] is None and stop["request_kind"] == "new_build"
    devlog.validate_ladder({k: v for k, v in stop.items() if k not in ("ts", "_path")})


def test_loop_stop_takes_free_task_when_ladder_left_files(repo):
    def ladder(argv, timeout):
        n = int(argv[argv.index("--iteration") + 1])
        devlog.write_ladder_result(MART, {"task": "raw_example", "iteration": n, "contract_version": 1,
                                          "request_kind": "new_build", "modules": {"expert": {"on": [], "version": None}},
                                          "bytes_total": 1, "rungs": [rung("L0")], "verdict": "pass",
                                          "halt_reason": None}, argv[argv.index("--dev-dir") + 1])
        return None  # 시간 초과

    code, *_ = run(repo, ladder=ladder)
    assert code == 2
    stop = [r for r in results(repo) if r["verdict"] == "halt"][0]
    assert stop["task"] == "stg_example" and stop["halt_reason"] == "timeout"


# ---------- T13: 재시작 ----------

def test_restart_a_continues_numbering_and_warns(repo, capsys):
    run(repo, ladder=Ladder([R, ("halt", "infra_error")]))
    assert_clean(repo)  # 멈추면 루프가 정리한다(결정 80). 사람 커밋 없이 같은 명령으로 다시 시작
    capsys.readouterr()
    code, agents, _ = run(repo, ladder=Ladder([R, R]))
    assert code == 2
    assert [c["iteration"] for c in agents.builder_calls()] == [3, 4]
    assert results(repo)[-1]["halt_reason"] == "same_type_3x"  # 1·3·4가 이어져 3회
    assert "뒤 다시 시작한다" in capsys.readouterr().err


def test_restart_with_manual_check_no_warning(repo, capsys):
    run(repo, ladder=Ladder([("halt", "infra_error")]))
    devlog.append("interventions", {"mart": MART, "kind": "manual_check", "target": "loop halt 재시작 (a) infra_error",
                                    "minutes_spent": 3, "note": ""}, dev(repo))
    commit_all(repo, "재시작 기록")
    capsys.readouterr()
    assert run(repo)[0] == 0
    assert "뒤 다시 시작한다" not in capsys.readouterr().err


def test_restart_b_restores_builder_paths(repo):
    def builder(root, prompt):
        (root / "dags" / "sql" / "stg" / "stg_example.sql").write_text("SELECT broken\n", encoding="utf-8")
        return result()

    run(repo, agents=Agents(builder=[builder]), ladder=Ladder([("halt", "infra_error")]))
    sha = state.iteration0_commits(repo, MART, 1)[0]
    git(repo, "restore", "--source", sha, "--staged", "--worktree", "--", *state.builder_paths())
    git(repo, "add", ".dev/")
    git(repo, "commit", "-q", "-m", "restart (b)")
    assert git(repo, "status", "--porcelain").strip() == ""
    code, agents, _ = run(repo)
    assert code == 0 and agents.builder_calls()[0]["iteration"] == 2
    assert "broken" not in (repo / "dags" / "sql" / "stg" / "stg_example.sql").read_text(encoding="utf-8")


def test_refuse_restart_after_contract_reapproved(repo, capsys):
    """iteration 0 뒤 contract를 다시 결재받아 main에서 합쳐 오면 시작 때 새 브랜치를 안내한다 (변경 검사 2로 멈추기 전에)."""
    run(repo, ladder=Ladder([("halt", "infra_error")]))
    assert_clean(repo)  # 멈추면 루프가 정리한다(결정 80). 사람 커밋 없이 같은 명령으로 다시 시작
    branch = git(repo, "symbolic-ref", "--short", "HEAD").strip()
    git(repo, "checkout", "-q", "main")
    f = repo / "docs" / "requirements" / f"{MART}.contract.json"
    c = json.loads(f.read_text(encoding="utf-8"))
    c["requirements"][0]["text"] = "다시 결재받음"
    f.write_text(json.dumps(c, ensure_ascii=False), encoding="utf-8")
    commit_all(repo, "contract fix")
    git(repo, "push", "-q", "origin", "main")
    git(repo, "checkout", "-q", branch)
    git(repo, "merge", "-q", "--no-edit", "main")
    code, agents, _ = run(repo)
    assert code == 2 and agents.calls == []
    assert "새 작업 브랜치" in capsys.readouterr().err


def test_restart_does_not_redo_iteration0(repo):
    run(repo, ladder=Ladder([("halt", "infra_error")]))
    assert_clean(repo)  # 멈추면 루프가 정리한다(결정 80). 사람 커밋 없이 같은 명령으로 다시 시작
    _, agents, _ = run(repo)
    assert [c["role"] for c in agents.calls] == ["builder"]


# ---------- 변경 검사 (run_loop 통합) ----------

def test_builder_editing_checks_halts_before_ladder(repo):
    def builder(root, prompt):
        f = root / "docs" / "requirements" / f"{MART}_checks" / "l4" / "C-02.sql"
        f.write_text(f.read_text(encoding="utf-8") + "-- 고침\n", encoding="utf-8")
        return result()

    code, _, ladder = run(repo, agents=Agents(builder=[builder]))
    assert code == 2 and ladder.calls == []
    stop = results(repo)[-1]
    assert stop["halt_reason"] == "input_invalid" and "변경 검사 1" in stop["halt_detail"]["message"]


def blocked_by_hook(root, prompt):
    """builder 세션 안에서 Hook이 차단 1줄을 남긴 경우."""
    with (root / ".dev" / "hook_blocks.jsonl").open("a", encoding="utf-8", newline="\n") as f:
        f.write('{"id": "B-0001", "hook": "check_write", "reason": "builder_write_checks"}\n')
    return result()


def test_hook_block_line_during_builder_does_not_halt(repo):
    code, _, ladder = run(repo, agents=Agents(builder=[blocked_by_hook]))
    assert code == 0 and len(ladder.calls) == 1


def test_hook_block_line_during_verifier_does_not_halt(repo):
    def verifier(root, prompt):
        blocked_by_hook(root, prompt)
        return write_checks(root, prompt)

    assert run(repo, agents=Agents(verifier=verifier))[0] == 0


def test_hook_blocks_rewritten_by_builder_halts(repo):
    def builder(root, prompt):
        (root / ".dev" / "hook_blocks.jsonl").write_text('{"id": "B-0001"}\n', encoding="utf-8")
        return result()

    run(repo, agents=Agents(builder=[blocked_by_hook]), ladder=Ladder([("halt", "infra_error")]))
    assert_clean(repo)  # 멈추면 루프가 정리한다(결정 80). 사람 커밋 없이 같은 명령으로 다시 시작
    code, _, ladder = run(repo, agents=Agents(builder=[builder]))
    assert code == 2 and ladder.calls == []
    stop = results(repo)[-1]
    assert stop["halt_reason"] == "input_invalid" and "hook_blocks.jsonl" in stop["halt_detail"]["message"]


def test_agent_error_halts_infra(repo):
    code, _, ladder = run(repo, agents=Agents(builder=[lambda root, p: result(is_error=True)]))
    assert code == 2 and ladder.calls == [] and results(repo)[-1]["halt_reason"] == "infra_error"


# ---------- T16: 프롬프트 ----------

def test_prompts():
    builder = (run_loop.PROMPTS / "builder.md").read_text(encoding="utf-8")
    verifier = (run_loop.PROMPTS / "verifier.md").read_text(encoding="utf-8")
    assert "새 SQL·DAG 파일을 Write하기 전에 같은 폴더의 기존 파일 1개(없으면 .gitkeep)를 Read한다 (결정 62)" in builder
    assert "dags/sql/raw·stg·mart/, dags/harness_daily.py, .dev/progress.md 뿐이다" in builder
    assert "STATUS: contract_change" in builder and "{직전 반려 블록}" in builder
    assert "STATUS" not in verifier and "_checks/<l3|l4|l5>/" in verifier


def test_builder_prompt_filled(repo):
    _, agents, _ = run(repo)
    p = agents.builder_calls()[0]["prompt"]
    assert f"마트 {MART}의" in p and "iteration 1" in p and "{" not in p
    assert "{mart}" not in agents.calls[0]["prompt"] and MART in agents.calls[0]["prompt"]


def test_loop_settings_denies_plan():
    data = json.loads((run_loop.PROJECT / ".claude" / "loop.settings.json").read_text(encoding="utf-8"))
    assert data == {"permissions": {"deny": ["Read(./docs/plan/**)"]}}


# ---------- T17: 연장 ----------

APPROVAL = ["--approver", "approver1", "--reason", "L4 원천 비교가 반품일 기준으로 다시 실패", "--minutes", "5"]


def max_stopped(repo):
    run(repo, ladder=Ladder([R, R2, R, R2, R]))
    assert_clean(repo)  # 멈추면 루프가 정리한다(결정 80). 사람 커밋 없이 같은 명령으로 다시 시작


def test_restart_after_max_without_extension_stops_again(repo):
    max_stopped(repo)
    code, agents, ladder = run(repo)
    assert code == 2 and agents.calls == [] and ladder.calls == []
    assert [r["halt_reason"] for r in results(repo) if r["verdict"] == "halt"] == ["max_iterations"] * 2


def test_extension_recorded_before_builder_and_runs_more(repo, capsys):
    max_stopped(repo)
    seen = []

    def builder(root, prompt):
        seen.append([r["stage"] for r in lines(root, "interventions")])
        return result()

    capsys.readouterr()
    code, agents, _ = run(repo, "--extend", "2", *APPROVAL, agents=Agents(builder=[builder, builder]),
                          ladder=Ladder([R2, R]))
    assert code == 2 and len(agents.builder_calls()) == 2
    assert seen[0] == ["loop_extension"]
    a = lines(repo, "interventions")[0]
    assert (a["kind"], a["stage"], a["minutes_spent"], a["extra_iterations"], a["approver"]) == \
        ("approval", "loop_extension", 5, 2, "approver1")
    assert a["contract_version"] == 1 and a["target"] == f"{MART} 반복 연장 +2" and a["note"] == ""
    assert results(repo)[-1]["halt_reason"] == "max_iterations"
    assert "연장분" in progress(repo) and "(연장분)" in capsys.readouterr().out


def test_extension_refused_when_last_is_not_max(repo, capsys):
    run(repo, ladder=Ladder([R, ("halt", "infra_error")]))
    assert_clean(repo)  # 멈추면 루프가 정리한다(결정 80). 사람 커밋 없이 같은 명령으로 다시 시작
    code, agents, _ = run(repo, "--extend", "2", *APPROVAL)
    assert code == 2 and agents.calls == [] and lines(repo, "interventions") == []
    assert "결재할 멈춤이 없음" in capsys.readouterr().err


def without(option):
    i = APPROVAL.index(option)
    return APPROVAL[:i] + APPROVAL[i + 2:]


def assert_refused(repo, *argv):
    """거절은 상태를 바꾸지 않으므로 멈춘 저장소 하나로 여러 옵션을 차례로 본다."""
    code, agents, ladder = run(repo, *argv)
    assert (code, agents.calls, ladder.calls) == (2, [], []), argv
    assert lines(repo, "interventions") == [], argv


def test_extension_options_refused(repo):
    max_stopped(repo)
    for drop in ("--approver", "--reason", "--minutes"):  # 셋 중 하나라도 없으면 기록 없이 종료 코드 2
        assert_refused(repo, "--extend", "2", *without(drop))
    for bad in (["--extend", "0", *APPROVAL],
                ["--extend", "2", "--approver", "kim", *APPROVAL[2:]],
                ["--extend", "2", *APPROVAL[:4], "--minutes", "-1"],
                ["--extend", "2", "--reset-streak", "stg_example:duplicate_rows", *APPROVAL],
                ["--approver", "approver1"]):
        assert_refused(repo, *bad)


# ---------- T18: 연속 초기화 ----------

def streak_stopped(repo, extra=()):
    run(repo, ladder=Ladder([*extra, R, R, R]))
    assert_clean(repo)  # 멈추면 루프가 정리한다(결정 80). 사람 커밋 없이 같은 명령으로 다시 시작


def test_restart_after_streak_without_reset_stops_on_next_same(repo):
    streak_stopped(repo)
    code, agents, _ = run(repo, ladder=Ladder([R]))
    assert code == 2 and len(agents.builder_calls()) == 1
    assert results(repo)[-1]["halt_reason"] == "same_type_3x"
    c = state.counts(state.iterations(results(repo)), [], MART, 1)
    assert c.streak == 4


def test_reset_streak_recorded_first_and_only_that_pair(repo):
    streak_stopped(repo)
    seen = []

    def builder(root, prompt):
        seen.append(len(lines(root, "interventions")))
        return result()

    code, agents, _ = run(repo, "--reset-streak", "stg_example:duplicate_rows", *APPROVAL,
                          agents=Agents(builder=[builder, builder]), ladder=Ladder([R, "pass"]))
    assert code == 0 and seen[0] == 1
    a = lines(repo, "interventions")[0]
    assert (a["stage"], a["streak_key"], a["minutes_spent"]) == ("loop_streak_reset", "stg_example:duplicate_rows", 5)
    assert a["target"] == f"{MART} 연속 초기화 stg_example:duplicate_rows"
    c = state.counts(state.iterations(results(repo)), lines(repo, "interventions"), MART, 1)
    assert c.judged == 5 and c.limit == 5  # 초기화는 상한을 늘리지 않는다


def test_reset_streak_does_not_raise_limit(repo):
    streak_stopped(repo, extra=[R2])
    code, agents, _ = run(repo, "--reset-streak", "stg_example:duplicate_rows", *APPROVAL, ladder=Ladder([R2]))
    assert code == 2 and len(agents.builder_calls()) == 1
    assert results(repo)[-1]["halt_reason"] == "max_iterations"


def test_reset_streak_options_refused(repo, capsys):
    streak_stopped(repo)
    capsys.readouterr()
    assert_refused(repo, "--reset-streak", "raw_example:duplicate_rows", *APPROVAL)  # 멈춘 쌍과 다른 키
    assert "결재할 멈춤이 없음" in capsys.readouterr().err
    assert_refused(repo, "--reset-streak", "stg_example:whatever", *APPROVAL)  # ERROR_TYPES 밖
    for drop in ("--approver", "--reason", "--minutes"):
        assert_refused(repo, "--reset-streak", "stg_example:duplicate_rows", *without(drop))


# ---------- 판정 날짜 --ds (결정 79 범위) ----------

TODAY = date(2026, 11, 9)


@pytest.fixture
def fixed_today(monkeypatch):
    monkeypatch.setattr(common, "utc_today", lambda: TODAY)


def incremental_repo(tmp_path):
    contract = copy.deepcopy(VALID)
    contract["load"] = {"mode": "incremental", "date_column": "created_at", "partition_column": "order_date"}
    for t in contract["tables"]:  # 시작 때 L0를 통과하는 증분 contract (모든 테이블에 DATE 파티션 컬럼)
        if all(col["name"] != "order_date" for col in t["columns"]):
            t["columns"].append({**t["columns"][0], "name": "order_date", "type": "DATE"})
    root, _ = make_repo(tmp_path, contract=contract, checks={})
    return root


def test_ds_passed_to_ladder_and_recorded(repo, fixed_today):
    code, _, ladder = run(repo, "--ds", "2026-11-08", ladder=Ladder([R, "pass"]))
    assert code == 0 and len(ladder.calls) == 2
    for call in ladder.calls:
        argv = call["argv"]
        assert argv.count("--ds") == 1 and argv[argv.index("--ds") + 1] == "2026-11-08"
    assert loop_commits(repo)[0] == f"loop: {MART} v1 통과 (iteration 2, ds 2026-11-08)"
    assert "iteration 2: 사다리 통과 (ds 2026-11-08)" in progress(repo)


def test_no_ds_not_passed_to_ladder(repo):
    code, _, ladder = run(repo)
    assert code == 0 and "--ds" not in ladder.calls[0]["argv"]
    assert "ds " not in loop_commits(repo)[0] and "사다리 통과 (ds" not in progress(repo)


@pytest.mark.parametrize("bad", ["2026/11/08", "20261108", "2026-11-8", "2026-13-01", "어제"])
def test_bad_ds_format_refused_before_agents(repo, bad, capsys, fixed_today):
    code, agents, ladder = run(repo, "--ds", bad)
    assert (code, agents.calls, ladder.calls) == (2, [], []) and no_records(repo)
    assert "루프를 시작하지 않음" in capsys.readouterr().err


@pytest.mark.parametrize("ds", ["2026-11-01", "2026-11-10"])  # 8일 전(7일 창 밖), 미래
def test_snapshot_ds_ladder_would_refuse_refused_before_agents(repo, ds, capsys, fixed_today):
    code, agents, ladder = run(repo, "--ds", ds)
    assert (code, agents.calls, ladder.calls) == (2, [], []) and no_records(repo)
    assert "사다리가 거절할 날짜" in capsys.readouterr().err


def test_snapshot_ds_window_edge_runs(repo, fixed_today):
    code, agents, ladder = run(repo, "--ds", "2026-11-03")  # 7일 창의 첫날
    assert code == 0 and len(agents.builder_calls()) == 1
    assert ladder.calls[0]["argv"][-2:] == ["--ds", "2026-11-03"]


def test_incremental_past_ds_runs_future_refused(tmp_path, capsys, fixed_today):
    root = incremental_repo(tmp_path)
    code, agents, _ = run(root, "--ds", "2026-11-10")
    assert (code, agents.calls) == (2, []) and "사다리가 거절할 날짜" in capsys.readouterr().err
    code, agents, ladder = run(root, "--ds", "2026-10-01")
    assert code == 0 and len(agents.builder_calls()) == 1
    assert ladder.calls[0]["argv"][-2:] == ["--ds", "2026-10-01"]


def test_bad_ds_refused_before_approval_recorded(repo, fixed_today):
    max_stopped(repo)
    assert_refused(repo, "--extend", "2", *APPROVAL, "--ds", "2026-11-01")


# ---------- T20: run_loop 자체 차단 ----------

@pytest.mark.parametrize("role", ["builder", "verifier", "anything"])
def test_harness_role_refused_before_auth_and_git(repo, role, capsys):
    fake = FakeBq()
    bq = common.Bq(runner=fake, env={"CLOUDSDK_CONFIG": "C:/cfg"})
    code, agents, ladder = run(repo, "--extend", "2", *APPROVAL, bq=bq, environ={"HARNESS_ROLE": role})
    assert code == 2 and fake.calls == [] and agents.calls == [] and ladder.calls == []
    assert no_records(repo)
    assert "Remove-Item Env:HARNESS_ROLE" in capsys.readouterr().err


def test_harness_role_checked_before_argument_errors(repo, capsys):
    code = run_loop.main(["--extend", "x"], agent_fn=None, ladder_fn=None, bq=None, environ={"HARNESS_ROLE": "builder"})
    assert code == 2 and "HARNESS_ROLE" in capsys.readouterr().err


def test_empty_harness_role_goes_to_next_check(repo, capsys):
    code, *_ = run(repo, bq=common.Bq(runner=FakeBq(), env={}), environ={"HARNESS_ROLE": ""})
    assert code == 2
    err = capsys.readouterr().err
    assert "HARNESS_ROLE" not in err and "CLOUDSDK_CONFIG" in err
