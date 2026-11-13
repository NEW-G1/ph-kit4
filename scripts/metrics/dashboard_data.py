"""대시보드 데이터 (진행표 4-14, 결정 71). 화면 7개에 필요한 값을 기존 기록에서 읽어 dict로 돌려준다. HTML은 4-15.

  from dashboard_data import collect; data = collect()

- 읽기 전용이다. 새 로그·상태 파일을 만들지 않고, 판정을 다시 계산하지 않는다(state·devlog의 함수를 그대로 쓴다)
- 원천: docs/requirements/<마트>.contract.json(마트 목록·버전·requested_by·검사 rule),
  docs/requirements/<마트>_checks/<l3|l4|l5>/*.sql(사다리 상세 패널의 검사 SQL 원문·규칙 주석 줄·머리말),
  dags/sql/<층>/<task>.sql(L1·L2 칸 패널의 task SQL 원문, 지금 파일 그대로, scrub),
  .dev/ladder_results, .dev/{interventions,rejections,cost,hook_blocks}.jsonl, .dev/progress.md(3줄),
  .dev/rule_candidates.md, .claude/rules/learned/*.md, git HEAD
- 데이터 값 차단: evidence는 읽지 않는다. 오류 메시지 원문(rejections.detail, rungs[].metrics.message·errors,
  halt_detail.message)은 결과에 넣지 않고 error_type·검사 ID·contract rule만 넣는다. 위반 건수는
  metrics.violations_shown이고 EVIDENCE_ROWS(5)면 "5건 이상". 자유 문장(3줄, target, note, 규칙 문장)은
  make_facts.scrub()을 거친다. 없는 값은 "기록 없음"
- 사다리 상세 패널(결정 71 범위)에 넣는 것: 검사 SQL 원문(검사 파일 그대로, 자리 표시 그대로, 데이터 값 없음),
  검사 규칙 문장(주석 줄, 없으면 contract rule), 반복마다 통과한 검사 id(metrics.checks), 사다리가 만든 L5 비교 문장
  (LADDER_NOTE 형식일 때만). 검사 SQL에 l4·l5가 들어가므로 builder는 out/dashboard.html·json을 읽지 못한다
  (check_write.py, 결정 55)
- 진행 단계 7개: 요구서 → 결재 1 → 루프 → PR → 결재 2 → 운영 → L6 (판정 규칙은 stages() 주석)
- 요약 숫자: 08 사전 등록 M1~M9·M11·M12와 V4-2·V4-3·V4-4·V4-7·V5-1. 측정 보고서(report.py, 5-5)가 같은 값을 쓴다.
  첫 approval_2 뒤의 개입은 "유지보수"로 따로 둔다(V4-7). ops_run은 M1 밖에서 따로 센다(M1 정의)
- L6 확인(4-15, 결정 72): 이 마트의 모든 contract 버전 post 결과 중 마지막 것의 ts·경과일. 그 뒤 contract 버전이
  바뀌었거나 ops_run이 새로 있으면 "재확인 필요". OM API는 조회하지 않는다(l6_om.py가 남긴 결과 파일만 읽는다)
- 다음 행동 링크(D-05): header.repo_url = git remote origin을 github_url()로 바꾼 주소(userinfo 제거, SSH → https,
  github.com이 아니거나 remote·git이 없으면 None). 마트별 links.{request_pr|impl_pr} = {"number", "url"} 또는 None.
  번호는 kind=approval 기록의 target에서 정규식 "PR #(\\d+)"만 읽는다(다른 글자·필드는 쓰지 않음, Mart.links)
"""
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
for sub in ("log", "loop", "ladder", "handover", "metrics"):
    sys.path.insert(0, str(PROJECT / "scripts" / sub))
import common  # noqa: E402  (scripts/ladder/common.py)
import devlog  # noqa: E402
import load_mode  # noqa: E402  (scripts/ladder/load_mode.py)
import rule_candidates as rc  # noqa: E402
import state  # noqa: E402
from make_facts import KST, RUNG_NAMES, scrub  # noqa: E402

NONE = "기록 없음"
DASH = "-"
STAGE_NAMES = ("요구서", "결재 1", "루프", "PR", "결재 2", "운영", "L6")
DONE, WAIT, ACTIVE, HALT, REJECT = "완료", "대기", "진행 중", "멈춤", "반려"
# 사다리 단계 이름(make_facts.RUNG_NAMES + L6)과 통과 조건. 출처 03 §5.3 표 (시험이 단계 목록 일치를 본다)
RUNG_INFO = {
    **{k: {"name": v} for k, v in RUNG_NAMES.items()},
    "L6": {"name": "L6 OM 등록 확인 (결재 후)"},
}
PASS_RULES = {
    "L0": "contract 형식, DAG 구조(task 목록·의존성 = contract, SQL 파일과 task 1:1), 검증 쿼리 머리말이 맞다",
    "L1": "dry-run 문법 통과, 스캔량 500 MB 이하, SQL 원문에 운영 데이터셋 이름이 없다",
    "L2": "ai_dev에서 실행 성공, contract의 테이블이 생긴다",
    "L3": "게이트 파일 = l3 원본에서 생성한 결과, 이 task의 l3 검사 0행",
    "L4": "이 task의 l4 검사(원천 대비 정합성) 0행",
    "L5": "같은 ds 재실행 전후 행 수·체크섬이 같고, l5 검사 0행",
    "L6": "OM에 contract 테이블이 있고 컬럼 설명 누락 0, 리니지 엣지 = contract 기대값",
}
for _k, _v in PASS_RULES.items():
    RUNG_INFO[_k]["pass_rule"] = _v
