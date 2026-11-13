"""L3·L4·L5 공용: verifier가 쓴 검증 쿼리 실행 (결정 59).

검사 쿼리는 "위반 행을 돌려준다, 0행이면 통과" 형식이다. 해당 task(머리말 task)의 쿼리만 실행한다.
실패하면 머리말 error_type으로 반려하고 위반 행 최대 5개를 metrics.evidence에 남긴다 (결정 49 ④, 합성 데이터만).
모든 쿼리는 dry-run을 먼저 돌리고, 본 실행에는 비용 상한을 건다.
검증 쿼리가 "Not found: Table"이면 builder 반려가 아니라 halt input_invalid다. 층 단위 실행으로 검사 전에
읽는 테이블은 이미 L2를 거쳤으므로, 없는 테이블은 verifier 파일 쪽 문제로 본다 (결정 59, 마트 1 R-0001).
L1·L2에서 builder SQL이 없는 테이블을 읽는 것은 지금처럼 반려다
"""
import common


def run_stage(ctx, task, stage, metrics=None):
    """(rung 이름, 결과 rung). 실패한 첫 검사에서 멈춘다."""
    name = common.STAGE_RUNG[stage]
    metrics = dict(metrics or {})
    ran = []
    try:
        loaded = common.load_checks(ctx.paths, stage)
    except ValueError as e:  # verifier 파일(인코딩·머리말 형식) 문제는 halt (결정 59 판정 원칙)
        raise common.InputInvalid(f"검증 쿼리: {e}") from None
    for check_id, header, body in loaded:
        if header["task"] != task["id"]:
            continue
        try:
            sql = common.render(body, ctx.project, ctx.ds)
        except common.QueryError as e:
            raise common.InputInvalid(f"검증 쿼리 {stage}/{check_id}.sql: {e}") from None
        try:
            common.check_prod(sql)
            ctx.bq.dry_run(sql)
            rows = ctx.bq.run(sql, max_rows=common.EVIDENCE_ROWS + 1)
        except common.QueryError as e:
            if common.NOT_FOUND_TABLE.search(e.verdict_text):  # verifier 파일이 없는 테이블을 읽음 (결정 59 판정 원칙)
                raise common.InputInvalid(f"검증 쿼리 {stage}/{check_id}.sql이 없는 테이블을 읽음: {e}") from None
            return common.rung(name, str(ctx.ds), {**metrics, "checks": ran, "check": check_id, "message": str(e)},
                               e.error_type)
        if rows:
            return common.rung(name, str(ctx.ds), {**metrics, "checks": ran, "check": check_id,
                                                   "violations_shown": len(rows[:common.EVIDENCE_ROWS]),
                                                   "evidence": rows[:common.EVIDENCE_ROWS]},
                               header["error_type"])
        ran.append(check_id)
    return common.rung(name, str(ctx.ds), {**metrics, "checks": ran})
