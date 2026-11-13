"""검증 사다리 L0 ②③·L1~L5·실행기 시험 (3-3). bq·gcloud는 가짜로 바꾸고 BigQuery는 부르지 않는다.

예시 마트(mart_example)는 test_l0_contract의 VALID contract를 쓰고, 임시 폴더에 저장소 구조를 만든다.
"""
import copy
import json
import re
import sys
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "ladder"))
import common  # noqa: E402
import gen_dq  # noqa: E402
import run_ladder  # noqa: E402
from config_fixture import hc, pii_list, prod, src  # noqa: E402,F401 (pii_list는 고정구)
from test_l0_contract import VALID  # noqa: E402

MART = "mart_example"
TODAY = date(2026, 10, 30)
DAG = """from airflow import DAG

UPSTREAM = {
    "raw_example": [],
    "gate_raw_mart_example": ["raw_example"],
    "stg_example": ["gate_raw_mart_example"],
    "gate_stg_mart_example": ["stg_example"],
    "mart_example_daily": ["gate_stg_mart_example"],
    "gate_mart_mart_example": ["mart_example_daily"],
}
"""
LOAD_SQL = """CREATE TABLE IF NOT EXISTS `{{{{ project }}}}.{{{{ dataset_{layer} }}}}.{table}` (snapshot_date DATE);
DELETE FROM `{{{{ project }}}}.{{{{ dataset_{layer} }}}}.{table}` WHERE snapshot_date = DATE('{{{{ ds }}}}');
INSERT INTO `{{{{ project }}}}.{{{{ dataset_{layer} }}}}.{table}` (snapshot_date) SELECT DATE('{{{{ ds }}}}');
"""
CHECKS = {
    "l3/C-01.sql": "-- error_type: duplicate_rows\n-- task: stg_example\nSELECT example_id FROM `{{ project }}.{{ dataset_stg }}.stg_example` GROUP BY 1 HAVING COUNT(*) > 1;\n",
    "l4/C-02.sql": "-- error_type: join_missing\n-- task: stg_example\nSELECT 1 AS c02 FROM `{{ project }}.{{ dataset_stg }}.stg_example` WHERE FALSE\n",
    "l4/I-01.sql": "-- error_type: range_violation\n-- task: mart_example_daily\nSELECT 1 AS i01 FROM `{{ project }}.{{ dataset_mart }}.mart_example_daily` WHERE FALSE\n",
}


def build(root, contract=None, checks=None, dag=DAG):
    contract = copy.deepcopy(contract or VALID)
    req = root / "docs" / "requirements"
    req.mkdir(parents=True, exist_ok=True)
    (req / f"{MART}.contract.json").write_text(json.dumps(contract, ensure_ascii=False), encoding="utf-8")
    for rel, text in (CHECKS if checks is None else checks).items():
        f = req / f"{MART}_checks" / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(text, encoding="utf-8")
    if dag is not None:
        (root / "dags").mkdir(parents=True, exist_ok=True)
        (root / "dags" / "harness_daily.py").write_text(dag, encoding="utf-8")
    for t in contract["tables"]:
        f = root / "dags" / "sql" / t["layer"] / f"{t['task']}.sql"
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(LOAD_SQL.format(layer=t["layer"], table=t["name"]), encoding="utf-8")
    paths = common.Paths(root, MART)
    for path, text in gen_dq.generate(paths, contract).items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
    return paths


class FakeBq:
    """규칙: (mode, 쿼리에 들어 있는 글자, (종료 코드, stdout, stderr)). mode는 dry·run. 먼저 맞는 규칙을 쓴다."""

    def __init__(self, rules=(), account="ai-builder@proj-x.iam.gserviceaccount.com", project="proj-x", impersonated="",
                 location=None):
        self.rules, self.account, self.project, self.calls, self.argv = list(rules), account, project, [], []
        self.impersonated = impersonated
        # ai_dev 리전 조회(bq show) 응답. 기본은 설정의 원천 리전과 같음. 글자면 그 리전, 튜플이면 (종료 코드, stdout, stderr)
        self.location, self.shows = location, []

    def __call__(self, args, env, stdin=None):
        # SQL은 stdin으로 온다. 시험에서 보기 쉽게 calls에는 마지막 칸으로 붙여 남긴다
        self.argv.append(args)
        if args[:2] == ["bq", "show"]:  # 쿼리가 아니므로 calls에 넣지 않는다
            self.shows.append(args)
            if isinstance(self.location, tuple):
                return self.location
            return 0, json.dumps({"location": self.location or hc.load()["source"]["location"]}), ""
        if args[0] == "gcloud":
            self.calls.append(args)
            if args[-1] == "auth/impersonate_service_account":
                return self.impersonated if isinstance(self.impersonated, tuple) else (0, self.impersonated + "\n", "")
            return (0, self.account + "\n", "") if args[1] == "auth" else (0, self.project + "\n", "")
        self.calls.append([*args, stdin])
        sql = stdin or ""
        mode = "dry" if "--dry_run" in args else "run"
        for m, needle, response in self.rules:
            if m == mode and needle in sql:
                return response() if callable(response) else response
        if mode == "dry":
            return 0, json.dumps({"statistics": {"totalBytesProcessed": "1000"}}), ""
        if "row_count" in sql:
            return 0, json.dumps([{"row_count": "1", "checksum": "42"}]), ""
        if "INFORMATION_SCHEMA.TABLES" in sql:  # L2 뒤 contract 테이블 확인
            return 0, json.dumps([{"n": "1"}]), ""
        return 0, "[]", ""


def run(tmp_path, *extra, fake=None, env=None, task=("--all",)):
    fake = fake or FakeBq()
    bq = common.Bq(runner=fake, env={"CLOUDSDK_CONFIG": "C:/cfg"} if env is None else env)
    argv = ["--mart", MART, *task, "--iteration", "1", "--root", str(tmp_path), "--dev-dir",
            str(tmp_path / ".dev"), "--ds", "2026-10-30", *extra]
    code = run_ladder.main(argv, bq=bq, today=TODAY)
    return code, fake


def result(tmp_path, task, sub=""):
    f = tmp_path / ".dev" / sub / "ladder_results" / MART / f"{task}-v1-1.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None


def last_rung(tmp_path, task):
    return result(tmp_path, task)["rungs"][-1]


def input_halt(tmp_path, task, fragment):
    """verifier·사람·하네스 파일 문제: 반려가 아니라 halt input_invalid (결정 59 판정 원칙)."""
    r = result(tmp_path, task)
    assert r["verdict"] == "halt" and r["halt_reason"] == "input_invalid", r
    assert r["halt_detail"]["exception"] == "InputInvalid" and fragment in r["halt_detail"]["message"], r["halt_detail"]
    assert all(g["status"] == "pass" for g in r["rungs"])
    return r


# ---------- 전체 통과 ----------

def test_all_pass(tmp_path, capsys):
    build(tmp_path)
    code, fake = run(tmp_path)
    assert code == 0
    for task in ("raw_example", "stg_example", "mart_example_daily"):
        r = result(tmp_path, task)
        assert r["verdict"] == "pass" and r["request_kind"] == "new_build"
        assert [g["rung"] for g in r["rungs"]] == ["L0", "L1", "L2", "L3", "L4", "L5"]
        assert r["rungs"][0]["ds"] is None and all(g["ds"] == "2026-10-30" for g in r["rungs"][1:])
        assert r["bytes_total"] > 0
    assert result(tmp_path, "stg_example")["rungs"][4]["metrics"]["checks"] == ["C-02"]
    summary = json.loads(capsys.readouterr().out)
    assert [t["verdict"] for t in summary["tasks"]] == ["pass"] * 3


def test_every_query_dry_run_first_and_capped(tmp_path):
    build(tmp_path)
    _, fake = run(tmp_path)
    bq_calls = [a for a in fake.calls if a[0] == "bq"]
    runs = [a for a in bq_calls if "--dry_run" not in a]
    # dry-run에도 본 실행에도 상한을 건다 (CLAUDE.md §4)
    assert runs and all(f"--maximum_bytes_billed={common.MAX_BYTES}" in a for a in bq_calls)
    for i, a in enumerate(bq_calls):
        if "--dry_run" not in a:
            assert any("--dry_run" in b and b[-1] == a[-1] for b in bq_calls[:i]), a[-1][:60]
    # ai_dev로 렌더링되고 자리 표시가 남지 않는다
    assert all("{{" not in a[-1] and "proj-x.ai_dev." in a[-1] for a in bq_calls)


def test_single_task(tmp_path):
    build(tmp_path)
    code, _ = run(tmp_path, task=("--task", "stg_example"))
    assert code == 0 and result(tmp_path, "stg_example") and result(tmp_path, "raw_example") is None


# ---------- L0 ②③ ----------

