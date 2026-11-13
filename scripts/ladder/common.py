"""검증 사다리 공용 부품 (03 §5.3, 결정 59).

- 경로: 저장소 구조를 root 기준으로 찾는다. 스모크 시험은 root를 임시 폴더로 바꿔 쓴다
- 렌더링: SQL 파일을 jinja2로 렌더링한다. 자리 표시 dataset_*는 ai_dev, 정의 안 된 자리 표시는 오류 (sql_rules.md §2)
- 검사 SQL 머리말: 파일 맨 위 연속 주석 줄의 `-- 키: 값`만 읽는다. 키는 error_type·task (결정 59)
- 판정 원칙: 원인 파일 작성자 기준 (결정 59). builder 파일(dags/sql/raw|stg|mart/, dags/harness_daily.py)의 문제는
  반려, verifier·사람·하네스 파일(contract, _checks/, pii_columns.md, dags/sql/dq/, dags/harness_config.json)의 문제는 InputInvalid(halt)
- bq: ai-builder 설정(CLOUDSDK_CONFIG, 키 또는 사람 계정의 가장)에서만 실행한다. 모든 쿼리는 dry-run 먼저, dry-run과 본 실행 모두 비용 상한을 건다
- 리전: 쿼리에 --location을 붙이지 않는다. 대신 사다리가 첫 쿼리 전에 ai_dev 리전을 `bq show`로 읽어 설정의
  source.location과 대조한다(run_ladder.check_location)
"""
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / "scripts" / "log"))
sys.path.insert(0, str(PROJECT / "scripts" / "ladder"))
import devlog  # noqa: E402
import harness_config  # noqa: E402

ERROR_TYPES = devlog.ERROR_TYPES
DEV_DATASET = harness_config.DEV_DATASET
MAX_BYTES = 524288000  # 쿼리당 500 MB (결정 46)
STAGES = ("l3", "l4", "l5")
STAGE_RUNG = {"l3": "L3", "l4": "L4", "l5": "L5"}
HEADER_KEYS = ("error_type", "task")
EVIDENCE_ROWS = 5
# 문법·실행 계열은 syntax, 데이터 의미 계열은 semantic. ex. 확장 유형은 semantic (결정 45)
SYNTAX_TYPES = {"contract_invalid", "dag_import_error", "dag_structure_mismatch", "syntax", "cost_exceeded",
                "runtime_error", "type_mismatch"}


class LadderError(Exception):
    """사다리를 시작할 수 없는 사용 오류 (종료 코드 2)."""


class HaltError(Exception):
    """판정하지 않고 멈춘다(verdict halt, 종료 코드 2). 반려로 세지 않는다."""
    default_reason = "infra_error"

    def __init__(self, message, halt_reason=None):
        super().__init__(message)
        self.halt_reason = halt_reason or self.default_reason


class InfraError(HaltError):
    """BigQuery·인증·네트워크 장애 (결정 49·52 ⑤)."""


class InputInvalid(HaltError):
    """builder가 아닌 쪽이 만든 입력 파일의 문제: contract·_checks/(verifier·사람), pii_columns.md(사람),
    dags/sql/dq/(gen_dq). 판정 원칙은 원인 파일 작성자 기준이라 반려가 아니라 halt다 (결정 59)."""
    default_reason = "input_invalid"


def config():
    """설정 사전. 형식이 틀리면 사람 파일 문제라 반려가 아니라 halt다 (결정 59·73)."""
    try:
        return harness_config.load()
    except harness_config.ConfigError as e:
        raise InputInvalid(f"dags/harness_config.json: {e}") from None


def prod_datasets():
    """SQL에 있으면 안 되는 운영 데이터셋 이름의 정규식."""
    config()
    return harness_config.prod_pattern()


class QueryError(Exception):
    """쿼리 자체의 실패. error_type으로 반려된다.
    verdict_text는 판정이 읽는 글자다. 기록용 message를 고쳐도 판정이 달라지지 않게 따로 둔다 (4-26, 사전 등록 v6)."""

    def __init__(self, error_type, message, verdict_text=None):
        super().__init__(message)
        self.error_type = error_type
        self.verdict_text = message if verdict_text is None else verdict_text


def error_class(error_type):
    return "syntax" if error_type in SYNTAX_TYPES else "semantic"


def rung(name, ds, metrics=None, error_type=None):
    """ladder_result의 rung 1개 (03 §6.2)."""
    return {"rung": name, "ds": ds, "status": "fail" if error_type else "pass", "metrics": metrics or {},
            "error_type": error_type, "error_class": error_class(error_type) if error_type else None}


