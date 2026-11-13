"""측정 보고서 생성기 (진행표 5-5). 사전 등록 v6(docs/plan/08_preregistration.md) 기준.

  python scripts/metrics/report.py [--out docs/contest/measurement_report.md] [--check]

- 값은 dashboard_data.collect()에서 읽는다. 계산식은 이 파일에 두지 않고, 여기서는 판정(08 §3)과 문서 조립만 한다
- 주장 문장은 08 §3 표의 문장만 쓴다. 새 주장을 만들지 않는다. "사실 참고"는 기록에 있는 id·건수만 옮긴다
- 데이터 값 차단은 dashboard_data 규칙 그대로다: evidence·오류 원문 없음, 자유 문장은 scrub
- --check: 도장의 기준 커밋 이후 WATCHED 경로가 바뀌었으면 종료 2와 halt input_invalid. progress.md는 값에 쓰지 않아 보지 않는다
- 08에는 있지만 dashboard_data가 아직 계산하지 못하는 기록(unsupported)이 나타나면 틀린 값을 쓰지 않고 halt input_invalid
- 손익분기점은 계산하지 않는다. 08에 없는 숫자이고 입력(시간 단가, M/D 기준)은 사람이 정한다
- 10절 멈춤 표는 참고다(사전 등록 지표 아님, 5-10). M1~M12 계산과 판정에 쓰지 않는다
- 사람 결정(08 밖)은 docs/contest/claim_decisions.md에서 읽어 3절 판정 아래에 표시만 한다. 판정·수치·08 문장은 바꾸지 않는다.
  파일이 없으면 줄을 더하지 않고, 표 형식이 깨졌거나 모르는 지표·결정이면 halt input_invalid
"""
import argparse
import re
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / "scripts" / "metrics"))
import dashboard_data as dd  # noqa: E402
from make_facts import cell  # noqa: E402  (scrub + 표 칸 이스케이프)

PREREG = "prereg-v6"
DEFAULT_OUT = Path("docs") / "contest" / "measurement_report.md"
MUTATION = Path("docs") / "contest" / "mutation_results.md"
TRIAGE = Path(".dev") / "checks" / "hook_blocks_triage.md"
CLAIM_DECISIONS = Path("docs") / "contest" / "claim_decisions.md"
WATCHED = (".dev/interventions.jsonl", ".dev/rejections.jsonl", ".dev/cost.jsonl", ".dev/hook_blocks.jsonl",
           ".dev/ladder_results", ".dev/rule_candidates.md", ".claude/rules/learned",
           "docs/requirements/*.contract.json", "docs/requirements/*.md", "docs/ai/rule_candidate_exclusions.md",
           "docs/contest/mutation_results.md", CLAIM_DECISIONS.as_posix())
STAMP_COMMIT = re.compile(r"^- 기준 커밋: (\S+)$", re.M)
RESULT_LINE = re.compile(r"^- \*\*결과: .+$", re.M)
HASH_LINE = re.compile(r"^- 결과 표 원본 해시.*SHA256 `[0-9A-Fa-f]{64}`.*$", re.M)
STEP1 = (("raw", 7), ("stg", 3), ("구매 마트", 4), ("stg_users·사용자 마트", 4), ("dq", 8))  # 08 §6
MART2_MARK = "마트 1 지표가 `docs/domain/`에 있는 상태"  # 08 §4 마지막 행
TOKEN_FIELDS = dd.COST_FIELDS[:4]
ESTIMATE = "정가 환산 추정"
USD = f"{ESTIMATE} USD"
HIT, CLEAR, NOT_JUDGED = "걸림", "걸리지 않음", "판정 대상 없음"
REFERENCE = "참고, 사전 등록 지표 아님"
DECISION_HEADER = ["지표", "결정", "이유", "근거"]
WITHHELD, FOOTNOTE = "발표에 쓰지 않음", "각주"
# 08 §3: 지표 → 하지 않는 주장. 실패 기준에 걸리지 않으면 같은 문장을 쓸 수 있다
CLAIMS = {
    "M1": "사람은 결재만 했다",
    "M2": "AI의 의미 오류를 코드가 잡았다",
    "M3": "루프가 스스로 고쳤다",
    "M4": "토큰 기준 사용량 숫자",
    "M5": "검증이 작동했다",
    "M6": "예방(인터뷰)이 작동했다",
    "M7": "요구가 처음부터 맞게 정해졌다",
    "M8": "그 마트의 소요 시간 숫자",
    "M9": "규칙이 쌓여 같은 실수가 줄었다",
    "M10": "규칙이 효과가 있었다",
    "M11": "안전장치가 실제 작업에서 뭔가를 막았다",
    "M12": "같은 조건에서 더 적었다",
}


class InputInvalid(Exception):
    """보고서를 만들지 못함 (종료 코드 2, halt input_invalid)."""


# ---------- 공통 ----------

def table(headers, rows):
    lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    lines += ["| " + " | ".join(str(c) for c in row) + " |" for row in rows]
    return "\n".join(lines)


