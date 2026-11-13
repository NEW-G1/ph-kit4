-- stg_us_states: raw_us_states 당일 파티션을 표준 컬럼명으로 정제한다 (contract load.mode = snapshot, sql_rules.md §1)

-- (1) 테이블이 없을 때만 생성
CREATE TABLE IF NOT EXISTS `{{ project }}.{{ dataset_stg }}.stg_us_states`
(
  snapshot_date DATE OPTIONS (description = '적재 실행 일자(Airflow ds). 일 단위 파티션 컬럼'),
  report_date DATE OPTIONS (description = '원천 date 컬럼. 해당 주의 누적값이 보고된 날짜'),
  state_fips_code STRING OPTIONS (description = '주·영토를 구분하는 2자리 FIPS 코드'),
  state_name STRING OPTIONS (description = '주·영토 이름'),
  cum_confirmed_cnt INT64 OPTIONS (description = '해당 주의 보고일까지 누적 확진 건수. 날짜 간 합산하면 중복 집계됨. 원천 정정으로 전일보다 줄 수 있음'),
  cum_death_cnt INT64 OPTIONS (description = '해당 주의 보고일까지 누적 사망 건수. 날짜 간 합산하면 중복 집계됨. 원천 정정으로 전일보다 줄 수 있음')
)
PARTITION BY snapshot_date
CLUSTER BY report_date, state_fips_code
OPTIONS (
  partition_expiration_days = 7,
  description = '미국 주별 일별 누적 정제. 소스 raw_us_states(원천 bigquery-public-data.covid19_nyt.us_states). 보고일 × 주 1행'
);

-- (2) 당일 파티션 삭제
DELETE FROM `{{ project }}.{{ dataset_stg }}.stg_us_states`
WHERE snapshot_date = DATE('{{ ds }}');

-- (3) 당일 파티션 적재
INSERT INTO `{{ project }}.{{ dataset_stg }}.stg_us_states`
  (snapshot_date, report_date, state_fips_code, state_name, cum_confirmed_cnt, cum_death_cnt)
SELECT
  DATE('{{ ds }}') AS snapshot_date,
  date AS report_date,
  state_fips_code,
  state_name,
  confirmed_cases AS cum_confirmed_cnt,
  deaths AS cum_death_cnt
FROM `{{ project }}.{{ dataset_raw }}.raw_us_states`
WHERE snapshot_date = DATE('{{ ds }}');
