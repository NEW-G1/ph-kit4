"""L0 contract 형식 검사 시험. 예시는 가짜 마트(mart_example)이고 BigQuery는 부르지 않는다."""
import copy
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from config_fixture import hc, pii_list, pin, shipped, src, write_pii  # noqa: F401 (pii_list·shipped는 고정구)
import l0_contract as l0  # noqa: E402 (config_fixture가 scripts/ladder를 경로에 넣는다)

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "ladder" / "l0_contract.py"
TEMPLATE = ROOT / "docs" / "requirements" / "_template.contract.json"


def col(name, type_="STRING"):
    return {"name": name, "type": type_, "description": f"{name} 설명 (예시)"}


VALID = {
    "mart": "mart_example",
    "version": 1,
    "requirements": [
        {"id": "R-01", "text": "예시 지표를 일자별로 본다", "section": 3},
        {"id": "R-02", "text": "원천과 행 수가 맞는다", "section": 7},
    ],
    "sources": [src("orders")],
    "interview": {
        "metrics": [{"name": "example_metric", "formula": "example_formula", "unit": "건",
                     "base_date": "example_date", "exclude": "없음", "numerator": None, "denominator": None}],
        "grain": "예시 행 1개 = 일자 1개",
        "keys": ["example_date"],
        "assumptions": ["예시 가정"],
        "out_of_scope": ["예시 범위 밖"],
    },
    "tables": [
        {"name": "raw_example", "layer": "raw", "task": "raw_example", "grain": "원천 행 1개",
         "keys": ["example_id"], "columns": [col("example_id", "INT64"), col("example_date", "DATE")]},
        {"name": "stg_example", "layer": "stg", "task": "stg_example", "grain": "원천 행 1개",
         "keys": ["example_id"], "columns": [col("example_id", "INT64"), col("example_date", "DATE")]},
        {"name": "mart_example_daily", "layer": "mart", "task": "mart_example_daily", "grain": "일자 1개",
         "keys": ["example_date"], "columns": [col("example_date", "DATE"), col("example_metric", "INT64")]},
    ],
    "dag": {"tasks": [
        {"id": "raw_example", "kind": "load", "layer": "raw", "upstream": []},
        {"id": "gate_raw_mart_example", "kind": "gate", "layer": "raw", "upstream": ["raw_example"]},
        {"id": "stg_example", "kind": "load", "layer": "stg", "upstream": ["gate_raw_mart_example"]},
        {"id": "gate_stg_mart_example", "kind": "gate", "layer": "stg", "upstream": ["stg_example"]},
        {"id": "mart_example_daily", "kind": "load", "layer": "mart", "upstream": ["gate_stg_mart_example"]},
        {"id": "gate_mart_mart_example", "kind": "gate", "layer": "mart", "upstream": ["mart_example_daily"]},
    ]},
    "checks": {
        "gates": [{"id": "C-01", "rule": "키는 고유하다", "rung": "L3", "written_by": "verifier"}],
        "reconciliation": [{"id": "C-02", "rule": "원천 대비 행 수 오차 0", "rung": "L4", "written_by": "verifier"}],
        "invariants": [{"id": "I-01", "rule": "행 유실 없음", "rung": "L4", "written_by": "verifier"}],
    },
    "traces_to": [
        {"req": "R-01", "check": "C-01", "rung": "L3"},
        {"req": "R-02", "check": "C-02", "rung": "L4"},
        {"req": "R-02", "check": "I-01", "rung": "L4"},
    ],
    "schedule": {"refresh": "daily", "retention_days": None},
    "modules": {"expert": {"on": [], "version": None}},
}


def contract(**changes):
    """VALID를 복사해 'a.b.0.c' 경로로 값을 바꾼다. 값이 DELETE면 그 칸을 지운다."""
    c = copy.deepcopy(VALID)
    for path, value in changes.items():
        keys = [int(k) if k.isdigit() else k for k in path.split("__")]
        target = c
        for k in keys[:-1]:
            target = target[k]
        if value is DELETE:
            del target[keys[-1]]
        else:
            target[keys[-1]] = value
    return c


DELETE = object()


def errors_of(c):
    result = l0.check_contract(c)
    assert result["status"] == "fail"
    assert result["error_type"] == "contract_invalid"
    return "\n".join(result["metrics"]["errors"])


