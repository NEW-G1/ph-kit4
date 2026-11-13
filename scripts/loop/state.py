"""반복 루프의 상태 계산과 변경 검사 (3-5 설계 3·5절, 결정 63 ②⑤⑫⑬).

- 세기: 판정된 반복(pass·reject) 수와 같은 (task, error_type) 연속 수를 ladder_result·interventions.jsonl에서
  매번 다시 계산한다. 재시작해도 이어서 센다. halt 반복은 끊지도 잇지도 않는다
- 연장(loop_extension)·연속 초기화(loop_streak_reset)는 같은 마트·같은 contract 버전의 결재만 반영한다
- iteration 0 커밋: 커밋 메시지 꼬리 "Loop-Iteration-0: <마트> v<ver>"
- 변경 검사 순서(5절): 0 HEAD 불변 → ① 허용 경로(스냅샷 비교) → ② iteration 0 커밋과 git diff(주 판정) → ③ 해시 파일(보조)
- progress.md의 "작업 목록 — <마트>" 절은 루프가 매번 다시 그린다. 그 마트의 절만 고친다 (03 §4.4, 결정 76)
"""
import hashlib
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / "scripts" / "log"))
import devlog  # noqa: E402

MAX_ITERATIONS = 5
SAME_TYPE_LIMIT = 3
TRAILER = "Loop-Iteration-0: {mart} v{version}"
PROGRESS = ".dev/progress.md"
# Hook(check_bash·check_write)은 CLAUDE_PROJECT_DIR(= 루프의 --root)의 .dev에 차단 기록을 남긴다.
# 기존 줄이 그대로이고 끝에 줄만 더해졌으면 허용한다 (결정 63 ⑤ 11/2 보완)
HOOK_BLOCKS = ".dev/hook_blocks.jsonl"
BUILDER_ALLOWED = (re.compile(r"dags/sql/(raw|stg|mart)/[^/]+\.sql"), re.compile(r"dags/harness_daily\.py"),
                   re.compile(re.escape(PROGRESS)))


def builder_allowed(contract):
    """루프의 builder 허용 경로: 이번 contract의 load task SQL, DAG 파일, progress.md.
    DAG 파일은 마트가 함께 쓰므로 그대로 허용한다(다른 마트 줄은 L0가 잡는다). 다른 마트 SQL은 허용 경로 밖이다."""
    sql = [re.compile(re.escape(f"dags/sql/{t['layer']}/{t['id']}.sql"))
           for t in contract["dag"]["tasks"] if t["kind"] == "load"]
    return (*sql, *BUILDER_ALLOWED[1:])


def verifier_allowed(mart):
    return (re.compile(re.escape(f"docs/requirements/{mart}_checks/") + r"(l3|l4|l5)/[^/]+\.sql"),
            re.compile(re.escape(PROGRESS)))


def protected_paths(mart):
    """iteration 0 커밋과 비교하는 경로 (5절 ②). builder가 고치면 안 되는 입력 파일."""
    return [f"docs/requirements/{mart}_checks/", f"docs/requirements/{mart}.contract.json",
            f"docs/requirements/{mart}.md", "docs/architecture/pii_columns.md", "dags/sql/dq/"]


def builder_paths():
    """통과 커밋·재시작 (a)에서 쓰는 builder 경로."""
    return ["dags/sql/raw", "dags/sql/stg", "dags/sql/mart", "dags/harness_daily.py"]


# ---------- 반복 세기 ----------

def parse_ts(text):
    return datetime.fromisoformat(text)


@dataclass
class Iteration:
    n: int
    verdict: str                       # pass·reject·halt
    ts: str
    files: list = field(default_factory=list)
    task: str | None = None            # reject이면 반려된 task
    error_type: str | None = None
    halt_reason: str | None = None

    @property
    def judged(self):
        return self.verdict in ("pass", "reject")

    @property
    def key(self):
        return (self.task, self.error_type) if self.verdict == "reject" else None


def load_results(dev, mart, version):
    """이 마트·contract 버전의 ladder_result 목록(파일 이름의 iteration 순)."""
    folder = Path(dev) / "ladder_results" / mart
    pattern = re.compile(r"(.+)-v" + str(version) + r"-(\d+)\.json")
    out = []
    for f in sorted(folder.glob(f"*-v{version}-*.json")) if folder.is_dir() else []:
        if not pattern.fullmatch(f.name):
            continue
        data = json.loads(f.read_text(encoding="utf-8"))
        data["_path"] = f
        out.append(data)
    return sorted(out, key=lambda r: (r["iteration"], r["ts"]))


