"""L0 ① contract.json 형식 검사와 개인 식별 컬럼 차단 (03 §5.3, 결정 51 ⑦). 표준 라이브러리만 쓴다.

결과는 ladder_result의 rung 형식({rung, status, metrics, error_type, error_class})으로 돌려준다.
실패하면 이유 목록은 metrics.errors에 담는다. error_type은 개인 식별 컬럼 실패가 하나라도 있으면
pii_column(semantic), 그 외 형식 오류만 있으면 contract_invalid(syntax)다.
개인 식별 컬럼 목록은 docs/architecture/pii_columns.md에서, 결재된 원천은 dags/harness_config.json에서 읽는다.
로그는 기록하지 않는다 (기록은 run_ladder.py가 scripts/log/devlog.py로 한다, 결정 56 ④).
L0 ② DAG 파일, ③ task·SQL 파일 대조는 l0_dag.py가 한다.

  python scripts/ladder/l0_contract.py docs/requirements/<마트>.contract.json [--sql-dir dags/sql]
  → 결과 JSON을 출력하고, 통과면 종료 코드 0, 실패면 1
"""
import json
import re
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / "scripts" / "ladder"))
import harness_config  # noqa: E402
import load_mode  # noqa: E402

PII_FILE = PROJECT / "docs" / "architecture" / "pii_columns.md"
SQL_DIR = PROJECT / "dags" / "sql"
LAYERS = ("raw", "stg", "mart")
RULE_BAD_CHARS = "{}'\\\n"  # gen_dq.message와 같은 글자
TASK_KINDS = {"load", "gate"}
RUNGS = {"L0", "L1", "L2", "L3", "L4", "L5", "L6"}
# 검사 종류마다 허용하는 판정 단계와 작성 주체 (2-9 결재).
# 작성 주체는 모두 verifier다. builder는 _checks/를 쓸 수 없어 written_by: builder인 contract는 루프를
# 통과할 수 없다 (결정 63 11/2 보완)
CHECK_RULES = {
    "gates": {"prefix": "C", "rungs": {"L3"}, "written_by": {"verifier"}},
    "reconciliation": {"prefix": "C", "rungs": {"L4"}, "written_by": {"verifier"}},
    "invariants": {"prefix": "I", "rungs": {"L4", "L5"}, "written_by": {"verifier"}},
}
BQ_TYPES = {"STRING", "INT64", "NUMERIC", "BIGNUMERIC", "FLOAT64", "BOOL", "DATE", "DATETIME",
            "TIMESTAMP", "TIME", "BYTES", "JSON", "GEOGRAPHY", "INTERVAL"}
NAME = re.compile(r"[a-z][a-z0-9_]*")
# 다른 contract(main에 있는 마트)의 task를 빌려 쓸 때 upstream 표기 (결정 61 ④ c). 있는지는 L0 ③이 본다
EXTERNAL_UPSTREAM = re.compile(r"([a-z][a-z0-9_]*):([a-z][a-z0-9_]*)")
TOP_FIELDS = ("mart", "version", "requirements", "sources", "interview", "tables", "dag",
              "checks", "traces_to", "schedule", "modules")
# 되돌림 버전 번호 (결정 64 ②), 요청자 역할 코드 (결정 71), 적재 방식 (결정 79, 없으면 snapshot)
TOP_OPTIONAL_FIELDS = ("reverts_to", "requested_by", "load")
REQUESTER = re.compile(r"requester[1-9]\d*")  # 역할 코드만. 사람 이름은 넣지 않는다 (대응표는 repo 밖)
OPTIONAL_FIELDS = ("name_ko",)  # tables[]·columns[]의 선택 칸 (결정 53)