# ---------- 통과 ----------

def test_valid_contract_passes():
    result = l0.check_contract(copy.deepcopy(VALID))
    assert result == {"rung": "L0", "status": "pass",
                      "metrics": {"stage": "contract", "load_tasks": 3, "gate_tasks": 3, "tables": 3,
                                  "checks": 3, "traces": 3},
                      "error_type": None, "error_class": None}


def test_result_fits_ladder_rung_format():
    for c in (copy.deepcopy(VALID), contract(mart="")):
        r = l0.check_contract(c)
        assert set(r) == {"rung", "status", "metrics", "error_type", "error_class"}


def test_ratio_metric_and_expert_snapshot_pass():
    c = contract(interview__metrics__0__numerator="example_a_cnt",
                 interview__metrics__0__denominator="example_b_cnt",
                 modules={"expert": {"on": ["EX-DBA-05"], "version": "abc123"}})
    assert l0.check_contract(c)["status"] == "pass"


def test_layer_without_load_needs_no_gate():
    # raw를 재사용해 raw 적재 task가 없는 마트: raw 게이트도 없어야 한다
    c = copy.deepcopy(VALID)
    c["dag"]["tasks"] = [t for t in c["dag"]["tasks"] if t["layer"] != "raw"]
    c["dag"]["tasks"][0]["upstream"] = []
    c["tables"] = [t for t in c["tables"] if t["layer"] != "raw"]
    assert l0.check_contract(c)["status"] == "pass"


# ---------- 실패: 빈 칸·누락 ----------

@pytest.mark.parametrize("changes,message", [
    ({"mart": ""}, "mart"),
    ({"mart": DELETE}, "필수 칸 없음 ['mart']"),
    ({"version": 0}, "version"),
    ({"requirements": []}, "requirements: 비어 있음"),
    ({"requirements__0__text": ""}, "requirements[0].text"),
    ({"sources": []}, "sources: 비어 있음"),
    ({"interview__metrics": []}, "interview.metrics: 비어 있음"),
    ({"interview__metrics__0__base_date": ""}, "base_date"),
    ({"interview__grain": ""}, "interview.grain"),
    ({"interview__keys": []}, "interview.keys: 비어 있음"),
    ({"interview__assumptions": []}, "interview.assumptions: 비어 있음"),
    ({"interview__out_of_scope": []}, "interview.out_of_scope: 비어 있음"),
    ({"interview__out_of_scope": [" "]}, "interview.out_of_scope[0]"),
    ({"interview__grain": DELETE}, "필수 칸 없음 ['grain']"),
    ({"tables": []}, "tables: 비어 있음"),
    ({"tables__0__columns__0__description": ""}, "description"),
    ({"tables__0__grain": ""}, "tables[0].grain"),
    ({"tables__0__keys": []}, "tables[0].keys: 비어 있음"),
    ({"checks__gates": []}, "checks.gates: 비어 있음"),
    ({"checks__reconciliation": []}, "checks.reconciliation: 비어 있음"),
    ({"checks__invariants": []}, "checks.invariants: 비어 있음"),
    ({"traces_to": []}, "traces_to: 비어 있음"),
    ({"schedule__refresh": ""}, "schedule.refresh"),
    ({"modules": DELETE}, "필수 칸 없음 ['modules']"),
])
def test_empty_or_missing_fails(changes, message):
    assert message in errors_of(contract(**changes))


@pytest.mark.parametrize("rule", ["status = 'Cancelled'인 행이 0개", "값이 {x}", "경로 a\\b", "두 줄\n문장"])
def test_check_rule_with_assert_breaking_chars_fails(rule):
    """검사 문장은 게이트 SQL의 ASSERT 메시지로 들어간다. gen_dq가 거절하는 글자는 L0(인터뷰 단계)에서 먼저 막는다."""
    assert "checks.gates[0].rule: 작은따옴표" in errors_of(contract(checks__gates__0__rule=rule))


# ---------- 실패: 허용 값 밖 ----------

