"""데이터 흐름도 생성기 (진행표 4-4 흐름도 부분, 결정 69, 칸 기준 docs/templates/standards_survey.md §5.1).

  python scripts/deliverables/flow_diagram.py --mart <마트> [--root R] [--dev-dir D] [--date YYYY-MM-DD] [--force]
  python scripts/deliverables/flow_diagram.py --mart <마트> --check [--file 흐름도.xlsx]

- 그림은 contract에서만 그린다(결정 69). OM에는 테이블 단위 리니지만 있으므로(결정 68) OM 리니지는 L6 결과로 대조만 한다
  · 원천 노드: contract sources (contract에 원천별 연결이 없으므로 원천 묶음 → raw 첫 task로 잇는다. 판정 안 함)
  · task 노드·의존 화살표: contract dag.tasks (load = 테이블 노드, gate = 게이트 노드)
  · 테이블 노드 칸: contract tables[] (이름·한글명·층·grain·키·담당 task)
  · 게이트 노드의 검사 ID: contract checks.gates 중 l3 검사 머리말 `task:`의 층이 게이트 층과 같은 것
    (gen_dq.py와 같은 연결). 검사 본문은 읽지 않는다
  · 갱신 주기·보관: contract schedule
  · 흐름 요약: scripts/handover/make_facts.section_flow() 출력 그대로. 최신 L6가 통과면 인수인계 초안과 같은 OM 문구(om_status)를 쓴다
  · 리니지 대조: 기대 엣지 = scripts/ladder/l6_om.plan()의 edges(게이트를 건너뛴 load 테이블 사이).
    최신 L6 결과(<마트>-v<버전>-post-<n>.json 중 가장 큰 n, devlog.latest_post)가 있으면 엣지마다 일치·누락을 적고
    "OM 확인: 일치 n/n", 기대 밖 엣지·원천 엣지(보고만)를 붙인다. 없으면 OM 확인 칸을 '미확인(결재 후 L6)'으로 두고
    deferred로 센다(생성은 허용)
- 출력: out/deliverables/<마트>/DFD_<마트>_<YYYYMMDD>.xlsx (기준 파일. 시트: 안내, 표지, 노드, 흐름, 리니지 대조, 흐름 요약)
  + 같은 이름의 .md (Mermaid flowchart, 도장 줄 포함), manifest.json의 flow_diagram 항목(다른 항목은 둔다)
- 도장·--check·manifest는 unit_test_report.py·table_spec.py와 같다(deliv_common, 결정 64 ⑤).
  --check는 xlsx 도장을 보고, 같은 이름의 .md가 없거나 .md 도장 줄이 xlsx 도장과 다르면 종료 코드 2
- 데이터 값은 넣지 않는다(메타데이터만). 프로젝트 ID·계정은 make_facts.scrub()으로 가린다
- 스크린샷 자동 캡처는 하지 않는다(결정 69)
- 종료 코드: 0 생성·최신, 2 만들지 못함·도장 불일치·사용 오류
"""
import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / "scripts" / "log"))
sys.path.insert(0, str(PROJECT / "scripts" / "ladder"))
sys.path.insert(0, str(PROJECT / "scripts" / "deliverables"))
from deliv_common import (KST, ReportError, STAMP_LABELS, check as check_stamp, git, load_contract,  # noqa: E402
                          pick_mart, put, read_stamp, write_manifest, write_stamp)
import common as ladder_common  # noqa: E402  (scripts/ladder/common.py)
import devlog  # noqa: E402
import l6_om  # noqa: E402
from make_facts import om_status, scrub, section_flow  # noqa: E402

