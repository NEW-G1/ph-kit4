"""키트 설정 한 번에 하기. 사람이 자기 창에서 한 번 실행한다(Windows PowerShell·Linux 같음).

  python scripts/setup/kit_setup.py [--project <프로젝트 ID>] [--github <아이디>] [--config-dir <폴더>]

하는 일 (차례대로)
1. 프로젝트 ID를 묻는다(--project로도 받음). GitHub 아이디는 선택으로 묻는다(--github, 빈 값이면 건너뜀)
2. 전용 gcloud 설정 폴더(기본 ~/.gcp/ai-builder-kit-config)를 만들고 그 설정(CLOUDSDK_CONFIG)으로
   gcloud config set project, gcloud config set auth/impersonate_service_account ai-builder@<프로젝트>.iam.gserviceaccount.com
3. 그 설정에 활성 계정이 없으면 gcloud auth login(사람이 브라우저에서 로그인). 키 파일은 만들지 않는다
4. .claude/settings.local.json의 env 칸에 CLOUDSDK_CONFIG를 합친다(다른 칸·다른 env 값은 그대로)
5. 저장소 루트 .kit_local.json(project, cloudsdk_config, github)을 쓰고 .gitignore에 넣는다(커밋하지 않음).
   루프·사다리는 새 창에서 CLOUDSDK_CONFIG가 없으면 이 파일의 경로를 쓴다(kit_local.apply_env)
6. GitHub 아이디를 받았고 원격 origin이 없으면 https://github.com/<아이디>/<폴더 이름>.git으로 연결한다(push 안 함)
7. git core.hooksPath를 .githooks로 둔다: 커밋에 들어가는 contract를 L0로 검사한다(.githooks/pre-commit, 결정 80)
8. 확인: bq로 SELECT SESSION_USER()를 --dry_run 먼저, 본 실행은 --maximum_bytes_billed=524288000으로 돌려 신원을 보여 준다

바깥 명령은 run() 하나로만 실행한다(시험에서 가짜로 바꾼다). 종료 코드: 0 완료(ai-builder 확인), 1 확인 실패, 2 사용 오류
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[1]
sys.path.insert(0, str(HERE))
import kit_local  # noqa: E402

DEFAULT_CONFIG = Path.home() / ".gcp" / "ai-builder-kit-config"
SETTINGS_LOCAL = Path(".claude") / "settings.local.json"
MAX_BYTES = 524288000  # 쿼리당 500 MB (CLAUDE.md §4)
CHECK_SQL = "SELECT SESSION_USER()"
PROJECT_ID = re.compile(r"[a-z][a-z0-9-]{4,28}[a-z0-9]")
GITHUB_ID = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?")


class SetupError(Exception):
    """사용 오류 (종료 코드 2)."""


def run(args, env=None, capture=True):
    """바깥 명령 1개. (종료 코드, 표준 출력, 표준 오류). capture=False면 사람과 바로 주고받는다(로그인)."""
    try:
        p = subprocess.run(args, env=env, capture_output=capture, text=True, encoding="utf-8", errors="replace")
    except OSError as e:
        return 127, "", str(e)
    return p.returncode, p.stdout or "", p.stderr or ""


def find_tool(name):
    """Windows에서는 gcloud.cmd·bq.cmd일 수 있다. 못 찾으면 SetupError."""
    path = shutil.which(name) or shutil.which(f"{name}.cmd")
    if not path:
        raise SetupError(f"{name}을 찾지 못함. Google Cloud SDK를 설치하고 PATH에 넣은 뒤 새 창에서 다시 실행한다")
    return path


def ask(prompt, given, required):
    if given is not None:
        return given.strip()
    try:
        value = input(prompt).strip()
    except EOFError:
        value = ""
    if required and not value:
        raise SetupError("값이 없음")
    return value


def merge_settings(root, config_dir):
    """settings.local.json의 env.CLOUDSDK_CONFIG만 바꾸고 나머지는 그대로 둔다."""
    path = Path(root) / SETTINGS_LOCAL
    data = {}
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            raise SetupError(f"{SETTINGS_LOCAL.as_posix()}를 JSON으로 읽지 못함. 고친 뒤 다시 실행한다") from None
        if not isinstance(data, dict) or not isinstance(data.get("env", {}), dict):
            raise SetupError(f"{SETTINGS_LOCAL.as_posix()}의 형식이 객체가 아님")
    data.setdefault("env", {})[kit_local.ENV_NAME] = str(config_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    return path


def write_local(root, project, config_dir, github):
    path = Path(root) / kit_local.KIT_LOCAL
    data = {"project": project, "cloudsdk_config": str(config_dir), "github": github or None}
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    ignore = Path(root) / ".gitignore"
    text = ignore.read_text(encoding="utf-8") if ignore.exists() else ""
    if kit_local.KIT_LOCAL not in text.split():
        sep = "" if not text or text.endswith("\n") else "\n"
        ignore.write_text(f"{text}{sep}\n# 키트 개인 설정 (scripts/setup/kit_setup.py, 커밋 금지)\n{kit_local.KIT_LOCAL}\n",
                          encoding="utf-8", newline="\n")
    return path


def enable_hooks(root, say):
    """커밋 때 contract 형식 검사(.githooks/pre-commit)를 켠다. 저장소 설정(.git/config)만 바꾼다."""
    if not (Path(root) / ".githooks" / "pre-commit").exists():
        return False
    code, _, err = run(["git", "-C", str(root), "config", "core.hooksPath", ".githooks"])
    if code != 0:
        say(f"경고: 커밋 검사를 켜지 못함 ({err.strip()[:200]})")
        return False
    say("커밋 검사: 요구서 contract를 커밋할 때 형식 검사(L0)를 한다")
    return True


def connect_origin(root, github, say):
    code, _, _ = run(["git", "-C", str(root), "remote", "get-url", "origin"])
    if code == 0:
        say("원격 origin이 이미 있어 그대로 둔다")
        return None
    url = f"https://github.com/{github}/{Path(root).resolve().name}.git"
    code, _, err = run(["git", "-C", str(root), "remote", "add", "origin", url])
    if code != 0:
        say(f"경고: 원격 origin을 연결하지 못함 ({err.strip()[:200]})")
        return None
    say(f"원격 origin 연결: {url} (push는 사람이 한다)")
    return url


def gcloud_setup(gcloud, project, env, say):
    service_account = f"ai-builder@{project}.iam.gserviceaccount.com"
    for args in (["config", "set", "project", project],
                 ["config", "set", "auth/impersonate_service_account", service_account]):
        code, _, err = run([gcloud, *args], env)
        if code != 0:
            raise SetupError(f"gcloud {' '.join(args[:3])} 실패: {err.strip()[:200]}")
    code, out, _ = run([gcloud, "auth", "list", "--filter=status:ACTIVE", "--format=value(account)"], env)
    if code == 0 and out.strip():
        say(f"로그인 계정이 이미 있음 (가장 대상 {service_account})")
        return
    say("브라우저에서 사람 계정으로 로그인한다 (키 파일은 만들지 않는다)")
    code, _, _ = run([gcloud, "auth", "login"], env, capture=False)
    if code != 0:
        raise SetupError("gcloud auth login이 끝나지 않음. 다시 실행한다")


def check_identity(bq, project, env, say):
    """--dry_run 먼저, 본 실행은 비용 상한. ai-builder면 True."""
    base = [bq, f"--project_id={project}", "query", "--use_legacy_sql=false", f"--maximum_bytes_billed={MAX_BYTES}"]
    code, _, err = run([*base, "--dry_run", CHECK_SQL], env)
    if code != 0:
        say(f"확인 실패(dry-run): {err.strip()[:300]}")
        return False
    code, out, err = run([*base, "--format=csv", CHECK_SQL], env)
    if code != 0:
        say(f"확인 실패: {err.strip()[:300]}")
        return False
    user = out.strip().splitlines()[-1].strip() if out.strip() else ""
    ok = user.startswith("ai-builder@")
    say(f"BigQuery 신원: {'ai-builder 확인' if ok else '(ai-builder 아님) ' + user}")
    return ok


def parse_args(argv):
    p = argparse.ArgumentParser(description="키트 설정 한 번에 하기 (gcloud 전용 설정, Claude Code env, 원격 연결)")
    p.add_argument("--project", help="GCP 프로젝트 ID (없으면 묻는다)")
    p.add_argument("--github", help="GitHub 아이디 (선택, 없으면 묻는다. 빈 값이면 건너뜀)")
    p.add_argument("--config-dir", type=Path, default=DEFAULT_CONFIG, help=f"전용 gcloud 설정 폴더 (기본 {DEFAULT_CONFIG})")
    p.add_argument("--root", type=Path, default=PROJECT, help="저장소 루트")
    return p.parse_args(argv)


def main(argv=None, say=print):
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    args = parse_args(argv)
    root = args.root
    try:
        project = ask("GCP 프로젝트 ID: ", args.project, required=True)
        if not PROJECT_ID.fullmatch(project):
            raise SetupError("프로젝트 ID 모양이 아님 (소문자로 시작, 소문자·숫자·하이픈 6~30자)")
        github = ask("GitHub 아이디 (없으면 Enter): ", args.github, required=False)
        if github and not GITHUB_ID.fullmatch(github):
            raise SetupError("GitHub 아이디 모양이 아님")
        gcloud, bq = find_tool("gcloud"), find_tool("bq")
        config_dir = args.config_dir.expanduser().resolve()
        config_dir.mkdir(parents=True, exist_ok=True)
        env = dict(os.environ, **{kit_local.ENV_NAME: str(config_dir)})
        say(f"전용 gcloud 설정 폴더: {config_dir}")
        gcloud_setup(gcloud, project, env, say)
        say(f"Claude Code 설정: {merge_settings(root, config_dir)} (env.{kit_local.ENV_NAME})")
        say(f"로컬 설정: {write_local(root, project, config_dir, github)} (.gitignore에 넣음, 커밋하지 않음)")
        if github:
            connect_origin(root, github, say)
        enable_hooks(root, say)
    except SetupError as e:
        print(f"멈춤: {e}", file=sys.stderr)
        return 2
    if not check_identity(bq, project, env, say):
        say("사람 계정에 ai-builder 서비스 계정 토큰 생성자 역할이 있는지 확인한 뒤 다시 실행한다")
        return 1
    say("설정 완료. Claude Code는 새로 켠다(settings.local.json의 env를 읽는다)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
