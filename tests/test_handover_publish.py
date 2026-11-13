"""scripts/handover/publish.py 시험 (03 §6.7 3·4단계). 임시 git 저장소에만 쓴다. docs/handover/ 실제 폴더는 건드리지 않는다."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "handover"))
import make_facts  # noqa: E402
import publish  # noqa: E402
from test_handover import (MART, PROJECT_ID, commit_file, dev, draft_path, fill_explanations, l6_post, make,  # noqa: E402,F401
                           repo, settle)


def run(repo, dev, *extra):
    return publish.main(["--mart", MART, "--draft", str(draft_path(dev)), "--root", str(repo), *extra])


def out_file(repo):
    return repo / "docs" / "handover" / f"{MART}.md"


@pytest.fixture
def ready(repo, dev):
    """설명 칸을 채운 최신 초안."""
    settle(repo)
    make(repo, dev)
    fill_explanations(dev)
    return draft_path(dev)


def test_stale_draft_writes_nothing(repo, dev, ready, capsys):
    commit_file(repo, "dags/sql/stg/stg_example.sql", "SELECT 2\n")
    assert run(repo, dev) == 2
    assert "halt input_invalid: " in capsys.readouterr().err
    assert not out_file(repo).exists()


def test_empty_slot_writes_nothing(repo, dev, capsys):
    make(repo, dev)
    assert run(repo, dev) == 2
    assert "초안 미완성: 설명 칸 1, 6, 7절" in capsys.readouterr().err
    assert not out_file(repo).exists()


def test_one_empty_slot_is_incomplete(repo, dev, ready, capsys):
    parts = make_facts.split_draft(ready.read_text(encoding="utf-8"))
    parts[4] = make_facts.AI_SLOT + "\n\n"
    ready.write_text("".join(parts), encoding="utf-8", newline="\n")
    assert run(repo, dev) == 2 and "설명 칸 6절" in capsys.readouterr().err


def test_publish_changes_notice_and_keeps_body(repo, dev, ready):
    assert run(repo, dev) == 0
    head = make_facts.git(repo, "rev-parse", "--short", "HEAD").strip()
    label = f".dev/handover/{ready.relative_to(dev / 'handover').as_posix()}"
    text = out_file(repo).read_text(encoding="utf-8")
    draft = ready.read_text(encoding="utf-8")
    assert text.splitlines()[2] == f"> 결재된 인수인계 문서. 원본 초안: {label}, 반영 커밋: {head}"
    assert "사실 칸(2·3·4·5·8)은" not in text and "설명 칸(1·6·7)만" not in text
    # 안내문 2줄이 1줄로 바뀐 것 말고는 초안과 같다
    assert [x for x in text.splitlines() if not x.startswith("> ")] == \
        [x for x in draft.splitlines() if not x.startswith("> ")]
    assert make_facts.read_stamp(text) == make_facts.read_stamp(draft)


def test_om_sentence_once_without_l6(repo, dev, ready):
    assert run(repo, dev) == 0
    section = publish.between(out_file(repo).read_text(encoding="utf-8"), make_facts.H3, make_facts.H4)
    assert section.count("OM 리니지") == 1 and "OM 리니지 링크는 결재 후 L6 통과 시" in section


def test_om_sentence_once_with_l6(repo, dev):
    l6_post(dev, "pass")
    settle(repo)
    make(repo, dev)
    fill_explanations(dev)
    assert run(repo, dev) == 0
    section = publish.between(out_file(repo).read_text(encoding="utf-8"), make_facts.H3, make_facts.H4)
    assert section.count("OM 리니지") == 1
    assert "OM 리니지: OM 서비스 Test_OM에서 등록 확인 (L6 통과, post-1)" in section


def test_overwrite_reports_changed_lines(repo, dev, ready, capsys):
    assert run(repo, dev) == 0
    path = out_file(repo)
    path.write_text(path.read_text(encoding="utf-8").replace("요약 문장", "옛 요약"), encoding="utf-8", newline="\n")
    capsys.readouterr()
    assert run(repo, dev) == 0
    assert "바뀐 줄 2" in capsys.readouterr().out
    assert "옛 요약" not in path.read_text(encoding="utf-8")


def test_out_option(repo, dev, ready, tmp_path):
    target = tmp_path / "elsewhere" / "x.md"
    assert run(repo, dev, "--out", str(target)) == 0
    assert target.exists() and not out_file(repo).exists()


def test_pr_body_prints_only(repo, dev, ready, capsys):
    capsys.readouterr()
    assert run(repo, dev, "--pr-body") == 0
    text = capsys.readouterr().out
    assert not out_file(repo).exists()
    assert "요약 문장 | 그대로" in text
    assert "| L4 정합성 | 통과 |" in text and "| R-0001 | 1 |" in text
    assert "- contract_version: 1" in text and "- 기준 커밋: " in text
    assert "운영 **방법**" not in text and "| 역할 | 호출 수 |" not in text


def test_pr_body_stops_when_stale(repo, dev, ready, capsys):
    commit_file(repo, f"docs/requirements/{MART}.md", "# 고침\n")
    capsys.readouterr()
    assert run(repo, dev, "--pr-body") == 2
    assert capsys.readouterr().out == ""


def test_output_hides_project_and_account(repo, dev, ready, capsys):
    parts = make_facts.split_draft(ready.read_text(encoding="utf-8"))
    parts[2] = f"Table {PROJECT_ID}:ai_dev.t 담당 ai-builder@{PROJECT_ID}.iam.gserviceaccount.com\n\n"
    ready.write_text("".join(parts), encoding="utf-8", newline="\n")
    assert run(repo, dev) == 0
    capsys.readouterr()
    assert run(repo, dev, "--pr-body") == 0
    for text in (out_file(repo).read_text(encoding="utf-8"), capsys.readouterr().out):
        assert PROJECT_ID not in text and "ai-builder@" not in text
        assert "<프로젝트>:ai_dev.t" in text and "<계정>" in text


def test_missing_draft(repo, dev, capsys):
    assert run(repo, dev) == 2
    assert "반영하지 못함" in capsys.readouterr().err
