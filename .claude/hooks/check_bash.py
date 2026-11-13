"""PreToolUse Hook: Bash·PowerShell 명령을 실행 전에 검사해 위험한 명령을 막는다 (03 §1.5).

막으면 종료 코드 2로 끝내고, 이유와 대신 할 일은 stderr로 AI에게 돌려준다.
.dev/hook_blocks.jsonl에는 명령 전문이 아니라 요약 1줄과, 값·경로·식별자를 가린 앞 200자(command_masked, 4-21)만
공용 도구(scripts/log/devlog.py)로 남긴다 (03 §6.2).
기록이 실패해도 차단은 그대로 한다.
패턴 차단은 보조 수단이다. 최종 방어선은 ai-builder 서비스 계정 권한이다 (03 §1.2).
판단할 수 없는 쓰기는 막는 쪽으로 한다.

루프 모드 (결정 63 ⑪·⑭, 3-5 설계 6-3절): HARNESS_ROLE은 루프가 builder·verifier 자식 프로세스에만 넣는다.
- HARNESS_ROLE이 있으면 docs/plan/ 경로가 든 명령을 막는다 (결정 52 ③, 실험 조건 보호)
- HARNESS_ROLE이 builder·verifier이면 연장·연속 초기화 결재 기록 명령을 막는다: run_loop.py --extend|--reset-streak,
  devlog.py나 python -c에 loop_extension|loop_streak_reset이 든 명령
- 명령 문자열 기준 차단이고 완전 차단이 아니다. 스크립트 파일로 우회하면 루프의 변경 검사(.dev/*.jsonl은 builder 허용
  경로 밖)와 run_loop.py 자체의 HARNESS_ROLE 검사가 잡는다
"""
import fnmatch
import importlib.util
import json
import os
import re
import sys
from pathlib import Path

AI_DEV = "ai_dev"
MAX_BYTES = 524288000
TOOLS = {"Bash", "PowerShell"}

SUGGEST = {
    "destructive_command": "bq rm·bq update는 사람 결재 대상이다. ai_dev 테이블은 멱등 3문장(DELETE 후 INSERT)으로 다시 쓰고, 삭제·수정이 꼭 필요하면 멈추고 사람에게 요청한다.",
    "git_push": "push·PR은 사람이 한다. 로컬 커밋까지만 하고 사람에게 push를 요청한다.",
    "env_read": ".env는 읽지 않는다. 환경변수 이름만 참조하고, 값이 필요하면 멈추고 사람에게 요청한다.",
    "write_outside_ai_dev": "쓰기 대상을 ai_dev 데이터셋으로 바꾼다. SQL의 {{ dataset_* }} 자리 표시는 ai_dev로 렌더링해서 실행한다.",
    "write_target_unknown": "쓰기 대상을 ai_dev.<테이블>처럼 데이터셋까지 명시하고, SQL을 명령 인자로 직접 넣어 다시 실행한다.",
    "cost_limit_missing": "--dry_run으로 먼저 문법·스캔량을 확인하고, --maximum_bytes_billed=524288000을 걸어 다시 실행한다.",
    "cost_limit_exceeded": "--maximum_bytes_billed를 524288000 이하로 낮춘다. 그래도 모자라면 쿼리 범위를 줄이거나 멈추고 사람에게 상한 조정을 요청한다.",
    "bq_command_unknown": "판단할 수 없는 bq 명령이다. 꼭 필요하면 멈추고 사람에게 요청한다.",
    "parse_error": "명령을 해석하지 못했다. 따옴표를 맞추고 명령을 단순하게 나눠 다시 실행한다.",
    "loop_plan_read": "루프 중에는 docs/plan/을 읽지 않는다(실험 조건 보호, 결정 52 ③·63 ⑪). 요구서·contract·docs/architecture/를 기준으로 작업한다.",
    "loop_approval_by_ai": "반복 연장·연속 초기화는 사람의 결재다(결정 63 ⑫~⑭). 기록하지 말고 progress.md에 멈춘 이유를 쓰고 끝낸다.",
}
AI_ROLES = {"builder", "verifier"}
PLAN_PATH = re.compile(r"docs[/\x5c]+plan(?:[/\x5c]|\b)", re.I)  # \x5c = 역슬래시 (PowerShell 경로)
LOOP_STAGE_WORDS = re.compile(r"loop_extension|loop_streak_reset|rule_promotion")
RUN_LOOP = re.compile(r"run_loop(?:\.py)?\b", re.I)
LOOP_APPROVAL_OPTS = re.compile(r"--(?:extend|reset-streak)\b")
DEVLOG = re.compile(r"devlog(?:\.py)?\b", re.I)
PYTHON_C = re.compile(r"\b(?:python[0-9.]*|py)(?:\.exe)?\b[^;|&\n]*?\s-c\b", re.I)

