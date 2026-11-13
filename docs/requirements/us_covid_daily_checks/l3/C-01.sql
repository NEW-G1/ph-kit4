-- error_type: range_violation
-- task: raw_us_states

-- C-01: raw_us_states의 당일 snapshot_date 파티션 행 수가 0보다 크다. 0이면 위반 1행.
SELECT
  DATE('{{ ds }}') AS snapshot_date,
  c.row_cnt
FROM (
  SELECT COUNT(*) AS row_cnt
  FROM `{{ project }}.{{ dataset_raw }}.raw_us_states`
  WHERE snapshot_date = DATE('{{ ds }}')
) AS c
WHERE c.row_cnt = 0
