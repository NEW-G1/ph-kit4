"""규칙 후보 생성과 learned 규칙 형식 검사 (진행표 4-1, 결정 74, 03 §6.3, 08 V6).

  python scripts/metrics/rule_candidates.py            # .dev/rule_candidates.md 갱신
  python scripts/metrics/rule_candidates.py --check    # .claude/rules/learned/ 형식 검사 (문제가 있으면 종료 코드 1)

- 후보 판정은 코드가 한다: 같은 error_type 누적 2회 이상 (03 §6.3). 묶음은 error_type 하나이고,
  근거 반려의 검사 id를 함께 적어 사람이 판단하게 한다
- 뺀다: docs/ai/rule_candidate_exclusions.md의 반려(08 V6-3), 노하우가 켜진 실행의 반려(08 §4). M2는 바꾸지 않는다
- 제목·규칙 문장·적용 경로는 비워 두고 AI가 채운다. 다시 돌려도 id와 그 문장을 지우지 않는다.
  "결재 대기" 후보는 근거 반려·검사 id만 갱신하고, 상태가 바뀐 후보는 건드리지 않는다
- 승격은 사람이 PR 머지로 결재한다. 머지 뒤 사람이 approval·rule_promotion을 기록하고, 출처 줄의 결재 id는
  후속 커밋으로 채운다. 그 전까지 출처 줄은 "결재 대기"다
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / "scripts" / "log"))
import devlog  # noqa: E402

THRESHOLD = 2  # 03 §6.3: 같은 error_type 누적 2회
PENDING = "결재 대기"
SHORT = "근거 부족"
BLANK = "(AI 작성 대기)"
EXCLUSIONS = Path("docs") / "ai" / "rule_candidate_exclusions.md"
LEARNED = Path(".claude") / "rules" / "learned"
FILE_NAME = "rule_candidates.md"
EXCLUSION_ROW = re.compile(r"^\|\s*(R-\d+)\s*\|\s*([^|]*?)\s*\|\s*([^|]*?)\s*\|\s*$", re.M)
BLOCK = re.compile(r"^(?=##\s+RC-)", re.M)
HEAD = re.compile(r"##\s+(RC-\d+)\s*(.*)")
REJECTION_ID = re.compile(r"R-\d+")
SOURCE = re.compile(r"^출처:\s*(RC-\d{3,})\s*/\s*근거 반려\s+(R-\d+(?:,\s*R-\d+)*)\s*/\s*결재\s+"
                    r"(?:대기|(H-\d+)\s*/\s*(\d{4}-\d{2}-\d{2}))\s*$", re.M)


def load_exclusions(root):
    """{반려 id: (이유, 근거)}. 파일이 없거나 이유·근거가 빈 줄이 있으면 ValueError (틀린 후보를 만들지 않는다)."""
    path = Path(root) / EXCLUSIONS
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        raise ValueError(f"제외 목록을 읽지 못함: {e.__class__.__name__}") from None
    out = {}
    for rid, reason, basis in EXCLUSION_ROW.findall(text):
        if not reason or not basis:
            raise ValueError(f"제외 목록 {rid}의 이유·근거가 비어 있음")
        out[rid] = (reason, basis)
    return out


def ladder_result(dev, r):
    path = (Path(dev) / "ladder_results" / r["mart"]
            / f"{r['task']}-v{r.get('contract_version')}-{r.get('iteration')}.json")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def expert_on(result):
    return bool(((result.get("modules") or {}).get("expert") or {}).get("on"))


def check_id(result):
    rungs = result.get("rungs") or []
    return (rungs[-1].get("metrics") or {}).get("check") if rungs else None


def groups(root, dev):
    """{error_type: [반려]}. 제외 목록과 노하우 켠 실행을 뺀 반려를 시간순으로 묶는다."""
    excluded = load_exclusions(root)
    out = {}
    for r in sorted(devlog.read_lines(Path(dev) / "rejections.jsonl"), key=lambda x: x["ts"]):
        if r["id"] in excluded or expert_on(ladder_result(dev, r)):
            continue
        out.setdefault(r["error_type"], []).append(r)
    return out


def evidence_line(error_type, rows):
    rungs = ", ".join(dict.fromkeys(r["caught_by_rung"] for r in rows))
    return f"- 근거 반려: {', '.join(r['id'] for r in rows)} ({error_type}, {rungs})"


def checks_line(dev, rows):
    ids = [c for c in (check_id(ladder_result(dev, r)) for r in rows) if c]
    return f"- 검사 id: {', '.join(dict.fromkeys(ids)) or '-'}"


def field(block, name):
    m = re.search(rf"^-\s*{name}:\s*(.+)$", block, re.M)
    return m.group(1).strip() if m else None


def parse_candidates(text):
    """[{"id", "title", "error_type", "evidence", "checks", "state"}]."""
    out = []
    for block in BLOCK.split(text):
        m = HEAD.match(block)
        if m:
            out.append({"id": m.group(1), "title": m.group(2).strip(), "error_type": field(block, "error_type"),
                        "evidence": field(block, "근거 반려"), "checks": field(block, "검사 id"),
                        "state": field(block, "상태")})
    return out


def evidence_short(candidate, excluded, known):
    """기록에 있고 제외 목록에 없는 근거 반려가 기준보다 적은가. 표시에만 쓰고 후보 파일은 바꾸지 않는다."""
    ids = REJECTION_ID.findall(candidate.get("evidence") or "")
    return sum(1 for rid in ids if rid in known and rid not in excluded) < THRESHOLD


def new_block(rid, error_type, rows, dev):
    return "\n".join((f"## {rid} {BLANK}", f"- error_type: {error_type}", f"- 규칙 문장: {BLANK}", f"- 적용 경로: {BLANK}",
                      evidence_line(error_type, rows), checks_line(dev, rows), f"- 예상 효과: {error_type} 반려 감소",
                      f"- 상태: {PENDING}", "", ""))


def refresh(block, error_type, rows, dev):
    block = re.sub(r"^-\s*근거 반려:.*$", lambda _: evidence_line(error_type, rows), block, flags=re.M)
    return re.sub(r"^-\s*검사 id:.*$", lambda _: checks_line(dev, rows), block, flags=re.M)


def update(root=PROJECT, dev=None):
    """후보 파일을 갱신하고 새로 만든 후보 id 목록을 돌려준다. 바뀐 것이 없으면 파일을 쓰지 않는다."""
    root = Path(root)
    dev = Path(dev or root / ".dev")
    path = dev / FILE_NAME
    old = path.read_text(encoding="utf-8") if path.exists() else ""
    by_type = {et: rows for et, rows in groups(root, dev).items() if len(rows) >= THRESHOLD}
    blocks = BLOCK.split(old)
    head = blocks[0] if blocks and not HEAD.match(blocks[0]) else "# 규칙 후보\n\n"
    body = [b for b in blocks if HEAD.match(b)]
    seen = set()
    for i, block in enumerate(body):
        et = field(block, "error_type")
        seen.add(et)
        if field(block, "상태") == PENDING and et in by_type:
            body[i] = refresh(block, et, by_type[et], dev)
    numbers = [int(HEAD.match(b).group(1)[3:]) for b in body]
    last = max(numbers, default=0)
    created = []
    for et, rows in by_type.items():
        if et not in seen:
            last += 1
            created.append(f"RC-{last:03d}")
            body.append(new_block(created[-1], et, rows, dev))
    text = head + "".join(body)
    if text != old and (body or old):
        dev.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)
    return created


# ---------- learned 규칙 ----------

def parse_learned(path):
    """learned 규칙 파일 1개. source가 없으면 출처 줄 형식이 틀린 것이다."""
    body = Path(path).read_text(encoding="utf-8")
    title = re.search(r"^#\s+(.+)$", body, re.M)
    front = body.split("---", 2)[1] if body.startswith("---") and body.count("---") >= 2 else ""
    rest = body.split("---", 2)[2] if front else body
    source = SOURCE.search(body)
    line = re.search(r"^출처:\s*(.+)$", body, re.M)
    return {"file": Path(path).name, "title": title.group(1).strip() if title else None,
            "paths": re.findall(r'^\s*-\s*"([^"]+)"', front, re.M), "source": line.group(1).strip() if line else None,
            "rules": re.findall(r"^-\s+(.+)$", rest, re.M),
            "rule_id": source.group(1) if source else None,
            "evidence": REJECTION_ID.findall(source.group(2)) if source else [],
            "approval": source.group(3) if source else None, "date": source.group(4) if source else None,
            "pending": bool(source) and source.group(3) is None}


def learned_rules(root):
    folder = Path(root) / LEARNED
    return [parse_learned(f) for f in sorted(folder.glob("*.md"))] if folder.is_dir() else []


def check_learned(root=PROJECT, dev=None):
    """{파일: [문제]}. 결재 대기(출처 줄에 결재 id 없음)는 문제가 아니다. 결재 id가 있으면 기록과 맞아야 한다."""
    root = Path(root)
    dev = Path(dev or root / ".dev")
    path = dev / FILE_NAME
    candidates = {c["id"]: c for c in parse_candidates(path.read_text(encoding="utf-8") if path.exists() else "")}
    rejections = {r["id"]: r for r in devlog.read_lines(dev / "rejections.jsonl")}
    interventions = {r["id"]: r for r in devlog.read_lines(dev / "interventions.jsonl")}
    excluded = load_exclusions(root)
    out = {}
    for rule in learned_rules(root):
        bad = []
        if not rule["paths"]:
            bad.append("paths가 없음")
        if not rule["title"]:
            bad.append("제목이 없음")
        if not rule["rules"]:
            bad.append("규칙 문장이 없음")
        if rule["rule_id"] is None:
            bad.append("출처 줄 형식이 틀림")
            out[rule["file"]] = bad
            continue
        candidate = candidates.get(rule["rule_id"])
        if candidate is None:
            bad.append(f"규칙 후보 {rule['rule_id']}가 없음")
        if len(rule["evidence"]) < THRESHOLD:
            bad.append(f"근거 반려가 {THRESHOLD}건 미만")
        for rid in rule["evidence"]:
            if rid not in rejections:
                bad.append(f"근거 반려 {rid}가 기록에 없음")
            elif rid in excluded:
                bad.append(f"근거 반려 {rid}는 제외 목록에 있음")
            elif candidate and rejections[rid]["error_type"] != candidate["error_type"]:
                bad.append(f"근거 반려 {rid}의 error_type이 후보와 다름")
        if not rule["pending"]:
            record = interventions.get(rule["approval"])
            if (record is None or record.get("stage") != devlog.RULE_STAGE
                    or record.get("rule_id") != rule["rule_id"]):
                bad.append(f"결재 {rule['approval']}가 이 규칙의 rule_promotion 기록이 아님")
            elif record["ts"][:10] != rule["date"]:
                bad.append(f"출처 날짜가 결재 {rule['approval']}의 날짜와 다름")
            else:
                known = [rejections[r] for r in rule["evidence"] if r in rejections]
                last = max(known, key=lambda r: r["ts"], default=None)
                if last and record.get("mart") != last["mart"]:  # 08 V6-5
                    bad.append(f"결재 {rule['approval']}의 mart가 마지막 근거 반려의 마트와 다름")
        if bad:
            out[rule["file"]] = bad
    return out


def promoted_map(root=PROJECT):
    """{근거 반려 id: 규칙 후보 id}. rejections의 rule_promoted 집계값이다 (03 §6.2)."""
    return {rid: rule["rule_id"] for rule in learned_rules(root) for rid in rule["evidence"]}


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description="규칙 후보 갱신과 learned 형식 검사 (03 §6.3)")
    p.add_argument("--root", type=Path, default=PROJECT)
    p.add_argument("--dev-dir", type=Path)
    p.add_argument("--check", action="store_true", help="learned 규칙 형식 검사")
    a = p.parse_args(argv)
    try:
        if a.check:
            problems = check_learned(a.root, a.dev_dir)
            for name, bad in problems.items():
                print(f"{name}: " + "; ".join(bad), file=sys.stderr)
            return 1 if problems else 0
        created = update(a.root, a.dev_dir)
    except ValueError as e:
        print(f"멈춤: {e}", file=sys.stderr)
        return 2
    print("새 후보: " + (", ".join(created) or "없음"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