# ---------- 명령 분해 ----------

SEPARATORS = set(";|&()<>\n")
PREFIXES = {"sudo", "env", "xargs", "time", "nohup", "exec", "command", "call", "start-process"}


def split_segments(command):
    """명령을 따옴표를 지키며 토큰으로 나누고, ; | & ( ) < > 줄바꿈에서 구간을 끊는다."""
    segments, tokens = [], []
    tok, quote = None, None
    i, n = 0, len(command)
    while i < n:
        c = command[i]
        if quote:
            if c == quote:
                quote = None
            elif c == "\\" and quote == '"' and i + 1 < n and command[i + 1] in '"\\$`':
                i += 1
                tok += command[i]
            else:
                tok += c
        elif c in "'\"":
            quote = c
            if tok is None:
                tok = ""
        elif c in SEPARATORS or c.isspace():
            if tok is not None:
                tokens.append(tok)
                tok = None
            if c in SEPARATORS and tokens:
                segments.append(tokens)
                tokens = []
        else:
            tok = (tok or "") + c
        i += 1
    if quote:
        raise ValueError("unbalanced quote")
    if tok is not None:
        tokens.append(tok)
    if tokens:
        segments.append(tokens)
    return segments


def prog(token):
    """실행 파일 이름만 남긴다. C:\\x\\bq.cmd → bq"""
    base = re.split(r"[\\/]", token.lstrip("`$"))[-1].lower()
    return re.sub(r"\.(exe|cmd|bat|ps1)$", "", base)


def command_start(seg):
    """sudo·env·X=1 같은 앞말을 건너뛴 실제 명령의 위치."""
    for i, t in enumerate(seg):
        if prog(t) in PREFIXES or t.startswith("-") or ("=" in t and not t.startswith("-")):
            continue
        return i
    return None


# 검색 명령의 패턴 인자는 파일 이름이 아니다 (B-0016: grep ".*"가 fnmatch(".env", ".*")로 막힘).
# 패턴 자리만 빼고, 그 뒤의 파일 인자는 그대로 검사한다. 판단이 애매하면 파일로 본다(막는 쪽).
GREP_PROGS = {"grep", "egrep", "fgrep", "rg"}
GREP_PATTERN_LONG = {"--regexp"}
GREP_FILE_LONG = {"--file"}  # 패턴을 파일에서 읽는다 → 값은 파일, 위치 인자 패턴은 없다
GREP_VALUE_SHORT = set("ABCmdDgtTMj")  # 값을 받는 짧은 옵션 (값은 패턴도 파일도 아님)
GREP_VALUE_LONG = {"--after-context", "--before-context", "--context", "--max-count", "--glob", "--iglob",
                   "--type", "--type-not", "--max-depth", "--threads", "--encoding", "--sort", "--sortr",
                   "--max-columns", "--include", "--exclude", "--exclude-dir", "--color", "--colors", "--binary-files",
                   "--devices", "--directories", "--label", "--context-separator", "--field-match-separator"}
SLS_PROGS = {"select-string", "sls"}


