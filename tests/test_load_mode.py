"""적재 방식 선택 시험 (결정 79). contract load 칸이 없거나 snapshot이면 지금 그대로, incremental이면 데이터 날짜 기준.

예시 마트는 test_l0_contract의 VALID에 load 칸을 더한 것이고, BigQuery는 부르지 않는다(가짜 bq).
"""
import copy
import json
import sys
from datetime import timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "ladder"))
import l0_dag  # noqa: E402
import load_mode  # noqa: E402
from config_fixture import hc, src  # noqa: E402
from test_l0_contract import VALID, errors_of, l0  # noqa: E402
from test_ladder import TODAY, FakeBq, build, input_halt, result, run  # noqa: E402

PC, DC = "example_date", "created_at"  # VALID의 모든 테이블에 example_date DATE가 있다
INCREMENTAL = {"mode": "incremental", "date_column": DC, "partition_column": PC}


def inc_contract(**load):
    c = copy.deepcopy(VALID)
    c["load"] = {**INCREMENTAL, **load}
    return c


TARGET = "`{{{{ project }}}}.{{{{ dataset_{layer} }}}}.{table}`"
CREATE = "CREATE TABLE IF NOT EXISTS {target} ({pc} DATE OPTIONS (description = '데이터 날짜'))\nPARTITION BY {pc};\n"
DELETE = "DELETE FROM {target} WHERE {pc} = DATE('{{{{ ds }}}}');\n"
RAW_INSERT = ("INSERT INTO {target} ({pc})\nSELECT DATE(o.{dc}) AS {pc}\nFROM `{source}` AS o\n"
              "WHERE DATE(o.{dc}) = DATE('{{{{ ds }}}}');\n")
UP_INSERT = ("INSERT INTO {target} ({pc})\nSELECT {pc}\nFROM `{{{{ project }}}}.{{{{ dataset_{up_layer} }}}}.{up}`\n"
             "WHERE {pc} = DATE('{{{{ ds }}}}');\n")
UPSTREAM_TABLE = {"stg": ("raw", "raw_example"), "mart": ("stg", "stg_example")}


def inc_sql(layer, table, create=CREATE, delete=DELETE, insert=None):
    target = TARGET.format(layer=layer, table=table)
    if insert is None:
        insert = RAW_INSERT if layer == "raw" else UP_INSERT
    up_layer, up = UPSTREAM_TABLE.get(layer, ("", ""))
    kw = dict(target=target, pc=PC, dc=DC, source=src("orders"), up_layer=up_layer, up=up)
    return create.format(**kw) + delete.format(**kw) + insert.format(**kw)


def build_inc(tmp_path, contract=None, **override):
    """증분 contract와 증분 SQL로 저장소를 만든다. override: {table: sql}."""
    contract = contract or inc_contract()
    paths = build(tmp_path, contract)
    for t in contract["tables"]:
        f = tmp_path / "dags" / "sql" / t["layer"] / f"{t['task']}.sql"
        f.write_text(override.get(t["name"], inc_sql(t["layer"], t["name"])), encoding="utf-8")
    return paths


# ---------- load_mode 공용 함수 ----------

def test_absent_load_is_snapshot():
    assert load_mode.mode(VALID) == "snapshot"
    assert load_mode.partition_column(VALID) == "snapshot_date"
    assert load_mode.date_column(VALID) is None and load_mode.allow_empty_days(VALID) is False


def test_incremental_reads_contract():
    c = inc_contract(allow_empty_days=True)
    assert load_mode.is_incremental(c) and load_mode.partition_column(c) == PC and load_mode.date_column(c) == DC
    assert load_mode.allow_empty_days(c) is True


@pytest.mark.parametrize("bad", [None, "incremental", [], {"mode": "weekly"}, {"mode": ["incremental"]}])
def test_malformed_load_reads_as_snapshot_without_crash(bad):
    # 사다리는 L0 전에 ds 창을 정하므로 틀린 값에도 터지지 않아야 한다. 틀린 contract는 L0가 멈춘다
    c = copy.deepcopy(VALID)
    c["load"] = bad
    assert load_mode.mode(c) == "snapshot" and load_mode.partition_column(c) == "snapshot_date"


# ---------- L0 ① load 형식 ----------

