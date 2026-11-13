"""3-3 스모크 시험용 예제 (.dev/checks/3-3_smoke.md). thelook 테이블을 읽지 않는 상수 테이블 3개.

마트 1의 정답이 될 SQL이 아니다. 사다리가 ai_dev에서 L0~L5를 한 바퀴 도는지만 본다.
contract는 test_l0_contract.VALID(mart_example)를 그대로 쓴다. sources 칸은 L0 형식 때문에 적혀 있을 뿐 SQL은 원천을 읽지 않는다.

  python tests/ladder_smoke_fixture.py <빈 폴더>
"""
import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "ladder"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402
import gen_dq  # noqa: E402
from test_l0_contract import VALID  # noqa: E402

MART = "mart_example"
DAG = """\"\"\"스모크 시험용 DAG 구조. 사다리는 이 파일을 실행하지 않고 UPSTREAM만 읽는다.\"\"\"
UPSTREAM = {
    "raw_example": [],
    "gate_raw_mart_example": ["raw_example"],
    "stg_example": ["gate_raw_mart_example"],
    "gate_stg_mart_example": ["stg_example"],
    "mart_example_daily": ["gate_stg_mart_example"],
    "gate_mart_mart_example": ["mart_example_daily"],
}
"""
TABLE = "`{{{{ project }}}}.{{{{ dataset_{layer} }}}}.{name}`"
SQL = {
    ("raw", "raw_example"): """CREATE TABLE IF NOT EXISTS {t}
(
  snapshot_date DATE OPTIONS (description = '실행 날짜'),
  example_id INT64 OPTIONS (description = '예시 키'),
  example_date DATE OPTIONS (description = '예시 날짜')
)
PARTITION BY snapshot_date
OPTIONS (partition_expiration_days = 7, description = '3-3 스모크 시험용 상수 테이블');

DELETE FROM {t} WHERE snapshot_date = DATE('{{{{ ds }}}}');

INSERT INTO {t} (snapshot_date, example_id, example_date)
SELECT DATE('{{{{ ds }}}}'), 1, DATE('{{{{ ds }}}}')
UNION ALL SELECT DATE('{{{{ ds }}}}'), 2, DATE('{{{{ ds }}}}');
""",
    ("stg", "stg_example"): """CREATE TABLE IF NOT EXISTS {t}
(
  snapshot_date DATE OPTIONS (description = '실행 날짜'),
  example_id INT64 OPTIONS (description = '예시 키'),
  example_date DATE OPTIONS (description = '예시 날짜')
)
PARTITION BY snapshot_date
OPTIONS (partition_expiration_days = 7, description = '3-3 스모크 시험용');

DELETE FROM {t} WHERE snapshot_date = DATE('{{{{ ds }}}}');

INSERT INTO {t} (snapshot_date, example_id, example_date)
SELECT DATE('{{{{ ds }}}}'), example_id, example_date
FROM {raw}
WHERE snapshot_date = DATE('{{{{ ds }}}}');
""",
    ("mart", "mart_example_daily"): """CREATE TABLE IF NOT EXISTS {t}
(
  snapshot_date DATE OPTIONS (description = '실행 날짜'),
  example_date DATE OPTIONS (description = '예시 날짜'),
  example_metric INT64 OPTIONS (description = '예시 건수')
)
PARTITION BY snapshot_date
OPTIONS (partition_expiration_days = 7, description = '3-3 스모크 시험용');

DELETE FROM {t} WHERE snapshot_date = DATE('{{{{ ds }}}}');

INSERT INTO {t} (snapshot_date, example_date, example_metric)
SELECT DATE('{{{{ ds }}}}'), example_date, COUNT(*)
FROM {stg}
WHERE snapshot_date = DATE('{{{{ ds }}}}')
GROUP BY example_date;
""",
}
RAW = TABLE.format(layer="raw", name="raw_example")
STG = TABLE.format(layer="stg", name="stg_example")
MRT = TABLE.format(layer="mart", name="mart_example_daily")
CHECKS = {
    "l3/C-01.sql": f"""-- error_type: duplicate_rows
-- task: stg_example

-- 키는 고유하다
SELECT example_id, COUNT(*) AS n
FROM {STG}
WHERE snapshot_date = DATE('{{{{ ds }}}}')
GROUP BY example_id
HAVING COUNT(*) > 1
""",
    "l4/C-02.sql": f"""-- error_type: join_missing
-- task: stg_example

-- 원천(raw) 대비 행 수 오차 0
SELECT raw_rows, stg_rows
FROM (
  SELECT
    (SELECT COUNT(*) FROM {RAW} WHERE snapshot_date = DATE('{{{{ ds }}}}')) AS raw_rows,
    (SELECT COUNT(*) FROM {STG} WHERE snapshot_date = DATE('{{{{ ds }}}}')) AS stg_rows
)
WHERE raw_rows != stg_rows
""",
    "l4/I-01.sql": f"""-- error_type: range_violation
-- task: mart_example_daily

-- 행 유실 없음: mart 건수 합 = stg 행 수
SELECT mart_sum, stg_rows
FROM (
  SELECT
    (SELECT SUM(example_metric) FROM {MRT} WHERE snapshot_date = DATE('{{{{ ds }}}}')) AS mart_sum,
    (SELECT COUNT(*) FROM {STG} WHERE snapshot_date = DATE('{{{{ ds }}}}')) AS stg_rows
)
WHERE mart_sum != stg_rows
""",
}


def build(root):
    root = Path(root)
    contract = copy.deepcopy(VALID)
    req = root / "docs" / "requirements"
    req.mkdir(parents=True, exist_ok=True)
    (req / f"{MART}.contract.json").write_text(json.dumps(contract, ensure_ascii=False, indent=2), encoding="utf-8")
    for rel, text in CHECKS.items():
        f = req / f"{MART}_checks" / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(text, encoding="utf-8")
    (root / "dags").mkdir(parents=True, exist_ok=True)
    (root / "dags" / "harness_daily.py").write_text(DAG, encoding="utf-8")
    for (layer, name), text in SQL.items():
        f = root / "dags" / "sql" / layer / f"{name}.sql"
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(text.format(t=TABLE.format(layer=layer, name=name), raw=RAW, stg=STG), encoding="utf-8")
    paths = common.Paths(root, MART)
    for path, text in gen_dq.generate(paths, contract).items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
    return paths


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("사용법: python tests/ladder_smoke_fixture.py <빈 폴더>", file=sys.stderr)
        sys.exit(2)
    target = Path(sys.argv[1])
    if target.exists() and any(target.iterdir()):
        print(f"빈 폴더가 아님: {target}", file=sys.stderr)
        sys.exit(2)
    build(target)
    print(f"스모크 예제를 만들었다: {target}")
