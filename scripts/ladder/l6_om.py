"""L6 OM 등록 확인 (03 §5.3, 결정 22·47·67). 결재 후, 운영 DAG 실행과 OM 에이전트 실행 뒤 사람이 실행한다.

  python scripts/ladder/l6_om.py --mart <마트> [--dry-plan] [--root R] [--dev-dir D]

- 기대값은 contract에서만 계산한다 (결정 47)
  · 테이블 = contract tables[] → FQN `<OM 서비스>.<프로젝트>.<운영 데이터셋>.<테이블>`
    (OM 서비스·운영 데이터셋은 dags/harness_config.json와 같은 매핑)
  · 리니지 엣지 = dag.tasks 의존 관계에서 게이트를 건너뛴 load task 사이의 테이블 연결
  · sources → raw 엣지는 판정하지 않고 결과에 "보고만" 남긴다 (결정 67)
- 프로젝트 ID는 다른 사다리 단계와 같이 ai-builder gcloud 설정에서 읽고(결정 59 ②, common.Bq.check_auth),
  출력·결과 파일에서는 scripts/handover/make_facts.py의 scrub()으로 <프로젝트>로 가린다
- OM 주소·토큰은 환경변수 OM_API_URL(예: http://<host>:8585/api)·OM_TOKEN에서 이름으로만 읽는다.
  값은 출력·파일·예외 메시지에 넣지 않는다. --dry-plan은 OM을 부르지 않으므로 둘 다 없어도 된다
- 판정 (읽기 전용 GET만, OM 2.0.x API):
  ① 테이블 존재: GET {OM_API_URL}/v1/tables/name/{fqn}?fields=columns, 404면 없음 → table_missing
     (https://docs.open-metadata.org/v2.0.x/api-reference/data-assets/tables/retrieve.md)
  ② contract 컬럼마다 OM 컬럼 description이 비어 있지 않음 → 아니면 description_missing
  ③ GET {OM_API_URL}/v1/lineage/table/name/{fqn}?upstreamDepth=1&downstreamDepth=0 의 upstreamEdges
     (fromEntity·toEntity = entity·nodes의 id) 중 contract 테이블 사이 엣지가 기대값을 모두 포함 → 아니면 lineage_missing.
     기대에 없는 엣지(자기 고리 포함)와 원천 엣지는 보고만
     (https://docs.open-metadata.org/v2.0.x/api-reference/lineage/get.md)
  error_type은 ①→②→③ 순서로 처음 걸린 것 하나. 나머지 목록도 metrics에 남긴다(메타데이터만, 데이터 값 없음)
- 결과: .dev/ladder_results/<마트>/<마트>-v<contract 버전>-post-<n>.json (rung L6 1개, iteration "post").
  n은 같은 마트·버전의 가장 큰 n + 1(devlog.write_ladder_result). 재확인은 새 순번 파일로 추가하고 이전 파일은
  지우거나 덮어쓰지 않는다. 최신 L6 = 가장 큰 n (devlog.latest_post, 결정 67)
- 반려(종료 1)면 .dev/rejections.jsonl에 1줄(task = 마트, iteration "post", caught_by_rung L6). detail은 빠진
  테이블·컬럼·엣지 이름, evidence는 같은 마트·task·error_type의 첫 반려면 null, 2번째부터 그 error_type의 빠진 항목
  이름 목록(데이터 값·프로젝트 ID 없음). 통과와 멈춤은 쓰지 않는다
- 쓰는 순서: ① 반려 줄을 devlog 검사로 미리 확인 ② 결과 파일 ③ 반려 줄. ①·②가 실패하면 아무것도 남기지 않고
  종료 2. ③이 실패하면 이번 실행이 만든 결과 파일(이번 순번)만 지우고 종료 2(반려 줄 없는 반려 결과가 최신 L6로
  읽히는 것을 막는다). 지우기도 실패하면 stderr에 파일 이름을 남기고 사람이 지운다
- 종료 코드: 0 통과, 1 반려, 2 멈춤(contract 읽기 실패, 환경변수 없음, gcloud 설정 문제, OM 연결·인증 실패,
  기록 실패). 인프라 오류는 결과 파일 없이 stderr만 남긴다(다시 실행 가능, 결정 67)
"""
import argparse
import json
import os
import socket
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1] / "scripts" / "handover"))
sys.path.insert(0, str(HERE.parents[1] / "scripts" / "metrics"))
import common  # noqa: E402
import devlog  # noqa: E402  (common이 scripts/log를 sys.path에 넣는다)
import rule_candidates  # noqa: E402
from make_facts import scrub  # noqa: E402

