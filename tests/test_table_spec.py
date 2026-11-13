"""scripts/deliverables/table_spec.py 시험 (진행표 4-4 정의서). 임시 git 저장소와 가짜 .dev·contract로 돈다."""
import copy
import json
import subprocess
import sys
from pathlib import Path

import openpyxl
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "deliverables"))
sys.path.insert(0, str(ROOT / "scripts" / "log"))
import devlog  # noqa: E402
import table_spec as ts  # noqa: E402
from config_fixture import write_pii  # noqa: E402
from test_l0_contract import VALID, col  # noqa: E402

MART = "mart_example"
PROJECT_ID = "my-proj-123"
SECRETS = ("987654321", "SECRETVALUE", "Seoul-Gangnam", PROJECT_ID, "ai-builder@", "gserviceaccount")
NOW = "2026-11-02T15:00:00+09:00"
LOADS = ["raw_example", "raw_users", "stg_example", "mart_example_daily"]

# C-01(L3): stg_example.example_id IS NULL을 잡고, LEFT JOIN 쪽 raw_example.example_id IS NULL은 짝 없음 검사
C01 = """-- error_type: null_violation
-- C-01: 키는 고유하다. example_date IS NULL 이라는 주석은 보지 않는다
SELECT 'dup' AS violation, example_id
FROM `{{ project }}.{{ dataset_stg }}.stg_example`
WHERE snapshot_date = DATE('{{ ds }}')
GROUP BY example_id
HAVING COUNT(*) > 1 OR example_id IS NULL
UNION ALL
SELECT 'missing', s.example_id
FROM `{{ project }}.{{ dataset_stg }}.stg_example` AS s
LEFT JOIN `{{ project }}.{{ dataset_raw }}.raw_example` AS r
  ON r.example_id = s.example_id AND r.snapshot_date = s.snapshot_date
WHERE s.snapshot_date = DATE('{{ ds }}') AND r.example_id IS NULL
"""
C02 = """-- C-02: 원천 대비 행 수
WITH m AS (
  SELECT SUM(example_metric) AS v FROM `{{ project }}.{{ dataset_mart }}.mart_example_daily`
  WHERE snapshot_date = DATE('{{ ds }}')
)
SELECT v FROM m WHERE v < 0
"""


def git(root, *args):
    p = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, encoding="utf-8")
    assert p.returncode == 0, p.stderr
    return p.stdout.strip()


def make_contract():
    c = copy.deepcopy(VALID)
    raw, stg, mart = c["tables"]
    raw["name_ko"] = "예시 원천"
    stg["name_ko"] = "예시"
    stg["columns"][0]["name_ko"] = f"예시ID ({PROJECT_ID}.ai_dev 복사, ai-builder@{PROJECT_ID}.iam.gserviceaccount.com)"
    # mart 테이블·컬럼의 name_ko는 비워 둔다 → "미작성" (결정 53)
    users = {"name": "raw_users", "name_ko": "고객 원천", "layer": "raw", "task": "raw_users", "grain": "고객 1명",
             "keys": ["user_id"], "columns": [col("user_id", "INT64"), col("email", "STRING")]}
    c["tables"].insert(1, users)
    c["dag"]["tasks"].insert(1, {"id": "raw_users", "kind": "load", "layer": "raw", "upstream": []})
    c["dag"]["tasks"][2]["upstream"].append("raw_users")
    c["checks"]["invariants"][0]["rule"] = "stg_example의 example_date 집합이 mart_example_daily로 보존된다"
    return c


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "repo"
    req = root / "docs" / "requirements"
    (req / f"{MART}_checks" / "l3").mkdir(parents=True)
    (req / f"{MART}_checks" / "l4").mkdir(parents=True)
    (req / f"{MART}.contract.json").write_text(json.dumps(make_contract(), ensure_ascii=False), encoding="utf-8")
    (req / f"{MART}_checks" / "l3" / "C-01.sql").write_text(C01, encoding="utf-8")
    (req / f"{MART}_checks" / "l4" / "C-02.sql").write_text(C02, encoding="utf-8")  # I-01은 쿼리 없음 → rule 문장
    write_pii(root / "docs" / "architecture" / "pii_columns.md")  # 시험용 목록 (table_spec은 --root의 목록을 읽는다)
    git(root, "init", "-q", "--template=", "-b", "week9/mart-example")
    git(root, "config", "user.email", "t@example.com")
    git(root, "config", "user.name", "t")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "contract")
    return root