@pytest.mark.parametrize("change,error_type,message", [
    (lambda root: (root / "dags" / "harness_daily.py").unlink(), "dag_import_error", "DAG 파일이 없음"),
    (lambda root: (root / "dags" / "harness_daily.py").write_text("UPSTREAM = {", encoding="utf-8"),
     "dag_import_error", "문법 오류"),
    (lambda root: (root / "dags" / "harness_daily.py").write_bytes(DAG.encode("utf-8") + "# 메모\n".encode("cp949")),
     "dag_import_error", "UTF-8로 읽지 못함"),
    (lambda root: (root / "dags" / "harness_daily.py").write_text(DAG.replace('"gate_stg_mart_example": ["stg_example"]', '"gate_stg_mart_example": []'), encoding="utf-8"),
     "dag_structure_mismatch", "gate_stg_mart_example의 상류가 다름"),
    (lambda root: (root / "dags" / "harness_daily.py").write_text(DAG.replace("UPSTREAM", "TASKS"), encoding="utf-8"),
     "dag_structure_mismatch", "UPSTREAM이 없음"),
    (lambda root: (root / "dags" / "harness_daily.py").write_text("UPSTREAM = dict(a=[])\n", encoding="utf-8"),
     "dag_structure_mismatch", "리터럴"),
    (lambda root: (root / "dags" / "sql" / "stg" / "stg_orphan.sql").write_text("SELECT 1", encoding="utf-8"),
     "dag_structure_mismatch", "고아 SQL"),
    (lambda root: (root / "dags" / "sql" / "mart" / "mart_example_daily.sql").unlink(),
     "dag_structure_mismatch", "SQL 파일이 없음"),
])
def test_l0_dag_structure(tmp_path, change, error_type, message):
    build(tmp_path)
    change(tmp_path)
    code, fake = run(tmp_path)
    assert code == 1
    r = result(tmp_path, "raw_example")
    assert [g["rung"] for g in r["rungs"]] == ["L0"] and r["rungs"][0]["error_type"] == error_type
    assert any(message in e for e in r["rungs"][0]["metrics"]["errors"])
    # L0 실패는 첫 task 파일 1개만 남기고 bq를 부르지 않는다
    assert result(tmp_path, "stg_example") is None and fake.calls == []


@pytest.mark.parametrize("rel,text,message", [
    ("l4/C-02.sql", "-- error_type: join_missing\n-- task: stg_example\n-- owner: verifier\nSELECT 1", "모르는 머리말 키"),
    ("l4/C-02.sql", "-- error_type: join_missing\n-- error_type: duplicate_rows\n-- task: stg_example\nSELECT 1", "중복"),
    ("l4/C-02.sql", "-- error_type: wrong_rows\n-- task: stg_example\nSELECT 1", "ERROR_TYPES"),
    ("l4/C-02.sql", "-- Error_Type: join_missing\n-- task: stg_example\nSELECT 1", "모르는 머리말 키"),
    ("l4/C-02.sql", "-- task: stg_example\nSELECT 1", "머리말 키 없음"),
    ("l4/C-02.sql", "-- 원천 대비 행 수\n-- error_type: join_missing\n-- task: stg_example\nSELECT 1", "형식"),
    ("l4/C-02.sql", "-- error_type: join_missing\n-- task: gate_stg_mart_example\nSELECT 1", "load task가 아님"),
    ("l4/C-02.sql", "-- error_type: join_missing\n-- task: stg_example\nSELECT 1; SELECT 2", "SELECT 문 1개"),
    ("l5/C-02.sql", "-- error_type: join_missing\n-- task: stg_example\nSELECT 1", "rung은 L4"),
    ("l4/C-99.sql", "-- error_type: join_missing\n-- task: stg_example\nSELECT 1", "없는 id"),
])
def test_l0_check_headers(tmp_path, rel, text, message):
    checks = dict(CHECKS)
    checks.pop("l4/C-02.sql")
    checks[rel] = text
    build(tmp_path, checks=checks)
    code, fake = run(tmp_path)
    assert code == 2 and input_halt(tmp_path, "raw_example", message)["rungs"] == []
    assert fake.calls == [] and result(tmp_path, "stg_example") is None


def test_l0_missing_check_file(tmp_path):
    checks = dict(CHECKS)
    checks.pop("l4/I-01.sql")
    build(tmp_path, checks=checks)
    assert run(tmp_path)[0] == 2
    input_halt(tmp_path, "raw_example", "I-01")


def test_l0_non_utf8_check_file_halts(tmp_path):
    build(tmp_path)
    f = tmp_path / "docs" / "requirements" / f"{MART}_checks" / "l4" / "C-02.sql"
    f.write_bytes(f.read_bytes() + "-- 메모\n".encode("cp949"))
    assert run(tmp_path)[0] == 2
    input_halt(tmp_path, "raw_example", "utf-8")


def test_l0_contract_invalid_halts(tmp_path):
    c = copy.deepcopy(VALID)
    del c["traces_to"]
    build(tmp_path, contract=c)
    code, fake = run(tmp_path)
    assert code == 2 and input_halt(tmp_path, "raw_example", "traces_to")["rungs"] == [] and fake.calls == []


def test_l0_contract_pii_column_halts(tmp_path, pii_list):
    c = copy.deepcopy(VALID)
    stg = next(t for t in c["tables"] if t["layer"] == "stg")
    stg["columns"].append({**stg["columns"][0], "name": "email"})
    build(tmp_path, contract=c)
    assert run(tmp_path)[0] == 2
    input_halt(tmp_path, "raw_example", "email")


@pytest.mark.parametrize("reviewed, fragment", [(None, "줄이 하나 있어야 함"), ("other-proj.other_ds", "설정의 원천")])
def test_pii_reviewed_source_problem_halts_not_rejection(tmp_path, monkeypatch, reviewed, fragment):
    """pii_columns.md는 사람 파일이라 "검토한 원천" 줄이 없거나 설정과 다르면 반려가 아니라 halt (결정 59)."""
    build(tmp_path)
    line = "" if reviewed is None else f"검토한 원천: `{reviewed}`\n\n"
    pii = tmp_path / "pii_columns.md"
    pii.write_text(f"# 목록\n\n{line}| `users` | `email` | 이메일 |\n", encoding="utf-8")
    monkeypatch.setattr(run_ladder.l0_contract, "PII_FILE", pii)
    monkeypatch.setattr(run_ladder.l0_contract.load_pii, "__defaults__", (pii,))
    code, fake = run(tmp_path)
    assert code == 2 and fake.calls == []
    r = result(tmp_path, "raw_example")
    assert r["verdict"] == "halt" and r["halt_reason"] == "input_invalid" and r["rungs"] == []
    assert "pii_columns.md" in r["halt_detail"]["message"] and fragment in r["halt_detail"]["message"]


def test_l0_builder_sql_pii_is_rejection(tmp_path, pii_list):
    build(tmp_path)
    f = tmp_path / "dags" / "sql" / "stg" / "stg_example.sql"
    f.write_text(f.read_text(encoding="utf-8") + "SELECT id, email FROM {{ dataset_raw }}.raw_users;\n", encoding="utf-8")
    code, _ = run(tmp_path)
    r = last_rung(tmp_path, "raw_example")
    assert code == 1 and r["rung"] == "L0" and r["error_type"] == "pii_column"


@pytest.mark.parametrize("change,message", [
    (lambda root: (root / "dags" / "sql" / "dq" / "gate_stg_mart_example.sql").unlink(), "SQL 파일이 없음"),
    (lambda root: (root / "dags" / "sql" / "dq" / "gate_extra.sql").write_text("SELECT 1", encoding="utf-8"), "고아 SQL"),
])
def test_l0_dq_folder_problem_halts(tmp_path, change, message):
    build(tmp_path)
    change(tmp_path)
    assert run(tmp_path)[0] == 2
    input_halt(tmp_path, "raw_example", message)


def test_l0_task_id_in_two_contracts_halts(tmp_path):
    build(tmp_path)
    other = {"mart": "mart_other", "dag": {"tasks": [{"id": "raw_example", "kind": "load", "layer": "raw", "upstream": []}]}}
    (tmp_path / "docs" / "requirements" / "mart_other.contract.json").write_text(json.dumps(other), encoding="utf-8")
    assert run(tmp_path)[0] == 2
    input_halt(tmp_path, "raw_example", "여러 contract")


def test_header_with_comment_after_blank_line_ok():
    header, body = common.parse_check("-- error_type: null_violation\n-- task: t\n\n-- 설명 주석\nSELECT 1;\n")
    assert header == {"error_type": "null_violation", "task": "t"} and body.endswith("SELECT 1")


# ---------- L1 ----------

def test_l1_syntax_stops_everything(tmp_path, capsys):
    build(tmp_path)
    fake = FakeBq([("dry", "stg_example` (snapshot_date", (1, "", "Syntax error: Unexpected keyword at [1:2]"))])
    code, _ = run(tmp_path, fake=fake)
    assert code == 1
    assert result(tmp_path, "raw_example") is None  # 층 단위 실행: L1~L3만 통과하고 멈춤 (L4·L5 전)
    r = result(tmp_path, "stg_example")
    assert r["verdict"] == "reject" and r["rungs"][-1]["rung"] == "L1"
    assert (r["rungs"][-1]["error_type"], r["rungs"][-1]["error_class"]) == ("syntax", "syntax")
    assert [(i["task"], i["passed_rungs"]) for i in r["interrupted_tasks"]] == [("raw_example", ["L0", "L1", "L2", "L3"])]
    assert result(tmp_path, "mart_example_daily") is None
    tasks = json.loads(capsys.readouterr().out)["tasks"]
    assert tasks[0] == {"task": "raw_example", "verdict": "중단", "passed_rungs": ["L0", "L1", "L2", "L3"]}
    assert tasks[-1] == {"task": "mart_example_daily", "verdict": "실행 안 함"}


@pytest.mark.parametrize("layer,task", [("raw", "raw_example"), ("stg", "stg_example"), ("mart", "mart_example_daily")])
def test_l1_non_utf8_builder_sql_is_rejection(tmp_path, layer, task):
    # builder가 쓴 SQL의 인코딩 문제는 반려(syntax). L0 PII 검사(stg·mart)도 예외 없이 지나가야 한다
    build(tmp_path)
    f = tmp_path / "dags" / "sql" / layer / f"{task}.sql"
    f.write_bytes(f.read_bytes() + "-- 메모\n".encode("cp949"))
    code, fake = run(tmp_path)
    r = result(tmp_path, task)
    assert code == 1 and r["verdict"] == "reject" and r["halt_reason"] is None and "halt_detail" not in r
    assert r["rungs"][-1]["rung"] == "L1" and r["rungs"][-1]["error_type"] == "syntax"
    assert "UTF-8" in r["rungs"][-1]["metrics"]["message"]
    assert not any(f"{task}`" in (c[-1] or "") for c in fake.calls if c[0] == "bq")  # dry-run 없이 반려


