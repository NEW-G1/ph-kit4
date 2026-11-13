# 인수인계 — us_covid_daily (build, 2026-11-13)

> 사실 칸(2·3·4·5·8)은 `scripts/handover/make_facts.py` 출력이다. 고치거나 추측해서 채우지 않는다.
> 설명 칸(1·6·7)만 builder가 쓴다 (`.claude/rules/handover.md`).

- contract_version: 1
- 생성 시각: 2026-11-13T14:34:19+09:00
- 기준 커밋: 21f187838ad5059ae1ec2bc2788e226e040b9725

## 1. 한 줄 요약
미국 NYT 코로나 원천(`bigquery-public-data.covid19_nyt.us_states`)을 주 1회 snapshot으로 복사·집계해, 분석가·기획자가 추세 모니터링에 쓰는 일별 전국 누적·신규 확진·사망 마트(`mart_daily_us_covid`, 전국 1일 1행)를 만든다.

## 2. 바뀐 것  ← 코드
기준점 `c5297169` 대비 (git diff c5297169...HEAD). contract: 기준점 v1 → 지금 v1

| 구분 | 이름 | 변경 |
|---|---|---|
| 테이블 | thelook_raw.raw_us_states | 그대로 |
| 테이블 | thelook_stg.stg_us_states | 그대로 |
| 테이블 | thelook_mart.mart_daily_us_covid | 그대로 |
| task | raw_us_states | 그대로 |
| task | gate_raw_us_covid_daily | 그대로 |
| task | stg_us_states | 그대로 |
| task | gate_stg_us_covid_daily | 그대로 |
| task | mart_daily_us_covid | 그대로 |
| task | gate_mart_us_covid_daily | 그대로 |
| 파일 | dags/harness_daily.py | 변경 |
| 파일 | dags/sql/dq/gate_mart_us_covid_daily.sql | 신규 |
| 파일 | dags/sql/dq/gate_raw_us_covid_daily.sql | 신규 |
| 파일 | dags/sql/dq/gate_stg_us_covid_daily.sql | 신규 |
| 파일 | dags/sql/mart/mart_daily_us_covid.sql | 신규 |
| 파일 | dags/sql/raw/raw_us_states.sql | 신규 |
| 파일 | dags/sql/stg/stg_us_states.sql | 신규 |
| 파일 | docs/requirements/us_covid_daily_checks/l3/C-01.sql | 신규 |
| 파일 | docs/requirements/us_covid_daily_checks/l3/C-02.sql | 신규 |
| 파일 | docs/requirements/us_covid_daily_checks/l3/C-03.sql | 신규 |
| 파일 | docs/requirements/us_covid_daily_checks/l4/C-04.sql | 신규 |
| 파일 | docs/requirements/us_covid_daily_checks/l4/C-05.sql | 신규 |
| 파일 | docs/requirements/us_covid_daily_checks/l4/C-06.sql | 신규 |
| 파일 | docs/requirements/us_covid_daily_checks/l4/I-01.sql | 신규 |
| 파일 | docs/requirements/us_covid_daily_checks/l4/I-02.sql | 신규 |
| 파일 | docs/requirements/us_covid_daily_checks/l4/I-03.sql | 신규 |
| 파일 | docs/requirements/us_covid_daily_checks/l5/I-04.sql | 신규 |

## 3. 데이터 흐름  ← 코드 (DAG 의존성)
원천: bigquery-public-data.covid19_nyt.us_states

- (원천) → raw_us_states
- raw_us_states → stg_us_states
- stg_us_states → mart_daily_us_covid

게이트: gate_raw_us_covid_daily (raw 층, 상류 raw_us_states), gate_stg_us_covid_daily (stg 층, 상류 stg_us_states), gate_mart_us_covid_daily (mart 층, 상류 mart_daily_us_covid)

OM 리니지 링크는 결재 후 L6 통과 시 docs/handover/ 반영 때 추가한다.

## 4. 검증 결과  ← 코드 (검증 사다리)
contract v1의 사다리 반복 1회

| 반복 | 판정 | task별 |
|---|---|---|
| 1 | pass | raw_us_states pass, stg_us_states pass, mart_daily_us_covid pass |

마지막 통과 반복 1 (task 3/3 통과, ds 2026-11-13)

| 단계 | 결과 | 수치 |
|---|---|---|
| L0 계약·DAG 구조 | 통과 | load_tasks 3, gate_tasks 3, tables 3, checks 10, traces 10 |
| L1 dry-run | 통과 | 스캔량 합 0 bytes (여러 문장 스크립트는 하한값) |
| L2 ai_dev 실행 | 통과 | 실행한 테이블 mart_daily_us_covid, raw_us_states, stg_us_states |
| L3 레이어 게이트 | 통과 | 검사 C-01, C-02, C-03 위반 0행 |
| L4 정합성 | 통과 | 검사 C-04, C-05, C-06, I-01, I-02, I-03 위반 0행 |
| L5 멱등성 | 통과 | 재실행 전후 행 수·체크섬 같음 (ds 파티션 행 수 합 125,042), 검사 I-04 위반 0행 |
| L6 OM 등록 | 결재 후 | 운영 DAG·OM 에이전트 실행 뒤 판정 |