ENV_URL, ENV_TOKEN = "OM_API_URL", "OM_TOKEN"
TIMEOUT = 30


def update_rule_candidates(root, dev):
    """반려 뒤 규칙 후보를 갱신한다 (03 §6.3). 측정 부가 작업이라 실패해도 L6 판정과 종료 코드를 바꾸지 않는다."""
    try:
        for rule_id in rule_candidates.update(root, dev):
            print(f"규칙 후보 {rule_id} 생성 (.dev/rule_candidates.md, 사람 결재 대기)")
    except Exception as e:  # noqa: BLE001  어떤 실패든 판정을 바꾸지 않는다
        print(f"규칙 후보 갱신 실패 ({e.__class__.__name__}: {scrub(str(e))[:200]}). L6 판정은 그대로", file=sys.stderr)


class OMUnavailable(common.InfraError):
    """OM 연결·인증 실패. 반려로 세지 않고 결과 파일도 남기지 않는다 (결정 67)."""


# ---------- 기대값 (contract만) ----------

def plan(contract, project, load_other=None):
    """{"tables": [(테이블, FQN)], "edges": [(상류 테이블, 하류 테이블)], "sources": [...], "roots": [...],
    "borrowed": [(빌린 테이블, FQN)]}. load_other(마트)는 빌려 쓴 상류(<마트>:<task>)의 contract를 돌려준다.
    빌린 테이블은 엣지 기대값에만 쓴다. 그 테이블의 등록·설명은 원래 마트의 L6가 본다."""
    tasks = {t["id"]: t for t in contract["dag"]["tasks"]}
    table_of = {t["task"]: t for t in contract["tables"]}
    config = common.config()
    service = config["om"]["service"]

    def fqn_of(t):
        dataset = config["datasets"].get(t["layer"])
        if dataset is None:
            raise common.LadderError(f"레이어 {t['layer']!r}의 운영 데이터셋을 모름 (테이블 {t['name']})")
        return f"{service}.{project}.{dataset}.{t['name']}"

    tables = [(t["name"], fqn_of(t)) for t in contract["tables"]]

    def resolve(c, up):
        """상류 표기를 (그 task의 contract, task id)로. 이 contract에 없는 일반 이름은 None."""
        if ":" not in up:
            return (c, up) if any(t["id"] == up for t in c["dag"]["tasks"]) else None
        mart, task_id = up.split(":", 1)
        if load_other is None:
            raise common.LadderError(f"빌려 쓴 상류 {up}의 contract를 읽을 수 없음")
        owner = load_other(mart)
        if not any(t["id"] == task_id for t in owner["dag"]["tasks"]):
            raise common.LadderError(f"빌려 쓴 상류 {up}가 {mart} contract에 없음")
        return owner, task_id

    def nearest_loads(c, task_id, seen=()):
        """[(contract, load task id)]. 게이트는 테이블을 만들지 않으므로 그 적재 상류를 따라간다."""
        out = []
        task = next(t for t in c["dag"]["tasks"] if t["id"] == task_id)
        for up in task["upstream"]:
            found = resolve(c, up)
            if found is None or (found[0]["mart"], found[1]) in seen:
                continue
            owner, up_id = found
            if next(t for t in owner["dag"]["tasks"] if t["id"] == up_id)["kind"] == "load":
                out.append(found)
            else:
                out += nearest_loads(owner, up_id, (*seen, (c["mart"], task_id)))
        return out

    edges, roots, borrowed = [], [], {}
    for tid, task in tasks.items():
        if task["kind"] != "load" or tid not in table_of:
            continue
        ups = []
        for owner, up_id in nearest_loads(contract, tid):
            t = next((x for x in owner["tables"] if x["task"] == up_id), None)
            if t is None:
                continue
            ups.append(t["name"])
            if owner is not contract:
                borrowed[t["name"]] = fqn_of(t)
        ups = list(dict.fromkeys(ups))
        if not ups:
            roots.append(table_of[tid]["name"])
        edges += [(u, table_of[tid]["name"]) for u in ups]
    return {"tables": tables, "edges": edges, "sources": list(contract.get("sources", [])), "roots": roots,
            "borrowed": list(borrowed.items())}


