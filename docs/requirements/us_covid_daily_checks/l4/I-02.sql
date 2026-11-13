-- error_type: range_violation
-- task: mart_daily_us_covid

-- I-02: 신규 확진·사망이 첫 날은 누적값, 그 외 날은 전일 누적과의 차이와 같아야 한다.
-- 전일은 mart의 직전 report_date 행이다. 날짜 연속은 I-03이 따로 본다.
SELECT
  report_date,
  new_confirmed_cnt,
  cum_confirmed_cnt - IFNULL(prev_confirmed, 0) AS expected_new_confirmed,
  new_death_cnt,
  cum_death_cnt - IFNULL(prev_death, 0) AS expected_new_death
FROM (
  SELECT
    report_date,
    cum_confirmed_cnt,
    cum_death_cnt,
    new_confirmed_cnt,
    new_death_cnt,
    LAG(cum_confirmed_cnt) OVER (ORDER BY report_date) AS prev_confirmed,
    LAG(cum_death_cnt) OVER (ORDER BY report_date) AS prev_death
  FROM `{{ project }}.{{ dataset_mart }}.mart_daily_us_covid`
  WHERE snapshot_date = DATE('{{ ds }}')
)
WHERE new_confirmed_cnt IS DISTINCT FROM cum_confirmed_cnt - IFNULL(prev_confirmed, 0)
   OR new_death_cnt IS DISTINCT FROM cum_death_cnt - IFNULL(prev_death, 0)
