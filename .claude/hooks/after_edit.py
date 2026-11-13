"""PostToolUse Hook: 파일을 고친 직후 검사하고 실패 결과를 AI에게 돌려준다 (03 §1.5).

- dags/sql/**/*.sql: 사다리 L1과 같은 부품(scripts/ladder/common.py)으로 bq query --dry_run
  - 인증: ai-builder 설정(CLOUDSDK_CONFIG)인지 확인하고 GCP 프로젝트 ID를 얻는다(Bq.check_auth)
  - 렌더링: jinja2 StrictUndefined. {{ project }}, {{ dataset_* }}(= ai_dev), {{ ds }}, params(common.render)
  - ds: 실행 시각의 UTC 날짜(common.utc_today, 결정 59)
  - SQL은 stdin으로 넘긴다(Bq.dry_run, 결정 59 ⑨)
  이 수정 전에는 자체 정규식 렌더링이 {{ project }}를 바꾸지 못해 sql_rules.md §1 패턴의 SQL에서 dry-run을 건너뛰었다
- docs/requirements/*.contract.json(_로 시작하는 양식 제외): scripts/ladder/l0_contract.py의 check_file로 contract만 검사한다
  (SQL 폴더는 보지 않는다, 결정 80). 인터뷰 중에 AI가 쓴 contract의 형식 오류를 바로 돌려줘 고치게 한다
- *.py: 시험을 돌리지 않고 고친 경로(repo 기준 상대 경로)를 .claude/state/changed_<session_id>.txt에 한 줄 덧붙인다
  관련 시험은 턴 끝에 on_stop.py가 1번 돌린다
PostToolUse는 이미 실행된 뒤라 막지 못한다. 실패하면 종료 코드 2와 stderr로 알린다.
"""
import functools
import json
import os
import sys
from pathlib import Path

LADDER = Path(__file__).resolve().parents[2] / "scripts" / "ladder"
sys.path.insert(0, str(LADDER))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402
from related_tests import changed_file, tail  # noqa: E402

DRY_RUN_TIMEOUT = 120  # Hook 안에서 오래 기다리지 않는다


def project_dir():
    return Path(os.environ.get("CLAUDE_PROJECT_DIR") or Path(__file__).resolve().parents[2])


def relative_path(file_path, project):
    try:
        rel = os.path.relpath(os.path.abspath(file_path), os.path.abspath(project))
    except ValueError:  # Windows에서 드라이브가 다를 때
        return None
    rel = rel.replace("\\", "/")
    return None if rel.startswith("../") else rel


def check_sql(path, bq=None, today=None):
    """문제가 있으면 메시지, 없으면 None. 인증·bq 장애로 확인하지 못해도 메시지로 알린다."""
    bq = bq or common.Bq(runner=functools.partial(common.subprocess_runner, timeout=DRY_RUN_TIMEOUT))
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as e:
        return f"UTF-8로 읽지 못해 dry-run을 건너뛰었다: {e}"
    try:
        project = bq.check_auth()
        bq.dry_run(common.render(text, project, today or common.utc_today()))
    except common.InfraError as e:
        return f"dry-run을 건너뛰었다(사다리 L1에서 다시 확인한다): {e}"
    except common.QueryError as e:
        return f"bq dry-run 실패 ({path.name}, ai_dev 기준 렌더링, {e.error_type}):\n{tail(str(e))}"
    return None


def check_contract(path):
    """L0 contract 검사. 통과면 None, 아니면 오류 메시지."""
    import l0_contract  # 이 Hook이 SQL만 고칠 때는 읽지 않는다
    result = l0_contract.check_file(path)
    if result["status"] == "pass":
        return None
    errors = result["metrics"].get("errors") or ["형식 검사 실패"]
    return ("contract 형식 검사(L0) 실패. 아래를 고친 뒤 다시 저장한다:\n"
            + "\n".join(f"- {e}" for e in errors[:20]))


def is_contract(rel):
    return (rel.startswith("docs/requirements/") and rel.count("/") == 2 and rel.endswith(".contract.json")
            and not rel.rsplit("/", 1)[1].startswith("_"))


def record_changed(project, session_id, rel):
    path = changed_file(project, session_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(rel + "\n")


def main():
    sys.stderr.reconfigure(encoding="utf-8")
    try:
        data = json.loads(sys.stdin.buffer.read().decode("utf-8", "replace"))
    except json.JSONDecodeError:
        return 0
    file_path = (data.get("tool_input") or {}).get("file_path")
    if not file_path:
        return 0
    project = project_dir()
    rel = relative_path(file_path, project)
    if rel is None:
        return 0
    problem = None
    if rel.startswith("dags/sql/") and rel.endswith(".sql") and (project / rel).exists():
        problem = check_sql(project / rel)
    elif is_contract(rel) and (project / rel).exists():
        problem = check_contract(project / rel)
    elif rel.endswith(".py"):
        record_changed(project, data.get("session_id") or "unknown", rel)
    if problem:
        print(f"[after_edit] {rel}\n{problem}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    common.apply_kit_local()  # Claude Code를 설정 전에 켰어도 .kit_local.json의 CLOUDSDK_CONFIG를 쓴다
    sys.exit(main())
