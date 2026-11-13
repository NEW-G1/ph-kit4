"""L0 ② DAG 파일 문법, ③ task·의존성·SQL 파일 대조와 검증 쿼리 머리말 검사 (03 §5.3, 결정 59).

Airflow 없이 검사한다. DAG 파일은 실행하지 않고 ast로 읽는다.
- ② dags/harness_daily.py가 파이썬 문법으로 읽히는지. 실제 import(연산자 인자, Airflow API 오용)는
  잡지 못한다. 알려진 한계: 실제 import는 결재 후 사람이 수동 배포할 때 처음 확인된다 (결정 59)
- ③ DAG 파일 최상위의 리터럴 `UPSTREAM = {task id: [상류 task id, ...]}`가 contract들의 dag.tasks와 같은지,
  dags/sql/<layer>/<task>.sql·dags/sql/dq/<gate>.sql이 task와 1:1인지(고아 0, 결정 50).
  DAG 하나에 마트가 여럿 들어가므로 docs/requirements/*.contract.json 전체와 비교한다
- ③ SQL과 contract 대조(결함 주입 후속 D04, 시험 뒤 고침): numerator·denominator가 있는 비율 지표가 SAFE_DIVIDE로
  계산되는지(sql_rules.md §3). 텍스트만 본다. 별칭 없이 쓴 지표 식은 보지 못한다
- ③ 증분 적재(contract load.mode = incremental, 결정 79): load task SQL의 문장마다 데이터 날짜 조건이 있는지
  (sql_rules.md §1-2). 주석·문자열을 지운 텍스트를 세미콜론으로 나눠 문장 첫 낱말(CREATE·DELETE·INSERT)로 고르고
  정규식으로 본다. (1) CREATE에 PARTITION BY <partition_column>, partition_expiration_days 없음
  (2) DELETE에 <partition_column> = DATE('{{ ds }}') (3) INSERT에 raw는 DATE(<date_column>) = DATE('{{ ds }}')
  (원천 SELECT), stg·mart는 <partition_column> = DATE('{{ ds }}')(상류 파티션). 조건이 그 문장 어디에 있는지
  (WHERE·ON)와 모든 상류에 걸렸는지는 보지 않는다. snapshot이면 보지 않는다
- 검증 쿼리 _checks/l3·l4·l5: 머리말 형식, error_type·task, 파일 이름 = contract check id와 단계, 빠진 파일
- 판정 원칙(결정 59): builder 파일(DAG 파일, dags/sql/raw|stg|mart/) 문제는 반려 rung,
  contract·_checks/·dags/sql/dq/ 문제는 common.InputInvalid(halt input_invalid)
- 다른 contract의 upstream(<마트>:<task>, 결정 61 ④): origin/main에 그 contract가 있고(결재 1 = PR 머지) task가 있는지.
  git fetch origin main 뒤에 확인하고, 아니면 halt input_invalid(contract 문제). fetch 실패는 infra_error(종료 코드 2).
  DAG 파일의 UPSTREAM에는 task id만 적는다(task id는 전역에서 고유).
  빌려 오는 마트와 load.mode가 다르거나, 둘 다 incremental인데 partition_column이 다르면 halt input_invalid(결정 79)
"""
import ast
import json
import re
import shutil
import subprocess

import l0_contract

import common
import load_mode

LAYER_FOLDERS = ("raw", "stg", "mart", "dq")
UNSAFE_DIVISION = re.compile(r"/|\bdiv\s*\(")
SAFE_DIVIDE = re.compile(r"\bsafe_divide\s*\(")
STATEMENT_KIND = re.compile(r"\s*(create|delete|insert)\b")
DS_DATE = r"\s*=\s*date\(\s*\)"  # strip_sql 뒤의 DATE('{{ ds }}') (문자열이 지워짐)


def fail(error_type, errors):
    return common.rung("L0", None, {"stage": "dag", "errors": errors}, error_type)


def all_contracts(paths):
    out = []
    for f in sorted(paths.requirements.glob("*.contract.json")):
        if f.name.startswith("_"):
            continue
        try:
            out.append(json.loads(f.read_text(encoding="utf-8")))
        except (OSError, ValueError) as e:  # ValueError: JSONDecodeError·UnicodeDecodeError
            raise common.InputInvalid(f"{f.name}을 읽지 못함: {e.__class__.__name__}") from None
    return out


