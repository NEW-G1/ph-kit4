"""인수인계 초안의 사실 부분 생성기 (03 §6.7, 진행표 4-5 중 사실 부분).

  python scripts/handover/make_facts.py --mart <마트> [--branch B] [--base REF] [--root R] [--dev-dir D]
         [--out PATH] [--date YYYY-MM-DD] [--head REF] [--check | --restamp]

- 입력: git diff(브랜치 기준점 대비), contract, .dev/ladder_results·rejections·cost·interventions
- 출력: .dev/handover/<브랜치>.md (03 §6.7 템플릿). 코드가 채우는 칸(2 바뀐 것, 3 데이터 흐름, 4 검증 결과와 비용,
  5 반려 이력, 8 링크)만 채우고, AI가 채우는 칸(1 한 줄 요약, 6 운영 방법, 7 주의점)은 빈 자리로 둔다
- 데이터 값은 넣지 않는다. 건수·바이트·판정만 쓴다(rejections의 evidence, rung metrics의 evidence는 옮기지 않는다)
- 계정·프로젝트 ID는 넣지 않는다. 옮기는 문장 속 `<프로젝트>:<데이터셋>.`·`<프로젝트>.<데이터셋>.`과 메일 주소는 가린다
- L6는 순번 파일(<마트>-v<버전>-post-<n>.json) 중 가장 큰 n을 최신 L6로 보인다. L6 반려의 해결은 그 뒤 통과한
  첫 순번 파일이다 (devlog.post_results·post_fixed_in, 결정 67)
- 반려 이력은 rejections 줄을 그대로 옮기고, 같은 마트의 interventions 줄도 해석 없이 함께 보인다
  (하네스 결함 재시작 같은 개입이 기록돼 있으면 그대로 보인다)
- 기준점(--base)의 기본값은 HEAD와 origin/main의 merge-base, 없으면 main과의 merge-base
- 안내문 아래에 도장 3줄(contract_version·생성 시각·기준 커밋)을 찍는다 (결정 64 ⑤)
- --check: 초안이 최신이면 0, 아니면 2와 "halt input_invalid: …" 한 줄 (freshness_problems)
- --restamp: 있는 초안의 제목 줄과 설명 칸(1·6·7)은 글자 그대로 두고 사실 칸과 도장만 다시 만든다
- 기준점 이후 고쳤다가 원래대로 돌아가 최종 diff에 없는 파일은 "되돌림"으로 보인다
- --head: 2절의 diff·되돌림 판정 끝점만 REF로 고정한다 (머지된 지난 작업을 다시 찍을 때). 도장 기준 커밋은 언제나 생성 때 HEAD
- 최신 L6가 통과면 3·8절에 OM 서비스 이름으로 등록 확인을 적는다. OM 주소는 적지 않는다 (OM_API_URL 환경변수로만 다룬다)
- docs/handover/ 반영과 PR 본문 출력은 scripts/handover/publish.py가 한다 (머지 후 사람이 실행, 03 §6.7 3·4단계)
"""
import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / "scripts" / "log"))
sys.path.insert(0, str(PROJECT / "scripts" / "ladder"))
import devlog  # noqa: E402
import harness_config  # noqa: E402

KST = timezone(timedelta(hours=9))
RUNG_NAMES = {"L0": "L0 계약·DAG 구조", "L1": "L1 dry-run", "L2": "L2 ai_dev 실행", "L3": "L3 레이어 게이트",
              "L4": "L4 정합성", "L5": "L5 멱등성"}
