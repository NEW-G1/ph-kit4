"""상류 준비 실행 (결정 61 ⑤, 결정 70으로 수정). run_ladder.main()이 L0 통과·인증 확인 직후, L1 전에 부른다.

- 대상: 이 마트 contract의 upstream 중 다른 contract의 task(<마트>:<task>, 결정 61 ④ c)와 그 상류 load task 전부.
  상류는 origin/main(결재 1을 받은) contract에서 따라가고, 빌린 contract가 또 다른 마트를 빌리면 그 contract로
  넘어가 재귀로 따라간다. 게이트는 지나가기만 하고 돌리지 않는다. 순서는 의존 순서(상류 먼저)
- 순환이 있거나, 따라가다 이 마트의 task로 돌아오거나, origin/main에 contract·task·SQL이 없으면 halt input_invalid
- 작업 트리의 빌린 SQL이 origin/main과 다르면(줄바꿈·BOM 차이는 무시) 아무것도 실행하지 않고 halt input_invalid
  (빌린 task는 고치지 않는다, 결정 61 ④ b)
- task마다: ai_dev의 같은 ds 파티션에 행이 있으면(INFORMATION_SCHEMA.PARTITIONS, partition_id=YYYYMMDD,
  total_rows>0) 건너뛴다. 없거나 0행이면 렌더링 → 운영 데이터셋 이름 차단(common.check_prod) → dry-run → 본 실행
  (l2_run.execute). 판정하지 않는다
- 실패: 권한·인프라 → InfraError(halt infra_error, 종료 2). 빌린 SQL 자체 오류(렌더링·문법·실행·비용 상한·운영
  데이터셋 이름) → InputInvalid(halt input_invalid, 원래 마트의 contract v2로). 확인 쿼리 실패는 하네스 쪽이라 InfraError
- 기록: 준비한 task마다 {"task": "<마트>:<task>", "skipped": bool, "bytes": dry-run 바이트} 를 items에 쌓는다.
  실패해도 그때까지(실패한 task 포함)를 남긴다. run_ladder가 그 실행이 처음 쓰는 ladder_result의 prep 칸에 적고
  bytes_total에는 넣지 않는다
- 빌린 task가 없는 마트는 아무것도 하지 않는다(git·bq 호출 없음)
"""
import json
import re

import common
import l0_contract
import l0_dag
import l2_run

NAME = re.compile(r"[A-Za-z0-9_]+")


def external_refs(contract):
    """[(마트, task)] 이 contract의 upstream 중 다른 contract의 task. 적힌 순서, 중복 없이."""
    refs = []
    for t in contract["dag"]["tasks"]:
        for up in t["upstream"]:
            m = l0_contract.EXTERNAL_UPSTREAM.fullmatch(up)
            if m and m.groups() not in refs:
                refs.append(m.groups())
    return refs


def approved_contract(root, mart, cache):
    if mart not in cache:
        rel = f"docs/requirements/{mart}.contract.json"
        text = l0_dag.git_show_approved(root, rel)
        if text is None:
            raise common.InputInvalid(f"상류 준비: {l0_dag.APPROVED_REF}에 {rel}이 없음")
        try:
            cache[mart] = json.loads(text)
        except json.JSONDecodeError:
            raise common.InputInvalid(f"상류 준비: {l0_dag.APPROVED_REF}의 {rel}을 읽지 못함") from None
    return cache[mart]


def plan(paths, contract):
    """[(마트, task, 테이블 이름)] 준비할 load task를 의존 순서로. 빌린 task가 없으면 []."""
    refs = external_refs(contract)
    if not refs:
        return []
    cache, order, done, stack = {}, [], set(), []

    def visit(mart, tid):
        key = (mart, tid)
        if key in done:
            return
        if key in stack:
            loop = [*stack[stack.index(key):], key]
            raise common.InputInvalid("상류 준비: 순환 " + " -> ".join(f"{m}:{t}" for m, t in loop))
        if mart == paths.mart:
            raise common.InputInvalid(f"상류 준비: 빌린 task의 상류가 이 마트의 task {tid}로 돌아옴")
        other = approved_contract(paths.root, mart, cache)
        tasks = {t["id"]: t for t in other.get("dag", {}).get("tasks", []) if isinstance(t, dict) and "id" in t}
        task = tasks.get(tid)
        if task is None:
            raise common.InputInvalid(f"상류 준비: {l0_dag.APPROVED_REF}의 {mart} contract에 task {tid!r}가 없음")
        stack.append(key)
        for up in task.get("upstream", []):
            m = l0_contract.EXTERNAL_UPSTREAM.fullmatch(up)
            visit(*m.groups()) if m else visit(mart, up)
        stack.pop()
        done.add(key)
        if task.get("kind") == "load":
            table = next((t.get("name") for t in other.get("tables", []) if t.get("task") == tid), None)
            if not isinstance(table, str) or not NAME.fullmatch(table):
                raise common.InputInvalid(f"상류 준비: {mart} contract에서 task {tid}의 테이블을 찾지 못함")
            order.append((mart, task, table))

    for mart, tid in refs:
        visit(mart, tid)
    return order