### 비용  ← 코드 (.dev/cost.jsonl)
실행 1회 (RUN-001)

| 역할 | 호출 수 | 비용 합(USD, 정가 환산 추정) | 입력 토큰 | 출력 토큰 | bq 바이트 |
|---|---|---|---|---|---|
| builder | 1 | 0.6108 | 24 | 8,092 | 50,677,044 |
| verifier | 1 | 0.2878 | 12 | 9,711 | 0 |

## 5. 반려 이력  ← 코드 (.dev/rejections.jsonl)
`.dev/rejections.jsonl` (해결 = 같은 task가 그 뒤 반복에서 통과한 첫 반복, ladder_result 기준)

반려 없음

**개입 기록** (`.dev/interventions.jsonl`, 같은 마트, 해석 없이 그대로)

| ID | 시각 | 종류 | 단계 | 대상 | 분 | 메모 |
|---|---|---|---|---|---|---|
| H-0001 | 2026-11-13T14:26:36+09:00 | approval | approval_1 | PR 머지 c529716 | 1 | git 머지 기록에서 자동 |

## 6. 운영 방법
- 적재 방식·주기: contract `load`는 `snapshot`이다. 주 1회 원천 전체를 복사하고 전체 이력을 다시 집계한다. 원천이 2023-03-23 이후 갱신되지 않아 주 1회로 충분하다는 것이 요구서의 가정이다.
- 실행 순서(DAG `dags/harness_daily.py`): `raw_us_states` → `gate_raw_us_covid_daily` → `stg_us_states` → `gate_stg_us_covid_daily` → `mart_daily_us_covid` → `gate_mart_us_covid_daily`. 적재 task 3개와 게이트 task 3개이며, 게이트가 실패하면 그 뒤 층은 실행되지 않는다.
- 재실행: 같은 날짜(`snapshot_date` = Airflow ds)로 다시 실행해도 결과가 같다(R-05, L5 `I-04`로 행 수·체크섬 동일 확인). 실패한 task는 같은 날짜로 다시 돌리면 된다.
- 보관: mart 90일, raw·stg 7일(요구서 §5, contract `schedule.retention_days`는 90).
- 장애 대응: 어느 게이트가 실패했는지로 층을 좁힌다. C-01 raw 당일 파티션 행 없음, C-02 stg 키 중복·NULL·음수, C-03 mart 키 중복·NULL·음수이며 규칙은 contract `checks`에 있다. 규칙 문장 외의 복구 절차는 요구서·contract에 없다.
- 현재 상태: 운영 데이터셋 적재와 일별 스케줄 운영은 이번 범위 밖이다(결재 후 별도). L6 OM 등록은 운영 DAG·OM 에이전트 실행 뒤에 판정한다.

## 7. 주의점과 알려진 데이터 특성
- 누적값이다: `cum_confirmed_cnt`·`cum_death_cnt`는 보고일까지의 누적이라 날짜 간에 합산하면 중복 집계된다.
- 정정으로 음수 신규가 나온다: NYT 사후 정정으로 원천 주별 누적이 전일보다 줄어든 행이 409건, 전국 합계 확진이 전일보다 줄어든 날이 3일 확인됐다(2026-11-13 조회). 보정하지 않고 음수 그대로 둔다(요청자 답변). ASSERT에도 넣지 않았다.
- 초기 날짜의 전국 합계는 보고된 주만의 합이다: 일부 초기 날짜는 보고 주가 1개뿐이다(일별 보고 주 수 1~56).
- 전국 = 56개 주·영토 전체의 합이다. 영토를 따로 빼지 않는다.
- 첫 날(2020-01-21)의 신규는 누적값 그대로다.
- 원천 기간은 2020-01-21~2023-03-23(1,158일)이고 날짜 간격이 없다. 2023-03-23 이후 갱신이 없는 과거 데이터다.
- 키에 `snapshot_date`가 포함된다(mart 키 `snapshot_date`, `report_date`). 일 단위 snapshot 파티션 때문이며, 인터뷰에서 요청자 확인이 필요한 기본안으로 남아 있다.
- 범위 밖: 주별·카운티별 마트, 보고 주 수 컬럼, 인구 대비 비율, 정정 보정·7일 이동평균, 다른 원천 테이블 사용.
- 개인 식별 컬럼은 없다(`pii_columns.md` 검토 완료).

## 8. 링크  ← 코드
- OM 테이블: 결재 후 L6 통과 시 docs/handover/ 반영 때 추가
- 납품 산출물: 아직 없음 (out/deliverables/)
- 요구서: docs/requirements/us_covid_daily.md
- contract: docs/requirements/us_covid_daily.contract.json
- 인터뷰 기록: docs/requirements/us_covid_daily_interview.md