def read_upstream(dag_file):
    """(UPSTREAM dict, 오류 목록). 문법 오류는 ('import', 메시지)."""
    try:
        tree = ast.parse(dag_file.read_text(encoding="utf-8"), filename=dag_file.name)
    except FileNotFoundError:
        return None, ("import", f"DAG 파일이 없음: dags/{dag_file.name}")
    except UnicodeDecodeError as e:  # builder 파일이므로 반려 (결정 59 판정 원칙)
        return None, ("import", f"DAG 파일을 UTF-8로 읽지 못함: {e}")
    except SyntaxError as e:
        return None, ("import", f"DAG 파일 문법 오류 {e.lineno}행: {e.msg}")
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "UPSTREAM" for t in node.targets):
            try:
                value = ast.literal_eval(node.value)
            except ValueError:
                return None, ("structure", "UPSTREAM은 리터럴 dict여야 함 (계산식 없이)")
            ok = isinstance(value, dict) and all(
                isinstance(k, str) and isinstance(v, list) and all(isinstance(x, str) for x in v)
                for k, v in value.items())
            if not ok:
                return None, ("structure", "UPSTREAM은 {task id: [상류 task id]} 형식이어야 함")
            return value, None
    return None, ("structure", "DAG 파일 최상위에 UPSTREAM이 없음")


def check_structure(paths, contracts):
    """(error_type, builder 파일 오류, 입력 파일 오류). 입력 파일 = contract 사이 task id 중복, dags/sql/dq/(gen_dq 생성)."""
    errors, input_errors = [], []
    expected, tasks = {}, []
    for c in contracts:
        for t in c["dag"]["tasks"]:
            if t["id"] in expected:
                input_errors.append(f"task id {t['id']!r}가 여러 contract에 있음")
            expected[t["id"]] = sorted(u.split(":", 1)[-1] for u in t["upstream"])
            tasks.append(t)
    upstream, problem = read_upstream(paths.dag_file)
    if problem and problem[0] == "import":
        return "dag_import_error", [problem[1]], input_errors
    if problem:
        errors.append(problem[1])
    else:
        actual = {k: sorted(v) for k, v in upstream.items()}
        for tid in sorted(set(expected) - set(actual)):
            errors.append(f"DAG에 없는 task {tid!r}")
        for tid in sorted(set(actual) - set(expected)):
            errors.append(f"contract에 없는 task {tid!r}가 DAG에 있음")
        for tid in sorted(set(expected) & set(actual)):
            if expected[tid] != actual[tid]:
                errors.append(f"{tid}의 상류가 다름: contract {expected[tid]} / DAG {actual[tid]}")
    wanted = {paths.task_sql(t).resolve(): t["kind"] for t in tasks}
    for path, kind in sorted(wanted.items()):
        if not path.exists():
            (input_errors if kind == "gate" else errors).append(
                f"task의 SQL 파일이 없음: {path.relative_to(paths.root.resolve()).as_posix()}")
    for folder in LAYER_FOLDERS:
        for path in sorted((paths.sql / folder).glob("*.sql")) if (paths.sql / folder).is_dir() else []:
            if path.resolve() not in wanted:
                (input_errors if folder == "dq" else errors).append(f"task가 없는 고아 SQL: dags/sql/{folder}/{path.name}")
    return ("dag_structure_mismatch" if errors else None), errors, input_errors


def expression_before(sql, end):
    """SELECT 항목의 끝(end)에서 거슬러 올라가 그 항목의 식을 돌려준다."""
    depth = 0
    for i in range(end - 1, -1, -1):
        ch = sql[i]
        if ch == ")":
            depth += 1
        elif ch == "(" and depth:
            depth -= 1
        elif depth == 0 and (ch in "(," or sql.endswith("select", 0, i + 1)):
            return sql[i + 1:end]
    return sql[:end]


def ratio_errors(sql, table, ratios):
    """이 테이블의 비율 지표 별칭을 찾아 식을 본다. 바깥 SELECT가 값을 넘기기만 하는 항목이 있어 전체 별칭 중 하나만 있으면 된다."""
    errors = []
    for column in (c["name"] for c in table["columns"] if c["name"] in ratios):
        found = [expression_before(sql, m.start()) for m in re.finditer(rf"\bas\s+{column}\b", sql)]
        if found and (any(UNSAFE_DIVISION.search(e) for e in found) or not any(SAFE_DIVIDE.search(e) for e in found)):
            errors.append(f"{table['name']}.{column}: contract의 비율 지표는 SAFE_DIVIDE로 계산한다 (sql_rules.md §3)")
    return errors


