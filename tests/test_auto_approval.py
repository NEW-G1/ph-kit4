"""결재 1·2 자동 기록 시험 (scripts/log/auto_approval.py). 임시 git 저장소에 시각을 정한 머지 커밋을 만든다."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
for sub in ("scripts/log", "scripts/loop", "scripts/ladder", "scripts/setup", "scripts/metrics"):
    sys.path.insert(0, str(ROOT / sub))
import auto_approval  # noqa: E402
import devlog  # noqa: E402
import run_loop  # noqa: E402

MART = "mart_x"
CONTRACT = f"docs/requirements/{MART}.contract.json"
TASKS = [{"id": "raw_x", "kind": "load", "layer": "raw", "upstream": []},
         {"id": "gate_raw_mart_x", "kind": "gate", "layer": "raw", "upstream": ["raw_x"]},
         {"id": "mart_x", "kind": "load", "layer": "mart", "upstream": ["gate_raw_mart_x"]}]
pytestmark = pytest.mark.real_git


def at(minute):
    """2026-11-01 09:00 +09:00에서 minute분 뒤 (git 날짜 형식)."""
    return f"2026-11-01T{9 + minute // 60:02d}:{minute % 60:02d}:00+09:00"


def git(root, *args, date=None):
    env = dict(os.environ, GIT_AUTHOR_DATE=date, GIT_COMMITTER_DATE=date) if date else None
    p = subprocess.run(["git", *args], cwd=root, env=env, capture_output=True, text=True, encoding="utf-8")
    assert p.returncode == 0, f"git {args}: {p.stderr}"
    return p.stdout.strip()


def write(root, rel, text):
    path = Path(root) / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q", "--template=", "-b", "main")
    with (root / ".git" / "config").open("a", encoding="utf-8") as f:
        f.write("[user]\n\tname = tester\n\temail = tester@example.com\n[core]\n\tautocrlf = false\n")
    write(root, "README.md", "# repo\n")
    write(root, ".gitignore", "*.lock\n")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "init", date=at(0))
    return root


def pr(root, branch, files, start, merge, commits=2):
    """main에서 branch를 만들어 start분부터 1분 간격으로 커밋하고 merge분에 --no-ff 머지. 머지 sha를 돌려준다."""
    git(root, "checkout", "-q", "-b", branch, "main")
    for i in range(commits):
        for rel, text in files.items():
            write(root, rel, f"{text}\n-- {i}\n" if rel.endswith(".sql") else text)
        write(root, f"notes/{branch}.txt", f"{i}\n")
        git(root, "add", "-A")
        git(root, "commit", "-q", "-m", f"{branch} {i}", date=at(start + i))
    git(root, "checkout", "-q", "main")
    git(root, "merge", "-q", "--no-ff", "-m", f"Merge {branch}", branch, date=at(merge))
    return git(root, "rev-parse", "HEAD")


def contract_files(version=1):
    return {CONTRACT: json.dumps({"mart": MART, "version": version, "dag": {"tasks": TASKS}})}


def build_files():
    return {"dags/sql/raw/raw_x.sql": "SELECT 1", "dags/sql/mart/mart_x.sql": "SELECT 2"}


def records(root):
    return devlog.read_lines(root / ".dev" / "interventions.jsonl")


def test_approval_1_and_2_from_merges(repo):
    m1 = pr(repo, "req", contract_files(), start=10, merge=30)
    m2 = pr(repo, "build", build_files(), start=40, merge=100)
    written = auto_approval.sync(repo, MART, say=lambda s: None)
    assert [(r["stage"], r["target"], r["minutes_spent"]) for r in written] == [
        ("approval_1", f"PR 머지 {m1[:7]}", 20), ("approval_2", f"PR 머지 {m2[:7]}", 60)]
    assert all(r["kind"] == "approval" and r["mart"] == MART and r["note"] == auto_approval.AUTO_NOTE for r in written)
    assert "approver" not in written[0]
    assert records(repo) == written


def test_minutes_round_up_and_at_least_one(repo, monkeypatch):
    m = pr(repo, "req", contract_files(), start=10, merge=10, commits=1)
    commit = next(c for c in auto_approval.history(repo, "main") if c["sha"] == m)
    assert auto_approval.branch_minutes(repo, commit) == 1  # 같은 분: 0분 → 최소 1
    commit = dict(commit, time=commit["time"] + 61)
    assert auto_approval.branch_minutes(repo, commit) == 2  # 61초 → 올림


def test_sync_is_idempotent_by_sha(repo):
    pr(repo, "req", contract_files(), start=10, merge=30)
    assert len(auto_approval.sync(repo, MART, say=lambda s: None)) == 1
    assert auto_approval.sync(repo, MART, say=lambda s: None) == []
    assert len(records(repo)) == 1


def test_sha_in_human_record_is_not_written_again(repo):
    m1 = pr(repo, "req", contract_files(), start=10, merge=30)
    devlog.append("interventions", {"mart": MART, "kind": "approval", "stage": "approval_1",
                                    "target": f"PR #3 merge {m1[:7]}", "minutes_spent": 4, "note": ""}, repo / ".dev")
    assert auto_approval.sync(repo, MART, say=lambda s: None) == []


def test_merges_before_latest_human_record_are_skipped(repo):
    """사람이 손으로 남긴 기록(시각은 지금)보다 이전의 머지는 이미 기록된 결재로 본다. 다른 stage는 따로 본다."""
    pr(repo, "req", contract_files(), start=10, merge=30)
    m2 = pr(repo, "build", build_files(), start=40, merge=100)
    devlog.append("interventions", {"mart": MART, "kind": "approval", "stage": "approval_1",
                                    "target": "요구서 PR 머지", "minutes_spent": 5, "note": ""}, repo / ".dev")
    written = auto_approval.sync(repo, MART, say=lambda s: None)
    assert [(r["stage"], r["target"]) for r in written] == [("approval_2", f"PR 머지 {m2[:7]}")]


def test_other_mart_records_do_not_block(repo):
    pr(repo, "req", contract_files(), start=10, merge=30)
    devlog.append("interventions", {"mart": "mart_other", "kind": "approval", "stage": "approval_1",
                                    "target": "요구서 PR 머지", "minutes_spent": 5, "note": ""}, repo / ".dev")
    assert [r["stage"] for r in auto_approval.sync(repo, MART, say=lambda s: None)] == ["approval_1"]


def test_one_build_approval_per_contract_approval(repo):
    """결재 1 뒤 첫 구현 머지만 결재 2다. 그 뒤 인수인계만 고친 PR은 결재가 아니다. contract v2 뒤에는 다시 센다."""
    m1 = pr(repo, "req", contract_files(), start=10, merge=30)
    first = pr(repo, "build", {**build_files(), ".dev/handover/b.md": f"# 인수인계 — {MART} (build, 2026-11-01)\n"},
               start=40, merge=100)
    pr(repo, "restamp", {".dev/handover/b.md": f"# 인수인계 — {MART} (build, 2026-11-01)\n도장\n"}, start=110, merge=120)
    v2 = pr(repo, "req-v2", contract_files(2), start=130, merge=140)
    again = pr(repo, "build-v2", {".dev/handover/c.md": f"# 인수인계 — {MART} (build-v2, 2026-11-01)\n"},
               start=150, merge=170)
    written = auto_approval.sync(repo, MART, say=lambda s: None)
    assert [(r["stage"], r["target"][-7:]) for r in written] == [
        ("approval_1", m1[:7]), ("approval_2", first[:7]),
        ("approval_1", v2[:7]), ("approval_2", again[:7])]


def test_handover_of_other_mart_is_not_build_approval(repo):
    pr(repo, "req", contract_files(), start=10, merge=30)
    pr(repo, "other", {".dev/handover/o.md": "# 인수인계 — mart_other (other, 2026-11-01)\n"}, start=40, merge=50)
    assert [r["stage"] for r in auto_approval.sync(repo, MART, say=lambda s: None)] == ["approval_1"]


def test_non_merge_commit_is_skipped_and_reported(repo):
    write(repo, CONTRACT, contract_files()[CONTRACT])
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "squash", date=at(20))
    said = []
    assert auto_approval.sync(repo, MART, say=said.append) == []
    assert len(said) == 1 and "머지 커밋이 아니다" in said[0]


def test_prefers_origin_main(repo, tmp_path):
    pr(repo, "req", contract_files(), start=10, merge=30)
    origin = tmp_path / "origin.git"
    git(tmp_path, "clone", "-q", "--bare", "--template=", str(repo), str(origin))
    git(repo, "remote", "add", "origin", str(origin))
    git(repo, "fetch", "-q", "origin")
    pr(repo, "build", build_files(), start=40, merge=100)  # 로컬 main에만 있는 머지
    assert auto_approval.main_ref(repo) == "origin/main"
    assert [r["stage"] for r in auto_approval.sync(repo, MART, say=lambda s: None)] == ["approval_1"]


def test_not_a_repository_does_nothing(tmp_path):
    assert auto_approval.sync(tmp_path, MART, say=lambda s: None) == []
    assert not (tmp_path / ".dev").exists()


def test_sync_all_uses_contract_marts(repo):
    pr(repo, "req", contract_files(), start=10, merge=30)
    write(repo, "docs/requirements/_template.contract.json", "{}")
    assert [r["mart"] for r in auto_approval.sync_all(repo, say=lambda s: None)] == [MART]


def test_pending_auto_only_and_loop_commits_it(repo):
    pr(repo, "req", contract_files(), start=10, merge=30)
    git(repo, "checkout", "-q", "-b", "work")
    assert auto_approval.pending_auto_only(repo) is False  # 바뀐 것이 없음
    run_loop.sync_approvals(repo, repo / ".dev", MART)
    assert git(repo, "status", "--porcelain") == ""
    assert "결재 기록" in git(repo, "log", "-1", "--format=%s")
    assert [r["stage"] for r in records(repo)] == ["approval_1"]


def test_pending_auto_only_refuses_other_changes(repo):
    pr(repo, "req", contract_files(), start=10, merge=30)
    auto_approval.sync(repo, MART, say=lambda s: None)
    assert auto_approval.pending_auto_only(repo) is True
    write(repo, "README.md", "# changed\n")
    assert auto_approval.pending_auto_only(repo) is False
    git(repo, "checkout", "-q", "--", "README.md")
    devlog.append("interventions", {"mart": MART, "kind": "manual_check", "target": "x", "minutes_spent": 1,
                                    "note": ""}, repo / ".dev")
    assert auto_approval.pending_auto_only(repo) is False  # 사람 기록이 섞이면 루프가 대신 커밋하지 않는다




def test_preview_all_shows_without_writing(repo):
    """대시보드용: 기록되지 않은 결재를 머지 시각으로 돌려주고 파일은 쓰지 않는다 (결정 71, 결정 80 ⑤)."""
    m1 = pr(repo, "req", contract_files(), start=10, merge=30)
    shown = auto_approval.preview_all(repo)
    assert [(r["stage"], r["target"], r["minutes_spent"], r["ts"]) for r in shown] == [
        ("approval_1", f"PR 머지 {m1[:7]}", 20, at(30))]
    assert not (repo / ".dev").exists() and git(repo, "status", "--porcelain") == ""
    auto_approval.sync(repo, MART, say=lambda s: None)
    assert auto_approval.preview_all(repo) == []  # 기록된 뒤에는 겹쳐 보이지 않는다


def test_dashboard_command_leaves_tree_clean(repo, tmp_path):
    """결재 2 뒤 main에서 대시보드를 만들어도 작업 트리가 더러워지지 않는다 (다음 브랜치·pull이 막히지 않게)."""
    import dashboard  # noqa: E402  (scripts/metrics)
    pr(repo, "req", contract_files(), start=10, merge=30)
    pr(repo, "build", build_files(), start=40, merge=100)
    out = tmp_path / "out" / "dashboard.html"
    assert dashboard.main(["--root", str(repo), "--out", str(out)]) == 0
    assert git(repo, "status", "--porcelain") == "" and out.exists()
