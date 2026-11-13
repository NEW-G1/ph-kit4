"""반복 루프의 AI 호출 (결정 63 ①, 3-5 설계 4-1절).

AI 호출은 call_agent 하나로 한다. 다른 AI로 바꿀 때는 이 파일만 바꾸고, 루프 본체는 AgentResult만 본다.
- 명령: claude -p --agent <role> --permission-mode acceptEdits --output-format json --settings .claude/loop.settings.json
- 프롬프트는 stdin으로 넘긴다. 이 PC의 claude는 npm 래퍼(claude.cmd)라 인수의 첫 줄만 넘어갈 수 있다
  (3-3 스모크 1차, S1). 줄바꿈이 든 명령줄 인수는 실행하지 않는다
- HARNESS_ROLE은 자식 프로세스 환경에만 넣는다. 루프 자신의 os.environ은 바꾸지 않는다 (결정 63 ③)
- 사용량은 json 출력의 modelUsage(모델별)와 total_cost_usd에서 읽는다 (S1). cost_usd는 정가 환산 추정이다
- 시간 초과면 프로세스 트리 전체(claude.cmd → node)를 끝낸다. Windows는 taskkill /T /F, 그 밖은 프로세스 그룹에 SIGKILL
"""
import json
import os
import shutil
import signal
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

KST = timezone(timedelta(hours=9))
PROJECT = Path(__file__).resolve().parents[2]
SETTINGS = Path(".claude") / "loop.settings.json"
ROLES = ("builder", "verifier")
STATUS_PREFIX = "STATUS:"
CONTRACT_CHANGE = "STATUS: contract_change"
# modelUsage 안의 모델별 칸 이름 (S1에서 확인한 Claude Code json 출력)
USAGE_KEYS = {"input_tokens": "inputTokens", "output_tokens": "outputTokens",
              "cache_read_tokens": "cacheReadInputTokens", "cache_write_tokens": "cacheCreationInputTokens",
              "cost_usd": "costUSD"}


class AgentError(Exception):
    """AI를 부르지 못함(명령 없음, 줄바꿈 인수, 잘못된 역할). 루프는 halt infra_error로 멈춘다."""


@dataclass
class ModelUsage:
    model: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    cache_read_tokens: int | None = None
    cache_write_tokens: int | None = None
    cost_usd: float | None = None  # 정가 환산 추정


@dataclass
class AgentResult:
    text: str                      # 최종 응답 텍스트
    contract_change: bool          # 마지막 줄이 "STATUS: contract_change"
    status_line: bool              # STATUS 줄이 있었나 (없으면 "신호 없음")
    usage: list = field(default_factory=list)  # [ModelUsage], 모델별
    total_cost_usd: float | None = None
    started: str = ""
    ended: str = ""
    is_error: bool = False
    timed_out: bool = False
    returncode: int | None = None


def now_ts():
    return datetime.now(KST).isoformat(timespec="seconds")


def find_claude():
    exe = shutil.which("claude.cmd") or shutil.which("claude")
    if exe is None:
        raise AgentError("claude 명령을 찾지 못함")
    return exe


def build_command(exe, role):
    if role not in ROLES:
        raise AgentError(f"역할은 {ROLES} 중 하나: {role!r}")
    cmd = [exe, "-p", "--agent", role, "--permission-mode", "acceptEdits", "--output-format", "json",
           "--settings", SETTINGS.as_posix()]
    bad = [a for a in cmd if "\n" in a or "\r" in a]
    if bad:
        raise AgentError(f"줄바꿈이 든 명령줄 인수는 실행하지 않음 (프롬프트는 stdin): {bad[0][:60]!r}")
    return cmd


def child_env(role, base=None):
    """부모 환경 복사본에 HARNESS_ROLE만 더한다. CLOUDSDK_CONFIG는 그대로 물려받는다."""
    return {**(os.environ if base is None else base), "HARNESS_ROLE": role}


def kill_tree(proc):
    """프로세스 트리 전체를 끝낸다. claude.cmd만 끝내면 node 자식이 남는다."""
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True)
    else:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass


def popen(cmd, cwd, env):
    kwargs = {"start_new_session": True} if sys.platform != "win32" else {}
    return subprocess.Popen(cmd, cwd=cwd, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, **kwargs)


def number(value, kind):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return kind(value)


def parse_usage(data):
    """modelUsage를 모델별 ModelUsage 목록으로. 없으면 빈 목록."""
    usage = []
    for model, u in (data.get("modelUsage") or {}).items():
        u = u if isinstance(u, dict) else {}
        usage.append(ModelUsage(model, **{k: number(u.get(src), float if k == "cost_usd" else int)
                                          for k, src in USAGE_KEYS.items()}))
    return usage


def status_of(text):
    """(contract_change, status_line). 신호는 마지막 줄의 "STATUS: contract_change"만이다 (결정 63 ⑨)."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    status_line = any(line.startswith(STATUS_PREFIX) for line in lines)
    return bool(lines) and lines[-1] == CONTRACT_CHANGE, status_line


def parse_output(stdout):
    """claude -p --output-format json의 출력을 (text, usage, total_cost_usd, is_error)로. 읽지 못하면 is_error."""
    try:
        data = json.loads(stdout)
    except (json.JSONDecodeError, TypeError):
        return stdout or "", [], None, True
    if not isinstance(data, dict):
        return "", [], None, True
    text = data.get("result") if isinstance(data.get("result"), str) else ""
    return text, parse_usage(data), number(data.get("total_cost_usd"), float), bool(data.get("is_error"))


def call_agent(role, prompt, *, iteration, timeout, root=None, exe=None, popen_fn=popen, kill_fn=kill_tree,
               env=None):
    """AI를 한 번 부르고 AgentResult를 돌려준다. iteration은 0(verifier 선작성) 또는 반복 번호."""
    if isinstance(iteration, bool) or not isinstance(iteration, int) or iteration < 0:
        raise AgentError(f"iteration은 0 이상 정수: {iteration!r}")
    cmd = build_command(exe or find_claude(), role)
    started = now_ts()
    proc = popen_fn(cmd, str(root or PROJECT), child_env(role, env))
    data = prompt.encode("utf-8")
    try:
        out, _err = proc.communicate(input=data, timeout=timeout)
    except subprocess.TimeoutExpired:
        kill_fn(proc)
        try:
            proc.communicate(timeout=30)
        except subprocess.TimeoutExpired:
            pass
        return AgentResult("", False, False, started=started, ended=now_ts(), is_error=True, timed_out=True,
                           returncode=proc.returncode)
    text, usage, total, is_error = parse_output((out or b"").decode("utf-8", "replace"))
    change, status_line = status_of(text)
    return AgentResult(text, change, status_line, usage, total, started, now_ts(),
                       is_error or proc.returncode != 0, False, proc.returncode)