def incremental_errors(sql, task, contract):
    """증분 적재 SQL 1개(strip_sql 뒤)의 데이터 날짜 조건을 본다 (결정 79, sql_rules.md §1-2)."""
    pc, dc = load_mode.partition_column(contract), load_mode.date_column(contract)
    by_kind = {}
    for statement in sql.split(";"):
        m = STATEMENT_KIND.match(statement)
        if m:
            by_kind.setdefault(m.group(1), []).append(statement)
    where = f"sql/{task['layer']}/{task['id']}.sql"
    ds = "DATE('{{ ds }}')"
    partition_ds = re.compile(rf"(?<![\w.])(?:\w+\.)?{pc}{DS_DATE}")
    errors = []
    creates = by_kind.get("create", [])
    if not any(re.search(rf"\bpartition\s+by\s+(?:\w+\.)?{pc}\b", st) for st in creates):
        errors.append(f"{where}: (1) CREATE에 PARTITION BY {pc}가 없음 (증분 적재, sql_rules.md §1-2)")
    if any(re.search(r"\bpartition_expiration_days\b", st) for st in creates):
        errors.append(f"{where}: (1) 증분 적재 테이블에는 partition_expiration_days를 두지 않는다 (sql_rules.md §1-2)")
    if not any(partition_ds.search(st) for st in by_kind.get("delete", [])):
        errors.append(f"{where}: (2) DELETE에 {pc} = {ds} 조건이 없음 (증분 적재)")
    inserts = by_kind.get("insert", [])
    if task["layer"] == "raw":
        source_ds = re.compile(rf"(?:\bdate\s*\(\s*(?:\w+\.)?{dc}\s*\)|(?<![\w.])(?:\w+\.)?{dc}){DS_DATE}")
        if not any(source_ds.search(st) for st in inserts):
            errors.append(f"{where}: (3) 원천 SELECT에 DATE({dc}) = {ds} 조건이 없음 (증분 적재)")
    elif not any(partition_ds.search(st) for st in inserts):
        errors.append(f"{where}: (3) INSERT의 상류 읽기에 {pc} = {ds} 조건이 없음 (증분 적재)")
    return errors


def check_sql_contract(paths, contract):
    """이 contract의 비율 지표(와 증분 적재면 날짜 조건)를 적재 SQL과 대조해 오류 목록을 돌려준다.
    SQL 파일은 check_structure가 확인한 뒤에 부른다."""
    tasks = {t["id"]: t for t in contract["dag"]["tasks"]}
    ratios = {m["name"] for m in contract["interview"]["metrics"] if m["numerator"] is not None}
    incremental = load_mode.is_incremental(contract)
    errors = []
    for table in contract["tables"]:
        task = tasks[table["task"]]
        # UTF-8이 아닌 builder SQL은 L1이 syntax로 반려한다. 여기서는 깨진 바이트만 바꿔 읽는다 (check_sql_dir와 같음)
        sql = l0_contract.strip_sql(paths.task_sql(task).read_bytes().decode("utf-8", "replace"))
        errors += ratio_errors(sql, table, ratios)
        if incremental:
            errors += incremental_errors(sql, task, contract)
    return errors


def check_checks(paths, contract):
    errors = []
    loads = {t["id"] for t in contract["dag"]["tasks"] if t["kind"] == "load"}
    rungs = {c["id"]: c["rung"] for group in contract["checks"].values() for c in group}
    found = set()
    for stage in common.STAGES:
        for f in paths.check_files(stage):
            try:
                header, _ = common.parse_check(f.read_text(encoding="utf-8"))
            except ValueError as e:
                errors.append(f"{stage}/{f.name}: {e}")
                continue
            if header["task"] not in loads:
                errors.append(f"{stage}/{f.name}: task {header['task']!r}가 contract의 load task가 아님")
            if f.stem not in rungs:
                errors.append(f"{stage}/{f.name}: contract checks에 없는 id")
            elif rungs[f.stem] != common.STAGE_RUNG[stage]:
                errors.append(f"{stage}/{f.name}: contract의 rung은 {rungs[f.stem]}")
            found.add(f.stem)
    for cid, r in sorted(rungs.items()):
        if r in ("L3", "L4", "L5") and cid not in found:
            errors.append(f"contract check {cid}({r})의 검증 쿼리 파일이 없음: {r.lower()}/{cid}.sql")
    return errors


