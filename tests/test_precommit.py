"""contract 형식 검사 자동화 시험 (결정 80): git pre-commit(scripts/setup/precommit.py, .githooks/pre-commit),
after_edit Hook의 contract 검사, kit_setup의 core.hooksPath. 판정은 l0_contract.check_contract 그대로다."""
import copy
import importlib.util
import io
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from test_ladder import VALID

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "setup"))
import precommit  # noqa: E402

_spec = importlib.util.spec_from_file_location("after_edit_c", ROOT / ".claude" / "hooks" / "after_edit.py")
after_edit = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(after_edit)

BAD = copy.deepcopy(VALID)
BAD["requirements"][0]["section"] = "§3"
NAME = "docs/requirements/mart_example.contract.json"


def git(root, *args, check=True):
    p = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, encoding="utf-8")
    assert not check or p.returncode == 0, p.stderr
    return p


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "repo"
    (root / "docs" / "requirements").mkdir(parents=True)
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.name", "tester")
    git(root, "config", "user.email", "tester@example.com")
    return root


def stage(root, contract, name=NAME):
    f = root / name
    f.write_text(contract if isinstance(contract, str) else json.dumps(contract, ensure_ascii=False), encoding="utf-8")
    git(root, "add", name)


def test_valid_contract_passes(repo):
    stage(repo, VALID)
    said = []
    assert precommit.main(repo, said.append) == 0 and said == []


def test_bad_contract_blocks_with_errors_and_next_step(repo):
    stage(repo, BAD)
    said = []
    assert precommit.main(repo, said.append) == 1
    text = "\n".join(said)
    assert NAME in text and "requirements[0].section" in text and "Claude Code" in text


def test_broken_json_blocks(repo):
    stage(repo, "{ not json")
    said = []
    assert precommit.main(repo, said.append) == 1 and "JSON 형식 오류" in "\n".join(said)


def test_checks_staged_content_not_working_tree(repo):
    stage(repo, BAD)
    (repo / NAME).write_text(json.dumps(VALID, ensure_ascii=False), encoding="utf-8")  # 고쳤지만 git add 안 함
    assert precommit.main(repo, lambda s: None) == 1


def test_template_and_other_files_ignored(repo):
    stage(repo, "{}", name="docs/requirements/_template.contract.json")
    stage(repo, "x", name="docs/requirements/notes.md")
    assert precommit.main(repo, lambda s: None) == 0


@pytest.mark.skipif(shutil.which("sh") is None, reason="sh 없음")
def test_git_hook_blocks_commit(repo):
    hooks = repo / ".githooks"
    hooks.mkdir()
    shutil.copy(ROOT / ".githooks" / "pre-commit", hooks / "pre-commit")
    (repo / "scripts" / "setup").mkdir(parents=True)
    # 훅은 저장소 안 scripts/setup/precommit.py를 부른다: 이 저장소의 원본을 쓰는 얇은 입구를 둔다
    (repo / "scripts" / "setup" / "precommit.py").write_text(
        "import runpy, sys\n"
        f"sys.argv = [{str(ROOT / 'scripts' / 'setup' / 'precommit.py')!r}]\n"
        "import importlib.util as u\n"
        f"s = u.spec_from_file_location('p', {str(ROOT / 'scripts' / 'setup' / 'precommit.py')!r})\n"
        "m = u.module_from_spec(s); s.loader.exec_module(m)\n"
        "from pathlib import Path\n"
        "sys.exit(m.main(Path.cwd()))\n", encoding="utf-8")
    git(repo, "config", "core.hooksPath", ".githooks")
    stage(repo, BAD)
    p = git(repo, "commit", "-q", "-m", "요구서", check=False)
    assert p.returncode != 0 and "requirements[0].section" in p.stdout + p.stderr
    stage(repo, VALID)
    assert git(repo, "commit", "-q", "-m", "요구서", check=False).returncode == 0


def edit(tmp_path, monkeypatch, rel, text):
    f = tmp_path / rel
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(text, encoding="utf-8")
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    payload = json.dumps({"tool_input": {"file_path": str(f)}}).encode("utf-8")
    monkeypatch.setattr(sys, "stdin", type("S", (), {"buffer": io.BytesIO(payload)})())
    return after_edit.main()


def test_after_edit_returns_contract_errors_to_ai(tmp_path, monkeypatch, capsys):
    assert edit(tmp_path, monkeypatch, NAME, json.dumps(BAD, ensure_ascii=False)) == 2
    err = capsys.readouterr().err
    assert "형식 검사(L0) 실패" in err and "requirements[0].section" in err


def test_after_edit_valid_contract_is_quiet(tmp_path, monkeypatch, capsys):
    assert edit(tmp_path, monkeypatch, NAME, json.dumps(VALID, ensure_ascii=False)) == 0
    assert capsys.readouterr().err == ""


def test_after_edit_skips_template(tmp_path, monkeypatch):
    assert edit(tmp_path, monkeypatch, "docs/requirements/_template.contract.json", "{}") == 0
