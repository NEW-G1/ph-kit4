"""scripts/handover/make_facts.py 시험 (03 §6.7 사실 부분). 임시 git 저장소와 가짜 .dev 폴더로 돈다. bq는 부르지 않는다."""
import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "handover"))
sys.path.insert(0, str(ROOT / "scripts" / "log"))
import devlog  # noqa: E402
import make_facts  # noqa: E402
from config_fixture import prod, src  # noqa: E402
from test_l0_contract import VALID  # noqa: E402

MART = "mart_example"
BRANCH = "week9/mart-example"
PROJECT_ID = "my-proj-123"
SECRET_VALUES = ("987654321", "SECRETVALUE", "Seoul-Gangnam")
LOADS = ["raw_example", "stg_example", "mart_example_daily"]


def git(root, *args):
    p = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, encoding="utf-8")
    assert p.returncode == 0, p.stderr
    return p.stdout


def write(root, rel, text):
    f = Path(root) / rel
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(text, encoding="utf-8", newline="\n")


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q", "--template=", "-b", "main")
    git(root, "config", "user.email", "t@example.com")
    git(root, "config", "user.name", "t")
    write(root, "README.md", "base\n")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "base")
    git(root, "checkout", "-q", "-b", BRANCH)
    write(root, f"docs/requirements/{MART}.contract.json", json.dumps(VALID, ensure_ascii=False))
    write(root, f"docs/requirements/{MART}.md", "# 요구서\n")
    for t in VALID["tables"]:
        write(root, f"dags/sql/{t['layer']}/{t['task']}.sql", "SELECT 1\n")
    write(root, "dags/harness_daily.py", "UPSTREAM = {}\n")
    write(root, ".dev/progress.md", "# 진행\n")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "build")
    return root


def rung(name, metrics=None, error_type=None):
    return {"rung": name, "ds": None if name == "L0" else "2026-11-02", "status": "fail" if error_type else "pass",
            "metrics": metrics or {}, "error_type": error_type,
            "error_class": ("semantic" if error_type else None)}


PASS_METRICS = {
    "L0": {"load_tasks": 3, "gate_tasks": 3, "tables": 3, "checks": 3, "traces": 3},
    "L1": {"bytes_processed": 1000, "bytes_accuracy": "LOWER_BOUND"},
    "L2": {"dataset": "ai_dev"},
    "L3": {"checks": []},
    "L4": {"checks": []},
    "L5": {"row_count": "7", "checks": []},
}


def pass_rungs(task):
    rungs = [rung(n, copy.deepcopy(PASS_METRICS[n])) for n in ("L0", "L1", "L2", "L3", "L4", "L5")]
    rungs[2]["metrics"]["table"] = task
    if task == "stg_example":
        rungs[3]["metrics"]["checks"] = ["C-01"]
        rungs[4]["metrics"]["checks"] = ["C-02"]
    return rungs


def ladder(dev, task, n, rungs, verdict, **extra):
    devlog.write_ladder_result(MART, {"task": task, "iteration": n, "contract_version": 1, "request_kind": "new_build",
                                      "modules": {"expert": {"on": [], "version": None}}, "bytes_total": 100,
                                      "rungs": rungs, "verdict": verdict, "halt_reason": extra.pop("halt_reason", None),
                                      **extra}, dev)


