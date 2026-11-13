-- error_type: join_missing
-- task: stg_us_states

-- C-04: raw_us_states와 stg_us_states 당일 파티션 행 수가 원천 us_states 행 수와 같아야 한다.
-- 다른 층마다 위반 1행.
WITH src AS (
  SELECT COUNT(*) AS row_cnt
  FROM `bigquery-public-data.covid19_nyt.us_states`
),
raw_t AS (
  SELECT COUNT(*) AS row_cnt
  FROM `{{ project }}.{{ dataset_raw }}.raw_us_states`
  WHERE snapshot_date = DATE('{{ ds }}')
),
stg_t AS (
  SELECT COUNT(*) AS row_cnt
  FROM `{{ project }}.{{ dataset_stg }}.stg_us_states`
  WHERE snapshot_date = DATE('{{ ds }}')
)
SELECT 'raw_us_states' AS layer_table, raw_t.row_cnt AS target_cnt, src.row_cnt AS source_cnt
FROM raw_t CROSS JOIN src
WHERE raw_t.row_cnt != src.row_cnt

UNION ALL

SELECT 'stg_us_states' AS layer_table, stg_t.row_cnt AS target_cnt, src.row_cnt AS source_cnt
FROM stg_t CROSS JOIN src
WHERE stg_t.row_cnt != src.row_cnt