def grep_pattern_positions(rest):
    """grep·rg 인자(명령 이름 뒤)에서 패턴 자리의 위치 집합."""
    pats, has_explicit, i, n = set(), False, 0, len(rest)
    while i < n:
        t = rest[i]
        if t == "--":
            i += 1
            break
        if t.startswith("--"):
            name, eq, _ = t.partition("=")
            if name in GREP_PATTERN_LONG:
                has_explicit = True
                if not eq and i + 1 < n:
                    pats.add(i + 1)
                    i += 1
                elif eq:
                    pats.add(i)
            elif name in GREP_FILE_LONG:
                has_explicit = True
                i += 0 if eq else 1  # 값(패턴 파일)은 파일로 검사한다
            elif name in GREP_VALUE_LONG and not eq:
                i += 1
            i += 1
            continue
        if t.startswith("-") and len(t) > 1:
            letters = t[1:]
            for k, ch in enumerate(letters):
                attached = letters[k + 1:]
                if ch == "e":
                    has_explicit = True
                    if attached:
                        pats.add(i)
                    elif i + 1 < n:
                        pats.add(i + 1)
                        i += 1
                    break
                if ch == "f":
                    has_explicit = True
                    if not attached:
                        i += 1
                    break
                if ch in GREP_VALUE_SHORT:
                    if not attached:
                        i += 1
                    break
            i += 1
            continue
        break  # 첫 위치 인자
    if not has_explicit and i < n:
        pats.add(i)
    return pats


def findstr_pattern_positions(rest):
    """findstr: /c:문자열·/g:파일 옵션, 그 밖에는 /옵션이 아닌 첫 인자가 패턴."""
    pats, has_explicit = set(), False
    for i, t in enumerate(rest):
        tl = t.lower()
        if tl.startswith("/c:"):
            pats.add(i)
            has_explicit = True
        elif tl.startswith("/g:"):
            has_explicit = True  # 패턴 파일 → 파일로 검사한다
        elif t.startswith("/"):
            continue
        else:
            if not has_explicit:
                pats.add(i)
            return pats
    return pats


def sls_pattern_positions(rest):
    """Select-String: -Pattern 값, 없으면 이름 없는 첫 인자가 패턴(두 번째가 Path)."""
    pats, named, i = set(), False, 0
    positional = []
    while i < len(rest):
        tl = rest[i].lower()
        if tl.startswith("-") and len(tl) > 1:
            if len(tl) >= 5 and "-pattern".startswith(tl):  # -patt 이상 (-pa·-pat는 -Path와 겹친다)
                named = True
                if i + 1 < len(rest):
                    pats.add(i + 1)
                i += 2
                continue
            if tl in ("-path", "-literalpath", "-encoding", "-context", "-include", "-exclude", "-culture"):
                i += 2  # 값은 패턴이 아니다 (Path·Include 값은 그대로 파일로 검사된다)
                continue
            i += 1
            continue
        positional.append(i)
        i += 1
    if not named and positional:
        pats.add(positional[0])
    return pats


def pattern_positions(seg, start):
    """구간(seg)에서 검색 패턴 인자의 위치 집합(seg 기준). 검색 명령이 아니면 빈 집합."""
    if start is None:
        return set()
    p, rest = prog(seg[start]), seg[start + 1:]
    if p in GREP_PROGS:
        local = grep_pattern_positions(rest)
    elif p == "findstr":
        local = findstr_pattern_positions(rest)
    elif p in SLS_PROGS:
        local = sls_pattern_positions(rest)
    else:
        return set()
    return {start + 1 + k for k in local}


def is_env_file(token, in_text=False):
    """in_text: 셸이 읽지 않는 heredoc 본문의 토큰. 정규식 ".*?"는 셸 글로브가 아니므로(B-0018)
    .e로 시작하거나 env가 든 패턴만 본다."""
    base = re.split(r"[\\/]", token)[-1]
    if base.lower() == ".env.example":
        return False
    if re.fullmatch(r"\.env(\..+)?", base, re.I):
        return True
    if any(ch in base for ch in "*?[") and base not in ("*", "*.*", "**"):
        if in_text and not (base.startswith(".e") or "env" in base.lower()):
            return False
        return fnmatch.fnmatch(".env", base) or fnmatch.fnmatch(".env.local", base)
    return False


