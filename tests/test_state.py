"""scripts/loop/state.py 시험 (3-5 설계 12-1 T4, T6·T7 계산 부분, T13 번호·이어 세기 부분)."""
import json
from pathlib import Path

import pytest

from loop_fixture import MART, approval, commit_all, git, make_repo, write_result

import state  # noqa: E402  (loop_fixture가 sys.path를 맞춘다)


def counts(dev, interventions=(), version=1, mart=MART):
    iters = state.iterations(state.load_results(dev, mart, version))
    return state.counts(iters, list(interventions), mart, version), iters


# ---------- T6: 판정 반복 수 ----------

def test_five_judged_reaches_limit(tmp_path):
    pairs = [("stg_example", "duplicate_rows"), ("mart_example_daily", "range_violation")]
    for n in range(1, 6):
        task, et = pairs[n % 2]
        write_result(tmp_path, task, n, "reject", n, et)
    c, _ = counts(tmp_path)
    assert (c.judged, c.limit, c.max_reached) == (5, 5, True)


def test_halt_iterations_not_counted(tmp_path):
    write_result(tmp_path, "raw_example", 1, "reject", 1, "syntax")
    write_result(tmp_path, "raw_example", 2, "halt", 2, halt_reason="infra_error")
    write_result(tmp_path, "raw_example", 3, "halt", 3, halt_reason="timeout")
    write_result(tmp_path, "raw_example", 4, "pass", 4)
    write_result(tmp_path, "stg_example", 4, "pass", 4)
    c, iters = counts(tmp_path)
    assert [it.verdict for it in iters] == ["reject", "halt", "halt", "pass"]
    assert c.judged == 2 and not c.max_reached


def test_iteration_with_pass_files_then_reject_is_reject(tmp_path):
    write_result(tmp_path, "raw_example", 1, "pass", 1)
    write_result(tmp_path, "stg_example", 1, "reject", 2, "duplicate_rows")
    _, iters = counts(tmp_path)
    assert len(iters) == 1 and iters[0].key == ("stg_example", "duplicate_rows")


def test_other_version_not_counted(tmp_path):
    for n in range(1, 6):
        write_result(tmp_path, "raw_example", n, "reject", n, "syntax", version=1)
    c, _ = counts(tmp_path, version=2)
    assert c.judged == 0


# ---------- T7: 같은 (task, error_type) 연속 ----------

def test_three_same_pairs(tmp_path):
    for n in range(1, 4):
        write_result(tmp_path, "stg_example", n, "reject", n, "duplicate_rows")
    c, _ = counts(tmp_path)
    assert c.streak_key == ("stg_example", "duplicate_rows") and c.streak == 3 and c.same_type_reached


def test_same_error_type_other_task_is_progress(tmp_path):
    write_result(tmp_path, "raw_example", 1, "reject", 1, "duplicate_rows")
    write_result(tmp_path, "stg_example", 2, "reject", 2, "duplicate_rows")
    write_result(tmp_path, "stg_example", 3, "reject", 3, "duplicate_rows")
    c, _ = counts(tmp_path)
    assert c.streak == 2 and not c.same_type_reached


def test_halt_between_keeps_streak(tmp_path):
    write_result(tmp_path, "stg_example", 1, "reject", 1, "duplicate_rows")
    write_result(tmp_path, "stg_example", 2, "halt", 2, halt_reason="infra_error")
    write_result(tmp_path, "stg_example", 3, "reject", 3, "duplicate_rows")
    write_result(tmp_path, "raw_example", 4, "halt", 4, halt_reason="timeout")
    write_result(tmp_path, "stg_example", 5, "reject", 5, "duplicate_rows")
    c, _ = counts(tmp_path)
    assert c.streak == 3 and c.judged == 3