def rung(name, metrics=None, error_type=None):
    return {"rung": name, "ds": None if name == "L0" else "2026-11-02", "status": "fail" if error_type else "pass",
            "metrics": metrics or {}, "error_type": error_type, "error_class": "semantic" if error_type else None}


def pass_rungs(task, l3_checks=("C-01",)):
    l2 = {"dataset": "ai_dev", "table": task}
    if task == "raw_example":
        l2["row_count"] = "5"  # L2에 행 수가 있으면 L2를 쓴다
    return [rung("L0", {"stage": "contract"}), rung("L1", {"bytes_processed": 2048}), rung("L2", l2),
            rung("L3", {"checks": list(l3_checks) if task == "stg_example" else []}),
            rung("L4", {"checks": []}), rung("L5", {"row_count": "7", "checks": []})]


def ladder(dev, task, n, rungs, verdict):
    devlog.write_ladder_result(MART, {"task": task, "iteration": n, "contract_version": 1, "request_kind": "new_build",
                                      "modules": {"expert": {"on": [], "version": None}}, "bytes_total": 100,
                                      "rungs": rungs, "verdict": verdict, "halt_reason": None}, dev)


def make_dev(repo, l3_checks=("C-01",)):
    """반복 1 반려(데이터 값이 든 evidence, 프로젝트 ID가 든 메시지) → 반복 2 통과."""
    d = repo / ".dev"
    rows = [{"example_id": 987654321, "name": "SECRETVALUE", "city": "Seoul-Gangnam"}]
    fail = rung("L4", {"check": "C-02", "evidence": rows,
                       "message": f"Not found: Table {PROJECT_ID}:ai_dev.stg_example"}, "join_missing")
    ladder(d, "stg_example", 1, pass_rungs("stg_example")[:4] + [fail], "reject")
    for task in LOADS:
        ladder(d, task, 2, pass_rungs(task, l3_checks), "pass")
    return d


@pytest.fixture
def dev(repo):
    return make_dev(repo)


def make(repo, dev, *extra):
    code = ts.main(["--mart", MART, "--root", str(repo), "--dev-dir", str(dev), "--date", "2026-11-02", *extra],
                   now=NOW)
    return code, repo / "out" / "deliverables" / MART / f"TDS_{MART}_20261102.xlsx"


def grid(ws):
    header = [ws.cell(ts.HEADER_ROW, c).value for c in range(1, ws.max_column + 1)]
    header = [h.removesuffix(" *") if h else h for h in header]
    return [dict(zip(header, (ws.cell(r, c).value for c in range(1, ws.max_column + 1))))
            for r in range(ts.FIRST_ROW, ws.max_row + 1) if ws.cell(r, 1).value]


def columns(wb):
    return {(r["영문 테이블명"], r["영문 컬럼명"]): r for r in grid(wb["컬럼 정보"])}


def manifest(repo):
    m = json.loads((repo / "out" / "deliverables" / MART / "manifest.json").read_text(encoding="utf-8"))
    return next(d for d in m["deliverables"] if d["name"] == "table_spec"), m