LADDER_RUNGS = ("L0", "L1", "L2", "L3", "L4", "L5")
# M11에서 빼는 hook_blocks id: 08 §4(2-13 차단 시험 B-0003~B-0006) + V5-1(3-2 차단 시험 B-0007~B-0010).
# 2-20 위험 요청 시험은 Hook 발동 0건이라 없다. 시험이 08 원문과 일치하는지 본다
M11_EXCLUDED = frozenset(f"B-{n:04d}" for n in range(3, 11))
M1_KINDS = ("approval", "correction", "manual_check", "requirement_change")
M12_STAGES = ("approval_1", "approval_2", "ops")              # V4-2
LOOP_STAGES = ("loop_extension", "loop_streak_reset")        # M1에서 따로 보인다 (V4-2)
RULE_STAGES = ("rule_promotion",)                            # M12에 넣지 않고 M1에서 따로 보인다 (V6-2)
NOT_COUNTED_HALTS = ("infra_error", "builder_blocked")       # M2·M3에서 뺀다 (08 §4, 결정 49 ③)
HAND_KINDS = ("correction", "manual_check")                  # 08 §3 M1 실패 기준
RISK_SECTION = re.compile(r"^## 위험 항목.*?(?=^## |\Z)", re.M | re.S)
RISK_ROW = re.compile(r"^\|\s*\d+\s*\|(.*)\|\s*$", re.M)
NO_CHECK = ("", "-", "—")                                     # 위험 표 "막는 check" 칸이 비었다는 표시
ADDED_LATER = "(인터뷰 뒤 추가)"
DIFFICULTY = re.compile(r"^## 6\. 난이도.*\n\|(.+)\|\s*\n\|[-| ]+\|\s*\n\|(.+)\|\s*$", re.M)
# 사다리가 만든 문장 중 화면에 넣는 것: L5 멱등성 비교(l5_idem.break_message). 이 형식이 아니면 오류 원문일 수 있어
# 넣지 않는다. 행 수는 건수이고 체크섬 값은 문장에 없다
LADDER_NOTE = re.compile(r"같은 ds로 2번 실행한 결과가 다름 \(행 수 (?:[\d,]+|없음) → (?:[\d,]+|없음), 체크섬 (?:같음|다름)\)")
RULE_LINE = re.compile(r"^--\s?(?:[A-Z]+-\d+\s*:\s*)?(.*)$")
CHECK_RUNGS = ("L3", "L4", "L5")
COST_FIELDS = ("input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens", "total_cost_usd",
               "bq_bytes_processed")


# ---------- 읽기 ----------

def ts_of(text):
    return datetime.fromisoformat(text)


def text(value):
    """자유 문장: 프로젝트 ID·메일을 가린다. 비면 "기록 없음"."""
    return scrub(value) if isinstance(value, str) and value.strip() else NONE


def contracts(root):
    folder = Path(root) / "docs" / "requirements"
    out = {}
    for f in sorted(folder.glob("*.contract.json")):
        if f.name.startswith("_"):
            continue
        c = json.loads(f.read_text(encoding="utf-8"))
        out[c["mart"]] = c
    return out


def head(root):
    p = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True)
    return p.stdout.decode("utf-8", "replace").strip() if p.returncode == 0 else NONE


# ---------- 다음 행동 링크 (D-05): git remote(origin)와 기록의 "PR #숫자"만 읽는다 ----------
PR_NO = re.compile(r"PR #(\d+)")
REPO_PART = re.compile(r"[A-Za-z0-9._-]+")


def github_url(remote):
    """remote 주소 → "https://github.com/<org>/<repo>". 계정 정보(userinfo)·포트·끝의 .git·/는 버린다. SSH 꼴
    (git@github.com:org/repo.git, ssh://git@github.com/org/repo)도 https로 바꾼다. 호스트가 github.com이 아니거나
    <org>/<repo> 꼴이 아니면 None(링크를 만들지 않는다)."""
    if not isinstance(remote, str) or not remote.strip():
        return None
    s = remote.strip()
    m = re.fullmatch(r"(?:[^@/:\s]+@)?([^@/:\s]+):(?!//)(.+)", s)  # scp 꼴 SSH: [user@]host:path
    if m:
        host, path = m.group(1), m.group(2)
    else:
        m = re.fullmatch(r"(?:https?|ssh|git)://(?:[^@/]*@)?([^/:?#]+)(?::\d+)?(/[^?#]*)?(?:[?#].*)?", s, re.I)
        if not m:
            return None
        host, path = m.group(1), m.group(2) or ""
    if host.lower() != "github.com":
        return None
    path = path.strip("/")
    path = path[:-4] if path.lower().endswith(".git") else path
    parts = path.split("/")
    if len(parts) != 2 or not all(REPO_PART.fullmatch(p) and p not in (".", "..") for p in parts):
        return None
    return f"https://github.com/{parts[0]}/{parts[1]}"


