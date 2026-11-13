-- error_type: idempotency_break
-- task: mart_daily_us_covid

-- I-04: 2회 실행 뒤 mart 당일 파티션이 원천에서 다시 계산한 기대값과 행 단위로 같아야 한다.
-- 재실행으로 행이 겹쳐 쌓였거나(키 중복) 값이 달라지면 위반 행이 나온다.
-- 사다리가 2회 실행 전후의 행 수·체크섬 비교는 따로 한다.
WITH expected AS (
  SELECT
    report_date,
    cum_confirmed_cnt,
    cum_death_cnt,
    cum_confirmed_cnt - IFNULL(LAG(cum_confirmed_cnt) OVER (ORDER BY report_date), 0) AS new_confirmed_cnt,
    cum_death_cnt - IFNULL(LAG(cum_death_cnt) OVER (ORDER BY report_date), 0) AS new_death_cnt
  FROM (
    SELECT date AS report_date, SUM(confirmed_cases) AS cum_confirmed_cnt, SUM(deaths) AS cum_death_cnt
    FROM `bigquery-public-data.covid19_nyt.us_states`
    GROUP BY date
  )
),
actual AS (
  SELECT report_date, cum_confirmed_cnt, cum_death_cnt, new_confirmed_cnt, new_death_cnt, COUNT(*) AS row_cnt
  FROM `{{ project }}.{{ dataset_mart }}.mart_daily_us_covid`
  WHERE snapshot_date = DATE('{{ ds }}')
  GROUP BY report_date, cum_confirmed_cnt, cum_death_cnt, new_confirmed_cnt, new_death_cnt
)
SELECT
  COALESCE(a.report_date, e.report_date) AS report_date,
  a.row_cnt AS actual_row_cnt
FROM actual AS a
FULL OUTER JOIN expected AS e
  ON a.report_date = e.report_date
WHERE a.report_date IS NULL
   OR e.report_date IS NULL
   OR a.row_cnt != 1
   OR a.cum_confirmed_cnt IS DISTINCT FROM e.cum_confirmed_cnt
   OR a.cum_death_cnt IS DISTINCT FROM e.cum_death_cnt
   OR a.new_confirmed_cnt IS DISTINCT FROM e.new_confirmed_cnt
   OR a.new_death_cnt IS DISTINCT FROM e.new_death_cnt
