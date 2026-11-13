"""테이블·컬럼 정의서 생성기 (진행표 4-4 정의서 부분, 기준 docs/templates/standards_survey.md §2).

  python scripts/deliverables/table_spec.py --mart <마트> [--root R] [--dev-dir D] [--date YYYY-MM-DD] [--force]
  python scripts/deliverables/table_spec.py --mart <마트> --check [--file 정의서.xlsx]

- 항목 구성: 행정안전부 「공공기관의 데이터베이스 표준화 지침」 [별표 4] 메타데이터 표준관리항목의
  3. 테이블 정보·4. 컬럼 정보(S1·S2). 필수(*) 여부도 별표 그대로. 표지는 §2.3 범위만(담당자 연락처 없음)
- 입력: contract, docs/architecture/pii_columns.md, .dev/ladder_results(마지막 통과 반복),
  docs/requirements/<마트>_checks/<단계>/<검사 ID>.sql (verifier 검사 쿼리, 있으면)
- 출력: out/deliverables/<마트>/TDS_<마트>_<YYYYMMDD>.xlsx (시트: 안내, 표지, 테이블 정보, 컬럼 정보),
  out/deliverables/<마트>/manifest.json의 table_spec 항목 (다른 항목은 둔다)
- 칸 원천 (§2.1·2.2 표):
  · 한글 테이블명·한글 컬럼명: contract name_ko. 비면 "미작성"(결정 53)이라 적고 missing으로 센다
  · 테이블 소유자: "미지정(결재 후 OM Owner)"이라 적고 deferred로 센다
  · 테이블 볼륨: 마지막 통과 반복의 L2 metrics.row_count(집계값). L2에 없으면 같은 반복 L5의 ds 파티션 행 수를
    쓰고 칸에 출처를 적는다. 둘 다 없으면 비운다(필수 아님)
  · 데이터 길이: "해당 없음(BigQuery)". PK: 키 컬럼이면 "논리 키(BigQuery PK 미강제, 고유성은 사다리 검사로 확인): <키 컬럼>", 아니면 "아님"
  · Not Null: 마지막 통과 반복에서 통과한 L3 게이트 검사의 쿼리가 그 테이블의 그 컬럼을 IS NULL로 잡으면
    "예(C-xx)", 아니면 "미보장". LEFT JOIN으로 붙은 테이블 쪽의 IS NULL(짝 없음 검사)은 보장으로 보지 않는다
  · 제약조건: 그 컬럼을 다루는 contract checks의 ID. 검사 쿼리가 그 테이블을 읽으며 컬럼 이름을 참조하면 다룬다고
    본다(별칭으로 테이블을 가리고, 별칭이 없으면 그 컬럼을 가진 테이블. 파티션 필터·조인의 파티션 컬럼은 제외.
    파티션 컬럼은 contract에서 읽는다: snapshot이면 snapshot_date, incremental이면 load.partition_column, 결정 79). 쿼리 파일이 없으면 검사 rule 문장에 테이블·컬럼 이름이
    함께 있는지로 본다
  · 개인정보 여부: pii_columns.md. raw_<원천> 테이블의 목록 컬럼이면 "예", stg·mart는 컬럼 이름이 목록에 있으면 "예"
    (L0가 막으므로 정상이면 없다), 그 밖은 "아니오"
  · 암호화 여부·공개/비공개 여부: §2.2 고정값
- 데이터 값·담당자 이름·연락처는 넣지 않는다. 프로젝트 ID·계정은 make_facts.scrub()으로 가린다
- 도장·--check·manifest는 unit_test_report.py와 같다(deliv_common, 결정 64 ⑤)
- 종료 코드: 0 생성·최신, 2 만들지 못함·도장 불일치·사용 오류
"""
import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / "scripts" / "deliverables"))
sys.path.insert(0, str(PROJECT / "scripts" / "ladder"))
from deliv_common import (KST, ReportError, check as check_stamp, git, last_passed, load_contract,  # noqa: E402
                          load_results, pick_mart, put, read_stamp, topo_loads, write_manifest, write_stamp)
import load_mode  # noqa: E402
from l0_contract import load_pii, strip_sql  # noqa: E402  (L0와 같은 목록·같은 SQL 정리)