def test_pass_resets_streak(tmp_path):
    write_result(tmp_path, "stg_example", 1, "reject", 1, "duplicate_rows")
    write_result(tmp_path, "stg_example", 2, "reject", 2, "duplicate_rows")
    write_result(tmp_path, "stg_example", 3, "pass", 3)
    c, _ = counts(tmp_path)
    assert (c.streak_key, c.streak) == (None, 0)


# ---------- 연장·연속 초기화 (같은 마트·같은 contract 버전만) ----------

def test_extension_raises_limit_same_mart_version_only(tmp_path):
    for n in range(1, 6):
        write_result(tmp_path, "raw_example", n, "reject", n, ["syntax", "type_mismatch"][n % 2])
    ext = [approval("loop_extension", 10, extra_iterations=2),
           approval("loop_extension", 11, mart="mart_other", extra_iterations=5),
           approval("loop_extension", 12, version=2, extra_iterations=5)]
    c, _ = counts(tmp_path, ext)
    assert c.limit == 7 and not c.max_reached
    assert c.extension_from == ext[0]["ts"]


def test_extension_marks_later_judged_iterations(tmp_path):
    for n in range(1, 6):
        write_result(tmp_path, "raw_example", n, "reject", n, ["syntax", "type_mismatch"][n % 2])
    write_result(tmp_path, "raw_example", 6, "halt", 6, halt_reason="max_iterations")
    write_result(tmp_path, "raw_example", 7, "pass", 20)
    c, iters = counts(tmp_path, [approval("loop_extension", 10, extra_iterations=2)])
    assert [it.n for it in iters if state.is_extension(it, c)] == [7]


def test_streak_reset_cuts_only_that_pair(tmp_path):
    for n in range(1, 4):
        write_result(tmp_path, "stg_example", n, "reject", n, "duplicate_rows")
    write_result(tmp_path, "stg_example", 4, "halt", 4, halt_reason="same_type_3x")
    reset = approval("loop_streak_reset", 10, streak_key="stg_example:duplicate_rows")
    other = approval("loop_streak_reset", 11, streak_key="raw_example:syntax")
    c, _ = counts(tmp_path, [reset, other])
    assert c.streak == 0 and c.judged == 3 and c.limit == 5
    write_result(tmp_path, "stg_example", 5, "reject", 20, "duplicate_rows")
    c, _ = counts(tmp_path, [reset])
    assert c.streak == 1


def test_streak_reset_of_other_version_ignored(tmp_path):
    for n in range(1, 4):
        write_result(tmp_path, "stg_example", n, "reject", n, "duplicate_rows")
    c, _ = counts(tmp_path, [approval("loop_streak_reset", 10, version=2, streak_key="stg_example:duplicate_rows")])
    assert c.streak == 3


# ---------- T13: 번호와 이어 세기 ----------

def test_next_iteration_continues_after_halts(tmp_path):
    assert state.next_iteration(state.load_results(tmp_path, MART, 1)) == 1
    write_result(tmp_path, "raw_example", 1, "reject", 1, "syntax")
    write_result(tmp_path, "raw_example", 2, "halt", 2, halt_reason="timeout")
    assert state.next_iteration(state.load_results(tmp_path, MART, 1)) == 3
    assert state.next_iteration(state.load_results(tmp_path, MART, 2)) == 1


def test_restart_keeps_counting(tmp_path):
    write_result(tmp_path, "stg_example", 1, "reject", 1, "duplicate_rows")
    write_result(tmp_path, "stg_example", 2, "reject", 2, "duplicate_rows")
    write_result(tmp_path, "stg_example", 3, "halt", 3, halt_reason="infra_error")
    c, _ = counts(tmp_path)
    assert (c.judged, c.streak) == (2, 2)


# ---------- iteration 0 커밋 ----------

def test_iteration0_commit_found_by_trailer(tmp_path):
    root, _ = make_repo(tmp_path)
    assert state.iteration0_commits(root, MART, 1) == []
    (root / "a.txt").write_text("a", encoding="utf-8")
    sha = commit_all(root, f"loop: iteration 0\n\nLoop-Iteration-0: {MART} v1")
    assert state.iteration0_commits(root, MART, 1) == [sha]
    assert state.iteration0_commits(root, MART, 2) == []
    assert state.iteration0_commits(root, MART + "x", 1) == []