NAME = "flow_diagram"
PREFIX = "DFD"
OM_PENDING = "미확인(결재 후 L6)"
MASK_PROJECT = "<프로젝트>"
HEADER_ROW, FIRST_ROW = 3, 4
NODE_COLS = ("노드 id", "종류", "층", "이름", "한글명", "grain", "키", "담당 task", "검사 ID")
FLOW_COLS = ("상류", "하류", "종류", "원천")
LINEAGE_COLS = ("기대 엣지 (상류 -> 하류)", "OM 확인", "근거")
# 필수 칸 (manifest required_fields). 원천이 없으면 비우고 missing으로 센다
NODE_REQUIRED = {"원천": ("이름",), "테이블": ("이름", "층", "담당 task"), "게이트": ("이름", "층", "검사 ID"),
                 "다른 마트 task": ("이름",)}
LABEL_SOURCES = "원천 (contract sources)"


# ---------- 모델 (contract·L6 결과만) ----------

def safe_id(prefix, name):
    return prefix + re.sub(r"[^A-Za-z0-9_]", "_", name)


def gate_checks(root, mart, contract):
    """{gate task id: [C-xx]}. gen_dq.py와 같은 연결: l3 머리말 task의 층 = 게이트 층. 본문은 쓰지 않는다."""
    tasks = {t["id"]: t for t in contract["dag"]["tasks"]}
    gate_ids = {c["id"] for c in contract.get("checks", {}).get("gates", [])}
    by_layer = {}
    try:
        checks = ladder_common.load_checks(ladder_common.Paths(root, mart), "l3")
    except ValueError as e:
        raise ReportError(f"l3 검사 머리말을 읽지 못함: {e}") from None
    for check_id, header, _body in checks:
        task = tasks.get(header.get("task"))
        if task is not None and task["kind"] == "load" and check_id in gate_ids:
            by_layer.setdefault(task["layer"], []).append(check_id)
    return {t["id"]: sorted(by_layer.get(t["layer"], [])) for t in tasks.values() if t["kind"] == "gate"}