CHANGE_KO = {"A": "신규", "M": "변경", "D": "삭제", "R": "이름 변경", "C": "복사", "T": "변경"}
AI_SLOT = "<!-- AI가 채운다 -->"
STAMP_LABELS = ("contract_version", "생성 시각", "기준 커밋")  # 납품 산출물 도장과 같은 이름 (deliv_common이 가져다 쓴다)
STAMP_LINE = re.compile(r"^- (" + "|".join(STAMP_LABELS) + r"): (.+)$", re.M)
H1 = "## 1. 한 줄 요약"
H2 = "## 2. 바뀐 것  ← 코드"
H3 = "## 3. 데이터 흐름  ← 코드 (DAG 의존성)"
H4 = "## 4. 검증 결과  ← 코드 (검증 사다리)"
H_COST = "### 비용  ← 코드 (.dev/cost.jsonl)"
H5 = "## 5. 반려 이력  ← 코드 (.dev/rejections.jsonl)"
H6 = "## 6. 운영 방법"
H7 = "## 7. 주의점과 알려진 데이터 특성"
H8 = "## 8. 링크  ← 코드"
# 설정을 읽지 못할 때만 쓴다. 기록(Hook 차단·halt)은 남겨야 하므로 멈추지 않고 더 넓게 가린다
PROJECT_REF_FALLBACK = re.compile(r"\b[a-z][a-z0-9-]{3,}[:.](?=[a-z][a-z0-9_]*\.)")
# 메일 주소(서비스 계정 포함). 문장 속 프로젝트 ID 패턴은 설정에서 만든다(harness_config.project_ref_pattern)
EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")


class FactsError(Exception):
    pass


def scrub(text):
    """계정·프로젝트 ID를 가린다."""
    text = EMAIL.sub("<계정>", str(text))
    try:
        pattern = harness_config.project_ref_pattern()
    except harness_config.ConfigError:
        pattern = PROJECT_REF_FALLBACK
    return pattern.sub("<프로젝트>:", text)


def cell(text):
    return scrub(text).replace("|", "\\|").replace("\n", " ")


def git(root, *args):
    p = subprocess.run(["git", *args], cwd=root, capture_output=True)
    if p.returncode != 0:
        raise FactsError(f"git {' '.join(args)}: {p.stderr.decode('utf-8', 'replace').strip()[:300]}")
    return p.stdout.decode("utf-8", "replace")


def git_ok(root, *args):
    return subprocess.run(["git", *args], cwd=root, capture_output=True).returncode == 0


def default_base(root):
    for ref in ("origin/main", "main"):
        if git_ok(root, "rev-parse", "--verify", "-q", ref):
            return git(root, "merge-base", "HEAD", ref).strip()
    raise FactsError("기준점을 찾지 못함 (origin/main·main 없음). --base로 준다")


# ---------- 입력 ----------

def load_contract(root, mart):
    path = Path(root) / "docs" / "requirements" / f"{mart}.contract.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise FactsError(f"contract를 읽지 못함 ({path.name}): {e.__class__.__name__}") from None


def base_contract(root, base, mart):
    rel = f"docs/requirements/{mart}.contract.json"
    if not git_ok(root, "cat-file", "-e", f"{base}:{rel}"):
        return None
    return json.loads(git(root, "show", f"{base}:{rel}"))


def load_results(dev, mart, version):
    folder = Path(dev) / "ladder_results" / mart
    pattern = re.compile(r".+-v" + str(version) + r"-(\d+)\.json")
    out = []
    for f in sorted(folder.glob(f"*-v{version}-*.json")) if folder.is_dir() else []:
        if pattern.fullmatch(f.name):
            out.append(json.loads(f.read_text(encoding="utf-8")))
    return sorted(out, key=lambda r: (r["iteration"], r["ts"]))


def mine(dev, name, mart):
    return [r for r in devlog.read_lines(Path(dev) / f"{name}.jsonl") if r.get("mart") == mart]


# ---------- 절별 ----------

def load_tasks(contract):
    return [t for t in contract["dag"]["tasks"] if t["kind"] == "load"]


def compare(old, new, key):
    """{이름: 신규·변경·그대로}. old가 None이면 모두 신규. 없어진 것은 삭제."""
    old_map = {x[key]: x for x in (old or [])}
    new_map = {x[key]: x for x in new}
    out = {}
    for name, x in new_map.items():
        out[name] = "신규" if name not in old_map else ("변경" if old_map[name] != x else "그대로")
    for name in old_map:
        if name not in new_map:
            out[name] = "삭제"
    return out