class View:
    """collect() 결과를 보고서 쪽에서 읽기 쉽게 잡아 둔다."""

    def __init__(self, data, texts):
        self.data, self.per, self.total, self.texts = data, data["marts"], data["summary"], texts
        self.order, self.rules = self.total["mart_order"], data["rules"]
        self.mart2 = self.order[1] if len(self.order) > 1 else None

    def name(self, mart):
        return f"{mart} ({MART2_MARK})" if mart == self.mart2 else mart

    def s(self, mart):
        return self.per[mart]["summary"]

    def said(self, rid, *fields):
        """기록 id의 자유 문장 칸(scrub 거친 값)을 "칸 값 / 칸 값"으로."""
        return " / ".join(f"{k} {cell(self.texts[rid][k])}" for k in fields)

    def row(self, metric, item, unit, fn, total=None):
        """fn(마트 요약)으로 마트 칸을 채운다. total이 None이면 숫자 칸의 합."""
        values = [fn(self.s(m)) for m in self.order]
        return (metric, item, unit, *values, sum(values) if total is None else total)

    def headers(self):
        return ("지표", "항목", "단위", *(self.name(m) for m in self.order), "전체")


def pair(count, minutes):
    return f"{count}건 / {minutes}분"


def tasks(view, kinds):
    return [(m, t, v) for m in view.order for t, v in view.s(m)["M3"].items() if v["class"] in kinds]


# ---------- 2) 지표 표 ----------

def rows_m1(v):
    def line(item, get):
        cells = [get(v.s(m)) for m in v.order]
        return ("M1", item, "건 / 분", *(pair(c["count"], c["minutes"]) for c in cells),
                pair(sum(c["count"] for c in cells), sum(c["minutes"] for c in cells)))
    out = [line(k, lambda s, k=k: s["M1"]["main"]["by_kind"][k]) for k in dd.M1_KINDS]
    out += [line(f"approval · {st}", lambda s, st=st: s["M1"]["main"]["approval_by_stage"][st])
            for st in (*dd.M12_STAGES, *dd.LOOP_STAGES, *dd.RULE_STAGES)]
    out.append(line("합계", lambda s: s["M1"]["main"]))
    out.append(line("ops_run (따로 센다)", lambda s: s["M1"]["ops_run"]))
    out.append(line("유지보수 (V4-7, 본 측정 밖)", lambda s: s["M1"]["maintenance"]))
    return out


def rows_m2(v):
    out = [v.row("M2", "합계 (기본분 + 연장분)", "건", lambda s: s["M2"]["total"]["count"]),
           v.row("M2", "기본분", "건", lambda s: s["M2"]["base"]["count"]),
           v.row("M2", "연장분", "건", lambda s: s["M2"]["extension"]["count"])]
    for key, label in (("by_error_type", "error_type"), ("by_caught_by_rung", "caught_by_rung"),
                       ("by_error_class", "error_class")):
        names = {k for m in v.order for k in v.s(m)["M2"]["total"][key]}
        names |= {"syntax", "semantic"} if key == "by_error_class" else set()
        out += [v.row("M2", f"{label} · {n}", "건", lambda s, key=key, n=n: s["M2"]["total"][key].get(n, 0))
                for n in sorted(names)]
    out.append(v.row("M2", "결재 후 반려 (L6, post)", "건", lambda s: s["M2"]["post_approval"]["count"]))
    return out


def rows_m3(v):
    def count(s, kind):
        return sum(1 for t in s["M3"].values() if t["class"] == kind)
    out = [v.row("M3", "reject 파일 수", "회", lambda s: sum(t["rejects"] for t in s["M3"].values()))]
    out += [v.row("M3", f"작업 수 · {k}", "개", lambda s, k=k: count(s, k))
            for k in ("스스로 고침", "연장 결재 뒤 통과", "멈춤", "진행 중", "반려 없음")]
    return out


def rows_m4(v):
    fields = [(k, "토큰", k) for k in TOKEN_FIELDS] + [("total_cost_usd", USD, "total_cost_usd"),
                                                       ("bq_bytes_processed", "bytes", "bq_bytes_processed")]
    return [("M4", label, unit, *(v.s(m)["M4"][key] for m in v.order), v.total["M4"][key])
            for key, unit, label in fields]