# ---------- T4: 변경 검사 순서 ----------

@pytest.fixture
def iter0(tmp_path):
    root, _ = make_repo(tmp_path)
    dev = root / ".dev"
    state.write_hash_file(root, dev, MART, 1)
    sha = commit_all(root, f"loop: iteration 0\n\nLoop-Iteration-0: {MART} v1")
    # 루프가 쓴 커밋 전 로그는 이미 "바뀐 파일"이다
    (dev / "rejections.jsonl").write_text('{"id": "R-0001"}\n', encoding="utf-8")
    return root, dev, sha


def check(root, dev, sha, before, head_before):
    return state.check_changes(root, dev, MART, 1, before, head_before, sha)


def test_builder_paths_pass(iter0):
    root, dev, sha = iter0
    before, h = state.snapshot(root), state.head(root)
    (root / "dags" / "sql" / "stg" / "stg_example.sql").write_text("SELECT 2\n", encoding="utf-8")
    (root / "dags" / "sql" / "mart" / "new_task.sql").write_text("SELECT 3\n", encoding="utf-8")
    (dev / "progress.md").write_text("# 진행 기록\n", encoding="utf-8")
    assert check(root, dev, sha, before, h) is None


def test_hash_file_edit_stops_at_step_1(iter0):
    root, dev, sha = iter0
    before, h = state.snapshot(root), state.head(root)
    state.hash_file(dev, MART, 1).write_text("{}\n", encoding="utf-8")
    step, message = check(root, dev, sha, before, h)
    assert step == "1" and "checks_hash" in message


def test_new_checks_file_stops_at_step_1(iter0):
    root, dev, sha = iter0
    before, h = state.snapshot(root), state.head(root)
    (root / "docs" / "requirements" / f"{MART}_checks" / "l3" / "C-99.sql").write_text("SELECT 1\n", encoding="utf-8")
    step, message = check(root, dev, sha, before, h)
    assert step == "1" and "C-99.sql" in message


def test_loop_log_rewritten_by_builder_stops_at_step_1(iter0):
    root, dev, sha = iter0
    before, h = state.snapshot(root), state.head(root)
    (dev / "rejections.jsonl").write_text("", encoding="utf-8")
    assert check(root, dev, sha, before, h)[0] == "1"


def test_committed_checks_change_stops_at_step_2(iter0):
    # 재시작 (a)에서 _checks 변경이 builder 변경분과 함께 커밋된 경우
    root, dev, sha = iter0
    f = root / "docs" / "requirements" / f"{MART}_checks" / "l4" / "C-02.sql"
    f.write_text(f.read_text(encoding="utf-8").replace("WHERE FALSE", "WHERE 1 = 0"), encoding="utf-8")
    commit_all(root, "restart (a)")
    before, h = state.snapshot(root), state.head(root)
    step, message = check(root, dev, sha, before, h)
    assert step == "2" and "C-02.sql" in message


def test_committed_hash_file_change_stops_at_step_3(iter0):
    root, dev, sha = iter0
    path = state.hash_file(dev, MART, 1)
    data = json.loads(path.read_text(encoding="utf-8"))
    data[next(iter(data))] = "0" * 64
    path.write_text(json.dumps(data), encoding="utf-8")
    commit_all(root, "restart (a)")
    before, h = state.snapshot(root), state.head(root)
    assert check(root, dev, sha, before, h)[0] == "3"


def test_head_moved_stops_at_step_0(iter0):
    root, dev, sha = iter0
    before, h = state.snapshot(root), state.head(root)
    state.hash_file(dev, MART, 1).write_text("{}\n", encoding="utf-8")  # ①에도 걸리지만 0번이 먼저
    (root / "b.txt").write_text("b", encoding="utf-8")
    git(root, "add", "b.txt")
    git(root, "commit", "-q", "-m", "builder commit")
    assert check(root, dev, sha, before, h)[0] == "0"