@pytest.fixture
def dev(repo):
    """반복 1 반려(stg L4, 데이터 값이 든 evidence) → 반복 2 하네스 halt → 재시작 개입 → 반복 3 통과."""
    d = repo / ".dev"
    evidence_rows = [{"example_id": 987654321, "name": "SECRETVALUE", "city": "Seoul-Gangnam"}]
    fail = rung("L4", {"check": "C-02", "violations_shown": 1, "evidence": evidence_rows}, "join_missing")
    ladder(d, "stg_example", 1, pass_rungs("stg_example")[:4] + [fail], "reject",
           interrupted_tasks=[{"task": "raw_example", "passed_rungs": ["L0", "L1", "L2", "L3", "L4"], "bytes": 50}])
    devlog.append("rejections", {"mart": MART, "task": "stg_example", "iteration": 1, "contract_version": 1,
                                 "caught_by_rung": "L4", "error_type": "join_missing", "error_class": "semantic",
                                 "detail": f"L4 join_missing [C-02]: Not found: Table {PROJECT_ID}:ai_dev.stg_example",
                                 "evidence": None}, d)
    devlog.append("rejections", {"mart": MART, "task": "stg_example", "iteration": 2, "contract_version": 1,
                                 "caught_by_rung": "L4", "error_type": "join_missing", "error_class": "semantic",
                                 "detail": "L4 join_missing [C-02]: 검사 C-02 위반 1행", "evidence": evidence_rows}, d)
    ladder(d, "raw_example", 2, [], "halt", halt_reason="infra_error",
           halt_detail={"exception": "InfraError", "message": "bq 끊김"})
    devlog.append("interventions", {"mart": MART, "kind": "manual_check", "target": "loop halt 재시작 (a) infra_error",
                                    "minutes_spent": 4,
                                    "note": f"하네스 결함으로 재시작, 계정 ai-builder@{PROJECT_ID}.iam.gserviceaccount.com 확인"}, d)
    for task in LOADS:
        ladder(d, task, 3, pass_rungs(task), "pass")
    for i, (role, n, usd) in enumerate((("verifier", 0, 0.16), ("builder", 1, 0.36), ("builder", 3, 0.31))):
        devlog.append("cost", {"run_id": "RUN-001", "mart": MART, "iteration": n, "role": role,
                               "model": "claude-x", "started": "2026-11-02T10:00:00+09:00",
                               "ended": "2026-11-02T10:01:00+09:00", "usage_before": None, "usage_after": None,
                               "input_tokens": 10, "output_tokens": 20, "cache_read_tokens": 0,
                               "cache_write_tokens": 0, "total_cost_usd": usd,
                               "bq_bytes_processed": 0 if role == "verifier" else 300}, d)
    return d


def make(repo, dev, *extra):
    code = make_facts.main(["--mart", MART, "--root", str(repo), "--dev-dir", str(dev), "--base", "main",
                            "--date", "2026-11-02", *extra])
    out = dev / "handover" / f"{BRANCH}.md"
    return code, (out.read_text(encoding="utf-8") if out.exists() else None)


def test_fact_sections_filled(repo, dev):
    code, text = make(repo, dev)
    assert code == 0
    assert text.startswith(f"# 인수인계 — {MART} ({BRANCH}, 2026-11-02)")
    # 2 바뀐 것: contract에서 테이블·task, git diff에서 파일 (.dev 로그는 뺌)
    assert f"| 테이블 | {prod('raw')}.raw_example | 신규 |" in text
    assert f"| 테이블 | {prod('mart')}.mart_example_daily | 신규 |" in text
    assert "| task | gate_stg_mart_example | 신규 |" in text
    assert "| 파일 | dags/sql/stg/stg_example.sql | 신규 |" in text
    assert "| 파일 | docs/requirements/mart_example.contract.json | 신규 |" in text
    assert ".dev/progress.md" not in text.split("## 3.")[0]
    # 3 데이터 흐름: 게이트를 건너뛴 load task 흐름
    assert "- (원천) → raw_example" in text and "- raw_example → stg_example" in text
    assert "- stg_example → mart_example_daily" in text
    assert "gate_raw_mart_example (raw 층, 상류 raw_example)" in text
    # 4 검증 결과: 반복별 판정과 마지막 통과 반복의 단계별 수치
    assert "| 1 | reject |" in text and "| 2 | halt |" in text and "| 3 | pass |" in text
    assert "마지막 통과 반복 3 (task 3/3 통과" in text
    assert "| L1 dry-run | 통과 | 스캔량 합 3,000 bytes (여러 문장 스크립트는 하한값) |" in text
    assert "| L3 레이어 게이트 | 통과 | 검사 C-01 위반 0행 |" in text
    assert "| L4 정합성 | 통과 | 검사 C-02 위반 0행 |" in text
    assert "ds 파티션 행 수 합 21" in text
    # 비용
    assert "| builder | 2 | 0.6700 | 20 | 40 | 600 |" in text and "| verifier | 1 | 0.1600 |" in text
    # 5 반려 이력: 두 줄 그대로, 해결 반복, 개입 기록(하네스 결함 재시작) 해석 없이
    assert "| R-0001 | 1 | stg_example | L4 | join_missing | semantic |" in text
    assert "| R-0002 | 2 | stg_example | L4 | join_missing | semantic | L4 join_missing [C-02]: 검사 C-02 위반 1행 |" in text
    assert "반복 3 통과" in text
    assert "있음(1행, 값은 옮기지 않음)" in text
    assert "| H-0001 |" in text and "manual_check" in text and "하네스 결함으로 재시작" in text
    # 8 링크, 설명 칸은 빈 자리
    assert "- 요구서: docs/requirements/mart_example.md" in text
    assert "- 인터뷰 기록: docs/requirements/mart_example_interview.md (없음)" in text
    assert text.count(make_facts.AI_SLOT) == 3


