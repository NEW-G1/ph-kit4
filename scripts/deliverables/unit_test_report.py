"""단위테스트 결과서 변환기 (진행표 3-6, 양식 docs/templates/unit_test/).

  python scripts/deliverables/unit_test_report.py --mart <마트> [--root R] [--dev-dir D] [--date YYYY-MM-DD] [--force]
  python scripts/deliverables/unit_test_report.py --mart <마트> --check [--file 결과서.xlsx]

- 입력: contract, .dev/ladder_results(마지막 통과 반복), rejections, interventions. 양식 UTR_양식_빈칸.xlsx를 복사해 채운다
- 출력: out/deliverables/<마트>/UTR_<마트>_<YYYYMMDD>.xlsx, out/deliverables/<마트>/manifest.json
  (03 §5.3 형식 deliverables[].required_fields·missing_fields. 같은 이름의 항목만 바꾸고 다른 산출물 항목은 둔다)
- 행의 기준: 마지막 통과 반복(모든 load task가 pass인 반복)의 ladder_result. 통과한 반복이 없으면 만들지 않는다(종료 코드 2)
- 데이터 값은 넣지 않는다: 집계값(행 수·검사 위반 행 수)·바이트·판정만. evidence 행은 옮기지 않고 행 수만 적는다.
  프로젝트 ID·계정은 scripts/handover/make_facts.py의 scrub()으로 가린다
- 표지의 노란 칸(승인자·승인일·승인 PR/의견)은 비운다. L6 행은 최신 L6 결과(<마트>-v<버전>-post-<n>.json 중 가장 큰 n,
  devlog.latest_post)가 있으면 그 판정·누락 수·실행 시각·경로, 없으면 판정 '미실행', 실제값·비고 '미실행(결재 후)' (결정 67)
- 도장(결정 64 ⑤): 표지 아래 "도장" 절에 contract_version·생성 시각·기준 커밋(HEAD)을 적는다.
  --check는 결과서의 도장이 지금 contract version·HEAD와 다르면 종료 코드 2(halt input_invalid)
- 필수 칸('칸 매핑' 시트의 필수=Y): 원천이 없으면 지어내지 않고 비운 뒤 manifest의 missing_fields로 센다.
  L6 판정이 '미실행'(결재 전)이면 L6 행의 실행 시각·증빙은 missing이 아니라 deferred_fields로 센다.
  L6가 실행된 뒤에는 다른 행처럼 필수다 (양식의 '칸 매핑' 시트는 그대로)
  검사의 "위반 0행"은 사다리 검사 쿼리 형식(위반 행을 돌려준다, 0행이면 통과)에서 나온 값이다
- 검사 해시: 검사 행의 시험 방법 칸 끝에 sha256 앞 12자를 붙인다. 값은 .dev/checks_hash/<마트>-v<버전>.json
  (iteration 0에 고정된 값)에서 읽고 지금 파일을 다시 계산하지 않는다. 없으면 비우고 missing으로 센다.
  --check는 그 마트의 검사 파일·게이트 파일이 해시 기록과 다르면 종료 코드 2. 다른 입력(pii_columns.md, 다른 마트의
  게이트)은 비교하지 않는다. 해시 파일이 없으면 비교를 건너뛰고 알린다
- 사다리 밖 항목 시트: 마지막 iteration 0 verifier 응답(RUN 번호가 가장 큰 RUN-*-i0-verifier.md)의 "사다리로 검증되지
  않는 완료 조건"과 가정 항목을 원문 그대로 옮긴다. 판정이 아니다. 절을 못 찾으면 그렇게 적고 missing으로 센다
- 종료 코드: 0 생성·최신, 2 만들지 못함·도장 불일치·검사 파일 불일치·사용 오류
"""
import argparse
from copy import copy
import json
import re
import sys
from datetime import datetime
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / "scripts" / "log"))
sys.path.insert(0, str(PROJECT / "scripts" / "deliverables"))
sys.path.insert(0, str(PROJECT / "scripts" / "loop"))
import devlog  # noqa: E402
import state  # noqa: E402  (해시 파일 경로·줄바꿈 맞춘 sha256을 루프와 같게 쓴다)
from deliv_common import (KST, ReportError, check as check_stamp, git, last_passed,  # noqa: E402
                          load_contract, load_results, pick_mart, put, read_stamp, topo_loads, write_manifest,
                          write_stamp)