def print_plan(p, mart, version):
    print(f"L6 기대값 (contract {mart} v{version}, 결정 47). OM을 부르지 않음")
    print(f"테이블 {len(p['tables'])}개:")
    for _, fqn in p["tables"]:
        print(f"  {scrub(fqn)}")
    print(f"리니지 엣지 {len(p['edges'])}개 (contract 테이블 사이, 판정):")
    for a, b in p["edges"]:
        print(f"  {a} -> {b}")
    if p["borrowed"]:
        print(f"빌린 테이블 {len(p['borrowed'])}개 (엣지 기대값에만 씀): {', '.join(n for n, _ in p['borrowed'])}")
    print("원천 엣지 (보고만, 판정 안 함):")
    print(f"  원천 {', '.join(p['sources']) or '없음'} -> {', '.join(p['roots']) or '없음'}")


# ---------- OM 조회 ----------

def urllib_get(url, token):
    """(HTTP 상태, JSON 또는 None). 연결 실패는 OMUnavailable. 토큰은 헤더에만 넣는다."""
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, None
    except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError) as e:
        raise OMUnavailable(f"OM 연결 실패 ({e.__class__.__name__})") from None
    except json.JSONDecodeError:
        raise OMUnavailable("OM 응답이 JSON이 아님") from None


class OM:
    def __init__(self, base, token, get=urllib_get):
        self.base, self.token, self.get = base.rstrip("/"), token, get

    def call(self, path, what):
        status, body = self.get(f"{self.base}{path}", self.token)
        if status in (401, 403):
            raise OMUnavailable(f"OM 인증 실패 (HTTP {status}, {what}). {ENV_TOKEN} 확인")
        if status == 404:
            return None
        if status != 200 or not isinstance(body, dict):
            raise OMUnavailable(f"OM 응답 오류 (HTTP {status}, {what})")
        return body

    def table(self, fqn):
        q = urllib.parse.quote(fqn, safe="")
        return self.call(f"/v1/tables/name/{q}?fields=columns", f"테이블 {scrub(fqn)}")

    def upstream_edges(self, fqn):
        """[(상류 FQN, 하류 FQN)]. id는 entity·nodes로 FQN에 맞춘다."""
        q = urllib.parse.quote(fqn, safe="")
        body = self.call(f"/v1/lineage/table/name/{q}?upstreamDepth=1&downstreamDepth=0", f"리니지 {scrub(fqn)}")
        if body is None:
            raise OMUnavailable(f"OM 리니지 응답 없음 (HTTP 404, {scrub(fqn)})")
        ids = {}
        for e in [body.get("entity") or {}, *(body.get("nodes") or [])]:
            if e.get("id"):
                ids[e["id"]] = e.get("fullyQualifiedName") or e.get("name") or e["id"]

        def ref(x):
            x = x.get("id") if isinstance(x, dict) else x
            return ids.get(x, str(x))
        return [(ref(e.get("fromEntity")), ref(e.get("toEntity"))) for e in body.get("upstreamEdges") or []]


# ---------- 판정 ----------