def test_no_data_values_or_project_id(repo, dev):
    _, text = make(repo, dev)
    for value in (*SECRET_VALUES, PROJECT_ID, "ai-builder@", "iam.gserviceaccount.com"):
        assert value not in text, value
    assert "Not found: Table <프로젝트>:ai_dev.stg_example" in text
    assert "<계정>" in text


def test_changed_contract_against_base(repo, dev):
    # 기준점에 contract가 있으면 테이블·task를 비교한다 (신규·변경·삭제)
    old = copy.deepcopy(VALID)
    old["tables"] = [t for t in old["tables"] if t["name"] != "mart_example_daily"]
    old["tables"].append({**copy.deepcopy(old["tables"][0]), "name": "raw_gone", "task": "raw_gone"})
    old["tables"][0]["grain"] = "옛 그레인"
    git(repo, "checkout", "-q", "main")
    write(repo, f"docs/requirements/{MART}.contract.json", json.dumps(old, ensure_ascii=False))
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "old contract")
    git(repo, "checkout", "-q", BRANCH)
    git(repo, "rebase", "-q", "main", "-X", "theirs")
    _, text = make(repo, dev)
    assert f"| 테이블 | {prod('raw')}.raw_example | 변경 |" in text
    assert f"| 테이블 | {prod('stg')}.stg_example | 그대로 |" in text
    assert f"| 테이블 | {prod('mart')}.mart_example_daily | 신규 |" in text
    assert f"| 테이블 | {prod('raw')}.raw_gone | 삭제 |" in text
    assert "| 파일 | docs/requirements/mart_example.contract.json | 변경 |" in text


def test_no_results_yet(repo, tmp_path):
    empty = tmp_path / "empty_dev"
    code, text = make(repo, empty)
    assert code == 0
    assert "사다리 결과 없음" in text and "반려 없음" in text and "비용 기록 없음" in text and "개입 기록 없음" in text


def test_does_not_overwrite(repo, dev, capsys):
    assert make(repo, dev)[0] == 0
    capsys.readouterr()
    code, _ = make(repo, dev)
    assert code == 2 and "덮어쓰지 않는다" in capsys.readouterr().err


def test_missing_contract_is_error(repo, dev, capsys):
    code = make_facts.main(["--mart", "mart_none", "--root", str(repo), "--dev-dir", str(dev), "--base", "main"])
    assert code == 2 and "contract를 읽지 못함" in capsys.readouterr().err


def test_scrub():
    mart = prod("mart")
    assert make_facts.scrub(f"Table my-proj-123:ai_dev.t and my-proj-123.{mart}.x") == \
        f"Table <프로젝트>:ai_dev.t and <프로젝트>:{mart}.x"
    assert make_facts.scrub(src("orders")) == src("orders")
    assert make_facts.scrub("ai-builder@p.iam.gserviceaccount.com") == "<계정>"


# ---------- 도장·최신성 검사·restamp·되돌림 (4-5, 결정 64 ⑤) ----------

def check(repo, dev):
    return make_facts.main(["--mart", MART, "--root", str(repo), "--dev-dir", str(dev), "--check"])


def commit_file(repo, rel, text, message="change"):
    write(repo, rel, text)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", message)


def draft_path(dev):
    return dev / "handover" / f"{BRANCH}.md"


def settle(repo):
    """가짜 사다리 결과까지 커밋한다. 도장 뒤에 결과 파일이 커밋되면 그 자체로 낡은 초안이 되므로 도장 전에 부른다."""
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "ladder results")


def test_stamp_lines_under_notice(repo, dev):
    _, text = make(repo, dev)
    head = git(repo, "rev-parse", "HEAD").strip()
    stamp = make_facts.read_stamp(text)
    assert list(stamp) == list(make_facts.STAMP_LABELS)
    assert stamp["contract_version"] == "1" and stamp["기준 커밋"] == head and len(head) == 40
    assert stamp["생성 시각"].endswith("+09:00")
    assert text.index("> 설명 칸") < text.index("- contract_version: 1") < text.index(make_facts.H1)