class Checker:
    def __init__(self, pii_names=frozenset()):
        self.errors = []
        self.pii_errors = []
        self.pii_names = pii_names

    def fail(self, where, message):
        self.errors.append(f"{where}: {message}")

    def pii(self, where, message):
        self.pii_errors.append(f"{where}: {message}")

    # ---------- 공통 ----------

    def obj(self, value, where, fields, optional=()):
        """객체이고 정해진 칸만 모두 있는지 본다(optional 칸은 없어도 됨). 맞으면 True."""
        if not isinstance(value, dict):
            self.fail(where, "객체여야 함")
            return False
        missing = [f for f in fields if f not in value]
        extra = sorted(set(value) - set(fields) - set(optional))
        if missing:
            self.fail(where, f"필수 칸 없음 {missing}")
        if extra:
            self.fail(where, f"정해지지 않은 칸 {extra}")
        return not missing

    def text(self, value, where):
        if not isinstance(value, str) or not value.strip():
            self.fail(where, "비어 있지 않은 문자열이어야 함")
            return False
        return True

    def name(self, value, where):
        if self.text(value, where) and not NAME.fullmatch(value):
            self.fail(where, f"이름 {value!r}은 소문자·숫자·밑줄만 쓴다")
            return False
        return isinstance(value, str) and bool(NAME.fullmatch(value))

    def name_ko(self, obj, where):
        # 한글명은 선택 칸. 쓰면 비어 있지 않은 문자열 (결정 53)
        if "name_ko" in obj:
            self.text(obj["name_ko"], f"{where}.name_ko")

    def items(self, value, where, allow_empty=False):
        if not isinstance(value, list):
            self.fail(where, "목록이어야 함")
            return []
        if not value and not allow_empty:
            self.fail(where, "비어 있음")
        return value

    def text_list(self, value, where):
        for i, v in enumerate(self.items(value, where)):
            self.text(v, f"{where}[{i}]")

    def one_of(self, value, allowed, where):
        if not isinstance(value, str) or value not in allowed:
            self.fail(where, f"{value!r}은 허용 값이 아님 {sorted(allowed)}")
            return False
        return True

    def unique(self, values, where):
        seen = set()
        for v in values:
            if not isinstance(v, str):
                continue
            if v in seen:
                self.fail(where, f"중복 {v!r}")
            seen.add(v)

    def positive_int(self, value, where):
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            self.fail(where, "1 이상 정수여야 함")
            return False
        return True

    # ---------- 칸별 ----------

    def check(self, c):
        if not self.obj(c, "contract", TOP_FIELDS, TOP_OPTIONAL_FIELDS):
            if not isinstance(c, dict):
                return
        self.name(c.get("mart"), "mart")
        version_ok = self.positive_int(c.get("version"), "version")
        self.reverts_to(c.get("reverts_to"), c.get("version") if version_ok else None)
        self.requested_by(c.get("requested_by"))
        req_ids = self.requirements(c.get("requirements"))
        self.sources(c.get("sources"))
        self.interview(c.get("interview"))
        tasks = self.dag(c.get("dag"), c.get("mart"))
        self.tables(c.get("tables"), tasks)
        self.load(c, c.get("tables"))
        checks = self.checks(c.get("checks"))
        self.traces(c.get("traces_to"), req_ids, checks)
        self.schedule(c.get("schedule"))
        self.modules(c.get("modules"))

    def reverts_to(self, value, version):
        """선택 칸. null·없음은 통과, 있으면 1 ≤ reverts_to < version 인 정수 (결정 64 ②)."""
        if value is None:
            return
        if not self.positive_int(value, "reverts_to"):
            return
        if version is not None and value >= version:
            self.fail("reverts_to", f"version({version})보다 작아야 함")

    def requested_by(self, value):
        """선택 칸. null·없음은 통과(대시보드는 "-"), 있으면 역할 코드 requester<숫자> (결정 71)."""
        if value is None:
            return
        if not isinstance(value, str) or not REQUESTER.fullmatch(value):
            self.fail("requested_by", "역할 코드 requester<숫자>여야 함 (이름은 넣지 않는다)")

    def requirements(self, value):
        ids = []
        for i, r in enumerate(self.items(value, "requirements")):
            where = f"requirements[{i}]"
            if not self.obj(r, where, ("id", "text", "section")):
                continue
            if self.text(r["id"], f"{where}.id"):
                if re.fullmatch(r"R-\d{2,}", r["id"]):
                    ids.append(r["id"])
                else:
                    self.fail(f"{where}.id", f"{r['id']!r}은 R-01 형식이 아님")
            self.text(r["text"], f"{where}.text")
            sec = r["section"]
            if isinstance(sec, bool) or not isinstance(sec, int) or not 1 <= sec <= 9:
                self.fail(f"{where}.section", f"요구서 절 번호 1~9여야 함 (따옴표 없는 숫자, 예: 3. 지금 값 {sec!r})")
        self.unique(ids, "requirements.id")
        return set(ids)

    def sources(self, value):
        srcs = self.items(value, "sources")
        source = harness_config.source_pattern()
        for i, s in enumerate(srcs):
            if self.text(s, f"sources[{i}]") and not source.fullmatch(s):
                self.fail(f"sources[{i}]", f"{harness_config.source_prefix()}.<table> 형식이어야 함")
        self.unique([s for s in srcs if isinstance(s, str)], "sources")

    def interview(self, value):
        fields = ("metrics", "grain", "keys", "assumptions", "out_of_scope")
        if not self.obj(value, "interview", fields):
            if not isinstance(value, dict):
                return
        metric_fields = ("name", "formula", "unit", "base_date", "exclude", "numerator", "denominator")
        names = []
        for i, m in enumerate(self.items(value.get("metrics"), "interview.metrics")):
            where = f"interview.metrics[{i}]"
            if not self.obj(m, where, metric_fields):
                continue
            for f in ("name", "formula", "unit", "base_date", "exclude"):
                self.text(m[f], f"{where}.{f}")
            num, den = m["numerator"], m["denominator"]
            if (num is None) != (den is None):
                self.fail(where, "numerator와 denominator는 함께 쓰거나 함께 null이어야 함")
            for f, v in (("numerator", num), ("denominator", den)):
                if v is not None:
                    self.text(v, f"{where}.{f}")
            names.append(m["name"])
        self.unique(names, "interview.metrics.name")
        self.text(value.get("grain"), "interview.grain")
        for f in ("keys", "assumptions", "out_of_scope"):
            self.text_list(value.get(f), f"interview.{f}")

    def dag(self, value, mart=None):
        """task 목록을 검사하고 {id: task}를 돌려준다. 다른 contract의 upstream(<마트>:<task>)은 형식만 본다."""
        if not self.obj(value, "dag", ("tasks",)):
            return {}
        tasks = {}
        raw_list = self.items(value["tasks"], "dag.tasks")
        for i, t in enumerate(raw_list):
            where = f"dag.tasks[{i}]"
            if not self.obj(t, where, ("id", "kind", "layer", "upstream")):
                continue
            ok = self.name(t["id"], f"{where}.id")
            ok &= self.one_of(t["kind"], TASK_KINDS, f"{where}.kind")
            ok &= self.one_of(t["layer"], set(LAYERS), f"{where}.layer")
            if not isinstance(t["upstream"], list):
                self.fail(f"{where}.upstream", "목록이어야 함")
                ok = False
            if ok:
                if t["id"] in tasks:
                    self.fail("dag.tasks.id", f"중복 {t['id']!r}")
                tasks[t["id"]] = t
        for tid, t in tasks.items():
            for up in t["upstream"]:
                ext = EXTERNAL_UPSTREAM.fullmatch(up) if isinstance(up, str) and ":" in up else None
                if isinstance(up, str) and ":" in up:
                    if ext is None:
                        self.fail(f"dag.tasks[{tid}].upstream", f"다른 contract의 task는 <마트>:<task>로 적는다: {up!r}")
                    elif ext.group(1) == mart:
                        self.fail(f"dag.tasks[{tid}].upstream", f"같은 contract의 task는 task id만 적는다: {up!r}")
                    continue
                if up == tid:
                    self.fail(f"dag.tasks[{tid}].upstream", "자기 자신을 가리킴")
                elif up not in tasks:
                    self.fail(f"dag.tasks[{tid}].upstream", f"없는 task {up!r}")
                elif t["kind"] == "load" and t["layer"] == "mart" and tasks[up]["layer"] == "raw":
                    self.fail(f"dag.tasks[{tid}].upstream", f"mart는 raw({up!r})를 직접 읽지 않는다 (task_design.md 규칙 3)")
        self.cycles(tasks)
        # 게이트 task id는 gate_<층>_<마트> (결정 61 ②)
        if isinstance(mart, str) and NAME.fullmatch(mart):
            for tid, t in tasks.items():
                if t["kind"] == "gate" and tid != f"gate_{t['layer']}_{mart}":
                    self.fail(f"dag.tasks[{tid}].id", f"게이트 task id는 gate_{t['layer']}_{mart}여야 함 (결정 61)")
        # 적재 task가 있는 층마다 게이트 task 1개, 마트(contract)별 (task_design.md 규칙 2, 결정 61 ①)
        for layer in LAYERS:
            loads = [t for t in tasks.values() if t["layer"] == layer and t["kind"] == "load"]
            gates = [t for t in tasks.values() if t["layer"] == layer and t["kind"] == "gate"]
            if loads and len(gates) != 1:
                self.fail("dag.tasks", f"{layer} 층 게이트 task가 {len(gates)}개 (1개여야 함)")
            if gates and not loads:
                self.fail("dag.tasks", f"{layer} 층에 적재 task가 없는데 게이트 task가 있음")
        return tasks

    def cycles(self, tasks):
        state = {}

        def visit(tid):
            if state.get(tid) == 1:
                return True
            if state.get(tid) == 2:
                return False
            state[tid] = 1
            found = any(visit(u) for u in tasks[tid]["upstream"] if u in tasks and u != tid)
            state[tid] = 2
            return found

        if any(visit(tid) for tid in tasks):
            self.fail("dag.tasks", "upstream에 순환이 있음")

    def tables(self, value, tasks):
        fields = ("name", "layer", "task", "grain", "keys", "columns")
        names, used_tasks = [], []
        for i, t in enumerate(self.items(value, "tables")):
            where = f"tables[{i}]"
            if not self.obj(t, where, fields, OPTIONAL_FIELDS):
                continue
            self.name(t["name"], f"{where}.name")
            names.append(t["name"])
            self.name_ko(t, where)
            self.one_of(t["layer"], set(LAYERS), f"{where}.layer")
            task = tasks.get(t["task"]) if isinstance(t["task"], str) else None
            if task is None:
                self.fail(f"{where}.task", f"dag.tasks에 없는 task {t['task']!r}")
            elif task["kind"] != "load":
                self.fail(f"{where}.task", "게이트 task는 테이블을 만들지 않는다")
            elif task["layer"] != t["layer"]:
                self.fail(f"{where}.layer", f"task {task['id']!r}의 층({task['layer']})과 다름")
            used_tasks.append(t["task"])
            self.text(t["grain"], f"{where}.grain")
            col_names = []
            for j, col in enumerate(self.items(t["columns"], f"{where}.columns")):
                cw = f"{where}.columns[{j}]"
                if not self.obj(col, cw, ("name", "type", "description"), OPTIONAL_FIELDS):
                    continue
                self.name(col["name"], f"{cw}.name")
                col_names.append(col["name"])
                self.name_ko(col, cw)
                # 개인 식별 컬럼은 stg·mart에 두지 않는다. raw는 원천을 가공 없이 보관 (결정 51 ⑦)
                if t["layer"] in ("stg", "mart") and isinstance(col["name"], str) and col["name"] in self.pii_names:
                    self.pii(f"{cw}.name", f"개인 식별 컬럼 {col['name']!r}은 stg·mart에 두지 않는다 (pii_columns.md)")
                if self.text(col["type"], f"{cw}.type"):
                    base = re.split(r"[<(]", col["type"].upper(), 1)[0].strip()
                    if base not in BQ_TYPES | {"ARRAY", "STRUCT"}:
                        self.fail(f"{cw}.type", f"BigQuery 타입이 아님 {col['type']!r}")
                self.text(col["description"], f"{cw}.description")
            self.unique(col_names, f"{where}.columns.name")
            for k, key in enumerate(self.items(t["keys"], f"{where}.keys")):
                if self.text(key, f"{where}.keys[{k}]") and key not in col_names:
                    self.fail(f"{where}.keys[{k}]", f"columns에 없는 키 {key!r}")
        self.unique(names, "tables.name")
        self.unique(used_tasks, "tables.task")
        # 테이블 1개 = 적재 task 1개 (task_design.md 규칙 1)
        for tid, t in tasks.items():
            if t["kind"] == "load" and tid not in used_tasks:
                self.fail("tables", f"적재 task {tid!r}가 만드는 테이블이 없음")

    def load(self, c, tables):
        """선택 칸 load (결정 79). 없으면 snapshot. snapshot이면 mode만, incremental이면 date_column·partition_column 필수,
        allow_empty_days는 선택(참·거짓). incremental의 partition_column은 모든 테이블에 DATE 컬럼으로 있어야 한다."""
        if "load" not in c:
            return
        value = c["load"]
        if not isinstance(value, dict):
            self.fail("load", "객체여야 함")
            return
        if not self.one_of(value.get("mode"), set(load_mode.MODES), "load.mode"):
            return
        mode = value["mode"]
        if not self.obj(value, "load", load_mode.FIELDS[mode], load_mode.OPTIONAL[mode]):
            return
        if mode == load_mode.SNAPSHOT:
            return
        self.name(value["date_column"], "load.date_column")
        if not self.name(value["partition_column"], "load.partition_column"):
            return
        if "allow_empty_days" in value and not isinstance(value["allow_empty_days"], bool):
            self.fail("load.allow_empty_days", "true 또는 false여야 함")
        pc = value["partition_column"]
        for i, t in enumerate(tables if isinstance(tables, list) else []):
            if not isinstance(t, dict) or not isinstance(t.get("columns"), list):
                continue
            types = {col.get("name"): col.get("type") for col in t["columns"] if isinstance(col, dict)}
            if pc not in types:
                self.fail(f"tables[{i}].columns", f"load.partition_column {pc!r} 컬럼이 없음 (모든 테이블의 파티션 컬럼)")
            elif not isinstance(types[pc], str) or types[pc].strip().upper() != "DATE":
                self.fail(f"tables[{i}].columns", f"load.partition_column {pc!r}은 DATE여야 함")

    def checks(self, value):
        """check id → rung 사전을 돌려준다."""
        found = {}
        if not self.obj(value, "checks", tuple(CHECK_RULES)):
            if not isinstance(value, dict):
                return found
        for group, rule in CHECK_RULES.items():
            for i, ch in enumerate(self.items(value.get(group), f"checks.{group}")):
                where = f"checks.{group}[{i}]"
                if not self.obj(ch, where, ("id", "rule", "rung", "written_by")):
                    continue
                if self.text(ch["id"], f"{where}.id"):
                    if not re.fullmatch(rule["prefix"] + r"-\d{2,}", ch["id"]):
                        self.fail(f"{where}.id", f"{ch['id']!r}은 {rule['prefix']}-01 형식이 아님")
                    elif ch["id"] in found:
                        self.fail("checks.id", f"중복 {ch['id']!r}")
                    else:
                        found[ch["id"]] = ch["rung"]
                if self.text(ch["rule"], f"{where}.rule") and any(c in ch["rule"] for c in RULE_BAD_CHARS):
                    # 게이트 SQL의 ASSERT 메시지 문자열로 들어간다(gen_dq.message). 인터뷰 단계에서 미리 막는다
                    self.fail(f"{where}.rule", "작은따옴표, 중괄호, 역슬래시, 줄바꿈은 쓸 수 없음 "
                                               "(예: status = 'Cancelled' 대신 status가 Cancelled)")
                self.one_of(ch["rung"], rule["rungs"], f"{where}.rung")
                self.one_of(ch["written_by"], rule["written_by"], f"{where}.written_by")
        return found

    def traces(self, value, req_ids, checks):
        traced = set()
        for i, t in enumerate(self.items(value, "traces_to")):
            where = f"traces_to[{i}]"
            if not self.obj(t, where, ("req", "check", "rung")):
                continue
            if not isinstance(t["req"], str) or t["req"] not in req_ids:
                self.fail(f"{where}.req", f"requirements에 없는 요구 {t['req']!r}")
            else:
                traced.add(t["req"])
            if not self.one_of(t["rung"], RUNGS, f"{where}.rung"):
                continue
            if not isinstance(t["check"], str) or t["check"] not in checks:
                self.fail(f"{where}.check", f"checks에 없는 검사 {t['check']!r}")
            elif checks[t["check"]] != t["rung"]:
                self.fail(f"{where}.rung", f"검사 {t['check']}의 단계({checks[t['check']]})와 다름")
        for r in sorted(req_ids - traced):
            self.fail("traces_to", f"요구 {r}를 가리키는 검사가 없음")

    def schedule(self, value):
        if not self.obj(value, "schedule", ("refresh", "retention_days")):
            return
        self.text(value["refresh"], "schedule.refresh")
        if value["retention_days"] is not None:
            self.positive_int(value["retention_days"], "schedule.retention_days")

    def modules(self, value):
        if not self.obj(value, "modules", ("expert",)):
            return
        expert = value["expert"]
        if not self.obj(expert, "modules.expert", ("on", "version")):
            return
        on = self.items(expert["on"], "modules.expert.on", allow_empty=True)
        for i, rid in enumerate(on):
            if not isinstance(rid, str) or not re.fullmatch(r"EX-[A-Z]+-\d+", rid):
                self.fail(f"modules.expert.on[{i}]", f"{rid!r}은 EX-DBA-05 형식이 아님")
        if on:
            self.text(expert["version"], "modules.expert.version")
        elif expert["version"] is not None and not isinstance(expert["version"], str):
            self.fail("modules.expert.version", "문자열 또는 null이어야 함")


