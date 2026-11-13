"""결재 1·2 기록 자동화 (git 머지 기록). 사람이 PR을 머지하면 루프·대시보드가 이 모듈로 interventions에 남긴다.

  python scripts/log/auto_approval.py [--mart <마트>] [--root R] [--dev-dir D]   (마트를 안 주면 모든 마트)

- 이력: origin/main(없으면 main)의 first-parent 이력. 커밋마다 첫 부모와의 차이로 바뀐 파일을 본다
- 결재 1: docs/requirements/<마트>.contract.json을 바꾼 커밋
- 결재 2: 결재 1 커밋 뒤(다음 결재 1 전)에 처음으로 그 마트 task SQL 파일(dags/sql/<층>/<task>.sql, 게이트는 dq/)이나
  그 마트의 인수인계 초안(.dev/handover/의 첫 줄에 마트 이름이 있는 파일)을 바꾼 커밋. 결재 1 하나에 결재 2 하나다.
  뒤에 인수인계 초안만 고친 PR 같은 것은 결재로 세지 않는다
- 머지 커밋이 아니면(스쿼시·직접 커밋) 기록하지 않고 출력으로 알린다
- 분: 머지 커밋 시각 - PR 브랜치 첫 커밋 시각(머지^1..머지^2 범위의 가장 이른 커밋). 커미터 시각, 올림, 최소 1
- 기록: devlog.append("interventions")를 그대로 쓴다(검사 규칙 같음). kind approval, stage approval_1·approval_2,
  target "PR 머지 <sha 7자리>", note AUTO_NOTE. approval_1·2에는 approver 칸이 없다(devlog STAGE_FIELDS)
- 중복 방지: 같은 마트·stage 기록의 target에 그 sha 7자리가 있으면 건너뛴다. 같은 마트·stage에 사람이 남긴 기록
  (note가 AUTO_NOTE가 아닌 것)이 있으면 그중 가장 늦은 ts 이전(같은 시각 포함)의 머지는 건너뛴다(이미 사람이 기록한 결재)
- git이 없거나 저장소가 아니면 아무것도 하지 않는다. 읽기 전용 원칙의 dashboard_data.py에서는 부르지 않는다(결정 71)
- 쓰는 곳은 루프(작업 브랜치에서 쓰고 바로 커밋)와 이 명령뿐이다. 대시보드는 preview_all로 아직 기록되지 않은 결재를
  화면에만 보이고 파일은 쓰지 않는다(결정 80 ⑤). 그래서 main 작업 트리가 대시보드 때문에 더러워지지 않는다
"""
import argparse
import json
import math
import subprocess
import sys
from datetime import datetime
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / "scripts" / "log"))
sys.path.insert(0, str(PROJECT / "scripts" / "setup"))
import devlog  # noqa: E402
import kit_local  # noqa: E402

AUTO_NOTE = "git 머지 기록에서 자동"
STAGES = ("approval_1", "approval_2")
HANDOVER = ".dev/handover/"
COMMIT_MARK = "@@commit "


def git(root, *args):
    """(성공 여부, 표준 출력). git이 없어도 예외를 내지 않는다."""
    try:
        p = subprocess.run(["git", "-C", str(root), *args], capture_output=True)
    except OSError:
        return False, ""
    return p.returncode == 0, p.stdout.decode("utf-8", "replace")


def main_ref(root):
    for ref in ("origin/main", "main"):
        if git(root, "rev-parse", "--verify", "-q", f"{ref}^{{commit}}")[0]:
            return ref
    return None


def history(root, ref):
    """first-parent 이력, 오래된 것부터. 각 항목 {sha, parents, time, files}."""
    ok, out = git(root, "log", ref, "--first-parent", "-m", "--reverse", "--name-only",
                  f"--format={COMMIT_MARK}%H %ct %P")
    commits = []
    for line in out.splitlines() if ok else []:
        if line.startswith(COMMIT_MARK):
            sha, ts, *parents = line[len(COMMIT_MARK):].split()
            commits.append({"sha": sha, "time": int(ts), "parents": parents, "files": set()})
        elif line.strip() and commits:
            commits[-1]["files"].add(line.strip())
    return commits


def task_sql_paths(root, mart):
    try:
        contract = json.loads((Path(root) / "docs" / "requirements" / f"{mart}.contract.json").read_text(encoding="utf-8"))
        tasks = contract["dag"]["tasks"]
    except (OSError, ValueError, KeyError, TypeError):
        return set()
    return {f"dags/sql/{'dq' if t.get('kind') == 'gate' else t.get('layer')}/{t.get('id')}.sql" for t in tasks}


def handover_of(root, sha, path, mart):
    """그 커밋의 인수인계 초안 첫 줄(제목)에 마트 이름이 있는가."""
    ok, out = git(root, "show", f"{sha}:{path}")
    first = next((line for line in out.splitlines() if line.strip()), "") if ok else ""
    return mart in first.replace("(", " ").replace(")", " ").split()


def approvals(root, mart, commits):
    """(stage, 커밋) 목록. 결재 1은 contract를 바꾼 커밋, 결재 2는 결재 1마다 그 뒤 첫 task SQL·인수인계 커밋."""
    contract = f"docs/requirements/{mart}.contract.json"
    sql = task_sql_paths(root, mart)
    found, waiting = [], False
    for c in commits:
        if contract in c["files"]:
            found.append(("approval_1", c))
            waiting = True
            continue
        if not waiting:
            continue
        build = c["files"] & sql or any(f.startswith(HANDOVER) and handover_of(root, c["sha"], f, mart)
                                        for f in c["files"])
        if build:
            found.append(("approval_2", c))
            waiting = False
    return found