def rows_rest(v):
    m8 = [v.s(m)["M8"]["hours"] for m in v.order]
    m11 = v.total["M11"]
    out = [v.row("M5", "결재 후 발견 결함", "건", lambda s: s["M5"]["count"])]
    names = {k for m in v.order for k in v.s(m)["M5"]["by_missed_by_rung"]}
    out += [v.row("M5", f"missed_by_rung · {n}", "건", lambda s, n=n: s["M5"]["by_missed_by_rung"].get(n, 0))
            for n in sorted(names)]
    out += [v.row("M6", "위험 항목", "건", lambda s: s["M6"]["count"]),
            v.row("M6", "그중 인터뷰 뒤 추가", "건", lambda s: s["M6"]["added_later"]),
            v.row("M6", "그중 완료 조건 검사로 추가된 항목", "건", lambda s: s["M6"]["with_check"]),
            v.row("M7", "결재 1 이후 요구 변경", "건", lambda s: s["M7"]["main"]["count"])]
    labels = {"expert_advice": "expert_advice (노하우가 잡은 설계 결함)"}
    out += [v.row("M7", f"cause · {labels.get(c, c)}", "건", lambda s, c=c: s["M7"]["main"]["by_cause"][c])
            for c in sorted(dd.devlog.CAUSES)]
    out.append(v.row("M7", "유지보수 (V4-7, 본 측정 밖)", "건", lambda s: s["M7"]["maintenance"]["count"]))
    out.append(("M8", "첫 approval_1 → 마지막 approval_2", "시간", *m8, dd.DASH))
    out.append(v.row("M9", "반려 건수 (M2 합계)", "건", lambda s: s["M2"]["total"]["count"]))
    out.append(v.row("M9", "사람 개입 건수 (M1 합계, ops_run 제외)", "건", lambda s: s["M1"]["main"]["count"]))
    out.append(("M10", "승격 규칙", "건", *(dd.DASH for _ in v.order), v.rules["promoted"]))
    out.append(("M11", "차단 (제외 후)", "건", *(m11["by_mart"].get(m, 0) for m in v.order), m11["count"]))
    out.append(("M11", "그중 마트 밖", "건", *(dd.DASH for _ in v.order), m11["by_mart"].get("마트 밖", 0)))
    out += [("M11", f"reason · {k}", "건", *(dd.DASH for _ in v.order), n) for k, n in sorted(m11["by_reason"].items())]
    out.append(v.row("M12", "결재 수", "건", lambda s: s["M12"]["main"]["count"]))
    out += [v.row("M12", f"stage · {st}", "건", lambda s, st=st: s["M12"]["main"]["by_stage"][st])
            for st in dd.M12_STAGES]
    out.append(v.row("M12", "유지보수 (V4-7, 본 측정 밖)", "건", lambda s: s["M12"]["maintenance"]["count"]))
    return out


def section_metrics(v):
    main = table(v.headers(), rows_m1(v) + rows_m2(v) + rows_m3(v) + rows_m4(v) + rows_rest(v))
    m3 = [(v.name(m), t, x["rejects"], x["class"], x["halt_reason"] or dd.DASH)
          for m in v.order for t, x in v.s(m)["M3"].items()]
    model_fields = (*TOKEN_FIELDS, "total_cost_usd")
    m4 = [(v.name(m), model, *(x[k] for k in model_fields))
          for m in v.order for model, x in v.s(m)["M4_by_model"].items()]
    m4 += [("모델 합계", model, *(x[k] for k in model_fields)) for model, x in v.total["M4_by_model"].items()]
    m9 = []
    for r in v.total["M9"]:
        d = r["difficulty"] if isinstance(r["difficulty"], dict) else {}
        m9.append((v.name(r["mart"]), r["rejections"], r["interventions"],
                   " / ".join(f"{k} {cell(x)}" for k, x in d.items()) or dd.NONE))
    parts = ["## 2) 지표 표 (M1~M12)", "", "값은 08 §4 제외 뒤의 본 측정 값이다. M1·M7·M12는 첫 approval_2까지 센다(V4-7).", "", main, "",
             "### M3 작업별", "", table(("마트", "task", "reject 파일 수", "분류", "halt_reason"), m3), "",
             f"### M4 마트별·모델별 (total_cost_usd는 {USD})", "",
             table(("마트", "model", *model_fields), m4), "",
             "### M9 마트 순서대로 (난이도는 판정에 쓰지 않는다)", "",
             table(("마트", "반려 건수", "사람 개입 건수", "난이도 기록"), m9)]
    if v.rules["m10"]:
        rows = [(r["rule_id"], r["error_type"], v.name(m), x["before"], x["after"], x["excluded"])
                for r in v.rules["m10"] for m, x in r["by_mart"].items()]
        parts += ["", "### M10 규칙별", "", table(("규칙", "error_type", "마트", "승격 전", "승격 후", "그중 제외 목록"), rows)]
    return "\n".join(parts)


# ---------- 3) 실패 기준 판정 ----------

def verdict(metric, state, *, instead=(), claim=None, notes=()):
    """state가 HIT이면 하지 않는 주장과 대신 보고할 것, CLEAR이면 쓸 수 있는 주장(08 §3 문장 그대로)."""
    return {"metric": metric, "state": state, "claim": CLAIMS[metric] if claim is None else claim,
            "instead": list(instead), "notes": list(notes)}


def excluded_rejections(v):
    """규칙 후보 제외 목록에 있는 반려 중 실제 기록이 있는 id."""
    return [rid for rid in v.rules["excluded"]
            if any(r["id"] == rid for m in v.order for r in v.per[m]["rejections"])]


def excluded_note(v):
    excluded = excluded_rejections(v)
    return [f"반려 {', '.join(excluded)}는 규칙 후보 제외 목록(V6-3, 원인이 하네스)에 있다"] if excluded else []


