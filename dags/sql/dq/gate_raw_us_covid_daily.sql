-- 자동 생성: scripts/ladder/gen_dq.py (결정 60). 직접 고치지 않는다.
-- 원본: docs/requirements/us_covid_daily_checks/l3/
ASSERT NOT {{ params.force_fail }} AS '[DQ-FORCE] 강제 실패 파라미터가 참';

ASSERT NOT EXISTS (
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
) AS '[C-01] raw_us_states의 당일 snapshot_date 파티션 행 수가 0보다 크다';