def repo_url(root):
    """git remote origin의 GitHub 주소(github_url). remote·git이 없거나 GitHub가 아니면 None. 읽기만 한다."""
    try:
        p = subprocess.run(["git", "-C", str(root), "remote", "get-url", "origin"], capture_output=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    return github_url(p.stdout.decode("utf-8", "replace")) if p.returncode == 0 else None


def pr_number(record):
    """기록 한 줄의 target에서 "PR #숫자"만. 번호가 없거나 서로 다른 번호가 둘 이상이면 None.
    target의 나머지 글자와 note 등 다른 필드는 쓰지 않는다(자유 문장 사용 금지, D-05)."""
    target = record.get("target") if record else None
    nums = set(PR_NO.findall(target)) if isinstance(target, str) else set()
    return int(nums.pop()) if len(nums) == 1 else None


def pr_link(record, repo):
    """{"number": n, "url": 주소 또는 None(remote가 없거나 GitHub가 아님)} 또는 None(번호 없음)."""
    n = pr_number(record)
    if n is None:
        return None
    return {"number": n, "url": f"{repo}/pull/{n}" if repo else None}


def by_ts(rows):
    return sorted(rows, key=lambda r: ts_of(r["ts"]))


def first(rows):
    return by_ts(rows)[0] if rows else None


def mins(r):
    v = r.get("minutes_spent")
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else 0


class Logs:
    def __init__(self, dev, extra_interventions=()):
        self.dev = Path(dev)
        # extra: 대시보드가 git 머지 기록에서 읽은, 아직 기록되지 않은 결재 줄(화면에만, 결정 80 ⑤)
        self.interventions = devlog.read_lines(self.dev / "interventions.jsonl") + list(extra_interventions)
        self.rejections = devlog.read_lines(self.dev / "rejections.jsonl")
        self.cost = devlog.read_lines(self.dev / "cost.jsonl")
        self.hook_blocks = devlog.read_lines(self.dev / "hook_blocks.jsonl")
        progress = self.dev / "progress.md"
        self.progress = progress.read_text(encoding="utf-8") if progress.exists() else ""

    def of(self, mart, kind=None, stage=None):
        return [r for r in self.interventions if r.get("mart") == mart and (kind is None or r.get("kind") == kind)
                and (stage is None or r.get("stage") == stage)]

    def progress_marts(self):
        """progress.md는 마트들이 함께 쓴다. "## 작업 목록 — <마트>" 절이 있는 마트들."""
        return state.progress_marts(self.progress)


class Mart:
    def __init__(self, root, logs, contract):
        self.root, self.logs, self.contract = Path(root), logs, contract
        self.mart, self.version = contract["mart"], contract["version"]
        self.results = state.load_results(logs.dev, self.mart, self.version)
        self.iters = state.iterations(self.results)
        self.counts = state.counts(self.iters, logs.interventions, self.mart, self.version)
        self.posts = devlog.post_results(self.mart, self.mart, self.version, logs.dev)
        self.latest_post = devlog.latest_post(self.mart, self.mart, self.version, logs.dev)
        self.loads = common.topo_load_tasks(contract)
        self.approval2 = first(logs.of(self.mart, "approval", "approval_2"))
        self.promoted = rc.promoted_map(root)
        try:
            self.harness_cause = set(rc.load_exclusions(root))  # 사람이 관리하는 제외 목록. M2 계산과 무관하다
        except ValueError:
            self.harness_cause = set()
        self.rules = {c["id"]: c.get("rule") for group in contract.get("checks", {}).values() for c in group}
        self.checks = check_files(root, self.mart, self.rules)

    # ---------- ③ 진행 단계 ----------

    def loop_state(self):
        """루프: 반복이 없으면 대기, 마지막 반복이 pass면 완료, halt면 멈춤(halt_reason), reject면 진행 중."""
        if not self.iters:
            return WAIT, None, None
        last = self.iters[-1]
        if last.verdict == "pass":
            return DONE, last, None
        if last.verdict == "halt":
            return HALT, last, last.halt_reason
        return ACTIVE, last, None

    def stages(self):
        """[{"name", "state", "basis", ...}]. 근거는 기록 id·파일 이름만(원문 메시지 없음).
        요구서: <마트>.md·contract / 결재 1: approval·approval_1 / 루프: state.iterations /
        PR: 루프 통과 뒤 첫 approval·ops / 결재 2: 첫 approval·approval_2 / 운영: 결재 2 뒤 ops_run /
        L6: 최신 post 결과(pass 완료, reject 반려).
        done_at: 완료한 기록의 ts(표시용, 판정에 쓰지 않음). 요구서는 ts 기록이 없어 NONE."""
        logs, out = self.logs, []
        req = (self.root / "docs" / "requirements" / f"{self.mart}.md").exists()
        out.append({"name": "요구서", "state": DONE if req else WAIT,
                    "basis": f"docs/requirements/{self.mart}.md" if req else NONE, "done_at": NONE})
        a1 = first(logs.of(self.mart, "approval", "approval_1"))
        out.append({"name": "결재 1", "state": DONE if a1 else WAIT, "basis": a1["id"] if a1 else NONE,
                    "target": text(a1["target"]) if a1 else NONE, "done_at": a1["ts"] if a1 else NONE})
        loop, last, reason = self.loop_state()
        out.append({"name": "루프", "state": loop, "halt_reason": reason,
                    "iterations": f"{self.counts.judged}/{self.counts.limit}",
                    "basis": f"반복 {last.n}" if last else NONE, "done_at": last.ts if loop == DONE else NONE})
        pr = None
        if loop == DONE:
            pr = first([r for r in logs.of(self.mart, "approval", "ops") if ts_of(r["ts"]) > ts_of(last.ts)])
        out.append({"name": "PR", "state": DONE if pr else WAIT, "basis": pr["id"] if pr else NONE,
                    "target": text(pr["target"]) if pr else NONE, "done_at": pr["ts"] if pr else NONE})
        a2 = self.approval2
        out.append({"name": "결재 2", "state": DONE if a2 else WAIT, "basis": a2["id"] if a2 else NONE,
                    "target": text(a2["target"]) if a2 else NONE, "done_at": a2["ts"] if a2 else NONE})
        ops = by_ts([r for r in logs.of(self.mart, "ops_run") if a2 and ts_of(r["ts"]) >= ts_of(a2["ts"])])
        out.append({"name": "운영", "state": DONE if ops else WAIT, "basis": [r["id"] for r in ops] or NONE,
                    "targets": [text(r["target"]) for r in ops], "done_at": ops[-1]["ts"] if ops else NONE})
        lp = self.latest_post
        l6 = WAIT if lp is None else DONE if lp.get("verdict") == "pass" else \
            REJECT if lp.get("verdict") == "reject" else HALT
        out.append({"name": "L6", "state": l6, "basis": lp["_name"] if lp else NONE,
                    "halt_reason": lp.get("halt_reason") if lp else None,
                    "done_at": (lp.get("ts") or NONE) if l6 == DONE else NONE})
        current = next((s["name"] for s in out if s["state"] != DONE), None)
        for s in out:
            s["current"] = s["name"] == current
        return out

    def links(self, repo):
        """다음 행동 링크 (D-05). kind=approval 기록 한 줄의 target에서만 "PR #숫자"를 읽는다.
        요구서 PR = 결재 1 근거(approval_1), 없으면 PR 단계 근거가 아닌 가장 이른 ops 기록.
        구현 PR = 결재 2 근거(approval_2), 없으면 PR 단계 근거(루프 통과 뒤 첫 ops)."""
        logs = self.logs
        s = {x["name"]: x for x in self.stages()}
        rows = {r.get("id"): r for r in logs.of(self.mart, "approval")}
        a1, a2 = rows.get(s["결재 1"]["basis"]), rows.get(s["결재 2"]["basis"])
        pr = rows.get(s["PR"]["basis"])
        if a1 is None:
            a1 = first([r for r in logs.of(self.mart, "approval", "ops") if r is not pr])
        return {"request_pr": pr_link(a1, repo), "impl_pr": pr_link(a2 or pr, repo)}

    # ---------- ④ 사다리 격자 ----------

    def grid(self):
        """task × L0~L5 칸마다 반복 이력, L6는 "contract 전체" 1행. 칸 값은 status·error_type·위반 건수만."""
        rows = []
        cells = {t["id"]: {r: [] for r in LADDER_RUNGS} for t in self.loads}
        verdicts = {t["id"]: [] for t in self.loads}
        for f in self.results:
            tid = f["task"]
            if tid in cells:
                verdicts[tid].append({"iteration": f["iteration"], "verdict": f["verdict"],
                                      "halt_reason": f.get("halt_reason"), "ts": f.get("ts") or NONE,
                                      "file": f["_path"].name if f.get("_path") else NONE})
                for g in f["rungs"]:
                    if g["rung"] in cells[tid]:
                        cells[tid][g["rung"]].append(cell(f["iteration"], g, f.get("ts")))
            for it in f.get("interrupted_tasks") or []:  # 다른 task 실패로 중단: 통과한 단계만
                for name in it["passed_rungs"]:
                    if it["task"] in cells and name in cells[it["task"]]:
                        cells[it["task"]][name].append({"iteration": f["iteration"], "status": "pass",
                                                        "note": "중단(다른 task 실패)", "ts": f.get("ts") or NONE})
        for t in self.loads:
            rows.append({"task": t["id"], "layer": t["layer"], "cells": cells[t["id"]],
                         "verdicts": verdicts[t["id"]], "table": table_name(self.contract, t["id"]),
                         "task_sql": task_sql(self.root, self.mart, t),
                         "checks": {r: self.checks.get(r, {}).get(t["id"], []) for r in CHECK_RUNGS}})
        l6 = []
        for p in self.posts:
            g = next((x for x in p.get("rungs", []) if x.get("rung") == "L6"), None)
            entry = {"iteration": f"post-{p['_n']}", "verdict": p.get("verdict"), "ts": p.get("ts") or NONE,
                     "file": p.get("_name") or NONE}
            if g is not None:
                m = g.get("metrics", {})
                entry.update(status=g["status"], error_type=g.get("error_type"),
                             counts={k: len(m.get(k, [])) for k in ("tables_missing", "description_missing",
                                                                     "edges_missing", "edges_unexpected")})
            l6.append(entry)
        return {"rows": rows, "l6": {"task": "(contract 전체)", "history": l6}, "summary": grid_summary(rows, l6),
                "partition_column": load_mode.partition_column(self.contract)}

    def l6_check(self, now):
        """L6 확인 시각·경과일과 재확인 필요(결정 72). 마지막 L6 = 모든 contract 버전의 post 결과 중 ts가 가장 늦은 것.
        재확인 사유: ① 마지막 L6의 contract 버전 != 현재 버전 ② 마지막 L6 뒤 ops_run이 있다
        ③ L6가 없는데 ops_run이 있다. L6도 ops_run도 없으면 확인 전(재확인 아님)."""
        posts = [p for v in range(1, int(self.version) + 1)
                 for p in devlog.post_results(self.mart, self.mart, v, self.logs.dev)]
        posts = [p for p in posts if isinstance(p.get("ts"), str)]
        ops = by_ts(self.logs.of(self.mart, "ops_run"))
        last = max(posts, key=lambda p: ts_of(p["ts"])) if posts else None
        reasons = []
        if last is None:
            if ops:
                reasons.append("L6 없음 (ops_run 뒤 L6 결과 파일이 없다)")
            return {"checked_at": NONE, "age_days": NONE, "basis": NONE, "verdict": NONE,
                    "contract_version": NONE, "current_version": self.version, "recheck": bool(reasons),
                    "reasons": reasons, "ops_after": [r["id"] for r in ops]}
        at = ts_of(last["ts"])
        v = last.get("contract_version")
        if v != self.version:
            reasons.append(f"contract 버전 변경 (L6 v{v} → 현재 v{self.version})")
        after = [r["id"] for r in ops if ts_of(r["ts"]) > at]
        if after:
            reasons.append(f"L6 뒤 ops_run {len(after)}건")
        return {"checked_at": last["ts"], "age_days": max((ts_of(now) - at).days, 0), "basis": last["_name"],
                "verdict": last.get("verdict"), "contract_version": v, "current_version": self.version,
                "recheck": bool(reasons), "reasons": reasons, "ops_after": after}

    # ---------- ⑥ 반려 상세 ----------

    def ladder_file(self, rej):
        return next((f for f in self.results if f["task"] == rej["task"] and f["iteration"] == rej["iteration"]
                     and f["verdict"] == "reject"), None)

    def rejection_rows(self):
        own = self.mart in self.logs.progress_marts()
        out = []
        for r in by_ts([x for x in self.logs.rejections if x.get("mart") == self.mart]):
            f = self.ladder_file(r) if r.get("iteration") != "post" else None
            m = f["rungs"][-1].get("metrics", {}) if f else {}
            check_id = m.get("check")
            lines = state.three_lines(self.logs.progress, r["id"]) if own else []
            out.append({"id": r["id"], "ts": r["ts"], "task": r["task"], "iteration": r["iteration"],
                        "contract_version": r.get("contract_version"), "caught_by_rung": r["caught_by_rung"],
                        "error_type": r["error_type"], "error_class": r["error_class"],
                        "check": check_id or NONE,
                        "rule": text(self.rules.get(check_id)) if check_id else NONE,
                        "violations": violations(m),
                        "three_lines": [scrub(x) for x in lines] or NONE,
                        "rule_promoted": self.promoted.get(r["id"]), "harness_cause": r["id"] in self.harness_cause})
        return out

    def measured_rejections(self):
        """본 측정 반려(노하우 켠 실행 제외, 08 §4). M10이 쓴다."""
        return [r for r in self.logs.rejections if r.get("mart") == self.mart and not self.expert_on(self.ladder_file(r))]

    # ---------- ⑤ 요약 숫자 ----------

    def expert_on(self, f):
        return bool(((f or {}).get("modules") or {}).get("expert", {}).get("on"))

    def summary(self):
        c = self.counts
        return {"iterations": {"judged": c.judged, "limit": c.limit, "extended": c.limit > state.MAX_ITERATIONS,
                               "streak": c.streak, "streak_key": ":".join(c.streak_key) if c.streak_key else None},
                "M1": self.m1(), "M2": self.m2(), "M3": self.m3(), "M4": m4([r for r in self.logs.cost
                                                                          if r.get("mart") == self.mart]),
                "M12": self.m12(), "reused_upstream": self.reused_upstream(), "prep_bytes": sum(p["bytes"] for f in self.results for p in f.get("prep") or []),
                "M1_hand": self.m1_hand(), "M4_by_model": m4_by_model([r for r in self.logs.cost
                                                                       if r.get("mart") == self.mart]),
                "M5": self.m5(), "M6": m6(self.root, self.mart), "M7": self.m7(), "M8": self.m8(),
                "difficulty": difficulty(self.root, self.mart), "exclusions": self.exclusions(),
                "halts": self.halts()}

    def halts(self):
        """멈춤 표(참고, 사전 등록 지표 아님). 결과 파일(반복·post) 전부를 세고 08 §4 제외를 적용하지 않는다.
        M1~M12 계산에 쓰지 않는다. 1회차 이전 멈춤은 결과 파일이 없어 세지 못한다."""
        files = [*self.results, *self.posts]
        by_reason = {}
        for f in files:
            if f.get("verdict") == "halt":
                reason = f.get("halt_reason") or NONE
                by_reason[reason] = by_reason.get(reason, 0) + 1
        return {"runs": len(files), "count": sum(by_reason.values()), "by_reason": by_reason}

    def reused_upstream(self):
        """재사용한 상류 task: contract upstream의 <마트>:<task>, 중복 없이 (08 V3-1)."""
        return sorted({u for t in self.contract["dag"]["tasks"] for u in t["upstream"] if ":" in u})

    def split_v47(self):
        """(본 측정, 유지보수): 첫 approval_2 ts까지 / 그 뒤 (V4-7). 같은 초의 줄은 문구대로 본 측정 쪽이다."""
        rows = self.logs.of(self.mart)
        if self.approval2 is None:
            return rows, []
        cut = ts_of(self.approval2["ts"])
        return [r for r in rows if ts_of(r["ts"]) <= cut], [r for r in rows if ts_of(r["ts"]) > cut]

    def m1(self):
        main, later = self.split_v47()

        def tally(rows):
            out = {k: {"count": 0, "minutes": 0} for k in M1_KINDS}
            stages = {s: {"count": 0, "minutes": 0} for s in (*M12_STAGES, *LOOP_STAGES, *RULE_STAGES)}
            for r in rows:
                if r.get("kind") in out:
                    out[r["kind"]]["count"] += 1
                    out[r["kind"]]["minutes"] += mins(r)
                if r.get("kind") == "approval" and r.get("stage") in stages:
                    stages[r["stage"]]["count"] += 1
                    stages[r["stage"]]["minutes"] += mins(r)
            return {"by_kind": out, "approval_by_stage": stages,
                    "count": sum(v["count"] for v in out.values()), "minutes": sum(v["minutes"] for v in out.values())}
        ops = self.logs.of(self.mart, "ops_run")
        return {"main": tally(main), "maintenance": tally(later),
                "ops_run": {"count": len(ops), "minutes": sum(mins(r) for r in ops)},
                "cutoff": self.approval2["id"] if self.approval2 else None}

    def m1_hand(self):
        """결재 2 전 correction·manual_check 줄의 id (08 §3 M1). 문장은 record_texts로 따로 읽는다."""
        return [{"id": r["id"], "kind": r["kind"]} for r in by_ts(self.split_v47()[0]) if r.get("kind") in HAND_KINDS]

    def m5(self):
        """결재 후 발견 결함: post_approval_defect 줄 수, missed_by_rung별 (08 M5)."""
        rows = by_ts(self.logs.of(self.mart, "post_approval_defect"))
        by_rung = {}
        for r in rows:
            by_rung[r["missed_by_rung"]] = by_rung.get(r["missed_by_rung"], 0) + 1
        return {"count": len(rows), "by_missed_by_rung": by_rung,
                "rows": [{"id": r["id"], "missed_by_rung": r["missed_by_rung"]} for r in rows]}

    def m7(self):
        """첫 approval_1 ts 이후 requirement_change를 cause별로 (08 M7, V4-6). 첫 approval_2 뒤는 유지보수 (V4-7)."""
        a1 = first(self.logs.of(self.mart, "approval", "approval_1"))

        def tally(rows):
            rows = [r for r in by_ts(rows) if r.get("kind") == "requirement_change"
                    and a1 and ts_of(r["ts"]) >= ts_of(a1["ts"])]
            by_cause = {c: sum(1 for r in rows if r.get("cause") == c) for c in sorted(devlog.CAUSES)}
            return {"count": len(rows), "by_cause": by_cause,
                    "rows": [{"id": r["id"], "cause": r.get("cause")} for r in rows]}
        main, later = self.split_v47()
        return {"main": tally(main), "maintenance": tally(later)}

    def m8(self):
        """첫 approval_1 ts부터 마지막 approval_2 ts까지의 시간 (08 M8). 없는 결재 단계가 있으면 값을 내지 않는다."""
        a1 = by_ts(self.logs.of(self.mart, "approval", "approval_1"))
        a2 = by_ts(self.logs.of(self.mart, "approval", "approval_2"))
        missing = [s for s, rows in (("approval_1", a1), ("approval_2", a2)) if not rows]
        if missing:
            return {"hours": NONE, "missing": missing}
        seconds = (ts_of(a2[-1]["ts"]) - ts_of(a1[0]["ts"])).total_seconds()
        return {"hours": round(seconds / 3600, 2), "missing": [], "start": a1[0]["id"], "end": a2[-1]["id"]}

    def exclusions(self):
        """08 §4로 뺀 것: 노하우 켠 결과 파일, infra_error·builder_blocked 멈춤 파일, 유지보수 개입 id (V4-7)."""
        halts = {}
        for f in self.results:
            if f["verdict"] == "halt" and f.get("halt_reason") in NOT_COUNTED_HALTS:
                halts.setdefault(f["halt_reason"], []).append(f["_path"].name)
        later = by_ts(self.split_v47()[1])
        return {"expert_on": [f["_path"].name for f in self.results if self.expert_on(f)], "halts": halts,
                "maintenance": [r["id"] for r in later],
                "maintenance_ops_run": sum(1 for r in later if r.get("kind") == "ops_run"),
                "same_second_ops_run": self.same_second_ops_run()}

    def same_second_ops_run(self):
        """첫 approval_2와 같은 초에 기록된 ops_run. V4-7 문구대로 결재 2 이전에 들어가 6절에 사실로 밝힌다."""
        a2 = self.approval2
        rows = [r["id"] for r in self.logs.of(self.mart, "ops_run") if a2 and ts_of(r["ts"]) == ts_of(a2["ts"])]
        return {"approval_2": a2["id"], "ids": rows} if rows else None

    def m12(self):
        main, later = self.split_v47()

        def tally(rows):
            out = {s: sum(1 for r in rows if r.get("kind") == "approval" and r.get("stage") == s) for s in M12_STAGES}
            return {"by_stage": out, "count": sum(out.values())}
        return {"main": tally(main), "maintenance": tally(later)}

    def m2(self):
        base, ext, expert, post = [], [], [], []
        for r in self.logs.rejections:
            if r.get("mart") != self.mart:
                continue
            if r.get("iteration") == "post":
                post.append(r)
            elif self.expert_on(self.ladder_file(r)):
                expert.append(r)
            elif self.counts.extension_from and ts_of(r["ts"]) > ts_of(self.counts.extension_from):
                ext.append(r)
            else:
                base.append(r)

        def tally(rows):
            out = {"count": len(rows)}
            for key in ("error_type", "caught_by_rung", "error_class"):
                out[f"by_{key}"] = {}
                for r in rows:
                    out[f"by_{key}"][r[key]] = out[f"by_{key}"].get(r[key], 0) + 1
            return out
        return {"base": tally(base), "extension": tally(ext), "total": tally(base + ext),
                "post_approval": tally(post), "expert_on": tally(expert)}

    def m3(self):
        """task마다 reject 파일 수와 마지막 파일 분류. infra_error·builder_blocked 멈춤 파일과 노하우 켠 파일은 뺀다."""
        out = {}
        ext_iters = {it.n for it in self.iters if state.is_extension(it, self.counts)}
        for t in self.loads:
            files = [f for f in self.results if f["task"] == t["id"] and not self.expert_on(f)
                     and not (f["verdict"] == "halt" and f.get("halt_reason") in NOT_COUNTED_HALTS)]
            rejects = [f for f in files if f["verdict"] == "reject"]
            if not files:
                kind = NONE
            elif not rejects:
                kind = "반려 없음"
            elif files[-1]["verdict"] == "pass":
                kind = "연장 결재 뒤 통과" if files[-1]["iteration"] in ext_iters else "스스로 고침"
            elif files[-1]["verdict"] == "halt":
                kind = "멈춤"
            else:
                kind = "진행 중"
            out[t["id"]] = {"rejects": len(rejects), "class": kind,
                            "halt_reason": files[-1].get("halt_reason") if files and kind == "멈춤" else None}
        return out


def grid_summary(rows, l6):
    """격자 요약 줄의 수치(표시용). 칸 = task × L0~L5 + L6 1칸. 통과 = 마지막 기록이 pass.
    반려 이력 = 기록에 reject로 남은 칸(멈춘 반복의 실패는 세지 않는다). 판정은 기록 값 그대로다."""
    cells = passed = 0
    at = []
    for r in rows:
        halted = {v["iteration"] for v in r["verdicts"] if v["verdict"] == "halt"}
        for rung in LADDER_RUNGS:
            items = r["cells"][rung]
            cells += 1
            passed += bool(items) and items[-1]["status"] == "pass"
            n = sum(1 for h in items if h["status"] == "fail" and h["iteration"] not in halted)
            if n:
                at.append({"task": r["task"], "rung": rung, "count": n})
    cells += 1
    passed += bool(l6) and l6[-1].get("verdict") == "pass"
    n = sum(1 for h in l6 if h.get("verdict") == "reject")
    if n:
        at.append({"task": "(contract 전체)", "rung": "L6", "count": n})
    return {"cells": cells, "passed": int(passed), "rejected": len(at), "rejected_at": at}


def cell(n, g, at=None):
    """칸 이력 1건. checks는 이 반복에서 통과한 검사 id(metrics.checks). 오류 글자(metrics.message)는
    L5의 LADDER_NOTE 형식(사다리가 만든 비교 문장)일 때만 ladder_note로 넣고, 그 밖에는 넣지 않는다."""
    m = g.get("metrics", {})
    out = {"iteration": n, "status": g["status"], "ts": at or NONE}
    ran = m.get("checks")
    if isinstance(ran, list):
        out["checks"] = [x for x in ran if isinstance(x, str)]
    if g["status"] == "fail":
        out.update(error_type=g.get("error_type"), check=m.get("check") or NONE, violations=violations(m))
        msg = m.get("message")
        if g.get("rung") == "L5" and isinstance(msg, str) and LADDER_NOTE.fullmatch(msg.strip()):
            out["ladder_note"] = msg.strip()
    return out


def rule_sentence(body):
    """검사 본문 맨 위 주석 줄(`-- C-01: ...`)을 한 문장으로. 주석 줄이 없으면 None."""
    lines = []
    for line in body.splitlines():
        if not line.strip().startswith("--"):
            break
        lines.append(RULE_LINE.match(line.strip()).group(1).strip())
    return " ".join(x for x in lines if x) or None


def check_files(root, mart, rules):
    """{단계: {task: [검사]}}. 검사 = id·파일 경로·error_type·규칙 문장·SQL 원문(파일 그대로, scrub).
    규칙 문장은 본문 맨 위 주석 줄, 없으면 contract rule. 형식이 틀린 파일은 사다리가 halt로 다루므로 여기서는
    task를 알 수 없어 넣지 않는다(판정을 다시 하지 않는다)."""
    paths = common.Paths(root, mart)
    out = {}
    for stage in common.STAGES:
        rung = common.STAGE_RUNG[stage]
        for f in paths.check_files(stage):
            try:
                raw = f.read_text(encoding="utf-8").lstrip("﻿")
                header, body = common.parse_check(raw)
            except (OSError, UnicodeDecodeError, ValueError):
                continue
            out.setdefault(rung, {}).setdefault(header["task"], []).append(
                {"id": f.stem, "file": f.relative_to(Path(root)).as_posix(), "error_type": header["error_type"],
                 "rule": text(rule_sentence(body) or rules.get(f.stem)), "sql": scrub(raw.strip())})
    return out


def task_sql(root, mart, task):
    """L1·L2 칸 패널의 task SQL: 파일 경로와 원문(파일 그대로, scrub). 읽지 못하면 원문은 NONE. 판정에 쓰지 않는다."""
    f = common.Paths(root, mart).task_sql(task)
    try:
        sql = scrub(f.read_text(encoding="utf-8").lstrip("﻿").strip())
    except (OSError, UnicodeDecodeError):
        sql = NONE
    return {"file": f.relative_to(Path(root)).as_posix(), "sql": sql}


def table_name(contract, task_id):
    """task가 만드는 테이블 이름(L5 내장 쿼리 표시용). contract에 없으면 NONE."""
    return next((t["name"] for t in contract.get("tables", []) if t.get("task") == task_id), NONE)


def violations(metrics):
    """위반 건수: violations_shown. EVIDENCE_ROWS(5)면 쿼리를 6행까지만 받았으므로 "5건 이상"."""
    n = metrics.get("violations_shown")
    if not isinstance(n, int) or isinstance(n, bool):
        return NONE
    return f"{n}건 이상" if n >= common.EVIDENCE_ROWS else f"{n}건"


def m4(rows):
    out = {"calls": len(rows), "note": "total_cost_usd는 정가 환산 추정 (결정 52 ④)"}
    for k in COST_FIELDS:
        values = [r.get(k) for r in rows if isinstance(r.get(k), (int, float)) and not isinstance(r.get(k), bool)]
        out[k] = (round(sum(values), 6) if k == "total_cost_usd" else sum(values)) if values else NONE
        out[f"{k}_null"] = len(rows) - len(values)
    return out


def record_texts(logs):
    """{개입 id: 자유 문장}. 08 §3이 보고하라는 칸만 scrub해서 준다. 대시보드 JSON에 나가지 않게 collect()에는 넣지 않는다."""
    return {r["id"]: {k: text(r.get(k)) for k in ("target", "note", "found_stage", "detail")}
            for r in logs.interventions}


def m4_by_model(rows):
    """모델별 m4 (08 V2-1). 계산은 m4 그대로이고 나누기만 한다."""
    return {model: m4([r for r in rows if r.get("model") == model])
            for model in sorted({r.get("model") for r in rows if r.get("model")})}


def m6(root, mart):
    """인터뷰 기록의 위험 표 줄 수와 그중 "막는 check"가 있는 줄 수 (08 M6). 위험 문장은 데이터 값이 있어 읽어 내지 않는다."""
    path = Path(root) / "docs" / "requirements" / f"{mart}_interview.md"
    section = RISK_SECTION.search(path.read_text(encoding="utf-8")) if path.exists() else None
    rows = [[c.strip() for c in row.split("|")] for row in RISK_ROW.findall(section.group(0))] if section else []
    return {"count": len(rows), "with_check": sum(1 for r in rows if r[-1] not in NO_CHECK),
            "added_later": sum(1 for r in rows if r[0].startswith(ADDED_LATER)), "file": "있음" if path.exists() else NONE}


def difficulty(root, mart):
    """요구서 6절 난이도 표 {칸 이름: 값} (08 M9, V3-1). 기록용이고 판정에 쓰지 않는다."""
    path = Path(root) / "docs" / "requirements" / f"{mart}.md"
    m = DIFFICULTY.search(path.read_text(encoding="utf-8")) if path.exists() else None
    if not m:
        return NONE
    return dict(zip((c.strip() for c in m.group(1).split("|")), (scrub(c.strip()) for c in m.group(2).split("|"))))


def mart_order(per):
    """마트 순서: 첫 결재 1 시각 순. 결재 1이 없는 마트는 뒤에 이름 순으로 둔다."""
    def key(mart):
        done = next(s["done_at"] for s in per[mart]["stages"] if s["name"] == "결재 1")
        return (done == NONE, ts_of(done).timestamp() if done != NONE else 0, mart)
    return sorted(per, key=key)


def m9(per, order):
    """마트 순서대로 M2 건수와 M1 건수(ops_run 제외)를 나란히 둔다 (08 M9). 난이도는 함께 보이되 판정에 쓰지 않는다."""
    return [{"mart": m, "rejections": per[m]["summary"]["M2"]["total"]["count"],
             "interventions": per[m]["summary"]["M1"]["main"]["count"],
             "difficulty": per[m]["summary"]["difficulty"]} for m in order]


def m11(logs, marts):
    """제외 id(M11_EXCLUDED)를 뺀 hook_blocks를 reason별로. 마트별은 그 마트의 ladder_result 첫~마지막 ts 사이."""
    windows = {}
    for m in marts:
        times = [ts_of(f["ts"]) for f in m.results] + [ts_of(p["ts"]) for p in m.posts]
        if times:
            windows[m.mart] = (min(times), max(times))
    counted = [r for r in logs.hook_blocks if r.get("id") not in M11_EXCLUDED]
    by_reason, by_mart = {}, {}
    for r in counted:
        by_reason[r["reason"]] = by_reason.get(r["reason"], 0) + 1
        t = ts_of(r["ts"])
        owner = next((mart for mart, (a, b) in windows.items() if a <= t <= b), "마트 밖")
        by_mart[owner] = by_mart.get(owner, 0) + 1
    return {"count": len(counted), "by_reason": by_reason, "by_mart": by_mart,
            "excluded": sorted(r["id"] for r in logs.hook_blocks if r.get("id") in M11_EXCLUDED)}


def learned_state(rule, interventions):
    if rule["rule_id"] is None:
        return "형식 확인 필요"
    if rule["pending"]:
        return "결재 기록 대기"
    record = interventions.get(rule["approval"])
    return "승격" if record and record.get("stage") == "rule_promotion" else "형식 확인 필요"


def m10(logs, marts, learned, candidates, excluded=()):
    """승격된 규칙마다 그 error_type의 반려를 승격 결재 시각 전후로 마트별로 센다 (08 M10·V6-5).
    계산식은 제외 목록과 무관하다. excluded는 그 안에 든 제외 목록 반려 수를 함께 보이려고 센다."""
    types = {c["id"]: c["error_type"] for c in candidates}
    records = {r.get("id"): r for r in logs.interventions}
    out = []
    for rule in learned:
        if rule["state"] != "승격" or types.get(rule["rule_id"], NONE) == NONE:
            continue
        at = ts_of(records[rule["approval"]]["ts"])
        by_mart = {}
        for m in marts:
            rows = [r for r in m.measured_rejections() if r["error_type"] == types[rule["rule_id"]]]
            by_mart[m.mart] = {"before": sum(1 for r in rows if ts_of(r["ts"]) <= at),
                               "after": sum(1 for r in rows if ts_of(r["ts"]) > at),
                               "excluded": sum(1 for r in rows if r["id"] in excluded)}
        out.append({"rule_id": rule["rule_id"], "error_type": types[rule["rule_id"]], "by_mart": by_mart})
    return out


def rules(root, logs, marts=()):
    """⑦ 승격 규칙(.claude/rules/learned/*.md)과 후보(.dev/rule_candidates.md), M10, 후보 집계 제외. 문장은 scrub."""
    records = {r.get("id"): r for r in logs.interventions}
    learned = []
    for x in rc.learned_rules(root):
        learned.append({"file": x["file"], "title": text(x["title"]), "paths": x["paths"], "source": text(x["source"]),
                        "rule_id": x["rule_id"], "approval": x["approval"], "state": learned_state(x, records)})
    try:
        excluded = sorted(rc.load_exclusions(root))
    except ValueError:
        excluded = []
    known = {r.get("id") for r in logs.rejections}
    candidates = []
    path = Path(logs.dev) / rc.FILE_NAME
    if path.exists():
        for c in rc.parse_candidates(path.read_text(encoding="utf-8")):
            state = text(c["state"])  # 근거 부족은 표시만 한다. 후보 파일의 상태는 자동으로 내리지 않는다
            candidates.append({"id": c["id"], "title": text(c["title"]), "error_type": c["error_type"] or NONE,
                               "basis": text(c["evidence"]), "checks": text(c["checks"]), "recorded_state": state,
                               "state": rc.SHORT if rc.evidence_short(c, excluded, known) else state})
    return {"learned": learned, "candidates": candidates, "candidates_file": "있음" if path.exists() else NONE,
            "promoted": sum(1 for x in learned if x["state"] == "승격"), "excluded": excluded,
            "m10": m10(logs, marts, learned, candidates, excluded)}


# ---------- 모으기 ----------

def mart_name_ko(contract):
    """contract tables 중 mart 층 테이블의 name_ko. 없으면 None."""
    name = next((t.get("name_ko") for t in contract.get("tables", []) if t.get("layer") == "mart"), None)
    return scrub(name) if isinstance(name, str) and name.strip() else None


def collect(root=PROJECT, dev=None, now=None, extra_interventions=()):
    """화면 7개의 값. 결과에는 evidence·오류 원문·프로젝트 ID·메일이 없다(시험이 확인)."""
    root = Path(root)
    logs = Logs(dev or root / ".dev", extra_interventions)
    cs = contracts(root)
    marts = [Mart(root, logs, c) for c in cs.values()]
    now = now or datetime.now(KST).isoformat(timespec="seconds")
    repo = repo_url(root)
    per = {}
    for m in marts:
        per[m.mart] = {"version": m.version, "requested_by": m.contract.get("requested_by") or DASH,
                       "name_ko": mart_name_ko(m.contract),
                       "stages": m.stages(), "grid": m.grid(), "summary": m.summary(),
                       "rejections": m.rejection_rows(), "l6_check": m.l6_check(now), "links": m.links(repo)}
    queue = {"approval_1": [], "halted": [], "approval_2": [], "l6_reject": []}
    for mart, d in per.items():
        s = {x["name"]: x for x in d["stages"]}
        if s["결재 1"]["state"] == WAIT:
            queue["approval_1"].append({"mart": mart, "requested_by": d["requested_by"]})
        if s["루프"]["state"] == HALT:
            queue["halted"].append({"mart": mart, "halt_reason": s["루프"]["halt_reason"]})
        if s["루프"]["state"] == DONE and s["결재 2"]["state"] == WAIT:
            queue["approval_2"].append({"mart": mart, "pr": s["PR"]["state"]})
        if s["L6"]["state"] == REJECT:
            queue["l6_reject"].append({"mart": mart, "basis": s["L6"]["basis"]})
    order = mart_order(per)
    total_m2 = {}
    for d in per.values():
        for k, v in d["summary"]["M2"]["total"]["by_error_type"].items():
            total_m2[k] = total_m2.get(k, 0) + v
    return {
        "header": {"generated_at": now, "commit": head(root),
                   "contracts": {m: d["version"] for m, d in per.items()}, "repo_url": repo},
        "queue": queue,
        "marts": per,
        "rungs": RUNG_INFO,
        "summary": {"M2_by_error_type": total_m2, "M4": m4(logs.cost), "M4_by_model": m4_by_model(logs.cost),
                    "M9": m9(per, order), "mart_order": order, "M11": m11(logs, marts),
                    "M1_minutes_main": sum(d["summary"]["M1"]["main"]["minutes"] for d in per.values()),
                    "M12_main": sum(d["summary"]["M12"]["main"]["count"] for d in per.values())},
        "rules": rules(root, logs, marts),
        "notes": {"iteration0_halts": "1회차 이전 멈춤은 progress.md 인계에만 남는다(결과 파일 없음)",
                  "progress_marts": logs.progress_marts() or NONE},
    }


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(collect(), ensure_ascii=False, indent=2, default=str))
