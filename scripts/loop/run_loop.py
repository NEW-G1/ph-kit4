"""반복 루프 (3-5, 결정 63). builder 기안 → 변경 검사 → 사다리 → 반려면 다시, 통과면 로컬 커밋.

  python scripts/loop/run_loop.py --mart <마트> [--ds YYYY-MM-DD] [--root R --dev-dir D] [--timeout-sec 1800]
  python scripts/loop/run_loop.py --mart <마트> --extend N --approver approver1 --reason "..." --minutes M
  python scripts/loop/run_loop.py --mart <마트> --reset-streak <task>:<error_type> --approver approver1 --reason "..." --minutes M

- --mart를 안 주면 contract가 정확히 1개일 때 그 마트를 쓴다(kit_local.pick_mart, 0개·2개 이상이면 종료 코드 2).
  명령줄 실행은 CLOUDSDK_CONFIG가 없으면 .kit_local.json의 경로를 먼저 넣는다(common.apply_kit_local)
- 시작 거절 검사 뒤 git 머지 기록에서 결재 1·2를 남긴다(auto_approval.sync). 작업 트리 변경이 자동 결재 줄뿐이면
  (예전 대시보드나 auto_approval.py 명령이 남긴 것 포함) 깨끗한 트리 검사를 통과시키고 그 파일만 "loop: <마트> 결재 기록" 커밋으로 남긴다
- 시작 전 확인(하나라도 아니면 종료 코드 2, 기록 없음): HARNESS_ROLE 없음(맨 먼저) → ai-builder 인증 → main이 아닌 브랜치
  → 깨끗한 작업 트리(아니면 파일 목록) → contract가 origin/main과 같음(결재 1) → contract L0 통과 → 노하우 검사 있음
  → iteration 0 커밋 0개 또는 1개 → iteration 0 커밋 뒤 contract가 바뀌지 않음
- iteration 0: verifier가 _checks를 쓰고, 루프가 허용 경로·머리말·파일 1:1을 검사하고 gen_dq로 게이트를 만든 뒤
  해시 파일과 함께 로컬 커밋한다(꼬리 "Loop-Iteration-0: <마트> v<ver>")
- 반복: 판정 반복 상한(5 + 연장) → 같은 (task, error_type) 3회 연속 → builder → 변경 검사 → STATUS → 사다리 --all
- 호출마다 응답 텍스트를 .dev/agent_responses/<마트>/<run_id>-i<iteration>-<role>.md로 남긴다(cost 줄처럼 변경 검사
  스냅샷 뒤에 쓰고 iteration 0·통과 커밋에 넣는다, 11/2 보완)
- 멈춤은 ladder_result 1파일(verdict halt, rungs [], halt_detail.exception "LoopStop")로 남긴다. 멈추면 작업 트리를
  정리한다(결정 80): .dev 기록과 builder 허용 경로의 작업은 "loop: <마트> 멈춤 기록" 커밋으로 남기고(iteration 0에서
  멈추면 .dev만), 그 밖의 변경은 되돌린다. 원인을 처리한 뒤 같은 명령으로 다시 실행하면 이어진다
- 시작 때 contract를 L0(l0_contract.check_contract)로 먼저 본다. 실패하면 AI를 부르지 않고 시작을 거절한다(결정 80)
- 연장·연속 초기화 결재는 이 옵션으로만 받고, builder를 부르기 전에 approval 1줄을 먼저 기록한다 (결정 63 ⑫~⑭)
- --ds: 매 반복 사다리에 그대로 넘기는 판정 날짜(없으면 사다리 기본값 오늘 UTC). 증분 마트는 원천에 데이터가 있는
  날짜를 준다(결정 79). builder 전에 형식과 사다리가 확실히 거절할 날짜(run_ladder.resolve_ds: snapshot 7일 창 밖,
  미래)를 시작 거절로 막는다. ai_dev 만료 사전 검사는 사다리가 한다. 준 ds는 통과 커밋 메시지와 progress.md 인계 줄에
  남긴다. 이전 실행의 ds를 저장하지 않으므로 멈춤 뒤 재시작할 때 같은 --ds를 다시 준다
- 종료 코드: 0 통과, 2 멈춤·시작 거절. push·PR은 사람이 한다
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

LOOP = Path(__file__).resolve().parent
PROJECT = LOOP.parents[1]
for sub in ("scripts/log", "scripts/ladder", "scripts/metrics", "scripts/setup"):
    sys.path.insert(0, str(PROJECT / sub))
sys.path.insert(0, str(LOOP))
import agent  # noqa: E402
import auto_approval  # noqa: E402
import common  # noqa: E402
import devlog  # noqa: E402
import gen_dq  # noqa: E402
import kit_local  # noqa: E402
import l0_contract  # noqa: E402
import l0_dag  # noqa: E402
import load_mode  # noqa: E402
import rule_candidates  # noqa: E402
import run_ladder  # noqa: E402
import state  # noqa: E402

DEFAULT_TIMEOUT = 1800  # 반복 1회 30분 (CLAUDE.md §5). 다른 값은 스모크 전용
PROMPTS = LOOP / "prompts"
LADDER = PROJECT / "scripts" / "ladder" / "run_ladder.py"
MESSAGE_CHARS = 300


class Refuse(Exception):
    """시작하지 않음. 기록 없이 종료 코드 2."""


class Stop(Exception):
    """루프가 정한 멈춤. ladder_result(LoopStop) 1파일을 남긴다."""

    def __init__(self, reason, message):
        super().__init__(message)
        self.reason = reason


def parse_args(argv):
    p = argparse.ArgumentParser(description="반복 루프 (3-5, 결정 63)")
    p.add_argument("--mart", help="마트. contract가 1개면 생략 가능(자동 선택)")
    p.add_argument("--root", default=str(PROJECT), help="저장소 루트 (스모크용)")
    p.add_argument("--dev-dir", help="기록할 .dev 폴더 (스모크용, 저장소 안이어야 함)")
    p.add_argument("--timeout-sec", type=int, default=DEFAULT_TIMEOUT, help="반복 1회 제한 (스모크 전용)")
    p.add_argument("--ds", help="사다리에 넘길 판정 날짜 YYYY-MM-DD (기본: 사다리 기본값 오늘 UTC). 재시작 때 다시 준다")
    approval = p.add_mutually_exclusive_group()
    approval.add_argument("--extend", type=int, metavar="N", help="max_iterations 뒤 +N회 연장 결재")
    approval.add_argument("--reset-streak", metavar="TASK:ERROR_TYPE", help="same_type_3x 뒤 연속 수 초기화 결재")
    p.add_argument("--approver", help="결재자 역할 코드 approver<숫자> (이름 금지)")
    p.add_argument("--reason", help="결재 사유 (이름·대외비 금지)")
    p.add_argument("--minutes", type=float, help="결재에 쓴 시간(분). 기본값 없음")
    return p.parse_args(argv)


def say(text, err=False):
    print(text, file=sys.stderr if err else sys.stdout, flush=True)


# ---------- 시작 전 확인 ----------

def check_role(environ):
    if environ.get("HARNESS_ROLE"):
        raise Refuse(f"HARNESS_ROLE={environ['HARNESS_ROLE']!r}가 설정된 프로세스에서는 루프를 시작하지 않는다 "
                     "(AI 프로세스 안에서의 호출 차단, 결정 63 ③). 사람 창이면 Remove-Item Env:HARNESS_ROLE 뒤 다시 실행한다")


def check_options(args):
    """연장·초기화 옵션 검사 (6-3절 2). 결재가 없으면 None, 있으면 stage."""
    stage = "loop_extension" if args.extend is not None else "loop_streak_reset" if args.reset_streak else None
    given = [n for n in ("approver", "reason", "minutes") if getattr(args, n) is not None]
    if stage is None:
        if given:
            raise Refuse(f"--{', --'.join(given)}는 --extend 또는 --reset-streak와 함께만 쓴다")
        return None
    missing = [f"--{n}" for n in ("approver", "reason", "minutes") if getattr(args, n) is None]
    if missing:
        raise Refuse(f"{', '.join(missing)}가 없음. 연장·초기화 결재는 --approver·--reason·--minutes가 모두 필요하다")
    if args.minutes < 0:
        raise Refuse("--minutes는 0 이상")
    if not devlog.APPROVER.fullmatch(args.approver):
        raise Refuse("--approver는 역할 코드 approver<숫자>여야 한다 (이름은 넣지 않는다)")
    if not args.reason.strip():
        raise Refuse("--reason이 비어 있음")
    if stage == "loop_extension" and args.extend < 1:
        raise Refuse("--extend는 1 이상 정수")
    if stage == "loop_streak_reset":
        m = re.fullmatch(r"([A-Za-z0-9_]+):(.+)", args.reset_streak)
        if not m or m.group(2) not in devlog.ERROR_TYPES:
            raise Refuse("--reset-streak는 <task>:<error_type>이고 error_type은 ERROR_TYPES 안이어야 한다")
    return stage


def check_ds(args, contract, today=None):
    """--ds 형식과, 사다리가 확실히 거절할 날짜를 builder 전에 막는다. 판정 규칙은 run_ladder.resolve_ds 그대로
    (snapshot 최근 7일, incremental 미래 거부, 결정 79). ai_dev 만료 검사(데이터셋 조회)는 사다리에 맡긴다."""
    if args.ds is None:
        return
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", args.ds):
        raise Refuse(f"--ds는 YYYY-MM-DD여야 함: {args.ds!r}")
    try:
        run_ladder.resolve_ds(args.ds, today or common.utc_today(), load_mode.is_incremental(contract))
    except common.LadderError as e:
        raise Refuse(f"사다리가 거절할 날짜: {e}") from None


def preflight(args, root, dev, bq):
    try:
        bq.check_auth()
    except common.InfraError as e:
        raise Refuse(f"인증: {e}") from None
    try:
        branch = state.git(root, "symbolic-ref", "--short", "-q", "HEAD").strip()
    except state.GitError:
        raise Refuse("detached HEAD에서는 시작하지 않는다. 작업 브랜치로 옮긴다") from None
    if branch == "main":
        raise Refuse("main 브랜치에서는 시작하지 않는다. 작업 브랜치를 만든다")
    if state.git(root, "status", "--porcelain", "--untracked-files=all").strip() and \
            not auto_approval.pending_auto_only(root, dev):  # 자동 결재 줄뿐이면 루프가 커밋한다
        raise Refuse(dirty_message(root))
    try:
        dev.resolve().relative_to(root.resolve())
    except ValueError:
        raise Refuse("--dev-dir는 --root 저장소 안이어야 한다 (로그를 커밋한다)") from None
    paths = common.Paths(root, args.mart)
    try:
        contract = common.load_contract(paths)
    except common.LadderError as e:
        raise Refuse(str(e)) from None
    rel = paths.contract.relative_to(root).as_posix()
    try:
        state.git(root, "fetch", "origin", "main")
    except state.GitError as e:
        raise Refuse(f"결재 1 확인 불가: {e}") from None
    if not state.git_ok(root, "cat-file", "-e", f"origin/main:{rel}") or \
            not state.git_ok(root, "diff", "--quiet", "origin/main", "--", rel):
        raise Refuse(f"{rel}이 origin/main과 다르다 (결재 1을 받은 contract로만 시작한다)")
    l0 = l0_contract.check_contract(contract)
    if l0["status"] != "pass":
        errors = "; ".join(l0["metrics"].get("errors") or [])[:MESSAGE_CHARS * 2]
        raise Refuse(f"{rel}이 형식 검사(L0)를 통과하지 못함: {errors}. 요구서를 고쳐 결재 1을 다시 받는다 ({RESTART_GUIDE})")
    missing = [r for r in contract["modules"]["expert"]["on"] if r not in run_ladder.EXPERT_CHECKS]
    if missing:
        raise Refuse(f"노하우 검사가 아직 없음: {missing}")
    commits = state.iteration0_commits(root, args.mart, contract["version"])
    if len(commits) > 1:
        raise Refuse(f"iteration 0 커밋이 {len(commits)}개다 (꼬리 {state.TRAILER.format(mart=args.mart, version=contract['version'])}). "
                     "사람이 확인한다")
    if commits and not state.git_ok(root, "diff", "--quiet", commits[0], "HEAD", "--", rel):
        raise Refuse(f"iteration 0 커밋({commits[0][:8]}) 뒤에 결재된 {rel}이 바뀌었다. 검증 쿼리를 새 contract로 "
                     "다시 써야 하므로 최신 main에서 새 작업 브랜치를 만들어 시작한다")
    return paths, contract, (commits[0] if commits else None)


RESTART_GUIDE = "docs/kit/START.md의 '요구서를 고친 뒤 다시 시작하기'"


def dirty_message(root):
    """깨끗하지 않은 작업 트리 거절 메시지: 파일 목록과 다음에 할 일."""
    _, changed = state.status(root)
    names = sorted(changed)
    shown = ", ".join(names[:10]) + (f" 외 {len(names) - 10}개" if len(names) > 10 else "")
    return (f"작업 트리가 깨끗하지 않다: {shown}. 요구서 파일이면 결재 1 PR로 올린다({RESTART_GUIDE}). "
            "그 밖이면 git status로 보고 커밋하거나 되돌린 뒤 다시 실행한다")


def next_run_id(dev):
    nums = [int(m.group(1)) for r in devlog.read_lines(Path(dev) / "cost.jsonl")
            if isinstance(r.get("run_id"), str) and (m := re.fullmatch(r"RUN-(\d+)", r["run_id"]))]
    return f"RUN-{(max(nums) if nums else 0) + 1:03d}"


# ---------- 루프 ----------

def default_ladder(argv, timeout):
    """사다리를 자식 프로세스로 돌린다. 시간 초과면 프로세스 트리를 끝내고 None."""
    proc = subprocess.Popen([sys.executable, str(LADDER), *argv], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            **({"start_new_session": True} if sys.platform != "win32" else {}))
    try:
        out, err = proc.communicate(timeout=max(timeout, 1))
    except subprocess.TimeoutExpired:
        agent.kill_tree(proc)
        proc.communicate()
        return None
    sys.stderr.write(err.decode("utf-8", "replace"))
    return proc.returncode


class Loop:
    def __init__(self, args, root, dev, paths, contract, agent_fn, ladder_fn):
        self.args, self.root, self.dev, self.paths, self.contract = args, root, dev, paths, contract
        self.mart, self.version = args.mart, contract["version"]
        self.agent_fn, self.ladder_fn = agent_fn, ladder_fn
        self.run_id = next_run_id(dev)
        self.loads = common.topo_load_tasks(contract)
        self.progress_path = dev / "progress.md"

    # ----- 기록 -----

    def rel(self, path):
        return Path(path).resolve().relative_to(self.root.resolve()).as_posix()

    def interventions(self):
        return devlog.read_lines(self.dev / "interventions.jsonl")

    def rejections(self):
        return devlog.read_lines(self.dev / "rejections.jsonl")

    def snapshot_state(self):
        results = state.load_results(self.dev, self.mart, self.version)
        iters = state.iterations(results)
        return results, iters, state.counts(iters, self.interventions(), self.mart, self.version)

    def write_progress(self, note=None, handoff=None):
        results, iters, c = self.snapshot_state()
        text = self.progress_path.read_text(encoding="utf-8") if self.progress_path.exists() else None
        if note is None and self.args.timeout_sec != DEFAULT_TIMEOUT:
            note = f"시간 제한 {self.args.timeout_sec}초 (스모크 전용 값, 기본 {DEFAULT_TIMEOUT})"
        section = state.progress_section(self.loads, results, self.rejections(), iters, c, self.mart, self.version, note)
        text = state.render_progress(text, self.mart, section)
        if handoff:
            text = state.append_handoff(text, self.mart, handoff)
        self.progress_path.parent.mkdir(parents=True, exist_ok=True)
        self.progress_path.write_text(text, encoding="utf-8", newline="\n")

    def cost(self, role, iteration, result, bq_bytes=0):
        usage = result.usage
        model = "+".join(u.model for u in usage) if usage else "unknown"

        def total(name):
            values = [getattr(u, name) for u in usage]
            return sum(values) if values and all(v is not None for v in values) else None

        devlog.append("cost", {
            "run_id": self.run_id, "mart": self.mart, "iteration": iteration, "role": role, "model": model,
            "started": result.started, "ended": result.ended, "usage_before": None, "usage_after": None,
            "input_tokens": total("input_tokens"), "output_tokens": total("output_tokens"),
            "cache_read_tokens": total("cache_read_tokens"), "cache_write_tokens": total("cache_write_tokens"),
            "total_cost_usd": result.total_cost_usd, "bq_bytes_processed": bq_bytes}, self.dev)

    def response_path(self, role, iteration):
        return self.dev / "agent_responses" / self.mart / f"{self.run_id}-i{iteration}-{role}.md"

    def response(self, role, iteration, result):
        """응답 텍스트를 그대로 남긴다 (11/2 보완). 변경 검사 스냅샷 뒤에만 부른다."""
        path = self.response_path(role, iteration)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((result.text or "").encode("utf-8"))
        return path

    def stop_file(self, n, reason, message):
        """루프가 정한 멈춤 1파일. task는 직전 반려의 task, 없으면 위상 순서 첫 load task (설계 2절 C)."""
        _, iters, _ = self.snapshot_state()
        last = state.last_judged_reject(iters)
        candidates = ([last.task] if last else []) + [t["id"] for t in self.loads]
        folder = self.dev / "ladder_results" / self.mart
        for task in dict.fromkeys(candidates):
            if (folder / f"{task}-v{self.version}-{n}.json").exists():
                continue  # 사다리가 시간 초과 전에 이 task의 결과를 남긴 경우
            return devlog.write_ladder_result(self.mart, {
                "task": task, "iteration": n, "contract_version": self.version, "request_kind": "new_build",
                "modules": self.contract["modules"], "bytes_total": None, "rungs": [], "verdict": "halt",
                "halt_reason": reason, "halt_detail": {"exception": "LoopStop", "message": message[:500]}}, self.dev)
        return None

    def halt(self, n, reason, message):
        path = self.stop_file(n, reason, message)
        self.write_progress(handoff=f"iteration {n}: 멈춤 {reason} — {message}")
        say(f"멈춤: {reason} (iteration {n}) — {message}", err=True)
        if path is None:
            say("(이 반복의 모든 task에 결과 파일이 있어 멈춤 파일을 남기지 못함)", err=True)
        return self.tidy(f"iteration {n}, {reason}", keep_builder=True)

    def tidy(self, label, keep_builder):
        """멈춘 뒤 작업 트리를 깨끗하게 둔다 (결정 80). .dev 기록과(keep_builder면) builder 허용 경로의 작업은 커밋하고,
        그 밖의 변경(허용 밖 수정, iteration 0의 미완성 검증 쿼리·게이트)은 되돌린다. 시작 때 트리가 깨끗했으므로
        남은 변경은 모두 이번 실행이 만든 것이다. 같은 명령으로 다시 실행하면 이어진다."""
        _, changed = state.status(self.root)
        dev = self.rel(self.dev) + "/"
        allowed = state.builder_allowed(self.contract) if keep_builder else ()
        keep = [p for p in changed if p.startswith(dev) or any(rx.fullmatch(p) for rx in allowed)]
        drop = [p for p in changed if p not in keep]
        if keep:
            sha = self.commit(keep, f"loop: {self.mart} v{self.version} 멈춤 기록 ({label})\n")
            say(f"멈춤 기록 커밋 {sha[:8]} (.dev 기록" + (", builder 작업" if keep_builder else "") + ")", err=True)
        if drop:
            in_head = set(state.git(self.root, "ls-tree", "-r", "--name-only", "HEAD", "--", *drop).splitlines())
            if in_head:
                state.git(self.root, "restore", "--source=HEAD", "--staged", "--worktree", "--", *sorted(in_head))
            for p in drop:
                if p not in in_head:
                    state.git(self.root, "rm", "-q", "--cached", "--ignore-unmatch", "--", p)
                    (self.root / p).unlink(missing_ok=True)
                    parent = (self.root / p).parent
                    while parent != self.root and parent.is_dir() and not any(parent.iterdir()):
                        parent.rmdir()  # 이번 실행이 만든 빈 폴더
                        parent = parent.parent
            shown = ", ".join(drop[:10]) + (f" 외 {len(drop) - 10}개" if len(drop) > 10 else "")
            say(f"되돌린 변경: {shown}", err=True)
        say(f"원인을 처리한 뒤 같은 명령으로 다시 실행하면 이어진다. 요구서를 고쳐야 하면 {RESTART_GUIDE}", err=True)
        return 2

    def commit(self, paths, message):
        state.git(self.root, "add", "-A", "--", *[p for p in paths if (self.root / p).exists()])
        gone = [p for p in paths if not (self.root / p).exists()]
        if gone:  # 지워진 경로 (예: builder가 지운 DAG 파일)
            state.git(self.root, "rm", "-q", "-r", "--cached", "--ignore-unmatch", "--", *gone)
        p = subprocess.run(["git", "commit", "-q", "-F", "-"], cwd=self.root, input=message.encode("utf-8"),
                           capture_output=True)
        if p.returncode != 0:
            raise state.GitError("git commit: " + p.stderr.decode("utf-8", "replace").strip()[:300])
        return state.head(self.root)

    # ----- iteration 0 -----

    def iteration0(self):
        self.write_progress()
        before = state.snapshot(self.root)
        hook_blocks = state.file_bytes(self.root, state.HOOK_BLOCKS) or b""
        prompt = (PROMPTS / "verifier.md").read_text(encoding="utf-8").replace("{mart}", self.mart)
        result = self.agent_fn("verifier", prompt, iteration=0, timeout=self.args.timeout_sec, root=self.root)
        after = state.snapshot(self.root)  # 루프가 쓰는 cost 줄·응답 파일보다 먼저 뜬다
        self.response("verifier", 0, result)
        self.cost("verifier", 0, result)
        problem = None
        if result.timed_out:
            problem = "timeout", f"verifier 호출이 {self.args.timeout_sec}초를 넘음 (프로세스 트리 종료)"
        elif result.is_error:
            problem = "infra_error", f"verifier 호출 실패 (종료 코드 {result.returncode})"
        else:
            bad = state.disallowed(self.root, before, after, state.verifier_allowed(self.mart), hook_blocks)
            if bad:
                problem = "input_invalid", "verifier가 허용 경로 밖을 바꿈: " + ", ".join(bad[:10])
        if problem is None:
            errors = l0_dag.check_checks(self.paths, self.contract)
            if errors:
                problem = "input_invalid", "검증 쿼리 사전 검사: " + "; ".join(errors)[:MESSAGE_CHARS * 2]
            elif gen_dq.main(["--mart", self.mart, "--root", str(self.root)]) != 0:
                problem = "input_invalid", "gen_dq.py로 게이트를 만들지 못함"
        if problem:  # iteration 0의 멈춤은 progress.md와 stderr만 (설계 9절 C). .dev만 커밋하고 나머지는 되돌린다
            self.write_progress(handoff=f"iteration 0: 멈춤 {problem[0]} — {problem[1]}")
            say(f"멈춤: {problem[0]} (iteration 0) — {problem[1]}. builder를 부르지 않는다", err=True)
            self.tidy(f"iteration 0, {problem[0]}", keep_builder=False)
            return None
        hash_path = state.write_hash_file(self.root, self.dev, self.mart, self.version)
        trailer = state.TRAILER.format(mart=self.mart, version=self.version)
        sha = self.commit([f"docs/requirements/{self.mart}_checks", "dags/sql/dq", self.rel(hash_path),
                           self.rel(self.progress_path), self.rel(self.dev / "cost.jsonl"),
                           self.rel(self.response_path("verifier", 0))],
                          f"loop: {self.mart} v{self.version} iteration 0 (검증 쿼리·게이트)\n\n{trailer}\n")
        say(f"iteration 0 커밋 {sha[:8]}")
        return sha

    # ----- 반복 -----

    def rejection_block(self, iters):
        """직전 판정 반복이 반려일 때의 블록과 (R-id, 같은 쌍 2번째 이상인가)."""
        judged = [it for it in iters if it.judged]
        if not judged or judged[-1].verdict != "reject":
            return "", None, False
        it = judged[-1]
        same = [r for r in self.rejections()
                if r.get("mart") == self.mart and r.get("task") == it.task and r.get("error_type") == it.error_type]
        if not same:
            return "", None, False
        r = same[-1]
        g = next(f for f in it.files if f["verdict"] == "reject")["rungs"][-1]
        check = g["metrics"].get("check", "—")
        block = (f"직전 반려 {r['id']}: task {it.task}, 단계 {g['rung']}, 유형 {it.error_type}({g['error_class']}), "
                 f"검사 {check}, 메시지 {r['detail'][:MESSAGE_CHARS]}")
        second = len(same) >= 2
        if second:
            block += (f"\n같은 유형으로 다시 반려되었다. 고치기 전에 .dev/progress.md 에 \"### {r['id']} 원인\" 아래 3줄\n"
                      "(왜 틀렸나 / 이번엔 무엇을 다르게 하나 / 어떻게 확인했나)을 먼저 쓴다.\n"
                      "실패한 검사의 결과 예시(최대 5행, 합성 데이터):\n"
                      + "\n".join(json.dumps(row, ensure_ascii=False) for row in self.evidence_rows(r["evidence"])))
        return block, r["id"], second

    @staticmethod
    def evidence_rows(evidence):
        return evidence if isinstance(evidence, list) else [evidence]

    def builder_prompt(self, n, block):
        text = (PROMPTS / "builder.md").read_text(encoding="utf-8")
        return text.replace("{mart}", self.mart).replace("{n}", str(n)).replace("{직전 반려 블록}", block).rstrip() + "\n"

    def record_rejection(self, n):
        files = state.load_results(self.dev, self.mart, self.version)
        f = next(r for r in files if r["iteration"] == n and r["verdict"] == "reject")
        g = f["rungs"][-1]
        m = g["metrics"]
        message = m.get("message") or "; ".join(m.get("errors") or []) or \
            f"검사 {m.get('check', '—')} 위반 {m.get('violations_shown', '?')}행"
        detail = f"{g['rung']} {g['error_type']}" + (f" [{m['check']}]" if m.get("check") else "") + f": {message}"
        same = [r for r in self.rejections()
                if r.get("mart") == self.mart and r.get("task") == f["task"] and r.get("error_type") == g["error_type"]]
        evidence = None
        if same:  # 같은 (task, error_type) 2번째부터 (결정 49 ④). 실패 rung의 evidence, 없으면 message·errors
            evidence = m.get("evidence") or {k: m[k] for k in ("message", "errors") if m.get(k)} or {"detail": detail}
        return devlog.append("rejections", {
            "mart": self.mart, "task": f["task"], "iteration": n, "contract_version": self.version,
            "caught_by_rung": g["rung"], "error_type": g["error_type"], "error_class": g["error_class"],
            "detail": detail[:1000], "evidence": evidence}, self.dev)

    def update_rule_candidates(self):
        """반려 뒤 규칙 후보를 갱신한다 (03 §6.3). 측정 부가 작업이라 실패해도 루프 판정에 영향을 주지 않는다."""
        try:
            for rule_id in rule_candidates.update(self.root, self.dev):
                say(f"규칙 후보 {rule_id} 생성 (.dev/rule_candidates.md, 사람 결재 대기)")
        except Exception as e:  # noqa: BLE001  어떤 실패든 판정을 바꾸지 않는다
            say(f"규칙 후보 갱신 실패 ({e.__class__.__name__}: {str(e)[:MESSAGE_CHARS]}). 판정은 그대로 진행", err=True)

    def ladder_bytes(self, n):
        """같은 반복 ladder_result의 bytes_total 합 + 실패 파일의 interrupted_tasks 바이트 합 (R-0001)."""
        return sum((r["bytes_total"] or 0) + sum(i["bytes"] for i in r.get("interrupted_tasks") or [])
                   for r in state.load_results(self.dev, self.mart, self.version) if r["iteration"] == n)

    def iterate(self, iter0):
        while True:
            results, iters, c = self.snapshot_state()
            n = state.next_iteration(results)
            # 상한은 builder 전에 본다. 연장 결재 없이 재시작하면 builder를 부르지 않고 다시 멈춘다 (6-1)
            if c.max_reached:
                return self.halt(n, "max_iterations", f"판정된 반복 {c.judged}/{c.limit}회. 연장은 --extend N 결재로만")
            block, rid, second = self.rejection_block(iters)
            self.write_progress()
            ext = " (연장분)" if c.extension_from else ""
            say(f"iteration {n}{ext}: builder 호출 (판정 반복 {c.judged}/{c.limit})")
            head_before, before = state.status(self.root)
            hook_blocks = state.file_bytes(self.root, state.HOOK_BLOCKS) or b""
            started = time.monotonic()
            result = self.agent_fn("builder", self.builder_prompt(n, block), iteration=n,
                                   timeout=self.args.timeout_sec, root=self.root)
            if result.timed_out:
                self.response("builder", n, result)
                self.cost("builder", n, result)
                return self.halt(n, "timeout", f"builder 호출이 {self.args.timeout_sec}초를 넘음 (프로세스 트리 종료)")
            if result.is_error:
                self.response("builder", n, result)
                self.cost("builder", n, result)
                return self.halt(n, "infra_error", f"builder 호출 실패 (종료 코드 {result.returncode})")
            problem = state.check_changes(self.root, self.dev, self.mart, self.version, before, head_before, iter0,
                                          allowed=state.builder_allowed(self.contract), hook_blocks_before=hook_blocks)
            self.response("builder", n, result)  # 변경 검사 뒤 (builder 변경으로 잡히지 않게)
            if problem:
                self.cost("builder", n, result)
                return self.halt(n, "input_invalid", f"변경 검사 {problem[0]}: {problem[1]}")
            if result.contract_change:
                self.cost("builder", n, result)
                return self.halt(n, "contract_change", "builder가 STATUS: contract_change를 남김. contract v2 PR을 기안한다")
            notes = []
            if not result.status_line:
                notes.append("신호 없음 (STATUS 줄 없음, 반려 아님)")
            if second:
                text = self.progress_path.read_text(encoding="utf-8") if self.progress_path.exists() else ""
                if not state.has_three_lines(text, rid):
                    notes.append(f"3줄 없음 ({rid} 원인, 사다리는 그대로 돌린다)")
            for note in notes:
                self.write_progress(handoff=f"iteration {n}: {note}")
            remaining = self.args.timeout_sec - (time.monotonic() - started)
            argv = ["--mart", self.mart, "--all", "--iteration", str(n), "--root", str(self.root),
                    "--dev-dir", str(self.dev)]
            if self.args.ds is not None:
                argv += ["--ds", self.args.ds]
            code = self.ladder_fn(argv, remaining) if remaining > 0 else None
            self.cost("builder", n, result, self.ladder_bytes(n))
            if code is None:
                return self.halt(n, "timeout", f"반복 1회가 {self.args.timeout_sec}초를 넘음 (사다리 프로세스 트리 종료)")
            if code == 0:
                return self.passed(n)
            if code == 1:
                r = self.record_rejection(n)
                self.update_rule_candidates()
                self.write_progress()
                say(f"iteration {n}: 반려 {r['id']} ({r['task']} {r['caught_by_rung']} {r['error_type']})")
                # 연속은 새 반려 직후에 본다. 초기화 결재 없이 재시작하면 같은 쌍 반려 1회로 다시 멈춘다(4회 연속, 6-2)
                _, _, c = self.snapshot_state()
                if c.same_type_reached:
                    key = f"{c.streak_key[0]}:{c.streak_key[1]}"
                    return self.halt(n + 1, "same_type_3x", f"같은 (task, error_type) {key} {c.streak}회 연속. "
                                     f"초기화는 --reset-streak {key} 결재로만")
                continue
            halted = [r for r in state.load_results(self.dev, self.mart, self.version)
                      if r["iteration"] == n and r["verdict"] == "halt"]
            if not halted:  # 사다리가 시작하지 못해 결과 파일이 없음
                return self.halt(n, "infra_error", f"사다리가 결과 없이 종료 코드 {code}로 끝남")
            h = halted[0]
            detail = (h.get("halt_detail") or {}).get("message", "")
            self.write_progress(handoff=f"iteration {n}: 사다리 멈춤 {h['halt_reason']} — {detail[:MESSAGE_CHARS]}")
            say(f"멈춤: 사다리 {h['halt_reason']} (iteration {n}). 반려로 세지 않는다", err=True)
            return self.tidy(f"iteration {n}, 사다리 {h['halt_reason']}", keep_builder=True)

    def passed(self, n):
        ds = self.args.ds
        self.write_progress(handoff=f"iteration {n}: 사다리 통과" + (f" (ds {ds})" if ds else ""))
        sha = self.commit([*state.builder_paths(), self.rel(self.dev)],
                          f"loop: {self.mart} v{self.version} 통과 (iteration {n}" + (f", ds {ds}" if ds else "") + ")\n")
        say(f"통과: iteration {n}, 커밋 {sha[:8]}. push·PR은 사람이 한다")
        say(f"인수인계 초안: python scripts/handover/make_facts.py --mart {self.mart} 실행 뒤 설명 칸(1·6·7)을 채운다")
        return 0


def record_approval(args, stage, dev, contract, iters, c):
    """연장·초기화 결재를 상태 검사 뒤 먼저 기록한다 (6-3절 3·4). 실패하면 Refuse."""
    last = iters[-1] if iters else None
    if stage == "loop_extension":
        if not last or last.verdict != "halt" or last.halt_reason != "max_iterations":
            raise Refuse("결재할 멈춤이 없음: 마지막 결과가 halt max_iterations가 아니다")
        extra = {"extra_iterations": args.extend}
        target = f"{args.mart} 반복 연장 +{args.extend}"
    else:
        key = f"{c.streak_key[0]}:{c.streak_key[1]}" if c.streak_key else None
        if not last or last.verdict != "halt" or last.halt_reason != "same_type_3x" or key != args.reset_streak:
            raise Refuse("결재할 멈춤이 없음: 마지막 결과가 이 (task, error_type)의 halt same_type_3x가 아니다")
        extra = {"streak_key": args.reset_streak}
        target = f"{args.mart} 연속 초기화 {args.reset_streak}"
    minutes = int(args.minutes) if float(args.minutes).is_integer() else args.minutes
    try:
        entry = devlog.append("interventions", {
            "mart": args.mart, "kind": "approval", "stage": stage, "target": target, "minutes_spent": minutes,
            "note": "", "contract_version": contract["version"], **extra, "approver": args.approver,
            "reason": args.reason}, dev, loop_record=True)
    except devlog.DevlogError as e:
        raise Refuse(f"결재를 기록하지 못함: {e}") from None
    say(f"결재 기록 {entry['id']} ({stage}, {target})")


def sync_approvals(root, dev, mart):
    """git 머지 기록에서 결재 1·2를 남기고(auto_approval.sync), 작업 트리 변경이 자동 결재 줄뿐이면 그 파일만 커밋한다.
    기록하지 못해도 루프는 시작한다(대시보드가 결재 대기로 보일 뿐이다)."""
    try:
        auto_approval.sync(root, mart, dev, say=say)
    except (devlog.DevlogError, OSError) as e:
        say(f"경고: 결재 자동 기록 실패 ({e}). 필요하면 devlog.py intervention으로 손으로 남긴다", err=True)
        return
    if not auto_approval.pending_auto_only(root, dev):
        return
    rel = (dev / "interventions.jsonl").resolve().relative_to(root.resolve()).as_posix()
    try:
        state.git(root, "add", "--", rel)
    except state.GitError as e:
        say(f"경고: 결재 기록을 커밋하지 못함 ({e})", err=True)
        return
    p = subprocess.run(["git", "commit", "-q", "-F", "-"], cwd=root, capture_output=True,
                       input=f"loop: {mart} 결재 기록 ({auto_approval.AUTO_NOTE})\n".encode("utf-8"))
    if p.returncode != 0:
        say("경고: 결재 기록을 커밋하지 못함: " + p.stderr.decode("utf-8", "replace").strip()[:300], err=True)
        return
    say(f"결재 기록 커밋 {state.head(root)[:8]}")


def warn_without_intervention(args, dev, iters):
    last = iters[-1] if iters else None
    if not last or last.verdict != "halt":
        return
    after = [r for r in devlog.read_lines(dev / "interventions.jsonl")
             if r.get("mart") == args.mart and state.parse_ts(r["ts"]) >= state.parse_ts(last.ts)]
    if not after:
        say(f"참고: 직전 멈춤(iteration {last.n}, {last.halt_reason}) 뒤 다시 시작한다. 원인을 사람이 확인했다면 "
            "devlog.py intervention --kind manual_check(직접 고쳤으면 correction)로 남길 수 있다", err=True)


def main(argv=None, *, agent_fn=None, ladder_fn=None, bq=None, environ=None):
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    try:
        check_role(os.environ if environ is None else environ)  # 인증·git 검사보다 먼저
        args = parse_args(argv)
        root = Path(args.root)
        args.mart = kit_local.pick_mart(root, args.mart)
        if args.mart is None:
            return 2
        dev = Path(args.dev_dir) if args.dev_dir else root / ".dev"
        paths, contract, iter0 = preflight(args, root, dev, bq or common.Bq())
        check_ds(args, contract)  # 결재 기록·verifier·builder 전
        stage = check_options(args)
        sync_approvals(root, dev, args.mart)  # 시작 거절 검사 뒤, 루프 결재 기록 전
        if stage:
            results = state.load_results(dev, args.mart, contract["version"])
            iters = state.iterations(results)
            c = state.counts(iters, devlog.read_lines(dev / "interventions.jsonl"), args.mart, contract["version"])
            record_approval(args, stage, dev, contract, iters, c)
    except Refuse as e:
        say(f"루프를 시작하지 않음: {e}", err=True)
        return 2
    except SystemExit as e:  # argparse 사용 오류
        return 2 if e.code else 0

    loop = Loop(args, root, dev, paths, contract, agent_fn or agent.call_agent, ladder_fn or default_ladder)
    if args.timeout_sec != DEFAULT_TIMEOUT:
        say(f"시간 제한 {args.timeout_sec}초 (스모크 전용 값, 기본 {DEFAULT_TIMEOUT})")
    try:
        if iter0 is None:
            iter0 = loop.iteration0()
            if iter0 is None:
                return 2
        else:
            warn_without_intervention(args, dev, state.iterations(state.load_results(dev, args.mart, loop.version)))
            if not loop.progress_path.exists():
                loop.write_progress()
        return loop.iterate(iter0)
    except (agent.AgentError, state.GitError, devlog.DevlogError, OSError) as e:
        say(f"멈춤: 루프 오류 {e.__class__.__name__}: {e}", err=True)
        return 2


if __name__ == "__main__":
    common.apply_kit_local()  # 새 창: .kit_local.json의 CLOUDSDK_CONFIG (있으면 덮어쓰지 않음)
    sys.exit(main())