NAME = "table_spec"
PREFIX = "TDS"
SYSTEM = "pipeline-harness"
DBMS = "BigQuery"
UNWRITTEN = "미작성"
OWNER = "미지정(결재 후 OM Owner)"
PUBLIC = "비공개 (내부 PoC, 합성 데이터)"
LENGTH = "해당 없음(BigQuery)"
PK_TEXT = "논리 키(BigQuery PK 미강제, 고유성은 사다리 검사로 확인)"
NOT_KEY = "아님"
FK_TEXT = "없음(물리 FK 없음, 상위 테이블은 흐름도)"
NOT_GUARANTEED = "미보장"
ENCRYPT = {"raw": "아니오(합성 데이터)"}
ENCRYPT_BLOCKED = "해당 없음(전달 차단)"
OPEN_DATA = "해당 없음"
HEADER_ROW = 4
FIRST_ROW = 5

# (열 이름, S2 필수) — S2 [별표 4] 3. 테이블 정보·4. 컬럼 정보 순서
TABLE_COLS = [("테이블 소유자", True), ("한글 테이블명", True), ("영문 테이블명", True), ("테이블 유형", False),
              ("테이블 볼륨", False), ("발생주기", False), ("공개/비공개 여부", True), ("개방데이터목록", False)]
COLUMN_COLS = [("한글 컬럼명", True), ("영문 컬럼명", True), ("데이터 타입", True), ("데이터 길이", False),
               ("Not Null 여부", True), ("PK 정보", True), ("FK 정보", False), ("제약조건", False),
               ("개인정보 여부", True), ("암호화 여부", True), ("공개/비공개 여부", True)]
# 칸 원천 (standards_survey.md §2.1·2.2 표 그대로). 안내 시트에 싣는다
SOURCES = [
    ("테이블 정보", "테이블 소유자", "*", "OM 테이블 Owner (아직 미등록)", "코드", f"'{OWNER}' (결재 후로 미룸, deferred)"),
    ("테이블 정보", "한글 테이블명", "*", "contract tables[].name_ko (선택 칸)", "AI 초안 → 결재 1", f"결정 53: 비면 '{UNWRITTEN}' (missing)"),
    ("테이블 정보", "영문 테이블명", "*", "contract tables[].name", "코드", ""),
    ("테이블 정보", "테이블 유형", "", "contract tables[].layer (raw·stg·mart)", "코드", ""),
    ("테이블 정보", "테이블 볼륨", "", "마지막 통과 반복 L2 row_count (집계값)", "코드", "L2에 없으면 L5 ds 파티션 행 수, 출처 표기"),
    ("테이블 정보", "발생주기", "", "contract schedule.refresh", "코드", ""),
    ("테이블 정보", "공개/비공개 여부", "*", "고정값", "코드", PUBLIC),
    ("테이블 정보", "개방데이터목록", "", "—", "—", OPEN_DATA),
    ("컬럼 정보", "한글 컬럼명", "*", "contract columns[].name_ko (선택 칸)", "AI 초안 → 결재 1",
     f"결정 53: 비면 '{UNWRITTEN}' (missing). S3 공통표준용어 미적용(사유: 합성 데이터 PoC)"),
    ("컬럼 정보", "영문 컬럼명", "*", "contract columns[].name", "코드", ""),
    ("컬럼 정보", "데이터 타입", "*", "contract columns[].type", "코드", "OM·BigQuery 스키마와 같아야 함(L2)"),
    ("컬럼 정보", "데이터 길이", "", "—", "코드", LENGTH),
    ("컬럼 정보", "Not Null 여부", "*", "L3 게이트 검사 쿼리의 IS NULL (마지막 통과 반복에서 통과)", "코드",
     f"'예(검사 ID)' 또는 '{NOT_GUARANTEED}'"),
    ("컬럼 정보", "PK 정보", "*", "contract tables[].keys", "코드", f"'{PK_TEXT}: 키 컬럼' 또는 '{NOT_KEY}'"),
    ("컬럼 정보", "FK 정보", "", "contract dag.tasks[].upstream·리니지", "코드", FK_TEXT),
    ("컬럼 정보", "제약조건", "", "contract checks 중 그 컬럼을 다루는 검사 ID", "코드",
     "검사 쿼리가 테이블을 읽고 컬럼 이름을 참조(이름 기준). 쿼리가 없으면 rule 문장"),
    ("컬럼 정보", "개인정보 여부", "*", "docs/architecture/pii_columns.md (결정 51 ⑦)", "코드", "raw_<원천>의 목록 컬럼은 '예'"),
    ("컬럼 정보", "암호화 여부", "*", "고정값", "코드", f"raw '{ENCRYPT['raw']}', stg·mart '{ENCRYPT_BLOCKED}'"),
    ("컬럼 정보", "공개/비공개 여부", "*", "고정값", "코드", PUBLIC),
]
CITATIONS = [
    ("S1", "「공공기관의 데이터베이스 표준화 지침」 행정안전부고시 제2025-19호 (2025.2.24 시행)",
     "https://law.go.kr/LSW//admRulInfoP.do?admRulSeq=2100000255382&chrClsCd=010201"),
    ("S2", "위 지침 [별표 4] 메타데이터 표준관리항목 (3. 테이블 정보, 4. 컬럼 정보)",
     "https://www.law.go.kr/LSW/flDownload.do?flSeq=149511281"),
]


