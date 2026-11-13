"""키트 설정 스크립트 시험 (scripts/setup/kit_setup.py). 바깥 명령(run)은 가짜로 바꾼다."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "setup"))
import kit_local  # noqa: E402
import kit_setup  # noqa: E402

PROJECT_ID = "my-proj-123"
SA = f"ai-builder@{PROJECT_ID}.iam.gserviceaccount.com"


class FakeRun:
    def __init__(self, account="", origin=False, user=SA):
        self.calls, self.account, self.origin, self.user = [], account, origin, user

    def __call__(self, args, env=None, capture=True):
        self.calls.append((list(args), dict(env or {}), capture))
        tail = list(args)[1:]
        if tail[:2] == ["auth", "list"]:
            return 0, self.account + "\n", ""
        if "remote" in args and "get-url" in args:
            return (0, "https://example.invalid/x.git\n", "") if self.origin else (2, "", "No such remote")
        if "query" in args:
            return 0, ("" if "--dry_run" in args else f"f0_\n{self.user}\n"), ""
        return 0, "", ""

    def commands(self):
        return [[Path(a[0]).name, *a[1:]] for a, _, _ in self.calls]


@pytest.fixture
def setup(tmp_path, monkeypatch):
    root = tmp_path / "team-repo"
    root.mkdir()
    (root / ".gitignore").write_text("out/\n", encoding="utf-8")
    monkeypatch.setattr(kit_setup.shutil, "which", lambda name: f"/sdk/{name}")
    fake = FakeRun()
    monkeypatch.setattr(kit_setup, "run", fake)
    cfg = tmp_path / "cfg"

    def go(*extra, fake_run=None):
        if fake_run is not None:
            monkeypatch.setattr(kit_setup, "run", fake_run)
        said = []
        code = kit_setup.main(["--root", str(root), "--config-dir", str(cfg), *extra], say=said.append)
        return code, said

    return root, cfg, fake, go


def test_full_setup(setup):
    root, cfg, fake, go = setup
    code, said = go("--project", PROJECT_ID, "--github", "someone")
    assert code == 0 and cfg.is_dir()
    cmds = fake.commands()
    assert ["gcloud", "config", "set", "project", PROJECT_ID] in cmds
    assert ["gcloud", "config", "set", "auth/impersonate_service_account", SA] in cmds
    login = [c for c in fake.calls if c[0][1:] == ["auth", "login"]]
    assert len(login) == 1 and login[0][2] is False  # 활성 계정이 없으면 사람이 로그인
    assert all(env.get("CLOUDSDK_CONFIG") == str(cfg.resolve()) for a, env, _ in fake.calls if "gcloud" in a[0] or "bq" in a[0])
    assert not any("keys" in c or "create-key" in " ".join(c) for c in cmds)  # 키 파일은 만들지 않는다
    queries = [c for c in cmds if "query" in c]
    assert len(queries) == 2 and "--dry_run" in queries[0] and "--dry_run" not in queries[1]
    assert all("--maximum_bytes_billed=524288000" in q for q in queries)
    assert ["git", "-C", str(root), "remote", "add", "origin", "https://github.com/someone/team-repo.git"] in cmds
    assert not any("push" in c for c in cmds)
    assert any("ai-builder 확인" in s for s in said)


def test_settings_local_env_is_merged(setup):
    root, cfg, fake, go = setup
    path = root / ".claude" / "settings.local.json"
    path.parent.mkdir()
    path.write_text(json.dumps({"permissions": {"allow": ["Bash(ls)"]}, "env": {"OTHER": "1", "CLOUDSDK_CONFIG": "old"}}),
                    encoding="utf-8")
    assert go("--project", PROJECT_ID, "--github", "")[0] == 0
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data == {"permissions": {"allow": ["Bash(ls)"]}, "env": {"OTHER": "1", "CLOUDSDK_CONFIG": str(cfg.resolve())}}


def test_settings_local_created_when_missing(setup):
    root, cfg, fake, go = setup
    assert go("--project", PROJECT_ID, "--github", "")[0] == 0
    data = json.loads((root / ".claude" / "settings.local.json").read_text(encoding="utf-8"))
    assert data == {"env": {"CLOUDSDK_CONFIG": str(cfg.resolve())}}


def test_broken_settings_local_is_not_overwritten(setup, capsys):
    root, cfg, fake, go = setup
    path = root / ".claude" / "settings.local.json"
    path.parent.mkdir()
    path.write_text("{broken", encoding="utf-8")
    assert go("--project", PROJECT_ID, "--github", "")[0] == 2
    assert path.read_text(encoding="utf-8") == "{broken"


def test_kit_local_file_and_gitignore(setup):
    root, cfg, fake, go = setup
    assert go("--project", PROJECT_ID, "--github", "someone")[0] == 0
    data = json.loads((root / kit_local.KIT_LOCAL).read_text(encoding="utf-8"))
    assert data == {"project": PROJECT_ID, "cloudsdk_config": str(cfg.resolve()), "github": "someone"}
    assert go("--project", PROJECT_ID, "--github", "")[0] == 0  # 두 번 실행해도 .gitignore 줄은 하나
    ignore = (root / ".gitignore").read_text(encoding="utf-8")
    assert ignore.startswith("out/\n") and ignore.split().count(kit_local.KIT_LOCAL) == 1
    assert json.loads((root / kit_local.KIT_LOCAL).read_text(encoding="utf-8"))["github"] is None
    env = {}
    assert kit_local.apply_env(root, env) == str(cfg.resolve())  # 새 창에서 루프·사다리가 쓰는 값


def test_repo_gitignore_has_kit_local():
    assert kit_local.KIT_LOCAL in (ROOT / ".gitignore").read_text(encoding="utf-8").split()


def test_logged_in_skips_login_and_existing_origin_kept(setup):
    root, cfg, fake, go = setup
    code, said = go("--project", PROJECT_ID, "--github", "someone", fake_run=FakeRun(account="human-account", origin=True))
    assert code == 0
    cmds = kit_setup.run.commands()
    assert ["gcloud", "auth", "login"] not in cmds
    assert not any("add" in c and "remote" in c for c in cmds)


def test_no_github_no_remote(setup):
    root, cfg, fake, go = setup
    assert go("--project", PROJECT_ID, "--github", "")[0] == 0
    assert not any("remote" in c for c in fake.commands())


def test_asks_project_and_github(setup, monkeypatch):
    root, cfg, fake, go = setup
    answers = iter([PROJECT_ID, ""])
    monkeypatch.setattr("builtins.input", lambda prompt: next(answers))
    assert go()[0] == 0
    assert json.loads((root / kit_local.KIT_LOCAL).read_text(encoding="utf-8"))["project"] == PROJECT_ID


@pytest.mark.parametrize("extra", [("--project", "Bad_ID"), ("--project", PROJECT_ID, "--github", "bad name")])
def test_bad_input_stops_before_commands(setup, extra):
    root, cfg, fake, go = setup
    assert go(*extra)[0] == 2
    assert fake.calls == [] and not (root / kit_local.KIT_LOCAL).exists()


def test_not_ai_builder_is_exit_1(setup):
    root, cfg, fake, go = setup
    code, said = go("--project", PROJECT_ID, "--github", "", fake_run=FakeRun(account="x", user="other-account"))
    assert code == 1 and any("ai-builder 아님" in s for s in said)


def test_missing_gcloud_stops(setup, monkeypatch):
    root, cfg, fake, go = setup
    monkeypatch.setattr(kit_setup.shutil, "which", lambda name: None)
    assert go("--project", PROJECT_ID, "--github", "")[0] == 2
    assert fake.calls == []


def test_windows_cmd_is_found(monkeypatch):
    monkeypatch.setattr(kit_setup.shutil, "which", lambda name: "C:/sdk/gcloud.cmd" if name == "gcloud.cmd" else None)
    assert kit_setup.find_tool("gcloud") == "C:/sdk/gcloud.cmd"


def test_commit_check_enabled_when_hook_exists(setup):
    root, _, fake, go = setup
    (root / ".githooks").mkdir()
    (root / ".githooks" / "pre-commit").write_text("#!/bin/sh\n", encoding="utf-8")
    code, said = go("--project", PROJECT_ID, "--github", "")
    assert code == 0
    assert ["git", "-C", str(root), "config", "core.hooksPath", ".githooks"] in fake.commands()
    assert any("커밋 검사" in s for s in said)


def test_commit_check_skipped_without_hook(setup):
    root, _, fake, go = setup
    assert go("--project", PROJECT_ID, "--github", "")[0] == 0
    assert not any("core.hooksPath" in c for c in fake.commands())