@pytest.mark.parametrize("changes,message", [
    ({"extra": 1}, "정해지지 않은 칸 ['extra']"),
    ({"mart": "Mart-Example"}, "소문자"),
    ({"requirements__0__id": "REQ1"}, "R-01 형식"),
    ({"requirements__0__section": 10}, "1~9"),
    ({"sources__0": "other_project.dataset.orders"}, hc.source_prefix() + ".<table> 형식"),
    ({"interview__metrics__0__numerator": "a_cnt"}, "함께"),
    ({"dag__tasks__0__kind": "transform"}, "dag.tasks[0].kind"),
    ({"dag__tasks__0__layer": "dw"}, "dag.tasks[0].layer"),
    ({"dag__tasks__2__upstream": ["nope"]}, "없는 task 'nope'"),
    ({"dag__tasks__0__upstream": ["gate_mart_mart_example"]}, "순환"),
    ({"dag__tasks__4__upstream": ["raw_example"]}, "mart는 raw"),
    ({"tables__0__columns__0__type": "VARCHAR"}, "BigQuery 타입"),
    ({"tables__0__keys": ["nope"]}, "columns에 없는 키"),
    ({"tables__0__layer": "stg"}, "층(raw)과 다름"),
    ({"tables__0__task": "gate_raw_mart_example"}, "게이트 task는 테이블을 만들지 않는다"),
    ({"tables__1__task": "raw_example"}, "중복 'raw_example'"),
    ({"checks__gates__0__written_by": "human"}, "written_by"),
    ({"checks__gates__0__written_by": "builder"}, "checks.gates[0].written_by"),
    ({"checks__reconciliation__0__written_by": "builder"}, "checks.reconciliation[0].written_by"),
    ({"checks__invariants__0__written_by": "builder"}, "checks.invariants[0].written_by"),
    ({"checks__gates__0__rung": "L4"}, "checks.gates[0].rung"),
    ({"checks__invariants__0__id": "C-09"}, "I-01 형식"),
    ({"checks__reconciliation__0__id": "C-01"}, "중복 'C-01'"),
    ({"traces_to__0__rung": "L9"}, "traces_to[0].rung"),
    ({"traces_to__0__check": "C-99"}, "checks에 없는 검사 'C-99'"),
    ({"traces_to__0__req": "R-09"}, "requirements에 없는 요구 'R-09'"),
    ({"traces_to__0__rung": "L4"}, "단계(L3)와 다름"),
    ({"modules__expert__on": ["dba"]}, "EX-DBA-05 형식"),
    ({"modules__expert__on": ["EX-DBA-05"]}, "modules.expert.version"),
    ({"schedule__retention_days": 0}, "retention_days"),
])
def test_disallowed_values_fail(changes, message):
    assert message in errors_of(contract(**changes))


def test_requirement_without_trace_fails():
    c = copy.deepcopy(VALID)
    c["traces_to"] = [t for t in c["traces_to"] if t["req"] != "R-02"]
    assert "요구 R-02를 가리키는 검사가 없음" in errors_of(c)


# ---------- 실패: 게이트 ----------

def test_missing_gate_for_layer_fails():
    c = copy.deepcopy(VALID)
    c["dag"]["tasks"] = [t for t in c["dag"]["tasks"] if t["id"] != "gate_stg_mart_example"]
    c["dag"]["tasks"][3]["upstream"] = ["stg_example"]
    assert "stg 층 게이트 task가 0개" in errors_of(c)


def test_two_gates_in_layer_fails():
    c = copy.deepcopy(VALID)
    c["dag"]["tasks"].append({"id": "gate_mart_2", "kind": "gate", "layer": "mart", "upstream": ["gate_mart_mart_example"]})
    assert "mart 층 게이트 task가 2개" in errors_of(c)


def test_gate_without_load_fails():
    c = copy.deepcopy(VALID)
    c["dag"]["tasks"] = [t for t in c["dag"]["tasks"] if t["id"] != "raw_example"]
    c["dag"]["tasks"][0]["upstream"] = []
    c["tables"] = [t for t in c["tables"] if t["layer"] != "raw"]
    assert "raw 층에 적재 task가 없는데 게이트 task가 있음" in errors_of(c)


def test_load_task_without_table_fails():
    c = copy.deepcopy(VALID)
    c["tables"] = c["tables"][:2]
    assert "적재 task 'mart_example_daily'가 만드는 테이블이 없음" in errors_of(c)


# ---------- 형식이 크게 깨진 경우 ----------

