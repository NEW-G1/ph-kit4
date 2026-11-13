"""PreToolUse Hook: builder·verifier의 Write·Edit·Read 경로를 실행 전에 검사한다 (결정 55, 결정 56 ①·③, 결정 60).

- verifier는 docs/requirements/<마트>_checks/<l3|l4|l5>/ 안에만 쓴다
- builder는 docs/requirements/<마트>_checks/에 쓰지 않는다 (검증 쿼리를 고쳐 통과하는 것을 막는다)
- builder는 dags/sql/dq/에 쓰지 않는다. 게이트 파일은 scripts/ladder/gen_dq.py가 l3에서 생성한다
- builder는 _checks/l4·l5를 읽지 않는다. l3(게이트 검사)는 dags/sql/dq/로 옮겨야 하므로 읽을 수 있다
- builder는 out/dashboard.html·out/dashboard.json을 읽지 않는다. 사다리 상세 패널에 l4·l5 검사 SQL 원문이 들어간다
- builder는 dags/harness_config.json, .claude/rules/learned/, docs/ai/rule_candidate_exclusions.md,
  docs/contest/claim_decisions.md(사람이 정한 08 밖 결정)에 쓰지 않는다. verifier는 첫 줄 규칙으로 막힌다
- 역할이 없으면(사람 세션) 검사하지 않는다

역할은 환경변수 HARNESS_ROLE(루프 스크립트가 claude -p 호출마다 넣음)을 먼저 보고,
없으면 Hook 입력의 agent_type(에이전트 name)을 본다.
막으면 종료 코드 2로 끝내고, 이유와 대신 할 일은 stderr로 돌려준다. 기록은 check_bash와 같은 방식이다.
Bash·PowerShell로 파일을 쓰거나 읽는 경우, Grep·Glob으로 읽는 경우는 이 Hook이 보지 않는다.
경로 기준 차단이며 완전한 차단이 아니다.
"""
import json
import os
import re
import sys

from check_bash import load_devlog, masked_field, project_dir

WRITE_TOOLS = {"Write", "Edit"}
READ_TOOLS = {"Read"}
ROLES = ("builder", "verifier")
CHECKS_DIR = re.compile(r"^docs/requirements/[^/]+_checks/[^/]", re.I)
STAGE_DIR = re.compile(r"^docs/requirements/[^/]+_checks/(l3|l4|l5)/[^/]", re.I)
HIDDEN_STAGES = {"l4", "l5"}
DASHBOARD_FILES = re.compile(r"^out/dashboard\.(html|json)$", re.I)  # 상세 패널에 l4·l5 검사 SQL이 있다
DQ_DIR = re.compile(r"^dags/sql/dq/[^/]", re.I)
CONFIG_FILE = re.compile(r"^dags/harness_config\.json$", re.I)
RULE_FILES = re.compile(r"^(\.claude/rules/learned/|docs/ai/rule_candidate_exclusions\.md$|docs/contest/claim_decisions\.md$)", re.I)

SUGGEST = {
    "verifier_write_outside_checks": "verifier는 docs/requirements/<마트>_checks/의 l3·l4·l5 하위 폴더에만 쓴다. 다른 파일을 고쳐야 하면 고치지 말고 보고서에 남긴다.",
    "builder_write_checks": "검증 쿼리는 verifier가 쓴다. 게이트 검사는 dags/sql/dq/에 옮겨 쓰고, 검증 쿼리가 틀렸다고 보이면 고치지 말고 progress.md에 이유를 적고 멈춘다.",
    "builder_write_dq": "dags/sql/dq/의 게이트 파일은 scripts/ladder/gen_dq.py가 _checks/l3/에서 생성한다. 게이트 검사가 틀렸다고 보이면 고치지 말고 progress.md에 이유를 적고 멈춘다.",
    "builder_write_config": "원천·운영 데이터셋 설정은 사람이 하네스 PR로 결재한다. 바꿔야 하면 멈추고 사람에게 요청한다.",
    "builder_write_rules": "승격 규칙, 후보 제외 목록, 주장 결정 표(claim_decisions.md)는 사람이 PR로 결재한다. 규칙 초안은 .dev/rule_candidates.md에 있다.",
    "builder_read_hidden_checks": "builder는 _checks/l4·l5를 읽지 않는다. 요구서와 contract의 완료 조건을 기준으로 작업한다. l3(게이트 검사)만 읽을 수 있다.",
    "builder_read_dashboard": "builder는 out/dashboard.html·out/dashboard.json을 읽지 않는다(사다리 상세 패널에 l4·l5 검사 SQL이 있다). 진행 상태는 .dev/progress.md와 사다리 결과의 반려 기록으로 본다.",
    "parse_error": "Hook 입력을 해석하지 못했다. 파일 경로를 확인하고 다시 실행한다.",
}


