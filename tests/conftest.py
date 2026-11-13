"""tests 공용 (D-54). 브라우저 시험이 조용히 건너뛰지 않게 하는 판단을 여기 한 곳에 둔다.

- 브라우저 시험 파일은 fixture `browser`(chromium)와 `playwright_api()`만 쓴다. 파일마다 importorskip·skip을 두지 않는다
- 환경변수 REQUIRE_BROWSER=1이면 playwright를 import하지 못하거나 chromium을 띄우지 못할 때 건너뛰지 않고 실패한다.
  값이 없거나 1이 아니면 지금처럼 건너뛴다. 원인은 대개 `python -m playwright install chromium` 누락이다

git 감싸기 (시험 속도, 시험 쪽만. scripts/는 그대로):
- autouse fixture `_git_wrap`이 하네스의 git 실행 함수(GIT_FUNCS)를 monkeypatch로 감싼다. 셋이 모두 맞을 때만 git을
  띄우지 않고, 진짜 git이 실패할 때 그 함수가 하는 일(같은 예외 종류·메시지 형식, False, None, "없음")을 그대로 한다.
  ① 하위 명령이 저장소가 꼭 필요한 것(REPO_COMMANDS, 저장소 밖에서 모두 같은 "not a git repository"로 실패하는 것.
     diff는 저장소 밖에서 --no-index로 동작이 달라 넣지 않는다) ② root(cwd 또는 -C 대상)와 그 위 모든 폴더에 .git이
     없다(Path.exists, 워크트리·서브모듈의 .git 파일도 저장소로 본다, 호출할 때마다 새로 본다)
  ③ GIT_DIR·GIT_WORK_TREE·GIT_CEILING_DIRECTORIES가 없다. 그 밖(root가 없는 폴더, PATH에 git 없음 등)은 원래 함수를 부른다
- stderr 글자는 고정하지 않는다. 세션(worker)마다 .git 없는 임시 폴더에서 진짜 git을 1번 띄워 받은 값을 쓴다
- 끄는 스위치: 환경변수 HARNESS_REAL_GIT=1이면 감싸기 전체를 끈다(전체 시험을 진짜 git으로 돌릴 때).
  git 동작 자체(저장소 없음 처리, git 실패 흉내 등)를 보는 시험은 @pytest.mark.real_git으로 그 시험에서만 끈다
- 감싸는 대상은 sys.modules에서 파일 경로로 찾는다(conftest가 import하지 않는다). `from deliv_common import git`처럼
  이름을 가져다 쓴 모듈의 이름도 같이 바꾼다. 키트처럼 모듈이 없으면 그 항목은 건너뛴다
"""
import importlib
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

INSTALL_HINT = "python -m playwright install chromium"
PROJECT = Path(__file__).resolve().parents[1]


def require_browser():
    return os.environ.get("REQUIRE_BROWSER") == "1"


def no_browser(reason):
    """브라우저를 쓸 수 없을 때의 판단 하나. REQUIRE_BROWSER=1이면 실패, 아니면 건너뜀."""
    msg = f"{reason}. 설치: {INSTALL_HINT}"
    if require_browser():
        pytest.fail(f"REQUIRE_BROWSER=1인데 브라우저 시험을 돌릴 수 없다: {msg}", pytrace=False)
    pytest.skip(msg)


def playwright_api():
    """playwright.sync_api 모듈. import하지 못하면 no_browser."""
    try:
        return importlib.import_module("playwright.sync_api")
    except ImportError as exc:
        no_browser(f"playwright를 import하지 못함 ({exc.__class__.__name__}: {exc})")


def launch_chromium(p):
    try:
        return p.chromium.launch()
    except Exception as exc:  # 브라우저 미설치 등
        no_browser(f"chromium을 띄우지 못함 ({exc.__class__.__name__})")


@pytest.fixture(scope="module")
def browser():
    with playwright_api().sync_playwright() as p:
        b = launch_chromium(p)
        yield b
        b.close()


