-- 자동 생성: scripts/ladder/gen_dq.py (결정 60). 직접 고치지 않는다.
-- 원본: docs/requirements/us_covid_daily_checks/l3/
ASSERT NOT {{ params.force_fail }} AS '[DQ-FORCE] 강제 실패 파라미터가 참';

ASSERT NOT EXISTS (
-- C-03: mart_daily_us_covid 당일 파티션에서 report_date 중복,
-- 누적 확진·사망 NULL, 음수인 행을 돌려준다.
SELECT
  'duplicate_key' AS violation,
  CAST(report_date AS STRING) AS report_date,
  COUNT(*) AS row_cnt
FROM `{{ project }}.{{ dataset_mart }}.mart_daily_us_covid`
WHERE snapshot_date = DATE('{{ ds }}')
GROUP BY report_date
HAVING COUNT(*) > 1

UNION ALL

SELECT
  'null_or_negative' AS violation,
  CAST(report_date AS STRING) AS report_date,
  1 AS row_cnt
FROM `{{ project }}.{{ dataset_mart }}.mart_daily_us_covid`
WHERE snapshot_date = DATE('{{ ds }}')
  AND (
    report_date IS NULL
    OR cum_confirmed_cnt IS NULL OR cum_death_cnt IS NULL
    OR cum_confirmed_cnt < 0 OR cum_death_cnt < 0
  )
) AS '[C-03] mart_daily_us_covid의 report_date가 고유하고 누적 확진·사망이 NULL이 아니며 음수가 아니다';