class Flow:
    def __init__(self, root, dev, mart):
        self.root, self.dev, self.mart = Path(root), Path(dev), mart
        self.contract = load_contract(root, mart)
        self.version = self.contract["version"]
        try:
            self.plan = l6_om.plan(self.contract, MASK_PROJECT, lambda other: load_contract(root, other))
        except ladder_common.LadderError as e:
            raise ReportError(str(e)) from None
        self.gates = gate_checks(root, mart, self.contract)
        self.latest = devlog.latest_post(mart, mart, self.version, self.dev)
        self.nodes, self.edges = self._graph()
        ids = [n["노드 id"] for n in self.nodes]
        dup = sorted({i for i in ids if ids.count(i) > 1})
        if dup:
            raise ReportError(f"Mermaid 노드 id가 겹침 (task 이름의 특수문자 치환 결과): {dup}")

    def _graph(self):
        c = self.contract
        tasks = {t["id"]: t for t in c["dag"]["tasks"]}
        table_of = {t["task"]: t for t in c["tables"]}
        nodes, node_of = [], {}
        for i, src in enumerate(c.get("sources") or [], start=1):
            nodes.append({"노드 id": f"S{i}", "종류": "원천", "층": "원천", "이름": scrub(src)})
        for t in c["dag"]["tasks"]:
            if t["kind"] == "gate":
                node = {"노드 id": safe_id("G_", t["id"]), "종류": "게이트", "층": t["layer"], "이름": t["id"],
                        "담당 task": t["id"], "검사 ID": ", ".join(self.gates.get(t["id"], []))}
            else:
                tb = table_of.get(t["id"], {})
                node = {"노드 id": safe_id("T_", t["id"]), "종류": "테이블", "층": t["layer"],
                        "이름": tb.get("name", ""), "한글명": tb.get("name_ko", ""), "grain": tb.get("grain", ""),
                        "키": ", ".join(tb.get("keys", [])), "담당 task": t["id"]}
            nodes.append(node)
            node_of[t["id"]] = node["노드 id"]
        edges = []
        for t in c["dag"]["tasks"]:
            for up in t["upstream"]:
                if up not in tasks:  # 다른 contract의 task (<마트>:<task>)
                    if up not in node_of:
                        node_of[up] = safe_id("X_", up)
                        nodes.append({"노드 id": node_of[up], "종류": "다른 마트 task", "층": "-", "이름": up})
                    kind = "의존 (다른 마트)"
                else:
                    kind = "의존"
                edges.append({"상류": up, "하류": t["id"], "종류": kind, "원천": "contract dag.tasks[].upstream",
                              "_from": node_of[up], "_to": node_of[t["id"]]})
        if c.get("sources"):
            for name in self.plan["roots"]:
                task = next(tb["task"] for tb in c["tables"] if tb["name"] == name)
                edges.append({"상류": LABEL_SOURCES, "하류": task, "종류": "원천 (보고만, 원천별 연결은 contract에 없음)",
                              "원천": "contract sources", "_from": "SRC", "_to": node_of[task]})
        return nodes, edges

    def lineage(self):
        """[(엣지 문자열, OM 확인, 근거)], 일치 수, 보고만 목록 {기대 밖, 원천}."""
        expected = [f"{a} -> {b}" for a, b in self.plan["edges"]]
        if self.latest is None:
            return [(e, OM_PENDING, "L6 결과 없음") for e in expected], None, None
        rung = next((g for g in self.latest.get("rungs", []) if g.get("rung") == "L6"), {})
        m = rung.get("metrics", {})
        seen, missing = set(m.get("edges_expected", [])), set(m.get("edges_missing", []))
        where = f".dev/ladder_results/{self.mart}/{self.latest['_name']}"
        rows = []
        for e in expected:
            status = "누락" if e in missing else "일치" if e in seen else "L6 기대값에 없음(재확인 필요)"
            rows.append((e, status, where))
        report = {"기대 밖 엣지": [scrub(x) for x in m.get("edges_unexpected", [])],
                  "원천 엣지": [scrub(x) for x in m.get("source_edges", [])]}
        return rows, sum(1 for _, s, _ in rows if s == "일치"), report

    def om_summary(self):
        rows, matched, _ = self.lineage()
        if matched is None:
            return OM_PENDING
        return f"일치 {matched}/{len(rows)} (post-{self.latest['_n']})"


# ---------- Mermaid ----------

def label(*parts):
    text = "<br/>".join(scrub(p) for p in parts if p)
    return '"' + text.replace('"', "#quot;") + '"'


def stamp_line(version, now, head):
    return "도장 (결정 64 ⑤): " + " · ".join(f"{k}={v}" for k, v in zip(STAMP_LABELS, (version, now, head)))


def parse_stamp_line(text):
    for line in text.splitlines():
        if line.startswith("도장 (결정 64 ⑤): "):
            pairs = line.split(": ", 1)[1].split(" · ")
            return dict(p.split("=", 1) for p in pairs if "=" in p)
    return None


def mermaid(flow):
    lines = ["flowchart LR"]
    layers = []
    for n in flow.nodes:
        if n["종류"] in ("테이블", "게이트") and n["층"] not in layers:
            layers.append(n["층"])
    sources = [n for n in flow.nodes if n["종류"] == "원천"]
    if sources:
        lines.append(f'  subgraph SRC[{label(LABEL_SOURCES)}]')
        lines += [f"    {n['노드 id']}[{label(n['이름'])}]" for n in sources]
        lines.append("  end")
    for layer in layers:
        lines.append(f"  subgraph {safe_id('LAYER_', layer)}[{label(layer + ' 층')}]")
        for n in flow.nodes:
            if n["층"] != layer:
                continue
            if n["종류"] == "게이트":
                lines.append(f"    {n['노드 id']}{{{{{label(n['이름'], n.get('검사 ID') or '검사 없음')}}}}}")
            elif n["종류"] == "테이블":
                lines.append(f"    {n['노드 id']}[({label(n['이름'], n.get('한글명'))})]")
        lines.append("  end")
    for n in flow.nodes:
        if n["종류"] == "다른 마트 task":
            lines.append(f"  {n['노드 id']}[/{label(n['이름'])}/]")
    for e in flow.edges:
        arrow = "-.->" if e["_from"] == "SRC" else "-->"
        lines.append(f"  {e['_from']} {arrow} {e['_to']}")
    return lines


