"""harness_daily: pipeline-harness 마트 파이프라인 DAG.

- 공통 설정: docs/architecture/design_principles.md §4 (schedule None, catchup False, max_active_runs 1)
- task 1개 = SQL 파일 1개 = 테이블 1개. 적재는 dags/sql/<raw|stg|mart>/<task>.sql, 게이트는 dags/sql/dq/<task>.sql
- 의존성은 아래 리터럴 UPSTREAM dict 하나로 정한다. 사다리 L0가 contract의 dag.tasks와 대조한다 (결정 59)
- 데이터셋 이름·위치는 같은 폴더의 harness_config.json에서 읽어 user_defined_macros로 고정해서 넣는다. 실행 시 conf로 바꿀 수 없다 (sql_rules.md §2)
"""
import json
import os
from pathlib import Path

import pendulum
from airflow import DAG
from airflow.models.param import Param
from airflow.providers.google.cloud.operators.bigquery import BigQueryInsertJobOperator

# task id: [상류 task id]. contract의 dag.tasks와 같아야 한다 (task id만 적는다)
UPSTREAM = {}

SQL_ROOT = "/opt/airflow/dags/harness/sql"
CONFIG = json.loads(Path(__file__).with_name("harness_config.json").read_text(encoding="utf-8"))
LOCATION = CONFIG["source"]["location"]  # location은 템플릿 필드가 아니므로 파일을 읽을 때 정한다

MACROS = {
    # 프로젝트 ID는 환경변수 이름만 참조한다 (값을 코드에 적지 않음)
    "project": os.environ.get("GCP_PROJECT_ID", ""),
    "dataset_raw": CONFIG["datasets"]["raw"],
    "dataset_stg": CONFIG["datasets"]["stg"],
    "dataset_mart": CONFIG["datasets"]["mart"],
}


def sql_path(task_id):
    """task id에서 SQL 파일 경로(template_searchpath 기준)를 만든다. 게이트는 dq/."""
    if task_id.startswith("gate_"):
        return f"dq/{task_id}.sql"
    return f"{task_id.split('_', 1)[0]}/{task_id}.sql"


with DAG(
    dag_id="harness_daily",
    schedule=None,
    start_date=pendulum.datetime(2026, 11, 1, tz="UTC"),
    catchup=False,
    max_active_runs=1,
    template_searchpath=[SQL_ROOT],
    user_defined_macros=MACROS,
    params={"force_fail": Param(False, type="boolean", description="참이면 게이트의 강제 실패 검사가 실패")},
    tags=["harness"],
) as dag:
    tasks = {}
    for task_id in UPSTREAM:
        tasks[task_id] = BigQueryInsertJobOperator(
            task_id=task_id,
            location=LOCATION,
            configuration={
                "query": {
                    "query": "{% include '" + sql_path(task_id) + "' %}",
                    "useLegacySql": False,
                }
            },
            retries=0 if task_id.startswith("gate_") else 1,
        )
    for task_id, ups in UPSTREAM.items():
        for up in ups:
            tasks[up] >> tasks[task_id]
