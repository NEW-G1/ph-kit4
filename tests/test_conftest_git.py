"""tests/conftest.py의 git 감싸기 시험 (시험 속도). 감싼 값·예외가 같은 폴더에서 감싸기를 끈 진짜 결과와 같고,
.git 없는 폴더 + 저장소가 필요한 명령에서만 git을 띄우지 않는지 본다. 키트처럼 모듈이 없으면 그 항목은 목록에서 빠진다."""
import importlib
import subprocess
import sys
from pathlib import Path

import pytest

TESTS = Path(__file__).resolve().parent
ROOT = TESTS.parent
sys.path.insert(0, str(TESTS))
for sub in ("handover", "loop", "deliverables", "metrics", "kit", "ladder", "cards"):
    sys.path.insert(0, str(ROOT / "scripts" / sub))
import conftest  # noqa: E402


def optional(name):
    try:
        return importlib.import_module(name)
    except ImportError:
        return None


MODS = {n: optional(n) for n in ("make_facts", "state", "deliv_common", "dashboard_data", "make_kit", "l0_dag",
                                 "make_cards", "flow_diagram", "table_spec", "unit_test_report")}
CALLS = {  # 감싼 함수마다 저장소가 필요한 명령 하나
    "make_facts.git": lambda m, r: m["make_facts"].git(r, "rev-parse", "HEAD"),
    "make_facts.git_ok": lambda m, r: m["make_facts"].git_ok(r, "rev-parse", "--verify", "-q", "main"),
    "state.git": lambda m, r: m["state"].git(r, "status", "--porcelain", "--untracked-files=all"),
    "state.git -c": lambda m, r: m["state"].git(r, "-c", "core.quotepath=off", "ls-files", "--others"),
    "state.git_ok": lambda m, r: m["state"].git_ok(r, "cat-file", "-e", "origin/main:x"),
    "state.head": lambda m, r: m["state"].head(r),
    "deliv_common.git": lambda m, r: m["deliv_common"].git(r, "rev-parse", "HEAD"),
    "make_cards.git": lambda m, r: m["make_cards"].git(r, "rev-parse", "HEAD"),
    "flow_diagram.git": lambda m, r: m["flow_diagram"].git(r, "rev-parse", "HEAD"),
    "table_spec.git": lambda m, r: m["table_spec"].git(r, "rev-parse", "HEAD"),
    "unit_test_report.git": lambda m, r: m["unit_test_report"].git(r, "rev-parse", "--abbrev-ref", "HEAD"),
    "dashboard_data.head": lambda m, r: m["dashboard_data"].head(r),
    "dashboard_data.repo_url": lambda m, r: m["dashboard_data"].repo_url(r),
    "make_kit.tracked": lambda m, r: m["make_kit"].tracked(r),
    "l0_dag.git": lambda m, r: m["l0_dag"].git(r, "cat-file", "-e", "origin/main:x"),
}
NEEDS = {k: k.split(".")[0] for k in CALLS}
AVAILABLE = [k for k in CALLS if MODS[NEEDS[k]] is not None]


@pytest.fixture(autouse=True)
def _wrap_even_when_switched_off(request, monkeypatch):
    """전체를 HARNESS_REAL_GIT=1로 돌려도 이 파일은 감싸기 자체를 시험한다(real_git 표시 시험만 끈 채로 둔다)."""
    if conftest.real_git_off() and not request.node.get_closest_marker("real_git"):
        monkeypatch.delenv("HARNESS_REAL_GIT")
        conftest.probe()  # 진짜 git 1번(세션 시작 몫)은 계수 밖에서
        conftest.install_git_wrap(monkeypatch)


class Count:
    """subprocess.Popen을 감싸 git 실행 수를 센다(이 시험 안에서만)."""

    def __init__(self, monkeypatch):
        self.n = 0
        real = subprocess.Popen
        counter = self

        class Popen(real):
            def __init__(self, args, *a, **kw):
                if Path(str(args[0])).stem.lower() == "git":
                    counter.n += 1
                super().__init__(args, *a, **kw)

        monkeypatch.setattr(subprocess, "Popen", Popen)


def outcome(key, root):
    """("값", 값) 또는 ("예외", 종류, 메시지). CompletedProcess는 (args, returncode, stdout, stderr)."""
    try:
        v = CALLS[key](MODS, root)
    except Exception as e:  # noqa: BLE001  감싼 것과 진짜가 같은 예외를 내는지 비교한다
        return ("예외", type(e), str(e))
    if isinstance(v, subprocess.CompletedProcess):
        v = (v.args, v.returncode, v.stdout, v.stderr)
    return ("값", v)


