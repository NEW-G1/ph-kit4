"""L2 ai_dev 실행 (03 §5.3).

렌더링 결과에 운영 데이터셋 이름(dags/harness_config.json)이 있으면 실행하지 않고 실패한다.
모든 실행에 --maximum_bytes_billed=524288000을 건다. 오류는 runtime_error·type_mismatch·cost_exceeded.
실행이 성공해도 contract의 테이블이 ai_dev에 없으면 반려 dag_structure_mismatch다. SQL이 다른 이름의 테이블을
만든 경우로, 테이블 이름은 builder 파일의 문제다 (결정 59, 마트 1 R-0001 후속). 확인 쿼리 자체의 실패는 infra_error
"""
import common


def execute(ctx, task):
    """task SQL을 ai_dev에서 1번 실행한다. 실패하면 QueryError."""
    sql = common.render(ctx.paths.task_sql(task).read_text(encoding="utf-8"), ctx.project, ctx.ds)
    common.check_prod(sql)
    ctx.bq.run(sql, max_rows=1)


def table_exists(ctx, table):
    """ai_dev에 테이블이 있나. 하네스가 쓰는 확인 쿼리라 실패하면 InfraError."""
    sql = (f"SELECT COUNT(*) AS n\n"
           f"FROM `{ctx.project}.{common.DEV_DATASET}.INFORMATION_SCHEMA.TABLES`\n"
           f"WHERE table_name = '{table}'")
    try:
        ctx.bq.dry_run(sql)
        rows = ctx.bq.run(sql, max_rows=1)
    except common.QueryError as e:
        raise common.InfraError(f"테이블 확인 쿼리 실패: {e}") from None
    return bool(rows) and int(rows[0].get("n") or 0) > 0


def run(ctx, task):
    try:
        execute(ctx, task)
    except common.QueryError as e:
        return common.rung("L2", str(ctx.ds), {"message": str(e)}, e.error_type)
    table = common.table_of(ctx.contract, task["id"])["name"]
    if not table_exists(ctx, table):
        return common.rung("L2", str(ctx.ds), {"table": table, "message": (
            f"SQL 실행은 성공했지만 contract의 테이블 {table}이 {common.DEV_DATASET}에 없음. "
            "SQL이 만드는 테이블 이름을 contract의 tables[].name과 맞춘다")}, "dag_structure_mismatch")
    return common.rung("L2", str(ctx.ds), {"dataset": common.DEV_DATASET, "table": table})