def section_changes(root, base, contract, mart, end="HEAD"):
    """end: diff·되돌림 판정의 끝점. HEAD가 아니면 전체 해시다."""
    old = base_contract(root, base, mart)
    rows = ["| 구분 | 이름 | 변경 |", "|---|---|---|"]
    in_diff = set()
    tables = {t["name"]: t for t in contract["tables"]}
    old_tables = {t["name"]: t for t in (old or {}).get("tables", [])}
    for name, change in compare((old or {}).get("tables"), contract["tables"], "name").items():
        t = tables.get(name) or old_tables[name]
        rows.append(f"| 테이블 | {harness_config.datasets().get(t['layer'], t['layer'])}.{name} | {change} |")
    for name, change in compare((old or {}).get("dag", {}).get("tasks"), contract["dag"]["tasks"], "id").items():
        rows.append(f"| task | {name} | {change} |")
    for line in git(root, "diff", "--name-status", "-M", f"{base}...{end}").splitlines():
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        status, path = parts[0][0], parts[-1]
        in_diff.update(parts[1:])
        if path.startswith(".dev/"):
            continue  # 로그는 바뀐 것에 넣지 않는다 (검증 결과·반려 이력·비용에 따로)
        name = f"{parts[1]} → {path}" if status == "R" else path
        rows.append(f"| 파일 | {cell(name)} | {CHANGE_KO.get(status, status)} |")
    touched, renamed = set(), set()  # 이름만 바뀐 파일의 옛 이름은 되돌림이 아니다
    for line in git(root, "log", "--name-status", "-M", "--format=", f"{base}..{end}").splitlines():
        parts = line.split("\t")
        touched.update(parts[1:])
        if parts[0].startswith("R"):
            renamed.add(parts[1])
    for path in sorted(touched - in_diff - renamed):
        if not path.startswith(".dev/"):
            rows.append(f"| 파일 | {cell(path)} | 되돌림 |")
    span = "" if end == "HEAD" else f", 끝점 `{end[:8]}`"
    note = f"기준점 `{base[:8]}` 대비{span} (git diff {base[:8]}...{end if end == 'HEAD' else end[:8]}). contract: " + \
        ("기준점에 없음(전부 신규)" if old is None else f"기준점 v{old.get('version')} → 지금 v{contract['version']}")
    return "\n".join([note, "", *rows])


def om_status(posts):
    """최신 L6가 통과면 등록 확인 문구, 아니면 None. 주소는 L6 결과에 남기지 않으므로 서비스 이름만 쓴다."""
    if not posts or posts[-1].get("verdict") != "pass":
        return None
    p = posts[-1]
    service = next((g["metrics"].get("service") for g in p.get("rungs", []) if g.get("rung") == "L6"), None)
    return f"OM 서비스 {service}에서 등록 확인 (L6 통과, post-{p['_n']})" if service else None


def section_flow(contract, om=None):
    """DAG 의존성. 게이트를 건너뛰고 load task 사이 흐름과 게이트 위치를 적는다. om: om_status() 문구."""
    tasks = {t["id"]: t for t in contract["dag"]["tasks"]}

    def load_ups(tid, seen=None):
        seen = seen if seen is not None else set()
        out = []
        for up in tasks[tid]["upstream"]:
            if up in seen:
                continue
            seen.add(up)
            if up not in tasks:
                out.append(up)  # 다른 contract의 task (<마트>:<task>)
            elif tasks[up]["kind"] == "gate":
                out += load_ups(up, seen)
            else:
                out.append(up)
        return out

    lines = ["원천: " + ", ".join(contract.get("sources") or ["—"]), ""]
    for t in load_tasks(contract):
        ups = load_ups(t["id"])
        lines.append(f"- {', '.join(ups)} → {t['id']}" if ups else f"- (원천) → {t['id']}")
    gates = [t for t in contract["dag"]["tasks"] if t["kind"] == "gate"]
    if gates:
        lines += ["", "게이트: " + ", ".join(f"{g['id']} ({g['layer']} 층, 상류 {', '.join(g['upstream'])})"
                                          for g in gates)]
    lines += ["", f"OM 리니지: {om}" if om else "OM 리니지 링크는 결재 후 L6 통과 시 docs/handover/ 반영 때 추가한다."]
    return "\n".join(lines)


def iterations(results):
    by_n = {}
    for r in results:
        by_n.setdefault(r["iteration"], []).append(r)
    return by_n


def iteration_verdict(files):
    verdicts = {f["verdict"] for f in files}
    return "reject" if "reject" in verdicts else "halt" if "halt" in verdicts else "pass"