@pytest.mark.parametrize("bad", [[], "x", None, {"mart": ["x"], "traces_to": [{"req": ["R"], "check": {}, "rung": []}]}])
def test_wrong_shapes_fail_without_crash(bad):
    r = l0.check_contract(bad)
    assert r["status"] == "fail" and r["error_type"] == "contract_invalid"


def test_template_fails_until_filled():
    template = json.loads(TEMPLATE.read_text(encoding="utf-8"))
    errors = errors_of(template)
    assert "mart" in errors and "interview.grain" in errors


def test_template_has_all_contract_fields():
    template = json.loads(TEMPLATE.read_text(encoding="utf-8"))
    assert tuple(k for k in template if k not in l0.TOP_OPTIONAL_FIELDS) == l0.TOP_FIELDS
    assert template["reverts_to"] is None
    assert set(template["interview"]) == set(VALID["interview"])
    assert set(template["checks"]) == set(VALID["checks"])


# ---------- 한글명 선택 칸 (결정 53) ----------

def test_name_ko_absent_passes():
    c = copy.deepcopy(VALID)
    assert all("name_ko" not in t for t in c["tables"])
    assert l0.check_contract(c)["status"] == "pass"


def test_name_ko_korean_passes():
    c = copy.deepcopy(VALID)
    c["tables"][2]["name_ko"] = "예시 일별 마트"
    c["tables"][2]["columns"][0]["name_ko"] = "기준일"
    assert l0.check_contract(c)["status"] == "pass"


@pytest.mark.parametrize("where", ["table", "column"])
@pytest.mark.parametrize("bad", ["", "  ", 1])
def test_name_ko_empty_or_not_string_fails(where, bad):
    c = copy.deepcopy(VALID)
    target = c["tables"][2] if where == "table" else c["tables"][2]["columns"][0]
    target["name_ko"] = bad
    r = l0.check_contract(c)
    assert (r["status"], r["error_type"]) == ("fail", "contract_invalid")
    assert ".name_ko: 비어 있지 않은 문자열이어야 함" in "\n".join(r["metrics"]["errors"])


def test_unknown_optional_field_still_fails():
    c = copy.deepcopy(VALID)
    c["tables"][2]["columns"][0]["name_en"] = "date"
    assert "정해지지 않은 칸 ['name_en']" in errors_of(c)


# ---------- 되돌림 버전 선택 칸 (결정 64 ②) ----------

@pytest.mark.parametrize("changes", [
    {"version": 3, "reverts_to": None},
    {"version": 3},
    {"version": 3, "reverts_to": 1},
    {"version": 3, "reverts_to": 2},
])
def test_reverts_to_valid_passes(changes):
    assert l0.check_contract(contract(**changes))["status"] == "pass"


@pytest.mark.parametrize("reverts_to, message", [
    (0, "reverts_to: 1 이상 정수여야 함"),
    (3, "reverts_to: version(3)보다 작아야 함"),
    (4, "reverts_to: version(3)보다 작아야 함"),
    ("2", "reverts_to: 1 이상 정수여야 함"),
    (True, "reverts_to: 1 이상 정수여야 함"),
])
def test_reverts_to_invalid_fails(reverts_to, message):
    assert message in errors_of(contract(version=3, reverts_to=reverts_to))


# ---------- 개인 식별 컬럼 (결정 51 ⑦) ----------
# 차단 시험은 시험용 목록(pii_list 고정구, config_fixture.PII_TEST_ROWS)을 쓴다. 실제 목록의 고정은 바로 아래 시험 하나다(키트에서 뺀다)


def pii_errors_of(result):
    assert result["status"] == "fail"
    assert (result["error_type"], result["error_class"]) == ("pii_column", "semantic")
    return "\n".join(result["metrics"]["errors"])


def sql_dir(tmp_path, layer, sql, name="t.sql"):
    folder = tmp_path / "sql" / layer
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name).write_text(sql, encoding="utf-8")
    return tmp_path / "sql"




# ---------- 개인 식별 컬럼 목록의 "검토한 원천" 줄 ----------

PII_HEAD = "| 원천 테이블 | 컬럼 | 근거 |\n|---|---|---|\n"
PII_ROWS = PII_HEAD + "| `users` | `email` | 이메일 |\n"
PII_NONE = PII_HEAD + "| (없음) | | 검토함 |\n"


