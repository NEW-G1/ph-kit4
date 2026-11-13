"""`.dev/` 로그 기록 도구. 루프·사람이 모두 이 도구로 남긴다 (03 §6.2).

- rejections·interventions·cost·hook_blocks: .dev/<이름>.jsonl, 1건 = 1줄, 추가만 한다
- ladder_result: .dev/ladder_results/<마트>/<task>-v<contract_version>-<iteration>.json, 1회 = 1파일, 덮어쓰지 않는다 (결정 52 ②)
- id는 파일마다 이어서 매기고, ts는 +09:00으로 채운다. cost는 예외로 run_id를 호출하는 쪽이 넘긴다
- 형식 오류나 비밀값으로 보이는 값이 있으면 기록하지 않고 DevlogError를 낸다
- 새로 쓰는 줄·파일의 문자열 칸은 make_facts.scrub()으로 프로젝트 ID·메일을 가린다. 과거 줄은 고치지 않는다 (결정 71)

03 §6.2와 다르게 정한 것 (2-8 결재):
- rejections의 fixed_in_iteration·rule_promoted는 기록 때 항상 null. 값은 집계에서 계산한다
- rejections의 evidence는 필수 칸. 같은 task·error_type의 2번째 반려부터 null이면 거부
- interventions의 mart는 module_toggle일 때만 null 허용
- iteration은 1 이상 정수 또는 "post"(L6만)
- L6(iteration "post") 파일 이름은 <task>-v<버전>-post-<n>.json. n은 같은 task·버전의 가장 큰 n + 1이고,
  재확인은 새 순번 파일로 추가하며 이전 파일은 지우지 않는다. 최신 L6 = 가장 큰 n (latest_post, 결정 67)
- cost에는 ts가 없다. started·ended는 호출하는 쪽이 +09:00으로 넘긴다
- cost는 claude -p 호출 1회 = 1줄. 같은 루프의 호출은 같은 run_id를 쓴다 (결정 57)
- rejections에 contract_version, cost에 캐시 토큰·total_cost_usd, approval에 stage를 둔다 (2-19 F1·F2·F3)
- hook_blocks에 선택 칸 command_masked를 둔다. 값은 mask_command()로 가린다. 과거 줄은 고치지 않는다 (4-21)
- approval의 loop_extension(반복 상한 연장)·loop_streak_reset(같은 유형 연속 초기화)은 run_loop.py 옵션으로만
  기록한다. CLI는 거부하고, 라이브러리 호출도 loop_record=True일 때만 받는다 (결정 63 ⑫~⑭, 08 V4-1)

사람이 개입을 남길 때:
  python scripts/log/devlog.py intervention --kind approval --stage approval_2 --mart mart_returns --target "PR #12" --minutes 6 --note "..."
"""
import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

KST = timezone(timedelta(hours=9))
PROJECT = Path(__file__).resolve().parents[2]

RUNGS = {"L0", "L1", "L2", "L3", "L4", "L5", "L6"}
ERROR_TYPES = {
    "contract_invalid", "dag_import_error", "dag_structure_mismatch", "syntax", "cost_exceeded",
    "runtime_error", "type_mismatch", "null_violation", "range_violation", "duplicate_rows",
    "join_missing", "idempotency_break", "description_missing", "lineage_missing", "pii_column",
    "hardcoded_dataset",  # SQL 원문에 운영 데이터셋 이름을 직접 씀 (L1 정적 검사)
    "table_missing",  # L6: contract 테이블이 OM에 없음 (결정 67)
}
ERROR_CLASSES = {"syntax", "semantic"}
KINDS = {"approval", "correction", "manual_check", "requirement_change", "ops_run",
         "post_approval_defect", "module_toggle"}
KIND_FIELDS = {
    "approval": ("stage",),
    "requirement_change": ("cause",),
    "post_approval_defect": ("found_stage", "detail", "missed_by_rung"),
    "module_toggle": ("scope", "now"),
}
CAUSES = {"user", "ladder_fail", "expert_advice", "defect"}  # defect: 결재 2 뒤 구조 결함 수정 (결정 64 ⑥)
# approval_1 요구서·contract 승인, approval_2 PR 결재·머지, ops push·PR 생성 등 운영 절차,
# loop_extension 반복 상한 연장, loop_streak_reset 같은 유형 연속 수 초기화 (결정 63 ⑫·⑬),
# rule_promotion 규칙 승격 결재: 승격 PR 머지 뒤 사람이 기록한다 (08 V6-1)
LOOP_STAGES = {"loop_extension", "loop_streak_reset"}
RULE_STAGE = "rule_promotion"
STAGES = {"approval_1", "approval_2", "ops", RULE_STAGE} | LOOP_STAGES
# 루프 결재의 stage별 칸. approver는 역할 코드만 쓰고 이름은 넣지 않는다 (대응표는 repo 밖)
STAGE_FIELDS = {
    "loop_extension": ("contract_version", "extra_iterations", "approver", "reason"),
    "loop_streak_reset": ("contract_version", "streak_key", "approver", "reason"),
    RULE_STAGE: ("rule_id",),
}
RULE_ID = re.compile(r"RC-\d{3,}")
APPROVER = re.compile(r"approver[1-9]\d*")
VERDICTS = {"pass", "reject", "halt"}
HALT_REASONS = {"max_iterations", "same_type_3x", "contract_change", "timeout", "infra_error", "builder_blocked",
                "input_invalid"}
