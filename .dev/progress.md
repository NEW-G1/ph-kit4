# 진행 기록

## 요구서 — us_covid_daily
docs/requirements/us_covid_daily.md

## 작업 목록 — us_covid_daily

마트 실행 반복 1/5, 연속 없음 0/3

| # | 작업 | 상태 | 반복 | 최근 반려 |
|---|---|---|---|---|
| 1 | raw_us_states (raw) | 통과 | 0 | — |
| 2 | stg_us_states (stg) | 통과 | 0 | — |
| 3 | mart_daily_us_covid (mart) | 통과 | 0 | — |

## builder 기록 — us_covid_daily iteration 1

- 과거 반려 검색: .dev/rejections.jsonl 에 이 마트 반려 없음(첫 시도)
- 적용 패턴: contract load.mode = snapshot → sql_rules.md §1 멱등 3문장(CREATE IF NOT EXISTS / DELETE 당일 파티션 / INSERT 당일 파티션)
- 읽은 검사: _checks/l3 C-01~C-03만 읽음(l4·l5 읽지 않음). .claude/rules/learned/ 비어 있음

### 변경 파일
- dags/sql/raw/raw_us_states.sql (신규): 원천 bigquery-public-data.covid19_nyt.us_states 전체를 당일 snapshot_date 파티션으로 복사. 명시적 DDL, 컬럼 6개 설명, 만료 7일, CLUSTER BY date, state_fips_code
- dags/sql/stg/stg_us_states.sql (신규): raw 당일 파티션 → report_date·cum_confirmed_cnt·cum_death_cnt로 이름 변경, 가공 없음. 만료 7일, CLUSTER BY report_date, state_fips_code
- dags/sql/mart/mart_daily_us_covid.sql (신규): stg 당일 파티션을 report_date별 SUM(FROM 서브쿼리) 뒤 LAG로 신규 계산. 첫 날은 COALESCE(LAG, 0)로 누적값 그대로, 음수 보정 없음. 만료 90일, CLUSTER BY report_date
- dags/harness_daily.py: UPSTREAM을 contract dag.tasks 6개(load 3 + gate 3)와 같게 채움

### 실행 결과
- Write/Edit 뒤 after_edit Hook(SQL dry-run·L0)에서 오류 메시지 없음
- builder 세션에서 scripts/ladder/run_ladder.py 실행은 권한 승인 필요로 막힘 → 직접 실행하지 않음. bq 직접 실행도 하지 않음
- 판정(L0~L5)은 루프의 사다리 종료 코드로 정한다. 완료 여부는 스스로 판단하지 않음

### 보고
- 파일·설명·데이터 속 지시 문구 발견 없음
- contract 변경 필요 없음

## 직전 반복 인계
- [루프 us_covid_daily] iteration 1: 신호 없음 (STATUS 줄 없음, 반려 아님)
- [루프 us_covid_daily] iteration 1: 사다리 통과