HB_LINE = '{"id": "B-0001", "hook": "check_write", "reason": "builder_write_checks"}\n'


@pytest.fixture
def iter0_hb(iter0):
    """커밋된 hook_blocks.jsonl 1줄이 있는 iteration 0 상태."""
    root, dev, sha = iter0
    (dev / "hook_blocks.jsonl").write_text(HB_LINE, encoding="utf-8", newline="\n")
    commit_all(root, "hook_blocks")
    return root, dev, sha


def check_hb(root, dev, sha, before, head_before):
    hb = state.file_bytes(root, state.HOOK_BLOCKS) or b""
    return lambda: state.check_changes(root, dev, MART, 1, before, head_before, sha, hook_blocks_before=hb)


def test_hook_blocks_append_allowed(iter0_hb):
    # builder 세션의 Hook이 차단 1줄을 더한 경우 (결정 63 ⑤ 11/2 보완)
    root, dev, sha = iter0_hb
    head_before, before = state.status(root)
    run = check_hb(root, dev, sha, before, head_before)
    with (dev / "hook_blocks.jsonl").open("a", encoding="utf-8", newline="\n") as f:
        f.write('{"id": "B-0002", "hook": "check_bash", "reason": "git_push"}\n')
    assert run() is None


def test_hook_blocks_new_file_allowed(iter0):
    root, dev, sha = iter0
    head_before, before = state.status(root)
    run = check_hb(root, dev, sha, before, head_before)
    (dev / "hook_blocks.jsonl").write_text(HB_LINE, encoding="utf-8", newline="\n")
    assert run() is None


def test_hook_blocks_line_changed_halts(iter0_hb):
    root, dev, sha = iter0_hb
    head_before, before = state.status(root)
    run = check_hb(root, dev, sha, before, head_before)
    (dev / "hook_blocks.jsonl").write_text(HB_LINE.replace("B-0001", "B-0009") + HB_LINE, encoding="utf-8",
                                           newline="\n")
    step, message = run()
    assert step == "1" and "hook_blocks.jsonl" in message


def test_hook_blocks_line_deleted_halts(iter0_hb):
    root, dev, sha = iter0_hb
    head_before, before = state.status(root)
    run = check_hb(root, dev, sha, before, head_before)
    (dev / "hook_blocks.jsonl").write_text("", encoding="utf-8")
    assert run()[0] == "1"
    (dev / "hook_blocks.jsonl").unlink()
    assert run()[0] == "1"


def test_hook_blocks_exception_only_for_that_file(iter0_hb):
    root, dev, sha = iter0_hb
    head_before, before = state.status(root)
    run = check_hb(root, dev, sha, before, head_before)
    (dev / "interventions.jsonl").write_text('{"id": "H-0001"}\n', encoding="utf-8")  # 다른 jsonl은 줄 추가도 밖
    step, message = run()
    assert step == "1" and "interventions.jsonl" in message


def test_hook_blocks_strict_without_before_bytes(iter0_hb):
    root, dev, sha = iter0_hb
    head_before, before = state.status(root)
    with (dev / "hook_blocks.jsonl").open("a", encoding="utf-8", newline="\n") as f:
        f.write(HB_LINE)
    assert state.check_changes(root, dev, MART, 1, before, head_before, sha)[0] == "1"


def test_appended_only():
    assert state.appended_only(b"a\n", b"a\nb\n") and state.appended_only(b"", b"a\n")
    assert not state.appended_only(b"a\n", b"a\n") and not state.appended_only(b"a\n", None)
    assert not state.appended_only(b"a", b"ab\n")  # 마지막 줄을 이어 쓴 것은 기존 줄 수정
    assert not state.appended_only(b"a\nb\n", b"a\nc\nd\n")