def markdown(flow, name, now, head):
    c = flow.contract
    sched = c.get("schedule", {})
    rows, _, report = flow.lineage()
    out = [f"# 데이터 흐름도 — {flow.mart}", "",
           stamp_line(flow.version, now, head), "",
           f"- 기준 파일: {name}.xlsx (도장·--check 기준, 결정 69). 그림은 contract에서 그리고 OM 리니지는 L6로 대조만 한다",
           f"- 갱신 주기: {sched.get('refresh', '-')}, 보관 {sched.get('retention_days', '-')}일 (contract schedule)",
           f"- OM 확인: {flow.om_summary()}", "",
           "```mermaid", *mermaid(flow), "```", "",
           "## 리니지 대조 (contract 기대 엣지 vs 최신 L6)", "",
           "| 기대 엣지 | OM 확인 |", "|---|---|", *[f"| {e} | {s} |" for e, s, _ in rows]]
    if report is not None:
        out += ["", "보고만(판정 안 함): " + "; ".join(f"{k} {len(v)}" + (f" ({', '.join(v)})" if v else "")
                                                for k, v in report.items())]
    return scrub("\n".join(out) + "\n")


# ---------- xlsx ----------

def style_header(ws, row, ncols):
    from openpyxl.styles import Font, PatternFill
    for c in range(1, ncols + 1):
        cell = ws.cell(row, c)
        cell.font = Font(bold=True)
        cell.fill = PatternFill("solid", fgColor="DDEBF7")


def write_grid(ws, title, cols, rows):
    put(ws, "A1", title)
    for c, name in enumerate(("번호", *cols), start=1):
        put(ws, (HEADER_ROW, c), name)
    style_header(ws, HEADER_ROW, len(cols) + 1)
    for i, row in enumerate(rows):
        put(ws, (FIRST_ROW + i, 1), i + 1)
        for c, name in enumerate(cols, start=2):
            if row.get(name) not in ("", None):
                put(ws, (FIRST_ROW + i, c), row[name])
    for c in range(1, len(cols) + 2):
        ws.column_dimensions[ws.cell(HEADER_ROW, c).column_letter].width = 8 if c == 1 else 26