def judge_m1(v):
    rows = [(m, r) for m in v.order for r in v.s(m)["M1_hand"]]
    if not rows:
        return verdict("M1", CLEAR)
    counts = {k: sum(1 for _, r in rows if r["kind"] == k) for k in dd.HAND_KINDS}
    lines = [" / ".join(f"{k} {n}건" for k, n in counts.items())]
    lines += [f"{r['id']} ({v.name(m)}, {r['kind']}): {v.said(r['id'], 'target', 'note')}" for m, r in rows]
    return verdict("M1", HIT, instead=lines)


def judge_m2(v):
    classes = {}
    for m in v.order:
        for part in ("total", "post_approval"):
            for k, n in v.s(m)["M2"][part]["by_error_class"].items():
                classes[k] = classes.get(k, 0) + n
    notes = excluded_note(v)
    if classes.get("semantic", 0):
        return verdict("M2", CLEAR, notes=notes)
    return verdict("M2", HIT, instead=[f"문법 반려 {classes.get('syntax', 0)}건만 있다 (semantic 0건)"], notes=notes)


def m3_notes(v, rows):
    """고친 작업의 반려가 제외 목록에 있거나 그 작업에 멈춤 반복이 있으면 id·건수를 그대로 적는다."""
    out = []
    for m, t, _ in rows:
        harness = [r["id"] for r in v.per[m]["rejections"] if r["task"] == t and r["harness_cause"]]
        grid = next((r for r in v.per[m]["grid"]["rows"] if r["task"] == t), {"verdicts": []})
        halts = [f"반복 {x['iteration']} {x['halt_reason']}" for x in grid["verdicts"] if x["verdict"] == "halt"]
        if harness:
            out.append(f"{v.name(m)} {t}: 반려 {', '.join(harness)}는 규칙 후보 제외 목록(V6-3, 원인이 하네스)에 있다")
        if halts:
            out.append(f"{v.name(m)} {t}: 통과 전에 멈춘 반복이 있다 ({', '.join(halts)})")
    return out


def judge_m3(v):
    halted = tasks(v, ("멈춤",))
    fixed = tasks(v, ("스스로 고침",))
    extended = tasks(v, ("연장 결재 뒤 통과",))
    names = ", ".join(f"{v.name(m)} {t}" for m, t, _ in fixed)
    notes = m3_notes(v, fixed)
    if extended:  # V4-4
        notes.append("연장 결재 뒤 통과한 작업에 대해 \"루프가 스스로 고쳤다\"고 하지 않는다: "
                     + ", ".join(f"{v.name(m)} {t}" for m, t, _ in extended))
    if halted:
        reasons = {}
        for _, _, x in halted:
            reasons[x["halt_reason"]] = reasons.get(x["halt_reason"], 0) + 1
        lines = [f"멈춘 작업 {len(halted)}개", *(f"halt_reason {k}: {n}건" for k, n in sorted(reasons.items()))]
        lines += [f"{v.name(m)} {t}" for m, t, _ in halted]
        return verdict("M3", HIT, instead=lines, notes=notes + ([f"이 작업에 한해 쓸 수 있는 주장: \"{CLAIMS['M3']}\" ({names})"]
                                                                  if fixed else []))
    if not fixed:
        return verdict("M3", NOT_JUDGED, notes=notes + ["반려 뒤 스스로 고친 작업이 없다"])
    return verdict("M3", CLEAR, notes=[f"대상 작업: {names}", *notes])


def judge_m4(v):
    total = v.total["M4"]
    missing = [f"{k}: {total['calls']}줄 중 null {total[f'{k}_null']}줄" for k in TOKEN_FIELDS
               if total[f"{k}_null"] or total[k] == dd.NONE]
    note = [f"금액은 \"{ESTIMATE}\"으로만 말한다 (결정 52 ④)"]
    if missing:
        return verdict("M4", HIT, instead=["수집 불가: cost.jsonl에 값이 없다", *missing], notes=note)
    return verdict("M4", CLEAR, notes=note)


def judge_m5(v):
    rows = [(m, r) for m in v.order for r in v.s(m)["M5"]["rows"]]
    if not rows:
        return verdict("M5", CLEAR)
    return verdict("M5", HIT, instead=[f"{len(rows)}건"] + [
        f"{r['id']} ({v.name(m)}): {v.said(r['id'], 'found_stage', 'detail')} / missed_by_rung {r['missed_by_rung']}"
        for m, r in rows])


def judge_m6(v):
    zero = [m for m in v.order if v.s(m)["M6"]["count"] == 0]
    if zero:
        return verdict("M6", HIT, instead=[f"위험 항목 0건: {v.name(m)}" for m in zero])
    return verdict("M6", CLEAR)


def judge_m7(v):
    rows = [(m, r) for m in v.order for r in v.s(m)["M7"]["main"]["rows"]]
    if not rows:
        return verdict("M7", CLEAR)
    causes = {}
    for _, r in rows:
        causes[r["cause"]] = causes.get(r["cause"], 0) + 1
    return verdict("M7", HIT, instead=[" / ".join(f"{k} {n}건" for k, n in sorted(causes.items()))] + [
        f"{r['id']} ({v.name(m)}, {r['cause']}): {v.said(r['id'], 'target', 'note')}" for m, r in rows])