def test_l1_cost_exceeded(tmp_path):
    build(tmp_path)
    big = (0, json.dumps({"statistics": {"totalBytesProcessed": str(common.MAX_BYTES + 1)}}), "")
    code, fake = run(tmp_path, fake=FakeBq([("dry", "raw_example` (snapshot_date", big)]))
    assert code == 1 and last_rung(tmp_path, "raw_example")["error_type"] == "cost_exceeded"
    assert not any(a[0] == "bq" and "--dry_run" not in a for a in fake.calls)


@pytest.mark.parametrize("message", [
    "Not found: Table proj-x:ai_dev.raw_example was not found in location US",      # 자기 테이블도 예외 없음
    "Not found: Table proj-x.ai_dev.raw_example was not found in location US",
    "Not found: Table proj-x:ai_dev.raw_other was not found in location US",
    "Not found: Dataset proj-x:ai_dev was not found in location US",
])
def test_l1_not_found_is_syntax(tmp_path, message):
    # 여러 문장 dry-run은 앞 문장의 CREATE를 인식하므로 "테이블 없음" 통과 예외를 두지 않는다 (결정 59 ⑨)
    build(tmp_path)
    code, _ = run(tmp_path, fake=FakeBq([("dry", "raw_example` (snapshot_date", (1, "", message))]))
    r = last_rung(tmp_path, "raw_example")
    assert code == 1 and r["rung"] == "L1" and r["error_type"] == "syntax"


def test_l1_records_bytes_accuracy(tmp_path):
    build(tmp_path)
    stats = {"statistics": {"totalBytesProcessed": "0",
                            "query": {"totalBytesProcessed": "0", "totalBytesProcessedAccuracy": "LOWER_BOUND"}}}
    code, _ = run(tmp_path, fake=FakeBq([("dry", "raw_example` (snapshot_date", (0, json.dumps(stats), ""))]),
                  task=("--task", "raw_example"))
    l1 = result(tmp_path, "raw_example")["rungs"][1]
    assert code == 0 and l1["metrics"] == {"bytes_processed": 0, "bytes_accuracy": "LOWER_BOUND"}


# ---------- SQL은 stdin으로 (3-3 스모크 1차: bq.CMD가 인수의 첫 줄만 전달) ----------

def test_sql_goes_through_stdin_not_argv(tmp_path):
    build(tmp_path)
    _, fake = run(tmp_path)
    bq_argv = [a for a in fake.argv if a[0] == "bq"]
    assert bq_argv and all("\n" not in x and "\r" not in x for a in bq_argv for x in a)
    sent = [c[-1] for c in fake.calls if c[0] == "bq"]
    assert all(s.count("\n") >= 2 for s in sent if "INSERT INTO" in s)  # 여러 줄 SQL이 통째로 감


def test_newline_in_argument_refused():
    bq = common.Bq(runner=FakeBq(), env={})
    with pytest.raises(common.InfraError, match="줄바꿈"):
        bq.call(["bq", "query", "SELECT 1\nFROM t"])


@pytest.mark.skipif(sys.platform != "win32", reason="Windows 배치 파일(.CMD) 동작 시험")
def test_multiline_sql_survives_cmd_wrapper(tmp_path, monkeypatch):
    # 실제 bq처럼 .CMD를 거쳐도 여러 줄 SQL 전체가 전달되는지 본다 (BigQuery는 부르지 않음)
    import os
    fake_dir = tmp_path / "bin"
    fake_dir.mkdir()
    (fake_dir / "bq.cmd").write_text(
        '@python -c "import sys, json; d = sys.stdin.read(); '
        "print(json.dumps({'statistics': {'totalBytesProcessed': str(len(d))}}))\"\r\n", encoding="utf-8")
    monkeypatch.setenv("PATH", str(fake_dir) + os.pathsep + os.environ["PATH"])
    sql = "CREATE TABLE IF NOT EXISTS `p.ai_dev.t`\n(\n  snapshot_date DATE\n);\nDELETE FROM `p.ai_dev.t` WHERE TRUE;"
    assert common.Bq(env=dict(os.environ)).dry_run(sql) == len(sql)


def test_l1_undefined_placeholder(tmp_path):
    build(tmp_path)
    f = tmp_path / "dags" / "sql" / "raw" / "raw_example.sql"
    f.write_text(f.read_text(encoding="utf-8") + "-- {{ dataset_ods }}\n", encoding="utf-8")
    code, _ = run(tmp_path)
    r = last_rung(tmp_path, "raw_example")
    assert code == 1 and r["rung"] == "L1" and r["error_type"] == "syntax" and "렌더링" in r["metrics"]["message"]


# ---------- L2 ----------

@pytest.mark.parametrize("layer,upper", [("mart", False), ("raw", True), ("stg", False)])
def test_l1_hardcoded_dataset_static(tmp_path, layer, upper):
    # 렌더링 전 원문을 검사하고 bq를 부르지 않는다. 대문자도 막는다
    name = prod(layer).upper() if upper else prod(layer)
    build(tmp_path)
    f = tmp_path / "dags" / "sql" / "raw" / "raw_example.sql"
    f.write_text(f.read_text(encoding="utf-8").replace("{{ dataset_raw }}", name, 1), encoding="utf-8")
    code, fake = run(tmp_path)
    r = last_rung(tmp_path, "raw_example")
    assert code == 1 and r["rung"] == "L1"
    assert (r["error_type"], r["error_class"]) == ("hardcoded_dataset", "semantic")
    assert not any(a[0] == "bq" for a in fake.calls)


def test_l1_source_dataset_allowed(tmp_path):
    build(tmp_path)
    f = tmp_path / "dags" / "sql" / "raw" / "raw_example.sql"
    f.write_text(f.read_text(encoding="utf-8") + f"-- {src('orders')}\n", encoding="utf-8")
    assert run(tmp_path, task=("--task", "raw_example"))[0] == 0


def test_l2_prod_dataset_backstop(tmp_path):
    # L1을 건너뛴 경우에도 L2가 렌더링 결과를 보고 실행하지 않는다
    import l2_run
    paths = build(tmp_path)
    f = tmp_path / "dags" / "sql" / "raw" / "raw_example.sql"
    f.write_text(f.read_text(encoding="utf-8") + f"-- {prod('mart')}\n", encoding="utf-8")
    fake = FakeBq()
    ctx = run_ladder.Ctx(paths, VALID, TODAY, common.Bq(runner=fake, env={}), "proj-x")
    r = l2_run.run(ctx, next(t for t in VALID["dag"]["tasks"] if t["id"] == "raw_example"))
    assert r["error_type"] == "runtime_error" and prod("mart") in r["metrics"]["message"] and fake.calls == []


@pytest.mark.parametrize("err,error_type", [
    ("Query error: Value has type STRING which cannot be inserted into column x, which has type INT64", "type_mismatch"),
    ("Query error: Division by zero", "runtime_error"),
    ("Query exceeded limit for bytes billed: 524288000", "cost_exceeded"),
])
def test_l2_errors(tmp_path, err, error_type):
    build(tmp_path)
    code, _ = run(tmp_path, fake=FakeBq([("run", "raw_example` (snapshot_date", (1, err, ""))]))
    r = last_rung(tmp_path, "raw_example")
    assert code == 1 and r["rung"] == "L2" and r["error_type"] == error_type


# ---------- L3 ----------

def test_l3_gate_file_changed_by_hand(tmp_path):
    paths = build(tmp_path)
    gate = tmp_path / "dags" / "sql" / "dq" / "gate_stg_mart_example.sql"
    gate.write_text(gate.read_text(encoding="utf-8") + "\n-- 손으로 고침\n", encoding="utf-8")
    code, _ = run(tmp_path)
    r = input_halt(tmp_path, "stg_example", "gate_stg_mart_example")
    assert code == 2 and [g["rung"] for g in r["rungs"]] == ["L0", "L1", "L2"]


def test_l3_gate_crlf_only_difference_passes(tmp_path):
    build(tmp_path)
    gate = tmp_path / "dags" / "sql" / "dq" / "gate_stg_mart_example.sql"
    gate.write_bytes(gate.read_bytes().replace(b"\n", b"\r\n"))
    assert run(tmp_path)[0] == 0


CP949_TAIL = "\n-- 손으로 고침\n".encode("cp949")  # PowerShell 5.1 Add-Content의 기본 인코딩 (3-3 스모크 2차)


def test_l3_gate_with_cp949_tail_is_mismatch_not_crash(tmp_path):
    # 3-3 스모크 4단계: builder는 dq/에 쓸 수 없으므로(결정 60) 불일치는 반려가 아니라 halt
    build(tmp_path)
    gate = tmp_path / "dags" / "sql" / "dq" / "gate_stg_mart_example.sql"
    gate.write_bytes(gate.read_bytes() + CP949_TAIL)
    code, _ = run(tmp_path)
    r = input_halt(tmp_path, "stg_example", "다름")
    assert code == 2 and [g["rung"] for g in r["rungs"]] == ["L0", "L1", "L2"]
    assert result(tmp_path, "raw_example") is None and result(tmp_path, "mart_example_daily") is None
    assert r["interrupted_tasks"][0]["task"] == "raw_example"  # halt 파일에도 남는다


