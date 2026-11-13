"""after_edit.py와 on_stop.py가 같이 쓰는 부분: 관련 시험 고르기, 고친 경로 기록 파일 위치 (03 §1.5).

관련 시험을 고르는 규칙(related_tests)
- tests/test_*.py를 고쳤으면 그 파일
- tests/test_<모듈>.py 이름 일치 + 그 모듈을 import하거나 "<모듈>.py"·"<모듈>"로 경로를 여는 시험 파일
- dags/ 의 .py면 L0 구조 시험(test_l0_contract.py, test_ladder.py의 l0 시험)
select_tests는 여러 경로의 결과를 pytest 1번 분량으로 합친다. 고르는 규칙은 바꾸지 않는다.

명령줄 입구 (사람·대화형 Claude용. Hook은 select_tests만 쓰고 아래 처리는 쓰지 않는다)
  python .claude/hooks/related_tests.py [--run] <고친 파일들>
  python .claude/hooks/related_tests.py --full [--run]
- 표준 출력 한 줄에 pytest 인자(공백이 든 인자는 큰따옴표), 고른 이유는 표준 오류에 한 줄씩
- --run: python -m pytest <인자>를 셸 없이 인자 목록으로 실행하고 그 종료 코드로 끝낸다
- .py가 아닌 파일: tests/test_*.py 중 그 파일 이름(경로 끝부분)을 글자로 언급하는 시험 파일. 없으면 건너뛴다
- 전체 신호: tests/conftest.py를 고쳤거나 관련 시험이 없는 .py(lonely)가 있으면 tests/ 전체
- 직전 실패: .pytest_cache의 lastfailed를 파일 경로로 바꿔 지금 있는 tests/ 파일만 더한다(select_tests로 합침).
  시험 이름이 그 파일에 "def <이름>"으로 아직 있을 때만 넣는다(없어진 시험은 버린다)
- 고를 시험이 없으면 표준 출력은 비우고 종료 0(--run이어도 pytest를 부르지 않는다)
- --full: tests/ 전체 + -rf + junit xml(.claude/state/junit/full-<YYYYMMDD-HHmmss>.xml, --run이면 최근 5개만 남김)
"""
import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

L0_TESTS = ["tests/test_l0_contract.py", "tests/test_ladder.py"]  # -k l0: test_l0_contract 전체 + test_ladder의 l0 시험
L0_FILTER = "l0"
NO_TESTS = "관련 시험 없음, 커밋 전 전체 pytest 필요"


def changed_file(project, session_id):
    """이번 세션에 고친 .py 경로를 모으는 파일. after_edit가 쓰고 on_stop이 읽는다."""
    return project / ".claude" / "state" / f"changed_{session_id}.txt"


def tail(text, lines=40):
    return "\n".join(text.strip().splitlines()[-lines:])


def related_tests(rel, project):
    """(pytest 인자 목록, 대상 설명). 관련 시험이 없으면 ([], None)."""
    if rel.startswith("dags/"):
        return L0_TESTS + ["-k", L0_FILTER], "L0 구조 시험"
    tests_dir = project / "tests"
    name = rel.rsplit("/", 1)[-1]
    if rel.startswith("tests/") and name.startswith("test_"):
        return ([rel], rel) if (project / rel).exists() else ([], None)
    stem = re.escape(name[:-3])
    uses = re.compile(
        rf"^\s*(?:import|from)\s+(?:[\w.]+\.)?{stem}\b"  # import <모듈>, from <패키지>.<모듈> import ...
        rf"|^\s*from\s+\S+\s+import\s+(?:[\w, ]*,\s*)?{stem}\b"  # from <패키지> import <모듈>
        rf"|[\"'/\\]{stem}\.py[\"']"  # 경로 문자열 "…/<모듈>.py"
        rf"|[\"']{stem}[\"']",  # spec_from_file_location("<모듈>", …)
        re.M,
    )
    found = []
    for f in sorted(tests_dir.glob("test_*.py")):
        try:
            text = f.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            text = ""
        if f.name == f"test_{name}" or uses.search(text):
            found.append(f"tests/{f.name}")
    return found, ", ".join(found) if found else None


def select_tests(paths, project):
    """(pytest 인자 목록, 대상 설명, 관련 시험이 없는 경로 목록).

    -k는 명령 전체에 걸리므로 그대로 합치면 다른 파일의 시험이 빠진다.
    dags/와 다른 경로가 섞이면 다른 파일을 이름으로 -k에 더해 각 경로가 고른 시험의 합집합을 유지한다.
    """
    whole, filtered, targets, lonely = [], [], [], []
    for rel in paths:
        args, target = related_tests(rel, project)
        if not args:
            lonely.append(rel)
            continue
        if "-k" in args:
            filtered += args[:args.index("-k")]
            targets.append(target)
        else:
            whole += args
            targets += args
    whole = list(dict.fromkeys(whole))
    args = list(dict.fromkeys(filtered + whole))
    if filtered:
        names = [f.rsplit("/", 1)[-1] for f in whole]
        args += ["-k", " or ".join([L0_FILTER, *names])]
    return args, ", ".join(dict.fromkeys(targets)), lonely


# ---------- 명령줄 입구: 아래는 Hook이 쓰지 않는다 ----------

CONFTEST = "tests/conftest.py"
RUN_OPTS = ["-q", "-n", "auto"]
JUNIT_DIR = ".claude/state/junit"
JUNIT_KEEP = 5
NOT_SELECTABLE = "고르기 대상 아님(마지막 전체 시험에서 확인)"
NOTHING = "고를 시험 없음(마지막 전체 시험에서 확인)"