def partition_filter(column):
    """파티션 필터·파티션 조인 조건(<컬럼> = ds, a.<컬럼> = b.<컬럼>)은 컬럼 규칙이 아니라 지운다.
    컬럼은 contract의 파티션 컬럼(load_mode.partition_column, 결정 79)."""
    c = re.escape(column.lower())
    return re.compile(rf"(?:\w+\.)?{c}\s*=\s*(?:date\(\s*\)|(?:\w+\.)?{c})")


PARTITION_FILTER = partition_filter(load_mode.SNAPSHOT_COLUMN)
SEGMENT_SPLIT = re.compile(r"\bunion\s+all\b|\)\s*,\s*\w+\s+as\s*\(|\bwith\b")
TABLE_REF = re.compile(r"\b(left\s+(?:outer\s+)?join|join|from)\s+([\w.]+)(?:\s+(?:as\s+)?(\w+))?")
IS_NULL = re.compile(r"(?<![\w.])(?:(\w+)\.)?(\w+)\s+is\s+null\b")
NOT_ALIAS = {"where", "on", "using", "group", "order", "having", "left", "right", "inner", "outer", "full", "cross",
             "join", "union", "window", "qualify", "limit", "select", "as"}


class Segment:
    """검사 쿼리의 UNION ALL·CTE 조각 하나: 읽는 테이블, 별칭, LEFT JOIN으로 붙은 테이블."""

    def __init__(self, text):
        self.text, self.alias, self.tables, self.left = text, {}, set(), set()
        for how, ref, alias in TABLE_REF.findall(text):
            table = ref.split(".")[-1]
            self.tables.add(table)
            self.alias[table] = table
            if alias and alias not in NOT_ALIAS:
                self.alias[alias] = table
            if how.startswith("left"):
                self.left.add(table)

    def owners(self, qualifier, col, columns):
        """컬럼 참조가 가리키는 contract 테이블. 별칭이 있으면 그 테이블, 없으면 그 컬럼을 가진 테이블 전부."""
        if qualifier:
            t = self.alias.get(qualifier)
            return {t} if t in columns else set()
        return {t for t in self.tables if col in columns.get(t, ())}

    def refs(self, col, columns):
        pat = re.compile(r"(?<![\w.])(?:(\w+)\.)?" + re.escape(col.lower()) + r"(?![A-Za-z0-9_])")
        return set().union(*[self.owners(q, col, columns) for q in pat.findall(self.text)] or [set()])

    def not_null(self, columns):
        """IS NULL로 잡는 (테이블, 컬럼). LEFT JOIN으로 붙은 쪽의 IS NULL은 짝 없음 검사라 뺀다."""
        out = set()
        for q, col in IS_NULL.findall(self.text):
            out |= {(t, col) for t in self.owners(q, col, columns) if t not in self.left}
        return out


def word(name):
    """영문 식별자 경계 (한글 조사가 붙어도 맞춘다)."""
    return re.compile(r"(?<![A-Za-z0-9_])" + re.escape(name.lower()) + r"(?![A-Za-z0-9_])")