def iterations(results):
    """반복 번호마다 묶는다. 반려 파일이 있으면 reject, halt 파일이 있으면 halt, 모두 pass면 pass."""
    by_n = {}
    for r in results:
        by_n.setdefault(r["iteration"], []).append(r)
    out = []
    for n in sorted(by_n):
        files = by_n[n]
        ts = max(f["ts"] for f in files)
        reject = next((f for f in files if f["verdict"] == "reject"), None)
        halt = next((f for f in files if f["verdict"] == "halt"), None)
        if reject:
            out.append(Iteration(n, "reject", ts, files, reject["task"], reject["rungs"][-1]["error_type"]))
        elif halt:
            out.append(Iteration(n, "halt", ts, files, halt["task"], halt_reason=halt["halt_reason"]))
        else:
            out.append(Iteration(n, "pass", ts, files))
    return out


def next_iteration(results):
    return max((r["iteration"] for r in results), default=0) + 1


def loop_approvals(interventions, mart, version, stage):
    return [r for r in interventions
            if r.get("kind") == "approval" and r.get("stage") == stage and r.get("mart") == mart
            and r.get("contract_version") == version]


@dataclass
class Counts:
    judged: int                        # 판정된 반복 수
    limit: int                         # 5 + 연장 합
    streak_key: tuple | None           # 끝에서 이어지는 같은 (task, error_type)
    streak: int
    extension_from: str | None         # 첫 연장 결재 ts. 이 뒤의 판정 반복이 연장분

    @property
    def max_reached(self):
        return self.judged >= self.limit

    @property
    def same_type_reached(self):
        return self.streak >= SAME_TYPE_LIMIT


def streak_of(iters, resets):
    """끝에서부터 같은 (task, error_type) 반려가 몇 번 이어지는지. 그 쌍의 초기화 결재보다 앞의 반려는 뺀다."""
    judged = [it for it in iters if it.judged]
    if not judged or judged[-1].verdict != "reject":
        return None, 0
    key = judged[-1].key
    cut = max((parse_ts(r["ts"]) for r in resets if r.get("streak_key") == f"{key[0]}:{key[1]}"), default=None)
    count = 0
    for it in reversed(judged):
        if it.key != key or (cut is not None and parse_ts(it.ts) <= cut):
            break
        count += 1
    return key, count


def counts(iters, interventions, mart, version):
    extensions = loop_approvals(interventions, mart, version, "loop_extension")
    resets = loop_approvals(interventions, mart, version, "loop_streak_reset")
    key, n = streak_of(iters, resets)
    first_ext = min((r["ts"] for r in extensions), key=parse_ts, default=None)
    return Counts(sum(1 for it in iters if it.judged), MAX_ITERATIONS + sum(r["extra_iterations"] for r in extensions),
                  key, n, first_ext)


def is_extension(it, c):
    return c.extension_from is not None and it.judged and parse_ts(it.ts) > parse_ts(c.extension_from)


def last_judged_reject(iters):
    return next((it for it in reversed(iters) if it.judged and it.verdict == "reject"), None)


# ---------- git ----------

class GitError(Exception):
    pass


def git(root, *args):
    p = subprocess.run(["git", *args], cwd=root, capture_output=True)
    if p.returncode != 0:
        raise GitError(f"git {' '.join(args)}: {p.stderr.decode('utf-8', 'replace').strip()[:300]}")
    return p.stdout.decode("utf-8", "replace")


def git_ok(root, *args):
    return subprocess.run(["git", *args], cwd=root, capture_output=True).returncode == 0


def head(root):
    return git(root, "rev-parse", "HEAD").strip()


def iteration0_commits(root, mart, version):
    trailer = TRAILER.format(mart=mart, version=version)
    out = git(root, "log", "--format=%H", "-E", f"--grep=^{re.escape(trailer)}$")
    return [line for line in out.split() if line]


# ---------- 스냅샷·변경 검사 ----------

def sha256_file(path):
    """줄바꿈(CRLF/LF)만 맞춘 sha256. 없는 파일은 None."""
    try:
        data = Path(path).read_bytes()
    except (FileNotFoundError, IsADirectoryError):
        return None
    return hashlib.sha256(data.replace(b"\r\n", b"\n")).hexdigest()


def snapshot(root):
    """바뀐 파일 + 미추적 파일의 {경로: sha256}. 무시 파일은 뺀다."""
    return status(root)[1]


# porcelain v2 줄 종류별 경로 앞 칸 수: 1 보통 변경, 2 이름 바꿈·복사(다음 칸이 원래 경로), u 충돌
V2_FIELDS = {"1": 8, "2": 9, "u": 10}


