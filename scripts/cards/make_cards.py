"""AgentGo용 카드 파일 생성기 (진행표 4-6, 결정 78, 형식 docs/ai/agentgo_card.md). 업로드는 하지 않는다(결정 29).

  python scripts/cards/make_cards.py --mart <마트> [--root R] [--dev-dir D]
  python scripts/cards/make_cards.py --mart <마트> --check

- 입력: contract, make_facts.section_flow()와 L6 상태, dags/harness_daily.py의 schedule,
  docs/handover/<마트>.md(없으면 .dev/handover/ 초안 경로를 글자로만)
- 출력: out/cards/<마트>/<테이블>.txt (mart 층 테이블 1개에 1장), out/cards/<마트>/manifest.json의 agentgo_cards 항목.
  같은 이름 카드는 덮어쓰고, contract에 없어진 테이블의 카드는 지운다
- 층을 알 수 없는 테이블이 있거나 mart 층 테이블이 없으면 만들지 않는다
- MAX_CHARS를 넘는 카드가 하나라도 있으면 어떤 카드도 쓰지 않고 긴 칸을 보고한다(자르지 않음)
- 데이터 값·행 수는 읽지도 넣지도 않는다. 예시 값 칸이 없으므로 개인정보 컬럼도 이름·설명까지만 나온다.
  프로젝트 ID·계정은 make_facts.scrub()으로, 주소는 <주소>로 가리고, 원천은 프로젝트를 뺀 데이터셋.테이블로 쓴다
- OM FQN은 넣지 않는다. 데이터베이스 자리가 프로젝트 ID이고 contract·설정에 없다(docs/ai/agentgo_card.md)
- 원천이 없는 칸은 "미작성"으로 적고 manifest의 missing_fields로 센다
- --check: 카드마다 도장이 지금 contract version·HEAD와 같은지(deliv_common과 같은 기준),
  mart 테이블과 카드 파일이 1:1인지 본다. 아니면 halt input_invalid
- 종료 코드: 0 생성·최신, 2 만들지 못함·길이 초과·도장 불일치·사용 오류
"""
import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / "scripts" / "deliverables"))
from deliv_common import (KST, ReportError, STAMP_LABELS, git, load_contract, pick_mart, scrub,  # noqa: E402
                          stamp_problems, write_manifest)
import devlog  # noqa: E402  (deliv_common이 make_facts를 불러 경로가 잡혀 있다)
from make_facts import STAMP_LINE, cell, om_status, section_flow  # noqa: E402

NAME = "agentgo_cards"
MAX_CHARS = 4000
UNWRITTEN = "미작성"
MART_LAYER = "mart"
DATASET = "{{ dataset_mart }}"
ADDRESS = re.compile(r"\b[a-z][a-z0-9+.-]*://[^\s|)]+|\b\d{1,3}(?:\.\d{1,3}){3}(?::\d+)?\b")
DAG_SCHEDULE = re.compile(r"^\s*schedule=(.+?),\s*$", re.M)


def clean(text):
    """프로젝트 ID·계정·주소를 가린다."""
    return ADDRESS.sub("<주소>", scrub(text))


def mart_tables(contract):
    """mart 층 테이블. 층 근거가 없으면 멈춘다."""
    unknown = [t.get("name", "?") for t in contract["tables"] if not t.get("layer")]
    if unknown:
        raise ReportError(f"contract에 layer가 없는 테이블: {', '.join(unknown)}")
    tables = [t for t in contract["tables"] if t["layer"] == MART_LAYER]
    if not tables:
        raise ReportError("contract에 mart 층 테이블이 없음")
    return tables


def refresh_text(root, contract):
    """contract schedule과 DAG의 schedule. 없는 쪽은 적지 않는다."""
    sched = contract.get("schedule") or {}
    parts = [sched.get("refresh")]
    if sched.get("retention_days"):
        parts.append(f"보관 {sched['retention_days']}일")
    dag = Path(root) / "dags" / "harness_daily.py"
    found = DAG_SCHEDULE.search(dag.read_text(encoding="utf-8")) if dag.exists() else None
    if found:
        value = found.group(1)
        parts.append("Airflow 자동 스케줄 없음(수동 실행)" if value == "None" else f"Airflow schedule {value}")
    return ", ".join(p for p in parts if p)