def normalized(text):
    return text.lstrip("﻿").replace("\r\n", "\n")


def check_same_as_approved(paths, mart, task):
    """작업 트리의 빌린 SQL이 origin/main과 같은지 (결정 70). 다르면 InputInvalid."""
    path = paths.task_sql(task)
    rel = path.relative_to(paths.root).as_posix()
    approved = l0_dag.git_show_approved(paths.root, rel)
    if approved is None:
        raise common.InputInvalid(f"상류 준비: {l0_dag.APPROVED_REF}에 {mart}:{task['id']}의 SQL {rel}이 없음")
    try:
        local = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        raise common.InputInvalid(f"상류 준비: 작업 트리의 {rel}을 읽지 못함 ({e.__class__.__name__})") from None
    if normalized(local) != normalized(approved):
        raise common.InputInvalid(f"상류 준비: 작업 트리의 빌린 SQL {rel}이 {l0_dag.APPROVED_REF}와 다름 "
                                  "(빌린 task는 고치지 않는다. 고쳐야 하면 원래 마트의 contract v2)")


def partition_has_rows(ctx, table):
    """ai_dev의 같은 ds 파티션에 행이 있나. 하네스 확인 쿼리라 실패하면 InfraError."""
    sql = (f"SELECT total_rows\n"
           f"FROM `{ctx.project}.{common.DEV_DATASET}.INFORMATION_SCHEMA.PARTITIONS`\n"
           f"WHERE table_name = '{table}' AND partition_id = '{ctx.ds.strftime('%Y%m%d')}'")
    try:
        ctx.bq.dry_run(sql)
        rows = ctx.bq.run(sql, max_rows=1)
    except common.QueryError as e:
        raise common.InfraError(f"파티션 확인 쿼리 실패: {e}") from None
    total = 0
    for r in rows:
        try:
            total += int(r.get("total_rows") or 0)
        except (TypeError, ValueError):
            raise common.InfraError(f"파티션 확인 결과를 읽지 못함: {r!r}") from None
    return total > 0


def prepare(ctx, mart, task, table, items):
    label = f"{mart}:{task['id']}"
    before, skipped = ctx.bq.bytes_total, False
    try:
        if partition_has_rows(ctx, table):
            skipped = True
            return
        sql = common.render(ctx.paths.task_sql(task).read_text(encoding="utf-8"), ctx.project, ctx.ds)
        common.check_prod(sql)
        ctx.bq.dry_run(sql)
        l2_run.execute(ctx, task)
    except common.QueryError as e:
        raise common.InputInvalid(f"상류 준비 {label}: 빌린 SQL 오류({e.error_type}). 원래 마트 {mart}의 "
                                  f"contract v2로 고친다: {e}") from None
    except common.InfraError as e:  # 권한 막힘(builder_blocked)도 준비 실행에서는 infra_error (결정 70)
        raise common.InfraError(f"상류 준비 {label}: {e}") from None
    finally:
        items.append({"task": label, "skipped": skipped, "bytes": ctx.bq.bytes_total - before})


def run(ctx, items):
    """준비 실행. items(list)에 task별 기록을 쌓는다. 실패는 InputInvalid·InfraError로 올린다."""
    order = plan(ctx.paths, ctx.contract)
    for mart, task, _table in order:  # 실행 전에 모두 확인한다: 하나라도 다르면 아무것도 돌리지 않는다
        check_same_as_approved(ctx.paths, mart, task)
    for mart, task, table in order:
        prepare(ctx, mart, task, table, items)
    return items