# heredoc 본문은 셸이 토큰으로 나누지 않는다. python - <<E 같은 본문의 정규식·문장을 파일 이름으로 보지 않게 따로 다룬다 (B-0018).
# 본문을 읽는 쪽이 셸이면 그대로 명령이다. 끝 표시를 못 찾으면 본문으로 보지 않는다(지금처럼 막는 쪽).
HEREDOC = re.compile(r"<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")
SHELL_PROGS = {"bash", "sh", "zsh", "dash", "ksh", "powershell", "pwsh", "cmd"}


def split_heredocs(command):
    """(본문을 뺀 명령, [(본문, 셸이 읽는가)])."""
    lines = command.split("\n")
    main, bodies, i = [], [], 0
    while i < len(lines):
        line = lines[i]
        main.append(line)
        i += 1
        for m in HEREDOC.finditer(line):
            tag, strip_tabs = m.group(2), m.group(0).startswith("<<-")
            end = next((j for j in range(i, len(lines))
                        if (lines[j].lstrip("\t") if strip_tabs else lines[j]).rstrip("\r") == tag), None)
            if end is None:
                continue
            shell = any(prog(t) in SHELL_PROGS for t in re.split(r"[\s;|&()]+", line) if t)
            bodies.append(("\n".join(lines[i:end]), shell))
            i = end + 1
    return "\n".join(main), bodies


def looks_like_command(text):
    """따옴표 문자열이 명령처럼 시작하는가. ".env 접근"이나 한글 문장은 아니고 "cat .env"는 맞다."""
    first = text.split()[0] if text.split() else ""
    return bool(re.fullmatch(r"[A-Za-z0-9_./\\:-]+", first)) and not is_env_file(first)


# ---------- git ----------

GIT_VALUE_OPTS = {"-C", "-c", "--git-dir", "--work-tree", "--namespace"}


def git_subcommand(args):
    i = 0
    while i < len(args):
        a = args[i]
        if a in GIT_VALUE_OPTS:
            i += 2
            continue
        if a.startswith("-"):
            i += 1
            continue
        return a.lower()
    return None


# ---------- 데이터셋 판정 ----------

def dataset_of(ref, kind="table", default=None):
    """테이블·스키마 참조에서 데이터셋 이름을 꺼낸다. 알 수 없으면 None."""
    if ref is None or "{{" in ref:
        return None
    ref = ref.split(":", 1)[-1]          # bq CLI의 project:dataset.table
    ref = re.split(r"[$@]", ref)[0]      # 파티션·스냅샷 데코레이터
    parts = [p.strip("`") for p in ref.strip("`").split(".")]
    parts = [p for p in parts if p]
    if not parts:
        return None
    if kind == "schema":
        return parts[-1]
    if len(parts) >= 2:
        return parts[-2]
    return default


# ---------- SQL ----------

PART = r"(?:`[^`]*`|\{\{[^}]*\}\}|[\w-]+)"
REF = r"(?P<ref>" + PART + r"(?:\." + PART + r")*)"
OBJ = (r"(?P<obj>TABLE\s+FUNCTION|EXTERNAL\s+TABLE|SNAPSHOT\s+TABLE|MATERIALIZED\s+VIEW"
       r"|AGGREGATE\s+FUNCTION|TABLE|VIEW|SCHEMA|FUNCTION|PROCEDURE|MODEL)")
STATEMENTS = {
    "INSERT": r"INSERT\s+(?:INTO\s+)?" + REF,
    "MERGE": r"MERGE\s+(?:INTO\s+)?" + REF,
    "UPDATE": r"UPDATE\s+" + REF,
    "DELETE": r"DELETE\s+(?:FROM\s+)?" + REF,
    "TRUNCATE": r"TRUNCATE\s+TABLE\s+" + REF,
    "CREATE": (r"CREATE\s+(?:OR\s+REPLACE\s+)?(?P<temp>TEMP(?:ORARY)?\s+)?" + OBJ
               + r"\s+(?:IF\s+NOT\s+EXISTS\s+)?" + REF),
    "DROP": r"DROP\s+" + OBJ + r"\s+(?:IF\s+EXISTS\s+)?" + REF,
    "ALTER": r"ALTER\s+" + OBJ + r"\s+(?:IF\s+EXISTS\s+)?" + REF,
    "LOAD DATA": r"LOAD\s+DATA\s+(?:OVERWRITE|INTO)\s+(?P<temp>TEMP(?:ORARY)?\s+TABLE\s+)?" + REF,
}
KEYWORDS = re.compile(
    r"\b(INSERT|MERGE|UPDATE|DELETE|TRUNCATE|CREATE|DROP|ALTER|LOAD\s+DATA"
    r"|EXPORT\s+DATA|CALL|EXECUTE\s+IMMEDIATE|GRANT|REVOKE)\b", re.I)