RUNG_STATUSES = {"pass", "fail"}
# 요청 종류. 본 측정은 new_build만 세고 나머지는 .dev/maintenance/에 따로 남긴다 (결정 58)
REQUEST_KINDS = {"new_build", "change", "backfill_check"}

# 파일별 id 형식 (03 §6.2 예시)
LOGS = {
    "rejections": {"id_key": "id", "prefix": "R-", "width": 4},
    "interventions": {"id_key": "id", "prefix": "H-", "width": 4},
    # cost는 claude -p 호출 1회 = 1줄이고 run_id는 루프가 넘긴다. 도구가 매기는 id는 없다 (결정 57)
    "cost": {"id_key": None},
    "hook_blocks": {"id_key": "id", "prefix": "B-", "width": 4},
}

SECRET_PATTERNS = [
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"\beyJ[\w-]{8,}\.[\w-]{8,}\.[\w-]{8,}"),            # JWT
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),                              # AWS 키
    re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"),                         # Google API 키
    re.compile(r"\bya29\.[\w-]{20,}"),                                # Google OAuth 토큰
    re.compile(r"\b(?:sk|pk|rk)-[A-Za-z0-9_-]{16,}"),
    re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr|github_pat)_[A-Za-z0-9_]{20,}"),
    re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}"),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{16,}", re.I),
    re.compile(r"(?:password|passwd|pwd|secret|token|api[_-]?key|access[_-]?key|private[_-]?key|client[_-]?secret)"
               r"\s*[:=]\s*['\"]?[^\s'\",}]{6,}", re.I),
]


class DevlogError(ValueError):
    pass


# ---------- 공통 검사 ----------

def now_ts():
    return datetime.now(KST).isoformat(timespec="seconds")


def require(record, fields, where):
    missing = [f for f in fields if f not in record]
    if missing:
        raise DevlogError(f"{where}: 필수 칸 없음 {missing}")


def no_extra(record, allowed, where):
    extra = sorted(set(record) - set(allowed))
    if extra:
        raise DevlogError(f"{where}: 기록 형식에 없는 칸 {extra}. 그 칸을 빼고 다시 기록한다 (03 §6.2)")


def one_of(value, allowed, name):
    if value not in allowed:
        raise DevlogError(f"{name} 값 {value!r}은 목록에 없음: {sorted(allowed)}")


def check_text(value, name, allow_empty=False):
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        raise DevlogError(f"{name}은 비어 있지 않은 문자열이어야 함")


def check_error_type(value, name="error_type"):
    if isinstance(value, str) and re.fullmatch(r"ex\.[a-z0-9_]+", value):
        return
    one_of(value, ERROR_TYPES, name)


def check_iteration(value, rung_ok_for_post):
    if value == "post":
        if not rung_ok_for_post:
            raise DevlogError('iteration "post"는 L6 기록에만 쓴다')
        return
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise DevlogError('iteration은 1 이상 정수 또는 "post"(L6)여야 함')


def check_contract_version(value):
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise DevlogError("contract_version은 1 이상 정수여야 함")


def check_kst(value, name):
    try:
        dt = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        raise DevlogError(f"{name}은 ISO 시각 문자열이어야 함") from None
    if dt.utcoffset() != timedelta(hours=9):
        raise DevlogError(f"{name}은 +09:00 시간대여야 함")


def check_number_or_null(value, name):
    if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float))):
        raise DevlogError(f"{name}은 숫자 또는 null이어야 함")


def find_secret(value, path="record"):
    """비밀값으로 보이는 칸의 위치를 돌려준다. 값 자체는 돌려주지 않는다."""
    if isinstance(value, dict):
        for k, v in value.items():
            hit = find_secret(str(k), f"{path}.{k}(키)") or find_secret(v, f"{path}.{k}")
            if hit:
                return hit
    elif isinstance(value, list):
        for i, v in enumerate(value):
            hit = find_secret(v, f"{path}[{i}]")
            if hit:
                return hit
    elif isinstance(value, str):
        if any(p.search(value) for p in SECRET_PATTERNS):
            return path
    return None


def scrub_strings(value):
    """문자열 칸(중첩 포함)의 프로젝트 ID·메일을 가린다 (결정 71). 새로 쓰는 기록에만 적용하고 과거 줄은 고치지 않는다.
    scripts/handover/make_facts.scrub을 쓴다(make_facts가 이 모듈을 import하므로 부를 때 가져온다)."""
    handover = str(PROJECT / "scripts" / "handover")
    if handover not in sys.path:
        sys.path.insert(0, handover)
    from make_facts import scrub

    def walk(v):
        if isinstance(v, str):
            return scrub(v)
        if isinstance(v, list):
            return [walk(x) for x in v]
        if isinstance(v, dict):
            return {k: walk(x) for k, x in v.items()}
        return v
    return walk(value)