def pii_file(tmp_path, rows=PII_ROWS, reviewed="default"):
    reviewed = hc.source_prefix() if reviewed == "default" else reviewed
    line = "" if reviewed is None else f"검토한 원천: `{reviewed}`\n\n"
    f = tmp_path / "pii_columns.md"
    f.write_text(f"# 개인 식별 컬럼 목록\n\n{line}## 목록\n\n{rows}", encoding="utf-8")
    return f


def other_source_config():
    data = copy.deepcopy(hc.load())
    data["source"]["dataset"] = data["source"]["dataset"] + "_other"
    return data


def test_repo_pii_file_reviewed_source_is_config_source():
    """저장소의 pii_columns.md는 지금 설정의 원천을 검토한 것이다(원천을 바꾸면 이 줄도 사람이 바꾼다)."""
    text = l0.PII_FILE.read_text(encoding="utf-8")
    assert l0.REVIEWED_SOURCE.findall(text) == [hc.source_prefix()]
    assert src("users").startswith(l0.REVIEWED_SOURCE.findall(text)[0] + ".")


def test_pii_reviewed_source_ok(tmp_path):
    assert l0.load_pii(pii_file(tmp_path)) == {"users": {"email"}}


def test_pii_reviewed_source_missing_fails(tmp_path):
    with pytest.raises(ValueError, match="검토한 원천"):
        l0.load_pii(pii_file(tmp_path, reviewed=None))


def test_pii_reviewed_source_twice_fails(tmp_path):
    f = pii_file(tmp_path)
    f.write_text(f.read_text(encoding="utf-8") + f"\n검토한 원천: `{hc.source_prefix()}`\n", encoding="utf-8")
    with pytest.raises(ValueError, match="하나 있어야 함"):
        l0.load_pii(f)


def test_pii_reviewed_source_differs_from_config_fails(tmp_path, monkeypatch):
    f = pii_file(tmp_path)  # 지금 설정의 원천으로 검토한 목록
    data = other_source_config()
    pin(tmp_path, monkeypatch, data)  # 원천만 바꾸고 목록은 그대로
    try:
        with pytest.raises(ValueError, match="설정의 원천") as e:
            l0.load_pii(f)
        assert f"{data['source']['project']}.{data['source']['dataset']}" in str(e.value)
    finally:
        hc.load.cache_clear()


def test_pii_none_row_with_matching_source_passes(tmp_path):
    assert l0.load_pii(pii_file(tmp_path, rows=PII_NONE)) == {}


def test_pii_none_row_lets_contract_pass(tmp_path):
    pii = l0.load_pii(pii_file(tmp_path, rows=PII_NONE))
    c = copy.deepcopy(VALID)
    c["tables"][1]["columns"].append(col("email"))  # 목록이 비었으므로 막지 않는다
    assert l0.check_contract(c, None, pii)["status"] == "pass"


def test_pii_none_row_needs_matching_source(tmp_path):
    with pytest.raises(ValueError, match="검토한 원천"):
        l0.load_pii(pii_file(tmp_path, rows=PII_NONE, reviewed=None))


def test_pii_none_row_with_column_rows_fails(tmp_path):
    with pytest.raises(ValueError, match="함께"):
        l0.load_pii(pii_file(tmp_path, rows=PII_ROWS + "| (없음) | | 검토함 |\n"))


def test_pii_empty_table_still_fails(tmp_path):
    with pytest.raises(ValueError, match="비어 있음"):
        l0.load_pii(pii_file(tmp_path, rows=PII_HEAD))


def test_l0_cli_path_reports_reviewed_source_mismatch(tmp_path, monkeypatch):
    """CLI(check_contract)는 pii_columns.md를 읽지 못한 기존 경우와 같이 contract_invalid로 둔다."""
    pin(tmp_path, monkeypatch, other_source_config())
    try:
        r = l0.check_contract(copy.deepcopy(VALID))
    finally:
        hc.load.cache_clear()
    assert r["status"] == "fail" and r["error_type"] == "contract_invalid"
    assert "설정의 원천" in r["metrics"]["errors"][0]


@pytest.mark.parametrize("table_index", [1, 2])
def test_pii_column_in_stg_or_mart_contract_fails(table_index, pii_list):
    c = copy.deepcopy(VALID)
    c["tables"][table_index]["columns"].append(col("email"))
    assert "개인 식별 컬럼 'email'" in pii_errors_of(l0.check_contract(c))