def test_check_fresh_after_draft_commit(repo, dev, capsys):
    settle(repo)
    make(repo, dev)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "draft")  # 초안을 커밋해 HEAD가 바뀌어도 최신이다
    assert check(repo, dev) == 0
    assert "최신:" in capsys.readouterr().out


def test_check_contract_version_changed(repo, dev, capsys):
    make(repo, dev)
    write(repo, f"docs/requirements/{MART}.contract.json", json.dumps({**VALID, "version": 2}, ensure_ascii=False))
    assert check(repo, dev) == 2
    err = capsys.readouterr().err
    assert err.startswith("halt input_invalid: ") and "contract_version 도장 1 ≠ 지금 2" in err
    assert len(err.strip().splitlines()) == 1


@pytest.mark.parametrize("rel", [
    f"docs/requirements/{MART}.contract.json",
    f"docs/requirements/{MART}.md",
    "dags/sql/stg/stg_example.sql",
    "dags/sql/dq/gate_stg_mart_example.sql",
    f"docs/requirements/{MART}_checks/l3/C-01.sql",
    f".dev/ladder_results/{MART}/stg_example-v1-9.json",
])
def test_check_mart_file_changed(repo, dev, capsys, rel):
    settle(repo)
    make(repo, dev)
    assert check(repo, dev) == 0
    old = (repo / rel).read_text(encoding="utf-8") if (repo / rel).exists() else ""
    commit_file(repo, rel, old + "\n")
    assert check(repo, dev) == 2
    assert "halt input_invalid: " in capsys.readouterr().err


@pytest.mark.parametrize("rel", ["dags/harness_daily.py", "docs/requirements/mart_other.md",
                                 "dags/sql/mart/mart_other.sql", ".dev/ladder_results/mart_other/x-v1-1.json"])
def test_check_other_files_do_not_stale(repo, dev, rel):
    settle(repo)
    make(repo, dev)
    commit_file(repo, rel, "# 다른 마트\n")
    assert check(repo, dev) == 0


def test_check_no_stamp_is_stale(repo, dev, capsys):
    _, text = make(repo, dev)
    draft_path(dev).write_text(make_facts.STAMP_LINE.sub("", text), encoding="utf-8", newline="\n")
    assert check(repo, dev) == 2
    assert "도장 없음" in capsys.readouterr().err


def test_check_stamp_in_body_is_not_a_stamp(repo, dev):
    _, text = make(repo, dev)
    head = git(repo, "rev-parse", "HEAD").strip()
    body = f"- contract_version: 1\n- 생성 시각: x\n- 기준 커밋: {head}\n"
    parts = make_facts.split_draft(make_facts.STAMP_LINE.sub("", text))
    parts[2] = body
    draft_path(dev).write_text("".join(parts), encoding="utf-8", newline="\n")
    assert check(repo, dev) == 2


def test_check_unknown_commit_and_missing_draft(repo, dev, capsys):
    assert check(repo, dev) == 2  # 초안 없음
    assert "초안을 읽지 못함" in capsys.readouterr().err
    _, text = make(repo, dev)
    head = git(repo, "rev-parse", "HEAD").strip()
    draft_path(dev).write_text(text.replace(head, "0" * 40), encoding="utf-8", newline="\n")
    assert check(repo, dev) == 2
    assert "찾지 못함" in capsys.readouterr().err


def fill_explanations(dev):
    parts = make_facts.split_draft(draft_path(dev).read_text(encoding="utf-8"))
    parts[2], parts[4], parts[6] = "요약 문장 | 그대로  \n\n", "- 운영 **방법**\n\n\n", "- 주의 <값>\n\n"
    draft_path(dev).write_text("".join(parts), encoding="utf-8", newline="\n")
    return parts


