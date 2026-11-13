"""L0 ③ SQL과 contract 대조 시험 (결함 주입 후속, 시험 뒤 고침). 예시는 직접 만든 작은 SQL·contract다."""
import copy
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "ladder"))
import common  # noqa: E402
import l0_dag  # noqa: E402
from test_l0_contract import VALID  # noqa: E402
from test_ladder import build, result, run  # noqa: E402

MART_SQL = "dags/sql/mart/mart_example_daily.sql"
DDL = "CREATE TABLE IF NOT EXISTS `{{{{ project }}}}.{{{{ dataset_mart }}}}.mart_example_daily`\n({ddl})\nPARTITION BY snapshot_date;\n"
INSERT = "INSERT INTO `{{{{ project }}}}.{{{{ dataset_mart }}}}.mart_example_daily`\n  ({cols})\n{select};\n"
SELECT = "SELECT DATE('{{ ds }}') AS snapshot_date, example_date, 1 AS example_metric"


def mart_sql(ddl="snapshot_date DATE, example_date DATE, example_metric INT64",
             cols="snapshot_date, example_date, example_metric", select=SELECT):
    return DDL.format(ddl=ddl) + INSERT.format(cols=cols, select=select)


def ratio_contract():
    c = copy.deepcopy(VALID)
    c["interview"]["metrics"][0].update(numerator="example_a_cnt", denominator="example_b_cnt")
    return c


def errors(tmp_path, sql, contract=None):
    paths = build(tmp_path, contract)
    (tmp_path / MART_SQL).write_text(sql, encoding="utf-8")
    return l0_dag.check_sql_contract(paths, contract or VALID)


def ratio_select(expr):
    return f"SELECT DATE('{{{{ ds }}}}') AS snapshot_date, example_date, {expr} FROM t"


@pytest.mark.parametrize("expr", [
    "a.x / a.y AS example_metric",
    "DIV(a.x, a.y) AS example_metric",
    "IEEE_DIVIDE(a.x, a.y) AS example_metric",
    "a.x AS example_metric",
    "SAFE_DIVIDE(a.x, a.y) / 100 AS example_metric",
    "ROUND(a.x / a.y, 2) as example_metric",
])
def test_ratio_without_safe_divide_fails(tmp_path, expr):
    found = errors(tmp_path, mart_sql(select=ratio_select(expr)), ratio_contract())
    assert len(found) == 1 and "mart_example_daily.example_metric" in found[0] and "SAFE_DIVIDE" in found[0]


@pytest.mark.parametrize("expr", [
    "SAFE_DIVIDE(a.x, a.y) AS example_metric",
    "safe_divide(CAST(a.x AS NUMERIC), CAST(a.y AS NUMERIC)) AS example_metric",
    "SAFE_DIVIDE(a.x, a.y) AS example_metric -- 나누기 a / b 메모",
    "a.y AS other, SAFE_DIVIDE(a.x, a.y) AS example_metric",
])
def test_ratio_with_safe_divide_passes(tmp_path, expr):
    assert errors(tmp_path, mart_sql(select=ratio_select(expr) + "\n"), ratio_contract()) == []


def test_ratio_passed_through_outer_select_passes(tmp_path):
    select = ("SELECT b.example_date, b.example_metric AS example_metric "
              "FROM (SELECT example_date, SAFE_DIVIDE(x, y) AS example_metric FROM t) AS b")
    assert errors(tmp_path, mart_sql(select=select), ratio_contract()) == []


def test_division_in_other_column_is_not_judged(tmp_path):
    select = ratio_select("a.x / a.y AS other, SAFE_DIVIDE(a.x, a.y) AS example_metric")
    assert errors(tmp_path, mart_sql(select=select), ratio_contract()) == []


def test_metric_without_ratio_fields_is_not_judged(tmp_path):
    assert errors(tmp_path, mart_sql(select=ratio_select("a.x / a.y AS example_metric"))) == []


def test_ladder_rejects_at_l0_without_bq(tmp_path):
    build(tmp_path, ratio_contract())
    (tmp_path / MART_SQL).write_text(mart_sql(select=ratio_select("a.x / a.y AS example_metric")), encoding="utf-8")
    code, fake = run(tmp_path)
    assert code == 1 and fake.calls == []
    rung = result(tmp_path, "raw_example")["rungs"][0]
    assert (rung["rung"], rung["error_type"], rung["error_class"]) == ("L0", "dag_structure_mismatch", "syntax")
    assert any("SAFE_DIVIDE" in e for e in rung["metrics"]["errors"])


def test_structure_failure_comes_first(tmp_path):
    build(tmp_path)
    (tmp_path / MART_SQL).unlink()
    code, _ = run(tmp_path)
    assert code == 1
    assert any("SQL 파일이 없음" in e for e in result(tmp_path, "raw_example")["rungs"][0]["metrics"]["errors"])