@pytest.mark.parametrize("load", [{"mode": "snapshot"}, INCREMENTAL, {**INCREMENTAL, "allow_empty_days": True},
                                  {**INCREMENTAL, "allow_empty_days": False}])
def test_load_valid_passes(load):
    c = copy.deepcopy(VALID)
    c["load"] = load
    assert l0.check_contract(c)["status"] == "pass"


@pytest.mark.parametrize("load,where", [
    ({"mode": "weekly"}, "load.mode"),
    ({}, "load.mode"),
    ("incremental", "load"),
    ({"mode": "incremental", "partition_column": PC}, "load"),                       # date_column 없음
    ({"mode": "incremental", "date_column": DC}, "load"),                            # partition_column 없음
    ({"mode": "snapshot", "partition_column": PC}, "load"),                          # snapshot은 mode만
    ({**INCREMENTAL, "allow_empty_days": "yes"}, "load.allow_empty_days"),
    ({**INCREMENTAL, "backfill": True}, "load"),
    ({**INCREMENTAL, "partition_column": "Example Date"}, "load.partition_column"),
    ({**INCREMENTAL, "date_column": ""}, "load.date_column"),
])
def test_load_invalid_fails_as_contract_invalid(load, where):
    c = copy.deepcopy(VALID)
    c["load"] = load
    r = l0.check_contract(c)
    assert r["status"] == "fail" and r["error_type"] == "contract_invalid"
    assert where in errors_of(c)


def test_partition_column_must_be_date_in_every_table():
    c = inc_contract(partition_column="example_id")  # raw·stg에는 INT64, mart에는 없음
    r = l0.check_contract(c)
    assert r["status"] == "fail" and r["error_type"] == "contract_invalid"
    text = "; ".join(r["metrics"]["errors"])
    assert "tables[0].columns" in text and "DATE여야" in text and "tables[2].columns" in text and "컬럼이 없음" in text


def test_template_load_is_snapshot():
    def no_duplicates(pairs):
        keys = [k for k, _ in pairs]
        assert len(keys) == len(set(keys)), keys  # json.loads는 중복 칸을 마지막 값으로 덮어 숨긴다
        return dict(pairs)

    text = (ROOT / "docs" / "requirements" / "_template.contract.json").read_text(encoding="utf-8")
    template = json.loads(text, object_pairs_hook=no_duplicates)
    assert template["load"] == {"mode": "snapshot"}


# ---------- L0 ③ 증분 SQL 날짜 조건 ----------

def test_incremental_sql_passes(tmp_path):
    paths = build_inc(tmp_path)
    assert l0_dag.check_sql_contract(paths, inc_contract()) == []


@pytest.mark.parametrize("variant", [
    "WHERE {dc} = DATE('{{{{ ds }}}}');\n",                 # 원천 컬럼이 이미 DATE
    "WHERE DATE ( o.{dc} ) = DATE('{{{{ ds }}}}');\n",
    "WHERE date(o.{dc})=date(\"{{{{ ds }}}}\");\n",
])
def test_raw_source_date_condition_variants_pass(tmp_path, variant):
    insert = RAW_INSERT.replace("WHERE DATE(o.{dc}) = DATE('{{{{ ds }}}}');\n", variant)
    paths = build_inc(tmp_path, raw_example=inc_sql("raw", "raw_example", insert=insert))
    assert l0_dag.check_sql_contract(paths, inc_contract()) == []


MISSING = [
    ("raw_example", dict(create=CREATE.replace("PARTITION BY {pc}", "PARTITION BY snapshot_date")),
     "(1) CREATE에 PARTITION BY example_date"),
    ("stg_example", dict(create=CREATE.replace(";", "\nOPTIONS (partition_expiration_days = 7);")),
     "partition_expiration_days"),
    ("mart_example_daily", dict(delete="DELETE FROM {target} WHERE TRUE;\n"), "(2) DELETE"),
    ("raw_example", dict(insert=RAW_INSERT.replace("WHERE DATE(o.{dc}) = DATE('{{{{ ds }}}}')", "WHERE TRUE")),
     "(3) 원천 SELECT에 DATE(created_at)"),
    ("raw_example", dict(insert=RAW_INSERT.replace("WHERE DATE(o.{dc})", "WHERE DATE(o.updated_at)")),
     "(3) 원천 SELECT"),
    ("stg_example", dict(insert=UP_INSERT.replace("WHERE {pc} = DATE('{{{{ ds }}}}')", "WHERE {pc} IS NOT NULL")),
     "(3) INSERT의 상류 읽기"),
    ("mart_example_daily", dict(insert=UP_INSERT.replace("WHERE {pc} = DATE('{{{{ ds }}}}')",
                                                         "-- WHERE {pc} = DATE('{{{{ ds }}}}')")),
     "(3) INSERT의 상류 읽기"),  # 주석 속 조건은 세지 않는다
]