def judge_m8(v):
    missing = [(m, v.s(m)["M8"]["missing"]) for m in v.order if v.s(m)["M8"]["missing"]]
    usable = [m for m in v.order if not v.s(m)["M8"]["missing"]]
    if missing:
        return verdict("M8", HIT, instead=[f"{v.name(m)}: 없는 결재 단계 {', '.join(x)}" for m, x in missing],
                       notes=[f"소요 시간 숫자를 쓸 수 있는 마트: {v.name(m)}" for m in usable])
    return verdict("M8", CLEAR)


def judge_m9(v):
    rows = v.total["M9"]
    if len(rows) < 2:
        return verdict("M9", NOT_JUDGED, notes=["마트가 2개 미만이라 비교할 수 없다"])
    counts = " → ".join(f"{v.name(r['mart'])} {r['rejections']}건" for r in rows)
    notes = [f"규칙 승격 {v.rules['promoted']}건 (4절)", *excluded_note(v)]
    if any(b["rejections"] >= a["rejections"] for a, b in zip(rows, rows[1:])):
        return verdict("M9", HIT, instead=[f"마트별 건수: {counts}", "난이도 기록: 2절 M9 표"], notes=notes)
    return verdict("M9", CLEAR, notes=[f"마트별 건수: {counts}", *notes])


def judge_m10(v):
    if not v.rules["m10"]:
        return verdict("M10", NOT_JUDGED, notes=["승격 0건이라 4절(08 §5)로 보고한다"])
    no_drop, lines = [], []
    for r in v.rules["m10"]:
        before = sum(x["before"] for x in r["by_mart"].values())
        after = sum(x["after"] for x in r["by_mart"].values())
        lines.append(f"{r['rule_id']} ({r['error_type']}): 승격 전 {before}건, 승격 후 {after}건")
        if after >= before:
            no_drop.append(r["rule_id"])
    caution = ["줄었더라도 인과 증명이라고 말하지 않는다 (결정 51 ⑤)"]
    if no_drop:
        return verdict("M10", HIT, instead=lines, notes=caution)
    return verdict("M10", CLEAR, notes=lines + caution)


def judge_m11(v, root):
    if v.total["M11"]["count"] == 0:
        return verdict("M11", HIT, instead=["차단 시험(2-13) 통과 사실만 따로 말한다"])
    notes = ["오탐 후보 줄도 08대로 센다 (V5-1)"]
    if (Path(root) / TRIAGE).exists():
        notes.append(f"줄별 분류 초안(사람 판정 전): `{TRIAGE.as_posix()}`")
    return verdict("M11", CLEAR, notes=notes)


def judge_m12():
    return verdict("M12", NOT_JUDGED, notes=["비교 지표라 실패 기준이 없다. 하지 않는 주장: \"같은 조건에서 더 적었다\". "
                                            "\"이전 방식 대비\"로만 말한다 (5절)"])


def judgments(v, root):
    return [judge_m1(v), judge_m2(v), judge_m3(v), judge_m4(v), judge_m5(v), judge_m6(v), judge_m7(v), judge_m8(v),
            judge_m9(v), judge_m10(v), judge_m11(v, root), judge_m12()]


def load_decisions(root):
    """사람 결정 표를 {지표: [(결정, 이유)]}로 읽는다. 파일이 없으면 빈 dict, 형식이 틀리면 InputInvalid."""
    path = Path(root) / CLAIM_DECISIONS
    if not path.exists():
        return {}
    name = CLAIM_DECISIONS.as_posix()
    lines = [x.strip() for x in path.read_text(encoding="utf-8").splitlines() if x.strip().startswith("|")]
    if any(not x.endswith("|") or len(x) < 2 for x in lines):
        raise InputInvalid(f"{name} 표 줄이 |로 끝나지 않음")
    rows = [[c.strip() for c in x[1:-1].split("|")] for x in lines]
    if len(rows) < 2 or rows[0] != DECISION_HEADER or len(rows[1]) != len(DECISION_HEADER) \
            or not all(re.fullmatch(r":?-+:?", c) for c in rows[1]):
        raise InputInvalid(f"{name} 표 머리글이 {' | '.join(DECISION_HEADER)}가 아님")
    out = {}
    for row in rows[2:]:
        if len(row) != len(DECISION_HEADER) or not all(row):
            raise InputInvalid(f"{name} 표 줄의 칸 수가 틀렸거나 빈 칸이 있음: {cell(row[0])}")
        metric, decision, reason, _ = row
        if metric not in CLAIMS:
            raise InputInvalid(f"{name}에 모르는 지표 id: {cell(metric)}")
        if decision not in (WITHHELD, FOOTNOTE):
            raise InputInvalid(f"{name}에 모르는 결정: {cell(decision)}")
        out.setdefault(metric, []).append((decision, reason))
    return out


def decision_line(decision, reason):
    said = f"{WITHHELD}. 이유: {cell(reason)}" if decision == WITHHELD else f"{decision} {cell(reason)}"
    return f"- 사람 결정(08 밖): {said} ({CLAIM_DECISIONS.as_posix()})"