# ---------- 개인 식별 컬럼 (결정 51 ⑦) ----------

PII_ROW = re.compile(r"^\|\s*`([a-z][a-z0-9_]*)`\s*\|\s*`([a-z][a-z0-9_]*)`\s*\|", re.M)
PII_NONE_ROW = re.compile(r"^\|\s*\(없음\)\s*\|", re.M)  # 개인 식별 컬럼이 없는 원천: 표에 이 행 하나만
REVIEWED_SOURCE = re.compile(r"^검토한 원천:\s*`([^`\s]+)`\s*$", re.M)
# 주석·문자열. 백틱 식별자와 {{ }} 자리 표시는 남긴다
SQL_NOISE = re.compile(r"--[^\n]*|#[^\n]*|/\*.*?\*/|'(?:\\.|[^'\\\n])*'|\"(?:\\.|[^\"\\\n])*\"", re.S)
PLACEHOLDER = re.compile(r"\{\{[^}]*\}\}\s*\.")
TABLE_REF = r"([\w\-]+(?:\.[\w\-]+)*)(?:\s+(?:AS\s+)?([A-Za-z_]\w*))?"
FROM_JOIN = re.compile(r"\b(?:FROM|JOIN)\s+" + TABLE_REF, re.I)
NEXT_REF = re.compile(r"\s*,\s*" + TABLE_REF, re.I)
SELECT_STAR = re.compile(r"\bSELECT\s+(?:DISTINCT\s+|ALL\s+)?\*", re.I)
ALIAS_STAR = re.compile(r"\b(\w+)\s*\.\s*\*")
NOT_ALIAS = {"where", "join", "left", "right", "inner", "outer", "full", "cross", "on", "using", "group",
             "order", "having", "qualify", "window", "limit", "union", "intersect", "except", "select",
             "from", "unnest", "tablesample", "for", "pivot", "unpivot"}