@pytest.mark.parametrize("table,parts,message", MISSING)
def test_incremental_missing_date_condition_fails(tmp_path, table, parts, message):
    layer = next(t["layer"] for t in VALID["tables"] if t["name"] == table)
    paths = build_inc(tmp_path, **{table: inc_sql(layer, table, **parts)})
    found = l0_dag.check_sql_contract(paths, inc_contract())
    assert len(found) == 1 and table in found[0] and message in found[0], found


def test_snapshot_sql_under_incremental_contract_fails(tmp_path):
    # test_ladder의 LOAD_SQL(snapshot_date 패턴)을 그대로 두고 contract만 incremental로
    paths = build(tmp_path, inc_contract())
    found = l0_dag.check_sql_contract(paths, inc_contract())
    assert len(found) == 3 * 3 and all("증분 적재" in e for e in found)  # 테이블 3개 × (1)(2)(3)


def test_snapshot_contract_does_not_check_date_condition(tmp_path):
    paths = build_inc(tmp_path, contract=copy.deepcopy(VALID))  # 증분 SQL이어도 snapshot이면 보지 않는다
    assert l0_dag.check_sql_contract(paths, VALID) == []


def test_ladder_rejects_missing_date_condition_at_l0_without_bq(tmp_path):
    build_inc(tmp_path, stg_example=inc_sql("stg", "stg_example", delete="DELETE FROM {target} WHERE TRUE;\n"))
    code, fake = run(tmp_path)
    assert code == 1 and fake.calls == []
    rung = result(tmp_path, "raw_example")["rungs"][0]
    assert (rung["rung"], rung["error_type"]) == ("L0", "dag_structure_mismatch")
    assert any("(2) DELETE" in e for e in rung["metrics"]["errors"])


def test_ladder_halts_on_malformed_load_at_l0(tmp_path):
    c = copy.deepcopy(VALID)
    c["load"] = {"mode": "incremental", "date_column": DC}
    build(tmp_path, c)
    code, fake = run(tmp_path)
    assert code == 2 and fake.calls == []
    input_halt(tmp_path, "raw_example", "load")


# ---------- 다른 마트 task 빌려 쓰기 (결정 61 ④, 79) ----------

def other_contract(load=None):
    other = {"mart": "mart_base", "dag": {"tasks": [
        {"id": "raw_base", "kind": "load", "layer": "raw", "upstream": []},
        {"id": "gate_raw_mart_base", "kind": "gate", "layer": "raw", "upstream": ["raw_base"]}]}}
    if load is not None:
        other["load"] = load
    return other


def external(tmp_path, monkeypatch, mine, theirs):
    monkeypatch.setattr(l0_dag, "fetch_approved", lambda root: None)
    monkeypatch.setattr(l0_dag, "git_show_approved", lambda root, rel: json.dumps(other_contract(theirs)))
    c = copy.deepcopy(VALID)
    if mine is not None:
        c["load"] = mine
    c["dag"]["tasks"][2]["upstream"].append("mart_base:gate_raw_mart_base")
    paths = build(tmp_path, c)
    return l0_dag.check_external(paths, c)


@pytest.mark.parametrize("mine,theirs", [
    (None, None), ({"mode": "snapshot"}, None), (None, {"mode": "snapshot"}), (INCREMENTAL, INCREMENTAL),
    (INCREMENTAL, {**INCREMENTAL, "date_column": "other_at", "allow_empty_days": True}),  # 원천 컬럼은 달라도 됨
])
def test_borrow_same_load_mode_passes(tmp_path, monkeypatch, mine, theirs):
    assert external(tmp_path, monkeypatch, mine, theirs) == []