def test_all_targets_found_and_wrapped():
    """키트 원본(scripts/kit)이 있는 저장소에서는 감쌀 함수가 모두 있고, autouse fixture가 모두 감쌌다."""
    if (ROOT / "scripts" / "kit" / "make_kit.py").exists():
        assert AVAILABLE == list(CALLS)
    for rel, name, _ in conftest.GIT_FUNCS:
        for mod in conftest.loaded_modules(rel):
            assert getattr(mod, name).__module__ == "conftest", (rel, name)
    for rels in conftest.IMPORTERS.values():
        for rel in rels:
            for mod in conftest.loaded_modules(rel):
                assert mod.git.__module__ == "conftest", rel


def test_probe_is_real_git_failure():
    rc, err = conftest.probe()
    assert rc != 0 and err.strip()


@pytest.mark.parametrize("key", AVAILABLE)
def test_wrapped_equals_real_and_spawns_no_git(key, tmp_path, monkeypatch):
    count = Count(monkeypatch)
    wrapped = outcome(key, tmp_path)
    assert count.n == 0, key
    monkeypatch.setenv("HARNESS_REAL_GIT", "1")
    real = outcome(key, tmp_path)
    assert count.n >= 1, key
    assert wrapped == real


@pytest.mark.parametrize("kind", ["dir", "file"])
@pytest.mark.parametrize("key", AVAILABLE)
def test_dot_git_dir_or_file_above_calls_original(key, kind, tmp_path, monkeypatch):
    dot = tmp_path / ".git"
    if kind == "dir":
        dot.mkdir()
    else:  # 워크트리·서브모듈은 .git이 파일이다
        dot.write_text("gitdir: ../nowhere\n", encoding="utf-8")
    root = tmp_path / "a" / "b"
    root.mkdir(parents=True)
    count = Count(monkeypatch)
    outcome(key, root)
    assert count.n >= 1, key


def test_checked_each_call_not_cached(tmp_path, monkeypatch):
    count = Count(monkeypatch)
    state = MODS["state"]
    assert state.git_ok(tmp_path, "rev-parse", "HEAD") is False and count.n == 0
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True, capture_output=True)
    n = count.n
    state.git_ok(tmp_path, "rev-parse", "--git-dir")
    assert count.n == n + 1  # 저장소가 생긴 뒤에는 원래 함수


@pytest.mark.parametrize("args", [("--version",), ("config", "--global", "--get", "harness.test-none"),
                                  ("diff", "--quiet", "a", "b")])
def test_commands_outside_repo_not_wrapped(args, tmp_path, monkeypatch):
    count = Count(monkeypatch)
    MODS["state"].git_ok(tmp_path, *args)
    assert count.n == 1


def test_missing_folder_calls_original(tmp_path, monkeypatch):
    count = Count(monkeypatch)
    wrapped = outcome("state.git", tmp_path / "missing")
    monkeypatch.setenv("HARNESS_REAL_GIT", "1")
    assert outcome("state.git", tmp_path / "missing") == wrapped and count.n == 2


@pytest.mark.parametrize("env", ["HARNESS_REAL_GIT", "GIT_DIR", "GIT_WORK_TREE", "GIT_CEILING_DIRECTORIES"])
def test_env_switches_off(env, tmp_path, monkeypatch):
    monkeypatch.setenv(env, "1" if env == "HARNESS_REAL_GIT" else str(tmp_path / "x"))
    count = Count(monkeypatch)
    MODS["state"].git_ok(tmp_path, "rev-parse", "HEAD")
    assert count.n == 1


@pytest.mark.real_git
def test_real_git_marker_switches_off(tmp_path, monkeypatch):
    count = Count(monkeypatch)
    assert MODS["state"].git_ok(tmp_path, "rev-parse", "HEAD") is False and count.n == 1
    assert MODS["state"].git.__module__ != "conftest"


@pytest.mark.parametrize("args, want", [
    (("rev-parse", "HEAD"), ("", "rev-parse")),
    (("-C", "x", "-c", "a=b", "ls-files"), ("x", "ls-files")),
    (("-c", "core.quotepath=off", "diff", "--name-only"), ("", "diff")),
    (("--no-pager", "log"), None),  # 모르는 전역 옵션은 감싸지 않는다
    ((), None),
])
def test_git_dir_of(args, want, tmp_path):
    got = conftest.git_dir_of(tmp_path, args)
    assert (got if got is None else (str(got[0].relative_to(tmp_path)).replace(".", ""), got[1])) == want