def load_pii(path=PII_FILE):
    """pii_columns.md의 표를 {원천 테이블: {컬럼}}으로 돌려준다.

    "검토한 원천" 줄이 설정의 원천(<프로젝트>.<데이터셋>)과 같아야 한다. 원천을 바꾸고 목록을 그대로 두면
    새 원천 테이블과 맞는 행이 없어 L0가 아무것도 막지 않기 때문이다. 개인 식별 컬럼이 없는 원천은 표에
    `(없음)` 행 하나를 두면 빈 목록({})을 돌려준다. 표가 그냥 비면 오류다. 형식 오류는 ValueError이고,
    사다리는 사람 파일 문제로 halt input_invalid, L0 CLI는 contract_invalid로 둔다(결정 59)."""
    text = Path(path).read_text(encoding="utf-8")
    reviewed = REVIEWED_SOURCE.findall(text)
    if len(reviewed) != 1:
        raise ValueError("'검토한 원천: `<프로젝트>.<데이터셋>`' 줄이 하나 있어야 함 "
                         f"({len(reviewed)}개). 원천의 개인 식별 컬럼을 검토한 뒤 사람이 적는다")
    expected = harness_config.source_prefix()
    if reviewed[0] != expected:
        raise ValueError(f"검토한 원천 {reviewed[0]}이 설정의 원천 {expected}과 다름. "
                         "새 원천의 개인 식별 컬럼을 검토해 표와 '검토한 원천' 줄을 다시 쓴다")
    table = {}
    for src, column in PII_ROW.findall(text):
        table.setdefault(src, set()).add(column)
    none = PII_NONE_ROW.search(text)
    if none and table:
        raise ValueError("목록에 (없음) 행과 컬럼 행이 함께 있음")
    if not table and not none:
        raise ValueError("개인 식별 컬럼 목록이 비어 있음 (없으면 (없음) 행을 명시한다)")
    return table