def test_restamp_keeps_explanations_and_updates_facts(repo, dev):
    settle(repo)
    make(repo, dev)
    before = fill_explanations(dev)
    old_stamp = make_facts.read_stamp("".join(before))
    commit_file(repo, "dags/sql/stg/stg_example.sql", "SELECT 2\n")
    commit_file(repo, "dags/sql/stg/new_file.sql", "SELECT 3\n")
    assert check(repo, dev) == 2
    code, text = make(repo, dev, "--restamp", "--date", "2026-12-31")
    assert code == 0
    after = make_facts.split_draft(text)
    assert after[0] == before[0]  # 제목 줄의 날짜는 처음 만든 날 그대로
    assert (after[2], after[4], after[6]) == (before[2], before[4], before[6])
    assert "| 파일 | dags/sql/stg/new_file.sql | 신규 |" in after[3] and "new_file" not in before[3]
    new_stamp = make_facts.read_stamp(text)
    assert new_stamp["기준 커밋"] == git(repo, "rev-parse", "HEAD").strip() != old_stamp["기준 커밋"]
    assert check(repo, dev) == 0


def test_restamp_old_draft_without_stamp_and_empty_slots(repo, dev):
    _, text = make(repo, dev)
    draft_path(dev).write_text(make_facts.STAMP_LINE.sub("", text), encoding="utf-8", newline="\n")
    code, text = make(repo, dev, "--restamp")
    assert code == 0 and make_facts.read_stamp(text)
    assert make_facts.empty_slots(text) == [1, 6, 7]


def test_restamp_needs_draft_and_headings(repo, dev, capsys):
    assert make(repo, dev, "--restamp")[0] == 2
    assert "--restamp할 초안이 없음" in capsys.readouterr().err
    draft_path(dev).parent.mkdir(parents=True, exist_ok=True)
    draft_path(dev).write_text("# 제목\n설명만 있음\n", encoding="utf-8", newline="\n")
    assert make(repo, dev, "--restamp")[0] == 2
    assert draft_path(dev).read_text(encoding="utf-8") == "# 제목\n설명만 있음\n"  # 손상 없음


def test_reverted_file_marked(repo, dev):
    commit_file(repo, "README.md", "고침\n", "edit")
    commit_file(repo, "README.md", "base\n", "revert")
    commit_file(repo, "tmp_note.md", "x\n", "add")
    git(repo, "rm", "-q", "tmp_note.md")
    git(repo, "commit", "-q", "-m", "drop")
    commit_file(repo, ".dev/note.md", "x\n", "log")
    git(repo, "rm", "-q", ".dev/note.md")
    git(repo, "commit", "-q", "-m", "drop log")
    _, text = make(repo, dev)
    assert "| 파일 | README.md | 되돌림 |" in text and "| 파일 | tmp_note.md | 되돌림 |" in text
    assert ".dev/note.md" not in text
    assert "| 파일 | dags/harness_daily.py | 신규 |" in text


def test_rename_is_not_reverted(repo, dev):
    git(repo, "mv", "dags/harness_daily.py", "dags/harness_moved.py")
    git(repo, "commit", "-q", "-m", "move")
    _, text = make(repo, dev)
    assert "되돌림" not in text


def test_head_fixes_end_of_changes(repo, dev):
    commit_file(repo, "README.md", "고침\n", "edit")
    end = git(repo, "rev-parse", "HEAD").strip()
    base = git(repo, "rev-parse", "main").strip()
    commit_file(repo, "scripts/later.py", "x\n", "later")
    commit_file(repo, "README.md", "base\n", "revert after end")
    _, text = make(repo, dev, "--head", end[:10])
    changes = text.split(make_facts.H3)[0]
    assert "later.py" not in changes
    assert "| 파일 | README.md | 변경 |" in changes  # 끝점 뒤의 되돌리기는 보지 않는다
    assert f"기준점 `{base[:8]}` 대비, 끝점 `{end[:8]}` (git diff {base[:8]}...{end[:8]})" in changes
    head = git(repo, "rev-parse", "HEAD").strip()
    assert make_facts.read_stamp(text)["기준 커밋"] == head != end  # 도장은 --head와 섞지 않는다


def test_head_equal_to_head_keeps_wording(repo, dev):
    base = git(repo, "rev-parse", "main").strip()
    _, text = make(repo, dev, "--head", git(repo, "rev-parse", "HEAD").strip())
    assert f"기준점 `{base[:8]}` 대비 (git diff {base[:8]}...HEAD)" in text and "끝점" not in text


def test_head_unknown_ref_is_error(repo, dev):
    assert make(repo, dev, "--head", "no-such-ref")[0] == 2


