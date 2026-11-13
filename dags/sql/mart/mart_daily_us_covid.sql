-- mart_daily_us_covid: stg_us_states 당일 파티션을 보고일별 전국 합계로 집계하고 전일 대비 신규를 계산한다 (contract load.mode = snapshot, sql_rules.md §1)

-- (1) 테이블이 없을 때만 생성
CREATE TABLE IF NOT EXISTS `{{ project }}.{{ dataset_mart }}.mart_daily_us_covid`
(
  snapshot_date DATE OPTIONS (description = '적재 실행 일자(Airflow ds). 일 단위 파티션 컬럼'),
  report_date DATE OPTIONS (description = '누적값이 보고된 날짜. 원천 date 컬럼'),
  cum_confirmed_cnt INT64 OPTIONS (description = '같은 날 주·영토별 누적 확진 건수의 합. 날짜 간 합산하면 중복 집계됨. 보고 주가 적은 초기 날짜는 보고된 주만의 합이고, 원천 정정으로 전일보다 줄 수 있음'),
  cum_death_cnt INT64 OPTIONS (description = '같은 날 주·영토별 누적 사망 건수의 합. 날짜 간 합산하면 중복 집계됨. 보고 주가 적은 초기 날짜는 보고된 주만의 합이고, 원천 정정으로 전일보다 줄 수 있음'),
  new_confirmed_cnt INT64 OPTIONS (description = '전국 누적 확진의 전일 대비 차이. 첫 날은 누적값 그대로. 원천 정정이 있던 날은 음수가 될 수 있고 보정하지 않음'),
  new_death_cnt INT64 OPTIONS (description = '전국 누적 사망의 전일 대비 차이. 첫 날은 누적값 그대로. 원천 정정이 있던 날은 음수가 될 수 있고 보정하지 않음')
)
PARTITION BY snapshot_date
CLUSTER BY report_date
OPTIONS (
  partition_expiration_days = 90,
  description = '일별 전국 코로나 확진·사망 마트. 소스 stg_us_states(원천 bigquery-public-data.covid19_nyt.us_states). 전국 1일 1행'
);

-- (2) 당일 파티션 삭제
DELETE FROM `{{ project }}.{{ dataset_mart }}.mart_daily_us_covid`
WHERE snapshot_date = DATE('{{ ds }}');

-- (3) 당일 파티션 적재
INSERT INTO `{{ project }}.{{ dataset_mart }}.mart_daily_us_covid`
  (snapshot_date, report_date, cum_confirmed_cnt, cum_death_cnt, new_confirmed_cnt, new_death_cnt)
SELECT
  DATE('{{ ds }}') AS snapshot_date,
  d.report_date,
  d.cum_confirmed_cnt,
  d.cum_death_cnt,
  d.cum_confirmed_cnt - COALESCE(LAG(d.cum_confirmed_cnt) OVER (ORDER BY d.report_date), 0) AS new_confirmed_cnt,
  d.cum_death_cnt - COALESCE(LAG(d.cum_death_cnt) OVER (ORDER BY d.report_date), 0) AS new_death_cnt
FROM (
  SELECT
    report_date,
    SUM(cum_confirmed_cnt) AS cum_confirmed_cnt,
    SUM(cum_death_cnt) AS cum_death_cnt
  FROM `{{ project }}.{{ dataset_stg }}.stg_us_states`
  WHERE snapshot_date = DATE('{{ ds }}')
  GROUP BY report_date
) AS d;