def strip_sql(sql):
    """주석과 문자열을 지우고, 자리 표시 데이터셋과 백틱을 떼어 소문자로 돌려준다."""
    sql = SQL_NOISE.sub(" ", sql)
    return PLACEHOLDER.sub("", sql).replace("`", "").lower()


def source_of(ref, pii):
    """FROM·JOIN 대상이 목록에 있는 원천(raw_<t> 또는 <원천 데이터셋>.<t>)이면 그 이름을 돌려준다."""
    parts = ref.split(".")
    last = parts[-1]
    if last.startswith("raw_") and last[4:] in pii:
        return last[4:]
    if last in pii and len(parts) >= 2 and parts[-2] == harness_config.source_dataset():
        return last
    return None


def table_refs(sql):
    """(시작 위치, 테이블 이름, 별칭)을 FROM·JOIN과 그 뒤 쉼표 목록에서 모은다."""
    refs = []
    for m in FROM_JOIN.finditer(sql):
        pos, match = m.start(), m
        while match:
            alias = match.group(2)
            if alias in NOT_ALIAS:
                alias = None
            refs.append((pos, match.group(1), alias))
            end = match.end(1) if alias is None else match.end(2)
            match = NEXT_REF.match(sql, end)
    return refs


def depths(sql):
    level, out = 0, []
    for ch in sql:
        if ch == ")":
            level -= 1
        out.append(level)
        if ch == "(":
            level += 1
    return out