def judge(contract, p, om):
    """L6 rung (common.rung 형식). metrics에는 메타데이터만, FQN은 가린다."""
    by_fqn = {fqn.lower(): name for name, fqn in (*p["tables"], *p["borrowed"])}
    roots = set(p["roots"])
    columns = {t["name"]: [c["name"] for c in t.get("columns", [])] for t in contract["tables"]}
    missing_tables, missing_desc, observed, unexpected, source_edges = [], [], set(), [], []
    checked = 0
    present = []
    for name, fqn in p["tables"]:
        body = om.table(fqn)
        if body is None:
            missing_tables.append(scrub(fqn))
            continue
        present.append((name, fqn))
        om_cols = {c.get("name", "").lower(): c for c in body.get("columns") or []}
        for col in columns[name]:
            checked += 1
            c = om_cols.get(col.lower())
            if c is None:
                missing_desc.append(f"{name}.{col} (OM에 컬럼 없음)")
            elif not str(c.get("description") or "").strip():
                missing_desc.append(f"{name}.{col}")
    for name, fqn in present:
        for a, b in om.upstream_edges(fqn):
            an, bn = by_fqn.get(a.lower()), by_fqn.get(b.lower())
            if an and bn and an != bn:
                observed.add((an, bn))
            elif bn in roots and an is None:
                source_edges.append(f"{scrub(a)} -> {bn}")
            else:
                unexpected.append(f"{an or scrub(a)} -> {bn or scrub(b)}")
    expected = set(p["edges"])
    edges_missing = sorted(f"{a} -> {b}" for a, b in expected - observed)
    unexpected = sorted(set(unexpected) | {f"{a} -> {b}" for a, b in observed - expected})
    metrics = {
        "service": common.config()["om"]["service"], "tables_expected": len(p["tables"]), "tables_missing": missing_tables,
        "columns_checked": checked, "description_missing": missing_desc,
        "edges_expected": [f"{a} -> {b}" for a, b in p["edges"]], "edges_missing": edges_missing,
        "edges_unexpected": unexpected, "source_edges": sorted(set(source_edges)),
        "report_only": ["edges_unexpected", "source_edges"],
    }
    error_type = ("table_missing" if missing_tables else "description_missing" if missing_desc
                  else "lineage_missing" if edges_missing else None)
    return common.rung("L6", None, metrics, error_type)


FAILED_ITEMS = {"table_missing": "tables_missing", "description_missing": "description_missing",
                "lineage_missing": "edges_missing"}
DETAIL_NAMES = 20  # detail에 적는 이름 수 상한 (나머지는 "외 N개")


def names(items):
    shown = ", ".join(items[:DETAIL_NAMES])
    return shown + (f" 외 {len(items) - DETAIL_NAMES}개" if len(items) > DETAIL_NAMES else "")


def rejection_record(mart, version, g, dev):
    """rejections.jsonl 1줄 (03 §6.2). evidence는 같은 마트·task·error_type의 첫 반려면 null, 2번째부터 빠진 항목 이름.
    devlog의 검사(형식·비밀값·evidence 규칙)를 여기서 미리 돌려, 결과 파일을 쓴 뒤 반려 줄이 거절되는 일을 줄인다."""
    m, et = g["metrics"], g["error_type"]
    parts = [f"{label} {len(m[key])}개: {names(m[key])}" for label, key in
             (("없는 테이블", "tables_missing"), ("설명 빠진 컬럼", "description_missing"),
              ("빠진 엣지", "edges_missing")) if m[key]]
    previous = devlog.read_lines(Path(dev) / "rejections.jsonl")
    seen = any(p.get("mart") == mart and p.get("task") == mart and p.get("error_type") == et for p in previous)
    r = {"mart": mart, "task": mart, "iteration": "post", "contract_version": version, "caught_by_rung": "L6",
         "error_type": et, "error_class": g["error_class"], "detail": f"L6 {et}: " + "; ".join(parts),
         "fixed_in_iteration": None, "rule_promoted": None, "evidence": list(m[FAILED_ITEMS[et]]) if seen else None}
    devlog.reject_secrets(r)
    devlog.validate_rejection(dict(r), previous)
    return r