def segments(sql, partition=PARTITION_FILTER):
    """검사 쿼리를 UNION ALL·CTE 단위로 나눈 Segment 목록 (테이블을 읽는 조각만)."""
    text = partition.sub(" ", strip_sql(sql))
    return [seg for seg in map(Segment, SEGMENT_SPLIT.split(text)) if seg.tables]


class Spec:
    def __init__(self, root, dev, mart):
        self.root, self.mart = Path(root), mart
        self.contract = load_contract(root, mart)
        self.version = self.contract["version"]
        results = load_results(dev, mart, self.version)
        loads = topo_loads(self.contract)
        _, self.n, self.files = last_passed(results, loads, mart, self.version, "정의서")
        self.pii = load_pii(self.root / "docs" / "architecture" / "pii_columns.md")
        self.pii_names = {c for cols in self.pii.values() for c in cols}
        self.columns = {t["name"]: {c.get("name") for c in t.get("columns", [])} for t in self.contract["tables"]}
        self.checks = [c for group in self.contract["checks"].values() for c in group]
        self.ran_l3 = {cid for f in self.files.values() for g in f["rungs"] if g["rung"] == "L3"
                       for cid in g.get("metrics", {}).get("checks", [])}
        self.sql = {}
        partition = partition_filter(load_mode.partition_column(self.contract))
        for c in self.checks:
            path = self.root / "docs" / "requirements" / f"{mart}_checks" / c["rung"].lower() / f"{c['id']}.sql"
            if path.exists():
                self.sql[c["id"]] = segments(path.read_text(encoding="utf-8"), partition)

    def volume(self, table):
        f = self.files.get(table.get("task"))
        if not f:
            return None
        for name, note in (("L2", "L2"), ("L5", "L5 재실행 측정, L2 기록 없음")):
            g = next((g for g in f["rungs"] if g["rung"] == name), None)
            rc = (g or {}).get("metrics", {}).get("row_count")
            if str(rc).isdigit():
                return f"{int(rc):,}행 (ds {g.get('ds')} 파티션, 반복 {self.n} {note})"
        return None

    def not_null(self, table, col):
        ids = [c["id"] for c in self.checks if c["rung"] == "L3" and c["id"] in self.ran_l3 and c["id"] in self.sql
               and any((table, col) in seg.not_null(self.columns) for seg in self.sql[c["id"]])]
        return f"예({', '.join(ids)})" if ids else NOT_GUARANTEED

    def constraints(self, table, col):
        ids = []
        for c in self.checks:
            if c["id"] in self.sql:
                hit = any(table in seg.refs(col, self.columns) for seg in self.sql[c["id"]])
            else:
                rule = c.get("rule", "").lower()
                hit = bool(word(table).search(rule) and word(col).search(rule))
            if hit:
                ids.append(c["id"])
        return ", ".join(ids)

    def pii_flag(self, table, col):
        if table["layer"] == "raw":
            src = table["name"][4:] if table["name"].startswith("raw_") else table["name"]
            return "예" if col in self.pii.get(src, set()) else "아니오"
        return "예" if col in self.pii_names else "아니오"

    def table_rows(self):
        refresh = (self.contract.get("schedule") or {}).get("refresh") or ""
        return [{"테이블 소유자": OWNER, "한글 테이블명": t.get("name_ko") or UNWRITTEN, "영문 테이블명": t.get("name"),
                 "테이블 유형": t.get("layer"), "테이블 볼륨": self.volume(t), "발생주기": refresh,
                 "공개/비공개 여부": PUBLIC, "개방데이터목록": OPEN_DATA} for t in self.contract["tables"]]

    def column_rows(self):
        rows = []
        for t in self.contract["tables"]:
            keys = t.get("keys") or []
            for c in t.get("columns", []):
                name = c.get("name")
                rows.append({
                    "영문 테이블명": t["name"], "한글 컬럼명": c.get("name_ko") or UNWRITTEN, "영문 컬럼명": name,
                    "데이터 타입": c.get("type"), "데이터 길이": LENGTH,
                    "Not Null 여부": self.not_null(t["name"], name),
                    "PK 정보": f"{PK_TEXT}: {', '.join(keys)}" if name in keys else NOT_KEY,
                    "FK 정보": FK_TEXT, "제약조건": self.constraints(t["name"], name),
                    "개인정보 여부": self.pii_flag(t, name),
                    "암호화 여부": ENCRYPT.get(t["layer"], ENCRYPT_BLOCKED), "공개/비공개 여부": PUBLIC})
        return rows

    def datasets(self):
        layers = []
        for t in self.contract["tables"]:
            if t.get("layer") and t["layer"] not in layers:
                layers.append(t["layer"])
        return ", ".join(f"{{{{ dataset_{x} }}}}" for x in layers)