def test_gen_dq_overwrites_cp949_gate(tmp_path, capsys):
    build(tmp_path)
    gate = tmp_path / "dags" / "sql" / "dq" / "gate_stg_mart_example.sql"
    clean = gate.read_bytes()
    gate.write_bytes(clean + CP949_TAIL)
    args = ["--mart", MART, "--root", str(tmp_path)]
    assert gen_dq.main(args + ["--check"]) == 1
    assert gen_dq.main(args) == 0 and gate.read_bytes() == clean
    assert gen_dq.main(args + ["--check"]) == 0


def test_l3_violation_rows_become_evidence(tmp_path):
    build(tmp_path)
    rows = json.dumps([{"example_id": i} for i in range(6)])
    code, _ = run(tmp_path, fake=FakeBq([("run", "HAVING COUNT(*) > 1", (0, rows, ""))]))
    r = last_rung(tmp_path, "stg_example")
    assert code == 1 and r["rung"] == "L3" and r["error_type"] == "duplicate_rows" and r["error_class"] == "semantic"
    assert r["metrics"]["check"] == "C-01" and len(r["metrics"]["evidence"]) == 5


def test_check_query_undefined_placeholder_halts(tmp_path):
    checks = dict(CHECKS)
    checks["l4/C-02.sql"] = checks["l4/C-02.sql"].replace("{{ dataset_stg }}", "{{ dataset_x }}")
    build(tmp_path, checks=checks)
    code, _ = run(tmp_path)
    r = input_halt(tmp_path, "stg_example", "l4/C-02.sql")
    assert code == 2 and r["rungs"][-1]["rung"] == "L3"


# ---------- L4·L5 ----------

def test_l4_violation(tmp_path):
    build(tmp_path)
    code, _ = run(tmp_path, fake=FakeBq([("run", "c02", (0, json.dumps([{"c02": 1}]), ""))]))
    r = last_rung(tmp_path, "stg_example")
    assert code == 1 and r["rung"] == "L4" and r["error_type"] == "join_missing"


def test_l5_idempotency_break(tmp_path):
    build(tmp_path)
    counts = iter(["1", "2"])
    snap = lambda: (0, json.dumps([{"row_count": next(counts), "checksum": "42"}]), "")  # noqa: E731
    code, _ = run(tmp_path, fake=FakeBq([("run", "row_count", snap)]), task=("--task", "raw_example"))
    r = last_rung(tmp_path, "raw_example")
    assert code == 1 and r["rung"] == "L5" and r["error_type"] == "idempotency_break"
    assert r["metrics"]["first"]["row_count"] == "1" and r["metrics"]["second"]["row_count"] == "2"
    assert r["metrics"]["message"] == "같은 ds로 2번 실행한 결과가 다름 (행 수 1 → 2, 체크섬 같음)"


def test_l5_checksum_only_break_message_has_counts_not_checksums(tmp_path):
    build(tmp_path)
    sums = iter(["-9100", "7300"])
    snap = lambda: (0, json.dumps([{"row_count": "1234", "checksum": next(sums)}]), "")  # noqa: E731
    code, _ = run(tmp_path, fake=FakeBq([("run", "row_count", snap)]), task=("--task", "raw_example"))
    r = last_rung(tmp_path, "raw_example")
    assert code == 1 and r["rung"] == "L5" and r["error_type"] == "idempotency_break"
    assert r["metrics"]["message"] == "같은 ds로 2번 실행한 결과가 다름 (행 수 1,234 → 1,234, 체크섬 다름)"
    assert "-9100" not in r["metrics"]["message"] and "7300" not in r["metrics"]["message"]


def test_l5_reruns_task_sql(tmp_path):
    build(tmp_path)
    _, fake = run(tmp_path, task=("--task", "raw_example"))
    load_runs = [a for a in fake.calls if a[0] == "bq" and "--dry_run" not in a and "INSERT INTO" in a[-1]]
    assert len(load_runs) == 2  # L2 1번 + L5 재실행 1번


class SnapBq:
    """snapshot()이 보낸 SQL을 남기는 가짜 bq."""

    def __init__(self):
        self.sent = []

    def dry_run(self, sql):
        self.sent.append(("dry", sql))

    def run(self, sql, max_rows=None):
        self.sent.append(("run", sql))
        return [{"row_count": "3", "checksum": "7"}]


@pytest.mark.parametrize("contract,col", [
    ({}, "snapshot_date"),
    ({"load": {"mode": "incremental", "date_column": "created_at", "partition_column": "order_date"}}, "order_date"),
])
def test_l5_snapshot_uses_snapshot_sql(contract, col):
    import types
    import l5_idem
    ctx = types.SimpleNamespace(project="proj-x", contract=contract, ds=date(2026, 10, 30), bq=SnapBq())
    assert l5_idem.snapshot(ctx, "raw_example") == {"row_count": "3", "checksum": "7"}
    want = l5_idem.snapshot_sql("proj-x", common.DEV_DATASET, "raw_example", col, date(2026, 10, 30))
    assert ctx.bq.sent == [("dry", want), ("run", want)]
    assert want == ("SELECT COUNT(*) AS row_count, BIT_XOR(FARM_FINGERPRINT(TO_JSON_STRING(t))) AS checksum\n"
                    f"FROM `proj-x.{common.DEV_DATASET}.raw_example` AS t\n"
                    f"WHERE {col} = DATE('2026-10-30')")  # 함수로 빼기 전과 같은 문장
    shown = l5_idem.snapshot_sql("{{ project }}", common.DEV_DATASET, "raw_example", col, "{{ ds }}")
    assert "proj-x" not in shown and "`{{ project }}." in shown and "DATE('{{ ds }}')" in shown


# ---------- 인프라 오류·인증 ----------

@pytest.mark.parametrize("err,halt_reason", [
    ("Could not connect with BigQuery server", "infra_error"),
    ("Access Denied: Table proj-x:ai_dev.raw_example: User does not have permission", "builder_blocked"),
])
def test_infra_error_halts(tmp_path, err, halt_reason):
    build(tmp_path)
    code, _ = run(tmp_path, fake=FakeBq([("run", "raw_example` (snapshot_date", (1, err, ""))]))
    r = result(tmp_path, "raw_example")
    assert code == 2 and r["verdict"] == "halt" and r["halt_reason"] == halt_reason
    assert [g["rung"] for g in r["rungs"]] == ["L0", "L1"]


def test_infra_error_halt_records_detail(tmp_path):
    build(tmp_path)
    run(tmp_path, fake=FakeBq([("run", "raw_example` (snapshot_date", (1, "Could not connect", ""))]))
    d = result(tmp_path, "raw_example")["halt_detail"]
    assert d["exception"] == "InfraError" and "Could not connect" in d["message"]


def test_unhandled_exception_in_rung_halts_with_exit_2(tmp_path, monkeypatch, capsys):
    build(tmp_path)

    def boom(ctx, task):
        raise UnicodeDecodeError("utf-8", b"\xbc", 0, 1, "invalid start byte")
    monkeypatch.setattr(run_ladder, "RUNGS", (("L1", run_ladder.l1_dryrun), ("L2", run_ladder.l2_run),
                                              ("L3", type("M", (), {"run": staticmethod(boom)}))))
    code, _ = run(tmp_path)
    r = result(tmp_path, "raw_example")
    assert code == 2 and r["verdict"] == "halt" and r["halt_reason"] == "infra_error"
    assert [g["rung"] for g in r["rungs"]] == ["L0", "L1", "L2"] and all(g["status"] == "pass" for g in r["rungs"])
    assert r["halt_detail"]["exception"] == "UnicodeDecodeError" and "0xbc" in r["halt_detail"]["message"]
    assert result(tmp_path, "stg_example") is None
    out = json.loads(capsys.readouterr().out)
    assert out["tasks"][0]["exception"] == "UnicodeDecodeError"
    assert [t["verdict"] for t in out["tasks"]] == ["halt", "실행 안 함", "실행 안 함"]


def test_unhandled_exception_in_l0_halts_with_exit_2(tmp_path, monkeypatch):
    build(tmp_path)

    def boom(paths, contract):
        raise KeyError("upstream")
    monkeypatch.setattr(run_ladder, "run_l0", boom)
    code, fake = run(tmp_path)
    r = result(tmp_path, "raw_example")
    assert code == 2 and r["verdict"] == "halt" and r["halt_reason"] == "infra_error" and r["rungs"] == []
    assert r["halt_detail"]["exception"] == "KeyError" and fake.calls == []


def test_unhandled_exception_before_start_exit_2(tmp_path, monkeypatch, capsys):
    build(tmp_path)

    def boom(contract, args):
        raise KeyError("dag")
    monkeypatch.setattr(run_ladder, "select_tasks", boom)
    assert run(tmp_path)[0] == 2
    assert "KeyError" in capsys.readouterr().err and not (tmp_path / ".dev").exists()


def test_no_cloudsdk_config(tmp_path):
    build(tmp_path)
    code, fake = run(tmp_path, env={})
    r = result(tmp_path, "raw_example")
    assert code == 2 and r["verdict"] == "halt" and r["halt_reason"] == "infra_error"
    assert [g["rung"] for g in r["rungs"]] == ["L0"] and fake.calls == []


def test_wrong_account(tmp_path):
    build(tmp_path)
    code, fake = run(tmp_path, fake=FakeBq(account="someone@example.com"))
    assert code == 2 and result(tmp_path, "raw_example")["halt_reason"] == "infra_error"
    assert all(a[0] == "gcloud" for a in fake.calls)


# 가장(impersonation) 인식 (4-19). 프로젝트와 사람 계정은 가짜다
BUILDER_KEY = "ai-builder@proj-x.iam.gserviceaccount.com"
PERSON = "someone@example.com"