def build(root, dev, mart, day, now, head, name):
    """(workbook, markdown, required, missing 목록, deferred 목록, version)."""
    import openpyxl
    flow = Flow(root, dev, mart)
    missing, deferred, required = [], [], 0

    def need(sheet, coord, label_, value, what):
        nonlocal required
        required += 1
        where = f"{sheet}!{coord} {label_} ({what})"
        if value in (None, "") or (isinstance(value, str) and not value.strip()):
            missing.append(where)
        elif value == OM_PENDING:
            deferred.append(where)

    wb = openpyxl.Workbook()
    guide = wb.active
    guide.title = "안내"
    cover = wb.create_sheet("표지")
    nodes_ws, flow_ws, lin_ws, sum_ws = (wb.create_sheet(s) for s in ("노드", "흐름", "리니지 대조", "흐름 요약"))

    put(guide, "A1", "데이터 흐름도 안내")
    guide_rows = [
        ("기준", "결정 69: 그림은 contract에서 그리고 OM 리니지는 L6 결과로 대조만 한다(OM에는 테이블 단위 리니지만 있음, 결정 68)"),
        ("칸 원천", "docs/templates/standards_survey.md §5.1 흐름도 칸 표"),
        ("그림", f"같은 이름의 .md(Mermaid flowchart): {name}.md. 이 xlsx가 도장·--check 기준"),
        ("manifest 집계", f"필수 칸이 비면 missing_fields, OM 확인 '{OM_PENDING}'은 deferred_fields로 센다"),
        ("넣지 않는 것", "데이터 값, 검사 쿼리 본문, 프로젝트 ID·계정(가림). 스크린샷 자동 캡처는 하지 않는다"),
    ]
    for i, (k, v) in enumerate(guide_rows, start=3):
        put(guide, (i, 1), k)
        put(guide, (i, 2), v)
    guide.column_dimensions["A"].width = 16
    guide.column_dimensions["B"].width = 100

    sched = flow.contract.get("schedule", {})
    lin_rows, _, report = flow.lineage()
    cover_rows = [
        ("문서명", "데이터 흐름도"), ("문서 번호", f"{PREFIX}-{mart}-{day.replace('-', '')}"),
        ("대상 마트", mart), ("contract 버전", f"v{flow.version}"),
        ("갱신 주기", sched.get("refresh", "")), ("보관 일수", sched.get("retention_days", "")),
        ("노드 수", len(flow.nodes)), ("흐름 화살표 수", len(flow.edges)),
        ("OM 확인", flow.om_summary()),
        ("L6 근거", f".dev/ladder_results/{mart}/{flow.latest['_name']}" if flow.latest else "없음(결재 후)"),
        ("그림 파일", f"{name}.md"), ("작성일", day),
    ]
    put(cover, "A1", "표지")
    for i, (k, v) in enumerate(cover_rows, start=3):
        put(cover, (i, 1), k)
        put(cover, (i, 2), v)
    write_stamp(cover, 3 + len(cover_rows) + 1, flow.version, now, head)
    cover.column_dimensions["A"].width = 18
    cover.column_dimensions["B"].width = 60
    cover.column_dimensions["C"].width = 32

    write_grid(nodes_ws, "노드 (contract sources·tables·dag.tasks·checks.gates)", NODE_COLS, flow.nodes)
    for i, n in enumerate(flow.nodes):
        for col in NODE_REQUIRED[n["종류"]]:
            coord = nodes_ws.cell(FIRST_ROW + i, 2 + NODE_COLS.index(col)).coordinate
            need(nodes_ws.title, coord, col, n.get(col), n["노드 id"])

    write_grid(flow_ws, "흐름 (contract dag.tasks[].upstream, 원천 묶음 → raw 첫 task)", FLOW_COLS, flow.edges)
    for i, e in enumerate(flow.edges):
        for col in ("상류", "하류"):
            coord = flow_ws.cell(FIRST_ROW + i, 2 + FLOW_COLS.index(col)).coordinate
            need(flow_ws.title, coord, col, e.get(col), f"{e['상류']} -> {e['하류']}")

    write_grid(lin_ws, "리니지 대조 (기대 = l6_om.plan, OM 확인 = 최신 L6 결과)", LINEAGE_COLS,
               [dict(zip(LINEAGE_COLS, r)) for r in lin_rows])
    for i, (edge, status, _) in enumerate(lin_rows):
        need(lin_ws.title, lin_ws.cell(FIRST_ROW + i, 3).coordinate, "OM 확인", status, edge)
    r = FIRST_ROW + len(lin_rows) + 1
    if report is not None:
        put(lin_ws, (r, 1), "보고만 (판정 안 함, 결정 67)")
        for j, (k, v) in enumerate(report.items(), start=1):
            put(lin_ws, (r + j, 1), k)
            put(lin_ws, (r + j, 2), len(v))
            put(lin_ws, (r + j, 3), ", ".join(v) or "-")

    put(sum_ws, "A1", "흐름 요약 (scripts/handover/make_facts.section_flow 출력 그대로)")
    om = om_status([flow.latest] if flow.latest else [])
    for i, line in enumerate(section_flow(flow.contract, om).splitlines(), start=3):
        if line:
            put(sum_ws, (i, 1), line)
    sum_ws.column_dimensions["A"].width = 120

    return wb, markdown(flow, name, now, head), required, missing, deferred, flow.version