def rung_numbers(name, rungs):
    """그 단계의 수치(건수·바이트·검사 id만). evidence 같은 데이터 값은 쓰지 않는다."""
    if name == "L0":
        m = rungs[0]["metrics"]
        keys = [k for k in ("load_tasks", "gate_tasks", "tables", "checks", "traces") if k in m]
        return ", ".join(f"{k} {m[k]}" for k in keys) or "—"
    if name == "L1":
        values = [g["metrics"].get("bytes_processed") for g in rungs]
        total = sum(v for v in values if isinstance(v, int))
        lower = any(g["metrics"].get("bytes_accuracy") == "LOWER_BOUND" for g in rungs)
        return f"스캔량 합 {total:,} bytes" + (" (여러 문장 스크립트는 하한값)" if lower else "")
    if name == "L2":
        return "실행한 테이블 " + ", ".join(sorted({g["metrics"].get("table", "?") for g in rungs}))
    if name in ("L3", "L4"):
        checks = sorted({c for g in rungs for c in g["metrics"].get("checks", [])})
        return ("검사 " + ", ".join(checks) + " 위반 0행") if checks else "이 단계 검사 없음"
    if name == "L5":
        checks = sorted({c for g in rungs for c in g["metrics"].get("checks", [])})
        rows = sum(int(g["metrics"]["row_count"]) for g in rungs if str(g["metrics"].get("row_count", "")).isdigit())
        text = f"재실행 전후 행 수·체크섬 같음 (ds 파티션 행 수 합 {rows:,})"
        return text + (", 검사 " + ", ".join(checks) + " 위반 0행" if checks else "")
    return "—"


def l6_line(posts):
    """최신 L6(가장 큰 n) 1줄. 없으면 결재 후 (결정 67)."""
    if not posts:
        return "| L6 OM 등록 | 결재 후 | 운영 DAG·OM 에이전트 실행 뒤 판정 |"
    p = posts[-1]
    g = next((x for x in p.get("rungs", []) if x.get("rung") == "L6"), {})
    m = g.get("metrics", {})
    result = "통과" if p.get("verdict") == "pass" else f"반려 ({g.get('error_type')})"
    nums = (f"최신 post-{p['_n']} (L6 실행 {len(posts)}회), 테이블 없음 {len(m.get('tables_missing', []))}, "
            f"설명 누락 {len(m.get('description_missing', []))}, 엣지 누락 {len(m.get('edges_missing', []))}, "
            f"`.dev/ladder_results/{p.get('task')}/{p['_name']}`")
    return f"| L6 OM 등록 | {result} | {cell(nums)} |"


def section_results(results, contract, posts=()):
    if not results:
        return "사다리 결과 없음 (.dev/ladder_results)"
    by_n = iterations(results)
    summary = ["| 반복 | 판정 | task별 |", "|---|---|---|"]
    for n, files in by_n.items():
        tasks = ", ".join(f"{f['task']} {f['verdict']}" + (f"({f['halt_reason']})" if f.get("halt_reason") else "")
                          for f in files)
        summary.append(f"| {n} | {iteration_verdict(files)} | {cell(tasks)} |")
    passed = [n for n, files in by_n.items() if iteration_verdict(files) == "pass"]
    out = [f"contract v{contract['version']}의 사다리 반복 {len(by_n)}회", "", *summary, ""]
    if not passed:
        return "\n".join(out + ["통과한 반복 없음"])
    n = passed[-1]
    files = by_n[n]
    loads = [t["id"] for t in load_tasks(contract)]
    done = {f["task"] for f in files if f["verdict"] == "pass"}
    out += [f"마지막 통과 반복 {n} (task {len(done)}/{len(loads)} 통과, ds {files[0]['rungs'][-1].get('ds')})", "",
            "| 단계 | 결과 | 수치 |", "|---|---|---|"]
    for name in ("L0", "L1", "L2", "L3", "L4", "L5"):
        rungs = [g for f in files for g in f["rungs"] if g["rung"] == name]
        if not rungs:
            continue
        ok = all(g["status"] == "pass" for g in rungs)
        out.append(f"| {RUNG_NAMES[name]} | {'통과' if ok else '실패'} | {cell(rung_numbers(name, rungs))} |")
    out.append(l6_line(list(posts)))
    return "\n".join(out)


