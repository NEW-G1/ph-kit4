"""scripts/loop/agent.py 시험 (3-5 설계 12-1 T8 종료 함수 부분, T14, T20 환경 부분).

claude는 실행하지 않는다. 가짜 Popen으로 명령·stdin·환경만 본다.
"""
import importlib.util
import json
import os
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "loop" / "agent.py"
_spec = importlib.util.spec_from_file_location("agent", SCRIPT)
agent = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(agent)

TWO_LINES = "Line 1: do not use any tools.\nLine 2: reply with exactly OK-2LINES.\n"


class FakeProc:
    def __init__(self, stdout=b"", returncode=0, hang=False):
        self.stdout_data, self.returncode, self.hang = stdout, returncode, hang
        self.pid = 4242
        self.inputs = []
        self.killed = False

    def communicate(self, input=None, timeout=None):
        self.inputs.append(input)
        if self.hang and not self.killed:
            raise subprocess.TimeoutExpired("claude", timeout)
        return self.stdout_data, b""


class Recorder:
    def __init__(self, proc):
        self.proc, self.calls = proc, []

    def __call__(self, cmd, cwd, env):
        self.calls.append({"cmd": cmd, "cwd": cwd, "env": env})
        return self.proc


def output(result="OK", model_usage=None, total=0.05, is_error=False):
    data = {"type": "result", "is_error": is_error, "result": result, "total_cost_usd": total, "usage": {}}
    if model_usage is not None:
        data["modelUsage"] = model_usage
    return json.dumps(data).encode("utf-8")


OPUS = {"inputTokens": 10, "outputTokens": 20, "cacheReadInputTokens": 30, "cacheCreationInputTokens": 40,
        "costUSD": 0.0552732, "webSearchRequests": 0}


def call(proc, role="builder", prompt=TWO_LINES, **kw):
    rec = Recorder(proc)
    kills = []
    r = agent.call_agent(role, prompt, iteration=kw.pop("iteration", 1), timeout=kw.pop("timeout", 60),
                         root="R", exe="C:/npm/claude.cmd", popen_fn=rec, kill_fn=kills.append, **kw)
    return r, rec, kills


# ---------- T14 ----------

def test_prompt_goes_to_stdin_and_args_have_no_newline():
    proc = FakeProc(output(model_usage={"claude-opus-5-5": OPUS}))
    r, rec, _ = call(proc)
    assert proc.inputs == [TWO_LINES.encode("utf-8")]
    cmd = rec.calls[0]["cmd"]
    assert all("\n" not in a and "\r" not in a for a in cmd)
    assert TWO_LINES.splitlines()[0] not in " ".join(cmd)
    assert cmd[1:] == ["-p", "--agent", "builder", "--permission-mode", "acceptEdits", "--output-format", "json",
                       "--settings", ".claude/loop.settings.json"]
    assert rec.calls[0]["cwd"] == "R"
    assert r.text == "OK" and not r.is_error and not r.timed_out


def test_newline_in_args_refused():
    with pytest.raises(agent.AgentError):
        agent.build_command("C:/a\nb/claude.cmd", "builder")


def test_unknown_role_refused():
    with pytest.raises(agent.AgentError):
        agent.build_command("claude", "admin")


def test_harness_role_only_in_child_env(monkeypatch):
    monkeypatch.delenv("HARNESS_ROLE", raising=False)
    monkeypatch.setenv("CLOUDSDK_CONFIG", "C:/cfg")
    before = dict(os.environ)
    _, rec, _ = call(FakeProc(output(model_usage={})), role="verifier", iteration=0)
    env = rec.calls[0]["env"]
    assert env["HARNESS_ROLE"] == "verifier"
    assert env["CLOUDSDK_CONFIG"] == "C:/cfg"
    assert "HARNESS_ROLE" not in os.environ
    assert dict(os.environ) == before


def test_one_model_usage():
    r, _, _ = call(FakeProc(output(model_usage={"claude-opus-5-5": OPUS}, total=0.0552732)))
    assert len(r.usage) == 1
    u = r.usage[0]
    assert (u.model, u.input_tokens, u.output_tokens, u.cache_read_tokens, u.cache_write_tokens) == \
        ("claude-opus-5-5", 10, 20, 30, 40)
    assert u.cost_usd == pytest.approx(0.0552732)
    assert r.total_cost_usd == pytest.approx(0.0552732)


def test_many_models_usage():
    usage = {"claude-opus-5-5": OPUS, "claude-haiku-5-5": {"inputTokens": 1, "outputTokens": 2, "costUSD": 0.001}}
    r, _, _ = call(FakeProc(output(model_usage=usage)))
    assert [u.model for u in r.usage] == ["claude-opus-5-5", "claude-haiku-5-5"]
    assert r.usage[1].cache_read_tokens is None and r.usage[1].output_tokens == 2


def test_no_model_usage():
    r, _, _ = call(FakeProc(output(model_usage=None, total=None)))
    assert r.usage == [] and r.total_cost_usd is None


def test_unparseable_output_is_error():
    r, _, _ = call(FakeProc(b"not json"))
    assert r.is_error and r.usage == [] and r.text == "not json"


def test_nonzero_exit_is_error():
    r, _, _ = call(FakeProc(output(), returncode=1))
    assert r.is_error and r.returncode == 1


@pytest.mark.parametrize("text,change,line", [
    ("고쳤다.\nSTATUS: contract_change", True, True),
    ("고쳤다.\nSTATUS: contract_change\n\n", True, True),
    ("STATUS: contract_change\n이유를 더 적음", False, True),
    ("STATUS: done", False, True),
    ("고쳤다.", False, False),
    ("", False, False),
])
def test_status_line(text, change, line):
    r, _, _ = call(FakeProc(output(result=text)))
    assert (r.contract_change, r.status_line) == (change, line)


def test_times_are_kst():
    r, _, _ = call(FakeProc(output()))
    assert r.started.endswith("+09:00") and r.ended.endswith("+09:00")


def test_bad_iteration_refused():
    with pytest.raises(agent.AgentError):
        call(FakeProc(output()), iteration=-1)


# ---------- T8 (종료 함수 호출 부분) ----------

def test_timeout_kills_process_tree():
    proc = FakeProc(hang=True)

    def kill(p):
        p.killed = True
        kills.append(p)

    kills = []
    r = agent.call_agent("builder", TWO_LINES, iteration=3, timeout=1, root="R", exe="claude",
                         popen_fn=Recorder(proc), kill_fn=kill)
    assert kills == [proc]
    assert r.timed_out and r.is_error
    assert r.usage == [] and r.text == ""


def test_kill_tree_uses_taskkill_on_windows(monkeypatch):
    calls = []
    monkeypatch.setattr(agent.sys, "platform", "win32")
    monkeypatch.setattr(agent.subprocess, "run", lambda cmd, **kw: calls.append(cmd))
    agent.kill_tree(FakeProc())
    assert calls == [["taskkill", "/T", "/F", "/PID", "4242"]]