# ---------- 최신성 검사 ----------

def check(root, mart, file=None):
    """xlsx 도장(deliv_common.check) + 같은 이름 .md의 도장 줄이 xlsx 도장과 같은지. 0 최신, 2 아님."""
    code = check_stamp(root, mart, PREFIX, "흐름도", file)
    if code != 0:
        return code
    folder = Path(root) / "out" / "deliverables" / mart
    xlsx = Path(file) if file else max(folder.glob(f"{PREFIX}_{mart}_*.xlsx"))
    md = xlsx.with_suffix(".md")
    if not md.exists():
        print(f"halt input_invalid: 흐름도 그림 {md.name}이 없음", file=sys.stderr)
        return 2
    want = {k: str(v) for k, v in read_stamp(xlsx).items()}
    got = parse_stamp_line(md.read_text(encoding="utf-8"))
    if got != want:
        print(f"halt input_invalid: {md.name} 도장 줄이 {xlsx.name} 도장과 다름", file=sys.stderr)
        return 2
    return 0


def parse_args(argv):
    p = argparse.ArgumentParser(description="데이터 흐름도 생성기 (진행표 4-4, 결정 69)")
    p.add_argument("--mart", help="마트. contract가 1개면 생략 가능(자동 선택)")
    p.add_argument("--root", default=str(PROJECT))
    p.add_argument("--dev-dir", help="기본: <root>/.dev")
    p.add_argument("--date", help="작성일 YYYY-MM-DD (기본: 오늘 +09:00)")
    p.add_argument("--force", action="store_true", help="같은 날짜 흐름도가 있으면 덮어씀")
    p.add_argument("--check", action="store_true", help="흐름도 도장이 지금 contract version·HEAD와 같은지만 검사")
    p.add_argument("--file", help="--check 대상 xlsx (기본: out/deliverables/<마트>/의 마지막 흐름도)")
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
        import openpyxl  # noqa: F401
    except ImportError:
        print("openpyxl이 없어 흐름도를 만들 수 없음 (설치는 사람이 한다)", file=sys.stderr)
        return 2
    try:
        if args.check:
            return check(root, args.mart, args.file)
        dev = Path(args.dev_dir) if args.dev_dir else root / ".dev"
        now = now or datetime.now(KST).isoformat(timespec="seconds")
        day = args.date or now[:10]
        head = git(root, "rev-parse", "HEAD")
        folder = root / "out" / "deliverables" / args.mart
        name = f"{PREFIX}_{args.mart}_{day.replace('-', '')}"
        xlsx, md = folder / f"{name}.xlsx", folder / f"{name}.md"
        if (xlsx.exists() or md.exists()) and not args.force:
            raise ReportError(f"이미 있음: {name}. 덮어쓰지 않는다 (--force)")
        wb, text, required, missing, deferred, version = build(root, dev, args.mart, day, now, head, name)
        folder.mkdir(parents=True, exist_ok=True)
        wb.save(xlsx)
        md.write_text(text, encoding="utf-8", newline="\n")
    except (ReportError, KeyError, ValueError, OSError, StopIteration) as e:
        print(f"흐름도를 만들지 못함: {e.__class__.__name__}: {e}", file=sys.stderr)
        return 2
    manifest = write_manifest(folder, {
        "name": NAME, "file": f"out/deliverables/{args.mart}/{xlsx.name}", "diagram": f"out/deliverables/{args.mart}/{md.name}",
        "required_fields": required, "missing_fields": len(missing), "missing": missing,
        "deferred_fields": len(deferred), "deferred": deferred,
        "contract_version": version, "generated_at": now, "base_commit": head})
    print(xlsx)
    print(md)
    print(f"필수 칸 {required}개 중 누락 {len(missing)}개, 결재 후로 미룸 {len(deferred)}개 → {manifest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