def section_judgments(items, decisions):
    hits = [j["metric"] for j in items if j["state"] == HIT]
    parts = ["## 3) 실패 기준 판정 (08 §3)", "", f"걸린 지표: {', '.join(hits) or '없음'}", ""]
    for j in items:
        parts.append(f"### {j['metric']}: {j['state']}")
        if j["state"] == HIT:
            parts.append(f"- 하지 않는 주장: \"{j['claim']}\"")
            parts.append("- 대신 보고할 것:")
            parts += [f"  - {x}" for x in j["instead"]]
        elif j["state"] == CLEAR:
            parts.append(f"- 쓸 수 있는 주장: \"{j['claim']}\"")
        parts += [decision_line(*x) for x in decisions.get(j["metric"], ())]
        parts += [f"- 사실 참고: {x}" for x in j["notes"]]
        parts.append("")
    return "\n".join(parts).rstrip()


# ---------- 4)~9) ----------

def section_promotion(v, root):
    excluded = dd.rc.load_exclusions(root)
    candidates = v.rules["candidates"]
    head = "## 4) 규칙 승격 보고 (08 §5)"
    if v.rules["promoted"]:
        return "\n".join((head, "", f"승격 {v.rules['promoted']}건. 전후 건수는 2절 M10 표와 3절 M10 판정을 본다."))
    m2 = []
    for key, label in (("by_error_type", "error_type"), ("by_caught_by_rung", "caught_by_rung"),
                       ("by_error_class", "error_class")):
        merged = {}
        for m in v.order:
            for k, n in v.s(m)["M2"]["total"][key].items():
                merged[k] = merged.get(k, 0) + n
        m2.append((label, ", ".join(f"{k} {n}건" for k, n in sorted(merged.items())) or "0건"))
    risks = sum(v.s(m)["M6"]["count"] for m in v.order)
    rejected = sum(v.s(m)["M2"]["total"]["count"] for m in v.order)
    return "\n".join((
        head, "",
        "구조는 갖췄고 실제 승격은 0건이다.", "",
        "1겹(인터뷰)과 2겹(사다리)이 막아 승격할 실수가 없었다 (08 §5 보고 문장).",
        f"- 사실 참고: 반려 {rejected}건, 제외 목록 {ids(excluded_rejections(v))}", "",
        "### 반려 로그 건수 (M2)", "", table(("구분", "건수"), m2), "",
        "### 규칙 후보 (`.dev/rule_candidates.md`)", "",
        f"같은 `error_type` 누적 2회 이상으로 생긴 후보: {len(candidates)}건 (후보 파일: {v.rules['candidates_file']})", "",
        table(("후보", "error_type", "결재 상태"), [(c["id"], c["error_type"], cell(c["state"])) for c in candidates])
        if candidates else "후보 없음", "",
        f"### 제외 목록 (`docs/ai/rule_candidate_exclusions.md`, V6-3): {len(excluded)}줄", "",
        table(("반려 id", "이유", "근거 결정·PR"), [(k, cell(a), cell(b)) for k, (a, b) in sorted(excluded.items())]), "",
        "### 인터뷰가 미리 찾은 위험 수 (M6)", "",
        table(("마트", "위험 항목", "그중 인터뷰 뒤 추가", "그중 완료 조건 검사로 추가된 항목"),
              [*((v.name(m), v.s(m)["M6"]["count"], v.s(m)["M6"]["added_later"], v.s(m)["M6"]["with_check"])
                 for m in v.order),
               ("전체", risks, sum(v.s(m)["M6"]["added_later"] for m in v.order),
                sum(v.s(m)["M6"]["with_check"] for m in v.order))])))


def section_step1(v):
    step1 = ", ".join(f"{k} {n}" for k, n in STEP1)
    rows = [(v.name(m), v.s(m)["M12"]["main"]["count"]) for m in v.order]
    rows.append(("전체", sum(v.s(m)["M12"]["main"]["count"] for m in v.order)))
    return "\n".join((
        "## 5) 1단계 대비 (08 §6)", "",
        f"1단계: 파이프라인 구축 요청 {sum(n for _, n in STEP1)}건 ({step1})", "",
        table(("이번 (루프 방식)", "결재 수 (M12)"), rows), "",
        "한계: 다른 마트·다른 시기이고, 같은 사람이 두 번째로 하는 작업이라 숙련 효과가 섞인다. "
        "\"같은 조건 비교\"가 아니라 \"이전 방식 대비\"로 말한다."))


def ids(items):
    return ", ".join(items) or dd.DASH


def maintenance_row(v, m):
    x = v.s(m)["exclusions"]
    count = len(x["maintenance"])
    return (f"결재 2 뒤 개입: {v.name(m)}", "V4-7", count, ids(x["maintenance"]),
            f"{count}건 중 ops_run {x['maintenance_ops_run']}건. 유지보수로 따로 둔다. M1·M7·M12에 넣지 않는다")


