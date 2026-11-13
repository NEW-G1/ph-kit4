-- error_type: range_violation
-- task: mart_daily_us_covid

-- I-01: mart 당일 파티션의 신규 확진·사망 합계가 마지막 보고일의 누적 확진·사망과 같아야 한다.
-- 행이 하나도 없으면 합계가 NULL이라 위반으로 잡는다.
SELECT
  t.sum_new_confirmed,
  l.last_cum_confirmed,
  t.sum_new_death,
  l.last_cum_death
FROM (
  SELECT
    SUM(new_confirmed_cnt) AS sum_new_confirmed,
    SUM(new_death_cnt) AS sum_new_death
  FROM `{{ project }}.{{ dataset_mart }}.mart_daily_us_covid`
  WHERE snapshot_date = DATE('{{ ds }}')
) AS t
LEFT JOIN (
  SELECT
    ARRAY_AGG(cum_confirmed_cnt ORDER BY report_date DESC LIMIT 1)[SAFE_OFFSET(0)] AS last_cum_confirmed,
    ARRAY_AGG(cum_death_cnt ORDER BY report_date DESC LIMIT 1)[SAFE_OFFSET(0)] AS last_cum_death
  FROM `{{ project }}.{{ dataset_mart }}.mart_daily_us_covid`
  WHERE snapshot_date = DATE('{{ ds }}')
) AS l
  ON TRUE
WHERE t.sum_new_confirmed IS DISTINCT FROM l.last_cum_confirmed
   OR t.sum_new_death IS DISTINCT FROM l.last_cum_death