# ---------- git 감싸기 ----------

def pytest_configure(config):
    config.addinivalue_line("markers", "real_git: 이 시험에서는 git 감싸기를 끈다(git 동작·실패 처리 자체를 보는 시험)")


# 저장소 밖에서 모두 128과 같은 stderr("not a git repository")로 실패하는 하위 명령. remote는 get-url만
REPO_COMMANDS = frozenset({"rev-parse", "log", "show", "cat-file", "merge-base", "ls-files", "status", "symbolic-ref",
                           "fetch", "add", "rm", "commit"})
GIT_ENV = ("GIT_DIR", "GIT_WORK_TREE", "GIT_CEILING_DIRECTORIES")


def real_git_off():
    return os.environ.get("HARNESS_REAL_GIT") == "1"


def git_dir_of(base, args):
    """(git이 실제로 볼 폴더, 하위 명령, 나머지 인자). 모르는 전역 옵션이 있으면 None(감싸지 않는다)."""
    d = Path(base) if base is not None else Path.cwd()
    args = [str(a) for a in args]
    while args and args[0] in ("-C", "-c") and len(args) >= 2:
        if args[0] == "-C":
            d = d / args[1]
        args = args[2:]
    if not args or args[0].startswith("-"):
        return None
    return d, args[0], args[1:]


def needs_repo(sub, rest):
    return sub in REPO_COMMANDS or (sub == "remote" and rest[:1] == ["get-url"])


def outside_repo(base, args):
    """감쌀 조건 셋이 모두 맞으면 True. 검사 결과는 저장하지 않는다(시험 중 git init이 있다)."""
    if real_git_off() or any(k in os.environ for k in GIT_ENV) or shutil.which("git") is None:
        return False
    parsed = git_dir_of(base, args)
    if parsed is None or not needs_repo(parsed[1], parsed[2]):
        return False
    d = parsed[0].resolve()
    if not d.is_dir():  # 없는 폴더는 원래 함수가 내는 오류(OSError·cannot change to)를 그대로 본다
        return False
    return not any((p / ".git").exists() for p in (d, *d.parents))


_PROBE = {}


def probe():
    """.git 없는 임시 폴더에서 진짜 git을 1번 띄운 (returncode, stderr bytes). 임시 폴더 위에 .git이 있으면 None."""
    if "v" not in _PROBE:
        with tempfile.TemporaryDirectory() as t:
            p = Path(t).resolve()
            if any((q / ".git").exists() for q in (p, *p.parents)) or shutil.which("git") is None:
                _PROBE["v"] = None
            else:
                r = subprocess.run(["git", "rev-parse", "HEAD"], cwd=t, capture_output=True)
                _PROBE["v"] = (r.returncode, r.stderr) if r.returncode != 0 else None
    return _PROBE["v"]


def fail_text(limit):
    return probe()[1].decode("utf-8", "replace").strip()[:limit]


# (파일, 함수 이름, 감싸기 만들기). 감싸기 만들기(orig, mod) → 감싼 함수
def raise_git(exc_name, limit):
    def make(orig, mod):
        def git(root, *args):
            if outside_repo(root, args) and probe():
                raise getattr(mod, exc_name)(f"git {' '.join(args)}: {fail_text(limit)}")
            return orig(root, *args)
        return git
    return make


def false_git_ok(orig, mod):
    def git_ok(root, *args):
        if outside_repo(root, args) and probe():
            return False
        return orig(root, *args)
    return git_ok


def none_head(orig, mod):  # dashboard_data.head: git -C root rev-parse HEAD, 실패면 NONE
    def head(root):
        if outside_repo(None, ["-C", str(root), "rev-parse", "HEAD"]) and probe():
            return mod.NONE
        return orig(root)
    return head


def none_repo_url(orig, mod):  # dashboard_data.repo_url: git -C root remote get-url origin, 실패면 None
    def repo_url(root):
        if outside_repo(None, ["-C", str(root), "remote", "get-url", "origin"]) and probe():
            return None
        return orig(root)
    return repo_url


