"""검증 사다리 실행기 (03 §5.3, 결정 58·59).

  python scripts/ladder/run_ladder.py --mart <마트> (--task <task> | --all) --iteration <n>
         [--request-kind new_build|change|backfill_check] [--ds YYYY-MM-DD]

- L0(contract·DAG 구조·검증 쿼리 머리말)를 실행 1번에 한 번 돌린 뒤 층 단위로 돈다 (마트 1 R-0001):
  층 순서(raw → stg → mart)대로 그 층 load task 전부 L1·L2 → 그 층 load task 전부 L3 → 다음 층.
  모든 층이 끝나면 L4 전부, 그다음 L5 전부(task 의존성 순서). 게이트·L4·L5 검사가 다른 task의 테이블을 읽어도
  그 테이블은 이미 L2를 거쳤다
- 처음 실패한 곳에서 실행 전체를 멈춘다. 파일은 실패(또는 halt)한 task와 L1~L5를 모두 마친 task만 남긴다.
  일부 단계만 통과하고 멈춘 task는 실패 파일의 interrupted_tasks에 통과한 단계와 쓴 바이트를 남기고,
  출력에 "중단"으로 적는다. 시작하지 않은 task는 출력에만 "실행 안 함"으로 적는다
- 결과는 task마다 ladder_result 1개(devlog.py). new_build가 아니면 .dev/maintenance/에 남긴다 (본 측정과 분리)
- 판정 원칙: 원인 파일 작성자 기준 (결정 59). builder 파일 문제는 반려(1), verifier·사람·하네스 파일 문제는
  halt input_invalid(2)
- 종료 코드: 0 통과, 1 판정된 반려, 2 인프라 오류·권한 막힘·입력 파일 문제·사용 오류. 처리하지 못한 예외도 2(halt, infra_error)이고
  결과 파일의 halt_detail에 예외 종류와 메시지를 남긴다 (3-3 스모크 2차)
- ds 기본값은 실행 시각의 UTC 날짜(운영 수동 실행의 ds와 같음). snapshot(contract load 없음 포함)은 raw·stg
  파티션 만료 7일(DDL의 partition_expiration_days) 때문에 최근 7일 안만 받는다. incremental은 ds가 데이터 날짜라
  과거 날짜를 받고 미래만 거부한다(결정 79)
- incremental이면 리전 확인과 같은 자리에서(같은 bq show 결과로) ai_dev 기본 파티션 만료를 본다. 만료가 있고 ds
  파티션이 이미 만료될 만큼 오래됐으면 halt input_invalid(ai_dev 설정은 사람 몫, 05_setup_runbook.md, 결정 79)
- --with-downstream, --ds-from/--ds-to는 자리만 있다 (마트 1 이후 구현)
- L0 통과·인증 확인 직후, 첫 BigQuery 쿼리 전에 ai_dev 리전을 한 번 조회해 설정의 source.location과 다르면
  halt input_invalid로 멈춘다(check_location). L0 앞에 두지 않는다(bq 없이 도는 L0 경로가 있음)
- 다른 contract의 task를 빌려 쓰면 L0 통과·인증 확인 직후(L1 전) prep_upstream.py로 상류를 ai_dev에 같은 ds로
  준비 실행한다(결정 61 ⑤·70). 판정하지 않는다. 준비 기록은 그 실행이 처음 쓰는 결과 파일의 prep 칸에만 남기고
  bytes_total에는 넣지 않는다. 빌린 task가 없으면 아무것도 하지 않는다
"""
import argparse
import json
import sys
import traceback
from datetime import date, timedelta

import common
import l0_contract
import l0_dag
import l1_dryrun
import l2_run
import l3_gate
import l4_recon
import l5_idem
import load_mode
import prep_upstream

