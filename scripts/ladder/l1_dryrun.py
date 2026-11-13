"""L1 SQL dry-run (03 §5.3, 결정 46).

task SQL을 ai_dev 기준으로 렌더링해 `bq query --dry_run`을 돌린다.
- 렌더링 전 SQL 원문에 운영 데이터셋 이름(dags/harness_config.json)이 있으면 dry-run 없이 hardcoded_dataset
  (sql_rules.md §2: 데이터셋 이름은 자리 표시로 쓴다)
- UTF-8로 읽지 못하는 SQL 파일·렌더링 실패·문법 오류 → syntax, 스캔 바이트 > 524288000 → cost_exceeded
- 여러 문장 스크립트의 dry-run은 앞 문장의 CREATE TABLE로 생길 테이블을 뒤 문장에서 인식하므로(10/30 확인)
  "테이블 없음" 예외를 두지 않는다. 스크립트의 바이트는 하한값이라 정확도를 함께 남긴다 (결정 59 ⑨)
"""
import common


def run(ctx, task):
    try:
        sql_text = ctx.paths.task_sql(task).read_text(encoding="utf-8")
    except UnicodeDecodeError as e:  # builder가 쓴 파일의 문제라 반려. halt는 하네스·인증·네트워크 문제에만 쓴다
        return common.rung("L1", str(ctx.ds), {"message": f"SQL 파일을 UTF-8로 읽지 못함: {e}. UTF-8로 저장한다"},
                           "syntax")
    hardcoded = common.prod_datasets().search(sql_text)
    if hardcoded:
        return common.rung("L1", str(ctx.ds), {"message": f"SQL 원문에 운영 데이터셋 이름 {hardcoded.group(0)!r}. "
                                                         "{{ dataset_raw }} 같은 자리 표시를 쓴다"},
                           "hardcoded_dataset")
    try:
        sql = common.render(sql_text, ctx.project, ctx.ds)
        n = ctx.bq.dry_run(sql)
    except common.QueryError as e:
        return common.rung("L1", str(ctx.ds), {"message": str(e)}, e.error_type)
    return common.rung("L1", str(ctx.ds), {"bytes_processed": n, "bytes_accuracy": ctx.bq.last_accuracy})
