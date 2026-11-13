# SQL 작성 규칙

> 적재 SQL과 검증 쿼리를 쓸 때 지키는 규칙입니다. builder는 SQL을 쓰기 전에, verifier는 검증 쿼리를 쓰기 전에 읽습니다. `.claude/rules/sql-idempotent.md`가 `dags/sql/**` 작업 때 이 문서를 가리킵니다.
> 1단계 정답지(`baseline-v1`)의 `pipeline_design.md` §18에서 **규칙만** 옮겼습니다. 실제 테이블의 SQL 본문은 옮기지 않았습니다.
> 아래 SQL의 `<...>`는 자리 표시입니다.

---

## 1. 멱등 3문장 패턴

- 모든 적재 SQL 파일은 세미콜론으로 구분한 3개 문장으로 만듭니다.
- BigQuery는 이를 멀티 스테이트먼트 스크립트로 실행합니다.
- 같은 날짜로 두 번 실행해도 결과가 같아야 합니다.

**먼저 contract의 `load.mode`를 봅니다.** 칸이 없거나 `snapshot`이면 아래 패턴(기본값)을 씁니다. `incremental`이면 [§1-2 증분 적재 패턴](#1-2-증분-적재-패턴-contract-loadmode--incremental-결정-79)을 씁니다. (결정 79)

```sql
-- (1) 테이블이 없을 때만 생성: 명시적 DDL + 테이블·컬럼 설명
CREATE TABLE IF NOT EXISTS `{{ project }}.{{ dataset_<layer> }}.<table>`
(
  snapshot_date DATE OPTIONS (description = '실행 날짜 (Airflow ds). 파티션 키'),
  <column_1> <TYPE> OPTIONS (description = '<설명>'),
  <column_2> <TYPE> OPTIONS (description = '<설명>')
)
PARTITION BY snapshot_date
CLUSTER BY <자주 조인·필터하는 컬럼>
OPTIONS (
  partition_expiration_days = <7 또는 90>,
  description = '<테이블 설명. 소스 테이블 포함>'
);

-- (2) 당일 파티션 삭제
DELETE FROM `{{ project }}.{{ dataset_<layer> }}.<table>`
WHERE snapshot_date = DATE('{{ ds }}');

-- (3) 당일 파티션 적재
INSERT INTO `{{ project }}.{{ dataset_<layer> }}.<table>`
  (snapshot_date, <column_1>, <column_2>)
SELECT
  DATE('{{ ds }}') AS snapshot_date,
  <expr_1>,
  <expr_2>
FROM `{{ project }}.{{ dataset_<upstream_layer> }}.<upstream_table>`
WHERE snapshot_date = DATE('{{ ds }}');
```

| 문장 | 규칙 | 이유 |
|---|---|---|
| (1) | `CREATE TABLE IF NOT EXISTS` + 컬럼 타입과 설명을 직접 적는다 | 집계 타입을 고정하고, 설명이 OM, 정의서, 카드로 흘러감 |
| (1) | raw만 예외적으로 `CREATE TABLE IF NOT EXISTS ... AS SELECT *, ... FROM <원천> WHERE FALSE`로 원천 스키마를 복사할 수 있다 | 원천 컬럼을 그대로 보관하는 레이어. 이때도 테이블 설명은 넣는다 |
| (1) | `PARTITION BY snapshot_date`. 만료는 raw, stg 7일, mart 90일 | [design_principles.md §2](design_principles.md#2-레이어-구조) |
| (1) | `CLUSTER BY`는 다음 레이어에서 조인, GROUP BY, 필터에 쓰는 컬럼 순서로 | 스캔량과 조인 비용 감소 |
| (2) | `DELETE ... WHERE snapshot_date = DATE('{{ ds }}')` | 재실행 시 기존 데이터를 지움. **멱등성의 핵심** |
| (3) | `INSERT INTO ... (컬럼 목록) SELECT` | 소스에서 대상으로 가는 관계가 SQL 텍스트에 드러나 리니지 파싱 가능. stg부터는 컬럼을 반드시 명시 |
| (3) | 상위 테이블은 `snapshot_date = DATE('{{ ds }}')`만 읽는다 | 스냅샷마다 원천 전체가 들어 있음 (현재 원천은 매일 재생성됨, design_principles.md §1) |

**주의**
- `CREATE TABLE IF NOT EXISTS`는 이미 있는 테이블의 옵션을 바꾸지 않습니다. 만료 등을 바꾸려면 `ALTER TABLE ... SET OPTIONS`를 따로 실행합니다(사람 결재 대상).
- raw의 `INSERT ... SELECT *`는 컬럼 **순서**로 들어갑니다. 원천 스키마가 바뀌면 실패할 수 있습니다.
- description 문자열은 작은따옴표로 감싸고 `{`, `}`, `{%`를 넣지 않습니다. SQL 파일이 Jinja로 렌더링되기 때문입니다.

### 1-2. 증분 적재 패턴 (contract `load.mode` = `incremental`, 결정 79)

- 적재 방식은 contract의 `load` 칸으로 마트마다 정하고, 결재 1에서 사람이 승인합니다.
- 칸이 없거나 `snapshot`이면 위 §1 패턴(기본값)입니다.
- `incremental`은 원천이 커서 매일 전체를 복사할 수 없고, 원천에 날짜 파티션이 있을 때 씁니다.
- 같은 멱등 3문장 패턴입니다. 다만 파티션 컬럼이 실행 날짜가 아니라 **데이터 날짜**(`load.partition_column`)입니다.

```sql
-- (1) 테이블이 없을 때만 생성. partition_expiration_days는 두지 않는다
CREATE TABLE IF NOT EXISTS `{{ project }}.{{ dataset_<layer> }}.<table>`
(
  <partition_column> DATE OPTIONS (description = '데이터 날짜 (원천 <date_column>의 날짜). 파티션 키'),
  <column_1> <TYPE> OPTIONS (description = '<설명>')
)
PARTITION BY <partition_column>
CLUSTER BY <자주 조인·필터하는 컬럼>
OPTIONS (description = '<테이블 설명. 소스 테이블 포함>');

-- (2) 그 데이터 날짜 파티션 삭제
DELETE FROM `{{ project }}.{{ dataset_<layer> }}.<table>`
WHERE <partition_column> = DATE('{{ ds }}');

-- (3) 그 데이터 날짜 파티션 적재. raw는 원천에서 그 날짜 조각만 읽는다
INSERT INTO `{{ project }}.{{ dataset_raw }}.raw_<table>` (<partition_column>, <column_1>)
SELECT DATE(<date_column>) AS <partition_column>, <column_1>
FROM `<원천_프로젝트>.<원천_데이터셋>.<table>`
WHERE DATE(<date_column>) = DATE('{{ ds }}');

-- (3) stg·mart는 상류의 같은 데이터 날짜 파티션만 읽는다
-- INSERT INTO ... SELECT ... FROM `{{ project }}.{{ dataset_<upstream_layer> }}.<upstream_table>`
-- WHERE <partition_column> = DATE('{{ ds }}');
```

| 문장 | 규칙 | 이유 |
|---|---|---|
| (1) | `PARTITION BY <partition_column>`. 모든 층의 테이블에 같은 이름의 DATE 컬럼을 둔다(contract `tables[].columns`, L0) | stg, mart가 같은 데이터 날짜 파티션을 잇는다 |
| (1) | `partition_expiration_days`를 두지 않는다 | 과거 데이터 날짜가 곧 보관 대상이다. 만료를 두면 운영에서 과거 파티션이 지워진다 |
| (2) | `DELETE ... WHERE <partition_column> = DATE('{{ ds }}')` | 같은 날짜로 재실행해도 그 날짜만 지우고 다시 쓴다(멱등) |
| (3) raw | 원천에서 `DATE(<date_column>) = DATE('{{ ds }}')`만 읽는다 | 원천 날짜 파티션만 스캔해 쿼리당 500 MB 상한 안에 둔다 |
| (3) stg, mart | 상류는 `<partition_column> = DATE('{{ ds }}')`만 읽는다 | 그 날짜 조각만으로 계산한다 |

- `{{ ds }}`는 실행 날짜가 아니라 **적재할 데이터 날짜**입니다. 사다리는 incremental이면 과거 `--ds`를 받습니다(미래는 거부).
- 지원하는 지표는 **일 단위 지표**뿐입니다(그 날짜 파티션만 읽음). 최근 N일, 누적 같은 기간 지표는 동결 뒤 과제입니다.
- L0가 위 조건을 텍스트로 검사합니다. 빠지면 반려(`dag_structure_mismatch`)입니다.
  - (1) `PARTITION BY`와 만료 없음
  - (2) DELETE 조건
  - (3) raw의 원천 날짜 조건, stg와 mart의 상류 파티션 조건
- L0는 조건이 WHERE와 ON 중 어디에 있는지, 모든 상류에 걸렸는지는 보지 않습니다. 이것은 리뷰에서 봅니다.
- 범위 밖:
  - 운영 DAG의 backfill, catchup, 비용 상한
  - 여러 원천
  - 와일드카드 테이블
  - BigQuery 밖 엔진

---

## 2. 데이터셋 이름 파라미터

같은 SQL 파일을 결재 전 검증(`ai_dev`)과 결재 후 운영 데이터셋에 그대로 씁니다. 검증한 코드와 운영 코드가 같다는 것을 보장하기 위해서입니다. 운영 데이터셋 이름의 현재 값은 `dags/harness_config.json`의 `datasets`입니다.

| 자리 표시 | 검증 사다리 (결재 전, PC의 bq) | Airflow 운영 실행 (결재 후) |
|---|---|---|
| `{{ project }}` | GCP 프로젝트 ID | GCP 프로젝트 ID |
| `{{ dataset_raw }}` | `ai_dev` | `datasets.raw` |
| `{{ dataset_stg }}` | `ai_dev` | `datasets.stg` |
| `{{ dataset_mart }}` | `ai_dev` | `datasets.mart` |
| `{{ ds }}` | 사다리가 지정한 실행 날짜 | Airflow 실행 날짜 |

- SQL 파일에 데이터셋 이름을 직접 쓰지 않습니다. 원천(`<source.project>.<source.dataset>`)만 예외입니다.
  - 원천의 현재 값은 `dags/harness_config.json`의 `source`입니다.
  - 원천을 바꾸면 raw SQL의 원천 경로도 함께 바꿉니다.
- `ai_dev`에는 세 레이어가 한 데이터셋에 모입니다. 그래서 테이블 이름의 레이어 접두사(`raw_`, `stg_`, `mart_`)가 곧 구분자입니다.
- 렌더링은 실행 전에 끝납니다. 그래서 BigQuery에 도착하는 SQL에는 전체 경로 테이블명이 그대로 남습니다. §4의 "변수 금지"와 충돌하지 않습니다.
- 렌더링하는 곳:
  - Airflow: `dags/harness_daily.py`의 `user_defined_macros`로 `dags/harness_config.json`의 데이터셋 이름을 고정해 넣습니다. 프로젝트 ID는 서버 환경변수 `GCP_PROJECT_ID`에서 읽습니다. 운영 실행에서 실행 시 conf로 데이터셋을 바꿀 수 없습니다.
  - 사다리: `scripts/ladder/common.py`의 `render`(jinja2 `StrictUndefined`)로 렌더링합니다.

---

## 3. 집계 SQL 작성 규칙

| 규칙 | 이유 |
|---|---|
| 0으로 나눌 수 있는 비율은 `SAFE_DIVIDE` | 분모가 0인 그룹에서 오류 대신 NULL |
| 같은 `SELECT`에서 만든 별칭을 다른 식에서 참조하지 않는다. 필요하면 집계식을 반복하거나 서브쿼리로 감싼다 | BigQuery는 같은 SELECT 안의 별칭 참조를 허용하지 않음 |
| 조건부 집계는 `COUNTIF`, `SUM(IF(...))`, `COUNT(DISTINCT IF(..., 키, NULL))` | 한 번의 GROUP BY로 여러 기준 지표를 계산 |

**실험 조건** (01 §6.2, P8)
- 1단계에서 얻은 도메인 교훈은 이 문서와 규칙 파일에 예방 규칙으로 미리 넣지 않습니다.
- verifier가 요구서만 보고 쓰는 일반 불변 조건(탐지)은 그대로 둡니다.
- 탐지된 반려가 반복되면 규칙 승격 흐름(`.claude/rules/learned/`)으로 예방이 생기는지 봅니다(11/6 기준 승격 0건).
- 모든 마트에 같은 조건이며, 발표에서도 이 사실을 밝힙니다.

---

## 4. 리니지 친화 SQL 규칙

OM은 BigQuery 쿼리 이력의 SQL 텍스트를 파싱해서 리니지를 만듭니다. 파서가 읽을 수 있는 형태로 씁니다.

| 규칙 | 이유 |
|---|---|
| 테이블은 항상 `` `project.dataset.table` `` 전체 경로, 백틱 하나로 감싼다 | 파서가 테이블을 정확히 식별 |
| `INSERT INTO ... SELECT` 또는 `CREATE TABLE ... AS SELECT` 형태 | 대상과 소스가 한 문장에 드러남 |
| `INSERT` 안의 중간 집계는 FROM 절 서브쿼리로 쓴다. `INSERT ... WITH`(CTE)는 피한다 | 파서는 CTE를 해석하지만 `INSERT ... WITH` 형태의 호환성은 보수적으로 판단 |
| 임시 테이블 금지 | 리니지 중간 노드가 사라져 연결이 끊김 |
| `DECLARE` / `SET` 변수 금지 | 실제 값이 쿼리 텍스트에 남지 않음 |
| `EXECUTE IMMEDIATE`(동적 SQL) 금지 | 실행 시점에 SQL이 만들어져 파싱 불가 |
| 레이어 게이트 SQL에는 `INSERT`, `CREATE`, `DELETE`를 넣지 않는다 | 조회만 해서 리니지에 엣지를 만들지 않음 |

---

## 5. 알려진 현상과 결정

| 항목 | 결정 | 이유 |
|---|---|---|
| 자기 자신 고리 엣지 | 3문장 패턴의 `DELETE FROM 대상` 때문에 OpenLineage 리니지에 자기 자신으로 돌아오는 엣지가 생긴다. 알려진 현상으로 수용 | 대안인 파티션 덮어쓰기(`destinationTable` + `WRITE_TRUNCATE`)는 쿼리 기반 리니지가 생기지 않음. 쿼리 기반 리니지와 OpenLineage를 모두 유지하기 위해 3문장 패턴 유지 |
| 멀티 스테이트먼트 SQL | 3문장을 한 파일, 한 task로 실행 | OM이 멀티 스테이트먼트에서도 리니지를 만드는 것을 1단계에서 확인 |
| 새 테이블의 리니지 | 새 테이블은 BigQuery Metadata Agent가 먼저 OM에 등록해야 OpenLineage 엣지가 붙는다 | 결재 후 운영 절차에서 L6 전에 순서대로 실행 |