@pytest.mark.parametrize("account, impersonated", [
    (PERSON, BUILDER_KEY),  # 사람 계정 + ai-builder 가장
    (BUILDER_KEY, ""),  # 기존 ai-builder 키 설정
    (BUILDER_KEY, "(unset)"),  # gcloud 판에 따라 stdout에 나오는 값
    (BUILDER_KEY, BUILDER_KEY),
])
def test_check_auth_accepts(account, impersonated):
    fake = FakeBq(account=account, impersonated=impersonated)
    assert common.Bq(runner=fake, env={"CLOUDSDK_CONFIG": "C:/cfg"}).check_auth() == "proj-x"


@pytest.mark.parametrize("account, impersonated", [
    (PERSON, "other-sa@proj-x.iam.gserviceaccount.com"),  # 다른 서비스 계정 가장
    (BUILDER_KEY, "other-sa@proj-x.iam.gserviceaccount.com"),  # 키가 ai-builder여도 실제 신원은 가장 대상
    (PERSON, ""),  # 가장 없는 사람 계정
    (PERSON, "(unset)"),
    ("", BUILDER_KEY),  # 로그인 없음
    ("", ""),
])
def test_check_auth_refuses(account, impersonated):
    fake = FakeBq(account=account, impersonated=impersonated)
    with pytest.raises(common.InfraError, match="ai-builder가 아님"):
        common.Bq(runner=fake, env={"CLOUDSDK_CONFIG": "C:/cfg"}).check_auth()


def test_check_auth_refuses_when_impersonation_unreadable():
    fake = FakeBq(impersonated=(1, "", "gcloud error"))
    with pytest.raises(common.InfraError, match="읽지 못함"):
        common.Bq(runner=fake, env={"CLOUDSDK_CONFIG": "C:/cfg"}).check_auth()


def test_impersonation_still_needs_cloudsdk_config():
    fake = FakeBq(account=PERSON, impersonated=BUILDER_KEY)
    with pytest.raises(common.InfraError, match="CLOUDSDK_CONFIG"):
        common.Bq(runner=fake, env={}).check_auth()
    assert fake.calls == []


# ---------- ai_dev 리전 사전 검사 ----------

def other_location():
    return "EU" if hc.load()["source"]["location"].casefold() != "eu" else "US"


def test_location_checked_once_before_first_query(tmp_path):
    build(tmp_path)
    code, fake = run(tmp_path)
    assert code == 0
    assert fake.shows == [["bq", "show", "--format=json", "proj-x:ai_dev"]]
    first_bq = next(i for i, a in enumerate(fake.argv) if a[0] == "bq")
    assert fake.argv[first_bq][:2] == ["bq", "show"]  # 첫 bq 호출이 리전 조회
    assert all(a[:2] != ["bq", "show"] for a in fake.argv[first_bq + 1:])


def test_location_compare_ignores_case(tmp_path):
    build(tmp_path)
    code, fake = run(tmp_path, fake=FakeBq(location=hc.load()["source"]["location"].swapcase()))
    assert code == 0 and len(fake.shows) == 1


def test_location_mismatch_halts_before_queries(tmp_path):
    build(tmp_path)
    want, got = hc.load()["source"]["location"], other_location()
    code, fake = run(tmp_path, fake=FakeBq(location=got))
    assert code == 2
    r = result(tmp_path, "raw_example")
    assert r["verdict"] == "halt" and r["halt_reason"] == "input_invalid"
    assert r["halt_detail"]["exception"] == "InputInvalid"
    message = r["halt_detail"]["message"]
    assert want in message and got in message and "ai_dev를 원천과 같은 리전에 만들 것" in message
    assert "proj-x" not in message
    assert [g["rung"] for g in r["rungs"]] == ["L0"] and r["rungs"][0]["status"] == "pass"
    assert fake.calls == [a for a in fake.calls if a[0] == "gcloud"]  # 쿼리는 하나도 돌지 않음
    assert result(tmp_path, "stg_example") is None


@pytest.mark.parametrize("err, halt_reason", [
    ("Could not connect with BigQuery server", "infra_error"),
    ("Access Denied: Dataset proj-x:ai_dev: User does not have permission", "builder_blocked"),
    ("Not found: Dataset proj-x:ai_dev", "infra_error"),
])
def test_location_lookup_failure_is_infra(tmp_path, err, halt_reason):
    build(tmp_path)
    code, fake = run(tmp_path, fake=FakeBq(location=(1, "", err)))
    r = result(tmp_path, "raw_example")
    assert code == 2 and r["verdict"] == "halt" and r["halt_reason"] == halt_reason
    assert r["halt_detail"]["exception"] == "InfraError" and "proj-x" not in r["halt_detail"]["message"]
    assert all(a[0] == "gcloud" for a in fake.calls)


def test_location_unreadable_output_is_infra(tmp_path):
    build(tmp_path)
    code, _ = run(tmp_path, fake=FakeBq(location=(0, "{}", "")))
    r = result(tmp_path, "raw_example")
    assert code == 2 and r["halt_reason"] == "infra_error" and "리전을 읽지 못함" in r["halt_detail"]["message"]


def test_location_not_checked_when_l0_fails(tmp_path):
    build(tmp_path, dag=DAG.replace('"stg_example": ["gate_raw_mart_example"]', '"stg_example": []'))
    code, fake = run(tmp_path)
    assert code == 1 and fake.shows == []


# ---------- 실행기 옵션 ----------

@pytest.mark.parametrize("extra", [["--with-downstream"], ["--ds-from", "2026-10-28"], ["--ds-to", "2026-10-30"]])
def test_not_yet_options(tmp_path, extra, capsys):
    build(tmp_path)
    code, fake = run(tmp_path, *extra)
    assert code == 2 and "마트 1 이후 구현" in capsys.readouterr().err and fake.calls == []


@pytest.mark.parametrize("kind", ["change", "backfill_check"])
def test_maintenance_kinds_go_to_separate_folder(tmp_path, kind):
    build(tmp_path)
    code, _ = run(tmp_path, "--request-kind", kind, task=("--task", "raw_example"))
    assert code == 0 and result(tmp_path, "raw_example") is None
    assert result(tmp_path, "raw_example", "maintenance")["request_kind"] == kind


def test_backfill_check_iteration_must_be_1(tmp_path, capsys):
    build(tmp_path)
    argv = ["--mart", MART, "--all", "--iteration", "2", "--root", str(tmp_path), "--request-kind", "backfill_check"]
    assert run_ladder.main(argv, bq=common.Bq(runner=FakeBq(), env={}), today=TODAY) == 2
    assert "--iteration 1" in capsys.readouterr().err


def test_unknown_request_kind_rejected(tmp_path):
    build(tmp_path)
    with pytest.raises(SystemExit) as e:
        run(tmp_path, "--request-kind", "hotfix")
    assert e.value.code == 2


@pytest.mark.parametrize("ds", ["2026-10-23", "2026-10-31", "2026/10/30"])
def test_ds_window(tmp_path, ds, capsys):
    build(tmp_path)
    argv = ["--mart", MART, "--all", "--iteration", "1", "--root", str(tmp_path), "--ds", ds]
    assert run_ladder.main(argv, bq=common.Bq(runner=FakeBq(), env={}), today=TODAY) == 2


def test_ds_default_is_today(tmp_path):
    build(tmp_path)
    argv = ["--mart", MART, "--task", "raw_example", "--iteration", "1", "--root", str(tmp_path),
            "--dev-dir", str(tmp_path / ".dev")]
    assert run_ladder.main(argv, bq=common.Bq(runner=FakeBq(), env={"CLOUDSDK_CONFIG": "x"}), today=TODAY) == 0
    assert result(tmp_path, "raw_example")["rungs"][1]["ds"] == "2026-10-30"


def test_gate_task_rejected(tmp_path):
    build(tmp_path)
    assert run(tmp_path, task=("--task", "gate_stg_mart_example"))[0] == 2


def test_existing_result_not_rerun(tmp_path):
    build(tmp_path)
    assert run(tmp_path, task=("--task", "raw_example"))[0] == 0
    code, fake = run(tmp_path, task=("--task", "raw_example"))
    assert code == 2 and fake.calls == []


def test_expert_rules_not_implemented_yet(tmp_path):
    c = copy.deepcopy(VALID)
    c["modules"]["expert"] = {"on": ["EX-DBA-05"], "version": "abc"}
    build(tmp_path, contract=c)
    assert run(tmp_path)[0] == 2


# ---------- gen_dq ----------

def test_gen_dq_output(tmp_path):
    paths = build(tmp_path)
    text = (tmp_path / "dags" / "sql" / "dq" / "gate_stg_mart_example.sql").read_text(encoding="utf-8")
    assert text.startswith("-- 자동 생성: scripts/ladder/gen_dq.py")
    assert "ASSERT NOT {{ params.force_fail }} AS '[DQ-FORCE]" in text
    assert "ASSERT NOT EXISTS (\nSELECT example_id" in text and ") AS '[C-01] 키는 고유하다';" in text
    assert "-- error_type" not in text and "HAVING COUNT(*) > 1;" not in text
    raw = (tmp_path / "dags" / "sql" / "dq" / "gate_raw_mart_example.sql").read_text(encoding="utf-8")
    assert "ASSERT NOT EXISTS" not in raw  # raw 층 검사는 없다
    assert common.render(text, "p", TODAY).count("ASSERT NOT False") == 1


def test_gen_dq_rejects_quote_in_rule(tmp_path):
    c = copy.deepcopy(VALID)
    c["checks"]["gates"][0]["rule"] = "키는 'id'로 고유하다"
    with pytest.raises(ValueError, match="쓸 수 없는 글자"):
        build(tmp_path, contract=c)