TEMPLATE = PROJECT / "docs" / "templates" / "unit_test" / "UTR_양식_빈칸.xlsx"
NAME = "unit_test_report"
FIRST_ROW = 5
STAMP_ROW = 30  # 표지: 양식의 마지막 칸(28행) 아래
CHECK_KIND = {"gates": "gates", "reconciliation": "reconciliation", "invariants": "invariants"}
RESULT_COLS = ["케이스 ID", "task", "레이어", "사다리 단계", "시험 항목", "요구 ID", "검사 ID", "검사 종류",
               "시험 방법 (판정 코드·쿼리)", "사전 조건·입력", "기대값", "실제값", "판정", "error_type", "error_class",
               "반복", "검사 작성", "실행 시각", "증빙 (ladder_result 경로)", "비고"]
# '칸 매핑' 시트의 필수=Y (시트별). 시험 결과의 요구 ID·검사 ID는 L3·L4 행만, error_type·class는 fail 행만 필수
REQUIRED_COVER = {"대상 마트": "B8", "contract 버전": "B11", "노하우 스냅샷": "B12", "최종 판정": "B18"}
REQUIRED_RESULT = ["케이스 ID", "task", "레이어", "사다리 단계", "시험 항목", "시험 방법 (판정 코드·쿼리)", "기대값",
                   "실제값", "판정", "반복", "검사 작성", "실행 시각", "증빙 (ladder_result 경로)"]
REQUIRED_TRACE = ["요구 ID", "요구 내용", "요구서 절", "검사 ID", "단계"]  # 판정은 양식의 수식
REQUIRED_REJECT = ["반려 ID", "시각", "task", "반복", "적발 단계", "error_type", "error_class", "내용"]
# L6가 '미실행'(결재 전)일 때 원천이 아직 없는 칸: missing이 아니라 deferred로 센다
DEFERRED_L6 = ("실행 시각", "증빙 (ladder_result 경로)")
METHOD = "시험 방법 (판정 코드·쿼리)"
HASH_ROW = STAMP_ROW + 4  # 표지: 도장 3줄 아래
OUTSIDE_SHEET = "사다리 밖 항목"
OUTSIDE_COLS = ["구분", "내용", "출처", "결재자 확인"]
OUTSIDE_WIDTHS = (34, 100, 58, 14)
KIND_OUTSIDE, KIND_ASSUMED = "사다리로 검증되지 않는 완료 조건", "verifier 가정"
NOT_FOUND = "verifier 보고에서 절을 찾지 못함"
VERIFIER_FILE = re.compile(r"RUN-(\d+)-i0-verifier\.md")
# verifier 응답의 절 제목: "## 제목" 또는 한 줄 전체가 굵은 글씨. 가정은 "…가정한 것" 또는 "사람이 볼 것" 절에 있다
HEADING = re.compile(r"(?:#{1,6}\s+(.+?)|\*\*([^*]+)\*\*:?)\s*")
ASSUMED_TITLES = ("가정", "사람이 볼 것")
OUTSIDE_ITEM = re.compile(r"[-*]\s+\*\*" + KIND_OUTSIDE)  # 절이 아니라 목록 항목 하나로 쓴 경우


def short_ts(ts):
    return ts[:16].replace("T", " ") if isinstance(ts, str) else ""


# ---------- 내용 계산 ----------