def section_exclusions(v, root):
    hooks = v.total["M11"]["excluded"]
    drill, agent = [x for x in hooks if int(x[2:]) <= 6], [x for x in hooks if int(x[2:]) >= 7]
    expert = [f"{v.name(m)}/{f}" for m in v.order for f in v.s(m)["exclusions"]["expert_on"]]
    expert_rej = sum(v.s(m)["M2"]["expert_on"]["count"] for m in v.order)
    halts = [f"{v.name(m)}/{f}" for m in v.order for files in v.s(m)["exclusions"]["halts"].values() for f in files]
    excluded = sorted(dd.rc.load_exclusions(root))
    rows = [
        ("노하우가 켜진 실행", "08 §4", len(expert), ids(expert), f"별도 집계. 반려 {expert_rej}건"),
        ("`halt_reason`이 `infra_error`·`builder_blocked`인 실행", "08 §4", len(halts), ids(halts), "M2·M3에서 뺀다"),
        ("결함 주입 시험", "08 §4·§7", "7절", "`docs/contest/mutation_results.md`", "본 측정에 넣지 않는다"),
        ("규칙 끄기 실행", "08 §4", 0, dd.DASH, "`DEVLOG_DIR` 분리. 이 `.dev/`에 없다"),
        ("재현 기록", "V6-4", 0, dd.DASH, "`DEVLOG_DIR` 분리. 이 `.dev/`에 없다"),
        ("2-13 차단 시험", "08 §4", len(drill), ids(drill), "M11에서 뺀다"),
        ("2-20 위험 요청 시험", "08 §4, V5-1", 0, dd.DASH, "Hook 발동 0건이라 뺄 줄이 없다"),
        ("3-2 에이전트 안 차단 시험", "V5-1", len(agent), ids(agent), "M11에서 뺀다"),
        ("규칙 후보 제외 목록", "V6-3", len(excluded), ids(excluded), "후보 집계에서만 뺀다. M2는 그대로"),
    ]
    rows += [maintenance_row(v, m) for m in v.order]
    same = [x for x in (v.s(m)["exclusions"]["same_second_ops_run"] for m in v.order) if x]
    notes = [f"- 사실 참고: {', '.join(x['ids'])}(ops_run)는 approval_2({x['approval_2']})와 같은 초에 기록되어 "
             "V4-7 문구대로 결재 2 이전으로 분류됨" for x in same]
    return "\n".join(("## 6) 제외·별도 집계 (08 §4, V5-1, V6-3)", "",
                      table(("제외 대상", "근거", "건수", "id", "처리"), rows), *(("", *notes) if notes else ())))


def section_mutation(root):
    path = Path(root) / MUTATION
    body = path.read_text(encoding="utf-8") if path.exists() else ""
    result, digest = RESULT_LINE.search(body), HASH_LINE.search(body)
    if not result or not digest:
        raise InputInvalid(f"{MUTATION.as_posix()}에 결과 줄 또는 해시 줄이 없음")
    return "\n".join(("## 7) 결함 주입 시험", "",
                      f"본 측정과 분리한 시험이다(08 §4·§7). `{MUTATION.as_posix()}`에서 인용만 한다.", "",
                      f"> {result.group(0)}", ">", f"> {digest.group(0)}"))


def section_mart2(v):
    target = v.mart2 or "마트 2 기록 없음"
    return "\n".join(("## 8) 마트 2 표시 (08 §4 마지막 행)", "",
                      f"{target}의 모든 결과는 {MART2_MARK}에서 측정했다. 이 보고서에서 그 마트 이름 옆에 같은 표시를 붙였다.", "",
                      "마트 1과 마트 2의 인터뷰 조건이 다르다."))


def section_breakeven(v):
    def hours(m):
        return v.s(m)["M8"]["hours"]
    rows = [("M1 합계", "분", *(v.s(m)["M1"]["main"]["minutes"] for m in v.order), v.total["M1_minutes_main"]),
            ("M4 total_cost_usd", USD, *(v.s(m)["M4"]["total_cost_usd"] for m in v.order),
             v.total["M4"]["total_cost_usd"]),
            ("M8 소요 시간", "시간", *(hours(m) for m in v.order), dd.DASH),
            ("1단계 구축 요청", "건", *(dd.DASH for _ in v.order), sum(n for _, n in STEP1))]
    return "\n".join(("## 9) 손익분기점(추정, 사전 등록 밖)", "",
                      "08에 없는 숫자라 계산하지 않았다. 계산에 쓸 측정값만 모았다.", "",
                      table(("측정값", "단위", *(v.name(m) for m in v.order), "전체"), rows), "",
                      "입력 필요: 사람이 정함 (시간 단가, M/D 기준)"))


