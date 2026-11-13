-- raw_us_states: 원천 us_states 를 가공 없이 당일 snapshot_date 파티션으로 복사한다 (contract load.mode = snapshot, sql_rules.md §1)

-- (1) 테이블이 없을 때만 생성
CREATE TABLE IF NOT EXISTS `{{ project }}.{{ dataset_raw }}.raw_us_states`
(
  snapshot_date DATE OPTIONS (description = '적재 실행 일자(Airflow ds). 일 단위 파티션 컬럼'),
  date DATE OPTIONS (description = '원천 us_states의 보고일'),
  state_name STRING OPTIONS (description = '원천의 주·영토 이름'),
  state_fips_code STRING OPTIONS (description = '주·영토를 구분하는 2자리 FIPS 코드'),
  confirmed_cases INT64 OPTIONS (description = '해당 주의 보고일까지 누적 확진 건수. 날짜 간 합산하면 중복 집계됨'),
  deaths INT64 OPTIONS (description = '해당 주의 보고일까지 누적 사망 건수. 날짜 간 합산하면 중복 집계됨')
)
PARTITION BY snapshot_date
CLUSTER BY date, state_fips_code
OPTIONS (
  partition_expiration_days = 7,
  description = '미국 주별 코로나 원천 복사. 원천 bigquery-public-data.covid19_nyt.us_states 를 snapshot_date 파티션마다 전체 복사'
);

-- (2) 당일 파티션 삭제
DELETE FROM `{{ project }}.{{ dataset_raw }}.raw_us_states`
WHERE snapshot_date = DATE('{{ ds }}');

-- (3) 당일 파티션 적재
INSERT INTO `{{ project }}.{{ dataset_raw }}.raw_us_states`
  (snapshot_date, date, state_name, state_fips_code, confirmed_cases, deaths)
SELECT
  DATE('{{ ds }}') AS snapshot_date,
  date,
  state_name,
  state_fips_code,
  confirmed_cases,
  deaths
FROM `bigquery-public-data.covid19_nyt.us_states`;