def load_check_hashes(dev, mart, version):
    """iteration 0에 고정된 {경로: sha256}. 없거나 읽지 못하면 None."""
    try:
        return json.loads(state.hash_file(dev, mart, version).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def latest_verifier(dev, mart):
    """RUN 번호가 가장 큰 iteration 0 verifier 응답 파일. 없으면 None."""
    found = [(int(m[1]), f) for f in (Path(dev) / "agent_responses" / mart).glob("RUN-*-i0-verifier.md")
             if (m := VERIFIER_FILE.fullmatch(f.name))]
    return max(found)[1] if found else None


def verifier_items(text):
    """{종류: [(원래 절 제목, 원문 항목)]}. 항목은 들여쓰지 않은 줄 하나와 그 아래 들여쓴 줄이다. 문장은 고치지 않는다.
    다른 절 안의 목록 항목 하나로 쓴 사다리 밖 항목은 그 항목의 제목(KIND_OUTSIDE)을 절 제목으로 본다."""
    sections = [("", [])]
    for line in text.splitlines():
        m = HEADING.fullmatch(line)
        if m:
            sections.append((m[1] or m[2], []))
        elif line.strip():
            items = sections[-1][1]
            if line[0].isspace() and items:
                items[-1] += "\n" + line.rstrip()
            else:
                items.append(line.rstrip())
    out = {KIND_OUTSIDE: [], KIND_ASSUMED: []}
    for title, items in sections:
        for item in items:
            if KIND_OUTSIDE in title:
                out[KIND_OUTSIDE].append((title, item))
            elif OUTSIDE_ITEM.match(item):
                out[KIND_OUTSIDE].append((KIND_OUTSIDE, item))
            elif any(word in title for word in ASSUMED_TITLES):
                out[KIND_ASSUMED].append((title, item))
    return out


class Facts:
    def __init__(self, root, dev, mart):
        self.root, self.dev, self.mart = Path(root), Path(dev), mart
        self.contract = load_contract(root, mart)
        self.version = self.contract["version"]
        self.results = load_results(dev, mart, self.version)
        self.loads = topo_loads(self.contract)
        self.by_n, self.n, self.files = last_passed(self.results, self.loads, mart, self.version, "결과서")
        self.checks = {c["id"]: {**c, "kind": kind} for kind, group in self.contract["checks"].items() for c in group}
        self.reqs = {}
        for t in self.contract["traces_to"]:
            self.reqs.setdefault(t["check"], []).append(t["req"])
        self.rejections = [r for r in devlog.read_lines(self.dev / "rejections.jsonl")
                           if r.get("mart") == mart and r.get("contract_version") == self.version]
        self.interventions = [r for r in devlog.read_lines(self.dev / "interventions.jsonl") if r.get("mart") == mart]
        self.hashes = load_check_hashes(dev, mart, self.version)
        self.verifier = latest_verifier(dev, mart)
        self.outside = verifier_items(self.verifier.read_text(encoding="utf-8") if self.verifier else "")

    def rung(self, task, name):
        return next((g for g in self.files[task]["rungs"] if g["rung"] == name), None)

    def gate_of(self, layer):
        return next((t["id"] for t in self.contract["dag"]["tasks"] if t["kind"] == "gate" and t["layer"] == layer), "")

    def rows(self):
        """시험 결과 행 목록 (dict, 키는 RESULT_COLS)."""
        rows, ran = [], set()
        first = next(iter(self.files.values()))
        l0 = first["rungs"][0]
        all_files = ", ".join(self.files[t["id"]]["_rel"] for t in self.loads)
        m = l0["metrics"]
        counts = (f"적재 task {m.get('load_tasks')}, 게이트 task {m.get('gate_tasks')}, 테이블 {m.get('tables')}, "
                  f"검사 {m.get('checks')}, 추적 {m.get('traces')}")
        base = {"task": "(contract 전체)", "레이어": "-", "사다리 단계": "L0", "요구 ID": "-", "검사 ID": "-",
                "검사 종류": "-", "사전 조건·입력": f"contract v{self.version}", "판정": l0["status"],
                "반복": str(self.n), "검사 작성": "code", "실행 시각": short_ts(first["ts"]),
                "증빙 (ladder_result 경로)": all_files}
        rows.append({**base, "케이스 ID": f"UT-{self.mart}-L0-01",
                     "시험 항목": "contract.json 형식(인터뷰 필수 칸·traces_to·요구 전부 추적, task 설계 규칙)",
                     "시험 방법 (판정 코드·쿼리)": "scripts/ladder/l0_contract.py", "기대값": "오류 0",
                     "실제값": f"오류 0 ({counts})", "비고": "metrics.stage=contract"})
        rows.append({**base, "케이스 ID": f"UT-{self.mart}-L0-02",
                     "시험 항목": "DAG import, task 목록·의존성 = contract, SQL 파일과 task 1:1, 검증 쿼리 머리말",
                     "시험 방법 (판정 코드·쿼리)": "scripts/ladder/l0_dag.py", "사전 조건·입력": "dags/harness_daily.py",
                     "기대값": "불일치 0, 고아 0", "실제값": "불일치 0, 고아 0" if m.get("dag") == "pass" else "",
                     "비고": "metrics.dag"})
        for t in self.loads:
            f = self.files[t["id"]]
            seq = {}

            def add(name, **cells):
                seq[name] = seq.get(name, 0) + 1
                g = self.rung(t["id"], name)
                rows.append({"케이스 ID": f"UT-{t['id']}-{name}-{seq[name]:02d}", "task": t["id"], "레이어": t["layer"],
                             "사다리 단계": name, "요구 ID": "-", "검사 ID": "-", "검사 종류": "-",
                             "판정": g["status"] if g else "미실행", "error_type": (g or {}).get("error_type") or "",
                             "error_class": (g or {}).get("error_class") or "", "반복": str(self.n),
                             "검사 작성": "code", "실행 시각": short_ts(f["ts"]),
                             "증빙 (ladder_result 경로)": f["_rel"], "비고": "", **cells})

            sql = f"dags/sql/{t['layer']}/{t['id']}.sql"
            ds = f"ds={(self.rung(t['id'], 'L1') or {}).get('ds')}"
            l1 = self.rung(t["id"], "L1")
            b = (l1 or {}).get("metrics", {}).get("bytes_processed")
            add("L1", **{"시험 항목": "dry-run 문법·스캔량", "시험 방법 (판정 코드·쿼리)": "scripts/ladder/l1_dryrun.py (bq --dry_run, ai_dev 렌더링)",
                         "사전 조건·입력": f"{sql}, {ds}", "기대값": "통과, ≤ 524,288,000 B",
                         "실제값": f"통과, {b:,} B" if isinstance(b, int) else "",
                         "비고": "여러 문장 스크립트는 하한값" if (l1 or {}).get("metrics", {}).get("bytes_accuracy") == "LOWER_BOUND" else ""})
            l2 = self.rung(t["id"], "L2")
            table = (l2 or {}).get("metrics", {}).get("table")
            add("L2", **{"시험 항목": "ai_dev 실행 성공, contract 테이블 생성", "시험 방법 (판정 코드·쿼리)": "scripts/ladder/l2_run.py",
                         "사전 조건·입력": f"{sql}, {ds}", "기대값": "성공, 테이블 있음",
                         "실제값": f"성공, 테이블 {table} 있음" if table else ""})
            for name, stage in (("L3", "l3"), ("L4", "l4"), ("L5", "l5")):
                g = self.rung(t["id"], name)
                if name == "L3":
                    gate = (g or {}).get("metrics", {}).get("gate") or self.gate_of(t["layer"])
                    sha = (g or {}).get("metrics", {}).get("gate_sha256")
                    add("L3", **{"시험 항목": "게이트 파일 = l3 원본에서 생성한 결과 (해시 비교)",
                                 "시험 방법 (판정 코드·쿼리)": "scripts/ladder/l3_gate.py, scripts/ladder/gen_dq.py",
                                 "사전 조건·입력": f"dags/sql/dq/{gate}.sql", "기대값": "해시 일치",
                                 "실제값": f"해시 일치 (sha256 {sha[:12]})" if sha else ""})
                if name == "L5":
                    rc = (g or {}).get("metrics", {}).get("row_count")
                    add("L5", **{"시험 항목": "같은 ds 2회 실행 행 수·체크섬 동일", "시험 방법 (판정 코드·쿼리)": "scripts/ladder/l5_idem.py",
                                 "사전 조건·입력": f"{sql}, {ds}", "기대값": "2회 행 수·체크섬 동일",
                                 "실제값": f"동일 (ds 파티션 행 수 {rc})" if rc is not None else ""})
                for cid in (g or {}).get("metrics", {}).get("checks", []):
                    ran.add(cid)
                    c = self.checks.get(cid, {})
                    method = f"docs/requirements/{self.mart}_checks/{stage}/{cid}.sql"
                    check_sha = (self.hashes or {}).get(method)
                    if name == "L3":
                        method += f" → dags/sql/dq/{self.gate_of(t['layer'])}.sql"
                    if check_sha:
                        method += f" (sha256 {check_sha[:12]})"
                    add(name, **{"시험 항목": c.get("rule", ""), "요구 ID": ", ".join(self.reqs.get(cid, [])),
                                 "검사 ID": cid, "검사 종류": CHECK_KIND.get(c.get("kind"), ""),
                                 METHOD: method, "사전 조건·입력": ds, "기대값": "위반 0행",
                                 "실제값": "위반 0행", "검사 작성": c.get("written_by", ""), "검사 해시": check_sha})
        for cid, c in self.checks.items():  # contract에는 있는데 마지막 통과 반복에서 실행 기록이 없는 검사
            if cid in ran:
                continue
            rows.append({"케이스 ID": f"UT-{self.mart}-{c['rung']}-{cid}", "task": "-", "레이어": "-",
                         "사다리 단계": c["rung"], "시험 항목": c["rule"], "요구 ID": ", ".join(self.reqs.get(cid, [])),
                         "검사 ID": cid, "검사 종류": c["kind"], "판정": "미실행", "반복": str(self.n),
                         "검사 작성": c.get("written_by", ""), "비고": "마지막 통과 반복에서 실행 기록 없음"})
        rows.append(self.l6_row())
        return rows

    def l6_row(self):
        """L6 행. 최신 L6 결과(post-<n> 중 가장 큰 n, devlog.latest_post)가 있으면 그 값, 없으면 '미실행' (결정 67)."""
        row = {"케이스 ID": f"UT-{self.mart}-L6-01", "task": "(contract 전체)", "레이어": "-",
               "사다리 단계": "L6", "시험 항목": "OM 등록: contract 테이블 존재, 컬럼 설명 누락 0, 리니지 엣지 = contract 기대값 (결정 47)",
               "요구 ID": "-", "검사 ID": "-", "검사 종류": "-", "시험 방법 (판정 코드·쿼리)": "scripts/ladder/l6_om.py",
               "사전 조건·입력": "운영 DAG 실행·OM 에이전트 실행 뒤", "기대값": "누락 0, 엣지 일치",
               "실제값": "미실행(결재 후)", "판정": "미실행", "반복": "post", "검사 작성": "code",
               "비고": "미실행(결재 후)"}
        latest = devlog.latest_post(self.mart, self.mart, self.version, self.dev)
        if latest is None:
            return row
        g = next((x for x in latest.get("rungs", []) if x.get("rung") == "L6"), {})
        m = g.get("metrics", {})
        count = len(devlog.post_files(self.dev / "ladder_results" / self.mart, self.mart, self.version))
        return {**row, "판정": g.get("status") or "미실행", "error_type": g.get("error_type") or "",
                "error_class": g.get("error_class") or "", "반복": f"post-{latest['_n']}",
                "실제값": (f"테이블 없음 {len(m.get('tables_missing', []))}, 설명 누락 {len(m.get('description_missing', []))}, "
                         f"엣지 누락 {len(m.get('edges_missing', []))}"),
                "실행 시각": short_ts(latest.get("ts")),
                "증빙 (ladder_result 경로)": f".dev/ladder_results/{self.mart}/{latest['_name']}",
                "비고": (f"L6 실행 {count}회 중 최신 post-{latest['_n']}. 보고만: 기대 밖 엣지 "
                       f"{len(m.get('edges_unexpected', []))}, 원천 엣지 {len(m.get('source_edges', []))}")}

    def fixed_in(self, rej):
        if rej["iteration"] == "post":  # L6 반려: 그 뒤 통과한 첫 L6 순번 파일 (결정 67)
            n = devlog.post_fixed_in(rej, devlog.post_results(self.mart, rej["task"], self.version, self.dev))
            return f"post-{n}" if n else ""
        later = [n for n, files in self.by_n.items() if n > rej["iteration"]
                 and any(f["task"] == rej["task"] and f["verdict"] == "pass" for f in files)]
        return str(min(later)) if later else ""

    def outside_summary(self):
        counts = [f"{kind} {len(self.outside[kind])}건" if self.outside[kind] else f"{kind} 절 찾지 못함"
                  for kind in (KIND_OUTSIDE, KIND_ASSUMED)]
        return f"'{OUTSIDE_SHEET}' 시트: {', '.join(counts)} (verifier 보고, 판정 아님)"

    def cover(self, branch):
        last_n = max(self.by_n)
        last = self.by_n[last_n]
        verdicts = {f["verdict"] for f in last}
        last_verdict = "reject" if "reject" in verdicts else "halt" if "halt" in verdicts else "pass"
        final = f"{last_verdict} (마지막 반복 {last_n})"
        if last_n != self.n:
            final += f", 결과서 행은 마지막 통과 반복 {self.n} 기준"
        counts = {"pass": 0, "reject": 0, "halt": 0}
        halts = []
        for n, files in self.by_n.items():
            vs = {f["verdict"] for f in files}
            v = "reject" if "reject" in vs else "halt" if "halt" in vs else "pass"
            counts[v] += 1
            halts += [f"반복 {n} {f['halt_reason']}" for f in files if f["verdict"] == "halt"]
        expert = self.files[self.loads[0]["id"]]["modules"]["expert"]
        tasks = self.contract["dag"]["tasks"]
        loads = [t["id"] for t in tasks if t["kind"] == "load"]
        gates = [t["id"] for t in tasks if t["kind"] == "gate"]
        ts = [r["ts"] for r in self.results]
        return {
            "B8": self.mart, "B9": f"적재: {', '.join(loads)} / 게이트: {', '.join(gates)} ({len(tasks)}개)",
            "B10": f"{branch} / PR 번호 없음(생성 시점)", "B11": f"v{self.version}",
            "B12": f"on: {json.dumps(expert['on'], ensure_ascii=False)} / version: {json.dumps(expert['version'])}",
            "B13": "본 측정 (노하우 꺼짐)" if not expert["on"] else "노하우 켜짐",
            "B15": f"{short_ts(min(ts))} ~ {short_ts(max(ts))}", "B18": final,
            "B20": f"마트 실행 반복 {len(self.by_n)}회 (pass {counts['pass']}, reject {counts['reject']}, halt {counts['halt']})",
            "B21": "; ".join(halts) if halts else "없음", "B22": self.outside_summary(),
            "B25": f".dev/ladder_results/{self.mart}/ (반복 {self.n}, verdict=pass)",
        }


# ---------- 쓰기 ----------

def header_cols(ws, row=4):
    return {ws.cell(row, c).value: c for c in range(1, ws.max_column + 1) if ws.cell(row, c).value}


def build(root, dev, mart, day, now, head, branch):
    """(workbook, required, missing 목록, deferred 목록). 목록 원소는 "시트!셀 칸"."""
    import openpyxl
    facts = Facts(root, dev, mart)
    wb = openpyxl.load_workbook(TEMPLATE)
    missing, deferred, required = [], [], 0

    def need(ws, coord, label, deferrable=False):
        nonlocal required
        required += 1
        v = ws[coord].value
        if v is None or (isinstance(v, str) and not v.strip()):
            (deferred if deferrable else missing).append(f"{ws.title}!{coord} {label}")

    cover = wb["표지"]
    put(cover, "B6", f"UTR-{mart}-{day.replace('-', '')}")
    put(cover, "B16", day)
    for coord, value in facts.cover(branch).items():
        put(cover, coord, value)
    for coord in ("B26", "B27", "B28"):  # 노란 칸: 사람이 결재 때 쓴다
        cover[coord].value = None
    write_stamp(cover, STAMP_ROW, facts.version, now, head, style_from=cover["A23"])
    put(cover, (HASH_ROW, 1), "검사 해시 기록")
    put(cover, (HASH_ROW, 3), "코드 · 검사 파일 비교(--check) 기준")
    if facts.hashes is not None:
        put(cover, (HASH_ROW, 2), f".dev/checks_hash/{mart}-v{facts.version}.json (iteration 0 커밋, 매 반복 사다리 전 비교)")
    for label, coord in {**REQUIRED_COVER, "검사 해시 기록": f"B{HASH_ROW}"}.items():
        need(cover, coord, label)

    ws = wb["시험 결과"]
    cols = header_cols(ws)
    for i, row in enumerate(facts.rows()):
        r = FIRST_ROW + i
        for name in RESULT_COLS:
            value = row.get(name, "")
            if value not in ("", None):
                put(ws, (r, cols[name]), value)
        letters = {name: ws.cell(r, cols[name]).column_letter for name in RESULT_COLS}
        conditional = []
        if row.get("사다리 단계") in ("L3", "L4") and row.get("판정") != "미실행":
            conditional += ["요구 ID", "검사 ID"]
        if row.get("판정") == "fail":
            conditional += ["error_type", "error_class"]
        l6_pending = row.get("사다리 단계") == "L6" and row.get("판정") == "미실행"
        for name in REQUIRED_RESULT + conditional:
            need(ws, f"{letters[name]}{r}", name, deferrable=l6_pending and name in DEFERRED_L6)
        if "검사 해시" in row:
            required += 1
            if not row["검사 해시"]:
                missing.append(f"{ws.title}!{letters[METHOD]}{r} 검사 해시")

    tr = wb["요구 추적"]
    tcols = header_cols(tr)
    reqs = {q["id"]: q for q in facts.contract["requirements"]}
    for i, t in enumerate(facts.contract["traces_to"]):
        r = FIRST_ROW + i
        q = reqs.get(t["req"], {})
        values = {"요구 ID": t["req"], "요구 내용": q.get("text", ""), "요구서 절": q.get("section"),
                  "검사 ID": t["check"], "단계": t["rung"]}
        for name, value in values.items():
            if value not in ("", None):
                put(tr, (r, tcols[name]), value)
        for name in REQUIRED_TRACE:
            need(tr, f"{tr.cell(r, tcols[name]).column_letter}{r}", name)

    rj = wb["반려 이력"]
    rcols = header_cols(rj)
    r = FIRST_ROW
    for rej in facts.rejections:
        ev = rej.get("evidence")
        values = {"반려 ID": rej["id"], "시각": short_ts(rej["ts"]), "task": rej["task"], "반복": rej["iteration"],
                  "적발 단계": rej["caught_by_rung"], "error_type": rej["error_type"], "error_class": rej["error_class"],
                  "내용": rej["detail"],
                  "증빙 (2번째 같은 유형부터)": "" if ev is None else
                  f"있음({len(ev) if isinstance(ev, list) else 1}행, 값은 옮기지 않음, .dev/rejections.jsonl)",
                  "고친 반복 (집계)": facts.fixed_in(rej)}
        for name, value in values.items():
            if value not in ("", None):
                put(rj, (r, rcols[name]), value)
        for name in REQUIRED_REJECT:
            need(rj, f"{rj.cell(r, rcols[name]).column_letter}{r}", name)
        r += 1
    r += 1
    put(rj, (r, 1), "개입 기록 (.dev/interventions.jsonl, 같은 마트, 해석 없이 그대로)")
    r += 1
    if facts.interventions:
        for c, name in enumerate(("ID", "시각", "종류", "단계", "대상", "분", "메모"), start=1):
            put(rj, (r, c), name)
        for i in facts.interventions:
            r += 1
            for c, value in enumerate((i["id"], short_ts(i["ts"]), i["kind"], i.get("stage") or "-",
                                       i.get("target", ""), i.get("minutes_spent"), i.get("note") or "-"), start=1):
                put(rj, (r, c), value)
    else:
        put(rj, (r, 1), "개입 기록 없음")

    required += 2  # 사다리 밖 항목 시트의 두 절
    missing += write_outside(wb, facts)
    return wb, required, missing, deferred


def write_outside(wb, facts):
    """'사다리 밖 항목' 시트를 '요구 추적' 뒤에 만든다. 찾지 못한 절의 missing 목록을 돌려준다."""
    from openpyxl.styles import Alignment
    trace = wb["요구 추적"]
    ws = wb.create_sheet(OUTSIDE_SHEET, wb.sheetnames.index(trace.title) + 1)
    put(ws, "A1", "verifier 보고 원문, 판정 아님").font = copy(trace["A1"].font)
    for c, (name, width) in enumerate(zip(OUTSIDE_COLS, OUTSIDE_WIDTHS), start=1):
        cell = put(ws, (FIRST_ROW - 1, c), name)
        cell.font, cell.fill = copy(trace["A4"].font), copy(trace["A4"].fill)
        ws.column_dimensions[cell.column_letter].width = width
    source = f".dev/agent_responses/{facts.mart}/{facts.verifier.name}" if facts.verifier else "(verifier 응답 파일 없음)"
    yellow = wb["표지"]["B26"].fill
    missing, r = [], FIRST_ROW
    for kind in (KIND_OUTSIDE, KIND_ASSUMED):
        if not facts.outside[kind]:
            missing.append(f"{ws.title}!B{r} {kind}")
        for title, text in facts.outside[kind] or [(kind, NOT_FOUND)]:
            for c, value in enumerate((title, text, source), start=1):
                put(ws, (r, c), value).alignment = Alignment(wrap_text=True, vertical="top")
            ws.cell(r, 4).fill = copy(yellow)
            r += 1
    return missing


def changed_checks(root, dev, mart, contract):
    """해시 기록과 다른 그 마트의 검사·게이트 파일 목록. 해시 파일이 없으면 None."""
    saved = load_check_hashes(dev, mart, contract["version"])
    if saved is None:
        return None
    now = state.hash_targets(root, mart)
    gates = {f"dags/sql/dq/{t['id']}.sql" for t in contract["dag"]["tasks"] if t["kind"] == "gate"}
    return sorted(k for k in set(saved) | set(now) if saved.get(k) != now.get(k)
                  and (k.startswith(f"docs/requirements/{mart}_checks/") or k in gates))


def check(root, dev, mart, file=None):
    """도장 최신성 검사 (결정 64 ⑤) + 검사 파일 비교. 둘 다 맞으면 0, 아니면 2(halt input_invalid)."""
    code = check_stamp(root, mart, "UTR", "결과서", file)
    changed = changed_checks(root, dev, mart, load_contract(root, mart))
    if changed is None:
        print("검사 해시 기록이 없어 검사 파일을 비교하지 않음", file=sys.stderr)
    elif changed:
        print("halt input_invalid: 결과서가 보여 준 SQL과 저장소의 SQL이 다름 — " + ", ".join(changed), file=sys.stderr)
        return 2
    return code


def parse_args(argv):
    p = argparse.ArgumentParser(description="단위테스트 결과서 변환기 (진행표 3-6)")
    p.add_argument("--mart", help="마트. contract가 1개면 생략 가능(자동 선택)")
    p.add_argument("--root", default=str(PROJECT))
    p.add_argument("--dev-dir", help="기본: <root>/.dev")
    p.add_argument("--date", help="작성일 YYYY-MM-DD (기본: 오늘 +09:00)")
    p.add_argument("--force", action="store_true", help="같은 날짜 결과서가 있으면 덮어씀 (사람이 쓴 노란 칸이 사라진다)")
    p.add_argument("--check", action="store_true", help="결과서 도장이 지금 contract version·HEAD와 같은지, 검사 파일이 해시 기록과 같은지 검사")
    p.add_argument("--file", help="--check 대상 (기본: out/deliverables/<마트>/의 마지막 결과서)")
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
        print("openpyxl이 없어 결과서를 만들 수 없음 (설치는 사람이 한다)", file=sys.stderr)
        return 2
    try:
        dev = Path(args.dev_dir) if args.dev_dir else root / ".dev"
        if args.check:
            return check(root, dev, args.mart, args.file)
        now = now or datetime.now(KST).isoformat(timespec="seconds")
        day = args.date or now[:10]
        head = git(root, "rev-parse", "HEAD")
        branch = git(root, "rev-parse", "--abbrev-ref", "HEAD")
        folder = root / "out" / "deliverables" / args.mart
        out = folder / f"UTR_{args.mart}_{day.replace('-', '')}.xlsx"
        if out.exists() and not args.force:
            raise ReportError(f"이미 있음: {out.name}. 덮어쓰지 않는다 (--force)")
        wb, required, missing, deferred = build(root, dev, args.mart, day, now, head, branch)
        folder.mkdir(parents=True, exist_ok=True)
        wb.save(out)
    except (ReportError, devlog.DevlogError, KeyError, ValueError, OSError) as e:
        print(f"결과서를 만들지 못함: {e.__class__.__name__}: {e}", file=sys.stderr)
        return 2
    manifest = write_manifest(folder, {
        "name": NAME, "file": f"out/deliverables/{args.mart}/{out.name}", "required_fields": required,
        "missing_fields": len(missing), "missing": missing, "deferred_fields": len(deferred), "deferred": deferred,
        "contract_version": wb["표지"].cell(STAMP_ROW + 1, 2).value, "generated_at": now, "base_commit": head})
    print(out)
    print(f"필수 칸 {required}개 중 누락 {len(missing)}개, 결재 후로 미룸 {len(deferred)}개 → {manifest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