def section_halts(v):
    """참고 표(5-10). 08의 지표가 아니라서 M1~M12 표와 3절 판정에 넣지 않는다."""
    cells = [v.s(m)["halts"] for m in v.order]
    runs, count = sum(c["runs"] for c in cells), sum(c["count"] for c in cells)

    def rate(n, total):
        return f"{n / total * 100:.1f}" if total else dd.DASH

    rows = [("사다리 결과 파일", "개", *(c["runs"] for c in cells), runs),
            ("멈춤", "건", *(c["count"] for c in cells), count),
            ("멈춤 비율", "%", *(rate(c["count"], c["runs"]) for c in cells), rate(count, runs))]
    for reason in sorted({k for c in cells for k in c["by_reason"]}):
        values = [c["by_reason"].get(reason, 0) for c in cells]
        rows.append((f"halt_reason · {cell(reason)}", "건", *values, sum(values)))
    return "\n".join((f"## 10) 멈춤 표 ({REFERENCE})", "",
                      "M1~M12 계산과 실패 기준 판정에 쓰지 않는다.", "",
                      table(("항목", "단위", *(v.name(m) for m in v.order), "전체"), rows), "",
                      "- 분모는 `.dev/ladder_results`의 결과 파일(반복의 task별 파일과 L6 post 파일)이다. "
                      "사다리를 돌리기 전에 멈춘 파일도 1개로 센다.",
                      "- 08 §4 제외를 적용하지 않고 모두 센다. `infra_error`·`builder_blocked`도 이 표에는 들어간다.",
                      f"- {v.data['notes']['iteration0_halts']}. 이 표에 세지 못한다."))


# ---------- 조립 ----------

def unsupported(v, logs):
    """08에 있지만 dashboard_data가 아직 계산하지 못하는 기록. 실제로 나타나면 틀린 값을 쓰지 않고 멈춘다."""
    out = []
    if any(int(v.per[m]["version"]) > 1 for m in v.order):
        out.append("contract v2 이상: M3의 버전별·누적 집계(08 M3)가 없다")
    if any(r.get("kind") == "module_toggle" and r.get("now") is True for r in logs.interventions):
        out.append("module_toggle now:true: 켠 시각 이후 제외(08 §4)가 없다")
    if any(v.s(m)["exclusions"]["expert_on"] for m in v.order):
        out.append("노하우 켠 실행: M4 분리(08 §4)가 없다")
    if any(r.get("kind") == "approval" and r.get("stage") == "loop_extension" for r in logs.interventions):
        out.append("loop_extension: M3의 기본분·연장분 reject 수(V4-3)가 없다")
    return out


def build(root=PROJECT, dev=None, now=None):
    root = Path(root)
    data = dd.collect(root, dev, now)
    logs = dd.Logs(dev or root / ".dev")
    v = View(data, dd.record_texts(logs))
    problems = unsupported(v, logs)
    if problems:
        raise InputInvalid("08과 dashboard_data가 다른 기록이 있음 — " + "; ".join(problems))
    head = data["header"]
    versions = ", ".join(f"{m} v{v.per[m]['version']}" for m in v.order)
    stamp = "\n".join(("# 측정 보고서", "", "## 1) 도장", "", f"- contract 버전: {versions}",
                       f"- 생성 시각: {head['generated_at']}", f"- 기준 커밋: {head['commit']}", "",
                       f"사전 등록 {PREREG} 기준"))
    try:
        parts = (stamp, section_metrics(v), section_judgments(judgments(v, root), load_decisions(root)),
                 section_promotion(v, root),
                 section_step1(v), section_exclusions(v, root), section_mutation(root), section_mart2(v),
                 section_breakeven(v), section_halts(v))
    except ValueError as e:  # 제외 목록 형식 오류, 결정 파일 인코딩 오류
        raise InputInvalid(str(e)) from None
    return "\n\n".join(parts) + "\n"


def stale(root, path):
    """도장의 기준 커밋 이후 바뀐 원천 경로 목록. 빈 목록이면 최신이다."""
    if not path.exists():
        return [f"{path.name} 없음"]
    m = STAMP_COMMIT.search(path.read_text(encoding="utf-8"))
    if not m:
        return ["도장 없음"]
    git = dd.state.git
    try:
        changed = git(root, "-c", "core.quotepath=off", "diff", "--name-only", m.group(1), "--", *WATCHED)
        added = git(root, "-c", "core.quotepath=off", "ls-files", "--others", "--exclude-standard", "--", *WATCHED)
    except dd.state.GitError:
        return [f"기준 커밋 {m.group(1)[:8]}을 찾지 못함"]
    return sorted(set(changed.split("\n") + added.split("\n")) - {""})


def check(root, path):
    problems = stale(root, path)
    if problems:
        print(f"halt input_invalid: 측정 보고서 {path.name}이 최신이 아님 — " + "; ".join(problems), file=sys.stderr)
        return 2
    print(f"최신: {path.name}")
    return 0


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description="사전 등록 v6 기준 측정 보고서 (진행표 5-5)")
    p.add_argument("--root", type=Path, default=PROJECT)
    p.add_argument("--dev-dir", type=Path)
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    p.add_argument("--check", action="store_true", help="도장의 기준 커밋 이후 원천이 바뀌었으면 종료 코드 2")
    a = p.parse_args(argv)
    path = a.out if a.out.is_absolute() else a.root / a.out
    if a.check:
        return check(a.root, path)
    try:
        body = build(a.root, a.dev_dir)
    except InputInvalid as e:
        print(f"halt input_invalid: {e}", file=sys.stderr)
        return 2
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8", newline="\n")
    print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