def test_pii_column_in_raw_contract_passes(pii_list):
    c = copy.deepcopy(VALID)
    c["tables"][0]["columns"].append(col("email"))
    assert l0.check_contract(c)["status"] == "pass"


def test_pii_failure_wins_over_format_errors(pii_list):
    c = contract(mart="")
    c["tables"][1]["columns"].append(col("latitude", "FLOAT64"))
    errors = pii_errors_of(l0.check_contract(c))
    assert "latitude" in errors and "mart:" in errors


@pytest.mark.parametrize("layer,sql", [
    ("stg", "SELECT id, email FROM {{ dataset_raw }}.raw_users WHERE snapshot_date = DATE('{{ ds }}')"),
    ("stg", "SELECT usr.id, usr.email AS contact FROM {{ dataset_raw }}.raw_users AS usr"),
    ("stg", "SELECT o.id, x.latitude FROM {{ dataset_raw }}.raw_orders o\nJOIN {{ dataset_raw }}.raw_users x ON o.user_id = x.id"),
    ("stg", "SELECT * FROM {{ dataset_raw }}.raw_users"),
    ("stg", "SELECT * EXCEPT(id) FROM {{ dataset_raw }}.raw_users"),
    ("stg", "SELECT u.*, o.id FROM {{ dataset_raw }}.raw_orders o JOIN {{ dataset_raw }}.raw_users u ON o.user_id = u.id"),
    ("stg", "SELECT id, postal_code FROM `{{ dataset_raw }}.raw_users`"),
    ("stg", "SELECT id, first_name FROM {{ dataset_raw }}.`raw_users`"),
    ("stg", f"SELECT id FROM `{src('users')}`, x WHERE last_name IS NULL"),
    ("mart", "SELECT a.id, u.street_address FROM {{ dataset_stg }}.stg_a a, {{ dataset_raw }}.raw_users u"),
    ("stg", "SELECT id, ST_X(u.user_geom) AS x FROM {{ dataset_raw }}.raw_users u"),
    # 목록의 다른 원천(events)에도 같은 규칙
    ("stg", "SELECT e.session_id, e.ip_address FROM {{ dataset_raw }}.raw_events e"),
    ("stg", "SELECT * FROM {{ dataset_raw }}.raw_events WHERE snapshot_date = DATE('{{ ds }}')"),
    ("stg", f"SELECT session_id FROM `{src('events')}` WHERE ip_address IS NOT NULL"),
])
def test_pii_sql_fails(tmp_path, layer, sql, pii_list):
    result = l0.check_contract(copy.deepcopy(VALID), sql_dir(tmp_path, layer, sql))
    assert f"sql/{layer}/t.sql" in pii_errors_of(result)


@pytest.mark.parametrize("layer,sql", [
    # 개인 식별 원천을 읽지 않는 파일의 latitude
    ("stg", "SELECT id, latitude, longitude FROM {{ dataset_raw }}.raw_distribution_centers"),
    # events를 읽어도 users 목록 컬럼은 events의 금지 컬럼이 아님
    ("stg", "SELECT session_id, postal_code FROM {{ dataset_raw }}.raw_events"),
    # 주석·문자열 안의 단어
    ("stg", "-- email, first_name 은 넣지 않는다\n/* SELECT * latitude */\n"
            "SELECT id, 'email' AS note, \"u.*\" AS s FROM {{ dataset_raw }}.raw_users # street_address"),
    # stg_users 등 다른 이름
    ("mart", "SELECT * FROM {{ dataset_stg }}.stg_users"),
    ("mart", "SELECT s.* FROM {{ dataset_stg }}.stg_users s"),
    # 하위 쿼리가 고른 컬럼만 바깥에서 * 로 읽음
    ("stg", "SELECT * FROM (SELECT id, age FROM {{ dataset_raw }}.raw_users)"),
    # dq·raw 폴더는 보지 않음
    ("raw", f"SELECT * FROM `{src('users')}`"),
    ("dq", "SELECT email FROM {{ dataset_raw }}.raw_users"),
])
def test_pii_sql_allowed(tmp_path, layer, sql, pii_list):
    assert l0.check_contract(copy.deepcopy(VALID), sql_dir(tmp_path, layer, sql))["status"] == "pass"