def parse_args(argv):
    p = argparse.ArgumentParser(description="L6 OM 등록 확인 (결재 후, 결정 22·47·67)")
    p.add_argument("--mart", required=True)
    p.add_argument("--dry-plan", action="store_true", help="OM을 부르지 않고 기대 테이블 FQN·엣지만 출력")
    p.add_argument("--root", default=str(common.PROJECT))
    p.add_argument("--dev-dir", help="기본: <root>/.dev")
    return p.parse_args(argv)


def main(argv=None, *, bq=None, get=urllib_get, environ=None):
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    args = parse_args(argv)
    env = os.environ if environ is None else environ
    try:
        contract = common.load_contract(common.Paths(args.root, args.mart))
        version = contract["version"]
        project = (bq or common.Bq()).check_auth()
        p = plan(contract, project, lambda mart: common.load_contract(common.Paths(args.root, mart)))
        if args.dry_plan:
            print_plan(p, args.mart, version)
            return 0
        missing_env = [n for n in (ENV_URL, ENV_TOKEN) if not env.get(n)]
        if missing_env:
            raise common.InfraError(f"환경변수 {', '.join(missing_env)} 없음 (값은 사람이 설정한다)")
        dev = Path(args.dev_dir) if args.dev_dir else Path(args.root) / ".dev"
        g = judge(contract, p, OM(env[ENV_URL], env[ENV_TOKEN], get))
    except (common.LadderError, common.HaltError, KeyError) as e:
        kind = "멈춤 infra_error" if isinstance(e, common.InfraError) else "멈춤"
        print(f"L6 {kind}: {scrub(str(e))} (결과 파일 없음)", file=sys.stderr)
        return 2
    verdict = "reject" if g["status"] == "fail" else "pass"
    record = {"task": args.mart, "iteration": "post", "contract_version": version, "request_kind": "new_build",
              "modules": contract.get("modules", {"expert": {"on": [], "version": None}}), "bytes_total": None,
              "rungs": [g], "verdict": verdict, "halt_reason": None}
    rejection = None
    try:
        if verdict == "reject":  # 결과 파일을 쓰기 전에 반려 줄을 먼저 검사한다 (아래 순서 설명)
            rejection = rejection_record(args.mart, version, g, dev)
        path = devlog.write_ladder_result(args.mart, record, dev)
    except devlog.DevlogError as e:
        print(f"L6 멈춤: 결과를 기록하지 못함: {scrub(str(e))} (결과 파일·반려 줄 없음)", file=sys.stderr)
        return 2
    if rejection is not None:
        try:
            entry = devlog.append("rejections", rejection, dev)
        except (devlog.DevlogError, OSError) as e:
            # 반려 줄만 빠진 결과 파일이 남으면 덮어쓰기 금지 때문에 다시 실행할 수 없다. 이번 실행이 만든 파일을 지운다
            try:
                path.unlink()
                undo = "이번 결과 파일을 지웠으므로 다시 실행할 수 있음"
            except OSError:
                undo = f"결과 파일 {path.name}을 지우지 못함. 사람이 지운 뒤 다시 실행한다"
            print(f"L6 멈춤: 반려 줄을 기록하지 못함: {scrub(str(e))}. {undo}", file=sys.stderr)
            return 2
        print(f"반려 {entry['id']} 기록 (.dev/rejections.jsonl)")
        update_rule_candidates(args.root, dev)
    m = g["metrics"]
    print(f"L6 {verdict}: 테이블 {m['tables_expected'] - len(m['tables_missing'])}/{m['tables_expected']}, "
          f"설명 누락 {len(m['description_missing'])}, 엣지 누락 {len(m['edges_missing'])}"
          f" (기대 밖 {len(m['edges_unexpected'])}, 원천 {len(m['source_edges'])}는 보고만) → {path}")
    if g["error_type"]:
        print(f"error_type {g['error_type']}", file=sys.stderr)
    return 1 if verdict == "reject" else 0


if __name__ == "__main__":
    common.apply_kit_local()  # 새 창: .kit_local.json의 CLOUDSDK_CONFIG (있으면 덮어쓰지 않음)
    sys.exit(main())