def section_cost(costs):
    if not costs:
        return "비용 기록 없음 (.dev/cost.jsonl)"
    rows = ["| 역할 | 호출 수 | 비용 합(USD, 정가 환산 추정) | 입력 토큰 | 출력 토큰 | bq 바이트 |", "|---|---|---|---|---|---|"]
    for role in sorted({c["role"] for c in costs}):
        cs = [c for c in costs if c["role"] == role]

        def total(key):
            values = [c.get(key) for c in cs if isinstance(c.get(key), (int, float))]
            return sum(values) if values else None
        usd = total("total_cost_usd")
        rows.append(f"| {role} | {len(cs)} | {'—' if usd is None else f'{usd:.4f}'} | {total('input_tokens') or 0:,} | "
                    f"{total('output_tokens') or 0:,} | {total('bq_bytes_processed') or 0:,} |")
    runs = sorted({c["run_id"] for c in costs})
    return "\n".join([f"실행 {len(runs)}회 ({', '.join(runs)})", "", *rows])


def section_rejections(results, rejections, interventions, posts=()):
    by_task_pass = {}
    for r in results:
        if r["verdict"] == "pass":
            by_task_pass.setdefault(r["task"], []).append(r["iteration"])
    rows = ["| ID | 반복 | task | 단계 | 유형 | 분류 | 내용 | evidence | 해결 |", "|---|---|---|---|---|---|---|---|---|"]
    for r in rejections:
        if r["iteration"] == "post":  # L6 반려: 그 뒤 통과한 첫 L6 순번 파일 (결정 67)
            n = devlog.post_fixed_in(r, [p for p in posts if p.get("task") == r["task"]])
            fixed = f"post-{n} 통과" if n else "—"
        else:
            later = [n for n in by_task_pass.get(r["task"], []) if n > r["iteration"]]
            fixed = f"반복 {min(later)} 통과" if later else "—"
        ev = r.get("evidence")
        ev_text = "없음" if ev is None else f"있음({len(ev) if isinstance(ev, list) else 1}행, 값은 옮기지 않음)"
        rows.append(f"| {r['id']} | {r['iteration']} | {r['task']} | {r['caught_by_rung']} | {r['error_type']} | "
                    f"{r['error_class']} | {cell(r['detail'])} | {ev_text} | {fixed} |")
    out = ["`.dev/rejections.jsonl` (해결 = 같은 task가 그 뒤 반복에서 통과한 첫 반복, ladder_result 기준)", ""]
    out += rows if rejections else ["반려 없음"]
    out += ["", "**개입 기록** (`.dev/interventions.jsonl`, 같은 마트, 해석 없이 그대로)", ""]
    if interventions:
        out += ["| ID | 시각 | 종류 | 단계 | 대상 | 분 | 메모 |", "|---|---|---|---|---|---|---|"]
        for i in interventions:
            out.append(f"| {i['id']} | {i['ts']} | {i['kind']} | {i.get('stage') or '—'} | {cell(i.get('target', ''))} | "
                       f"{i.get('minutes_spent', '—')} | {cell(i.get('note') or '—')} |")
    else:
        out.append("개입 기록 없음")
    return "\n".join(out)


def section_links(root, mart, om=None):
    root = Path(root)

    def exists(rel):
        return f"{rel}" if (root / rel).exists() else f"{rel} (없음)"
    out_dir = root / "out" / "deliverables"
    files = sorted(p.name for p in out_dir.glob(f"*{mart}*")) if out_dir.is_dir() else []
    return "\n".join([
        f"- OM 테이블: {om or '결재 후 L6 통과 시 docs/handover/ 반영 때 추가'}",
        "- 납품 산출물: " + (", ".join(f"out/deliverables/{f}" for f in files) if files else "아직 없음 (out/deliverables/)"),
        f"- 요구서: {exists(f'docs/requirements/{mart}.md')}",
        f"- contract: {exists(f'docs/requirements/{mart}.contract.json')}",
        f"- 인터뷰 기록: {exists(f'docs/requirements/{mart}_interview.md')}",
    ])


