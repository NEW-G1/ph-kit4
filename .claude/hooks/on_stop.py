"""Stop Hook: 턴 끝에 관련 시험을 1번 돌리고(재시도 3회) 기록 누락을 알린다 (03 §1.5).

관련 시험: after_edit.py가 모은 .claude/state/changed_<session_id>.txt의 경로로 고른다(related_tests.py)
- 경로가 없으면 시험을 돌리지 않는다
- 통과(종료 0·5): changed 파일과 재시도 수를 지우고 종료 0
- 관련 시험이 없는 경로: "관련 시험 없음, 커밋 전 전체 pytest 필요"를 알린다(실패 아님)
- 실패: 재시도 수를 1 올리고 실패 끝 40줄을 stderr로 내고 종료 2(Claude가 이어서 고친다). changed 파일은 둔다
- 3번째 실패: 더 붙잡지 않고 종료 0, 사람 확인 알림. 재시도 수만 지우고 changed 파일은 둔다
- 시간 초과: 고쳐서 풀리는 실패가 아니므로 재시도로 세지 않고 종료 0, 알림. changed 파일은 둔다
재시도 수는 stop_hook_active가 참일 때만 이어 센다. 새 턴이면 0부터다.
전체 시험은 python -m pytest tests/ -q -n auto로 마지막 커밋 뒤 따로 돌린다.

기록 누락 알림: 막지 않는다
- .dev/progress.md가 이번 세션에 갱신됐는지
- 이번 실행 로그(.dev/rejections·interventions·cost.jsonl)가 이번 세션에 기록됐는지
세션 시작 시각은 transcript 파일이 만들어진 시각으로 본다. 알 수 없으면 있는지만 본다.
턴의 첫 Stop에서만 확인해, 시험 실패로 이어져도 한 턴에 한 번만 낸다.
종료 0이면 stdout JSON의 systemMessage로, 종료 2면 JSON이 읽히지 않으므로 stderr로 시험 결과와 함께 낸다.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from related_tests import NO_TESTS, changed_file, select_tests, tail  # noqa: E402

RUN_LOGS = ("rejections.jsonl", "interventions.jsonl", "cost.jsonl")
MAX_RETRIES = 3  # CLAUDE.md §5 "같은 유형 3회 연속이면 멈춤"
PYTEST_TIMEOUT = 840  # Stop Hook 제한(settings.json 900초) 안에서 끝낸다


def project_dir():
    return Path(os.environ.get("CLAUDE_PROJECT_DIR") or Path(__file__).resolve().parents[2])


def session_start(transcript_path):
    if not transcript_path or not os.path.exists(transcript_path):
        return None
    st = os.stat(transcript_path)
    if hasattr(st, "st_birthtime"):
        return st.st_birthtime
    return st.st_ctime if os.name == "nt" else None  # Windows의 st_ctime은 만든 시각


def find_notes(project, start):
    dev = project / ".dev"
    notes = []
    progress = dev / "progress.md"
    if not progress.exists():
        notes.append(".dev/progress.md가 아직 없다. 작업을 시작하면 03 §4.4 형식으로 만든다.")
    elif start and progress.stat().st_mtime < start:
        notes.append("이번 세션에 .dev/progress.md를 갱신하지 않았다.")
    logs = [dev / name for name in RUN_LOGS if (dev / name).exists()]
    if not logs:
        notes.append("실행 로그(.dev/rejections·interventions·cost.jsonl)가 아직 없다.")
    elif start and all(p.stat().st_mtime < start for p in logs):
        notes.append("이번 세션에 실행 로그(.dev/*.jsonl)를 남기지 않았다.")
    return notes


def retry_file(project, session_id):
    return project / ".claude" / "state" / f"retry_{session_id}.txt"


def read_retry(path):
    text = path.read_text(encoding="utf-8").strip() if path.exists() else ""
    return int(text) if text.isdigit() else 0


def check_tests(project, session_id, active, runner):
    """(실패 메시지 또는 None, 알림 목록). 실패면 changed 파일이 남아 다음 Stop에 알리므로 알림은 비운다."""
    changed, retry = changed_file(project, session_id), retry_file(project, session_id)
    if not changed.exists():
        return None, []
    paths = dict.fromkeys(p.strip() for p in changed.read_text(encoding="utf-8").splitlines() if p.strip())
    args, target, lonely = select_tests(paths, project)
    notices = [f"{p}: {NO_TESTS}" for p in lonely]
    if args:
        cmd = [sys.executable, "-m", "pytest", *args, "-q", "--tb=short"]
        try:
            r = runner(cmd, cwd=project, capture_output=True, text=True, encoding="utf-8", errors="replace",
                       timeout=PYTEST_TIMEOUT)
        except subprocess.TimeoutExpired:
            retry.unlink(missing_ok=True)
            return None, [f"pytest가 {PYTEST_TIMEOUT}초 안에 끝나지 않았다(대상: {target}). 커밋 전 전체 pytest로 확인", *notices]
        if r.returncode not in (0, 5):  # 5 = 모은 테스트 없음
            count = (read_retry(retry) if active else 0) + 1
            if count >= MAX_RETRIES:
                retry.unlink(missing_ok=True)
                return None, [f"관련 시험이 {MAX_RETRIES}회 고친 뒤에도 실패, 사람 확인 필요 (대상: {target})", *notices]
            retry.write_text(str(count), encoding="utf-8")
            return (f"pytest 실패 (대상: {target}, 종료 코드 {r.returncode}, 재시도 {count}/{MAX_RETRIES}):\n"
                    f"{tail(r.stdout + r.stderr)}"), []
    changed.unlink()
    retry.unlink(missing_ok=True)
    return None, notices


def main(runner=subprocess.run):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    try:
        data = json.loads(sys.stdin.buffer.read().decode("utf-8", "replace"))
    except json.JSONDecodeError:
        data = {}
    project = project_dir()
    active = bool(data.get("stop_hook_active"))
    notes = [] if active else find_notes(project, session_start(data.get("transcript_path")))
    failure, notices = check_tests(project, data.get("session_id") or "unknown", active, runner)
    if failure:
        print("\n".join([f"[on_stop] {failure}"] + ([f"[on_stop] {' / '.join(notes)}"] if notes else [])), file=sys.stderr)
        return 2
    notes += notices
    if notes:
        print(json.dumps({"systemMessage": "[on_stop] " + " / ".join(notes)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
