-- error_type: range_violation
-- task: mart_daily_us_covid

-- C-06: report_date별 mart 누적 확진·사망이 원천 us_states를 같은 date로 합한 값과 같아야 한다.
-- 한쪽에만 있는 날짜도 위반이다.
SELECT
  COALESCE(m.report_date, s.date) AS report_date,
  m.cum_confirmed_cnt AS mart_confirmed,
  s.confirmed_sum AS source_confirmed,
  m.cum_death_cnt AS mart_death,
  s.death_sum AS source_death
FROM (
  SELECT report_date, cum_confirmed_cnt, cum_death_cnt
  FROM `{{ project }}.{{ dataset_mart }}.mart_daily_us_covid`
  WHERE snapshot_date = DATE('{{ ds }}')
) AS m
FULL OUTER JOIN (
  SELECT date, SUM(confirmed_cases) AS confirmed_sum, SUM(deaths) AS death_sum
  FROM `bigquery-public-data.covid19_nyt.us_states`
  GROUP BY date
) AS s
  ON m.report_date = s.date
WHERE m.report_date IS NULL
   OR s.date IS NULL
   OR m.cum_confirmed_cnt IS DISTINCT FROM s.confirmed_sum
   OR m.cum_death_cnt IS DISTINCT FROM s.death_sum