def utc_today():
    """사다리 기본 ds. Airflow 템플릿의 ds는 UTC 날짜이므로 운영 수동 실행의 ds와 같다 (결정 59)."""
    return datetime.now(timezone.utc).date()


# ---------- 경로 ----------

class Paths:
    def __init__(self, root, mart):
        self.root = Path(root)
        self.mart = mart
        self.requirements = self.root / "docs" / "requirements"
        self.contract = self.requirements / f"{mart}.contract.json"
        self.checks = self.requirements / f"{mart}_checks"
        self.sql = self.root / "dags" / "sql"
        self.dag_file = self.root / "dags" / "harness_daily.py"

    def task_sql(self, task):
        folder = "dq" if task["kind"] == "gate" else task["layer"]
        return self.sql / folder / f"{task['id']}.sql"

    def check_files(self, stage):
        folder = self.checks / stage
        return sorted(folder.glob("*.sql")) if folder.is_dir() else []


def load_contract(paths):
    try:
        return json.loads(paths.contract.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise LadderError(f"contract를 읽지 못함 ({paths.contract}): {e.__class__.__name__}") from None


def topo_load_tasks(contract):
    """load task를 의존성 순서로 돌려준다. 게이트는 건너뛰되 게이트를 거친 의존도 따른다."""
    tasks = {t["id"]: t for t in contract["dag"]["tasks"]}
    order, seen = [], set()

    def visit(tid):
        if tid in seen:
            return
        seen.add(tid)
        for up in tasks[tid]["upstream"]:
            if up in tasks:  # 다른 contract의 task(<마트>:<task>)는 이 마트의 실행 대상이 아니다
                visit(up)
        order.append(tid)

    for tid in tasks:
        visit(tid)
    return [tasks[t] for t in order if tasks[t]["kind"] == "load"]


def table_of(contract, task_id):
    for t in contract["tables"]:
        if t["task"] == task_id:
            return t
    raise InputInvalid(f"task {task_id!r}가 만드는 테이블이 contract에 없음")


# ---------- 검사 SQL 머리말 ----------

HEADER_LINE = re.compile(r"--\s*([A-Za-z_]+):\s*(\S.*?)\s*$")


def parse_check(text):
    """(머리말 dict, 본문)을 돌려준다. 형식이 틀리면 ValueError (L0에서 halt input_invalid)."""
    lines = text.lstrip("﻿").splitlines()
    header, i = {}, 0
    while i < len(lines) and lines[i].lstrip().startswith("--"):
        m = HEADER_LINE.fullmatch(lines[i].strip())
        if not m:
            raise ValueError(f"{i + 1}행: 머리말은 `-- 키: 값` 형식이어야 함")
        key, value = m.groups()
        if key not in HEADER_KEYS:
            raise ValueError(f"모르는 머리말 키 {key!r} (허용: {', '.join(HEADER_KEYS)})")
        if key in header:
            raise ValueError(f"머리말 키 {key!r}가 중복됨")
        header[key] = value
        i += 1
    missing = [k for k in HEADER_KEYS if k not in header]
    if missing:
        raise ValueError(f"머리말 키 없음 {missing}")
    if header["error_type"] not in ERROR_TYPES:
        raise ValueError(f"error_type {header['error_type']!r}가 기본 목록(devlog.py ERROR_TYPES)에 없음")
    body = "\n".join(lines[i:]).strip()
    body = re.sub(r";\s*$", "", body).rstrip()
    if not body:
        raise ValueError("쿼리 본문이 비어 있음")
    if ";" in body:
        raise ValueError("검사 쿼리는 SELECT 문 1개여야 함 (세미콜론으로 나뉜 여러 문장)")
    return header, body


def load_checks(paths, stage):
    """[(check id, 머리말, 본문)]. 형식 오류는 ValueError."""
    out = []
    for f in paths.check_files(stage):
        try:
            header, body = parse_check(f.read_text(encoding="utf-8"))
        except ValueError as e:
            raise ValueError(f"{stage}/{f.name}: {e}") from None
        out.append((f.stem, header, body))
    return out


# ---------- 렌더링 ----------

def render(sql, project, ds):
    """운영과 같은 jinja2 문법으로 렌더링한다. 정의 안 된 자리 표시가 있으면 QueryError(syntax)."""
    import jinja2
    env = jinja2.Environment(undefined=jinja2.StrictUndefined, keep_trailing_newline=True)
    context = {"project": project, "dataset_raw": DEV_DATASET, "dataset_stg": DEV_DATASET,
               "dataset_mart": DEV_DATASET, "ds": str(ds), "params": {"force_fail": False}}
    try:
        return env.from_string(sql).render(**context)
    except jinja2.TemplateError as e:
        raise QueryError("syntax", f"자리 표시 렌더링 실패: {e}") from None


# ---------- bq ----------

INFRA = re.compile(r"Could not connect|Connection (?:reset|refused|aborted)|timed out|Temporary failure|"
                   r"Name or service not known|getaddrinfo|backendError|internalError|Service Unavailable|"
                   r"HTTP(?:Error)? 50[023]|[Rr]eauth|credentials|Anonymous caller|no active account|"
                   r"not currently have an active account", re.I)
DENIED = re.compile(r"Access Denied|Permission .*denied|does not have .*permission", re.I)
COST = re.compile(r"bytes billed|maximumBytesBilled|billing tier", re.I)
TYPE = re.compile(r"cannot be inserted|Value has type|cannot be assigned to|Could not cast|Invalid cast|"
                  r"Bad (?:int64|double|bool|numeric) value", re.I)
BYTES_TEXT = re.compile(r"process (\d+) bytes")
NOT_FOUND_TABLE = re.compile(r"Not found: Table\b")
MESSAGE_LIMIT = 500
# 줄 속의 bq 진행 표시. 뒤에 오류가 붙은 줄은 진행 표시만 지운다. 막대는 줄 전체가 막대일 때만 지운다
PROGRESS = re.compile(r"Waiting on \S+ \.\.\.(?: \(\d+s\))?(?: Current status: \w+)?|"
                      r"^\s*\[[=#>.\- ]*\]\s*(?:\d{1,3}%)?\s*$")
ERROR_LINE = re.compile(r"error|fail|not found|denied|invalid|unrecognized|exceeded", re.I)
# 오류 종류 글자는 남기고 값만 가린다. 값은 줄 끝이나 세미콜론까지다
VALUE_ERROR = re.compile(r"(\bBad(?: \w+)? value|\bInvalid\b[^:\n]*\bvalue)\s*:\s*[^;\n]+", re.I)
# 작은·큰따옴표 값. 낱말 속 아포스트로피(can't)와 가린 job 참조는 빼고, 백틱(SQL 식별자)은 값이 아니라 그대로 둔다
QUOTED_VALUE = re.compile(r"""(?<!\w)(['"])(?!\[project\])[^\n]*?\1(?!\w)""")


def mask_reason(text):
    """기록할 오류 글자의 프로젝트 ID·값을 가린다 (4-26). 기존 scrub을 먼저 거치고, scrub이 못 가리는
    `proj:bqjob_…`·`proj:아무_데이터셋`·`Project proj`와 값을 더 가린다. 판정은 가림 전 글자를 읽는다."""
    text = devlog.scrub_strings(text).replace("<프로젝트>:", "[project]:")
    text = devlog.MASK_PROJECT_REF.sub("[project]", text)
    text = devlog.MASK_PROJECT_OPTION.sub(lambda m: f"{m.group(1)}[project]", text)
    text = VALUE_ERROR.sub(lambda m: f"{m.group(1)}: [value]", text)
    return QUOTED_VALUE.sub("[value]", text)


def reason_text(message, limit=MESSAGE_LIMIT):
    """기록할 bq 오류 글자 (4-26). 프로젝트 ID·값을 가리고(자르기 전), 진행 표시를 거르고, 오류 줄을 앞에, 남은 자리에
    나머지의 끝부분을 둔다. 진행 표시만 있으면 앞 limit자 그대로다. 기록용일 뿐 판정은 이 값을 읽지 않는다."""
    text = mask_reason(message.strip())
    raw = text.splitlines()
    lines = [line for line in (PROGRESS.sub("", r).strip() for r in raw) if line]
    if not lines:
        return text[:limit]
    if len(text) <= limit and not any(PROGRESS.search(r) for r in raw):
        return text
    cleaned = "\n".join(lines)
    if len(cleaned) <= limit:
        return cleaned
    head = "\n".join(line for line in lines if ERROR_LINE.search(line))[:limit]
    rest = "\n".join(line for line in lines if not ERROR_LINE.search(line))
    room = limit - len(head) - 1 if head else limit
    tail = rest[-room:] if room > 0 and rest else ""
    return "\n".join(part for part in (head, tail) if part)


def subprocess_runner(args, env, stdin=None, timeout=1800):
    exe = shutil.which(args[0])
    if exe is None:
        raise InfraError(f"{args[0]} 명령을 찾지 못함")
    try:
        p = subprocess.run([exe, *args[1:]], input=None if stdin is None else stdin.encode("utf-8"),
                           capture_output=True, env=env, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise InfraError(f"{args[0]} 실행이 {timeout}초를 넘음") from None
    return p.returncode, p.stdout.decode("utf-8", "replace"), p.stderr.decode("utf-8", "replace")


def apply_kit_local(environ=None):
    """새 창에서도 키트 설정을 쓰게 한다: CLOUDSDK_CONFIG가 없으면 저장소 루트 .kit_local.json의 경로를 넣는다
    (scripts/setup/kit_local.apply_env, 있으면 덮어쓰지 않음). 진입점이 Bq를 만들기 전에 부른다. 인증 확인은 check_auth가 한다."""
    setup = str(PROJECT / "scripts" / "setup")
    if setup not in sys.path:
        sys.path.insert(0, setup)
    import kit_local
    return kit_local.apply_env(PROJECT, environ)


def is_ai_builder(account, impersonated=""):
    """ai-builder 인증 기준 (4-19). 가장 설정이 있으면 실제 신원은 가장 대상이므로 활성 계정이 무엇이든 그 값만 본다.
    사람 계정 + ai-builder 가장, 또는 가장 없는 ai-builder 키 설정만 참이다. 로그인이 없으면 거짓이다."""
    return bool(account) and (impersonated or account).startswith("ai-builder@")


class Bq:
    """bq·gcloud 호출. 시험에서는 runner를 가짜로 바꾼다.

    SQL은 명령줄 인수가 아니라 stdin으로 넘긴다. Windows의 bq·gcloud는 배치 파일(.CMD)이라 cmd.exe가
    인수의 첫 줄바꿈 뒤를 버리기 때문이다(3-3 스모크 1차, 결정 59 ⑨). 줄바꿈이 든 인수는 실행하지 않는다.
    """

    def __init__(self, runner=None, env=None):
        self.runner = runner or subprocess_runner
        self.env = dict(os.environ if env is None else env)
        self.bytes_total = 0
        self.last_accuracy = None
        self.datasets = {}  # bq show 결과 캐시 (리전 확인과 ai_dev 만료 확인이 한 번의 조회를 같이 쓴다)

    def call(self, args, stdin=None):
        args = list(args)
        bad = [a for a in args if "\n" in a or "\r" in a]
        if bad:
            raise InfraError(f"줄바꿈이 든 명령줄 인수는 실행하지 않음 (SQL은 stdin으로 넘긴다): {bad[0][:60]!r}")
        return self.runner(args, self.env, stdin)

    def impersonated(self):
        """gcloud 설정의 가장 대상. 없으면 빈 글자. 읽지 못하면 판단할 수 없으므로 InfraError."""
        code, out, err = self.call(["gcloud", "config", "get-value", "auth/impersonate_service_account"])
        if code != 0:
            raise InfraError("gcloud 설정 auth/impersonate_service_account를 읽지 못함")
        value = out.strip().splitlines()[-1].strip() if out.strip() else ""
        return "" if value == "(unset)" else value

    def check_auth(self):
        """ai-builder 인증인지 확인하고 GCP 프로젝트 ID를 돌려준다 (결정 59, 4-19). 아니면 InfraError."""
        if not self.env.get("CLOUDSDK_CONFIG"):
            raise InfraError("CLOUDSDK_CONFIG가 없음. ai-builder 전용 gcloud 설정에서만 실행한다")
        code, out, err = self.call(["gcloud", "auth", "list", "--filter=status:ACTIVE", "--format=value(account)"])
        account = out.strip().splitlines()[0].strip() if code == 0 and out.strip() else ""
        impersonated = self.impersonated()
        if not is_ai_builder(account, impersonated):
            raise InfraError(f"활성 계정이 ai-builder가 아님 ({impersonated or account or '없음'})")
        code, out, err = self.call(["gcloud", "config", "get-value", "project"])
        project = out.strip().splitlines()[-1].strip() if code == 0 and out.strip() else ""
        if not project or project == "(unset)":
            raise InfraError("ai-builder 설정에 GCP 프로젝트가 없음")
        return project

    def dataset_info(self, project, dataset=DEV_DATASET):
        """데이터셋 정보(`bq show --format=json`의 JSON)를 읽기 전용으로 한 번 조회하고 캐시한다. 실패는 쿼리 판정이
        아니므로 모두 InfraError이고, 권한 거절은 다른 bq 호출과 같이 builder_blocked다."""
        key = f"{project}:{dataset}"
        if key in self.datasets:
            return self.datasets[key]
        code, out, err = self.call(["bq", "show", "--format=json", key])
        if code != 0:
            message = err + out
            if DENIED.search(message):
                raise InfraError(f"권한 막힘: {reason_text(message)}", "builder_blocked")
            raise InfraError(f"{dataset} 조회 실패: {reason_text(message)}")
        try:
            info = json.loads(out.strip().splitlines()[-1])
        except (ValueError, IndexError):
            info = None
        if not isinstance(info, dict):
            raise InfraError(f"{dataset} 조회 결과를 읽지 못함")
        self.datasets[key] = info
        return info

    def dataset_location(self, project, dataset=DEV_DATASET):
        """데이터셋 리전 (dataset_info에서)."""
        try:
            location = self.dataset_info(project, dataset)["location"]
        except KeyError:
            location = None
        if not isinstance(location, str) or not location:
            raise InfraError(f"{dataset} 조회 결과에서 리전을 읽지 못함")
        return location

    @staticmethod
    def raise_for(message, default_type):
        reason, head = reason_text(message), message.strip()[:MESSAGE_LIMIT]
        if DENIED.search(message):
            raise InfraError(f"권한 막힘: {reason}", "builder_blocked")
        if INFRA.search(message):
            raise InfraError(reason)
        if COST.search(message):
            raise QueryError("cost_exceeded", reason, head)
        if default_type != "syntax" and TYPE.search(message):
            raise QueryError("type_mismatch", reason, head)
        raise QueryError(default_type, reason, head)

    def dry_run(self, sql):
        """스캔 바이트를 돌려준다. 상한을 넘으면 cost_exceeded, 그 밖의 오류는 syntax.
        dry-run에도 비용 상한을 함께 건다 (CLAUDE.md §4, 3-3 스모크 2차 후속)."""
        code, out, err = self.call(["bq", "query", "--use_legacy_sql=false", "--dry_run",
                                    f"--maximum_bytes_billed={MAX_BYTES}", "--format=json"], stdin=sql)
        if code != 0:
            self.raise_for(err + out, "syntax")
        n, self.last_accuracy = None, None
        try:
            stats = json.loads(out).get("statistics", {})
            n = int(stats.get("totalBytesProcessed", stats.get("query", {}).get("totalBytesProcessed")))
            # 여러 문장 스크립트의 dry-run 바이트는 하한값이다(LOWER_BOUND) (결정 59 ⑨)
            self.last_accuracy = stats.get("query", {}).get("totalBytesProcessedAccuracy")
        except (ValueError, TypeError, AttributeError):
            m = BYTES_TEXT.search(out)
            n = int(m.group(1)) if m else None
        if n is None:
            raise InfraError("dry-run 결과에서 스캔 바이트를 읽지 못함")
        self.bytes_total += n
        if n > MAX_BYTES:
            raise QueryError("cost_exceeded", f"dry-run {n} bytes > 상한 {MAX_BYTES}. 읽는 컬럼이나 날짜 파티션을 "
                                              "줄여 쿼리당 500 MB 아래로 맞춘다 (결정 46)")
        return n

    def run(self, sql, max_rows=EVIDENCE_ROWS + 1):
        """본 실행. 비용 상한을 걸고 결과 행을 돌려준다. 오류는 runtime_error·type_mismatch·cost_exceeded."""
        code, out, err = self.call(["bq", "query", "--use_legacy_sql=false", f"--maximum_bytes_billed={MAX_BYTES}",
                                    "--format=json", f"--max_rows={max_rows}"], stdin=sql)
        if code != 0:
            self.raise_for(err + out, "runtime_error")
        text = out.strip()
        if not text:
            return []
        for candidate in (text, text.splitlines()[-1]):
            try:
                rows = json.loads(candidate)
                return rows if isinstance(rows, list) else []
            except json.JSONDecodeError:
                continue
        return []


def check_prod(sql):
    """렌더링 결과에 운영 데이터셋 이름이 있으면 실행하지 않는다."""
    m = prod_datasets().search(sql)
    if m:
        raise QueryError("runtime_error", f"렌더링 결과에 운영 데이터셋 이름 {m.group(0)!r}이 있어 실행하지 않음")