devlog = common.devlog
RUNGS = (("L1", l1_dryrun), ("L2", l2_run), ("L3", l3_gate), ("L4", l4_recon), ("L5", l5_idem))
LAYERS = ("raw", "stg", "mart")
LAYER_RUNGS = (("L1", "L2"), ("L3",))  # 층마다: 그 층 task 전부 L1·L2, 그다음 그 층 task 전부 L3
# snapshot의 ds 창. raw·stg DDL의 partition_expiration_days 7일 (결정 59). 근거였던 ai_dev 기본 파티션 만료 7일은
# 11/9 결정 79로 "기본 파티션 만료 없음 + 기본 테이블 만료 7일"로 바뀐다(사람이 설정, 05_setup_runbook.md)
DS_WINDOW_DAYS = 7
DAY_MS = 86400000
NOT_YET = "마트 1 이후 구현"
# 노하우 검사 자리: {규칙 id: {"rung": "L3", "run": fn(ctx, task) -> rung 또는 None}} (결정 45). 지금은 비어 있다
EXPERT_CHECKS = {}


class Ctx:
    def __init__(self, paths, contract, ds, bq, project=None):
        self.paths, self.contract, self.ds, self.bq, self.project = paths, contract, ds, bq, project


def parse_args(argv):
    p = argparse.ArgumentParser(description="검증 사다리 L0~L5")
    p.add_argument("--mart", required=True)
    target = p.add_mutually_exclusive_group(required=True)
    target.add_argument("--task")
    target.add_argument("--all", action="store_true", help="마트의 모든 load task")
    p.add_argument("--iteration", required=True, type=int)
    p.add_argument("--request-kind", default="new_build", choices=sorted(devlog.REQUEST_KINDS))
    p.add_argument("--ds", help="실행 날짜 YYYY-MM-DD (기본: 오늘 UTC)")
    p.add_argument("--with-downstream", action="store_true", help=NOT_YET)
    p.add_argument("--ds-from", help=NOT_YET)
    p.add_argument("--ds-to", help=NOT_YET)
    p.add_argument("--root", default=str(common.PROJECT), help="저장소 루트 (스모크 시험용)")
    p.add_argument("--dev-dir", help="기록할 .dev 폴더 (기본: 저장소의 .dev, 또는 DEVLOG_DIR)")
    return p.parse_args(argv)


def resolve_ds(text, today, incremental=False):
    """snapshot은 최근 7일(UTC), incremental은 오늘 이전 아무 날짜(데이터 날짜, 결정 79). 미래는 둘 다 거부."""
    try:
        ds = date.fromisoformat(text) if text else today
    except ValueError:
        raise common.LadderError(f"--ds는 YYYY-MM-DD여야 함: {text!r}") from None
    if incremental:
        if ds > today:
            raise common.LadderError(f"ds {ds}는 오늘({today}, UTC) 이전이어야 함 (증분 적재의 데이터 날짜)")
        return ds
    oldest = today - timedelta(days=DS_WINDOW_DAYS - 1)
    if not oldest <= ds <= today:
        raise common.LadderError(f"ds {ds}는 {oldest}~{today}(UTC, 최근 {DS_WINDOW_DAYS}일) 안이어야 함. "
                                 "더 오래된 파티션은 ai_dev에서 바로 만료된다")
    return ds


def select_tasks(contract, args):
    loads = common.topo_load_tasks(contract)
    if args.all:
        return loads
    by_id = {t["id"]: t for t in contract["dag"]["tasks"]}
    task = by_id.get(args.task)
    if task is None:
        raise common.LadderError(f"contract에 없는 task: {args.task!r}")
    if task["kind"] != "load":
        raise common.LadderError(f"{args.task}는 게이트 task다. 게이트는 같은 층 load task의 L3에서 검사한다")
    return [task]