def test_pii_sql_missing_folder_passes(tmp_path, pii_list):
    assert l0.check_sql_dir(tmp_path / "nope", l0.load_pii()) == []
    assert l0.check_contract(copy.deepcopy(VALID), tmp_path / "nope")["status"] == "pass"


# ---------- 명령 ----------

def test_cli_pass_and_fail(tmp_path):
    good = tmp_path / "good.contract.json"
    good.write_text(json.dumps(VALID, ensure_ascii=False), encoding="utf-8")
    bad = tmp_path / "bad.contract.json"
    bad.write_text("{not json", encoding="utf-8")
    run = lambda p: subprocess.run([sys.executable, str(SCRIPT), str(p)], capture_output=True,
                                   text=True, encoding="utf-8", timeout=30)
    r = run(good)
    assert r.returncode == 0 and json.loads(r.stdout)["status"] == "pass"
    r = run(bad)
    assert r.returncode == 1 and json.loads(r.stdout)["error_type"] == "contract_invalid"


def cli_repo(root):
    """하위 프로세스의 l0_contract.py는 자기 위치 기준 저장소의 pii_columns.md·harness_config.json을 읽는다.
    임시 저장소에 스크립트와 설정을 복사하고 시험용 목록을 써서 그 저장소의 스크립트 경로를 돌려준다."""
    ladder = root / "scripts" / "ladder"
    ladder.mkdir(parents=True)
    for name in ("l0_contract.py", "harness_config.py", "load_mode.py"):
        shutil.copy(SCRIPT.parent / name, ladder / name)
    (root / "dags").mkdir()
    shutil.copy(hc.PATH, root / "dags" / "harness_config.json")
    write_pii(root / "docs" / "architecture" / "pii_columns.md")
    return ladder / "l0_contract.py"


def test_cli_sql_dir(tmp_path):
    good = tmp_path / "good.contract.json"
    good.write_text(json.dumps(VALID, ensure_ascii=False), encoding="utf-8")
    sql = sql_dir(tmp_path, "stg", "SELECT email FROM {{ dataset_raw }}.raw_users")
    script = cli_repo(tmp_path / "repo")
    r = subprocess.run([sys.executable, str(script), str(good), "--sql-dir", str(sql)], capture_output=True,
                       text=True, encoding="utf-8", timeout=30)
    assert r.returncode == 1 and json.loads(r.stdout)["error_type"] == "pii_column"


# ---------- 게이트 이름과 다른 contract의 upstream (결정 61) ----------

def test_gate_id_must_follow_rule():
    c = copy.deepcopy(VALID)
    c["dag"]["tasks"][1]["id"] = "gate_raw"
    c["dag"]["tasks"][2]["upstream"] = ["gate_raw"]
    assert "gate_raw_mart_example여야 함" in errors_of(c)


@pytest.mark.parametrize("up,ok,message", [
    ("mart_base:gate_raw_mart_base", True, None),
    ("mart_example:gate_raw_mart_example", False, "같은 contract의 task는 task id만"),
    ("Mart_Base:gate_raw", False, "<마트>:<task>"),
    ("mart_base:x:y", False, "<마트>:<task>"),
    ("mart_base:", False, "<마트>:<task>"),
])
def test_external_upstream_format(up, ok, message):
    c = copy.deepcopy(VALID)
    c["dag"]["tasks"][2]["upstream"] = ["gate_raw_mart_example", up]
    if ok:
        assert l0.check_contract(c)["status"] == "pass"
    else:
        assert message in errors_of(c)


# ---------- 요청자 역할 코드 선택 칸 (결정 71) ----------

@pytest.mark.parametrize("changes", [{}, {"requested_by": None}, {"requested_by": "requester1"},
                                     {"requested_by": "requester12"}])
def test_requested_by_valid_passes(changes):
    assert l0.check_contract(contract(**changes))["status"] == "pass"


@pytest.mark.parametrize("value", ["", "requester0", "requester", "Requester1", "홍길동", "requester1 ", 1,
                                   ["requester1"]])
def test_requested_by_invalid_fails(value):
    assert "requested_by: 역할 코드 requester<숫자>여야 함" in errors_of(contract(requested_by=value))


def test_template_requested_by_is_null():
    assert json.loads(TEMPLATE.read_text(encoding="utf-8"))["requested_by"] is None