def stop_tracked(orig, mod):  # make_kit.tracked: git -C root ls-files -z, 실패면 Stop
    def tracked(root):
        if outside_repo(None, ["-C", str(root), "ls-files", "-z"]) and probe():
            raise mod.Stop("git ls-files 실패. 저장소 안에서 실행한다")
        return orig(root)
    return tracked


def completed_l0(orig, mod):  # l0_dag.git: CompletedProcess를 돌려준다(returncode만 보고 판단)
    def git(root, *args, timeout=30):
        if outside_repo(None, ["-C", str(root), *args]) and probe():
            rc, err = probe()
            return subprocess.CompletedProcess([shutil.which("git"), "-C", str(root), *args], rc, b"", err)
        return orig(root, *args, timeout=timeout)
    return git


GIT_FUNCS = (
    ("scripts/handover/make_facts.py", "git", raise_git("FactsError", 300)),
    ("scripts/handover/make_facts.py", "git_ok", false_git_ok),
    ("scripts/loop/state.py", "git", raise_git("GitError", 300)),  # state.head·report.stale도 이 이름을 부른다
    ("scripts/loop/state.py", "git_ok", false_git_ok),
    ("scripts/deliverables/deliv_common.py", "git", raise_git("ReportError", 200)),
    ("scripts/metrics/dashboard_data.py", "head", none_head),
    ("scripts/metrics/dashboard_data.py", "repo_url", none_repo_url),
    ("scripts/kit/make_kit.py", "tracked", stop_tracked),
    ("scripts/ladder/l0_dag.py", "git", completed_l0),
)
# 이름을 가져다 쓴 모듈: 원래 함수와 같은 객체를 가진 이름이면 같이 바꾼다
IMPORTERS = {"scripts/deliverables/deliv_common.py": ("scripts/cards/make_cards.py",
                                                      "scripts/deliverables/flow_diagram.py",
                                                      "scripts/deliverables/table_spec.py",
                                                      "scripts/deliverables/unit_test_report.py")}


_INDEX = {"n": -1, "by_name": {}}
WANTED = {Path(rel).name for rel, _, _ in GIT_FUNCS} | {Path(r).name for v in IMPORTERS.values() for r in v}


def loaded_modules(rel):
    """sys.modules에서 그 파일로 읽은 모듈들 (이름이 달라도 같은 파일이면 모두). 색인은 sys.modules 수가 바뀔 때만 다시 만든다."""
    if _INDEX["n"] != len(sys.modules):
        by_name = {}
        for m in list(sys.modules.values()):
            f = getattr(m, "__file__", None)
            if isinstance(f, str) and os.path.basename(f) in WANTED:
                by_name.setdefault(os.path.basename(f), []).append(m)
        _INDEX.update(n=len(sys.modules), by_name=by_name)
    want = (PROJECT / rel).resolve()
    return [m for m in _INDEX["by_name"].get(want.name, ()) if Path(m.__file__).resolve() == want]


def install_git_wrap(mp):
    """mp(MonkeyPatch)로 GIT_FUNCS를 감싼다. 감싼 (모듈 이름, 함수 이름) 목록."""
    done = []
    for rel, name, make in GIT_FUNCS:
        for mod in loaded_modules(rel):
            orig = getattr(mod, name, None)
            if orig is None:
                continue
            wrapped = make(orig, mod)
            mp.setattr(mod, name, wrapped)
            done.append((mod.__name__, name))
            for imp in IMPORTERS.get(rel, ()):
                for other in loaded_modules(imp):
                    if getattr(other, name, None) is orig:
                        mp.setattr(other, name, wrapped)
                        done.append((other.__name__, name))
    return done


@pytest.fixture(autouse=True)
def _git_wrap(request, monkeypatch):
    if real_git_off() or request.node.get_closest_marker("real_git") or probe() is None:
        return
    install_git_wrap(monkeypatch)
