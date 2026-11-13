# 개인 식별 컬럼 목록

> 사람이 관리하는 금지 목록입니다(결정 51 ⑦). `.claude/rules/security.md`와 `design_principles.md`는 이 파일을 가리킵니다.
> L0(`scripts/ladder/l0_contract.py`)가 아래 표를 읽어 검사합니다. 표 형식(칸 순서, 테이블·컬럼의 백틱)을 바꾸지 마십시오.

> 데이터셋 이름의 출처는 `dags/harness_config.json`입니다.

검토한 원천: `bigquery-public-data.covid19_nyt`

> 위 줄은 이 표를 검토한 원천(`<프로젝트>.<데이터셋>`)입니다. L0는 이 줄이 없거나 `dags/harness_config.json`의 `source`와 다르면 멈춥니다(사람 파일 문제, halt `input_invalid`). 원천을 바꾸면 새 원천의 컬럼을 검토해 표와 이 줄을 함께 다시 씁니다. 후보는 인터뷰의 "개인정보 후보 찾기"(`docs/plan/03_harness_guide.md`(원본 저장소 문서, 키트에 없음) §3.3)가 메타데이터로 찾고, 확정은 사람이 합니다.

## 범위

- **stg·mart**에는 아래 컬럼을 전달하지 않습니다.
- **raw**는 "원천을 가공 없이 일자별 보관" 원칙을 유지합니다(`design_principles.md` §2, 7일 보관). raw 테이블은 검사하지 않습니다.
- 다른 후보 컬럼은 원천 스키마를 확인한 뒤 사람이 이 표에 추가합니다. 원천 테이블이 추가되면 L0 SQL 검사도 그 원천(`raw_<원천>`, 설정의 원천 데이터셋 `<source.dataset>.<원천>`)에 같은 규칙을 적용합니다.

## L0 검사 (이름·참조 기준)

다음 중 하나면 L0 실패, `error_type: pii_column`(`error_class: semantic`)입니다.

1. contract에서 layer가 stg·mart인 테이블의 컬럼 이름이 목록에 있음
2. `dags/sql/stg/`·`dags/sql/mart/`의 SQL이 원천 테이블(`raw_<테이블>` 또는 `<원천 데이터셋>.<테이블>`)을 FROM·JOIN으로 읽으면서 그 테이블의 목록 컬럼을 참조함
3. 같은 SQL이 그 테이블을 `SELECT *`·`별칭.*`로 읽음 (`SELECT * EXCEPT(...)`도 실패로 둠)

주석과 문자열 안의 단어는 보지 않습니다. 이름과 참조를 기준으로 막는 검사이며, 완전한 차단은 아닙니다.

## 목록

| 원천 테이블 | 컬럼 | 근거 |
|---|---|---|
| (없음) | | 4개 테이블(`us_counties`, `us_states`, `excess_deaths`, `mask_use_by_county`) 모두 지역 단위 집계이고 개인 단위 컬럼이 없음(컬럼 이름 기준) |

원천 컬럼 이름은 원천 `INFORMATION_SCHEMA.COLUMNS` 조회(컬럼 이름·타입만, 데이터 값 조회 없음)로 확인했습니다(2026-11-13).

개인 식별 컬럼이 없는 원천이면 표에 `| (없음) | | 검토 근거 |` 행 하나만 둡니다. 표가 그냥 비어 있으면 L0가 멈춥니다.