def test_gen_dq_cli_check(tmp_path, capsys):
    build(tmp_path)
    args = ["--mart", MART, "--root", str(tmp_path)]
    assert gen_dq.main(args + ["--check"]) == 0
    (tmp_path / "dags" / "sql" / "dq" / "gate_stg_mart_example.sql").write_text("SELECT 1", encoding="utf-8")
    assert gen_dq.main(args + ["--check"]) == 1
    assert gen_dq.main(args) == 0 and gen_dq.main(args + ["--check"]) == 0


# ---------- 스모크 예제 (.dev/checks/3-3_smoke.md) ----------

def test_smoke_fixture_runs_with_fake_bq(tmp_path):
    import ladder_smoke_fixture
    ladder_smoke_fixture.build(tmp_path)
    code, fake = run(tmp_path)
    assert code == 0
    sent = " ".join(a[-1] for a in fake.calls if a[0] == "bq")
    for word in (hc.source_dataset(), hc.load()["source"]["project"], *hc.prod_names()):
        assert word not in sent, word


# ---------- 다른 contract의 task 빌려 쓰기 (결정 61 ④) ----------
# 결재 1은 GitHub PR 머지이므로 L0 ③은 git fetch origin main 뒤 origin/main을 본다.
# 시험은 임시 폴더에 원격 역할 저장소(origin)를 따로 만든다.

import subprocess  # noqa: E402

BASE = {"mart": "mart_base", "dag": {"tasks": [
    {"id": "raw_base", "kind": "load", "layer": "raw", "upstream": []},
    {"id": "gate_raw_mart_base", "kind": "gate", "layer": "raw", "upstream": ["raw_base"]},
]}, "tables": [{"name": "raw_base", "layer": "raw", "task": "raw_base"}]}
BASE_REL = "docs/requirements/mart_base.contract.json"
# 빌린 task의 상류 load task SQL. 사다리가 L1 전에 ai_dev에 준비 실행한다 (결정 70)
BASE_SQL_REL = "dags/sql/raw/raw_base.sql"
BASE_SQL = LOAD_SQL.format(layer="raw", table="raw_base")
BASE_GATE_REL = "dags/sql/dq/gate_raw_mart_base.sql"
BASE_DAG = '    "raw_base": [],\n    "gate_raw_mart_base": ["raw_base"],\n'


def git(root, *args):
    subprocess.run(["git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
                   check=True, capture_output=True)


def put_base(root):
    f = Path(root) / BASE_REL
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(BASE), encoding="utf-8")
    for rel, text in ((BASE_SQL_REL, BASE_SQL), (BASE_GATE_REL, "SELECT 1;\n")):
        s = Path(root) / rel
        s.parent.mkdir(parents=True, exist_ok=True)
        s.write_text(text, encoding="utf-8")


def borrow(tmp_path, up, where="origin", task_index=2):
    """mart_example의 task 하나가 mart_base의 task를 상류로 쓰게 만든다.

    where: origin(원격 main에 머지됨), local(로컬 main에만 커밋, 미결재), worktree(작업 폴더에만), no_remote(origin 없음)
    """
    c = copy.deepcopy(VALID)
    c["dag"]["tasks"][task_index]["upstream"] = [*c["dag"]["tasks"][task_index]["upstream"], up]
    tid = c["dag"]["tasks"][task_index]["id"]
    dag = DAG.replace(f'"{tid}": [', f'"{tid}": ["{up.split(":", 1)[1]}", ')
    build(tmp_path, contract=c, dag=dag)
    origin = tmp_path.parent / f"{tmp_path.name}_origin"
    origin.mkdir()
    git(origin, "init", "-q", "-b", "main")
    if where == "origin":
        put_base(origin)
        git(origin, "add", BASE_REL, BASE_SQL_REL, BASE_GATE_REL)
        git(origin, "commit", "-q", "-m", "base 결재")
        # main에서 브랜치를 땄으므로 작업 트리에도 같은 contract·SQL·DAG 항목이 있다 (준비 실행이 읽는 SQL 포함)
        put_base(tmp_path)
        dag_file = tmp_path / "dags" / "harness_daily.py"
        dag_file.write_text(dag.replace("UPSTREAM = {\n", "UPSTREAM = {\n" + BASE_DAG), encoding="utf-8")
    else:
        git(origin, "commit", "-q", "--allow-empty", "-m", "empty")
    git(tmp_path, "init", "-q", "-b", "main")
    git(tmp_path, "remote", "add", "origin", str(origin) if where != "no_remote" else str(origin) + "_missing")
    if where == "local":
        put_base(tmp_path)
        git(tmp_path, "add", BASE_REL, BASE_SQL_REL, BASE_GATE_REL)
        git(tmp_path, "commit", "-q", "-m", "base 로컬")
    elif where == "worktree":
        put_base(tmp_path)
    return c


def test_borrow_task_on_origin_main_passes(tmp_path):
    # 로컬에는 아직 fetch하지 않았어도 사다리가 fetch한 뒤 origin/main에서 찾는다
    borrow(tmp_path, "mart_base:gate_raw_mart_base")
    code, _ = run(tmp_path, task=("--task", "stg_example"))
    assert code == 0 and result(tmp_path, "stg_example")["verdict"] == "pass"


@pytest.mark.parametrize("up,where,task_index,message", [
    ("mart_base:gate_raw_mart_base", "local", 2, "origin/main에"),      # 로컬 main에만 있음 = 미결재
    ("mart_base:gate_raw_mart_base", "worktree", 2, "origin/main에"),   # 작업 폴더에만 있음
    ("mart_base:gate_stg_mart_base", "origin", 2, "task 'gate_stg_mart_base'가 없음"),
    ("mart_none:gate_raw_mart_none", "origin", 2, "origin/main에"),
    ("mart_base:raw_base", "origin", 4, "mart는 raw를 직접 읽지 않는다"),
])
def test_borrow_task_not_approved_halts(tmp_path, up, where, task_index, message):
    # upstream은 contract(사람 결재 파일)에 적히므로 반려가 아니라 halt (결정 59 판정 원칙)
    borrow(tmp_path, up, where, task_index)
    code, _ = run(tmp_path)
    assert code == 2 and input_halt(tmp_path, "raw_example", message)["rungs"] == []


def test_borrow_fetch_failure_is_infra_error(tmp_path):
    borrow(tmp_path, "mart_base:gate_raw_mart_base", where="no_remote")
    code, fake = run(tmp_path)
    r = result(tmp_path, "raw_example")
    assert code == 2 and r["verdict"] == "halt" and r["halt_reason"] == "infra_error" and r["rungs"] == []
    assert fake.calls == [] and result(tmp_path, "stg_example") is None


def test_no_borrow_no_fetch(tmp_path, monkeypatch):
    # 빌린 task가 없으면 git을 부르지 않는다 (저장소가 아니어도 통과)
    import l0_dag
    called = []
    monkeypatch.setattr(l0_dag, "git", lambda *a, **k: called.append(a))
    build(tmp_path)
    assert run(tmp_path)[0] == 0 and called == []


def test_borrowed_task_not_run_by_this_mart(tmp_path):
    c = borrow(tmp_path, "mart_base:gate_raw_mart_base")
    assert [t["id"] for t in common.topo_load_tasks(c)] == ["raw_example", "stg_example", "mart_example_daily"]


# ---------- 메모장으로 고친 검증 쿼리: BOM과 CRLF (3-3 스모크 1차 후속) ----------

def notepad_bytes(text):
    return b"\xef\xbb\xbf" + text.replace("\n", "\r\n").encode("utf-8")


def test_header_parser_tolerates_bom_and_crlf():
    text = CHECKS["l3/C-01.sql"]
    plain = common.parse_check(text)
    assert common.parse_check(notepad_bytes(text).decode("utf-8")) == plain


def test_bom_crlf_check_files_pass_l0_and_gate_unchanged(tmp_path):
    build(tmp_path)
    gate = tmp_path / "dags" / "sql" / "dq" / "gate_stg_mart_example.sql"
    before = gate.read_bytes()
    for rel, text in CHECKS.items():
        (tmp_path / "docs" / "requirements" / f"{MART}_checks" / rel).write_bytes(notepad_bytes(text))
    assert gen_dq.main(["--mart", MART, "--root", str(tmp_path), "--check"]) == 0
    assert gate.read_bytes() == before
    assert run(tmp_path)[0] == 0


# ---------- 층 단위 실행 순서 (마트 1 R-0001) ----------
# 한 층에 load task가 2개이고 게이트 검사 하나가 두 테이블을 함께 읽는 경우.
# task마다 L1~L5를 끝까지 돌리면 raw_example의 L3가 아직 L2를 거치지 않은 raw_example2를 읽어 "Not found"가 난다.

def two_raw_contract():
    c = copy.deepcopy(VALID)
    c["tables"].insert(1, {"name": "raw_example2", "layer": "raw", "task": "raw_example2", "grain": "원천 행 1개",
                           "keys": ["example_id"], "columns": copy.deepcopy(c["tables"][0]["columns"])})
    c["dag"]["tasks"].insert(1, {"id": "raw_example2", "kind": "load", "layer": "raw", "upstream": []})
    c["dag"]["tasks"][2]["upstream"] = ["raw_example", "raw_example2"]
    c["checks"]["gates"].append({"id": "C-03", "rule": "raw 두 테이블의 날짜가 맞는다", "rung": "L3",
                                 "written_by": "verifier"})
    c["traces_to"].append({"req": "R-01", "check": "C-03", "rung": "L3"})
    return c


TWO_RAW_DAG = DAG.replace('"gate_raw_mart_example": ["raw_example"],',
                          '"raw_example2": [],\n    "gate_raw_mart_example": ["raw_example", "raw_example2"],')