def reject_secrets(record):
    hit = find_secret(record)
    if hit:
        raise DevlogError(f"비밀값(토큰·키·비밀번호)으로 보이는 값이 있어 기록하지 않음: {hit}")


# ---------- Hook 차단 명령 가리기 (4-21) ----------

MASK_LIMIT = 200
MASK_NAME = r"(?:key|token|secret|password|passwd|pwd|credentials?)"
MASK_VALUE = r"(?:\"[^\"]*\"|'[^']*'|[\"']?[^\s'\",;&|)}]+)"
MASK_ASSIGN = re.compile(r"(?<![\w.-])([\w.-]*" + MASK_NAME + r"[\w.-]*)(\s*[=:]+\s*)" + MASK_VALUE, re.I)
MASK_OPTION = re.compile(r"(--[\w-]*" + MASK_NAME + r"[\w-]*\s+)(?!-)" + MASK_VALUE, re.I)
MASK_AUTH = re.compile(r"\b(Bearer|Basic)\s+[^\s'\"]+", re.I)
MASK_URL_LOGIN = re.compile(r"://[^/\s:@]+:[^/\s@]+@")
# 사용자 폴더 경로. 따옴표 안이면 공백이 든 이름까지 통째로 가린다 (Git Bash /c/Users, WSL /mnt/c/Users 포함)
USER_ROOT = r"(?<![\w.-])(?:[A-Za-z]:|/mnt/[A-Za-z]|/[A-Za-z])?[\\/]+(?:Users|home)[\\/]+"
MASK_QUOTED_PATH = re.compile(r"([\"'])" + USER_ROOT + r"[^\"']*\1", re.I)
MASK_PATH = re.compile(USER_ROOT + r"[^\s\"'`;|&<>()]+", re.I)
MASK_EMAIL = re.compile(r"(?<![\w.+-])[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
GCP_ID = r"[a-z][a-z0-9-]{4,28}[a-z0-9]"  # GCP 프로젝트 ID 형식: 6~30자
MASK_PROJECT_OPTION = re.compile(r"(?<![\w-])([\w-]*project(?:[_-]id)?(?:\s*=\s*|\s+))" + GCP_ID + r"\b", re.I)
MASK_PROJECT_REF = re.compile(r"(?<![\w./\\-])" + GCP_ID + r"(?=\.[A-Za-z_]\w*\.[A-Za-z_{*]|:[A-Za-z_])")
MASK_CHUNK = re.compile(r"[A-Za-z0-9+/_-]{20,}={0,2}")
MASK_WORD = re.compile(r"[a-z]{0,19}\d{0,2}|[A-Z]{1,19}|[A-Z][a-z]{1,18}")


def mask_chunk(m):
    """20자 이상 덩어리를 <값>으로. 단어를 / _ - 로 이은 것(경로, --maximum_bytes_billed)은 값이 아니라 그대로 둔다."""
    words = re.split(r"[/_-]", m.group(0).rstrip("="))
    return m.group(0) if len(words) > 1 and all(MASK_WORD.fullmatch(w) for w in words) else "<값>"


def mask_command(text, limit=MASK_LIMIT):
    """Hook 차단 명령의 값·경로·식별자를 가린 뒤 앞 limit자만 남긴다. 두 Hook이 같이 쓴다.
    비밀이 잘린 채 남지 않게 전체를 가린 뒤에 자른다. 그래도 비밀 패턴이 남으면 append가 기록을 거부해
    차단 기록까지 잃으므로 전체를 <값>으로 둔다."""
    text = MASK_ASSIGN.sub(lambda m: f"{m.group(1)}{m.group(2)}<값>", str(text))
    text = MASK_OPTION.sub(lambda m: f"{m.group(1)}<값>", text)
    text = MASK_AUTH.sub(lambda m: f"{m.group(1)} <값>", text)
    text = MASK_URL_LOGIN.sub("://<값>@", text)
    text = MASK_QUOTED_PATH.sub(lambda m: f"{m.group(1)}<경로>{m.group(1)}", text)
    text = MASK_PATH.sub("<경로>", text)
    text = MASK_EMAIL.sub("<메일>", text)
    text = MASK_PROJECT_OPTION.sub(lambda m: f"{m.group(1)}<프로젝트>", text)
    text = MASK_PROJECT_REF.sub("<프로젝트>", text)
    text = MASK_CHUNK.sub(mask_chunk, text)
    if any(p.search(text) for p in SECRET_PATTERNS):
        return "<값>"
    return text if len(text) <= limit else text[:limit] + "…"


# ---------- 형식 검사 ----------

REJECTION_FIELDS = ("mart", "task", "iteration", "contract_version", "caught_by_rung", "error_type", "error_class",
                    "detail", "fixed_in_iteration", "rule_promoted", "evidence")
INTERVENTION_FIELDS = ("mart", "kind", "target", "minutes_spent", "note")
COST_FIELDS = ("run_id", "mart", "iteration", "role", "model", "started", "ended", "usage_before", "usage_after",
               "input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens",
               "total_cost_usd", "bq_bytes_processed")
HOOK_BLOCK_FIELDS = ("hook", "command_summary", "reason", "suggested")
# 값·경로·식별자를 가린 명령 앞부분(mask_command). 차단 판정(진짜·오탐)용. 이 칸이 없는 과거 줄도 유효하다 (4-21)
HOOK_BLOCK_OPTIONAL = ("command_masked",)
# 얻지 못하면 null로 둔다. total_cost_usd는 정가 환산 추정이다 (결정 52 ④).
# 요금제(plan)는 기록하지 않고 model로 모델별 집계한다 (결정 57)
COST_OPTIONAL = ("usage_before", "usage_after", "input_tokens", "output_tokens",
                 "cache_read_tokens", "cache_write_tokens", "total_cost_usd")
COST_ROLES = {"builder", "verifier"}
RUN_ID = re.compile(r"RUN-\d{3,}")
LADDER_FIELDS = ("task", "iteration", "contract_version", "request_kind", "modules", "bytes_total", "rungs",
                 "verdict", "halt_reason")
# halt일 때만 쓰는 선택 칸: 멈춘 원인의 예외 종류와 메시지 {"exception", "message"} (3-3 스모크 2차)
# reject·halt일 때만 쓰는 선택 칸: 일부 단계만 통과하고 멈춘 다른 task [{"task", "passed_rungs", "bytes"}]
# (사다리 층 단위 실행, 마트 1 R-0001). 그 task들은 파일을 남기지 않으므로 바이트를 여기에 보존한다
# 선택 칸: 다른 contract에서 빌린 상류의 준비 실행 [{"task": "<마트>:<task>", "skipped", "bytes"}] (결정 61 ⑤·70).
# 실행 1번의 기록을 그 실행이 처음 쓰는 파일에만 둔다. 바이트는 bytes_total에 넣지 않는다
LADDER_OPTIONAL = ("halt_detail", "interrupted_tasks", "prep")
INTERRUPTED_FIELDS = ("task", "passed_rungs", "bytes")
PREP_FIELDS = ("task", "skipped", "bytes")
PREP_TASK = re.compile(r"[a-z][a-z0-9_]*:[a-z][a-z0-9_]*")
RUNG_FIELDS = ("rung", "ds", "status", "metrics", "error_type", "error_class")


def validate_rejection(r, previous):
    r.setdefault("fixed_in_iteration", None)
    r.setdefault("rule_promoted", None)
    r.setdefault("evidence", None)
    require(r, REJECTION_FIELDS, "rejection")
    no_extra(r, REJECTION_FIELDS, "rejection")
    check_text(r["mart"], "mart")
    check_text(r["task"], "task")
    one_of(r["caught_by_rung"], RUNGS, "caught_by_rung")
    check_iteration(r["iteration"], r["caught_by_rung"] == "L6")
    check_contract_version(r["contract_version"])
    check_error_type(r["error_type"])
    one_of(r["error_class"], ERROR_CLASSES, "error_class")
    check_text(r["detail"], "detail")
    if r["fixed_in_iteration"] is not None or r["rule_promoted"] is not None:
        raise DevlogError("fixed_in_iteration·rule_promoted는 기록 때 null이다. 값은 집계에서 계산한다")
    if r["evidence"] is not None and not r["evidence"]:
        raise DevlogError("evidence는 null 또는 비어 있지 않은 값이어야 함")
    same = [p for p in previous
            if p.get("mart") == r["mart"] and p.get("task") == r["task"] and p.get("error_type") == r["error_type"]]
    if same and r["evidence"] is None:
        raise DevlogError(f"같은 유형({r['error_type']}) 2번째 반려부터 evidence(실패한 검사 쿼리 결과 예시)가 필요함")


def validate_intervention(r, loop_record=False):
    require(r, INTERVENTION_FIELDS, "intervention")
    one_of(r["kind"], KINDS, "kind")
    extra_fields = KIND_FIELDS.get(r["kind"], ())
    require(r, extra_fields, f"intervention({r['kind']})")
    if r["kind"] == "approval" and r["stage"] in STAGE_FIELDS:
        if r["stage"] in LOOP_STAGES and not loop_record:
            raise DevlogError(f"stage {r['stage']}는 run_loop.py 옵션(--extend·--reset-streak)으로만 기록한다")
        extra_fields += STAGE_FIELDS[r["stage"]]
        require(r, extra_fields, f"intervention({r['stage']})")
    no_extra(r, INTERVENTION_FIELDS + extra_fields, f"intervention({r['kind']})")
    if r["mart"] is None:
        if r["kind"] != "module_toggle":
            raise DevlogError("mart는 module_toggle일 때만 null을 허용함")
    else:
        check_text(r["mart"], "mart")
    check_text(r["target"], "target")
    check_text(r["note"], "note", allow_empty=True)
    m = r["minutes_spent"]
    if isinstance(m, bool) or not isinstance(m, (int, float)) or m < 0:
        raise DevlogError("minutes_spent는 0 이상 숫자여야 함")
    if r["kind"] == "approval":
        one_of(r["stage"], STAGES, "stage")
        if r["stage"] in LOOP_STAGES:
            check_loop_approval(r)
        elif r["stage"] == RULE_STAGE and (not isinstance(r["rule_id"], str) or not RULE_ID.fullmatch(r["rule_id"])):
            raise DevlogError("rule_id는 RC-<숫자 3자리 이상> 형식이어야 함")
    elif r["kind"] == "requirement_change":
        one_of(r["cause"], CAUSES, "cause")
    elif r["kind"] == "post_approval_defect":
        check_text(r["found_stage"], "found_stage")
        check_text(r["detail"], "detail")
        one_of(r["missed_by_rung"], RUNGS, "missed_by_rung")
    elif r["kind"] == "module_toggle":
        check_text(r["scope"], "scope")
        if not isinstance(r["now"], bool):
            raise DevlogError("now는 true 또는 false여야 함")


def check_loop_approval(r):
    check_contract_version(r["contract_version"])
    if not isinstance(r["approver"], str) or not APPROVER.fullmatch(r["approver"]):
        raise DevlogError("approver는 역할 코드 approver<숫자>여야 함 (이름은 넣지 않는다)")
    check_text(r["reason"], "reason")
    if r["stage"] == "loop_extension":
        n = r["extra_iterations"]
        if isinstance(n, bool) or not isinstance(n, int) or n < 1:
            raise DevlogError("extra_iterations는 1 이상 정수여야 함")
    else:
        key = r["streak_key"]
        m = re.fullmatch(r"([A-Za-z0-9_]+):(.+)", key) if isinstance(key, str) else None
        if not m:
            raise DevlogError("streak_key는 <task>:<error_type> 형식이어야 함")
        check_error_type(m.group(2), "streak_key의 error_type")


def validate_cost(r):
    for f in COST_OPTIONAL:
        r.setdefault(f, None)
    require(r, COST_FIELDS, "cost")
    no_extra(r, COST_FIELDS, "cost")
    if not isinstance(r["run_id"], str) or not RUN_ID.fullmatch(r["run_id"]):
        raise DevlogError("run_id는 RUN-<숫자 3자리 이상> 형식이어야 함 (루프가 넘긴다)")
    check_text(r["mart"], "mart")
    one_of(r["role"], COST_ROLES, "role")
    check_text(r["model"], "model")
    check_kst(r["started"], "started")
    check_kst(r["ended"], "ended")
    if datetime.fromisoformat(r["ended"]) < datetime.fromisoformat(r["started"]):
        raise DevlogError("ended가 started보다 앞섬")
    # 0은 반복 시작 전 호출(verifier의 검증 쿼리 작성)
    it = r["iteration"]
    if isinstance(it, bool) or not isinstance(it, int) or it < 0:
        raise DevlogError("iteration은 0 이상 정수여야 함")
    for f in COST_OPTIONAL:
        check_number_or_null(r[f], f)
    b = r["bq_bytes_processed"]
    if isinstance(b, bool) or not isinstance(b, int) or b < 0:
        raise DevlogError("bq_bytes_processed는 0 이상 정수여야 함")


def validate_hook_block(r):
    require(r, HOOK_BLOCK_FIELDS, "hook_block")
    no_extra(r, HOOK_BLOCK_FIELDS + HOOK_BLOCK_OPTIONAL, "hook_block")
    for f in HOOK_BLOCK_FIELDS:
        check_text(r[f], f)
    for f in HOOK_BLOCK_OPTIONAL:
        if f in r:
            check_text(r[f], f)


def validate_ladder(r):
    require(r, LADDER_FIELDS, "ladder_result")
    no_extra(r, LADDER_FIELDS + LADDER_OPTIONAL, "ladder_result")
    check_text(r["task"], "task")
    check_contract_version(r["contract_version"])
    one_of(r["request_kind"], REQUEST_KINDS, "request_kind")
    b = r["bytes_total"]
    if b is not None and (isinstance(b, bool) or not isinstance(b, int) or b < 0):
        raise DevlogError("bytes_total은 null 또는 0 이상 정수여야 함")
    expert = (r["modules"] or {}).get("expert") if isinstance(r["modules"], dict) else None
    if not isinstance(expert, dict) or set(expert) != {"on", "version"} or not isinstance(expert["on"], list):
        raise DevlogError('modules는 {"expert": {"on": [...], "version": ...}} 형식이어야 함')
    rungs = r["rungs"]
    if not isinstance(rungs, list):
        raise DevlogError("rungs는 목록이어야 함")
    for i, g in enumerate(rungs):
        where = f"rungs[{i}]"
        if not isinstance(g, dict):
            raise DevlogError(f"{where}는 객체여야 함")
        require(g, RUNG_FIELDS, where)
        no_extra(g, RUNG_FIELDS, where)
        one_of(g["rung"], RUNGS, f"{where}.rung")
        if g["ds"] is not None and not (isinstance(g["ds"], str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", g["ds"])):
            raise DevlogError(f"{where}.ds는 null 또는 YYYY-MM-DD여야 함")
        one_of(g["status"], RUNG_STATUSES, f"{where}.status")
        if not isinstance(g["metrics"], dict):
            raise DevlogError(f"{where}.metrics는 객체여야 함")
        if g["status"] == "fail":
            check_error_type(g["error_type"], f"{where}.error_type")
            one_of(g["error_class"], ERROR_CLASSES, f"{where}.error_class")
            if i != len(rungs) - 1:
                raise DevlogError("처음 실패한 단계에서 멈추므로 fail 뒤에 단계가 올 수 없음")
        elif g["error_type"] is not None or g["error_class"] is not None:
            raise DevlogError(f"{where}: pass 단계의 error_type·error_class는 null이어야 함")
    check_iteration(r["iteration"], bool(rungs) and all(g["rung"] == "L6" for g in rungs))
    if r["request_kind"] == "backfill_check" and r["iteration"] != 1:
        raise DevlogError("backfill_check는 루프 반복이 아니므로 iteration이 1이어야 함 (결정 59)")
    one_of(r["verdict"], VERDICTS, "verdict")
    failed = bool(rungs) and rungs[-1]["status"] == "fail"
    if r["verdict"] == "pass" and (failed or not rungs):
        raise DevlogError("verdict pass인데 통과하지 않은 단계가 있음")
    if r["verdict"] == "reject" and not failed:
        raise DevlogError("verdict reject인데 실패한 단계가 없음")
    if r["verdict"] == "halt":
        one_of(r["halt_reason"], HALT_REASONS, "halt_reason")
    elif r["halt_reason"] is not None:
        raise DevlogError("halt_reason은 verdict가 halt일 때만 씀")
    if "halt_detail" in r:
        d = r["halt_detail"]
        if r["verdict"] != "halt":
            raise DevlogError("halt_detail은 verdict가 halt일 때만 씀")
        if not isinstance(d, dict) or set(d) != {"exception", "message"}:
            raise DevlogError('halt_detail은 {"exception": ..., "message": ...} 형식이어야 함')
        check_text(d["exception"], "halt_detail.exception")
        check_text(d["message"], "halt_detail.message", allow_empty=True)
    if "interrupted_tasks" in r:
        validate_interrupted(r)
    if "prep" in r:
        validate_prep(r["prep"])


def validate_prep(items):
    if not isinstance(items, list) or not items:
        raise DevlogError("prep은 비어 있지 않은 목록이어야 함")
    seen = set()
    for i, it in enumerate(items):
        where = f"prep[{i}]"
        if not isinstance(it, dict):
            raise DevlogError(f"{where}는 객체여야 함")
        require(it, PREP_FIELDS, where)
        no_extra(it, PREP_FIELDS, where)
        if not isinstance(it["task"], str) or not PREP_TASK.fullmatch(it["task"]) or it["task"] in seen:
            raise DevlogError(f"{where}.task는 중복 없는 <마트>:<task>여야 함: {it['task']!r}")
        seen.add(it["task"])
        if not isinstance(it["skipped"], bool):
            raise DevlogError(f"{where}.skipped는 true/false여야 함")
        b = it["bytes"]
        if isinstance(b, bool) or not isinstance(b, int) or b < 0:
            raise DevlogError(f"{where}.bytes는 0 이상 정수여야 함")


def validate_interrupted(r):
    items = r["interrupted_tasks"]
    if r["verdict"] == "pass":
        raise DevlogError("interrupted_tasks는 verdict가 reject·halt일 때만 씀")
    if not isinstance(items, list) or not items:
        raise DevlogError("interrupted_tasks는 비어 있지 않은 목록이어야 함")
    seen = set()
    for i, it in enumerate(items):
        where = f"interrupted_tasks[{i}]"
        if not isinstance(it, dict):
            raise DevlogError(f"{where}는 객체여야 함")
        require(it, INTERRUPTED_FIELDS, where)
        no_extra(it, INTERRUPTED_FIELDS, where)
        check_text(it["task"], f"{where}.task")
        if it["task"] == r["task"] or it["task"] in seen:
            raise DevlogError(f"{where}.task가 이 파일의 task이거나 중복됨: {it['task']!r}")
        seen.add(it["task"])
        rungs = it["passed_rungs"]
        if not isinstance(rungs, list) or not rungs:
            raise DevlogError(f"{where}.passed_rungs는 비어 있지 않은 목록이어야 함")
        for g in rungs:
            one_of(g, RUNGS, f"{where}.passed_rungs")
        b = it["bytes"]
        if isinstance(b, bool) or not isinstance(b, int) or b < 0:
            raise DevlogError(f"{where}.bytes는 0 이상 정수여야 함")


# ---------- 쓰기 ----------

def dev_dir(path=None):
    return Path(path or os.environ.get("DEVLOG_DIR") or PROJECT / ".dev")


class FileLock:
    """여러 세션이 동시에 써도 id가 겹치지 않게 잠금 파일로 순서를 맞춘다."""

    def __init__(self, path, timeout=10.0, stale=30.0):
        self.path, self.timeout, self.stale = Path(str(path) + ".lock"), timeout, stale

    def __enter__(self):
        deadline = time.monotonic() + self.timeout
        while True:
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.close(fd)
                return self
            except (FileExistsError, PermissionError):
                # Windows에서는 다른 프로세스가 잠금 파일을 지우는 중이면 PermissionError가 난다
                try:
                    if time.time() - self.path.stat().st_mtime > self.stale:
                        self.path.unlink()
                        continue
                except (FileNotFoundError, PermissionError):
                    pass
                if time.monotonic() > deadline:
                    raise DevlogError(f"잠금을 얻지 못함: {self.path.name}") from None
                time.sleep(0.02)

    def __exit__(self, *exc):
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass


def read_lines(path):
    if not path.exists():
        return []
    records = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return records


def next_id(records, spec):
    pattern = re.compile(re.escape(spec["prefix"]) + r"(\d+)$")
    nums = [int(m.group(1)) for r in records
            if isinstance(r.get(spec["id_key"]), str) and (m := pattern.match(r[spec["id_key"]]))]
    return f"{spec['prefix']}{(max(nums) if nums else 0) + 1:0{spec['width']}d}"


def append(name, record, base=None, loop_record=False):
    """검사를 통과한 1건을 .dev/<name>.jsonl 끝에 1줄 추가하고 기록한 줄을 돌려준다.
    loop_record=True는 run_loop.py만 넘긴다. 루프 결재(loop_extension·loop_streak_reset)는 이때만 받는다."""
    if name not in LOGS:
        raise DevlogError(f"알 수 없는 로그: {name}")
    if not isinstance(record, dict):
        raise DevlogError("기록은 JSON 객체여야 함")
    spec = LOGS[name]
    record = scrub_strings(dict(record))
    for auto in (spec["id_key"], "ts"):
        if auto and auto in record:
            raise DevlogError(f"{auto}는 도구가 채운다. 넘기지 않는다")
    reject_secrets(record)
    path = dev_dir(base) / f"{name}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with FileLock(path):
        previous = read_lines(path)
        if name == "rejections":
            validate_rejection(record, previous)
        elif name == "interventions":
            validate_intervention(record, loop_record)
        elif name == "cost":
            validate_cost(record)
        else:
            validate_hook_block(record)
        head = {spec["id_key"]: next_id(previous, spec)} if spec["id_key"] else {}
        if name != "cost":
            head["ts"] = now_ts()
        entry = {**head, **record}
        line = json.dumps(entry, ensure_ascii=False) + "\n"
        with path.open("ab") as f:
            f.write(line.encode("utf-8"))
    return entry


def write_ladder_result(mart, record, base=None):
    """ladder_result 1파일을 만든다. 같은 파일이 있으면 덮어쓰지 않고 오류를 낸다. L6(post)는 순번 파일로 추가한다."""
    if not isinstance(record, dict):
        raise DevlogError("기록은 JSON 객체여야 함")
    record = scrub_strings(dict(record))
    if "ts" in record:
        raise DevlogError("ts는 도구가 채운다. 넘기지 않는다")
    for name, value in (("mart", mart), ("task", record.get("task"))):
        if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_]+", value):
            raise DevlogError(f"{name}은 영문·숫자·밑줄만 쓴다 (파일 경로에 들어감)")
    reject_secrets(record)
    validate_ladder(record)
    entry = {k: record[k] for k in ("task", "iteration", "contract_version", "request_kind", "modules")}
    entry["ts"] = now_ts()
    entry.update({k: record[k] for k in ("bytes_total", "rungs", "verdict", "halt_reason")})
    for k in LADDER_OPTIONAL:
        if k in record:
            entry[k] = record[k]
    folder = dev_dir(base) / "ladder_results" / mart
    folder.mkdir(parents=True, exist_ok=True)
    text = json.dumps(entry, ensure_ascii=False, indent=2) + "\n"
    if record["iteration"] == "post":  # L6 재확인은 순번 파일로 추가한다 (결정 67)
        for _ in range(100):
            n = max((k for k, _p in post_files(folder, record["task"], record["contract_version"])), default=0) + 1
            path = folder / f"{record['task']}-v{record['contract_version']}-post-{n}.json"
            try:
                with path.open("x", encoding="utf-8", newline="\n") as f:
                    f.write(text)
                return path
            except FileExistsError:
                continue  # 다른 실행이 같은 순번을 먼저 만들었다
        raise DevlogError("L6 순번 파일을 만들지 못함 (순번 충돌이 계속됨)")
    filename = f"{record['task']}-v{record['contract_version']}-{record['iteration']}.json"
    path = folder / filename
    try:
        with path.open("x", encoding="utf-8", newline="\n") as f:
            f.write(text)
    except FileExistsError:
        raise DevlogError(f"이미 있는 파일이라 덮어쓰지 않음: {path.name}") from None
    return path


def post_files(folder, task, version):
    """[(n, 경로)] — L6 순번 파일 <task>-v<버전>-post-<n>.json, n 오름차순."""
    pattern = re.compile(re.escape(task) + r"-v" + str(version) + r"-post-([1-9]\d*)\.json")
    folder = Path(folder)
    found = [(int(m.group(1)), f) for f in folder.glob(f"{task}-v{version}-post-*.json")
             if (m := pattern.fullmatch(f.name))] if folder.is_dir() else []
    return sorted(found)


def post_results(mart, task, version, base=None):
    """L6 결과 전부(n 오름차순). 각 결과에 "_n"·"_name" 칸을 붙인다."""
    return [{**json.loads(path.read_text(encoding="utf-8")), "_n": n, "_name": path.name}
            for n, path in post_files(dev_dir(base) / "ladder_results" / mart, task, version)]


def latest_post(mart, task, version, base=None):
    """최신 L6 결과(가장 큰 n). 없으면 None (결정 67)."""
    results = post_results(mart, task, version, base)
    return results[-1] if results else None


def post_fixed_in(rejection, posts):
    """L6 반려(iteration "post")를 고친 L6 결과의 n, 없으면 None.
    반려 줄은 결과 파일 뒤에 쓰므로(l6_om.py) 그 반려의 결과 파일 = ts가 반려 줄보다 늦지 않은 reject 파일 중 가장 큰 n.
    고친 결과 = 그보다 큰 n의 첫 pass 파일. ts는 초 단위라 같은 초에 겹쳐도 순번으로 가린다."""
    ts = str(rejection.get("ts", ""))
    own = [p["_n"] for p in posts if p.get("verdict") == "reject" and str(p.get("ts", "")) <= ts]
    start = max(own) if own else 0
    later = [p["_n"] for p in posts if p.get("verdict") == "pass" and p["_n"] > start]
    return min(later) if later else None


# ---------- 명령 ----------

def load_json_arg(args):
    if args.json_file:
        return json.loads(Path(args.json_file).read_text(encoding="utf-8"))
    if args.json:
        return json.loads(args.json)
    raise DevlogError("--json 또는 --json-file이 필요함")


def parse_bool(value):
    if value.lower() in ("true", "1", "yes"):
        return True
    if value.lower() in ("false", "0", "no"):
        return False
    raise argparse.ArgumentTypeError("true 또는 false")


def build_parser():
    p = argparse.ArgumentParser(description=".dev/ 로그 기록 도구 (03 §6.2)")
    p.add_argument("--dev-dir", help="기록할 .dev 폴더 (기본: 저장소의 .dev, 또는 DEVLOG_DIR)")
    sub = p.add_subparsers(dest="cmd", required=True)

    i = sub.add_parser("intervention", help="사람 개입 1건 기록")
    i.add_argument("--kind", required=True, choices=sorted(KINDS))
    i.add_argument("--mart", help="module_toggle이 아니면 필수")
    i.add_argument("--target", required=True)
    i.add_argument("--minutes", required=True, type=float, help="minutes_spent")
    i.add_argument("--note", default="")
    i.add_argument("--stage", choices=sorted(STAGES), help="approval")
    i.add_argument("--rule-id", help="approval·rule_promotion: 규칙 후보 id (RC-001)")
    i.add_argument("--cause", choices=sorted(CAUSES), help="requirement_change")
    i.add_argument("--found-stage", help="post_approval_defect")
    i.add_argument("--detail", help="post_approval_defect")
    i.add_argument("--missed-by-rung", choices=sorted(RUNGS), help="post_approval_defect")
    i.add_argument("--scope", help="module_toggle: 역할 또는 규칙 id")
    i.add_argument("--now", type=parse_bool, help="module_toggle: true/false")

    for name, help_text in (("rejection", "반려 1건"), ("cost", "claude -p 호출 1회 비용"), ("hook-block", "Hook 차단 1건")):
        s = sub.add_parser(name, help=f"{help_text} 기록 (JSON)")
        s.add_argument("--json")
        s.add_argument("--json-file")

    lr = sub.add_parser("ladder", help="ladder_result 1파일 기록 (JSON)")
    lr.add_argument("--mart", required=True)
    lr.add_argument("--json")
    lr.add_argument("--json-file")
    return p


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    args = build_parser().parse_args(argv)
    try:
        if args.cmd == "intervention":
            if args.stage in LOOP_STAGES:
                raise DevlogError(f"stage {args.stage}는 CLI로 기록하지 않는다. "
                                  "run_loop.py --extend·--reset-streak 옵션으로만 기록한다 (결정 63 ⑭)")
            minutes = int(args.minutes) if args.minutes.is_integer() else args.minutes
            record = {"mart": args.mart, "kind": args.kind, "target": args.target,
                      "minutes_spent": minutes, "note": args.note}
            extras = {"stage": args.stage, "cause": args.cause, "found_stage": args.found_stage, "detail": args.detail,
                      "missed_by_rung": args.missed_by_rung, "scope": args.scope, "now": args.now,
                      "rule_id": args.rule_id}
            record.update({k: v for k, v in extras.items() if v is not None})
            entry = append("interventions", record, args.dev_dir)
            print(entry["id"])
        elif args.cmd == "ladder":
            print(write_ladder_result(args.mart, load_json_arg(args), args.dev_dir))
        else:
            name = {"rejection": "rejections", "cost": "cost", "hook-block": "hook_blocks"}[args.cmd]
            entry = append(name, load_json_arg(args), args.dev_dir)
            print(entry[LOGS[name]["id_key"] or "run_id"])
    except (DevlogError, json.JSONDecodeError, OSError) as e:
        print(f"기록하지 않음: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