def render(root, dev, mart, branch, base, day, end="HEAD"):
    contract = load_contract(root, mart)
    results = load_results(dev, mart, contract["version"])
    rejections = [r for r in mine(dev, "rejections", mart) if r.get("contract_version") == contract["version"]]
    posts = devlog.post_results(mart, mart, contract["version"], dev)  # L6 순번 파일, 최신 = 마지막 (결정 67)
    stamp = (contract["version"], datetime.now(KST).isoformat(timespec="seconds"), git(root, "rev-parse", "HEAD").strip())
    om = om_status(posts)
    text = "\n".join([
        f"# 인수인계 — {mart} ({branch}, {day})",
        "",
        "> 사실 칸(2·3·4·5·8)은 `scripts/handover/make_facts.py` 출력이다. 고치거나 추측해서 채우지 않는다.",
        "> 설명 칸(1·6·7)만 builder가 쓴다 (`.claude/rules/handover.md`).",
        "",
        *(f"- {label}: {value}" for label, value in zip(STAMP_LABELS, stamp)),
        "",
        H1, AI_SLOT, "",
        H2, section_changes(root, base, contract, mart, end), "",
        H3, section_flow(contract, om), "",
        H4, section_results(results, contract, posts), "",
        H_COST, section_cost(mine(dev, "cost", mart)), "",
        H5, section_rejections(results, rejections, mine(dev, "interventions", mart), posts), "",
        H6, AI_SLOT, "",
        H7, AI_SLOT, "",
        H8, section_links(root, mart, om), "",
    ])
    return scrub(text)


# ---------- 도장·최신성·다시 찍기 ----------

def read_draft(path):
    """줄바꿈까지 글자 그대로 읽는다."""
    return Path(path).read_bytes().decode("utf-8")


def read_stamp(text):
    """초안 머리(1절 앞)의 도장 {이름: 값}. 본문의 같은 모양 줄은 보지 않는다."""
    return dict(STAMP_LINE.findall(text.split(f"\n{H1}\n", 1)[0]))


def split_draft(text):
    """초안을 8조각으로 나눈다. "".join하면 원문이다.
    [제목 줄, 머리(1절 제목까지), 1절, 사실 칸(2~5절, 6절 제목까지), 6절, 7절 제목, 7절, 8절]"""
    starts = []
    for head in (H1, H2, H6, H7, H8):
        at = text.find(f"\n{head}\n")
        if at < 0:
            raise FactsError(f"초안에 제목이 없음: {head}")
        starts.append(at + 1)
    if starts != sorted(starts):
        raise FactsError("초안의 절 순서가 다름")
    h1, h2, h6, h7, h8 = starts
    cuts = [0, text.index("\n") + 1, h1 + len(H1) + 1, h2, h6 + len(H6) + 1, h7, h7 + len(H7) + 1, h8, len(text)]
    return [text[a:b] for a, b in zip(cuts, cuts[1:])]


def empty_slots(text):
    """설명 칸(1·6·7) 중 빈 자리 표시 그대로인 절 번호."""
    parts = split_draft(text)
    return [n for n, part in zip((1, 6, 7), parts[2::2]) if part.strip() == AI_SLOT]


def restamp(old, fresh):
    """old의 제목 줄과 설명 칸을 글자 그대로 두고, 머리(도장)와 사실 칸은 fresh로 바꾼다."""
    o, f = split_draft(old), split_draft(fresh)
    return "".join([o[0], f[1], o[2], f[3], o[4], f[5], o[6], f[7]])


def mart_paths(contract, mart):
    """이 마트 관련 파일. dags/harness_daily.py처럼 여러 마트가 같이 쓰는 파일은 넣지 않는다
    (다른 마트 작업 때문에 낡은 것으로 보지 않게)."""
    sql = [f"dags/sql/{'dq' if t['kind'] == 'gate' else t['layer']}/{t['id']}.sql" for t in contract["dag"]["tasks"]]
    return [f"docs/requirements/{mart}.contract.json", f"docs/requirements/{mart}.md",
            f"docs/requirements/{mart}_checks", *sql, f".dev/ladder_results/{mart}"]


