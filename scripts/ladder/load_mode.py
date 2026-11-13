"""적재 방식 (결정 79). contract의 선택 칸 load에서 적재 방식과 파티션 컬럼을 정하는 곳은 여기 하나다.

  "load": {"mode": "incremental", "date_column": "<원천 시각·날짜 컬럼>", "partition_column": "<우리 파티션 컬럼>",
           "allow_empty_days": false}

- load 칸이 없으면 snapshot(기본값, 지금 방식). snapshot이면 다른 칸을 두지 않는다
- 형식 검사는 L0(l0_contract.Checker.load)가 한다. 여기 함수는 L0 전에 불려도(사다리의 ds 창) 터지지 않게
  모양이 틀린 값은 snapshot으로 읽는다. 틀린 contract는 곧 L0가 멈춘다
- 쓰는 곳: L0(l0_contract·l0_dag), 사다리 ds 창·ai_dev 만료 검사(run_ladder), L5(l5_idem), 정의서(table_spec)
"""
SNAPSHOT = "snapshot"
INCREMENTAL = "incremental"
MODES = (SNAPSHOT, INCREMENTAL)
SNAPSHOT_COLUMN = "snapshot_date"
FIELDS = {SNAPSHOT: ("mode",), INCREMENTAL: ("mode", "date_column", "partition_column")}
OPTIONAL = {SNAPSHOT: (), INCREMENTAL: ("allow_empty_days",)}


def _load(contract):
    load = contract.get("load") if isinstance(contract, dict) else None
    return load if isinstance(load, dict) else {}


def mode(contract):
    """snapshot 또는 incremental. 칸이 없거나 모양이 틀리면 snapshot."""
    value = _load(contract).get("mode")
    return value if value in MODES else SNAPSHOT


def is_incremental(contract):
    return mode(contract) == INCREMENTAL


def partition_column(contract):
    """우리 테이블의 파티션 컬럼. snapshot이면 snapshot_date, incremental이면 load.partition_column."""
    if is_incremental(contract):
        value = _load(contract).get("partition_column")
        if isinstance(value, str) and value:
            return value
    return SNAPSHOT_COLUMN


def date_column(contract):
    """원천의 시각·날짜 컬럼. snapshot이면 None."""
    value = _load(contract).get("date_column") if is_incremental(contract) else None
    return value if isinstance(value, str) and value else None


def allow_empty_days(contract):
    """데이터가 없는 날(해당 날짜 행 0)을 통과로 보는지. incremental에서만 true일 수 있다."""
    return is_incremental(contract) and _load(contract).get("allow_empty_days") is True