def resolve_role(agent_type):
    """HARNESS_ROLE을 먼저, 없으면 agent_type. 둘 다 builder·verifier가 아니면 None (결정 56 ①)."""
    env_role = os.environ.get("HARNESS_ROLE", "").strip()
    if env_role in ROLES:
        return env_role
    return agent_type if agent_type in ROLES else None


def relative_path(file_path, project):
    """저장소 기준 상대 경로. 저장소 밖이거나 해석할 수 없으면 None."""
    try:
        rel = os.path.relpath(os.path.abspath(file_path), os.path.abspath(project))
    except ValueError:  # Windows에서 드라이브가 다를 때
        return None
    rel = rel.replace("\\", "/")
    return None if rel == ".." or rel.startswith("../") else rel


def evaluate(role, tool, file_path, project):
    """막을 이유를 돌려준다. 막지 않으면 None."""
    if role not in ROLES:
        return None
    rel = relative_path(file_path, project) if file_path else None
    in_checks = rel is not None and bool(CHECKS_DIR.match(rel))
    stage = STAGE_DIR.match(rel) if rel is not None else None
    stage = stage.group(1).lower() if stage else None
    if tool in READ_TOOLS:
        if role == "builder" and stage in HIDDEN_STAGES:
            return "builder_read_hidden_checks"
        if role == "builder" and rel is not None and DASHBOARD_FILES.match(rel):
            return "builder_read_dashboard"
        return None
    if role == "verifier" and stage is None:
        return "verifier_write_outside_checks"
    if role == "builder" and in_checks:
        return "builder_write_checks"
    if role == "builder" and rel is not None and DQ_DIR.match(rel):
        return "builder_write_dq"
    if role == "builder" and rel is not None and CONFIG_FILE.match(rel):
        return "builder_write_config"
    if role == "builder" and rel is not None and RULE_FILES.match(rel):
        return "builder_write_rules"
    return None


def log_block(tool, role, file_path, reason):
    rel = relative_path(file_path, project_dir()) if file_path else None
    target = f"[{tool}] {role} -> {rel or '<repo 밖 경로>'}"
    devlog = load_devlog()
    masked = masked_field(devlog, target)
    devlog.append("hook_blocks", {
        "hook": "check_write",
        "command_summary": masked.get("command_masked", target),
        "reason": reason,
        "suggested": SUGGEST[reason],
        **masked,
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
    if tool not in WRITE_TOOLS | READ_TOOLS:
        return 0
    role = resolve_role(data.get("agent_type"))
    file_path = (data.get("tool_input") or {}).get("file_path") or ""
    reason = evaluate(role, tool, file_path, project_dir())
    if not reason:
        return 0
    lines = ["차단: check_write Hook이 이 파일 접근을 막았다.",
             f"- 이유: {reason} ({role} -> {file_path})",
             f"  대신 할 일: {SUGGEST[reason]}"]
    # 기록이 실패해도 차단은 그대로 한다
    try:
        log_block(tool, role, file_path, reason)
    except Exception as e:
        lines.append(f"(hook_blocks.jsonl 기록 실패: {e.__class__.__name__}: {e})")
    print("\n".join(lines), file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