def test_verifier_allowed_paths():
    allowed = state.verifier_allowed(MART)
    ok = [f"docs/requirements/{MART}_checks/l3/C-01.sql", f"docs/requirements/{MART}_checks/l5/I-02.sql",
          ".dev/progress.md"]
    bad = [f"docs/requirements/{MART}_checks/l2/C-01.sql", f"docs/requirements/{MART}.contract.json",
           "dags/sql/dq/gate.sql", "dags/sql/stg/x.sql"]
    assert state.outside(ok + bad, allowed) == bad


# ---------- progress.md ----------

TASKS = [{"id": "raw_example", "layer": "raw"}, {"id": "stg_example", "layer": "stg"}]


def test_progress_created_and_table_redrawn(tmp_path):
    write_result(tmp_path, "raw_example", 1, "pass", 1)
    write_result(tmp_path, "stg_example", 1, "reject", 1, "duplicate_rows")
    c, iters = counts(tmp_path)
    rej = [{"id": "R-0001", "mart": MART, "task": "stg_example", "contract_version": 1, "caught_by_rung": "L4",
            "error_type": "duplicate_rows"}]
    section = state.progress_section(TASKS, state.load_results(tmp_path, MART, 1), rej, iters, c, MART, 1)
    text = state.render_progress(None, MART, section)
    assert text.startswith(f"# 진행 기록\n\n## 요구서 — {MART}\n")
    assert "마트 실행 반복 1/5, 연속 (stg_example, duplicate_rows) 1/3" in text
    assert "| 1 | raw_example (raw) | 통과 | 0 | — |" in text
    assert "| 2 | stg_example (stg) | 반려 | 1 | R-0001 (L4 duplicate_rows) |" in text
    kept = text + "- builder 인계\n\n### R-0001 원인\n왜\n무엇\n어떻게\n"
    redrawn = state.render_progress(kept, MART, section.replace("1/5", "2/5"))
    assert "2/5" in redrawn and "- builder 인계" in redrawn and "### R-0001 원인" in redrawn


OTHER_SECTION = ("## 작업 목록 — mart_daily_sales\n\n마트 실행 반복 2/5, 연속 없음 0/3\n\n"
                 "| # | 작업 | 상태 | 반복 | 최근 반려 |\n|---|---|---|---|---|\n"
                 "| 1 | raw_orders (raw) | 통과 | 1 | R-0001 (L3 syntax) |\n\n")
FILE_HEAD = "# 진행 기록\n\n## 요구서 — mart_daily_sales\ndocs/requirements/mart_daily_sales.md\n\n"
FILE_TAIL = "## 직전 반복 인계\n- 마트 1 인계\n\n### 마트 1과 달라진 조건\n표\n\n## 마트 2 메모\n초안\n"


def mart_section(mart, n):
    return f"## 작업 목록 — {mart}\n\n마트 실행 반복 {n}/5\n\n"


def requirement(mart):
    return f"## 요구서 — {mart}\ndocs/requirements/{mart}.md\n\n"


def test_section_heading_names_the_mart(tmp_path):
    c, iters = counts(tmp_path)
    section = state.progress_section(TASKS, [], [], iters, c, MART, 1)
    assert section.startswith(f"## 작업 목록 — {MART}\n\n마트 실행 반복 0/5")
    assert state.progress_marts(state.render_progress(None, MART, section)) == [MART]


def test_new_mart_section_goes_before_handoff_and_changes_nothing_else():
    text = FILE_HEAD + OTHER_SECTION + FILE_TAIL
    mine = "mart_user_returns"
    section = mart_section(mine, 0)
    assert state.render_progress(text, mine, section) == FILE_HEAD + OTHER_SECTION + requirement(mine) + section + FILE_TAIL


def test_new_mart_section_at_end_without_handoff():
    text = FILE_HEAD + OTHER_SECTION
    mine = "mart_user_returns"
    section = mart_section(mine, 0)
    assert state.render_progress(text, mine, section) == text + requirement(mine) + section