NOT_A_REF = {"SET", "ROW", "VALUES", "WHEN", "WHERE", "THEN", "SELECT", "AS"}


def normalize_sql(sql):
    """주석을 지우고 문자열 리터럴을 ''로 바꾼다. 백틱 식별자는 그대로 둔다."""
    out, i, n = [], 0, len(sql)
    while i < n:
        c, two = sql[i], sql[i:i + 2]
        if two == "--" or c == "#":
            j = sql.find("\n", i)
            i = n if j < 0 else j
            continue
        if two == "/*":
            j = sql.find("*/", i + 2)
            i = n if j < 0 else j + 2
            out.append(" ")
            continue
        if c in "'\"":
            q = sql[i:i + 3] if sql[i:i + 3] in ("'''", '"""') else c
            j = i + len(q)
            while j < n and sql[j:j + len(q)] != q:
                j += 2 if sql[j] == "\\" else 1
            i = j + len(q)
            out.append("''")
            continue
        if c == "`":
            j = sql.find("`", i + 1)
            j = n - 1 if j < 0 else j
            out.append(sql[i:j + 1])
            i = j + 1
            continue
        out.append(c)
        i += 1
    return "".join(out)


def sql_write_targets(sql, default_ds=None):
    """SQL의 쓰기 문장마다 (문장, 데이터셋 또는 None) 을 돌려준다."""
    sql = normalize_sql(sql)
    # MERGE 안의 THEN INSERT/UPDATE/DELETE는 별도 문장이 아니다
    sql = re.sub(r"\bTHEN(\s+)(INSERT|UPDATE|DELETE)\b",
                 lambda m: "THEN" + m.group(1) + "x" * len(m.group(2)), sql, flags=re.I)
    masked = re.sub(r"`[^`]*`", lambda m: "x" * len(m.group(0)), sql)
    temp_names, targets = set(), []
    for kw in KEYWORDS.finditer(masked):
        name = re.sub(r"\s+", " ", kw.group(1).upper())
        pattern = STATEMENTS.get(name)
        m = re.match(pattern, sql[kw.start():], re.I) if pattern else None
        if not m or m.group("ref").upper() in NOT_A_REF:
            targets.append((name, None))
            continue
        ref, groups = m.group("ref"), m.groupdict()
        if groups.get("temp"):
            temp_names.add(ref.strip("`").lower())
            continue
        kind = "schema" if (groups.get("obj") or "").upper() == "SCHEMA" else "table"
        if kind == "table" and "." not in ref.strip("`") and ref.strip("`").lower() in temp_names:
            continue
        targets.append((name, dataset_of(ref, kind, default_ds)))
    return targets


# ---------- bq ----------

BQ_READ = {"show", "ls", "head", "help", "version", "wait", "get-iam-policy", "mkdef", "info"}
BQ_DESTRUCTIVE = {"rm", "update"}
BQ_WRITE_DEST = {"load": 0, "insert": 0, "mk": 0, "undelete": 0, "truncate": 0, "cp": -1, "partition": -1}
BQ_OTHER = {"query", "extract", "cancel", "set-iam-policy", "add-iam-policy-binding",
            "remove-iam-policy-binding", "init", "shell"}
