"""키트 사용 편의 공용 함수: 로컬 설정(.kit_local.json) 적용과 --mart 자동 선택.

- .kit_local.json: scripts/setup/kit_setup.py가 저장소 루트에 쓴다(커밋하지 않음, .gitignore). 칸은
  project(GCP 프로젝트 ID), cloudsdk_config(전용 gcloud 설정 폴더), github(선택)
- apply_env: 환경변수 CLOUDSDK_CONFIG가 없고 .kit_local.json에 경로가 있으면 os.environ에 넣는다. 이미 있으면 덮어쓰지
  않는다. 인증 확인(common.Bq.check_auth: ai-builder인지)은 그대로 각 진입점이 한다
- pick_mart: --mart를 안 주면 docs/requirements/*.contract.json(_template 제외)이 정확히 1개일 때 그 마트를 쓴다.
  0개나 2개 이상이면 None(부르는 쪽이 종료 코드 2)
"""
import json
import os
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
KIT_LOCAL = ".kit_local.json"
ENV_NAME = "CLOUDSDK_CONFIG"


def read_local(root=PROJECT):
    """.kit_local.json 내용. 없거나 읽지 못하면 빈 사전."""
    try:
        data = json.loads((Path(root) / KIT_LOCAL).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def apply_env(root=PROJECT, environ=None):
    """CLOUDSDK_CONFIG가 없으면 .kit_local.json의 경로를 넣고 그 값을 돌려준다. 넣지 않았으면 None."""
    environ = os.environ if environ is None else environ
    if environ.get(ENV_NAME):
        return None
    value = read_local(root).get("cloudsdk_config")
    if not isinstance(value, str) or not value.strip():
        return None
    environ[ENV_NAME] = value
    return value


def contract_marts(root=PROJECT):
    folder = Path(root) / "docs" / "requirements"
    suffix = ".contract.json"
    return sorted(p.name[:-len(suffix)] for p in folder.glob(f"*{suffix}") if not p.name.startswith("_template"))


def pick_mart(root, given, out=None, err=None):
    """--mart 값. 주지 않았으면 contract가 1개일 때 그 마트. 고르지 못하면 이유를 출력하고 None."""
    if given:
        return given
    out, err = out or sys.stdout, err or sys.stderr
    names = contract_marts(root)
    if len(names) == 1:
        print(f"마트: {names[0]} (자동 선택)", file=out, flush=True)
        return names[0]
    listed = ", ".join(names) if names else "없음"
    print(f"마트를 고르지 못함: contract가 {len(names)}개다 (목록: {listed}). --mart <마트>를 준다", file=err, flush=True)
    return None
