"""결재된 인수인계 초안을 docs/handover/ 문서와 PR 본문 내용으로 낸다 (03 §6.7 3·4단계). 머지 후 사람이 실행한다.

  python scripts/handover/publish.py --mart <마트> --draft <.dev/handover/...md> [--out docs/handover/<마트>.md] [--pr-body]

- 초안이 낡았으면(make_facts --check와 같은 검사) 또는 설명 칸(1·6·7)이 빈 자리면 종료 코드 2로 멈추고 아무것도 쓰지 않는다
- 맨 위 안내문만 바꾸고 본문은 그대로 둔다. 3·8절의 OM 문구는 make_facts 출력이다 (L6 상태별, 주소는 넣지 않는다)
- --pr-body: 파일을 쓰지 않고 1절 한 줄 요약, 4절 검증 결과, 5절 반려 이력, 도장을 표준 출력으로만 낸다. GitHub에 올리지 않는다
- 데이터 값은 넣지 않는다. 프로젝트 ID·계정은 make_facts.scrub로 가린다
- AI는 이 스크립트로 docs/handover/를 쓰지 않는다 (CLAUDE.md §2, .claude/rules/handover.md)
"""
import argparse
import difflib
import re
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / "scripts" / "handover"))
import make_facts  # noqa: E402

NOTICE =re.compile(r"(?:^> .*\n)+", re.M)


def between(text, start, end):
    """start 제목 다음 줄부터 end 제목 앞까지."""
    a = text.find(f"\n{start}\n")
    b = text.find(f"\n{end}\n", a + 1)
    if a < 0 or b < 0:
        raise make_facts.FactsError(f"초안에 제목이 없음: {start if a < 0 else end}")
    return text[a + len(start) + 2:b + 1].strip()


def draft_label(root, draft):
    try:
        return Path(draft).resolve().relative_to(Path(root).resolve()).as_posix()
    except ValueError:
        return Path(draft).as_posix()


def published(text, label, head):
    """docs/handover/ 문서 내용. 안내문만 바꾼다."""
    notice = f"> 결재된 인수인계 문서. 원본 초안: {label}, 반영 커밋: {head}\n"
    parts = make_facts.split_draft(text)
    parts[1] = NOTICE.sub(lambda _: notice, parts[1], count=1)
    return make_facts.scrub("".join(parts))


def pr_body(text, mart):
    stamp = make_facts.read_stamp(text)
    return make_facts.scrub("\n".join([
        f"## 인수인계 — {mart}", "",
        between(text, make_facts.H1, make_facts.H2), "",
        "### 검증 결과", "", between(text, make_facts.H4, make_facts.H_COST), "",
        "### 반려 이력", "", between(text, make_facts.H5, make_facts.H6), "",
        "### 도장", "", *(f"- {label}: {stamp[label]}" for label in make_facts.STAMP_LABELS), "",
    ]))


def changed_lines(old, new):
    diff = difflib.unified_diff(old.splitlines(), new.splitlines(), n=0, lineterm="")
    return sum(1 for line in diff if line[:1] in "+-" and line[:3] not in ("+++", "---"))


def parse_args(argv):
    p = argparse.ArgumentParser(description="인수인계 docs/handover 반영 (03 §6.7, 머지 후 사람이 실행)")
    p.add_argument("--mart", required=True)
    p.add_argument("--draft", required=True, help=".dev/handover/<브랜치>.md")
    p.add_argument("--out", help="기본: <root>/docs/handover/<마트>.md")
    p.add_argument("--pr-body", action="store_true", help="파일을 쓰지 않고 PR 본문 내용을 표준 출력으로 낸다")
    p.add_argument("--root", default=str(PROJECT))
    return p.parse_args(argv)


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    args = parse_args(argv)
    root = Path(args.root)
    draft = Path(args.draft) if Path(args.draft).is_absolute() else root / args.draft
    try:
        text = make_facts.read_draft(draft)
        problems = make_facts.freshness_problems(root, args.mart, text)
        if problems:
            print(f"halt input_invalid: 인수인계 초안 {draft.name}이 최신이 아님 — " + "; ".join(problems), file=sys.stderr)
            return 2
        empty = make_facts.empty_slots(text)
        if empty:
            print(f"초안 미완성: 설명 칸 {', '.join(map(str, empty))}절이 빈 자리다", file=sys.stderr)
            return 2
        if args.pr_body:
            print(pr_body(text, args.mart))
            return 0
        head = make_facts.git(root, "rev-parse", "--short", "HEAD").strip()
        doc = published(text, draft_label(root, draft), head)
    except (OSError, make_facts.FactsError, KeyError) as e:
        print(f"반영하지 못함: {e.__class__.__name__}: {e}", file=sys.stderr)
        return 2
    out = Path(args.out) if args.out else root / "docs" / "handover" / f"{args.mart}.md"
    if out.exists():
        print(f"덮어씀: {out} (바뀐 줄 {changed_lines(make_facts.read_draft(out), doc)})")
    else:
        print(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(doc, encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