def handover_path(root, dev, mart):
    rel = f"docs/handover/{mart}.md"
    if (Path(root) / rel).exists():
        return rel
    folder = Path(dev) / "handover"
    title = f"# 인수인계 — {mart} ("
    drafts = sorted(p for p in folder.rglob("*.md") if p.read_text(encoding="utf-8").startswith(title))
    return f".dev/handover/{drafts[-1].relative_to(folder).as_posix()} (초안)" if drafts else ""


def lineage(contract, task, om):
    """section_flow()에서 task의 상류 줄만 raw 쪽부터 고른다. 원천은 프로젝트를 뺀다."""
    ups = {}
    for line in section_flow(contract, om).splitlines():
        if line.startswith("- ") and " → " in line:
            left, down = line[2:].rsplit(" → ", 1)
            ups[down] = left
    lines, seen = [], set()

    def visit(tid):
        if tid in seen or tid not in ups:
            return
        seen.add(tid)
        for up in ups[tid].split(", "):
            visit(up)
        lines.append(f"- {ups[tid]} → {tid}")
    visit(task)
    sources = [s.split(".", 1)[-1] for s in contract.get("sources") or []]
    return [f"- 원천: {', '.join(sources) or UNWRITTEN}", *lines]


def build_card(table, contract, mart, common, now, head, need):
    """[(칸 이름, 글)]. common: 마트 공통 칸 {refresh, status, handover, om}. need(칸, 값)은 빈 칸을 "미작성"으로 바꾸고 센다."""
    name = table["name"]
    name_ko = need("한글 별칭", table.get("name_ko"))
    rows = []
    for c in table.get("columns", []):
        col = c.get("name")
        label = f"{col} ({c['name_ko']})" if c.get("name_ko") else col
        kind, about = need(col + " 타입", c.get("type")), need(col + " 설명", c.get("description"))
        rows.append(f"| {cell(label)} | {cell(kind)} | {cell(about)} |")
    if not rows:
        need("컬럼", None)
    columns = {c.get("name") for c in table.get("columns", [])}
    metrics = [m for m in contract.get("interview", {}).get("metrics", []) if m.get("name") in columns]
    metric_rows = ["| 지표 | 계산식 | 단위 | 기준일 | 제외 |", "|---|---|---|---|---|",
                   *[f"| {m['name']} | " + " | ".join(cell(m.get(k) or "—") for k in ("formula", "unit", "base_date", "exclude"))
                     + " |" for m in metrics]]
    task = need("담당 task", table.get("task"))
    stamp = zip(STAMP_LABELS, (contract["version"], now, head))
    return [
        ("첫머리", "\n".join([
            f"# {name} ({name_ko})", "",
            f"- 표준 테이블 이름: {name}",
            f"- 한글 별칭: {name_ko}",
            f"- 데이터셋: {DATASET} (논리 이름)",
            f"- 카드 생성 시각: {now}"])),
        ("한 줄 설명", f"## 설명\n{name_ko}({name}). {mart} 마트의 {MART_LAYER} 층 테이블이다."),
        ("grain·키", "\n".join([
            "## 한 행의 뜻과 키",
            f"- 한 행: {need('grain', table.get('grain'))}",
            f"- 키: {need('키', ', '.join(table.get('keys') or []))}"])),
        ("컬럼", "\n".join(["## 컬럼", "| 이름 | 타입 | 설명 |", "|---|---|---|", *rows])),
        ("지표 정의", "\n".join(["## 지표 정의", *(metric_rows if metrics else ["이 테이블에 해당하는 지표 없음"])])),
        ("상류", "\n".join(["## 상류(리니지)", *lineage(contract, table.get("task"), common["om"])])),
        ("담당 task", f"## 담당 task\n{task}"),
        ("갱신 주기", f"## 갱신 주기\n{need('갱신 주기', common['refresh'])}"),
        ("결재 상태", f"## 결재 상태\n{common['status']}"),
        ("인수인계 문서", f"## 인수인계 문서\n{need('인수인계 문서', common['handover'])}"),
        ("도장", "\n".join(["## 도장 (결정 64 ⑤)", *(f"- {k}: {v}" for k, v in stamp)])),
    ]