BQ_SUBCOMMANDS = BQ_READ | BQ_DESTRUCTIVE | set(BQ_WRITE_DEST) | BQ_OTHER
BQ_VALUE_FLAGS = {"destination_table", "maximum_bytes_billed", "parameter", "location", "project_id",
                  "dataset_id", "format", "max_rows", "n", "job_id", "label", "source_format",
                  "schema", "time_partitioning_field", "time_partitioning_type", "clustering_fields",
                  "description", "expiration", "default_table_expiration", "session_id",
                  "destination_kms_key", "external_table_definition", "udf_resource", "apilog",
                  "job_timeout", "reservation_id", "connection_property"}
BQ_BOOL_FLAGS = {"dry_run", "use_legacy_sql", "replace", "append_table", "nouse_cache", "batch"}
BQ_MK_OTHER = {"transfer_config", "reservation", "capacity_commitment", "reservation_assignment", "connection"}


def parse_bq_args(args):
    flags, pos = {}, []
    i = 0
    while i < len(args):
        a = args[i]
        if a.startswith("-") and len(a) > 1:
            name, eq, val = a.lstrip("-").partition("=")
            if eq:
                flags[name] = val
            elif name in BQ_VALUE_FLAGS and i + 1 < len(args):
                flags[name] = args[i + 1]
                i += 1
            elif name.startswith("no") and name[2:] in BQ_BOOL_FLAGS:
                flags[name[2:]] = "false"
            else:
                flags[name] = "true"
        else:
            pos.append(a)
        i += 1
    return flags, pos


def truthy(value):
    return str(value).lower() in ("true", "1", "yes")


def check_bq(args, add):
    sub_i = next((i for i, a in enumerate(args) if a.lower() in BQ_SUBCOMMANDS), None)
    if sub_i is None:
        flags, pos = parse_bq_args(args)
        if pos:
            add("bq_command_unknown", "bq with unknown subcommand")
        return
    sub = args[sub_i].lower()
    flags, _ = parse_bq_args(args[:sub_i])
    after_flags, pos = parse_bq_args(args[sub_i + 1:])
    flags.update(after_flags)

    if sub in BQ_READ:
        return
    if sub in BQ_DESTRUCTIVE:
        add("destructive_command", f"bq {sub}")
        return
    if sub in BQ_WRITE_DEST:
        if sub == "mk" and BQ_MK_OTHER & set(flags):
            add("bq_command_unknown", "bq mk (non-table resource)")
            return
        kind = "schema" if sub == "mk" and (truthy(flags.get("d")) or truthy(flags.get("dataset"))) else "table"
        ref = pos[BQ_WRITE_DEST[sub]] if pos else None
        report_target(f"bq {sub}", dataset_of(ref, kind), add)
        return
    if sub != "query":
        add("bq_command_unknown", f"bq {sub}")
        return

    dry_run = truthy(flags.get("dry_run", "false"))
    if not dry_run:
        limit = flags.get("maximum_bytes_billed")
        if limit is None:
            add("cost_limit_missing", "bq query without --maximum_bytes_billed")
        else:
            try:
                if int(limit) > MAX_BYTES:
                    add("cost_limit_exceeded", "bq query with --maximum_bytes_billed over 524288000")
            except ValueError:
                add("cost_limit_exceeded", "bq query with non-numeric --maximum_bytes_billed")

    default_ds = dataset_of(flags["dataset_id"], "schema") if flags.get("dataset_id") else None
    if "destination_table" in flags:
        report_target("bq query --destination_table",
                      dataset_of(flags["destination_table"], "table", default_ds), add)
    sql = " ".join(pos)
    if not sql.strip():
        if not dry_run:
            add("write_target_unknown", "bq query with SQL not visible (stdin or file)")
        return
    for stmt, ds in sql_write_targets(sql, default_ds):
        report_target(f"bq query {stmt}", ds, add)


def report_target(what, ds, add):
    if ds is None:
        add("write_target_unknown", f"{what} with unknown target dataset")
    elif ds != AI_DEV:
        add("write_outside_ai_dev", f"{what} to dataset {ds}")


# ---------- 셸이 읽지 않는 본문의 느슨한 검사 ----------

