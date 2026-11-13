"""시험용 설정 도우미 (결정 73). dags/harness_config.json의 원천·운영 데이터셋 이름을 바꿔도 시험이 깨지지 않게 한다.

- 가짜 데이터(인라인 contract, 가짜 SQL, 가짜 bq 결과)로 만든 시험: 이름을 하드코딩하지 않고 src()·prod()로 지금 설정에서 읽는다
- 우리 실제 마트 파일(mart_*.contract.json, 실제 SQL·기록)을 읽는 시험: 원천이 thelook인 것이 맞으므로 shipped 고정구로
  출하 설정을 고정한다. 하위 프로세스는 실제 dags/harness_config.json을 읽으므로 이 고정이 닿지 않는다
- 결재된 설정 자체의 고정은 test_config_swap.test_shipped_config_is_the_approved_one 하나뿐이다
- 개인 식별 컬럼 차단 시험은 실제 docs/architecture/pii_columns.md가 아니라 시험용 목록(write_pii·pii_list)을 쓴다.
  실제 목록은 원천을 바꾼 키트에서 사람이 다시 쓰므로 시험이 그 행에 기대면 안 된다
  (실제 목록의 고정은 test_l0_contract.test_pii_list 하나뿐이고 키트에서는 뺀다(make_kit.TESTS_CUT))
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "ladder"))
import harness_config as hc  # noqa: E402

def src(table):
    """지금 설정의 원천 테이블 이름 (<원천 프로젝트>.<원천 데이터셋>.<table>)."""
    return f"{hc.source_prefix()}.{table}"


def prod(layer):
    """지금 설정의 운영 데이터셋 이름."""
    return hc.load()["datasets"][layer]


def use(monkeypatch, path):
    """설정 파일 경로를 바꾸고 캐시를 비운다. 끝나면 monkeypatch가 경로를 되돌린다(캐시는 부르는 쪽이 비운다)."""
    monkeypatch.setattr(hc, "PATH", path)
    hc.load.cache_clear()


def pin(tmp_path, monkeypatch, data):
    path = tmp_path / "pinned_harness_config.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    use(monkeypatch, path)
    return path


@pytest.fixture
def shipped(tmp_path, monkeypatch):
    """출하 설정(thelook)을 고정한다. 우리 실제 마트 파일을 읽는 시험에 쓴다.

    SHIPPED는 test_config_swap에 둔다. 이 파일은 키트에 들어가므로 OM 서비스 이름을 쓰지 않는다
    (test_make_kit.test_om_service_name_not_in_kit). 키트에는 이 고정구를 쓰는 시험이 없다(TESTS_LEFT_OUT·TESTS_CUT)
    """
    from test_config_swap import SHIPPED
    pin(tmp_path, monkeypatch, SHIPPED)
    yield SHIPPED
    hc.load.cache_clear()


# 시험용 개인 식별 컬럼 목록. 원천 테이블 이름은 시험 SQL의 raw_<테이블>·src(<테이블>)과 맞춘다
PII_TEST_ROWS = {
    "users": ("first_name", "last_name", "email", "street_address", "postal_code", "latitude", "longitude", "user_geom"),
    "events": ("ip_address",),
}


def write_pii(path):
    """시험용 pii_columns.md를 path에 쓴다. "검토한 원천"은 지금 설정의 원천이다.

    임시 저장소를 만드는 시험(table_spec의 --root 등)은 그 저장소의 docs/architecture/pii_columns.md에 쓴다."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = "".join(f"| `{table}` | `{column}` | 시험용 |\n" for table, columns in PII_TEST_ROWS.items() for column in columns)
    path.write_text(f"# 시험용 개인 식별 컬럼 목록\n\n검토한 원천: `{hc.source_prefix()}`\n\n## 목록\n\n"
                    f"| 원천 테이블 | 컬럼 | 근거 |\n|---|---|---|\n{rows}", encoding="utf-8")
    return path


@pytest.fixture
def pii_list(tmp_path, monkeypatch):
    """같은 프로세스의 l0_contract(run_ladder가 쓰는 모듈)가 기본으로 읽는 목록을 시험용 목록으로 바꾼다.

    load_pii(path=PII_FILE)의 기본값은 정의 때 묶이므로 PII_FILE과 load_pii.__defaults__를 함께 바꾼다.
    하위 프로세스에는 닿지 않는다(그 시험은 임시 저장소에 write_pii로 쓴다). 시험용 목록 경로를 돌려준다"""
    import l0_contract
    path = write_pii(tmp_path / "pii_fixture" / "pii_columns.md")
    monkeypatch.setattr(l0_contract, "PII_FILE", path)
    monkeypatch.setattr(l0_contract.load_pii, "__defaults__", (path,))
    return path
