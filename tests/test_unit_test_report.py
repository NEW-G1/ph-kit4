"""scripts/deliverables/unit_test_report.py 시험 (진행표 3-6). 임시 git 저장소와 가짜 .dev 폴더로 돈다."""
import copy
import json
import shutil
import subprocess
import sys
from pathlib import Path

import openpyxl
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "deliverables"))
sys.path.insert(0, str(ROOT / "scripts" / "log"))
import devlog  # noqa: E402
import unit_test_report as utr  # noqa: E402
from test_l0_contract import VALID  # noqa: E402

MART = "mart_example"
PROJECT_ID = "my-proj-123"
SECRETS = ("987654321", "SECRETVALUE", "Seoul-Gangnam", PROJECT_ID, "ai-builder@", "gserviceaccount")
LOADS = ["raw_example", "stg_example", "mart_example_daily"]
NOW = "2026-11-02T15:00:00+09:00"
TASK_CHECKS = {"stg_example": {"L3": ["C-01"], "L4": ["C-02"]}, "mart_example_daily": {"L4": ["I-01"]}}
CHECK_FILES = {"C-01": "l3", "C-02": "l4", "I-01": "l4"}
# mart_user_returns 형식: 두 절이 굵은 제목이고 가정 항목 아래에 들여쓴 줄이 있다
VERIFIER = f"""검증 쿼리 3개를 썼습니다.

**contract만으로는 정해지지 않아 가정한 것**
- **머리말 `task` 값:** 게이트를 고르는 값입니다.
  - C-01은 stg 층입니다.
- **C-02:** 원천 `{PROJECT_ID}:ai_dev.raw_example`을 읽습니다.

**쓰지 않은 파일**
- 없습니다.

**사다리로 검증되지 않는 완료 조건**
- **L6(OM 등록):** 결재 후 운영 절차 뒤에 코드가 판정합니다.
- **문의:** ai-builder@{PROJECT_ID}.iam.gserviceaccount.com 계정 기록은 사다리 밖입니다.
"""
# mart_daily_sales 형식: "사람이 볼 것" 절 안의 목록 항목 하나가 사다리 밖 항목이다
VERIFIER_INLINE = """**사람이 볼 것**
- **C-01의 task:** 머리말에는 task를 하나만 쓸 수 있습니다.
- **사다리로 검증되지 않는 완료 조건:** L0, L1, L2는 이 쿼리로 검증하지 않습니다.
- **알려진 데이터 특성:** 요구서대로 게이트에 넣지 않았습니다.
"""


def git(root, *args):
    p = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, encoding="utf-8")
    assert p.returncode == 0, p.stderr
    return p.stdout.strip()


def build_repo(root):
    (root / "docs" / "requirements").mkdir(parents=True)
    (root / "docs" / "requirements" / f"{MART}.contract.json").write_text(json.dumps(VALID, ensure_ascii=False),
                                                                          encoding="utf-8")
    git(root, "init", "-q", "--template=", "-b", "week9/mart-example")
    git(root, "config", "user.email", "t@example.com")
    git(root, "config", "user.name", "t")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "contract")
    return root


def rung(name, metrics=None, error_type=None):
    return {"rung": name, "ds": None if name == "L0" else "2026-11-02", "status": "fail" if error_type else "pass",
            "metrics": metrics or {}, "error_type": error_type, "error_class": "semantic" if error_type else None}


def pass_rungs(task):
    checks = TASK_CHECKS.get(task, {})
    return [rung("L0", {"stage": "contract", "load_tasks": 3, "gate_tasks": 3, "tables": 3, "checks": 3, "traces": 3,
                        "dag": "pass"}),
            rung("L1", {"bytes_processed": 2048, "bytes_accuracy": "LOWER_BOUND"}),
            rung("L2", {"dataset": "ai_dev", "table": task}),
            rung("L3", {"gate": "gate_x", "gate_sha256": "ab" * 32, "checks": checks.get("L3", [])}),
            rung("L4", {"checks": checks.get("L4", [])}),
            rung("L5", {"row_count": "7", "checks": checks.get("L5", [])})]