def test_sheets_filled(repo, dev):
    code, out = make(repo, dev)
    assert code == 0 and out.exists()
    wb = openpyxl.load_workbook(out)
    assert wb.sheetnames == ["안내", "표지", "테이블 정보", "컬럼 정보"]
    guide = json.dumps([c.value for row in wb["안내"].iter_rows() for c in row], ensure_ascii=False)
    assert "S1" in guide and "S2" in guide and "[별표 4]" in guide and "Not Null 여부" in guide
    cover = {r[0]: r[1] for r in wb["표지"].iter_rows(values_only=True) if r[0]}
    assert cover["정보시스템명"] == "pipeline-harness" and cover["DBMS 정보"] == "BigQuery"
    assert cover["DB명(데이터셋)"].startswith("{{ dataset_raw }}, {{ dataset_stg }}, {{ dataset_mart }}")
    assert cover["테이블 수"] == 4 and cover["contract 버전"] == "v1" and cover["문서 번호"] == f"TDS-{MART}-20261102"
    tables = {r["영문 테이블명"]: r for r in grid(wb["테이블 정보"])}
    assert list(tables) == ["raw_example", "raw_users", "stg_example", "mart_example_daily"]
    raw = tables["raw_example"]
    assert (raw["테이블 소유자"], raw["한글 테이블명"], raw["테이블 유형"], raw["발생주기"]) == \
        ("미지정(결재 후 OM Owner)", "예시 원천", "raw", "daily")
    assert raw["테이블 볼륨"] == "5행 (ds 2026-11-02 파티션, 반복 2 L2)"
    assert tables["stg_example"]["테이블 볼륨"].startswith("7행 (ds 2026-11-02 파티션, 반복 2 L5")
    assert raw["공개/비공개 여부"] == "비공개 (내부 PoC, 합성 데이터)" and raw["개방데이터목록"] == "해당 없음"
    cols = columns(wb)
    sid = cols[("stg_example", "example_id")]
    assert sid["데이터 타입"] == "INT64" and sid["데이터 길이"] == "해당 없음(BigQuery)"
    assert sid["PK 정보"] == "논리 키(BigQuery PK 미강제, 고유성은 사다리 검사로 확인): example_id"
    assert sid["Not Null 여부"] == "예(C-01)" and sid["제약조건"] == "C-01"
    assert sid["FK 정보"].startswith("없음") and sid["암호화 여부"] == "해당 없음(전달 차단)"
    # 주석의 IS NULL은 보지 않고, LEFT JOIN 쪽 IS NULL(짝 없음)은 Not Null 보장이 아니다
    assert cols[("stg_example", "example_date")]["Not Null 여부"] == "미보장"
    assert cols[("raw_example", "example_id")]["Not Null 여부"] == "미보장"
    assert cols[("raw_example", "example_id")]["제약조건"] == "C-01"
    assert cols[("raw_example", "example_id")]["암호화 여부"] == "아니오(합성 데이터)"
    # C-02는 쿼리(CTE)로, I-01은 쿼리가 없어 rule 문장으로 연결
    assert cols[("mart_example_daily", "example_metric")]["제약조건"] == "C-02"
    assert cols[("mart_example_daily", "example_date")]["제약조건"] == "I-01"
    assert cols[("stg_example", "example_date")]["제약조건"] == "I-01"
    assert cols[("mart_example_daily", "example_metric")]["PK 정보"] == "아님"
    assert cols[("mart_example_daily", "example_metric")]["한글 컬럼명"] == "미작성"


def test_not_null_needs_passed_l3_run(repo):
    """L3 게이트 쿼리가 있어도 마지막 통과 반복에서 실행 기록이 없으면 보장으로 보지 않는다."""
    dev = make_dev(repo, l3_checks=())
    _, out = make(repo, dev)
    assert columns(openpyxl.load_workbook(out))[("stg_example", "example_id")]["Not Null 여부"] == "미보장"


def test_pii_column_marked(repo, dev):
    _, out = make(repo, dev)
    cols = columns(openpyxl.load_workbook(out))
    assert cols[("raw_users", "email")]["개인정보 여부"] == "예"
    assert cols[("raw_users", "user_id")]["개인정보 여부"] == "아니오"
    assert cols[("stg_example", "example_id")]["개인정보 여부"] == "아니오"


def test_manifest_counts_missing_and_deferred(repo, dev):
    make(repo, dev)
    entry, _ = manifest(repo)
    # 테이블 4개 × 필수 4칸 + 컬럼 8개 × 필수 8칸
    assert entry["required_fields"] == 4 * 4 + 8 * 8
    assert entry["deferred_fields"] == len(entry["deferred"]) == 4
    assert all("테이블 소유자" in x for x in entry["deferred"])
    # mart의 한글 테이블명 1 + name_ko 없는 컬럼(raw 2, raw_users 2, stg 1, mart 2)
    assert entry["missing_fields"] == len(entry["missing"]) == 1 + 7
    assert "테이블 정보!C8 한글 테이블명 (mart_example_daily)" in entry["missing"]
    assert all("한글" in x for x in entry["missing"])
    assert entry["contract_version"] == 1 and entry["generated_at"] == NOW