def status(root):
    """(HEAD, {경로: sha256}). git 호출 1번으로 HEAD와 스냅샷을 함께 얻는다 (Windows에서 git 호출이 비싸다)."""
    out = git(root, "status", "--porcelain=v2", "-z", "--branch", "--untracked-files=all")
    entries = out.split("\0")
    head_sha, paths, i = None, [], 0
    while i < len(entries):
        e = entries[i]
        if e.startswith("# branch.oid "):
            head_sha = e.split()[-1]
        elif e[:1] in V2_FIELDS and e[1:2] == " ":
            paths.append(e.split(" ", V2_FIELDS[e[0]])[-1])
            if e[0] == "2":
                i += 1
                paths.append(entries[i])
        elif e.startswith("? "):
            paths.append(e[2:])
        i += 1
    return head_sha, {p: sha256_file(Path(root) / p) for p in paths}


def changed_paths(before, after):
    keys = set(before) | set(after)
    return sorted(k for k in keys if before.get(k, "absent") != after.get(k, "absent"))


def outside(paths, allowed):
    return [p for p in paths if not any(rx.fullmatch(p) for rx in allowed)]


def file_bytes(root, rel):
    """파일 내용. 없으면 None."""
    try:
        return (Path(root) / rel).read_bytes()
    except FileNotFoundError:
        return None


def appended_only(before, after):
    """기존 줄이 그대로이고 끝에 줄만 더해졌나. 없던 파일이 새로 생긴 것도 줄 추가로 본다."""
    before = before or b""
    return after is not None and len(after) > len(before) and after.startswith(before) and \
        (not before or before.endswith(b"\n"))


def disallowed(root, before, after, allowed, hook_blocks_before=None):
    """허용 경로 밖 변경 목록 (5절 ①). hook_blocks_before(호출 전 hook_blocks.jsonl 내용, 없으면 b"")를
    넘기면 그 파일의 줄 추가만은 허용한다. None이면 예외 없이 본다."""
    changed = changed_paths(before, after)
    if hook_blocks_before is not None and HOOK_BLOCKS in changed and \
            appended_only(hook_blocks_before, file_bytes(root, HOOK_BLOCKS)):
        changed.remove(HOOK_BLOCKS)
    return outside(changed, allowed)


def hash_targets(root, mart):
    """해시 파일에 넣는 입력 파일 {저장소 상대 경로: sha256}."""
    root = Path(root)
    files = []
    for rel in protected_paths(mart):
        p = root / rel
        if p.is_dir():
            files += [f for f in p.rglob("*") if f.is_file()]
        elif p.is_file():
            files.append(p)
    return {f.relative_to(root).as_posix(): sha256_file(f) for f in sorted(files)}


def hash_file(dev, mart, version):
    return Path(dev) / "checks_hash" / f"{mart}-v{version}.json"


def write_hash_file(root, dev, mart, version):
    path = hash_file(dev, mart, version)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(hash_targets(root, mart), ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
                    newline="\n")
    return path


def check_changes(root, dev, mart, version, before, head_before, iter0, allowed=BUILDER_ALLOWED,
                  hook_blocks_before=None):
    """builder 호출 뒤 사다리 전 변경 검사(5절). 통과면 None, 아니면 (단계, 메시지)."""
    head_now, after = status(root)
    if head_now != head_before:
        return "0", "HEAD가 바뀌었음 (builder는 커밋하지 않는다)"
    bad = disallowed(root, before, after, allowed, hook_blocks_before)
    if bad:
        return "1", "허용 경로 밖 변경: " + ", ".join(bad[:10])
    if not git_ok(root, "diff", "--quiet", iter0, "--", *protected_paths(mart)):
        out = git(root, "diff", "--name-only", iter0, "--", *protected_paths(mart)).split()
        return "2", f"iteration 0 커밋({iter0[:8]}) 이후 입력 파일이 바뀜: " + ", ".join(out[:10])
    path = hash_file(dev, mart, version)
    try:
        saved = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return "3", f"해시 파일을 읽지 못함: {path.name}"
    now = hash_targets(root, mart)
    if saved != now:
        diff = sorted(k for k in set(saved) | set(now) if saved.get(k) != now.get(k))
        return "3", "해시 파일과 다름: " + ", ".join(diff[:10])
    return None


# ---------- progress.md ----------

STATUS_KO = {"pass": "통과", "reject": "반려", "halt": "멈춤"}
HEADING = "## 작업 목록 — {mart}"
REQUIREMENT = "## 요구서 — {mart}\ndocs/requirements/{mart}.md\n\n"
HEADINGS = re.compile(r"^## 작업 목록 — (\S+)[ \t]*$", re.M)
HANDOFF = re.compile(r"^## 직전 반복 인계[ \t]*$", re.M)


