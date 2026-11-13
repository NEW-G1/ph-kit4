"""원천·운영 데이터셋 설정 읽기 (진행표 4-16, 결정 73). 표준 라이브러리만 쓴다.

- 설정은 dags/harness_config.json 하나다. dags/ 폴더만 서버로 배포되므로 DAG도 같은 파일을 읽는다
- 설정 변경은 하네스 PR로 사람이 결재한다. 경로를 환경변수로 바꾸는 기능은 일부러 없다(우회 통로가 된다)
- 형식이 틀리면 기본값으로 넘어가지 않고 ConfigError로 멈춘다. 사다리에서는 common.config()가
  InputInvalid(halt input_invalid)로 바꾼다. 사람 파일 문제라 반려로 세지 않는다 (결정 59)
- 개발 데이터셋 ai_dev는 설정에 넣지 않는다. 설정으로 쓰기 허용 대상을 바꿀 수 없게 하려는 것이다.
  .claude/hooks/check_bash.py는 이 설정을 읽지 않고 ai_dev 밖 쓰기를 막는다
- retired_datasets: 예전 운영 데이터셋 이름. 과거 기록의 프로젝트 ID를 계속 가리고 SQL 하드코딩도 계속 막는다
"""
import functools
import json
import re
from pathlib import Path

PATH = Path(__file__).resolve().parents[2] / "dags" / "harness_config.json"
SCHEMA_VERSION = 1
DEV_DATASET = "ai_dev"
LAYERS = ("raw", "stg", "mart")
TOP_KEYS = {"schema_version", "source", "datasets", "retired_datasets", "om"}
DATASET = re.compile(r"[a-z][a-z0-9_]*")
PROJECT = re.compile(r"[a-z][a-z0-9-]*")
LOCATION = re.compile(r"[A-Za-z][A-Za-z0-9-]*")
SERVICE = re.compile(r"[A-Za-z][A-Za-z0-9_-]*")


class ConfigError(ValueError):
    """설정 파일을 읽지 못했거나 형식이 틀렸다."""


def section(data, key, keys):
    value = data.get(key)
    if not isinstance(value, dict) or set(value) != set(keys):
        raise ConfigError(f"{key}의 키는 {sorted(keys)}여야 함")
    return value


def match(pattern, value, where):
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise ConfigError(f"{where} 형식이 틀림: {value!r}")


def validate(data):
    if not isinstance(data, dict) or set(data) != TOP_KEYS:
        raise ConfigError(f"최상위 키는 {sorted(TOP_KEYS)}여야 함")
    if data["schema_version"] != SCHEMA_VERSION:
        raise ConfigError(f"schema_version은 {SCHEMA_VERSION}이어야 함")
    source = section(data, "source", ("project", "dataset", "location"))
    match(PROJECT, source["project"], "source.project")
    match(DATASET, source["dataset"], "source.dataset")
    match(LOCATION, source["location"], "source.location")
    datasets = section(data, "datasets", LAYERS)
    retired = data["retired_datasets"]
    if not isinstance(retired, list):
        raise ConfigError("retired_datasets는 목록이어야 함")
    names = [datasets[k] for k in LAYERS] + retired
    for name in names:
        match(DATASET, name, "데이터셋 이름")
    if len(set(names)) != len(names):
        raise ConfigError("운영·예전 데이터셋 이름이 겹침")
    if DEV_DATASET in names or source["dataset"] in names or source["dataset"] == DEV_DATASET:
        raise ConfigError(f"원천·운영 데이터셋 이름은 서로 다르고 {DEV_DATASET}와 달라야 함")
    match(SERVICE, section(data, "om", ("service",))["service"], "om.service")
    return data


@functools.lru_cache(maxsize=1)
def load():
    """형식을 검사한 설정 사전. 한 번 읽으면 캐시한다."""
    try:
        data = json.loads(PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise ConfigError(f"{PATH.name}을 읽지 못함: {e.__class__.__name__}") from None
    return validate(data)


def source_prefix():
    source = load()["source"]
    return f"{source['project']}.{source['dataset']}"


def source_dataset():
    return load()["source"]["dataset"]


def source_pattern():
    """contract sources 한 항목의 형식 (<원천 프로젝트>.<원천 데이터셋>.<테이블>)."""
    return re.compile(re.escape(source_prefix()) + r"\.[a-z][a-z0-9_]*")


def datasets():
    """{층: 운영 데이터셋}."""
    return load()["datasets"]


def om_service():
    return load()["om"]["service"]


def prod_names():
    """운영 데이터셋과 예전 운영 데이터셋 이름."""
    config = load()
    return [config["datasets"][k] for k in LAYERS] + config["retired_datasets"]


def prod_pattern():
    """SQL에 있으면 안 되는 운영 데이터셋 이름."""
    return re.compile(r"\b(?:" + "|".join(map(re.escape, prod_names())) + r")\b", re.I)


def project_ref_pattern():
    """문장 속 프로젝트 ID(`proj:dataset.`·`proj.dataset.`). 개발·운영·예전 데이터셋 앞만 본다."""
    names = "|".join(map(re.escape, [DEV_DATASET, *prod_names()]))
    return re.compile(r"\b[a-z][a-z0-9-]{3,}[:.](?=(?:" + names + r")\b)")
