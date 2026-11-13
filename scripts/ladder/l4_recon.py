"""L4 원천 대비 정합성: verifier가 쓴 _checks/l4/ 중 이 task의 쿼리를 실행한다 (03 §5.3)."""
import checks


def run(ctx, task):
    return checks.run_stage(ctx, task, "l4")