# ---------- 쓰기 ----------

def style_header(ws, row, ncols):
    from openpyxl.styles import Font, PatternFill
    for c in range(1, ncols + 1):
        cell = ws.cell(row, c)
        cell.font = Font(bold=True)
        cell.fill = PatternFill("solid", fgColor="DDEBF7")


def write_grid(ws, title, cols, rows, lead, need):
    """lead: 앞에 붙는 (열 이름) 목록. cols: (열 이름, 필수). need(셀 좌표, 칸 이름, 값)으로 필수 칸을 센다."""
    put(ws, "A1", title)
    put(ws, "A2", "* = S2 [별표 4] 필수 항목")
    names = ["번호", *lead, *[n + (" *" if req else "") for n, req in cols]]
    for c, name in enumerate(names, start=1):
        put(ws, (HEADER_ROW, c), name)
    style_header(ws, HEADER_ROW, len(names))
    for i, row in enumerate(rows):
        r = FIRST_ROW + i
        put(ws, (r, 1), i + 1)
        for c, name in enumerate([*lead, *[n for n, _ in cols]], start=2):
            value = row.get(name)
            if value not in ("", None):
                put(ws, (r, c), value)
        for c, (name, req) in enumerate(cols, start=2 + len(lead)):
            if req:
                need(ws.cell(r, c).coordinate, name, row.get(name), row.get("영문 테이블명"))
    for c in range(1, len(names) + 1):
        ws.column_dimensions[ws.cell(HEADER_ROW, c).column_letter].width = 8 if c == 1 else 22


def build(root, dev, mart, day, now, head):
    """(workbook, required, missing 목록, deferred 목록). 목록 원소는 "시트!셀 칸 (테이블)"."""
    import openpyxl
    spec = Spec(root, dev, mart)
    wb = openpyxl.Workbook()
    guide = wb.active
    guide.title = "안내"
    cover, tables, columns = wb.create_sheet("표지"), wb.create_sheet("테이블 정보"), wb.create_sheet("컬럼 정보")
    missing, deferred, required = [], [], 0

    put(guide, "A1", "테이블·컬럼 정의서 안내")
    put(guide, "A2", "공개 표준의 항목 구성만 참고한다(고객사 전용 양식 아님). 데이터 값·담당자 연락처는 넣지 않는다.")
    put(guide, "A4", "출처")
    for i, cit in enumerate(CITATIONS):
        for c, v in enumerate(cit, start=1):
            put(guide, (5 + i, c), v)
    r = 5 + len(CITATIONS) + 1
    put(guide, (r, 1), "칸 원천 (docs/templates/standards_survey.md §2.1·2.2)")
    for c, name in enumerate(("시트", "항목", "필수", "우리 원천", "채우는 주체", "적용"), start=1):
        put(guide, (r + 1, c), name)
    style_header(guide, r + 1, 6)
    for i, row in enumerate(SOURCES):
        for c, v in enumerate(row, start=1):
            if v:
                put(guide, (r + 2 + i, c), v)
    r += 2 + len(SOURCES) + 1
    put(guide, (r, 1), "manifest.json 집계")
    put(guide, (r + 1, 1), f"필수(*) 칸이 비었거나 '{UNWRITTEN}'이면 missing_fields, 테이블 소유자 '{OWNER}'는 deferred_fields로 센다.")
    for c, w in zip("ABCDEF", (14, 22, 8, 48, 18, 60)):
        guide.column_dimensions[c].width = w

    cover_rows = [
        ("문서명", "테이블·컬럼 정의서"), ("문서 번호", f"{PREFIX}-{mart}-{day.replace('-', '')}"),
        ("정보시스템명", SYSTEM), ("DBMS 정보", DBMS),
        ("DB명(데이터셋)", f"{spec.datasets()} (운영 이름 자리 표시, sql_rules §2)"),
        ("대상 마트", mart), ("contract 버전", f"v{spec.version}"),
        ("테이블 수", len(spec.contract["tables"])), ("작성일", day),
        ("기준 반복", f"{spec.n} (마지막 통과 반복, .dev/ladder_results/{mart}/)"),
    ]
    put(cover, "A1", "표지 (S2 1·2절 중 §2.3 범위만)")
    for i, (k, v) in enumerate(cover_rows, start=3):
        put(cover, (i, 1), k)
        put(cover, (i, 2), v)
    stamp_row = 3 + len(cover_rows) + 1
    write_stamp(cover, stamp_row, spec.version, now, head)
    cover.column_dimensions["A"].width = 18
    cover.column_dimensions["B"].width = 60
    cover.column_dimensions["C"].width = 32

    def need_for(ws):
        def need(coord, label, value, table):
            nonlocal required
            required += 1
            where = f"{ws.title}!{coord} {label} ({table})"
            if value in (None, "") or (isinstance(value, str) and not value.strip()) or value == UNWRITTEN:
                missing.append(where)
            elif value == OWNER:
                deferred.append(where)
        return need

    write_grid(tables, "테이블 정보 (S2 [별표 4] 3)", TABLE_COLS, spec.table_rows(), [], need_for(tables))
    write_grid(columns, "컬럼 정보 (S2 [별표 4] 4)", COLUMN_COLS, spec.column_rows(), ["영문 테이블명"],
               need_for(columns))
    return wb, required, missing, deferred, spec.version


