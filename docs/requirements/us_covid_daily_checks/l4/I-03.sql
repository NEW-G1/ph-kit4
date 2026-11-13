-- error_type: join_missing
-- task: mart_daily_us_covid

-- I-03: mart 당일 파티션의 최소 report_date부터 최대 report_date까지 빠진 날짜를 돌려준다.
SELECT d AS missing_date
FROM (
  SELECT MIN(report_date) AS min_date, MAX(report_date) AS max_date
  FROM `{{ project }}.{{ dataset_mart }}.mart_daily_us_covid`
  WHERE snapshot_date = DATE('{{ ds }}')
) AS r
CROSS JOIN UNNEST(GENERATE_DATE_ARRAY(r.min_date, r.max_date)) AS d
WHERE d NOT IN (
  SELECT report_date
  FROM `{{ project }}.{{ dataset_mart }}.mart_daily_us_covid`
  WHERE snapshot_date = DATE('{{ ds }}')
    AND report_date IS NOT NULL
)