def ladder(dev, task, n, rungs, verdict, **extra):
    devlog.write_ladder_result(MART, {"task": task, "iteration": n, "contract_version": 1, "request_kind": "new_build",
                                      "modules": {"expert": {"on": [], "version": None}}, "bytes_total": 100,
                                      "rungs": rungs, "verdict": verdict, "halt_reason": extra.pop("halt_reason", None),
                                      **extra}, dev)


def check_file(repo, stage, cid):
    return repo / "docs" / "requirements" / f"{MART}_checks" / stage / f"{cid}.sql"


def verifier_file(d, run):
    return d / "agent_responses" / MART / f"RUN-{run:03d}-i0-verifier.md"


def build_dev(repo):
    """반복 1 반려(stg L4, 데이터 값이 든 evidence·프로젝트 ID가 든 메시지) → 반복 2 반려 → 재시작 개입 → 반복 3 통과."""
    d = repo / ".dev"
    for cid, stage in CHECK_FILES.items():
        check_file(repo, stage, cid).parent.mkdir(parents=True, exist_ok=True)
        check_file(repo, stage, cid).write_text(f"SELECT '{cid}' WHERE FALSE\n", encoding="utf-8")
    utr.state.write_hash_file(repo, d, MART, 1)
    verifier_file(d, 1).parent.mkdir(parents=True)
    verifier_file(d, 1).write_text(VERIFIER, encoding="utf-8")
    rows = [{"example_id": 987654321, "name": "SECRETVALUE", "city": "Seoul-Gangnam"}]
    for n in (1, 2):
        fail = rung("L4", {"check": "C-02", "violations_shown": 1, "evidence": rows}, "join_missing")
        ladder(d, "stg_example", n, pass_rungs("stg_example")[:4] + [fail], "reject")
        devlog.append("rejections", {"mart": MART, "task": "stg_example", "iteration": n, "contract_version": 1,
                                     "caught_by_rung": "L4", "error_type": "join_missing", "error_class": "semantic",
                                     "detail": f"L4 join_missing [C-02]: Not found: Table {PROJECT_ID}:ai_dev.stg_example",
                                     "evidence": None if n == 1 else rows}, d)
    devlog.append("interventions", {"mart": MART, "kind": "manual_check", "target": "loop halt 재시작 (a)",
                                    "minutes_spent": 3,
                                    "note": f"하네스 결함 재시작, ai-builder@{PROJECT_ID}.iam.gserviceaccount.com"}, d)
    for task in LOADS:
        ladder(d, task, 3, pass_rungs(task), "pass")
    return d


@pytest.fixture(scope="module")
def seed(tmp_path_factory):
    """저장소와 .dev는 파일당 1번만 만든다. 시험은 고쳐 쓰므로 공유하지 않고 복사본을 받는다."""
    clean = tmp_path_factory.mktemp("utr_seed") / "repo"
    build_repo(clean)
    full = clean.parent / "full"
    shutil.copytree(clean, full)
    build_dev(full)
    return clean, full


@pytest.fixture
def repo(tmp_path, seed):
    return Path(shutil.copytree(seed[0], tmp_path / "repo"))


@pytest.fixture
def dev(repo, seed):
    checks = Path("docs") / "requirements" / f"{MART}_checks"
    shutil.copytree(seed[1] / checks, repo / checks)
    return Path(shutil.copytree(seed[1] / ".dev", repo / ".dev"))


def make(repo, dev, *extra):
    code = utr.main(["--mart", MART, "--root", str(repo), "--dev-dir", str(dev), "--date", "2026-11-02", *extra],
                    now=NOW)
    out = repo / "out" / "deliverables" / MART / f"UTR_{MART}_20261102.xlsx"
    return code, out


def values(ws):
    return {c.coordinate: c.value for row in ws.iter_rows() for c in row if c.value is not None}


def result_rows(wb):
    ws = wb["시험 결과"]
    cols = {ws.cell(4, c).value: c for c in range(1, ws.max_column + 1)}
    out = []
    for r in range(5, ws.max_row + 1):
        if ws.cell(r, 1).value:
            out.append({name: ws.cell(r, c).value for name, c in cols.items()})
    return out


