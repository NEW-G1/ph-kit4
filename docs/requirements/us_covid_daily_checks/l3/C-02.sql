-- error_type: duplicate_rows
-- task: stg_us_states

-- C-02: stg_us_states 당일 파티션에서 (snapshot_date, report_date, state_fips_code) 중복,
-- 누적 확진·사망 NULL, 음수인 행을 돌려준다.
SELECT
  'duplicate_key' AS violation,
  CAST(report_date AS STRING) AS report_date,
  state_fips_code,
  COUNT(*) AS row_cnt
FROM `{{ project }}.{{ dataset_stg }}.stg_us_states`
WHERE snapshot_date = DATE('{{ ds }}')
GROUP BY report_date, state_fips_code
HAVING COUNT(*) > 1

UNION ALL

SELECT
  'null_or_negative' AS violation,
  CAST(report_date AS STRING) AS report_date,
  state_fips_code,
  1 AS row_cnt
FROM `{{ project }}.{{ dataset_stg }}.stg_us_states`
WHERE snapshot_date = DATE('{{ ds }}')
  AND (
    cum_confirmed_cnt IS NULL OR cum_death_cnt IS NULL
    OR cum_confirmed_cnt < 0 OR cum_death_cnt < 0
    OR report_date IS NULL OR state_fips_code IS NULL
  )
