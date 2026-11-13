"""납품 산출물 생성기 공통 부분: contract·사다리 결과 읽기, 도장, 최신성 검사(--check), manifest 갱신.

단위테스트 결과서(unit_test_report.py)와 테이블·컬럼 정의서(table_spec.py)가 같이 쓴다.
도장(결정 64 ⑤): 표지 시트에 contract_version·생성 시각·기준 커밋(HEAD)을 적고,
--check는 도장이 지금 contract version·HEAD와 다르면 종료 코드 2(halt input_invalid).
이름을 common.py로 하지 않는 이유: scripts/ladder/common.py와 sys.path에서 부딪힌다.
"""
from copy import copy
import json
import re
import subprocess
import sys
from datetime import timedelta, timezone
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / "scripts" / "handover"))
sys.path.insert(0, str(PROJECT / "scripts" / "setup"))
from make_facts import STAMP_LABELS, scrub  # noqa: E402  (도장 이름과 계정·프로젝트 ID 가림, 인수인계와 같은 것)
from kit_local import pick_mart  # noqa: E402,F401  (--mart 생략: contract가 1개면 자동 선택)

KST = timezone(timedelta(hours=9))


class ReportError(Exception):
    """산출물을 만들지 못함 (종료 코드 2)."""


def git(root, *args):
    p = subprocess.run(["git", *args], cwd=root, capture_output=True)
    if p.returncode != 0:
        raise ReportError(f"git {' '.join(args)}: {p.stderr.decode('utf-8', 'replace').strip()[:200]}")
    return p.stdout.decode("utf-8", "replace").strip()


def load_contract(root, mart):
    path = Path(root) / "docs" / "requirements" / f"{mart}.contract.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise ReportError(f"contract를 읽지 못함 ({path.name}): {e.__class__.__name__}") from None


def load_results(dev, mart, version):
    folder = Path(dev) / "ladder_results" / mart
    pattern = re.compile(r".+-v" + str(version) + r"-(\d+)\.json")
    out = []
    for f in sorted(folder.glob(f"*-v{version}-*.json")) if folder.is_dir() else []:
        if pattern.fullmatch(f.name):
            data = json.loads(f.read_text(encoding="utf-8"))
            data["_rel"] = f".dev/ladder_results/{mart}/{f.name}"
            out.append(data)
    return sorted(out, key=lambda r: (r["iteration"], r["ts"]))


def topo_loads(contract):
    tasks = {t["id"]: t for t in contract["dag"]["tasks"]}
    order, seen = [], set()

    def visit(tid):
        if tid in seen or tid not in tasks:
            return
        seen.add(tid)
        for up in tasks[tid]["upstream"]:
            visit(up)
        order.append(tid)
    for tid in tasks:
        visit(tid)
    return [tasks[t] for t in order if tasks[t]["kind"] == "load"]


def last_passed(results, loads, mart, version, what):
    """(반복별 결과 {n: [파일]}, 마지막 통과 반복 n, 그 반복의 pass 파일 {task: 파일}).
    통과 반복 = 모든 load task가 pass인 반복. 없으면 ReportError."""
    by_n = {}
    for r in results:
        by_n.setdefault(r["iteration"], []).append(r)
    load_ids = {t["id"] for t in loads}
    passed = [n for n, files in by_n.items()
              if {f["task"] for f in files if f["verdict"] == "pass"} >= load_ids]
    if not passed:
        raise ReportError(f"{mart} v{version}에 모든 load task가 통과한 반복이 없음. {what}는 사다리 통과 뒤에 만든다")
    n = passed[-1]
    return by_n, n, {f["task"]: f for f in by_n[n] if f["verdict"] == "pass"}


def put(ws, coord_or_rc, value):
    cell = ws[coord_or_rc] if isinstance(coord_or_rc, str) else ws.cell(*coord_or_rc)
    cell.value = scrub(value) if isinstance(value, str) else value
    return cell


def write_stamp(ws, row, version, now, head, style_from=None):
    """row에 "도장" 제목, 그 아래 3줄에 STAMP_LABELS를 쓴다. style_from 셀이 있으면 제목 서식을 따른다."""
    title = put(ws, (row, 1), "도장 (결정 64 ⑤)")
    if style_from is not None:
        title.fill = copy(style_from.fill)
        title.font = copy(style_from.font)
    for i, (label, value) in enumerate(zip(STAMP_LABELS, (version, now, head)), start=1):
        put(ws, (row + i, 1), label)
        put(ws, (row + i, 2), value)
        put(ws, (row + i, 3), "코드 · 최신성 검사(--check) 기준")


def read_stamp(path, sheet="표지"):
    import openpyxl
    ws = openpyxl.load_workbook(path, read_only=True)[sheet]
    stamp = {}
    for row in ws.iter_rows(min_row=1, max_col=2, values_only=True):
        if row[0] in STAMP_LABELS:
            stamp[row[0]] = row[1]
    return stamp


def stamp_problems(stamp, contract, head):
    """도장 {이름: 값}이 지금 contract version·HEAD와 다른 이유 목록. 빈 목록이면 최신 (결정 64 ⑤)."""
    problems = []
    if str(stamp.get("contract_version")) != str(contract["version"]):
        problems.append(f"contract_version 도장 {stamp.get('contract_version')} ≠ 지금 {contract['version']}")
    if stamp.get("기준 커밋") != head:
        problems.append(f"기준 커밋 도장 {str(stamp.get('기준 커밋'))[:8]} ≠ HEAD {head[:8]}")
    return problems


def check(root, mart, prefix, what, file=None):
    """도장 최신성 검사 (결정 64 ⑤). 최신이면 0, 아니면 2(halt input_invalid).
    prefix: 파일 이름 앞부분(UTR·TDS), what: 메시지에 쓰는 산출물 이름."""
    folder = Path(root) / "out" / "deliverables" / mart
    path = Path(file) if file else max(folder.glob(f"{prefix}_{mart}_*.xlsx"), default=None)
    if path is None or not Path(path).exists():
        raise ReportError(f"{what}가 없음 ({folder})")
    contract = load_contract(root, mart)
    head = git(root, "rev-parse", "HEAD")
    problems = stamp_problems(read_stamp(path), contract, head)
    if problems:
        print(f"halt input_invalid: {what} {Path(path).name}이 최신이 아님 — " + "; ".join(problems), file=sys.stderr)
        return 2
    print(f"최신: {Path(path).name} (contract v{contract['version']}, {head[:8]})")
    return 0


def write_manifest(folder, entry):
    """manifest.json의 deliverables 중 entry와 같은 name 항목만 바꾸고 다른 항목·키는 둔다."""
    path = folder / "manifest.json"
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    items = [d for d in data.get("deliverables", []) if d.get("name") != entry["name"]]
    data["deliverables"] = [*items, entry]
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    return path