@pytest.mark.parametrize("mine,theirs,message", [
    (INCREMENTAL, None, "적재 방식이 다름 (이 마트 load.mode incremental, mart_base snapshot"),
    (None, INCREMENTAL, "적재 방식이 다름 (이 마트 load.mode snapshot, mart_base incremental"),
    (INCREMENTAL, {**INCREMENTAL, "partition_column": "event_date"}, "load.partition_column이 다름"),
])
def test_borrow_different_load_mode_fails(tmp_path, monkeypatch, mine, theirs, message):
    found = external(tmp_path, monkeypatch, mine, theirs)
    assert len(found) == 1 and message in found[0], found


def test_ladder_halts_on_borrow_load_mode_mismatch(tmp_path, monkeypatch):
    # upstream·load는 contract(사람 결재 파일)에 있으므로 반려가 아니라 halt input_invalid (결정 59 판정 원칙)
    monkeypatch.setattr(l0_dag, "fetch_approved", lambda root: None)
    monkeypatch.setattr(l0_dag, "git_show_approved", lambda root, rel: json.dumps(other_contract()))
    c = inc_contract()
    c["dag"]["tasks"][2]["upstream"].append("mart_base:gate_raw_mart_base")
    build_inc(tmp_path, c)
    code, fake = run(tmp_path)
    assert code == 2 and fake.calls == []
    assert input_halt(tmp_path, "raw_example", "적재 방식이 다름")["rungs"] == []


# ---------- 사다리 ds 창과 ai_dev 만료 사전 검사 (결정 79) ----------

class ExpiringBq(FakeBq):
    """ai_dev 조회(bq show)에 기본 파티션 만료(defaultPartitionExpirationMs)를 함께 돌려준다."""

    def __init__(self, expiration_ms, **kw):
        super().__init__(**kw)
        self.expiration_ms = expiration_ms

    def __call__(self, args, env, stdin=None):
        if args[:2] == ["bq", "show"]:
            self.shows.append(args)
            info = {"location": hc.load()["source"]["location"]}
            if self.expiration_ms is not None:
                info["defaultPartitionExpirationMs"] = str(self.expiration_ms)
            return 0, json.dumps(info), ""
        return super().__call__(args, env, stdin)


SEVEN_DAYS_MS = 7 * 86400000


def test_incremental_accepts_past_ds(tmp_path):
    build_inc(tmp_path)
    code, fake = run(tmp_path, "--ds", "2025-01-15")
    assert code == 0, result(tmp_path, "raw_example")
    assert all(result(tmp_path, t)["verdict"] == "pass" for t in ("raw_example", "stg_example", "mart_example_daily"))
    assert result(tmp_path, "raw_example")["rungs"][1]["ds"] == "2025-01-15"
    assert len(fake.shows) == 1


def test_incremental_rejects_future_ds(tmp_path, capsys):
    build_inc(tmp_path)
    code, fake = run(tmp_path, "--ds", str(TODAY + timedelta(days=1)))
    assert code == 2 and fake.calls == [] and result(tmp_path, "raw_example") is None
    assert "이전이어야 함" in capsys.readouterr().err


@pytest.mark.parametrize("load", [None, {"mode": "snapshot"}])
def test_snapshot_still_rejects_old_ds(tmp_path, load, capsys):
    c = copy.deepcopy(VALID)
    if load is not None:
        c["load"] = load
    build(tmp_path, c)
    code, fake = run(tmp_path, "--ds", str(TODAY - timedelta(days=7)))
    assert code == 2 and fake.calls == []
    assert "최근 7일" in capsys.readouterr().err


def test_l5_measures_partition_column(tmp_path):
    build_inc(tmp_path)
    code, fake = run(tmp_path, "--ds", "2025-01-15")
    assert code == 0
    measured = [a[-1] for a in fake.calls if a[0] == "bq" and a[-1] and "row_count" in a[-1]]
    assert measured and all(f"WHERE {PC} = DATE('2025-01-15')" in sql for sql in measured)
    assert not any("snapshot_date" in sql for sql in measured)


def test_l5_snapshot_still_measures_snapshot_date(tmp_path):
    build(tmp_path)
    code, fake = run(tmp_path)
    measured = [a[-1] for a in fake.calls if a[0] == "bq" and a[-1] and "row_count" in a[-1]]
    assert code == 0 and measured and all("WHERE snapshot_date = DATE('2026-10-30')" in sql for sql in measured)