APPROVED_REF = "origin/main"  # 결재 1 = GitHub PR 머지이므로 로컬 main이 아니라 원격 main을 본다


def git(root, *args, timeout=30):
    exe = shutil.which("git")
    if exe is None:
        raise common.InfraError("git 명령을 찾지 못함")
    try:
        return subprocess.run([exe, "-C", str(root), *args], capture_output=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise common.InfraError(f"git {args[0]} 실행 실패: {e.__class__.__name__}") from None


def fetch_approved(root):
    """git fetch origin main. 실패하면 InfraError (결재 여부를 확인할 수 없으므로 반려가 아님)."""
    out = git(root, "fetch", "origin", "main", timeout=120)
    if out.returncode != 0:
        raise common.InfraError("git fetch origin main 실패: " + out.stderr.decode("utf-8", "replace").strip()[:300])


def git_show_approved(root, rel):
    """origin/main의 파일 내용. 없으면 None."""
    spec = f"{APPROVED_REF}:{rel}"
    if git(root, "cat-file", "-e", spec).returncode:
        return None
    out = git(root, "show", spec)
    return out.stdout.decode("utf-8", "replace") if out.returncode == 0 else None


def check_external(paths, contract):
    """다른 contract의 upstream이 origin/main에 있는(결재 1을 받은) contract의 task인지 (결정 61 ④ a).

    빌린 task가 있을 때만 git fetch origin main을 먼저 한다. fetch가 실패하면 InfraError.
    """
    refs = [(t, up, m) for t in contract["dag"]["tasks"] for up in t["upstream"]
            if (m := l0_contract.EXTERNAL_UPSTREAM.fullmatch(up))]
    if not refs:
        return []
    fetch_approved(paths.root)
    errors, cache = [], {}
    for t, up, m in refs:
        mart, task_id = m.groups()
        rel = f"docs/requirements/{mart}.contract.json"
        if mart not in cache:
            text = git_show_approved(paths.root, rel)
            try:
                cache[mart] = json.loads(text) if text is not None else None
            except json.JSONDecodeError:
                cache[mart] = None
        other = cache[mart]
        if other is None:
            errors.append(f"{t['id']}의 상류 {up}: {APPROVED_REF}에 {rel}이 없음 (결재 1을 받은 contract만 빌려 쓴다)")
            continue
        found = {x["id"]: x for x in other.get("dag", {}).get("tasks", []) if isinstance(x, dict) and "id" in x}
        mine, theirs = load_mode.mode(contract), load_mode.mode(other)
        if mine != theirs:
            errors.append(f"{t['id']}의 상류 {up}: 적재 방식이 다름 (이 마트 load.mode {mine}, {mart} {theirs}, 결정 79)")
        elif mine == load_mode.INCREMENTAL and load_mode.partition_column(contract) != load_mode.partition_column(other):
            errors.append(f"{t['id']}의 상류 {up}: load.partition_column이 다름 (이 마트 "
                          f"{load_mode.partition_column(contract)}, {mart} {load_mode.partition_column(other)}, 결정 79)")
        if task_id not in found:
            errors.append(f"{t['id']}의 상류 {up}: {APPROVED_REF}의 {mart} contract에 task {task_id!r}가 없음")
        elif t["kind"] == "load" and t["layer"] == "mart" and found[task_id].get("layer") == "raw":
            errors.append(f"{t['id']}의 상류 {up}: mart는 raw를 직접 읽지 않는다 (task_design.md 규칙 3)")
    return errors


def check(paths, contract):
    """L0 ②·③과 검증 쿼리 머리말. 통과면 None, builder 파일 문제면 L0 rung(반려).
    verifier·사람·하네스 파일 문제는 InputInvalid, git fetch 실패는 InfraError로 올린다 (결정 59 판정 원칙)."""
    check_errors = check_checks(paths, contract)
    if check_errors:
        raise common.InputInvalid("검증 쿼리: " + "; ".join(check_errors))
    external = check_external(paths, contract)
    if external:
        raise common.InputInvalid("다른 contract의 upstream: " + "; ".join(external))
    error_type, errors, input_errors = check_structure(paths, all_contracts(paths))
    if input_errors:
        raise common.InputInvalid("; ".join(input_errors))
    if error_type:
        return fail(error_type, errors)
    sql_errors = check_sql_contract(paths, contract)
    return fail("dag_structure_mismatch", sql_errors) if sql_errors else None