def check_sql_file(text, pii):
    """SQL 1개에서 개인 식별 컬럼 참조와 SELECT * 읽기를 찾아 이유 목록을 돌려준다."""
    sql = strip_sql(text)
    refs = [(pos, name, alias, source_of(name, pii)) for pos, name, alias in table_refs(sql)]
    read = {src for _, _, _, src in refs if src}
    if not read:
        return []
    found = []
    for src in sorted(read):
        for column in sorted(pii[src]):
            if re.search(rf"\b{column}\b", sql):
                found.append(f"{src}의 개인 식별 컬럼 {column!r} 참조")
    names = {n for _, name, alias, src in refs if src for n in (alias, name.split(".")[-1]) if n}
    for m in ALIAS_STAR.finditer(sql):
        if m.group(1) in names:
            found.append(f"{m.group(1)}.*로 개인 식별 원천을 읽음")
    level = depths(sql)
    for m in SELECT_STAR.finditer(sql):
        d, end = level[m.start()], len(sql)
        for i in range(m.end(), len(sql)):
            if level[i] < d or (sql[i] == ";" and level[i] == d):
                end = i
                break
        if any(src and m.end() <= pos < end and level[pos] == d for pos, _, _, src in refs):
            found.append("SELECT *로 개인 식별 원천을 읽음 (EXCEPT 포함)")
    return found