def by_gate(rows):
    return {r["케이스 ID"]: r["실제값"] for r in rows if r["시험 항목"] and r["시험 항목"].startswith("게이트 파일")}


def test_sheets_filled(repo, dev):
    code, out = make(repo, dev)
    assert code == 0 and out.exists()
    wb = openpyxl.load_workbook(out)
    cover = wb["표지"]
    assert cover["B6"].value == f"UTR-{MART}-20261102" and cover["B8"].value == MART and cover["B11"].value == "v1"
    assert cover["B12"].value == "on: [] / version: null" and cover["B13"].value == "본 측정 (노하우 꺼짐)"
    assert cover["B18"].value == "pass (마지막 반복 3)"
    assert cover["B20"].value == "마트 실행 반복 3회 (pass 1, reject 2, halt 0)"
    assert cover["B26"].value is None and cover["B27"].value is None and cover["B28"].value is None  # 노란 칸
    rows = result_rows(wb)
    ids = [r["케이스 ID"] for r in rows]
    assert ids[:2] == [f"UT-{MART}-L0-01", f"UT-{MART}-L0-02"] and ids[-1] == f"UT-{MART}-L6-01"
    assert "UT-stg_example-L3-02" in ids and "UT-stg_example-L4-01" in ids and "UT-mart_example_daily-L4-01" in ids
    assert by_gate(rows)["UT-raw_example-L3-01"] == "해시 일치 (sha256 abababababab)"
    by_id = {r["케이스 ID"]: r for r in rows}
    c01 = by_id["UT-stg_example-L3-02"]
    assert (c01["검사 ID"], c01["요구 ID"], c01["검사 종류"], c01["검사 작성"], c01["판정"]) == \
        ("C-01", "R-01", "gates", "verifier", "pass")
    assert c01["실제값"] == "위반 0행" and c01["반복"] == "3"
    assert by_id["UT-raw_example-L1-01"]["실제값"] == "통과, 2,048 B"
    assert by_id["UT-raw_example-L5-01"]["실제값"] == "동일 (ds 파티션 행 수 7)"
    l6 = by_id[f"UT-{MART}-L6-01"]
    assert (l6["판정"], l6["실제값"], l6["비고"], l6["반복"]) == ("미실행", "미실행(결재 후)", "미실행(결재 후)", "post")
    assert all(r["판정"] == "pass" for r in rows[:-1])
    trace = values(wb["요구 추적"])
    assert trace["A5"] == "R-01" and trace["D5"] == "C-01" and trace["E5"] == "L3" and trace["C5"] == 3
    rej = values(wb["반려 이력"])
    assert rej["A5"] == "R-0001" and rej["E5"] == "L4" and rej["J5"] == "3" and "I5" not in rej
    assert rej["I6"].startswith("있음(1행, 값은 옮기지 않음")
    assert any(v == "H-0001" for v in rej.values()) and any("하네스 결함 재시작" in str(v) for v in rej.values())


def test_no_data_values_or_project_id(repo, dev):
    _, out = make(repo, dev)
    wb = openpyxl.load_workbook(out)
    text = json.dumps([values(ws) for ws in wb.worksheets], ensure_ascii=False, default=str)
    for s in SECRETS:
        assert s not in text, s
    assert "<프로젝트>:ai_dev.stg_example" in text and "<계정>" in text
    manifest = (repo / "out" / "deliverables" / MART / "manifest.json").read_text(encoding="utf-8")
    assert not any(s in manifest for s in SECRETS)


