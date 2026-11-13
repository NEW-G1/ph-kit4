---
paths:
  - "dags/sql/**"
---
# SQL 작성 규칙
- 모든 적재 SQL은 멱등 3문장 패턴(docs/architecture/sql_rules.md 참조)을 따른다. 두 번 실행해도 결과가 같아야 한다.
- 데이터셋 이름은 직접 쓰지 않고 {{ dataset_raw }}·{{ dataset_stg }}·{{ dataset_mart }} 자리 표시를 쓴다. 사다리는 ai_dev, 운영은 운영 데이터셋으로 렌더링된다(현재 값은 dags/harness_config.json의 datasets).
- 먼저 contract의 load.mode를 보고 맞는 패턴을 쓴다(결정 79). 칸이 없거나 snapshot이면 sql_rules.md §1, incremental이면 §1-2.
- 파티션 기준 컬럼은 snapshot이면 snapshot_date, incremental이면 contract의 load.partition_column(데이터 날짜). 대상 파티션을 지우고 다시 쓰는 방식으로 재실행을 보장한다.
- 컬럼마다 설명(description)을 함께 작성한다. 이 설명이 OM, 납품 정의서, AgentGo 카드로 그대로 흘러간다.
