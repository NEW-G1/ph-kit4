# us_covid_daily 인터뷰 기록 (2026-11-13)

요청: `bigquery-public-data.covid19_nyt`의 `us_states`로 일별 전국 누적 확진·사망 건수 마트. 답변자는 요청자(`requester1`).

## 고정 조회 결과 (메타데이터·집계만, 데이터 값 없음)
- 컬럼: `date` DATE, `state_name` STRING, `state_fips_code` STRING, `confirmed_cases` INT64, `deaths` INT64 (dry-run 10,485,760 B)
- 집계(dry-run 2,418,131 B): 61,942행, 고유 날짜 1,158일(2020-01-21~2023-03-23), 주·영토 56개, 확진·사망 NULL 0, 음수 0, (날짜, 주 코드) 중복 0
- 정정 점검(dry-run 1,734,376 B): 주별 누적이 전일보다 줄어든 행 409건, 전국 합계 확진이 전일보다 줄어든 날 3일, 일별 보고 주 수 1~56, 날짜 간격 0
- 원천 크기·파티션·리전·개인정보 검토는 `docs/kit/source_checklist.md`와 `pii_columns.md`에 이미 결재됨(일반 테이블, 파티션 없음, US, 개인 식별 컬럼 없음)

## 질문과 답
| 질문 | 답 | 반영 |
|---|---|---|
| 누가 어떤 의사결정에 쓰나 | 추세 모니터링 | §1 |
| 지표 범위 | 누적 + 일별 신규 | §3 지표 4개 |
| 정정·초기 날짜 처리 | 원천 그대로 합산 | §4 알려진 데이터 특성, ASSERT에 넣지 않음 |
| 갱신 주기·보관 | 주 1회 snapshot, 90일 | §5, contract `load`·`schedule` |
| 음수 신규 | 음수 그대로 둠 | 지표 제외 조건, 컬럼 설명, I-01·I-02 |
| 첫 날 신규 | 누적값 그대로 | 지표 계산식, I-01·I-02 |

## 기본안으로 정한 것 (요청자 확인 필요)
- 마트명 `us_covid_daily`, 테이블 `raw_us_states` / `stg_us_states` / `mart_daily_us_covid`, 컬럼 `report_date`·`cum_*_cnt`·`new_*_cnt`
- 영토를 포함한 56개 전체를 전국으로 합산
- mart 키에 `snapshot_date` 포함(일 단위 snapshot 파티션 때문)