TWO_RAW_CHECKS = {
    **CHECKS,
    "l3/C-03.sql": "-- error_type: join_missing\n-- task: raw_example\n"
                   "SELECT a.snapshot_date FROM `{{ project }}.{{ dataset_raw }}.raw_example` AS a\n"
                   "LEFT JOIN `{{ project }}.{{ dataset_raw }}.raw_example2` AS b ON a.snapshot_date = b.snapshot_date\n"
                   "WHERE b.snapshot_date IS NULL\n",
}


class TableBq(FakeBq):
    """ai_dev 테이블이 L2(적재 SQL 실행)로 생기기 전에 읽으면 BigQuery처럼 "Not found: Table"을 낸다."""

    def __init__(self, rules=(), tables=("raw_example", "raw_example2", "stg_example", "mart_example_daily")):
        super().__init__(rules)
        self.tables, self.created = tables, set()

    def __call__(self, args, env, stdin=None):
        sql = stdin or ""
        if args[0] == "bq" and "INFORMATION_SCHEMA.TABLES" in sql:
            self.argv.append(args)
            self.calls.append([*args, stdin])
            if "--dry_run" in args:
                return 0, json.dumps({"statistics": {"totalBytesProcessed": "0"}}), ""
            name = re.search(r"table_name = '(\w+)'", sql).group(1)
            return 0, json.dumps([{"n": "1" if name in self.created else "0"}]), ""
        if args[0] == "bq" and "--dry_run" not in args:
            self.created |= set(re.findall(r"CREATE TABLE IF NOT EXISTS `proj-x\.ai_dev\.(\w+)`", sql))
        if args[0] == "bq":
            for t in self.tables:
                if f"ai_dev.{t}`" not in sql:
                    continue
                if f"CREATE TABLE IF NOT EXISTS `proj-x.ai_dev.{t}`" in sql:  # 이 테이블의 적재 SQL
                    if "--dry_run" not in args:
                        self.created.add(t)
                elif t not in self.created:
                    self.argv.append(args)
                    self.calls.append([*args, stdin])
                    return 1, "", f"Not found: Table proj-x:ai_dev.{t} was not found in location US"
        return super().__call__(args, env, stdin)


def build_two_raw(tmp_path, checks=None):
    return build(tmp_path, contract=two_raw_contract(), checks=checks or TWO_RAW_CHECKS, dag=TWO_RAW_DAG)


def test_layer_order_gate_reads_two_tables_of_same_layer(tmp_path, capsys):
    build_two_raw(tmp_path)
    code, fake = run(tmp_path, fake=TableBq())
    assert code == 0, capsys.readouterr().out
    for task in ("raw_example", "raw_example2", "stg_example", "mart_example_daily"):
        r = result(tmp_path, task)
        assert r["verdict"] == "pass" and [g["rung"] for g in r["rungs"]] == ["L0", "L1", "L2", "L3", "L4", "L5"]
    assert result(tmp_path, "raw_example")["rungs"][3]["metrics"]["checks"] == ["C-03"]


def test_layer_order_schedule(tmp_path):
    build_two_raw(tmp_path)
    contract = two_raw_contract()
    order = [(t["id"], name) for t, name, _ in run_ladder.schedule(common.topo_load_tasks(contract))]
    assert order == [
        ("raw_example", "L1"), ("raw_example", "L2"), ("raw_example2", "L1"), ("raw_example2", "L2"),
        ("raw_example", "L3"), ("raw_example2", "L3"),
        ("stg_example", "L1"), ("stg_example", "L2"), ("stg_example", "L3"),
        ("mart_example_daily", "L1"), ("mart_example_daily", "L2"), ("mart_example_daily", "L3"),
        ("raw_example", "L4"), ("raw_example2", "L4"), ("stg_example", "L4"), ("mart_example_daily", "L4"),
        ("raw_example", "L5"), ("raw_example2", "L5"), ("stg_example", "L5"), ("mart_example_daily", "L5"),
    ]


def test_layer_order_interrupted_tasks_keep_bytes(tmp_path, capsys):
    # stg L3에서 반려: raw 두 task는 L1~L3, mart는 시작 전. raw는 파일 없이 stg 파일의 interrupted_tasks에 남는다
    build_two_raw(tmp_path)
    rows = json.dumps([{"example_id": 1}])
    code, _ = run(tmp_path, fake=TableBq([("run", "HAVING COUNT(*) > 1", (0, rows, ""))]))
    assert code == 1
    r = result(tmp_path, "stg_example")
    assert r["verdict"] == "reject" and r["rungs"][-1]["rung"] == "L3"
    assert [(i["task"], i["passed_rungs"]) for i in r["interrupted_tasks"]] == [
        ("raw_example", ["L0", "L1", "L2", "L3"]), ("raw_example2", ["L0", "L1", "L2", "L3"])]
    assert all(i["bytes"] > 0 for i in r["interrupted_tasks"])
    assert r["bytes_total"] > 0  # 이 task 것만
    assert result(tmp_path, "raw_example") is None and result(tmp_path, "raw_example2") is None
    assert result(tmp_path, "mart_example_daily") is None
    verdicts = [t["verdict"] for t in json.loads(capsys.readouterr().out)["tasks"]]
    assert verdicts == ["중단", "중단", "reject", "실행 안 함"]


def test_layer_order_l5_failure_after_others_passed(tmp_path):
    # L5 단계에서 앞 task는 L1~L5를 마쳐 pass 파일, 실패 task 뒤는 L1~L4까지 → interrupted_tasks
    build_two_raw(tmp_path)
    counts = iter(["1", "1", "1", "1", "1", "2"])  # raw_example·raw_example2 같음, stg_example 다름
    snap = lambda: (0, json.dumps([{"row_count": next(counts), "checksum": "42"}]), "")  # noqa: E731
    code, _ = run(tmp_path, fake=TableBq([("run", "row_count", snap)]))
    assert code == 1
    assert result(tmp_path, "raw_example")["verdict"] == "pass" and result(tmp_path, "raw_example2")["verdict"] == "pass"
    r = result(tmp_path, "stg_example")
    assert r["rungs"][-1]["rung"] == "L5" and r["rungs"][-1]["error_type"] == "idempotency_break"
    assert [(i["task"], i["passed_rungs"]) for i in r["interrupted_tasks"]] == [
        ("mart_example_daily", ["L0", "L1", "L2", "L3", "L4"])]


def test_layer_order_checks_read_only_loaded_tables(tmp_path):
    # 게이트·L4·L5 검사가 읽는 테이블은 모두 그 전에 L2(적재 SQL)를 거쳤다
    build_two_raw(tmp_path)
    _, fake = run(tmp_path, fake=TableBq())
    loaded, checked = set(), []
    for a in fake.calls:
        if a[0] != "bq" or "--dry_run" in a:
            continue
        sql = a[-1]
        tables = {t for t in TableBq().tables if f"ai_dev.{t}`" in sql}
        if "INSERT INTO" in sql:
            loaded |= tables
        else:
            assert tables <= loaded, (tables - loaded, sql)
            checked.append(tables)
    assert {"raw_example", "raw_example2"} in checked  # C-03이 raw 두 테이블을 함께 읽음


@pytest.mark.parametrize("stage,rung", [("l3", "L3"), ("l4", "L4")])
def test_check_query_missing_table_halts_input_invalid(tmp_path, stage, rung):
    # 검증 쿼리(verifier 파일)가 없는 테이블을 읽으면 builder 반려가 아니라 halt input_invalid (결정 59)
    checks = dict(CHECKS)
    key = "l3/C-01.sql" if stage == "l3" else "l4/C-02.sql"
    checks[key] = checks[key].replace("stg_example`", "stg_typo`")
    build(tmp_path, checks=checks)
    msg = (1, "", "Not found: Table proj-x:ai_dev.stg_typo was not found in location US")
    code, _ = run(tmp_path, fake=FakeBq([("dry", "stg_typo", msg)]))
    r = input_halt(tmp_path, "stg_example", f"{stage}/{key.split('/')[1]}")
    assert code == 2 and r["rungs"][-1]["rung"] == ("L2" if stage == "l3" else "L3")
    assert "Not found: Table" in r["halt_detail"]["message"]


PROGRESS_OUT = "".join(f"Waiting on bqjob_r1a2b_0000_1 ... ({i}s) Current status: RUNNING\r" for i in range(20))
BQ_REASON = "BigQuery error in query operation: Unrecognized name: delivered_at at [3:5] (proj-x:ai_dev.stg_example)"


def test_l2_message_keeps_reason_after_progress(tmp_path):
    # 4-22: 진행 표시가 앞 500자를 채워 오류 이유가 기록에서 잘렸다. 판정·기록 칸은 그대로 (4-26)
    assert len(PROGRESS_OUT) > 500
    build(tmp_path)
    code, _ = run(tmp_path, fake=FakeBq([("run", "stg_example", (1, PROGRESS_OUT + "\n" + BQ_REASON + "\n", ""))]))
    r = result(tmp_path, "stg_example")
    g = r["rungs"][-1]
    assert code == 1 and r["verdict"] == "reject"
    assert (g["rung"], g["error_type"], g["error_class"]) == ("L2", "runtime_error", "syntax")
    assert list(g["metrics"]) == ["message"]
    message = g["metrics"]["message"]
    assert "Unrecognized name: delivered_at" in message and "Waiting on" not in message and len(message) <= 500
    assert "proj-x" not in message  # 기록의 기존 가림(scrub)을 그대로 거친다