def test_restamp_with_head(repo, dev):
    settle(repo)
    make(repo, dev)
    fill_explanations(dev)
    end = git(repo, "rev-parse", "HEAD").strip()
    commit_file(repo, "scripts/later.py", "x\n", "later")
    code, text = make(repo, dev, "--restamp", "--head", end)
    assert code == 0 and "later.py" not in text and f"끝점 `{end[:8]}`" in text
    assert check(repo, dev) == 0


def l6_post(d, verdict, error_type=None, missing=()):
    """L6 순번 파일 1개 (결정 67). task = 마트."""
    metrics = {"service": "Test_OM", "tables_missing": [], "description_missing": list(missing), "edges_missing": [],
               "edges_unexpected": [], "source_edges": []}
    g = {"rung": "L6", "ds": None, "status": "fail" if error_type else "pass", "metrics": metrics,
         "error_type": error_type, "error_class": "semantic" if error_type else None}
    return devlog.write_ladder_result(MART, {"task": MART, "iteration": "post", "contract_version": 1,
                                             "request_kind": "new_build",
                                             "modules": {"expert": {"on": [], "version": None}}, "bytes_total": None,
                                             "rungs": [g], "verdict": verdict, "halt_reason": None}, d)


OM_DONE = "OM 서비스 Test_OM에서 등록 확인 (L6 통과, post-{})"


def sections_3_and_8(text):
    return text.split(make_facts.H3)[1].split(make_facts.H4)[0], text.split(make_facts.H8)[1]


def assert_om_pending(text):
    flow, links = sections_3_and_8(text)
    assert "OM 리니지 링크는 결재 후 L6 통과 시 docs/handover/ 반영 때 추가한다." in flow
    assert "- OM 테이블: 결재 후 L6 통과 시 docs/handover/ 반영 때 추가" in links
    assert "등록 확인" not in text


def test_om_wording_without_l6(repo, dev):
    assert_om_pending(make(repo, dev)[1])


def test_om_wording_after_l6_pass(repo, dev):
    l6_post(dev, "reject", "description_missing", ["stg_example.example_id"])
    l6_post(dev, "pass")
    text = make(repo, dev)[1]
    flow, links = sections_3_and_8(text)
    assert f"OM 리니지: {OM_DONE.format(2)}" in flow
    assert f"- OM 테이블: {OM_DONE.format(2)}" in links
    assert "L6 통과 시 docs/handover/" not in text


def test_om_wording_follows_latest_l6(repo, dev):
    l6_post(dev, "pass")
    l6_post(dev, "reject", "description_missing", ["stg_example.example_id"])
    assert_om_pending(make(repo, dev)[1])


def test_section_flow_default_wording_for_flow_diagram():
    assert "OM 리니지 링크는 결재 후" in make_facts.section_flow(copy.deepcopy(VALID))


def test_l6_latest_post_and_resolution(repo, dev):
    """인수인계는 L6 순번 파일 중 가장 큰 n을 최신 L6로 보이고, L6 반려의 해결을 그 뒤 통과한 순번으로 적는다."""
    assert "| L6 OM 등록 | 결재 후 |" in make(repo, dev)[1]
    l6_post(dev, "reject", "description_missing", ["stg_example.example_id"])
    devlog.append("rejections", {"mart": MART, "task": MART, "iteration": "post", "contract_version": 1,
                                 "caught_by_rung": "L6", "error_type": "description_missing",
                                 "error_class": "semantic", "detail": "L6 description_missing: 설명 빠진 컬럼 1개",
                                 "evidence": None}, dev)
    _, text = make(repo, dev, "--out", str(dev / "handover" / "a.md"))
    text = (dev / "handover" / "a.md").read_text(encoding="utf-8")
    assert "| L6 OM 등록 | 반려 (description_missing) | 최신 post-1 (L6 실행 1회), 테이블 없음 0, 설명 누락 1" in text
    assert "| R-0003 | post | mart_example | L6 | description_missing |" in text and "| — |" in text
    l6_post(dev, "pass")
    make(repo, dev, "--out", str(dev / "handover" / "b.md"))
    text = (dev / "handover" / "b.md").read_text(encoding="utf-8")
    assert "| L6 OM 등록 | 통과 | 최신 post-2 (L6 실행 2회), 테이블 없음 0, 설명 누락 0, 엣지 누락 0" in text
    assert f"`.dev/ladder_results/{MART}/{MART}-v1-post-2.json`" in text
    assert "description_missing | semantic | L6 description_missing: 설명 빠진 컬럼 1개 | 없음 | post-2 통과 |" in text
