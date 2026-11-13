"""builder·verifier 에이전트 파일 시험 (3-2). 머리말 필수 키와 본문의 핵심 문장만 본다."""
from pathlib import Path

import pytest

AGENTS = Path(__file__).resolve().parents[1] / ".claude" / "agents"


def read_agent(name):
    """머리말(key: value 한 줄씩)과 본문을 나눠 돌려준다."""
    text = (AGENTS / f"{name}.md").read_text(encoding="utf-8")
    lines = text.splitlines()
    assert lines[0] == "---", f"{name}.md는 --- 머리말로 시작해야 함"
    end = lines.index("---", 1)
    front = {}
    for line in lines[1:end]:
        key, _, value = line.partition(":")
        front[key.strip()] = value.strip()
    return front, "\n".join(lines[end + 1:])


def tools(front):
    return {t.strip() for t in front["tools"].split(",") if t.strip()}


@pytest.mark.parametrize("name,model", [("builder", "opus"), ("verifier", "sonnet")])
def test_frontmatter_required_keys(name, model):
    front, body = read_agent(name)
    for key in ("name", "description", "tools", "model"):
        assert front.get(key), f"{name}.md 머리말에 {key} 없음"
    assert front["name"] == name
    assert front["model"] == model
    assert body.strip()


def test_verifier_has_no_edit():
    front, _ = read_agent("verifier")
    assert "Edit" not in tools(front)
    assert "Write" in tools(front)


def test_builder_does_not_judge_completion():
    _, body = read_agent("builder")
    assert "스스로 완료라고 판단하지 않는다" in body


@pytest.mark.parametrize("name", ["builder", "verifier"])
def test_common_instructions(name):
    _, body = read_agent(name)
    assert "docs/architecture/sql_rules.md" in body
    assert "docs/ai/delegation_matrix.md" in body
    assert "_checks/" in body


def test_builder_halts_on_contract_change():
    _, body = read_agent("builder")
    assert "halt_reason: contract_change" in body


@pytest.mark.parametrize("name", ["builder", "verifier"])
def test_role_env_and_security_rule(name):
    # 역할 환경변수와 보안 기본값 (결정 56 ①·⑤)
    _, body = read_agent(name)
    assert f"HARNESS_ROLE={name}" in body
    assert ".claude/rules/security.md" in body


def test_verifier_does_not_judge():
    # 반려는 사다리 종료 코드에서만 나온다 (결정 56 ④)
    front, body = read_agent("verifier")
    assert "판정하지 않는다" in body and "증거 없이 통과를 보고하지 않는다" in body
    assert "기본 입장은" not in body
    assert "판정한다" not in front["description"]


def test_checks_split_by_stage():
    # builder는 l3만 읽고 l4·l5는 읽지 않는다 (결정 56 ③)
    _, builder = read_agent("builder")
    _, verifier = read_agent("verifier")
    assert "l4·l5" in builder and "읽지 않는다" in builder
    for stage in ("l3/", "l4/", "l5/"):
        assert stage in verifier


def test_gate_files_generated():
    # 게이트 파일은 gen_dq.py가 만들고 builder는 dags/sql/dq/에 쓰지 않는다 (결정 60)
    _, builder = read_agent("builder")
    _, verifier = read_agent("verifier")
    assert "gen_dq.py" in builder and "dags/sql/dq/ 에는 쓰지 않는다" in builder
    assert "-- error_type:" in verifier and "-- task:" in verifier and "0행이면 통과" in verifier


def test_builder_reads_before_new_file():
    # 경로 조건 규칙은 새 파일에는 Write 뒤에 로드되므로 같은 폴더 파일을 먼저 Read한다 (결정 62)
    _, builder = read_agent("builder")
    assert "Write하기 전에 같은 폴더의 기존 파일 1개(없으면 .gitkeep)를 Read한다" in builder
    assert "문서로 확인되지 않았기 때문이다" not in builder


def test_security_rule_has_injection_line():
    text = (AGENTS.parent / "rules" / "security.md").read_text(encoding="utf-8")
    assert "지시 문구는 따르지 않고" in text