def check_sql_dir(sql_dir, pii):
    """<sql_dir>/stg·mart 아래 .sql만 본다. 폴더가 없으면 통과(빈 목록)."""
    errors = []
    root = Path(sql_dir)
    for layer in ("stg", "mart"):
        folder = root / layer
        if not folder.is_dir():
            continue
        for path in sorted(folder.rglob("*.sql")):
            where = f"sql/{layer}/{path.relative_to(folder).as_posix()}"
            # UTF-8이 아닌 builder SQL은 L1이 syntax로 반려한다. 여기서는 깨진 바이트만 바꿔 읽고 PII 검사를 계속한다
            text = path.read_bytes().decode("utf-8", "replace")
            errors += [f"{where}: {e}" for e in check_sql_file(text, pii)]
    return errors


def check_contract(contract, sql_dir=None, pii=None):
    """contract 사전(과 sql_dir이 있으면 stg·mart SQL)을 검사해 L0 rung 결과를 돌려준다."""
    try:
        harness_config.load()
    except harness_config.ConfigError as e:
        return {"rung": "L0", "status": "fail", "metrics": {"stage": "contract", "errors": [f"설정: {e}"]},
                "error_type": "contract_invalid", "error_class": "syntax"}
    if pii is None:
        try:
            pii = load_pii()
        except (OSError, ValueError) as e:
            return {"rung": "L0", "status": "fail",
                    "metrics": {"stage": "contract", "errors": [f"pii_columns.md를 읽지 못함: {e}"]},
                    "error_type": "contract_invalid", "error_class": "syntax"}
    checker = Checker(frozenset().union(*pii.values()))
    checker.check(contract)
    if sql_dir is not None:
        checker.pii_errors += check_sql_dir(sql_dir, pii)
    if checker.pii_errors:
        return {"rung": "L0", "status": "fail",
                "metrics": {"stage": "contract", "errors": checker.pii_errors + checker.errors},
                "error_type": "pii_column", "error_class": "semantic"}
    if checker.errors:
        return {"rung": "L0", "status": "fail",
                "metrics": {"stage": "contract", "errors": checker.errors},
                "error_type": "contract_invalid", "error_class": "syntax"}
    tasks = contract["dag"]["tasks"]
    return {"rung": "L0", "status": "pass",
            "metrics": {"stage": "contract",
                        "load_tasks": sum(t["kind"] == "load" for t in tasks),
                        "gate_tasks": sum(t["kind"] == "gate" for t in tasks),
                        "tables": len(contract["tables"]),
                        "checks": sum(len(v) for v in contract["checks"].values()),
                        "traces": len(contract["traces_to"])},
            "error_type": None, "error_class": None}


def check_file(path, sql_dir=None):
    try:
        contract = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        return {"rung": "L0", "status": "fail",
                "metrics": {"stage": "contract", "errors": [f"contract 파일을 읽지 못함: {e.__class__.__name__}"]},
                "error_type": "contract_invalid", "error_class": "syntax"}
    return check_contract(contract, sql_dir)


def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8")
    argv = sys.argv[1:] if argv is None else list(argv)
    sql_dir = SQL_DIR
    if "--sql-dir" in argv:
        i = argv.index("--sql-dir")
        if i + 1 >= len(argv):
            argv = []
        else:
            sql_dir = argv[i + 1]
            del argv[i:i + 2]
    if len(argv) != 1:
        print("사용법: python scripts/ladder/l0_contract.py <contract.json> [--sql-dir dags/sql]", file=sys.stderr)
        return 2
    result = check_file(argv[0], sql_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