def run_l0(paths, contract):
    """판정 원칙은 원인 파일 작성자 기준 (결정 59). contract·설정·pii_columns.md·_checks/·dq/ 문제는 InputInvalid(halt),
    builder 파일(stg·mart SQL의 개인 식별 컬럼, DAG 파일, task SQL 파일) 문제는 반려 rung."""
    common.config()
    try:
        pii = l0_contract.load_pii()
    except (OSError, ValueError) as e:
        raise common.InputInvalid(f"pii_columns.md를 읽지 못함: {e}") from None
    r = l0_contract.check_contract(contract, None, pii)
    if r["status"] == "fail":
        raise common.InputInvalid("contract: " + "; ".join(r["metrics"]["errors"]))
    sql_errors = l0_contract.check_sql_dir(paths.sql, pii)
    if sql_errors:
        return common.rung("L0", None, {"stage": "contract", "errors": sql_errors}, "pii_column")
    dag_fail = l0_dag.check(paths, contract)
    if dag_fail:
        return dag_fail
    return common.rung("L0", None, {**r["metrics"], "dag": "pass"})


def check_location(ctx):
    """ai_dev 리전이 설정의 원천 리전과 같은지 본다. 다르면 L2에서 원인이 안 보이는 "찾을 수 없음"이 나므로 쿼리 전에
    halt input_invalid로 멈춘다(설정·데이터셋 준비는 사람 몫, 결정 59). 대소문자는 무시한다(US·us).
    조회 실패는 Bq.dataset_location이 InfraError로 낸다."""
    want = common.config()["source"]["location"]
    got = ctx.bq.dataset_location(ctx.project)
    if got.casefold() != want.casefold():
        raise common.InputInvalid(f"리전이 다름: 원천(source.location) {want}, {common.DEV_DATASET} {got}. "
                                  f"{common.DEV_DATASET}를 원천과 같은 리전에 만들 것")


def check_expiration(ctx, today):
    """incremental이면 ai_dev 기본 파티션 만료(defaultPartitionExpirationMs)가 ds 파티션을 바로 지우는지 본다 (결정 79).
    증분 테이블 DDL에는 partition_expiration_days가 없어 새 테이블은 데이터셋 기본값을 받는다. 날짜 D 파티션은
    D 00:00(UTC) + 만료 시간에 지워지므로 (오늘 - ds)일 × 하루 ≥ 만료면 L2에서 쓴 행이 사라져 L3~L5가 원인 없이 실패한다.
    그래서 쿼리 전에 halt input_invalid로 멈춘다(설정은 사람 몫). 만료가 없으면 통과. snapshot은 보지 않는다
    (DDL에 자체 만료가 있고 ds 창이 7일). check_location과 같은 bq show 결과를 쓴다."""
    if not load_mode.is_incremental(ctx.contract):
        return
    raw = ctx.bq.dataset_info(ctx.project).get("defaultPartitionExpirationMs")
    if raw in (None, "", "0", 0):
        return
    try:
        expiration_ms = int(raw)
    except (TypeError, ValueError):
        raise common.InfraError(f"{common.DEV_DATASET} 기본 파티션 만료 값을 읽지 못함: {raw!r}") from None
    age_days = (today - ctx.ds).days
    if age_days * DAY_MS >= expiration_ms:
        raise common.InputInvalid(
            f"{common.DEV_DATASET} 기본 파티션 만료({expiration_ms / DAY_MS:g}일)보다 오래된 ds {ctx.ds}({age_days}일 전). "
            f"증분 적재 테이블의 이 파티션은 바로 지워진다. {common.DEV_DATASET}의 기본 파티션 만료를 없애고 기본 테이블 만료로 "
            "바꿀 것(05_setup_runbook.md, 결정 79)")


def run_expert(ctx, task, rung_name):
    for rule_id in ctx.contract["modules"]["expert"]["on"]:
        spec = EXPERT_CHECKS[rule_id]
        if spec["rung"] == rung_name:
            r = spec["run"](ctx, task)
            if r is not None and r["status"] == "fail":
                return r
    return None