def build(root, dev, mart, now, head):
    """({파일 이름: 본문}, 누락 목록, contract version). 길이 상한을 넘으면 ReportError."""
    contract = load_contract(root, mart)
    tables = mart_tables(contract)
    version = contract["version"]
    posts = devlog.post_results(mart, mart, version, dev)
    om = om_status(posts)
    common = {"om": om, "refresh": refresh_text(root, contract), "handover": handover_path(root, dev, mart),
              "status": f"운영 반영·OM 등록 확인(post-{posts[-1]['_n']})" if om else "OM 등록 미확인(결재 후 L6)"}
    cards, missing, over = {}, [], []
    for table in tables:
        def need(label, value, name=table["name"]):
            if value in (None, "") or not str(value).strip():
                missing.append(f"{name}: {label}")
                return UNWRITTEN
            return value
        sections = [(k, clean(v)) for k, v in build_card(table, contract, mart, common, now, head, need)]
        text = "\n\n".join(v for _, v in sections) + "\n"
        if len(text) > MAX_CHARS:
            longest = sorted(sections, key=lambda s: -len(s[1]))[:3]
            over.append(f"{table['name']} {len(text)}자 (긴 칸: " + ", ".join(f"{k} {len(v)}자" for k, v in longest) + ")")
        cards[f"{table['name']}.txt"] = text
    if over:
        raise ReportError(f"길이 상한 {MAX_CHARS}자를 넘음. 자르지 않는다: " + "; ".join(over))
    return cards, missing, version


def check(root, mart):
    """도장 최신성 검사. 최신이면 0, 아니면 2(halt input_invalid)."""
    folder = Path(root) / "out" / "cards" / mart
    contract = load_contract(root, mart)
    head = git(root, "rev-parse", "HEAD")
    want = {f"{t['name']}.txt" for t in mart_tables(contract)}
    have = {p.name for p in folder.glob("*.txt")}
    problems = [f"{n} 없음" for n in sorted(want - have)] + [f"{n}은 contract에 없음" for n in sorted(have - want)]
    for name in sorted(want & have):
        stamp = dict(STAMP_LINE.findall((folder / name).read_text(encoding="utf-8")))
        problems += [f"{name}: {p}" for p in stamp_problems(stamp, contract, head)]
    if problems:
        print(f"halt input_invalid: {mart} 카드가 최신이 아님 — " + "; ".join(problems), file=sys.stderr)
        return 2
    print(f"최신: {mart} 카드 {len(want)}장 (contract v{contract['version']}, {head[:8]})")
    return 0


def parse_args(argv):
    p = argparse.ArgumentParser(description="AgentGo용 카드 파일 생성기 (진행표 4-6, 업로드 없음)")
    p.add_argument("--mart", help="마트. contract가 1개면 생략 가능(자동 선택)")
    p.add_argument("--root", default=str(PROJECT))
    p.add_argument("--dev-dir", help="기본: <root>/.dev")
    p.add_argument("--check", action="store_true", help="카드 도장이 지금 contract version·HEAD와 같은지만 검사")
    return p.parse_args(argv)


def main(argv=None, now=None):
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    args = parse_args(argv)
    root = Path(args.root)
    args.mart = pick_mart(root, args.mart)
    if args.mart is None:
        return 2
    try:
        if args.check:
            return check(root, args.mart)
        dev = Path(args.dev_dir) if args.dev_dir else root / ".dev"
        now = now or datetime.now(KST).isoformat(timespec="seconds")
        head = git(root, "rev-parse", "HEAD")
        cards, missing, version = build(root, dev, args.mart, now, head)
        folder = root / "out" / "cards" / args.mart
        folder.mkdir(parents=True, exist_ok=True)
        for old in folder.glob("*.txt"):
            if old.name not in cards:
                old.unlink()
        for name, text in cards.items():
            (folder / name).write_text(text, encoding="utf-8", newline="\n")
    except (ReportError, KeyError, ValueError, OSError, devlog.DevlogError) as e:
        print(f"카드를 만들지 못함: {e.__class__.__name__}: {e}", file=sys.stderr)
        return 2
    manifest = write_manifest(folder, {
        "name": NAME, "cards": [{"file": f"out/cards/{args.mart}/{n}", "chars": len(t)} for n, t in cards.items()],
        "max_chars": MAX_CHARS, "missing_fields": len(missing), "missing": missing,
        "contract_version": version, "generated_at": now, "base_commit": head})
    for name, text in cards.items():
        print(f"{folder / name} ({len(text)}자)")
    print(f"카드 {len(cards)}장, 누락 칸 {len(missing)}개 → {manifest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