def test_existing_requirement_section_is_not_repeated():
    mine = "mart_user_returns"
    text = FILE_HEAD + requirement(mine) + OTHER_SECTION + FILE_TAIL
    section = mart_section(mine, 0)
    assert state.render_progress(text, mine, section) == FILE_HEAD + requirement(mine) + OTHER_SECTION + section + FILE_TAIL


def test_new_file_has_common_title_and_named_requirement():
    text = state.render_progress(None, MART, mart_section(MART, 0))
    assert text == f"# 진행 기록\n\n{requirement(MART)}{mart_section(MART, 0)}## 직전 반복 인계\n"


@pytest.mark.parametrize("before, after", [
    (OTHER_SECTION, ""),            # 고칠 절이 다른 마트 절 뒤
    ("", OTHER_SECTION),            # 고칠 절이 다른 마트 절 앞
])
def test_redraw_keeps_other_mart_section_exact(before, after):
    mine = "mart_user_returns"
    text = FILE_HEAD + before + mart_section(mine, 1) + after + FILE_TAIL
    redrawn = state.render_progress(text, mine, mart_section(mine, 2))
    assert redrawn == FILE_HEAD + before + mart_section(mine, 2) + after + FILE_TAIL


def test_redraw_own_section_last_in_file():
    mine = "mart_user_returns"
    text = FILE_HEAD + OTHER_SECTION + mart_section(mine, 1)
    assert state.render_progress(text, mine, mart_section(mine, 2)) == FILE_HEAD + OTHER_SECTION + mart_section(mine, 2)


def test_mart_name_that_is_prefix_of_another_is_separate():
    text = FILE_HEAD + OTHER_SECTION + FILE_TAIL
    section = mart_section("mart_daily", 1)
    redrawn = state.render_progress(text, "mart_daily", section)
    assert redrawn == FILE_HEAD + OTHER_SECTION + requirement("mart_daily") + section + FILE_TAIL
    assert state.progress_marts(redrawn) == ["mart_daily_sales", "mart_daily"]


def test_old_heading_without_mart_is_left_alone():
    old = "## 작업 목록\n\n마트 실행 반복 2/5\n\n"
    section = mart_section(MART, 1)
    redrawn = state.render_progress(FILE_HEAD + old + FILE_TAIL, MART, section)
    assert redrawn == FILE_HEAD + old + requirement(MART) + section + FILE_TAIL
    assert state.progress_marts(old) == []


def test_handoff_keeps_mart_sections():
    text = FILE_HEAD + OTHER_SECTION + mart_section(MART, 1) + FILE_TAIL
    out = state.append_handoff(text, MART, "iteration 1: 신호 없음")
    assert out.startswith(FILE_HEAD + OTHER_SECTION + mart_section(MART, 1))
    assert f"- [루프 {MART}] iteration 1: 신호 없음\n\n## 마트 2 메모\n초안\n" in out


def test_handoff_keeps_old_loop_lines():
    text = "## 직전 반복 인계\n- [루프] iteration 3: 사다리 통과\n"
    out = state.append_handoff(text, "mart_user_returns", "iteration 1: 신호 없음")
    assert out == text + "- [루프 mart_user_returns] iteration 1: 신호 없음\n"


def test_append_handoff_and_three_lines():
    text = state.render_progress(None, MART, f"## 작업 목록 — {MART}\n\n")
    text = state.append_handoff(text, MART, "iteration 2: 신호 없음")
    assert text.rstrip().endswith(f"- [루프 {MART}] iteration 2: 신호 없음")
    assert not state.has_three_lines(text, "R-0002")
    assert not state.has_three_lines(text + "\n### R-0002 원인\n왜\n무엇\n", "R-0002")
    assert state.has_three_lines(text + "\n### R-0002 원인\n왜\n무엇\n어떻게\n", "R-0002")