def test_manifest_counts_blank_required(repo, dev):
    """원천이 없는 필수 칸(타입 없음)은 지어내지 않고 비운 뒤 missing으로 센다."""
    c = make_contract()
    del c["tables"][0]["columns"][0]["type"]
    (repo / "docs" / "requirements" / f"{MART}.contract.json").write_text(json.dumps(c), encoding="utf-8")
    _, out = make(repo, dev)
    entry, _ = manifest(repo)
    assert "컬럼 정보!E5 데이터 타입 (raw_example)" in entry["missing"]
    assert columns(openpyxl.load_workbook(out))[("raw_example", "example_id")]["데이터 타입"] is None


def test_manifest_keeps_other_deliverables(repo, dev):
    folder = repo / "out" / "deliverables" / MART
    folder.mkdir(parents=True)
    (folder / "manifest.json").write_text(json.dumps({"deliverables": [
        {"name": "unit_test_report", "required_fields": 3}, {"name": "table_spec", "required_fields": -1}],
        "handover": {"fact_fields": 1}}), encoding="utf-8")
    make(repo, dev)
    entry, m = manifest(repo)
    assert [d["name"] for d in m["deliverables"]] == ["unit_test_report", "table_spec"]
    assert m["deliverables"][0] == {"name": "unit_test_report", "required_fields": 3} and "handover" in m
    assert entry["required_fields"] > 0


def test_no_data_values_or_project_id(repo, dev):
    _, out = make(repo, dev)
    wb = openpyxl.load_workbook(out)
    text = json.dumps([[c.value for row in ws.iter_rows() for c in row] for ws in wb.worksheets],
                      ensure_ascii=False, default=str)
    for s in SECRETS:
        assert s not in text, s
    assert "<프로젝트>:ai_dev" in text and "<계정>" in text
    manifest_text = (repo / "out" / "deliverables" / MART / "manifest.json").read_text(encoding="utf-8")
    assert not any(s in manifest_text for s in SECRETS)


def test_stamp_and_check(repo, dev, capsys):
    _, out = make(repo, dev)
    head = git(repo, "rev-parse", "HEAD")
    assert ts.read_stamp(out) == {"contract_version": 1, "생성 시각": NOW, "기준 커밋": head}
    assert ts.main(["--mart", MART, "--root", str(repo), "--check"]) == 0
    (repo / "README.md").write_text("x\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "next")
    capsys.readouterr()
    assert ts.main(["--mart", MART, "--root", str(repo), "--check"]) == 2
    assert "halt input_invalid" in capsys.readouterr().err


def test_check_contract_version_mismatch(repo, dev, capsys):
    _, out = make(repo, dev)
    c = make_contract()
    c["version"] = 2
    (repo / "docs" / "requirements" / f"{MART}.contract.json").write_text(json.dumps(c), encoding="utf-8")
    capsys.readouterr()
    assert ts.main(["--mart", MART, "--root", str(repo), "--check", "--file", str(out)]) == 2
    assert "contract_version 도장 1 ≠ 지금 2" in capsys.readouterr().err


def test_check_without_spec(repo, capsys):
    assert ts.main(["--mart", MART, "--root", str(repo), "--check"]) == 2
    assert "정의서가 없음" in capsys.readouterr().err


def test_check_ignores_unit_test_report(repo, dev, capsys):
    """--check는 TDS 파일만 본다 (같은 폴더의 UTR 결과서와 섞이지 않는다)."""
    folder = repo / "out" / "deliverables" / MART
    folder.mkdir(parents=True)
    (folder / f"UTR_{MART}_20261103.xlsx").write_bytes(b"")
    assert ts.main(["--mart", MART, "--root", str(repo), "--check"]) == 2
    assert "정의서가 없음" in capsys.readouterr().err


def test_no_passed_iteration_is_error(repo, capsys):
    d = repo / ".dev"
    ladder(d, "raw_example", 1, [rung("L0", {"stage": "contract"}), rung("L1", {"message": "x"}, "syntax")], "reject")
    code, out = make(repo, d)
    assert code == 2 and not out.exists() and "통과한 반복이 없음" in capsys.readouterr().err


def test_does_not_overwrite_without_force(repo, dev, capsys):
    assert make(repo, dev)[0] == 0
    capsys.readouterr()
    assert make(repo, dev)[0] == 2 and "덮어쓰지 않는다" in capsys.readouterr().err
    assert make(repo, dev, "--force")[0] == 0
