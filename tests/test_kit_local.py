"""키트 편의 시험: .kit_local.json의 CLOUDSDK_CONFIG 자동 적용, --mart 자동 선택(0·1·2개) (scripts/setup/kit_local.py)."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
for sub in ("scripts/setup", "scripts/ladder", "scripts/loop", "scripts/deliverables", "scripts/cards"):
    sys.path.insert(0, str(ROOT / sub))
import common  # noqa: E402
import flow_diagram  # noqa: E402
import kit_local  # noqa: E402
import make_cards  # noqa: E402
import run_loop  # noqa: E402
import table_spec  # noqa: E402
import unit_test_report  # noqa: E402

CFG = "C:/Users/someone/.gcp/ai-builder-kit-config"


def local(root, **data):
    (Path(root) / kit_local.KIT_LOCAL).write_text(json.dumps(data), encoding="utf-8")


def contracts(root, *marts):
    req = Path(root) / "docs" / "requirements"
    req.mkdir(parents=True, exist_ok=True)
    (req / "_template.contract.json").write_text("{}", encoding="utf-8")
    for mart in marts:
        (req / f"{mart}.contract.json").write_text("{}", encoding="utf-8")
    return Path(root)


# ---------- CLOUDSDK_CONFIG ----------

def test_apply_env_sets_missing_value(tmp_path):
    local(tmp_path, project="my-proj-123", cloudsdk_config=CFG, github=None)
    env = {}
    assert kit_local.apply_env(tmp_path, env) == CFG
    assert env == {"CLOUDSDK_CONFIG": CFG}


def test_apply_env_keeps_existing_value(tmp_path):
    local(tmp_path, cloudsdk_config=CFG)
    env = {"CLOUDSDK_CONFIG": "D:/mine"}
    assert kit_local.apply_env(tmp_path, env) is None
    assert env == {"CLOUDSDK_CONFIG": "D:/mine"}


@pytest.mark.parametrize("text", [None, "not json", "[]", json.dumps({"cloudsdk_config": ""})])
def test_apply_env_without_usable_file(tmp_path, text):
    if text is not None:
        (tmp_path / kit_local.KIT_LOCAL).write_text(text, encoding="utf-8")
    env = {}
    assert kit_local.apply_env(tmp_path, env) is None and env == {}


def test_common_apply_kit_local_uses_repo_root(monkeypatch, tmp_path):
    seen = {}
    monkeypatch.setattr(kit_local, "apply_env", lambda root, environ: seen.update(root=root, environ=environ) or "x")
    env = {}
    assert common.apply_kit_local(env) == "x"
    assert seen == {"root": common.PROJECT, "environ": env}


@pytest.mark.parametrize("rel", ["scripts/loop/run_loop.py", "scripts/ladder/run_ladder.py", "scripts/ladder/l6_om.py",
                                 ".claude/hooks/after_edit.py"])
def test_entry_points_apply_before_main(rel):
    """명령줄 진입점은 main(Bq 생성) 전에 적용한다. 인증 확인(check_auth)은 그대로 둔다."""
    text = (ROOT / rel).read_text(encoding="utf-8")
    block = text[text.index('if __name__ == "__main__":'):]
    assert block.index("common.apply_kit_local()") < block.index("main()")


def test_check_auth_still_refuses_without_config():
    with pytest.raises(common.InfraError, match="CLOUDSDK_CONFIG"):
        common.Bq(runner=lambda *a: (0, "", ""), env={}).check_auth()


# ---------- --mart 자동 선택 ----------

def test_pick_mart_given_wins(tmp_path):
    assert kit_local.pick_mart(contracts(tmp_path, "a", "b"), "b") == "b"


def test_pick_mart_one(tmp_path, capsys):
    assert kit_local.pick_mart(contracts(tmp_path, "mart_one"), None) == "mart_one"
    assert "마트: mart_one (자동 선택)" in capsys.readouterr().out


@pytest.mark.parametrize("marts", [(), ("mart_a", "mart_b")])
def test_pick_mart_zero_or_many(tmp_path, capsys, marts):
    assert kit_local.pick_mart(contracts(tmp_path, *marts), None) is None
    err = capsys.readouterr().err
    assert "--mart" in err and all(m in err for m in marts) and "_template" not in err


@pytest.mark.parametrize("mod", [flow_diagram, table_spec, unit_test_report, make_cards])
@pytest.mark.parametrize("marts", [(), ("mart_a", "mart_b")])
def test_scripts_exit_2_without_single_mart(tmp_path, capsys, mod, marts):
    contracts(tmp_path, *marts)
    assert mod.main(["--root", str(tmp_path)]) == 2
    assert "--mart" in capsys.readouterr().err


@pytest.mark.parametrize("mod", [flow_diagram, table_spec, unit_test_report, make_cards])
def test_scripts_pick_single_mart(tmp_path, capsys, mod):
    contracts(tmp_path, "mart_one")
    mod.main(["--root", str(tmp_path), "--check"])  # 도장 검사는 실패해도 된다. 마트를 고르는지만 본다
    out = capsys.readouterr()
    assert "마트: mart_one (자동 선택)" in out.out
    assert "--mart <마트>를 준다" not in out.err


class NoAuthBq:
    def check_auth(self):
        raise common.InfraError("CLOUDSDK_CONFIG가 없음")


@pytest.mark.parametrize("marts, picked", [(("mart_one",), True), (("mart_a", "mart_b"), False), ((), False)])
def test_run_loop_mart_optional(tmp_path, capsys, marts, picked):
    contracts(tmp_path, *marts)
    assert run_loop.main(["--root", str(tmp_path)], bq=NoAuthBq(), environ={}) == 2
    out = capsys.readouterr()
    assert ("마트: mart_one (자동 선택)" in out.out) is picked
    assert ("인증" in out.err) is picked  # 고르면 다음 확인(인증)으로 간다