def section_pattern(mart):
    """그 마트의 절. 이름이 앞부분만 같은 다른 마트나 마트 없는 옛 제목 "## 작업 목록"은 잡지 않는다."""
    return re.compile("^" + re.escape(HEADING.format(mart=mart)) + r"[ \t]*$.*?(?=^## |\Z)", re.M | re.S)


def progress_marts(text):
    """progress.md에 작업 목록 절이 있는 마트들 (파일 순서)."""
    return HEADINGS.findall(text or "")


def task_rows(tasks, results, rejections, mart, version):
    rows = []
    for i, t in enumerate(tasks, 1):
        mine = [r for r in results if r["task"] == t["id"]]
        status = STATUS_KO[mine[-1]["verdict"]] if mine else "대기"
        tries = sum(1 for r in mine if r["verdict"] == "reject")
        rej = [r for r in rejections if r.get("mart") == mart and r.get("task") == t["id"]
               and r.get("contract_version") == version]
        last = f"{rej[-1]['id']} ({rej[-1]['caught_by_rung']} {rej[-1]['error_type']})" if rej else "—"
        rows.append(f"| {i} | {t['id']} ({t['layer']}) | {status} | {tries} | {last} |")
    return rows


def progress_section(tasks, results, rejections, iters, c, mart, version, note=None):
    key = f"({c.streak_key[0]}, {c.streak_key[1]})" if c.streak_key else "없음"
    head_line = f"마트 실행 반복 {c.judged}/{c.limit}, 연속 {key} {c.streak}/{SAME_TYPE_LIMIT}"
    lines = [HEADING.format(mart=mart), "", head_line]
    ext = [it.n for it in iters if is_extension(it, c)]
    if c.extension_from:
        lines.append(f"연장분: 연장 결재({c.extension_from}) 뒤의 판정 반복" + (f" {ext}" if ext else " (아직 없음)"))
    if note:
        lines.append(note)
    lines += ["", "| # | 작업 | 상태 | 반복 | 최근 반려 |", "|---|---|---|---|---|"]
    lines += task_rows(tasks, results, rejections, mart, version)
    return "\n".join(lines) + "\n\n"


def render_progress(text, mart, section):
    """progress.md에서 이 마트의 작업 목록 절만 바꾼다. 절이 없으면 "직전 반복 인계" 앞(없으면 끝)에 새로 넣고,
    이 마트의 요구서 절도 없으면 그 앞에 함께 넣는다. 파일이 없으면 03 §4.4 형식으로 만든다.
    다른 마트의 절과 옛 제목의 절은 건드리지 않는다."""
    requirement = REQUIREMENT.format(mart=mart)
    if not text:
        return f"# 진행 기록\n\n{requirement}{section}## 직전 반복 인계\n"
    pattern = section_pattern(mart)
    if pattern.search(text):
        return pattern.sub(lambda m: section, text, count=1)
    has_requirement = re.search("^" + re.escape(requirement.split("\n")[0]) + r"[ \t]*$", text, re.M)
    new = section if has_requirement else requirement + section
    handoff = HANDOFF.search(text)
    if handoff:
        return text[:handoff.start()] + new + text[handoff.start():]
    return text.rstrip("\n") + "\n\n" + new


def append_handoff(text, mart, line):
    """"직전 반복 인계" 절 끝에 루프 기록 1줄("[루프 <마트>]")을 더한다. 절이 없으면 만든다.
    이 절은 마트들이 함께 쓴다. 이미 있는 옛 형식 "[루프]" 줄은 그대로 둔다."""
    if "## 직전 반복 인계" not in text:
        text = text.rstrip("\n") + "\n\n## 직전 반복 인계\n"
    m = re.search(r"^## 직전 반복 인계\s*$.*?(?=^## |\Z)", text, re.M | re.S)
    body = m.group(0).rstrip("\n") + f"\n- [루프 {mart}] {line}\n"
    rest = text[m.end():]
    return text[:m.start()] + body + ("\n" + rest if rest else "")


def three_lines(text, rid):
    """"### <R-id> 원인" 아래 비어 있지 않은 줄 목록. 절이 없으면 [] (결정 49 ④, 대시보드도 쓴다)."""
    m = re.search(r"^###\s*" + re.escape(rid) + r"\s*원인\s*$(.*?)(?=^#{1,3} |\Z)", text or "", re.M | re.S)
    return [line.strip() for line in m.group(1).splitlines() if line.strip()] if m else []


def has_three_lines(text, rid):
    """"### <R-id> 원인" 아래 비어 있지 않은 줄이 3줄 이상인가 (결정 49 ④)."""
    return len(three_lines(text, rid)) >= 3