# python 코드의 따옴표는 셸 기준으로 짝이 안 맞을 수 있다. 그 본문은 따옴표를 무시하고 나눠 같은 규칙으로 본다 (B-0019).
RISKY_MENTION = re.compile(r"\.env|\bbq\b|\bgit\b[\s\S]*\bpush\b", re.I)
GIT_PUSH_MENTION = re.compile(r"\bgit\b[\s\S]*\bpush\b", re.I)
LOOSE_LINE = re.compile(r"[\n;|&<>]")
LOOSE_TOKEN = re.compile(r"[\s'\"`(){}\[\],]+")
ENV_MENTION = re.compile(r"\.env(?![A-Za-z0-9_]|\.example\b)", re.I)  # os.environ·.env.example은 아니다


def bq_in_prose(rest):
    """셸이 읽지 않는 본문에서 bq 뒤 첫 토큰이 한글 등 ASCII가 아닌 글자로 시작하면 명령이 아니라 문장이다
    ("bq 명령 5", B-0020~B-0022). bq 하위 명령·옵션은 ASCII라 이 예외에 걸리지 않는다."""
    return bool(rest) and not rest[0][:1].isascii()


def check_text_loosely(text, add):
    """본문을 줄 단위 토큰으로 나눠 env_read·git_push·check_bq를 본다. 판단할 수 없는 언급이 남으면 parse_error.

    판단할 수 없는 언급: 이어지는 인자가 없는 bq·git("bq",만 있는 줄), 토큰에 붙은 bq·git·.env(bq.query, .env:).
    """
    undecided = git_open = False
    for line in LOOSE_LINE.split(re.sub(r"\\\r?\n", " ", text)):  # 줄 끝 역슬래시는 한 줄로 잇는다
        tokens = [t for t in LOOSE_TOKEN.split(line) if t]
        for k, t in enumerate(tokens):
            p, rest = prog(t), tokens[k + 1:]
            if is_env_file(t, in_text=True):
                add("env_read", "access to .env file")
            elif ENV_MENTION.search(t):
                undecided = True
            if p == "git":
                sub = git_subcommand(rest)
                if sub == "push":
                    add("git_push", "git push")
                elif sub is None:
                    git_open = True
            elif re.search(r"\bgit\b", t, re.I):
                git_open = True
            if p == "bq":
                if bq_in_prose(rest):
                    continue
                if parse_bq_args(rest)[1]:
                    check_bq(rest, add)
                else:
                    undecided = True
            elif re.search(r"\bbq\b", t, re.I):
                undecided = True
    if undecided or (git_open and GIT_PUSH_MENTION.search(text)):
        add("parse_error", "unparseable heredoc text mentioning bq, git push or .env")


# ---------- 판정 ----------

def evaluate(tool, command, depth=0, in_text=False):
    """막을 이유 목록을 돌려준다. 빈 목록이면 허용. in_text는 셸이 읽지 않는 heredoc 본문이다."""
    blocks = []
    bodies = []
    if tool == "Bash" and not in_text:
        command, bodies = split_heredocs(command)

    def add(reason, summary):
        item = {"reason": reason, "summary": summary}
        if item not in blocks:
            blocks.append(item)

    try:
        segments = split_segments(command)
    except ValueError:
        segments = []
        if RISKY_MENTION.search(command):
            if in_text:
                check_text_loosely(command, add)
            else:
                add("parse_error", "unparseable command mentioning bq, git push or .env")

    for seg in segments:
        start = command_start(seg)
        patterns = pattern_positions(seg, start)  # grep·rg·findstr·Select-String의 패턴 인자는 파일이 아님
        if any(is_env_file(t, in_text) for k, t in enumerate(seg) if k not in patterns):
            add("env_read", "access to .env file")
        if start is not None:
            p, rest = prog(seg[start]), seg[start + 1:]
            if p == "git" and git_subcommand(rest) == "push":
                add("git_push", "git push")
            elif p == "bq" and not (in_text and bq_in_prose(rest)):
                check_bq(rest, add)
        # bash -c "...", powershell -Command "..." 처럼 따옴표 안에 든 명령도 검사한다
        if depth < 3:
            for k, t in enumerate(seg):
                if k not in patterns and re.search(r"\s", t):
                    for b in evaluate(tool, t, depth + 1, in_text):
                        if not (in_text and b["reason"] == "env_read" and not looks_like_command(t)):
                            add(b["reason"], b["summary"])
    for text, shell in bodies:
        for b in evaluate(tool, text, depth, in_text=not shell):
            add(b["reason"], b["summary"])
    return blocks


