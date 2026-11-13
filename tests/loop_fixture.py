"""반복 루프 시험용 공용 부품 (test_state.py·test_loop.py).

- 임시 git 저장소: test_ladder.build로 예시 마트(mart_example)를 만들고 main에 커밋, origin 역할의 로컬 bare 저장소에
  올린 뒤 작업 브랜치로 옮긴다
- ladder_result 파일을 ts를 정해 직접 쓴다 (세기 시험용)
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for sub in ("scripts/log", "scripts/ladder", "scripts/loop"):
    sys.path.insert(0, str(ROOT / sub))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_ladder import MART, build  # noqa: E402

BRANCH = "week9/mart-example"


def git(root, *args):
    p = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, encoding="utf-8")
    assert p.returncode == 0, f"git {args}: {p.stderr}"
    return p.stdout


def make_repo(tmp_path, contract=None, checks=None):
    """작업 브랜치에 있는 깨끗한 저장소 (root, origin)."""
    root, origin = tmp_path / "repo", tmp_path / "origin.git"
    root.mkdir()
    # Windows에서는 git 호출과 파일 수가 시간을 좌우한다: 샘플 Hook 없이 만들고, 설정은 파일에 바로 쓴다
    git(root, "init", "-q", "--template=", "-b", "main")
    with (root / ".git" / "config").open("a", encoding="utf-8") as f:
        f.write("[user]\n\tname = tester\n\temail = tester@example.com\n[core]\n\tautocrlf = false\n")
    build(root, contract=contract, checks=checks)
    (root / "docs" / "architecture").mkdir(parents=True, exist_ok=True)
    (root / "docs" / "architecture" / "pii_columns.md").write_text("# 개인 식별 컬럼\n", encoding="utf-8")
    (root / "docs" / "requirements" / f"{MART}.md").write_text("# 요구서\n", encoding="utf-8")
    (root / ".gitignore").write_text("*.lock\n__pycache__/\n", encoding="utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "init")
    git(tmp_path, "clone", "-q", "--bare", "--template=", str(root), str(origin))
    with (root / ".git" / "config").open("a", encoding="utf-8") as f:
        f.write(f'[remote "origin"]\n\turl = {origin.as_posix()}\n\tfetch = +refs/heads/*:refs/remotes/origin/*\n')
    git(root, "checkout", "-q", "-b", BRANCH)
    return root, origin


def commit_all(root, message):
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", message)
    return git(root, "rev-parse", "HEAD").strip()


def ts(second):
    return f"2026-11-03T10:{second // 60:02d}:{second % 60:02d}+09:00"


def write_result(dev, task, n, verdict, second, error_type=None, halt_reason=None, version=1, mart=MART):
    """세기 시험용 ladder_result. 형식 검사는 하지 않는다."""
    rungs = [{"rung": "L0", "ds": None, "status": "pass", "metrics": {}, "error_type": None, "error_class": None}]
    if verdict == "reject":
        rungs.append({"rung": "L4", "ds": "2026-11-03", "status": "fail", "metrics": {"evidence": [{"x": 1}]},
                      "error_type": error_type, "error_class": "semantic"})
    data = {"task": task, "iteration": n, "contract_version": version, "request_kind": "new_build",
            "modules": {"expert": {"on": [], "version": None}}, "ts": ts(second), "bytes_total": 0,
            "rungs": [] if verdict == "halt" else rungs, "verdict": verdict, "halt_reason": halt_reason}
    path = Path(dev) / "ladder_results" / mart / f"{task}-v{version}-{n}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


def approval(stage, second, mart=MART, version=1, **extra):
    return {"id": "H-0001", "ts": ts(second), "mart": mart, "kind": "approval", "stage": stage,
            "contract_version": version, **extra}