def schedule(tasks, rungs=None):
    """[(task, rung 이름, 모듈)] 실행 순서. 층 단위로 L1·L2 → L3, 모든 층 뒤에 L4 전부 → L5 전부 (R-0001).
    tasks는 의존성 순서이고 같은 층 안에서도 그 순서를 지킨다."""
    modules = dict(RUNGS if rungs is None else rungs)
    order, done = [], set()
    for layer in LAYERS:
        mine = [t for t in tasks if t["layer"] == layer]
        for names in LAYER_RUNGS:
            for t in mine:
                for name in names:
                    if name in modules:
                        order.append((t, name, modules[name]))
                        done.add(name)
    for name in modules:
        if name not in done:
            order += [(t, name, modules[name]) for t in tasks]
    return order


def record(args, contract, task, rungs, verdict, halt_reason, bytes_total, base, detail=None, interrupted=None,
           prep=None):
    entry = {"task": task["id"], "iteration": args.iteration, "contract_version": contract["version"],
             "request_kind": args.request_kind, "modules": contract["modules"], "bytes_total": bytes_total,
             "rungs": rungs, "verdict": verdict, "halt_reason": halt_reason}
    if detail:
        entry["halt_detail"] = detail
    if interrupted:
        entry["interrupted_tasks"] = interrupted
    if prep:
        entry["prep"] = prep
    return devlog.write_ladder_result(args.mart, entry, base)


def halt_of(e):
    """멈춘 원인 (halt_reason, halt_detail). 인프라 오류가 아닌 처리하지 못한 예외도 하네스 쪽 장애이므로
    반려로 세지 않고 infra_error로 멈춘다. 종료 코드 1은 판정된 반려에만 쓴다 (3-3 스모크 2차)."""
    if not isinstance(e, common.HaltError):
        traceback.print_exception(e, file=sys.stderr)
    reason = e.halt_reason if isinstance(e, common.HaltError) else "infra_error"
    return reason, {"exception": e.__class__.__name__, "message": str(e)[:500]}