def parse_args(argv):
    p = argparse.ArgumentParser(description="테이블·컬럼 정의서 생성기 (진행표 4-4)")
    p.add_argument("--mart", help="마트. contract가 1개면 생략 가능(자동 선택)")
    p.add_argument("--root", default=str(PROJECT))
    p.add_argument("--dev-dir", help="기본: <root>/.dev")
    p.add_argument("--date", help="작성일 YYYY-MM-DD (기본: 오늘 +09:00)")
    p.add_argument("--force", action="store_true", help="같은 날짜 정의서가 있으면 덮어씀")
    p.add_argument("--check", action="store_true", help="정의서 도장이 지금 contract version·HEAD와 같은지만 검사")
    p.add_argument("--file", help="--check 대상 (기본: out/deliverables/<마트>/의 마지막 정의서)")
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
        print("openpyxl이 없어 정의서를 만들 수 없음 (설치는 사람이 한다)", file=sys.stderr)
        return 2
    try:
        if args.check:
            return check_stamp(root, args.mart, PREFIX, "정의서", args.file)
        dev = Path(args.dev_dir) if args.dev_dir else root / ".dev"
        now = now or datetime.now(KST).isoformat(timespec="seconds")
        day = args.date or now[:10]
        head = git(root, "rev-parse", "HEAD")
        folder = root / "out" / "deliverables" / args.mart
        out = folder / f"{PREFIX}_{args.mart}_{day.replace('-', '')}.xlsx"
        if out.exists() and not args.force:
            raise ReportError(f"이미 있음: {out.name}. 덮어쓰지 않는다 (--force)")
        wb, required, missing, deferred, version = build(root, dev, args.mart, day, now, head)
        folder.mkdir(parents=True, exist_ok=True)
        wb.save(out)
    except (ReportError, KeyError, ValueError, OSError) as e:
        print(f"정의서를 만들지 못함: {e.__class__.__name__}: {e}", file=sys.stderr)
        return 2
    manifest = write_manifest(folder, {
        "name": NAME, "file": f"out/deliverables/{args.mart}/{out.name}", "required_fields": required,
        "missing_fields": len(missing), "missing": missing, "deferred_fields": len(deferred), "deferred": deferred,
        "contract_version": version, "generated_at": now, "base_commit": head})
    print(out)
    print(f"필수 칸 {required}개 중 누락 {len(missing)}개, 결재 후로 미룸 {len(deferred)}개 → {manifest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
