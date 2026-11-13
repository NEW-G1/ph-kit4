"""related_tests.py 시험. 관련 시험 고르는 규칙과 pytest 1번 분량으로 합치기."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("related_tests", ROOT / ".claude" / "hooks" / "related_tests.py")
related = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(related)


def fake_project(tmp_path, tests):
    (tmp_path / "tests").mkdir()
    for name, text in tests.items():
        (tmp_path / "tests" / name).write_text(text, encoding="utf-8")
    return tmp_path


def test_related_by_name_and_import(tmp_path):
    p = fake_project(tmp_path, {
        "test_devlog.py": "x = 1\n",
        "test_by_path.py": 'SCRIPT = ROOT / "scripts" / "log" / "devlog.py"\n',
        "test_by_spec.py": 'spec_from_file_location("devlog", SCRIPT)\n',
        "test_by_import.py": "import devlog  # noqa\n",
        "test_by_from.py": "from log import devlog\n",
        "test_other.py": "import devlogger\nx = 'devlog_extra.py'\n",
    })
    args, target = related.related_tests("scripts/log/devlog.py", p)
    assert args == ["tests/test_by_from.py", "tests/test_by_import.py", "tests/test_by_path.py",
                    "tests/test_by_spec.py", "tests/test_devlog.py"]
    assert target == ", ".join(args)


def test_edited_test_file_runs_itself(tmp_path):
    p = fake_project(tmp_path, {"test_a.py": "", "test_b.py": "import test_a\n"})
    assert related.related_tests("tests/test_a.py", p) == (["tests/test_a.py"], "tests/test_a.py")


def test_dags_file_runs_l0_structure_tests(tmp_path):
    args, target = related.related_tests("dags/harness_daily.py", fake_project(tmp_path, {}))
    assert args == ["tests/test_l0_contract.py", "tests/test_ladder.py", "-k", "l0"] and target == "L0 구조 시험"


def test_l0_test_files_exist():
    assert all((ROOT / f).exists() for f in related.L0_TESTS)


def test_no_related_tests_returns_empty(tmp_path):
    p = fake_project(tmp_path, {"test_other.py": "import json\n"})
    assert related.related_tests("scripts/misc/lonely.py", p) == ([], None)


# ---------- select_tests: 여러 경로를 pytest 1번 분량으로 합친다 ----------

def test_select_removes_duplicates_and_lists_lonely(tmp_path):
    p = fake_project(tmp_path, {"test_a.py": "", "test_b.py": "import a\n"})
    args, target, lonely = related.select_tests(["scripts/a.py", "tests/test_a.py", "scripts/lonely.py"], p)
    assert args == ["tests/test_a.py", "tests/test_b.py"]
    assert target == "tests/test_a.py, tests/test_b.py" and lonely == ["scripts/lonely.py"]


def test_select_dags_only_keeps_rule_as_is(tmp_path):
    args, target, lonely = related.select_tests(["dags/harness_daily.py"], fake_project(tmp_path, {}))
    assert args == [*related.L0_TESTS, "-k", "l0"] and target == "L0 구조 시험" and lonely == []


def test_select_dags_with_other_file_does_not_filter_it_out(tmp_path):
    p = fake_project(tmp_path, {"test_a.py": ""})
    args, target, _ = related.select_tests(["dags/harness_daily.py", "scripts/a.py"], p)
    assert args == [*related.L0_TESTS, "tests/test_a.py", "-k", "l0 or test_a.py"]
    assert target == "L0 구조 시험, tests/test_a.py"


def test_select_dags_with_whole_l0_file_keeps_it_whole(tmp_path):
    p = fake_project(tmp_path, {"test_ladder.py": ""})
    args, _, _ = related.select_tests(["dags/harness_daily.py", "tests/test_ladder.py"], p)
    assert args == [*related.L0_TESTS, "-k", "l0 or test_ladder.py"]


def test_select_nothing_related(tmp_path):
    assert related.select_tests(["scripts/lonely.py"], fake_project(tmp_path, {})) == ([], "", ["scripts/lonely.py"])


# ---------- 명령줄 입구: 규칙은 select_tests 그대로, 전체 신호·비 .py·직전 실패·--run·--full ----------

import json  # noqa: E402
import os  # noqa: E402
import shlex  # noqa: E402
from datetime import datetime  # noqa: E402


class FakeRunner:
    def __init__(self, code=0):
        self.code, self.calls = code, []

    def __call__(self, cmd, **kw):
        self.calls.append((cmd, kw))
        return type("R", (), {"returncode": self.code})()


def cli(p, argv, capsys, runner=None, now=None):
    code = related.main(argv, runner=runner or FakeRunner(), project=p, now=now)
    out, err = capsys.readouterr()
    return code, out.strip(), err.strip().splitlines()


def write_lastfailed(p, nodes):
    cache = p / ".pytest_cache" / "v" / "cache"
    cache.mkdir(parents=True)
    (cache / "lastfailed").write_text(json.dumps({n: True for n in nodes}), encoding="utf-8")


def test_cli_args_equal_select_tests(tmp_path, capsys):
    p = fake_project(tmp_path, {"test_a.py": "", "test_b.py": "import a\n", "test_c.py": ""})
    paths = ["scripts/a.py", "tests/test_c.py", "dags/harness_daily.py"]
    code, out, err = cli(p, paths, capsys)
    assert code == 0
    assert shlex.split(out) == related.select_tests(paths, p)[0] + ["-q", "-n", "auto"]
    assert any(line.startswith("대상: ") for line in err)


def test_cli_conftest_means_full(tmp_path, capsys):
    p = fake_project(tmp_path, {"test_a.py": "", "conftest.py": ""})
    code, out, err = cli(p, ["scripts/a.py", "tests/conftest.py"], capsys)
    assert code == 0 and out == "tests/ -q -n auto"
    assert any(line.startswith("전체: tests/conftest.py") for line in err)


def test_cli_lonely_py_means_full(tmp_path, capsys):
    p = fake_project(tmp_path, {"test_a.py": ""})
    _, out, err = cli(p, ["scripts/a.py", "scripts/lonely.py"], capsys)
    assert out == "tests/ -q -n auto"
    assert any(line.startswith("전체: ") and "scripts/lonely.py" in line for line in err)


def test_cli_non_py_file_selects_tests_mentioning_its_name(tmp_path, capsys):
    p = fake_project(tmp_path, {"test_dash.py": 'DESIGN = ROOT / "docs" / "design" / "DESIGN.md"\n', "test_x.py": ""})
    _, out, err = cli(p, ["docs/design/DESIGN.md"], capsys)
    assert shlex.split(out) == ["tests/test_dash.py", "-q", "-n", "auto"]
    assert any("DESIGN.md: 이름을 언급하는 시험 tests/test_dash.py" in line for line in err)


def test_cli_non_py_file_without_tests_is_skipped_not_full(tmp_path, capsys):
    p = fake_project(tmp_path, {"test_x.py": ""})
    runner = FakeRunner()
    code, out, err = cli(p, ["--run", "docs/notes.md"], capsys, runner=runner)
    assert code == 0 and out == "" and runner.calls == []
    assert err == [f"docs/notes.md: {related.NOT_SELECTABLE}", related.NOTHING]
    assert not any(line.startswith("전체") for line in err)


def test_cli_non_py_and_py_are_merged(tmp_path, capsys):
    p = fake_project(tmp_path, {"test_a.py": "", "test_cfg.py": "x = 'harness_config.json'\n"})
    _, out, _ = cli(p, ["scripts/a.py", "dags/harness_config.json"], capsys)
    assert shlex.split(out) == ["tests/test_a.py", "tests/test_cfg.py", "-q", "-n", "auto"]


def test_cli_adds_existing_last_failed_files_once(tmp_path, capsys):
    p = fake_project(tmp_path, {"test_a.py": "def test_z():\n    pass\n",
                                "test_f.py": "def test_one():\n    pass\n\n\ndef test_two():\n    pass\n",
                                "test_renamed.py": "def test_old_name():\n    pass\n"})
    write_lastfailed(p, ["tests/test_f.py::test_one", "tests/test_f.py::test_two", "tests/test_gone.py::test_x",
                         "tests/test_renamed.py::test_old_name", "scripts/test_outside.py::test_y",
                         "tests/test_a.py::test_z"])
    _, out, err = cli(p, ["scripts/a.py"], capsys)
    assert shlex.split(out) == ["tests/test_a.py", "tests/test_f.py", "tests/test_renamed.py", "-q", "-n", "auto"]
    assert "직전 실패: tests/test_f.py, tests/test_renamed.py, tests/test_a.py" in err


def test_last_failed_drops_tests_that_no_longer_exist(tmp_path):
    p = fake_project(tmp_path, {"test_a.py": "def test_new_name():\n    pass\n"})
    write_lastfailed(p, ["tests/test_a.py::test_old_name", "tests/test_a.py::test_old_name[click]"])
    assert related.last_failed_files(p) == []


def test_last_failed_keeps_parametrized_and_class_methods(tmp_path):
    p = fake_project(tmp_path, {
        "test_a.py": "@pytest.mark.parametrize('x', ['click'])\ndef test_reload(x):\n    pass\n",
        "test_b.py": "class TestX:\n    def test_m(self):\n        pass\n",
    })
    write_lastfailed(p, ["tests/test_a.py::test_reload[click]", "tests/test_b.py::TestX::test_m"])
    assert related.last_failed_files(p) == ["tests/test_a.py", "tests/test_b.py"]


def test_last_failed_mixed_keeps_only_living(tmp_path):
    p = fake_project(tmp_path, {"test_a.py": "def test_alive():\n    pass\n", "test_b.py": "def test_other():\n    pass\n"})
    write_lastfailed(p, ["tests/test_b.py::test_gone[x]", "tests/test_a.py::test_gone",
                         "tests/test_a.py::test_alive[click]"])
    assert related.last_failed_files(p) == ["tests/test_a.py"]


def test_cli_last_failed_missing_or_broken_is_skipped(tmp_path, capsys):
    p = fake_project(tmp_path, {"test_a.py": ""})
    _, out, err = cli(p, ["scripts/a.py"], capsys)
    assert out == "tests/test_a.py -q -n auto" and not any("직전 실패" in line for line in err)
    cache = p / ".pytest_cache" / "v" / "cache"
    cache.mkdir(parents=True)
    (cache / "lastfailed").write_text("{broken", encoding="utf-8")
    code, out, err = cli(p, ["scripts/a.py"], capsys)
    assert code == 0 and out == "tests/test_a.py -q -n auto" and not any("직전 실패" in line for line in err)


def test_cli_last_failed_with_dags_joins_k_filter(tmp_path, capsys):
    p = fake_project(tmp_path, {"test_f.py": "def test_one():\n    pass\n",
                                "test_ladder.py": "def test_not_l0():\n    pass\n"})
    write_lastfailed(p, ["tests/test_f.py::test_one", "tests/test_ladder.py::test_not_l0"])
    _, out, _ = cli(p, ["dags/harness_daily.py"], capsys)
    assert shlex.split(out) == [*related.L0_TESTS, "tests/test_f.py", "-k", "l0 or test_f.py or test_ladder.py",
                                "-q", "-n", "auto"]


def test_cli_quotes_k_expression_as_one_arg(tmp_path, capsys):
    p = fake_project(tmp_path, {"test_a.py": ""})
    _, out, _ = cli(p, ["dags/harness_daily.py", "scripts/a.py"], capsys)
    assert '-k "l0 or test_a.py"' in out
    assert shlex.split(out)[shlex.split(out).index("-k") + 1] == "l0 or test_a.py"


def test_cli_run_uses_arg_list_and_returns_exit_code(tmp_path, capsys):
    p = fake_project(tmp_path, {"test_a.py": ""})
    runner = FakeRunner(code=3)
    code, _, _ = cli(p, ["--run", "dags/harness_daily.py", "scripts/a.py"], capsys, runner=runner)
    assert code == 3 and len(runner.calls) == 1
    cmd, kw = runner.calls[0]
    assert isinstance(cmd, list) and cmd[1:3] == ["-m", "pytest"] and not kw.get("shell")
    assert cmd[3:] == [*related.L0_TESTS, "tests/test_a.py", "-k", "l0 or test_a.py", "-q", "-n", "auto"]
    assert kw["cwd"] == p


def test_cli_full_prints_junit_and_rf(tmp_path, capsys):
    now = datetime(2026, 11, 11, 9, 5, 7)
    code, out, err = cli(fake_project(tmp_path, {}), ["--full"], capsys, now=now)
    assert code == 0
    assert shlex.split(out) == ["tests/", "-q", "-n", "auto", "-rf",
                                f"--junitxml=.claude/state/junit/full-{now:%Y%m%d-%H%M%S}.xml"]
    assert out.endswith("-20261111-090507.xml")  # 날짜-시각 (키트 검사가 하이픈+숫자 이름을 프로젝트 ID로 보지 않게 나눠 씀)
    assert err == ["전체: --full"]


def test_cli_full_run_keeps_latest_five_by_mtime(tmp_path, capsys):
    p = fake_project(tmp_path, {})
    folder = p / ".claude" / "state" / "junit"
    folder.mkdir(parents=True)
    names = [f"full-2026111{i}-000000.xml" for i in range(6)]  # 이름순 0..5
    for age, name in zip((1, 6, 2, 5, 3, 4), names):  # 수정 시각은 이름순과 다르게(값이 클수록 오래됨)
        (folder / name).write_text("", encoding="utf-8")
        os.utime(folder / name, (1_000_000 - age * 100, 1_000_000 - age * 100))
    (folder / "other.xml").write_text("", encoding="utf-8")
    (folder / "keep.txt").write_text("", encoding="utf-8")
    runner = FakeRunner(code=1)
    now = datetime(2026, 11, 11, 23, 0, 0)
    code, _, _ = cli(p, ["--full", "--run"], capsys, runner=runner, now=now)
    assert code == 1
    cmd, _ = runner.calls[0]
    assert "-rf" in cmd and "-n" in cmd and f"--junitxml=.claude/state/junit/full-{now:%Y%m%d-%H%M%S}.xml" in cmd
    left = sorted(f.name for f in folder.iterdir())
    # 가장 오래된 둘(age 6 = names[1], age 5 = names[3])을 지워 남은 4개 + 새 파일 = 5개
    assert left == sorted([names[0], names[2], names[4], names[5], "other.xml", "keep.txt"])


def test_cli_needs_paths_or_full(tmp_path, capsys):
    import pytest
    p = fake_project(tmp_path, {})
    for argv in ([], ["--full", "scripts/a.py"]):
        with pytest.raises(SystemExit) as e:
            related.main(argv, runner=FakeRunner(), project=p)
        assert e.value.code == 2
    capsys.readouterr()