def test_check_verdict_reads_old_head_not_new_message(tmp_path):
    # 진행 표시 뒤의 "Not found: Table"은 전에 판정에 보이지 않아 반려였다. 기록만 고치고 판정은 그대로 (사전 등록 v6)
    build(tmp_path)
    missing = "Not found: Table proj-x:ai_dev.stg_example was not found in location US"
    code, _ = run(tmp_path, fake=FakeBq([("run", "GROUP BY 1", (1, PROGRESS_OUT + "\n" + missing, ""))]))
    r = result(tmp_path, "stg_example")
    g = r["rungs"][-1]
    assert code == 1 and r["verdict"] == "reject" and r["halt_reason"] is None
    assert (g["rung"], g["error_type"]) == ("L3", "runtime_error") and "Not found: Table" in g["metrics"]["message"]


@pytest.mark.parametrize("text,default,exc,error_type,halt", [
    (PROGRESS_OUT + "Access Denied: Table x", "runtime_error", common.InfraError, None, "builder_blocked"),
    (PROGRESS_OUT + "Could not connect", "runtime_error", common.InfraError, None, "infra_error"),
    (PROGRESS_OUT + "Query exceeded limit for bytes billed", "runtime_error", common.QueryError, "cost_exceeded", None),
    (PROGRESS_OUT + "Could not cast literal", "runtime_error", common.QueryError, "type_mismatch", None),
    (PROGRESS_OUT + "Could not cast literal", "syntax", common.QueryError, "syntax", None),
])
def test_raise_for_classifies_whole_output_as_before(text, default, exc, error_type, halt):
    with pytest.raises(exc) as e:
        common.Bq.raise_for(text, default)
    assert getattr(e.value, "error_type", None) == error_type
    assert getattr(e.value, "halt_reason", None) == halt
    assert "Waiting on" not in str(e.value)


@pytest.mark.parametrize("text", ["", "   \n", "Syntax error: odd", "  line one\n\nline two\r\nline three  \n"])
def test_reason_text_short_output_is_unchanged(text):
    assert common.reason_text(text) == text.strip()


def test_reason_text_progress_only_keeps_old_head():
    assert common.reason_text(PROGRESS_OUT) == PROGRESS_OUT.strip()[:500]
    assert common.reason_text("[=====>    ] 50%\n") == "[=====>    ] 50%"


@pytest.mark.parametrize("text,expected", [
    ("Waiting on bqjob_1 ... (2s) Current status: DONE   \n\nError in query string: bad", "Error in query string: bad"),
    ("Waiting on bqjob_1 ... (2s) Current status: DONE   Error in query string: bad", "Error in query string: bad"),
    ("[=====>    ] 50%\nError in query string: bad", "Error in query string: bad"),
    ("Syntax error at [3:5]\nWaiting on bqjob_1 ...", "Syntax error at [3:5]"),
])
def test_reason_text_removes_progress_only(text, expected):
    assert common.reason_text(text) == expected


def test_reason_text_long_output_prefers_error_lines_then_tail():
    others = [f"context {i:03d} " + "x" * 40 for i in range(30)]
    text = "\n".join([PROGRESS_OUT, *others[:15], "Error in query string: bad", *others[15:]])
    message = common.reason_text(text)
    assert len(message) == 500 and message.startswith("Error in query string: bad\n")
    assert message.endswith(others[-1]) and others[0] not in message


def test_reason_text_long_error_stays_within_limit():
    long_error = "Error in query string: " + "y" * 600
    assert common.reason_text(PROGRESS_OUT + "\n" + long_error) == long_error[:500]
    assert common.reason_text(long_error) == long_error[:500]
    plain = "z" * 700
    assert common.reason_text(plain) == plain[-500:]


@pytest.mark.parametrize("bq_error,error_type,hidden,kept", [
    ("BigQuery error in query operation: Error processing job 'proj-x:bqjob_r1a2b_0000_1': Unrecognized name: foo",
     "runtime_error", "proj-x", "Unrecognized name: foo"),
    ("Not found: Dataset proj-x:other_ds was not found in location US", "runtime_error", "proj-x", "Not found: Dataset"),
    ("Bad int64 value: 12345", "type_mismatch", "12345", "Bad int64 value: [value]"),
])
def test_l2_record_hides_project_and_value(tmp_path, bq_error, error_type, hidden, kept):
    # 저장 message에 프로젝트 ID·값이 남지 않고 오류 종류는 남는다. reject_secrets에 걸리면 반려 기록이 남지 않는다 (4-26)
    build(tmp_path)
    code, _ = run(tmp_path, fake=FakeBq([("run", "stg_example", (1, PROGRESS_OUT + "\n" + bq_error, ""))]))
    r = result(tmp_path, "stg_example")
    g = r["rungs"][-1]
    assert code == 1 and r["verdict"] == "reject" and (g["rung"], g["error_type"]) == ("L2", error_type)
    assert hidden not in g["metrics"]["message"] and kept in g["metrics"]["message"]


@pytest.mark.parametrize("text,expected", [
    ("Error processing job 'proj-x:bqjob_r1_0_1': bad", "Error processing job '[project]:bqjob_r1_0_1': bad"),
    ("Not found: Dataset proj-x:other_ds", "Not found: Dataset [project]:other_ds"),
    ("Not found: Table proj-x:ai_dev.t", "Not found: Table [project]:ai_dev.t"),
    ("Not found: Table proj-x.other_ds.t", "Not found: Table [project].other_ds.t"),
    ("Access Denied: Project proj-x: no access", "Access Denied: Project [project]: no access"),
    ("Bad double value: abc; error in writing field x", "Bad double value: [value]; error in writing field x"),
    ("Invalid NUMERIC value: 1,234", "Invalid NUMERIC value: [value]"),
    ("Invalid value: 'abc'", "Invalid value: [value]"),
    ("Could not cast literal 'abc' to type INT64 at [3:5]", "Could not cast literal [value] to type INT64 at [3:5]"),
    ('Invalid date: "2026-13-01"', "Invalid date: [value]"),
    ("Can't read, doesn't exist", "Can't read, doesn't exist"),
    ("Unrecognized name: `discount` at [3:5]", "Unrecognized name: `discount` at [3:5]"),
])
def test_mask_reason(text, expected):
    assert common.mask_reason(text) == expected


def test_value_cut_by_limit_is_masked_before_cutting():
    message = common.reason_text("x" * 490 + " Error Bad int64 value: 123456789012345")
    assert len(message) <= 500 and "1234" not in message


@pytest.mark.parametrize("text,error_type", [("Not found: Table proj-x:ai_dev.t", "runtime_error"),
                                             ("Bad int64 value: 12345", "type_mismatch")])
def test_verdict_text_is_not_masked(text, error_type):
    with pytest.raises(common.QueryError) as e:
        common.Bq.raise_for(text, "runtime_error")
    assert e.value.error_type == error_type and e.value.verdict_text == text and str(e.value) != text


def test_l2_sql_creates_other_table_name_is_rejection(tmp_path):
    # SQL이 contract와 다른 이름의 테이블을 만들면 L2 실행은 성공해도 반려 dag_structure_mismatch (결정 59, builder 파일)
    build(tmp_path)
    f = tmp_path / "dags" / "sql" / "stg" / "stg_example.sql"
    f.write_text(f.read_text(encoding="utf-8").replace("stg_example`", "stg_examples`"), encoding="utf-8")
    code, fake = run(tmp_path, fake=TableBq())
    r = result(tmp_path, "stg_example")
    assert code == 1 and r["verdict"] == "reject" and r["halt_reason"] is None
    g = r["rungs"][-1]
    assert (g["rung"], g["error_type"], g["error_class"]) == ("L2", "dag_structure_mismatch", "syntax")
    assert g["metrics"]["table"] == "stg_example" and "stg_example" in g["metrics"]["message"]
    assert "stg_examples" in fake.created and "stg_example" not in fake.created
    # 확인 쿼리도 dry-run 먼저, 비용 상한
    info = [a for a in fake.calls if a[0] == "bq" and "INFORMATION_SCHEMA" in a[-1]]
    assert info and all(f"--maximum_bytes_billed={common.MAX_BYTES}" in a for a in info)
    assert "--dry_run" in info[0]


def test_l2_table_check_query_failure_is_infra_error(tmp_path):
    build(tmp_path)
    code, _ = run(tmp_path, fake=FakeBq([("run", "INFORMATION_SCHEMA", (1, "", "Syntax error: odd"))]))
    r = result(tmp_path, "raw_example")
    assert code == 2 and r["verdict"] == "halt" and r["halt_reason"] == "infra_error"
    assert "테이블 확인 쿼리 실패" in r["halt_detail"]["message"]


def string_leaves(value, path=()):
    """contract 안의 모든 문자열 칸 경로."""
    if isinstance(value, str):
        yield path
    elif isinstance(value, dict):
        for k, v in value.items():
            yield from string_leaves(v, path + (k,))
    elif isinstance(value, list):
        for i, v in enumerate(value):
            yield from string_leaves(v, path + (i,))


@pytest.mark.parametrize("bad", ["'", "{", "}", "\\", "\n", "😀"])
def test_l0_pass_means_gate_generation_does_not_break(tmp_path, bad):
    """모든 문자열 칸에 게이트를 깨는 글자를 넣어 본다: L0를 통과한 contract는 gen_dq가 거절하지 않는다
    (L0가 못 잡고 루프에서야 멈추는 늦은 검증을 막는다, 결정 80)."""
    import l0_contract  # noqa: E402
    for i, path in enumerate(string_leaves(VALID)):
        c = copy.deepcopy(VALID)
        node = c
        for key in path[:-1]:
            node = node[key]
        node[path[-1]] = node[path[-1]] + bad
        if l0_contract.check_contract(c)["status"] != "pass":
            continue
        root = tmp_path / str(i)
        try:
            build(root, contract=c)
        except ValueError as e:
            pytest.fail(f"{'.'.join(map(str, path))}에 {bad!r}: L0는 통과했는데 게이트 생성이 깨짐 ({e})")
