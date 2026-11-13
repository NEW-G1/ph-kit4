"""L3 레이어 게이트 (결정 55·60).

(1) dags/sql/dq/<gate>.sql이 l3 원본에서 다시 생성한 결과(gen_dq.py)와 해시가 같은지.
    파일은 bytes로 읽고 줄바꿈(CRLF/LF) 말고는 정규화하지 않는다. 다르면(인코딩이 깨진 파일 포함) halt input_invalid.
    builder는 dags/sql/dq/에 쓸 수 없으므로(결정 60) 불일치는 builder 실수가 아니다 (결정 59 판정 원칙)
(2) 이 task의 l3 쿼리가 ai_dev에서 0행인지. 위반이 있으면 머리말 error_type
"""
import checks
import common
import gen_dq


def run(ctx, task):
    gate = next(t for t in ctx.contract["dag"]["tasks"] if t["kind"] == "gate" and t["layer"] == task["layer"])
    path = ctx.paths.task_sql(gate)
    try:
        expected = gen_dq.generate(ctx.paths, ctx.contract)[path]
    except ValueError as e:
        raise common.InputInvalid(f"게이트 생성 실패: {e}") from None
    actual = path.read_bytes() if path.exists() else b""
    if gen_dq.sha256_text(actual) != gen_dq.sha256_text(expected):
        raise common.InputInvalid(f"게이트 파일 {gate['id']}.sql이 l3 원본에서 생성한 결과와 다름. gen_dq.py로 다시 생성한다")
    return checks.run_stage(ctx, task, "l3", {"gate": gate["id"], "gate_sha256": gen_dq.sha256_text(expected)})
