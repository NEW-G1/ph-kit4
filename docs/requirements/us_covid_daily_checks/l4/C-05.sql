-- error_type: join_missing
-- task: mart_daily_us_covid

-- C-05: mart_daily_us_covid 당일 파티션 행 수가 원천 us_states의 고유 date 수와 같아야 한다.
SELECT
  m.row_cnt AS mart_cnt,
  s.date_cnt AS source_date_cnt
FROM (
  SELECT COUNT(*) AS row_cnt
  FROM `{{ project }}.{{ dataset_mart }}.mart_daily_us_covid`
  WHERE snapshot_date = DATE('{{ ds }}')
) AS m
CROSS JOIN (
  SELECT COUNT(DISTINCT date) AS date_cnt
  FROM `bigquery-public-data.covid19_nyt.us_states`
) AS s
WHERE m.row_cnt != s.date_cnt