def normalize(path, project):
    """명령줄 경로를 repo 기준 상대 경로(/ 구분)로. 밖이면 그대로 둔다."""
    p = Path(path)
    if p.is_absolute():
        try:
            p = p.resolve().relative_to(Path(project).resolve())
        except ValueError:
            return path.replace("\\", "/")
    rel = p.as_posix()
    return rel[2:] if rel.startswith("./") else rel


def mentioned_by(rel, project):
    """.py가 아닌 파일: 그 파일 이름을 글자로 언급하는 tests/test_*.py."""
    name = rel.rsplit("/", 1)[-1]
    found = []
    for f in sorted((Path(project) / "tests").glob("test_*.py")):
        try:
            text = f.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if name in text:
            found.append(f"tests/{f.name}")
    return found


def last_failed_files(project):
    """직전 실패 시험이 든 파일 중 지금 있는 tests/ 파일. 캐시가 없거나 깨졌으면 []."""
    try:
        data = json.loads((Path(project) / ".pytest_cache" / "v" / "cache" / "lastfailed").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if not isinstance(data, dict):
        return []
    texts, files = {}, []
    for node in data:
        parts = str(node).split("[", 1)[0].split("::")  # 매개변수 [..] 앞부분: 파일::[클래스::]함수
        f = parts[0].replace("\\", "/")
        if not (f.startswith("tests/") and f.endswith(".py") and (Path(project) / f).is_file()):
            continue
        if len(parts) > 1:  # 시험 이름이 있으면 그 함수가 아직 파일에 있을 때만(없어진 시험은 버린다)
            if f not in texts:
                try:
                    texts[f] = (Path(project) / f).read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError):
                    texts[f] = ""
            if not re.search(rf"^\s*(?:async\s+)?def\s+{re.escape(parts[-1])}\b", texts[f], re.M):
                continue
        files.append(f)  # 파일만 있는 항목(수집 오류)은 파일을 넣는다
    return list(dict.fromkeys(files))


def cli_select(paths, project):
    """(pytest 인자 목록, 표준 오류 줄 목록). 규칙은 select_tests 그대로, 전체 신호·비 .py·직전 실패만 여기서."""
    notes, py, extra = [], [], []
    for rel in paths:
        if rel.endswith(".py"):
            py.append(rel)
            continue
        found = mentioned_by(rel, project)
        if found:
            notes.append(f"{rel}: 이름을 언급하는 시험 {', '.join(found)}")
            extra += found
        else:
            notes.append(f"{rel}: {NOT_SELECTABLE}")
    if CONFTEST in py:
        return ["tests/"], notes + [f"전체: {CONFTEST}를 고쳤다(모든 시험에 영향)"]
    args, target, lonely = select_tests(py, project)
    if lonely:
        return ["tests/"], notes + [f"전체: 관련 시험 없는 .py {', '.join(lonely)}"]
    if target:
        notes.append(f"대상: {target}")
    failed = last_failed_files(project)  # args에 이미 있어도 다시 넣는다: dags/의 -k에 파일 이름이 붙어야 빠지지 않는다
    if failed:
        notes.append(f"직전 실패: {', '.join(failed)}")
    if extra or failed:
        args = select_tests([*py, *dict.fromkeys(extra + failed)], project)[0]
    return args, notes


def junit_path(project, now=None):
    stamp = (now or datetime.now()).strftime("%Y%m%d-%H%M%S")
    return Path(project) / JUNIT_DIR / f"full-{stamp}.xml"


def prune_junit(folder, keep=JUNIT_KEEP):
    """새 파일을 만들기 전에 full-*.xml을 수정 시각이 오래된 것부터 지워 새 것 포함 keep개가 되게 한다."""
    old = sorted(Path(folder).glob("full-*.xml"), key=lambda f: f.stat().st_mtime)
    for f in old[:max(0, len(old) - (keep - 1))]:
        f.unlink(missing_ok=True)


def quote(args):
    return " ".join(f'"{a}"' if (" " in a or not a) else a for a in args)


def main(argv=None, runner=subprocess.run, project=None, now=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="고친 파일의 관련 시험을 골라 pytest 인자를 출력한다")
    ap.add_argument("paths", nargs="*", help="고친 파일들")
    ap.add_argument("--run", action="store_true", help="python -m pytest <인자> -q -n auto를 직접 실행")
    ap.add_argument("--full", action="store_true", help="tests/ 전체 + junit xml(.claude/state/junit/)")
    a = ap.parse_args(argv)
    project = Path(project or os.environ.get("CLAUDE_PROJECT_DIR") or Path(__file__).resolve().parents[2])
    if a.full == bool(a.paths):
        ap.error("고친 파일들 또는 --full 중 하나만 준다")
    if a.full:
        xml = junit_path(project, now)
        args = ["tests/", *RUN_OPTS, "-rf", f"--junitxml={xml.relative_to(project).as_posix()}"]
        notes = ["전체: --full"]
    else:
        args, notes = cli_select([normalize(p, project) for p in a.paths], project)
        if args:
            args += RUN_OPTS
    for line in notes:
        print(line, file=sys.stderr)
    if not args:
        print(NOTHING, file=sys.stderr)
        return 0
    print(quote(args))
    if not a.run:
        return 0
    if a.full:
        xml.parent.mkdir(parents=True, exist_ok=True)
        prune_junit(xml.parent)
    return runner([sys.executable, "-m", "pytest", *args], cwd=project).returncode


if __name__ == "__main__":
    sys.exit(main())
