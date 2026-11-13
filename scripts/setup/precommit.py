"""git pre-commit: 커밋에 들어가는 contract를 L0로 검사한다 (결정 80). kit_setup.py가 core.hooksPath를 .githooks로 켠다.

  .githooks/pre-commit 이 python scripts/setup/precommit.py 를 부른다

- 대상: 스테이징된 docs/requirements/*.contract.json (이름이 _로 시작하는 양식은 뺀다). 작업 트리가 아니라 커밋될 내용을 본다
- 검사: scripts/ladder/l0_contract.py의 check_contract (contract만, SQL 폴더는 보지 않는다). 판정 규칙은 그대로다
- 실패하면 오류와 다음 할 일을 출력하고 종료 코드 1(커밋을 막는다). 대상이 없거나 모두 통과하면 0
- git·Python 문제로 검사하지 못하면 경고만 내고 커밋은 막지 않는다(루프가 시작할 때 L0를 다시 본다)
"""
import json
import subprocess
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / "scripts" / "ladder"))


def staged_contracts(root):
    p = subprocess.run(["git", "-C", str(root), "diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z"],
                       capture_output=True)
    if p.returncode != 0:
        return None
    names = [n for n in p.stdout.decode("utf-8", "replace").split("\0") if n]
    return [n for n in names if n.startswith("docs/requirements/") and n.count("/") == 2
            and n.endswith(".contract.json") and not Path(n).name.startswith("_")]


def staged_text(root, name):
    p = subprocess.run(["git", "-C", str(root), "show", f":{name}"], capture_output=True)
    return p.stdout.decode("utf-8") if p.returncode == 0 else None


def check(root, name, check_contract):
    """오류 목록. 통과면 []."""
    text = staged_text(root, name)
    if text is None:
        return ["커밋될 내용을 읽지 못함"]
    try:
        contract = json.loads(text)
    except json.JSONDecodeError as e:
        return [f"JSON 형식 오류: {e.msg} (줄 {e.lineno})"]
    result = check_contract(contract)
    return [] if result["status"] == "pass" else list(result["metrics"].get("errors") or ["형식 검사 실패"])


def main(root=PROJECT, out=print):
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    names = staged_contracts(root)
    if not names:
        return 0
    try:
        import l0_contract
    except Exception as e:  # noqa: BLE001  검사 도구가 깨졌으면 막지 않는다(루프가 시작할 때 다시 본다)
        out(f"경고: contract 형식 검사를 하지 못함 ({e.__class__.__name__}). 커밋은 막지 않는다")
        return 0
    failed = False
    for name in names:
        errors = check(root, name, l0_contract.check_contract)
        if errors:
            failed = True
            out(f"커밋을 막음: {name} 형식 검사(L0) 실패")
            for e in errors[:20]:
                out(f"  - {e}")
    if failed:
        out("Claude Code에 위 오류 줄을 붙여 넣고 \"이 오류를 고쳐 줘\"라고 한 뒤 다시 git add, git commit 한다")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