def branch_minutes(root, merge):
    """머지 시각 - 브랜치 첫 커밋 시각(분, 올림, 최소 1)."""
    first_parent, second = merge["parents"][0], merge["parents"][1]
    ok, out = git(root, "log", "--format=%ct", f"{first_parent}..{second}")
    times = [int(t) for t in out.split()] if ok else []
    if not times:
        return 1
    return max(1, math.ceil((merge["time"] - min(times)) / 60))


def human_cutoff(records, mart, stage):
    times = [datetime.fromisoformat(r["ts"]).timestamp() for r in records
             if r.get("kind") == "approval" and r.get("mart") == mart and r.get("stage") == stage
             and r.get("note") != AUTO_NOTE and isinstance(r.get("ts"), str)]
    return max(times) if times else None


def pending(root, mart, records, say=print):
    """아직 기록되지 않은 결재 1·2 머지 [(기록할 칸, 머지 커밋)]. 아무것도 쓰지 않는다."""
    root = Path(root)
    ref = main_ref(root)
    if ref is None:
        return []
    found, seen = [], list(records)
    for stage, c in approvals(root, mart, history(root, ref)):
        short = c["sha"][:7]
        same = [r for r in seen if r.get("kind") == "approval" and r.get("mart") == mart and r.get("stage") == stage]
        if any(short in str(r.get("target", "")) for r in same):
            continue
        cutoff = human_cutoff(seen, mart, stage)
        if cutoff is not None and c["time"] <= cutoff:
            continue
        if len(c["parents"]) < 2:
            say(f"결재 기록 건너뜀: {mart} {stage} {short}는 머지 커밋이 아니다(스쿼시 등). "
                "필요하면 devlog.py intervention으로 손으로 남긴다")
            continue
        fields = {"mart": mart, "kind": "approval", "stage": stage, "target": f"PR 머지 {short}",
                  "minutes_spent": branch_minutes(root, c), "note": AUTO_NOTE}
        found.append((fields, c))
        seen.append(fields)
    return found


def sync(root, mart, dev=None, say=print):
    """그 마트의 결재 1·2 머지를 interventions에 남기고 새로 쓴 줄 목록을 돌려준다."""
    root = Path(root)
    dev = Path(dev) if dev else root / ".dev"
    records = devlog.read_lines(dev / "interventions.jsonl")
    written = []
    for fields, _ in pending(root, mart, records, say):
        entry = devlog.append("interventions", fields, dev)
        written.append(entry)
        say(f"결재 기록 {entry['id']}: {mart} {fields['stage']} {fields['target']} "
            f"({entry['minutes_spent']}분, {AUTO_NOTE})")
    return written


def preview_all(root, dev=None, say=lambda s: None):
    """대시보드용: 아직 기록되지 않은 결재를 기록 모양으로 돌려준다(쓰지 않음). id는 "자동", ts는 머지 시각."""
    root = Path(root)
    dev = Path(dev) if dev else root / ".dev"
    records = devlog.read_lines(dev / "interventions.jsonl")
    out = []
    for mart in kit_local.contract_marts(root):
        for fields, c in pending(root, mart, records, say):
            ts = datetime.fromtimestamp(c["time"], devlog.KST).isoformat(timespec="seconds")
            out.append({"id": "자동", "ts": ts, **fields})
    return out


def sync_all(root, dev=None, say=print):
    written = []
    for mart in kit_local.contract_marts(root):
        written += sync(root, mart, dev, say)
    return written


def pending_auto_only(root, dev=None):
    """작업 트리의 변경이 interventions.jsonl 끝에 붙은 자동 결재 줄뿐인가(루프가 대신 커밋해도 되는가)."""
    root = Path(root)
    dev = Path(dev) if dev else root / ".dev"
    try:
        rel = (dev / "interventions.jsonl").resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return False
    ok, out = git(root, "status", "--porcelain", "--untracked-files=all")
    lines = [line for line in out.splitlines() if line.strip()] if ok else []
    if not lines or any(line[3:].strip().strip('"') != rel for line in lines):
        return False
    try:
        now = (root / rel).read_bytes()
    except OSError:
        return False
    p = subprocess.run(["git", "-C", str(root), "show", f"HEAD:{rel}"], capture_output=True)
    before = p.stdout if p.returncode == 0 else b""
    if not now.startswith(before):
        return False
    added = [line for line in now[len(before):].decode("utf-8", "replace").splitlines() if line.strip()]
    try:
        return bool(added) and all(json.loads(line).get("note") == AUTO_NOTE for line in added)
    except (ValueError, AttributeError):
        return False


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description="결재 1·2 기록 자동화 (git 머지 기록)")
    p.add_argument("--mart", help="기본: 모든 마트")
    p.add_argument("--root", default=str(PROJECT))
    p.add_argument("--dev-dir", help="기본: <root>/.dev")
    args = p.parse_args(argv)
    try:
        written = (sync(args.root, args.mart, args.dev_dir) if args.mart
                   else sync_all(args.root, args.dev_dir))
    except devlog.DevlogError as e:
        print(f"기록하지 않음: {e}", file=sys.stderr)
        return 1
    print(f"새 결재 기록 {len(written)}건")
    return 0


if __name__ == "__main__":
    sys.exit(main())