def loop_blocks(command, role):
    """루프 모드 차단. role은 HARNESS_ROLE 값(없으면 빈 문자열)."""
    blocks = []
    if not role:
        return blocks
    if PLAN_PATH.search(command):
        blocks.append({"reason": "loop_plan_read", "summary": "docs/plan/ path while HARNESS_ROLE is set"})
    if role in AI_ROLES:
        if RUN_LOOP.search(command) and LOOP_APPROVAL_OPTS.search(command):
            blocks.append({"reason": "loop_approval_by_ai", "summary": f"run_loop.py --extend/--reset-streak as {role}"})
        elif LOOP_STAGE_WORDS.search(command) and (DEVLOG.search(command) or PYTHON_C.search(command)):
            blocks.append({"reason": "loop_approval_by_ai", "summary": f"human approval record as {role}"})
    return blocks


# ---------- 기록과 실행 ----------

def project_dir():
    return Path(os.environ.get("CLAUDE_PROJECT_DIR") or Path(__file__).resolve().parents[2])


def load_devlog():
    """공용 로그 도구를 ${CLAUDE_PROJECT_DIR} 기준으로 찾고, 없으면 이 Hook이 있는 저장소에서 찾는다."""
    candidates = [project_dir(), Path(__file__).resolve().parents[2]]
    for root in candidates:
        path = root / "scripts" / "log" / "devlog.py"
        if path.exists():
            spec = importlib.util.spec_from_file_location("devlog", path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module
    raise FileNotFoundError("scripts/log/devlog.py")


def masked_field(devlog, text):
    """command_masked 칸. 가리기 함수는 devlog 한 곳에 있다. 그 함수가 없는 devlog면 칸만 빼고 기록은 남긴다."""
    mask = getattr(devlog, "mask_command", None)
    return {"command_masked": mask(text)} if mask else {}


def log_block(tool, blocks, command):
    """차단 1건을 .dev/hook_blocks.jsonl에 공용 도구(devlog)로 기록한다. id·ts는 도구가 채운다."""
    first = blocks[0]
    devlog = load_devlog()
    devlog.append("hook_blocks", {
        "hook": "check_bash",
        "command_summary": f"[{tool}] " + "; ".join(b["summary"] for b in blocks),
        "reason": first["reason"],
        "suggested": SUGGEST[first["reason"]],
        **masked_field(devlog, command),
    }, project_dir() / ".dev")


def main():
    sys.stderr.reconfigure(encoding="utf-8")
    raw = sys.stdin.buffer.read().decode("utf-8", "replace")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        print("차단: Hook 입력 JSON을 읽지 못했다.\n대신 할 일: " + SUGGEST["parse_error"], file=sys.stderr)
        return 2
    tool = data.get("tool_name")
    if tool not in TOOLS:
        return 0
    command = (data.get("tool_input") or {}).get("command") or ""
    blocks = evaluate(tool, command)
    blocks += [b for b in loop_blocks(command, os.environ.get("HARNESS_ROLE", "")) if b not in blocks]
    if not blocks:
        return 0
    lines = ["차단: check_bash Hook이 이 명령을 막았다."]
    for b in blocks:
        lines.append(f"- 이유: {b['reason']} ({b['summary']})")
        lines.append(f"  대신 할 일: {SUGGEST[b['reason']]}")
    # 기록이 실패해도 차단은 그대로 한다
    try:
        log_block(tool, blocks, command)
    except Exception as e:
        lines.append(f"(hook_blocks.jsonl 기록 실패: {e.__class__.__name__}: {e})")
    print("\n".join(lines), file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