def test_stamp_and_check(repo, dev, capsys):
    _, out = make(repo, dev)
    head = git(repo, "rev-parse", "HEAD")
    stamp = utr.read_stamp(out)
    assert stamp == {"contract_version": 1, "생성 시각": NOW, "기준 커밋": head}
    assert utr.main(["--mart", MART, "--root", str(repo), "--check"]) == 0
    # HEAD가 바뀌면 최신이 아님
    (repo / "README.md").write_text("x\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "next")
    capsys.readouterr()
    assert utr.main(["--mart", MART, "--root", str(repo), "--check"]) == 2
    assert "halt input_invalid" in capsys.readouterr().err


def test_check_contract_version_mismatch(repo, dev, capsys):
    _, out = make(repo, dev)
    c = copy.deepcopy(VALID)
    c["version"] = 2
    (repo / "docs" / "requirements" / f"{MART}.contract.json").write_text(json.dumps(c), encoding="utf-8")
    capsys.readouterr()
    assert utr.main(["--mart", MART, "--root", str(repo), "--check", "--file", str(out)]) == 2
    assert "contract_version 도장 1 ≠ 지금 2" in capsys.readouterr().err


def test_check_without_report(repo, capsys):
    assert utr.main(["--mart", MART, "--root", str(repo), "--check"]) == 2
    assert "결과서가 없음" in capsys.readouterr().err


def test_manifest_counts_missing_required(repo, dev):
    code, _ = make(repo, dev)
    m = json.loads((repo / "out" / "deliverables" / MART / "manifest.json").read_text(encoding="utf-8"))
    entry = next(d for d in m["deliverables"] if d["name"] == "unit_test_report")
    assert entry["required_fields"] > 0
    # L6(결재 전, 미실행)의 실행 시각·증빙은 원천이 아직 없다 → missing이 아니라 deferred
    assert entry["missing_fields"] == len(entry["missing"]) == 0
    assert entry["deferred_fields"] == len(entry["deferred"]) == 2
    assert all(x.startswith("시험 결과!") for x in entry["deferred"])
    assert any("실행 시각" in x for x in entry["deferred"]) and any("증빙" in x for x in entry["deferred"])
    assert entry["contract_version"] == 1 and entry["generated_at"] == NOW


def test_manifest_counts_check_without_run_record(repo, dev):
    # contract에는 있는데 마지막 통과 반복에서 실행 기록이 없는 검사 → 미실행 행, 기대·실제값 등 누락으로 셈
    c = copy.deepcopy(VALID)
    c["checks"]["invariants"].append({"id": "I-02", "rule": "합계 보존", "rung": "L4", "written_by": "verifier"})
    (repo / "docs" / "requirements" / f"{MART}.contract.json").write_text(json.dumps(c), encoding="utf-8")
    make(repo, dev)
    m = json.loads((repo / "out" / "deliverables" / MART / "manifest.json").read_text(encoding="utf-8"))
    entry = m["deliverables"][0]
    assert entry["missing_fields"] > 0 and any("기대값" in x for x in entry["missing"])
    assert entry["deferred_fields"] == 2  # 미실행 검사 행은 deferred가 아니라 missing
    assert not any("L6" in x for x in entry["missing"])


def test_manifest_keeps_other_deliverables(repo, dev):
    folder = repo / "out" / "deliverables" / MART
    folder.mkdir(parents=True)
    (folder / "manifest.json").write_text(json.dumps({"deliverables": [
        {"name": "table_definition", "required_fields": 3, "missing_fields": 0}], "handover": {"fact_fields": 1,
                                                                                                "missing": 0}}),
        encoding="utf-8")
    make(repo, dev)
    m = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    assert [d["name"] for d in m["deliverables"]] == ["table_definition", "unit_test_report"] and "handover" in m


def test_no_passed_iteration_is_error(repo, capsys):
    d = repo / ".dev"
    fail = rung("L1", {"message": "x"}, "syntax")
    ladder(d, "raw_example", 1, [pass_rungs("raw_example")[0], fail], "reject")
    code, out = make(repo, d)
    assert code == 2 and not out.exists() and "통과한 반복이 없음" in capsys.readouterr().err


def test_does_not_overwrite_without_force(repo, dev, capsys):
    assert make(repo, dev)[0] == 0
    capsys.readouterr()
    assert make(repo, dev)[0] == 2 and "덮어쓰지 않는다" in capsys.readouterr().err
    assert make(repo, dev, "--force")[0] == 0


def test_required_fields_match_mapping_sheet():
    """변환기의 필수 칸 목록이 양식 '칸 매핑' 시트의 필수=Y와 맞는지 (양식이 바뀌면 여기서 걸린다)."""
    ws = openpyxl.load_workbook(utr.TEMPLATE)["칸 매핑"]
    required = {(ws.cell(r, 1).value, ws.cell(r, 2).value) for r in range(5, ws.max_row + 1) if ws.cell(r, 5).value == "Y"}
    assert {k for s, k in required if s == "표지"} == set(utr.REQUIRED_COVER)
    expected_result = {"케이스 ID", "task", "레이어", "사다리 단계", "시험 항목", "시험 방법", "기대값 / 실제값", "판정",
                       "반복", "검사 작성", "실행 시각", "증빙"}
    assert {k for s, k in required if s == "시험 결과"} == expected_result
    assert {k for s, k in required if s == "요구 추적"} == {"요구 ID·내용·절", "검사 ID·단계", "판정"}
    assert {k for s, k in required if s == "반려 이력"} == {"반려 ID~내용"}


def test_l6_executed_fields_count_as_missing(repo, dev, monkeypatch):
    """L6가 실행된 뒤(판정이 미실행이 아님)에는 실행 시각·증빙도 다른 행처럼 필수로 센다."""
    original = utr.Facts.rows

    def rows_with_l6_run(self):
        rows = original(self)
        rows[-1] = {**rows[-1], "판정": "pass", "실제값": "누락 0, 엣지 일치", "비고": ""}
        return rows
    monkeypatch.setattr(utr.Facts, "rows", rows_with_l6_run)
    make(repo, dev)
    entry = json.loads((repo / "out" / "deliverables" / MART / "manifest.json").read_text(encoding="utf-8"))["deliverables"][0]
    assert entry["deferred_fields"] == 0 and entry["missing_fields"] == 2
    assert any("실행 시각" in x for x in entry["missing"]) and any("증빙" in x for x in entry["missing"])


def l6_post(d, verdict, error_type=None, missing=()):
    """L6 순번 파일 1개 (결정 67). task = 마트."""
    metrics = {"tables_missing": [], "description_missing": list(missing), "edges_missing": [],
               "edges_unexpected": ["a -> b"], "source_edges": []}
    g = {"rung": "L6", "ds": None, "status": "fail" if error_type else "pass", "metrics": metrics,
         "error_type": error_type, "error_class": "semantic" if error_type else None}
    return devlog.write_ladder_result(MART, {"task": MART, "iteration": "post", "contract_version": 1,
                                             "request_kind": "new_build",
                                             "modules": {"expert": {"on": [], "version": None}}, "bytes_total": None,
                                             "rungs": [g], "verdict": verdict, "halt_reason": None}, d)


def test_l6_row_reads_latest_post(repo, dev):
    """결과서 L6 행은 순번 파일 중 가장 큰 n을 읽고, 실행 뒤에는 실행 시각·증빙도 필수(deferred 아님)로 센다."""
    l6_post(dev, "reject", "description_missing", ["stg_example.example_id"])
    devlog.append("rejections", {"mart": MART, "task": MART, "iteration": "post", "contract_version": 1,
                                 "caught_by_rung": "L6", "error_type": "description_missing",
                                 "error_class": "semantic", "detail": "L6 description_missing: 설명 빠진 컬럼 1개",
                                 "evidence": None}, dev)
    make(repo, dev)
    l6 = result_rows(openpyxl.load_workbook(repo / "out" / "deliverables" / MART / f"UTR_{MART}_20261102.xlsx"))[-1]
    assert (l6["판정"], l6["반복"], l6["error_type"]) == ("fail", "post-1", "description_missing")
    l6_post(dev, "pass")
    code, out = make(repo, dev, "--force")
    assert code == 0
    wb = openpyxl.load_workbook(out)
    l6 = result_rows(wb)[-1]
    assert (l6["케이스 ID"], l6["판정"], l6["반복"]) == (f"UT-{MART}-L6-01", "pass", "post-2")
    assert l6["실제값"] == "테이블 없음 0, 설명 누락 0, 엣지 누락 0"
    assert l6["증빙 (ladder_result 경로)"] == f".dev/ladder_results/{MART}/{MART}-v1-post-2.json"
    assert l6["실행 시각"] and "L6 실행 2회 중 최신 post-2" in l6["비고"] and "기대 밖 엣지 1" in l6["비고"]
    assert l6["시험 방법 (판정 코드·쿼리)"] == "scripts/ladder/l6_om.py"
    rej = values(wb["반려 이력"])
    l6_rej_row = next(k[1:] for k, v in rej.items() if v == "R-0003")
    assert rej[f"E{l6_rej_row}"] == "L6" and rej[f"J{l6_rej_row}"] == "post-2"
    entry = json.loads((repo / "out" / "deliverables" / MART / "manifest.json").read_text(encoding="utf-8"))
    entry = next(d for d in entry["deliverables"] if d["name"] == "unit_test_report")
    assert entry["deferred_fields"] == 0 and entry["missing_fields"] == 0


# ---------- 검사 해시 ----------

def manifest_entry(repo):
    data = json.loads((repo / "out" / "deliverables" / MART / "manifest.json").read_text(encoding="utf-8"))
    return next(d for d in data["deliverables"] if d["name"] == "unit_test_report")


def saved_hash(repo, stage, cid):
    return utr.state.sha256_file(check_file(repo, stage, cid))[:12]


def test_hash_on_method_cell_and_cover(repo, dev):
    _, out = make(repo, dev)
    wb = openpyxl.load_workbook(out)
    rows = {r["케이스 ID"]: r for r in result_rows(wb)}
    method = "시험 방법 (판정 코드·쿼리)"
    assert rows["UT-stg_example-L3-02"][method] == (
        f"docs/requirements/{MART}_checks/l3/C-01.sql → dags/sql/dq/gate_stg_mart_example.sql "
        f"(sha256 {saved_hash(repo, 'l3', 'C-01')})")
    assert rows["UT-stg_example-L4-01"][method].endswith(f"l4/C-02.sql (sha256 {saved_hash(repo, 'l4', 'C-02')})")
    assert sum("(sha256 " in str(r[method]) for r in rows.values()) == 3  # 검사 행에만
    cover = wb["표지"]
    assert cover.cell(utr.HASH_ROW, 1).value == "검사 해시 기록"
    assert cover.cell(utr.HASH_ROW, 2).value == f".dev/checks_hash/{MART}-v1.json (iteration 0 커밋, 매 반복 사다리 전 비교)"


def test_hash_comes_from_saved_file_not_current_file(repo, dev):
    """결재 때 고정된 값이 근거다. 파일이 나중에 바뀌어도 결과서에는 해시 기록의 값이 나온다."""
    before = saved_hash(repo, "l4", "C-02")
    check_file(repo, "l4", "C-02").write_text("SELECT 'changed'\n", encoding="utf-8")
    _, out = make(repo, dev)
    rows = {r["케이스 ID"]: r for r in result_rows(openpyxl.load_workbook(out))}
    assert rows["UT-stg_example-L4-01"]["시험 방법 (판정 코드·쿼리)"].endswith(f"(sha256 {before})")


def test_hash_file_missing_counts_as_missing(repo, dev):
    utr.state.hash_file(dev, MART, 1).unlink()
    code, out = make(repo, dev)
    assert code == 0
    wb = openpyxl.load_workbook(out)
    assert wb["표지"].cell(utr.HASH_ROW, 2).value is None
    assert not any("sha256" in str(r["시험 방법 (판정 코드·쿼리)"]) for r in result_rows(wb))
    entry = manifest_entry(repo)
    assert entry["missing_fields"] == 4  # 표지 1 + 검사 행 3
    assert f"표지!B{utr.HASH_ROW} 검사 해시 기록" in entry["missing"]
    assert sum(x.endswith("검사 해시") for x in entry["missing"]) == 3


def test_hash_entry_missing_for_one_check(repo, dev):
    path = utr.state.hash_file(dev, MART, 1)
    saved = json.loads(path.read_text(encoding="utf-8"))
    del saved[f"docs/requirements/{MART}_checks/l4/I-01.sql"]
    path.write_text(json.dumps(saved), encoding="utf-8")
    make(repo, dev)
    entry = manifest_entry(repo)
    assert entry["missing_fields"] == 1 and entry["missing"][0].endswith("검사 해시")


def run_check(repo):
    return utr.main(["--mart", MART, "--root", str(repo), "--check"])


@pytest.mark.parametrize("change", ["edit", "delete", "add"])
def test_check_catches_check_file_change(repo, dev, capsys, change):
    make(repo, dev)
    assert run_check(repo) == 0
    target = check_file(repo, "l4", "C-02")
    if change == "edit":
        target.write_text("SELECT 'changed'\n", encoding="utf-8")
    elif change == "delete":
        target.unlink()
    else:
        target = check_file(repo, "l4", "I-09")
        target.write_text("SELECT 1\n", encoding="utf-8")
    capsys.readouterr()
    assert run_check(repo) == 2
    err = capsys.readouterr().err
    assert "halt input_invalid" in err and target.name in err and "C-01" not in err


def test_check_catches_own_gate_change_only(repo, dev, capsys):
    """같은 해시 파일에 든 공용 입력·다른 마트 게이트는 뒤에 바뀌는 것이 정상이라 보지 않는다 (mart_daily_sales 실제 상황)."""
    dq = repo / "dags" / "sql" / "dq"
    dq.mkdir(parents=True)
    pii = repo / "docs" / "architecture" / "pii_columns.md"
    pii.parent.mkdir(parents=True)
    pii.write_text("v1\n", encoding="utf-8")
    (dq / "gate_stg_mart_example.sql").write_text("SELECT 1\n", encoding="utf-8")
    utr.state.write_hash_file(repo, dev, MART, 1)
    make(repo, dev)
    pii.write_text("v2\n", encoding="utf-8")
    (dq / "gate_stg_mart_other.sql").write_text("SELECT 1\n", encoding="utf-8")
    assert run_check(repo) == 0
    (dq / "gate_stg_mart_example.sql").write_text("SELECT 2\n", encoding="utf-8")
    capsys.readouterr()
    assert run_check(repo) == 2
    err = capsys.readouterr().err
    assert "gate_stg_mart_example.sql" in err and "pii_columns" not in err and "mart_other" not in err


def test_check_ignores_line_endings(repo, dev):
    make(repo, dev)
    check_file(repo, "l4", "C-02").write_bytes(b"SELECT 'C-02' WHERE FALSE\r\n")
    assert run_check(repo) == 0


def test_check_without_hash_file_keeps_stamp_result(repo, dev, capsys):
    make(repo, dev)
    utr.state.hash_file(dev, MART, 1).unlink()
    capsys.readouterr()
    assert run_check(repo) == 0
    assert "비교하지 않음" in capsys.readouterr().err


# ---------- 사다리 밖 항목 ----------

def outside_rows(wb):
    ws = wb[utr.OUTSIDE_SHEET]
    assert [ws.cell(4, c).value for c in range(1, 5)] == utr.OUTSIDE_COLS
    return [tuple(ws.cell(r, c).value for c in range(1, 5)) for r in range(5, ws.max_row + 1)]


def test_outside_sheet_copies_verifier_text(repo, dev):
    _, out = make(repo, dev)
    wb = openpyxl.load_workbook(out)
    assert wb[utr.OUTSIDE_SHEET]["A1"].value == "verifier 보고 원문, 판정 아님"
    assert wb.sheetnames.index(utr.OUTSIDE_SHEET) == wb.sheetnames.index("요구 추적") + 1
    rows = outside_rows(wb)
    source = f".dev/agent_responses/{MART}/RUN-001-i0-verifier.md"
    assert {r[2] for r in rows} == {source} and {r[3] for r in rows} == {None}
    outside = [r[1] for r in rows if r[0] == utr.KIND_OUTSIDE]
    assumed = [r[1] for r in rows if r[0] == "contract만으로는 정해지지 않아 가정한 것"]  # 응답의 절 제목 그대로
    assert {r[0] for r in rows} == {utr.KIND_OUTSIDE, "contract만으로는 정해지지 않아 가정한 것"}
    assert outside[0] == "- **L6(OM 등록):** 결재 후 운영 절차 뒤에 코드가 판정합니다." and len(outside) == 2
    assert assumed[0] == "- **머리말 `task` 값:** 게이트를 고르는 값입니다.\n  - C-01은 stg 층입니다." and len(assumed) == 2
    assert not any("없습니다." in r[1] for r in rows)  # 다른 절은 옮기지 않는다
    assert wb["표지"]["B22"].value == (f"'{utr.OUTSIDE_SHEET}' 시트: {utr.KIND_OUTSIDE} 2건, {utr.KIND_ASSUMED} 2건 "
                                       "(verifier 보고, 판정 아님)")
    assert manifest_entry(repo)["missing_fields"] == 0


def test_outside_item_inside_other_section(repo, dev):
    verifier_file(dev, 1).write_text(VERIFIER_INLINE, encoding="utf-8")
    _, out = make(repo, dev)
    rows = outside_rows(openpyxl.load_workbook(out))
    assert [r[1] for r in rows if r[0] == utr.KIND_OUTSIDE] == [
        "- **사다리로 검증되지 않는 완료 조건:** L0, L1, L2는 이 쿼리로 검증하지 않습니다."]
    assert [r[1] for r in rows if r[0] == "사람이 볼 것"] == [
        "- **C-01의 task:** 머리말에는 task를 하나만 쓸 수 있습니다.", "- **알려진 데이터 특성:** 요구서대로 게이트에 넣지 않았습니다."]
    assert manifest_entry(repo)["missing_fields"] == 0


def test_outside_uses_largest_run_number(repo, dev):
    (dev / "agent_responses" / MART / "RUN-9-i0-verifier.md").write_text("**가정**\n- 옛 보고\n", encoding="utf-8")
    (dev / "agent_responses" / MART / "RUN-10-i0-verifier.md").write_text(VERIFIER_INLINE, encoding="utf-8")
    (dev / "agent_responses" / MART / "RUN-11-i1-builder.md").write_text("**가정**\n- builder 응답\n", encoding="utf-8")
    _, out = make(repo, dev)
    rows = outside_rows(openpyxl.load_workbook(out))
    assert {r[2] for r in rows} == {f".dev/agent_responses/{MART}/RUN-10-i0-verifier.md"}


def test_outside_section_not_found_counts_as_missing(repo, dev):
    verifier_file(dev, 1).write_text("**contract 가정**\n- **C-02:** 가정입니다.\n", encoding="utf-8")
    code, out = make(repo, dev)
    assert code == 0
    wb = openpyxl.load_workbook(out)
    rows = outside_rows(wb)
    assert rows[0][:2] == (utr.KIND_OUTSIDE, utr.NOT_FOUND) and rows[1][:2] == ("contract 가정", "- **C-02:** 가정입니다.")
    assert f"{utr.KIND_OUTSIDE} 절 찾지 못함" in wb["표지"]["B22"].value
    entry = manifest_entry(repo)
    assert entry["missing"] == [f"{utr.OUTSIDE_SHEET}!B5 {utr.KIND_OUTSIDE}"] and entry["missing_fields"] == 1


def test_outside_no_verifier_file_counts_as_missing(repo, dev):
    verifier_file(dev, 1).unlink()
    code, out = make(repo, dev)
    assert code == 0
    rows = outside_rows(openpyxl.load_workbook(out))
    assert [r[:2] for r in rows] == [(utr.KIND_OUTSIDE, utr.NOT_FOUND), (utr.KIND_ASSUMED, utr.NOT_FOUND)]
    assert rows[0][2] == "(verifier 응답 파일 없음)"
    assert manifest_entry(repo)["missing_fields"] == 2


def test_outside_sheet_is_scrubbed(repo, dev):
    _, out = make(repo, dev)
    text = json.dumps(outside_rows(openpyxl.load_workbook(out)), ensure_ascii=False)
    assert PROJECT_ID not in text and "gserviceaccount" not in text
    assert "<프로젝트>:ai_dev.raw_example" in text and "<계정> 계정 기록" in text