def freshness_problems(root, mart, text):
    """초안이 낡은 이유 목록. 빈 목록이면 최신.
    납품 산출물의 check(기준 커밋 = HEAD)와 기준이 다른 이유: 초안은 커밋되는 파일이라 커밋하는 순간 HEAD가 바뀐다.
    그래서 도장 기준 커밋 이후 이 마트 관련 파일이 바뀌었는지를 본다."""
    stamp = read_stamp(text)
    if set(stamp) != set(STAMP_LABELS):
        return ["도장 없음 (4-5 이전 초안)"]
    contract = load_contract(root, mart)
    problems = []
    if stamp["contract_version"] != str(contract["version"]):
        problems.append(f"contract_version 도장 {stamp['contract_version']} ≠ 지금 {contract['version']}")
    commit = stamp["기준 커밋"]
    if not git_ok(root, "cat-file", "-e", f"{commit}^{{commit}}"):
        return problems + [f"기준 커밋 {commit[:8]}을 찾지 못함"]
    changed = git(root, "log", "--format=%h", f"{commit}..HEAD", "--", *mart_paths(contract, mart)).split()
    if changed:
        problems.append(f"기준 커밋 {commit[:8]} 이후 마트 관련 파일이 커밋 {len(changed)}개에서 바뀜 (최근 {changed[0]})")
    return problems


def check_draft(root, mart, path):
    """--check. 최신이면 0, 아니면 2(halt input_invalid)."""
    path = Path(path)
    try:
        problems = freshness_problems(root, mart, read_draft(path))
    except OSError as e:
        problems = [f"초안을 읽지 못함 ({e.__class__.__name__})"]
    except (FactsError, KeyError) as e:
        problems = [f"{e.__class__.__name__}: {e}"]
    if problems:
        print(f"halt input_invalid: 인수인계 초안 {path.name}이 최신이 아님 — " + "; ".join(problems), file=sys.stderr)
        return 2
    print(f"최신: {path.name}")
    return 0


def parse_args(argv):
    p = argparse.ArgumentParser(description="인수인계 초안 사실 부분 (03 §6.7)")
    p.add_argument("--mart", required=True)
    p.add_argument("--branch", help="기본: 지금 브랜치")
    p.add_argument("--base", help="git diff 기준점 (기본: HEAD와 origin/main의 merge-base)")
    p.add_argument("--root", default=str(PROJECT))
    p.add_argument("--dev-dir", help="기본: <root>/.dev")
    p.add_argument("--out", help="기본: <dev-dir>/handover/<브랜치>.md")
    p.add_argument("--date", help="기본: 오늘(+09:00)")
    p.add_argument("--head", default="HEAD", help="2절 diff·되돌림 판정의 끝점 (기본: HEAD). 도장 기준 커밋과는 무관")
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="초안 도장 최신성 검사 (최신 0, 아니면 2)")
    mode.add_argument("--restamp", action="store_true", help="설명 칸은 두고 사실 칸과 도장만 다시 만든다")
    return p.parse_args(argv)


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    args = parse_args(argv)
    root = Path(args.root)
    dev = Path(args.dev_dir) if args.dev_dir else root / ".dev"
    try:
        branch = args.branch or git(root, "rev-parse", "--abbrev-ref", "HEAD").strip()
        out = Path(args.out) if args.out else dev / "handover" / f"{branch}.md"
        if args.check:
            return check_draft(root, args.mart, out)
        base = args.base or default_base(root)
        base = git(root, "rev-parse", base).strip()
        day = args.date or datetime.now(KST).date().isoformat()
        end = git(root, "rev-parse", f"{args.head}^{{commit}}").strip()
        end = "HEAD" if end == git(root, "rev-parse", "HEAD").strip() else end
        text = render(root, dev, args.mart, branch, base, day, end)
        if args.restamp:
            if not out.exists():
                raise FactsError(f"--restamp할 초안이 없음: {out}")
            text = restamp(read_draft(out), text)
    except (FactsError, devlog.DevlogError, KeyError, ValueError) as e:
        print(f"인수인계 사실 부분을 만들지 못함: {e.__class__.__name__}: {e}", file=sys.stderr)
        return 2
    if out.exists() and not args.restamp:
        print(f"이미 있음: {out}. 덮어쓰지 않는다 (설명 칸을 잃지 않게). 지우거나 --out을 준다", file=sys.stderr)
        return 2
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8", newline="\n")
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