@pytest.mark.parametrize("age_days,expiration_ms,ok", [
    (6, SEVEN_DAYS_MS, True),      # 날짜 D 파티션은 D + 7일 00:00에 지워진다. 6일 전은 아직 남음
    (7, SEVEN_DAYS_MS, False),
    (300, SEVEN_DAYS_MS, False),
    (300, None, True),             # 기본 파티션 만료 없음 (사람이 바꾼 뒤의 설정)
    (300, 0, True),
    (30, 60 * 86400000, True),
])
def test_incremental_ai_dev_expiration_check(tmp_path, age_days, expiration_ms, ok):
    build_inc(tmp_path)
    fake = ExpiringBq(expiration_ms)
    code, _ = run(tmp_path, "--ds", str(TODAY - timedelta(days=age_days)), fake=fake)
    assert len(fake.shows) == 1  # 리전 확인과 같은 bq show 한 번
    if ok:
        assert code == 0
    else:
        assert code == 2 and fake.calls[-1][0] == "gcloud"  # 인증 뒤, 첫 쿼리 전에 멈춤
        r = input_halt(tmp_path, "raw_example", "기본 파티션 만료(7일)보다 오래된 ds")
        assert [g["rung"] for g in r["rungs"]] == ["L0"]


def test_snapshot_ignores_ai_dev_expiration(tmp_path):
    build(tmp_path)
    fake = ExpiringBq(86400000)  # 1일이어도 snapshot은 DDL 자체 만료라 보지 않는다
    code, _ = run(tmp_path, fake=fake)
    assert code == 0 and len(fake.shows) == 1


def test_unreadable_expiration_is_infra(tmp_path):
    build_inc(tmp_path)
    code, _ = run(tmp_path, "--ds", "2025-01-15", fake=ExpiringBq("seven days"))
    r = result(tmp_path, "raw_example")
    assert code == 2 and r["verdict"] == "halt" and r["halt_reason"] == "infra_error"


# ---------- 정의서 파티션 필터 (결정 79) ----------

def test_table_spec_partition_filter_follows_contract():
    sys.path.insert(0, str(ROOT / "scripts" / "deliverables"))
    import table_spec
    sql = (f"SELECT a.order_id FROM `p.d.stg_x` AS a JOIN `p.d.raw_y` AS b ON a.{PC} = b.{PC} "
           f"WHERE a.{PC} = DATE('{{{{ ds }}}}') AND a.order_id IS NULL")
    kept = " ".join(s.text for s in table_spec.segments(sql, table_spec.partition_filter(PC)))
    assert PC not in kept and "order_id is null" in kept
    default = " ".join(s.text for s in table_spec.segments(sql))  # 기본은 snapshot_date만 지운다
    assert PC in default
    assert table_spec.PARTITION_FILTER.pattern == table_spec.partition_filter("snapshot_date").pattern


# ---------- 게이트 allow_empty_days (결정 79 ⑤) ----------
# 게이트 검사 SQL은 verifier가 쓰고(_checks/l3) gen_dq.py는 감싸기만 하므로, 행 0 통과는 verifier 안내로 정한다.

def test_verifier_drops_empty_day_check_when_allowed():
    text = (ROOT / ".claude" / "agents" / "verifier.md").read_text(encoding="utf-8")
    line = next(x for x in text.splitlines() if "allow_empty_days" in x)
    assert "해당 날짜 행 있음" in line and "쓰지 않는다" in line


def test_allow_empty_days_needs_incremental():
    c = copy.deepcopy(VALID)
    c["load"] = {"mode": "snapshot", "allow_empty_days": True}  # snapshot은 매일 원천 전체라 빈 날이 없다
    assert l0.check_contract(c)["status"] == "fail"
    assert load_mode.allow_empty_days(c) is False


def test_gate_generation_is_unchanged_by_load(tmp_path):
    # gen_dq는 load를 보지 않는다. 같은 l3 원본이면 snapshot·incremental 게이트 파일 내용이 같다
    import gen_dq
    snap = gen_dq.generate(build(tmp_path / "a"), VALID)
    inc = gen_dq.generate(build_inc(tmp_path / "b"), inc_contract())
    assert sorted((p.name, t) for p, t in snap.items()) == sorted((p.name, t) for p, t in inc.items())