def main(argv=None, bq=None, today=None):
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    args = parse_args(argv)
    try:
        if args.with_downstream or args.ds_from or args.ds_to:
            raise common.LadderError(f"--with-downstream, --ds-from/--ds-to는 {NOT_YET}")
        if args.iteration < 1:
            raise common.LadderError("--iteration은 1 이상")
        if args.request_kind == "backfill_check" and args.iteration != 1:
            raise common.LadderError("backfill_check는 루프 반복이 아니므로 --iteration 1로 실행한다 (결정 59)")
        paths = common.Paths(args.root, args.mart)
        contract = common.load_contract(paths)
        tasks = select_tasks(contract, args)
        today = today or common.utc_today()
        ds = resolve_ds(args.ds, today, load_mode.is_incremental(contract))
        missing = [r for r in contract["modules"]["expert"]["on"] if r not in EXPERT_CHECKS]
        if missing:
            raise common.LadderError(f"노하우 검사가 아직 없음: {missing}")
        base = devlog.dev_dir(args.dev_dir)
        if args.request_kind != "new_build":
            base = base / "maintenance"
        for t in tasks:
            name = f"{t['id']}-v{contract['version']}-{args.iteration}.json"
            if (base / "ladder_results" / args.mart / name).exists():
                raise common.LadderError(f"이미 있는 ladder_result: {name}. 반복 번호를 확인한다")
    except common.LadderError as e:
        print(f"사다리를 시작하지 않음: {e}", file=sys.stderr)
        return 2
    except Exception as e:  # 실행 대상을 정하기 전이라 결과 파일을 남길 task가 없다. 출력에만 남긴다
        traceback.print_exception(e, file=sys.stderr)
        print(f"사다리를 시작하지 않음 (처리하지 못한 예외 {e.__class__.__name__}): {e}", file=sys.stderr)
        return 2

    summary = {"mart": args.mart, "ds": str(ds), "request_kind": args.request_kind, "tasks": []}
    ctx = Ctx(paths, contract, ds, bq or common.Bq())

    items = {}  # task id → 출력 요약 항목 (마지막에 task 순서로 모은다)
    prep_items = []  # 상류 준비 기록 (결정 70). 처음 쓰는 결과 파일에만 남긴다
    pending_prep = {"items": prep_items}

    def finish(task, rungs, verdict, halt_reason=None, bytes_total=None, detail=None, interrupted=None):
        item = {"task": task["id"], "verdict": verdict}
        if detail:
            item.update(halt_reason=halt_reason, exception=detail["exception"], message=detail["message"])
        try:
            item["file"] = str(record(args, contract, task, rungs, verdict, halt_reason, bytes_total, base, detail,
                                      interrupted, pending_prep.pop("items", None)))
        except Exception as e:  # 기록 자체가 실패하면 결과를 믿을 수 없으므로 멈춘다
            traceback.print_exception(e, file=sys.stderr)
            item.update(file=None, record_error=f"{e.__class__.__name__}: {e}")
            verdict = "halt"
        items[task["id"]] = item
        return {"pass": 0, "reject": 1, "halt": 2}[verdict]

    exit_code, l0 = 0, None
    try:
        l0 = run_l0(paths, contract)
        if l0["status"] == "pass":
            ctx.project = ctx.bq.check_auth()
            check_location(ctx)  # 첫 BigQuery 쿼리(상류 준비·L1) 전에 한 번
            check_expiration(ctx, today)  # incremental만. 같은 bq show 결과 (결정 79)
            prep_upstream.run(ctx, prep_items)  # L1 전 (결정 70)
    except Exception as e:  # git fetch origin main 실패, 인증 없음, 리전 다름, 상류 준비 실패, 처리하지 못한 예외
        reason, detail = halt_of(e)
        exit_code = finish(tasks[0], [l0] if l0 else [], "halt", reason, None, detail)
    else:
        if l0["status"] == "fail":
            exit_code = finish(tasks[0], [l0], "reject")
    if exit_code == 0:
        exit_code = run_rungs(ctx, tasks, l0, finish, items)
    for t in tasks:
        summary["tasks"].append(items.get(t["id"], {"task": t["id"], "verdict": "실행 안 함"}))
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return exit_code


def run_rungs(ctx, tasks, l0, finish, items):
    """schedule() 순서로 돈다. 첫 실패에서 멈추고, 일부 단계만 마친 task는 실패 파일의 interrupted_tasks로 남긴다."""
    rungs = {t["id"]: [l0] for t in tasks}
    spent = {t["id"]: 0 for t in tasks}
    last = RUNGS[-1][0]
    for task, name, module in schedule(tasks):
        tid = task["id"]
        start = ctx.bq.bytes_total
        verdict, halt_reason, detail = None, None, None
        try:
            r = module.run(ctx, task)
            if r["status"] == "pass":
                r = run_expert(ctx, task, name) or r
            rungs[tid].append(r)
            if r["status"] == "fail":
                verdict = "reject"
        except Exception as e:
            verdict = "halt"
            halt_reason, detail = halt_of(e)
        spent[tid] += ctx.bq.bytes_total - start
        if verdict is None:
            if name == last:
                code = finish(task, rungs[tid], "pass", None, spent[tid])
                if code:  # 기록 실패
                    return code
            continue
        interrupted = [{"task": t["id"], "passed_rungs": [g["rung"] for g in rungs[t["id"]]],
                        "bytes": spent[t["id"]]}
                       for t in tasks if t["id"] != tid and t["id"] not in items and len(rungs[t["id"]]) > 1]
        code = finish(task, rungs[tid], verdict, halt_reason, spent[tid], detail, interrupted)
        for i in interrupted:
            items[i["task"]] = {"task": i["task"], "verdict": "중단", "passed_rungs": i["passed_rungs"]}
        return code
    return 0


if __name__ == "__main__":
    common.apply_kit_local()  # 새 창: .kit_local.json의 CLOUDSDK_CONFIG (있으면 덮어쓰지 않음)
    sys.exit(main())
