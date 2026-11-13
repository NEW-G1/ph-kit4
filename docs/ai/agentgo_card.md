# AgentGo 카드 형식

AgentGo용 카드 파일에 무엇을 넣고 빼는지 정한 문서다. 생성기 `scripts/cards/make_cards.py`가 이 형식을 따르고, 카드를 고치거나 검토할 때 읽는다.

> 확인된 기능 수준 사실 기준 초안이며, 실제 업로드 비교 시험 전이라 형식은 확정 아님.

- 생성기는 `scripts/cards/make_cards.py`다.
- 카드 파일을 만드는 데서 끝난다. 업로드와 외부 전송은 하지 않는다. (결정 29, 결정 78)

## 기본 형식

- 카드 1장 = 테이블 1개. contract 테이블 중 `layer`가 mart인 것만 만든다(raw, stg는 만들지 않음)
- 파일 이름 = 테이블 이름: `out/cards/<마트>/<테이블>.txt`
- 파일 형식은 .txt이고 본문은 md 제목, 표 문법으로 쓴다
- 파일 1개가 검색 1조각이 되도록 길이 상한을 둔다
  - 상수 `MAX_CHARS`, 기본 4000자
  - 넘으면 자르지 않는다. 종료 2와 어느 칸이 긴지 보고하고, 그 실행에서는 카드를 쓰지 않는다
- 테이블, 컬럼 영문 이름은 키워드 검색용으로 본문에 그대로 둔다

## 들어가는 것 (순서대로)

| 칸 | 원천 |
|---|---|
| 제목: 표준 테이블 이름과 한글 별칭 | contract `tables[].name`, `name_ko` |
| 첫머리: 표준 테이블 이름, 한글 별칭, 데이터셋 논리 이름, 카드 생성 시각 | contract, 생성 시각(+09:00) |
| 한 줄 설명 | contract 값으로 만든 문장(마트, 층, 한글 별칭). contract에 테이블 설명 칸이 없어 새로 지어 쓰지 않는다 |
| 한 행의 뜻(grain)과 키 | contract `tables[].grain`, `keys` |
| 컬럼 표(이름·타입·설명) | contract `tables[].columns[]` |
| 지표 정의 | contract `interview.metrics` 중 이 테이블 컬럼에 해당하는 것만 |
| 상류(리니지) | `make_facts.section_flow()`에서 이 테이블의 상류 줄만, 원천은 데이터셋.테이블까지 |
| 담당 task | contract `tables[].task` |
| 갱신 주기 | contract `schedule`, DAG 설정(`dags/harness_daily.py`의 `schedule`) |
| 결재 상태 | 최신 L6가 통과면 "운영 반영·OM 등록 확인(post-<n>)" |
| 인수인계 문서 위치 | `docs/handover/<마트>.md`가 있으면 그 경로, 없으면 `.dev/handover/` 초안 경로를 글자로만 |
| 도장 3줄 | `contract_version`, 생성 시각, 기준 커밋 (결정 64 ⑤) |

OM 표준 이름(FQN, `서비스.데이터베이스.스키마.테이블`)은 지금 넣지 않는다.
- 데이터베이스 자리가 프로젝트 ID이고, contract와 설정에 없다.
- 프로젝트 ID는 카드에 넣지 않는다.

## 넣지 않는 것

- 데이터 값, 행 수, 통계
- 내부 주소, URL(글에 있으면 `<주소>`로 가린다)
- 프로젝트 ID, 계정(`make_facts.scrub()`으로 가린다). 원천의 프로젝트 이름도 뺀다
- 개인정보 컬럼 값
  - `docs/architecture/pii_columns.md`의 컬럼은 이름과 설명까지만 두고 예시 값을 쓰지 않는다
  - 카드에는 예시 값 칸 자체가 없다

원천이 없는 칸은 지어내지 않고 "미작성"으로 적는다. 그리고 `manifest.json`의 `missing_fields`로 센다.

## 갱신 흐름

1. 파이프라인 실행
2. 카드 재생성: `python scripts/cards/make_cards.py --mart <마트>`
3. 사람이 같은 이름으로 다시 올린다

## 도장과 --check

- 카드 끝에 도장 3줄을 찍는다. 이름은 납품 산출물과 같다(`deliv_common.STAMP_LABELS`)
- `python scripts/cards/make_cards.py --mart <마트> --check`는 납품 산출물과 같은 기준으로 판정한다
  - 모든 카드의 도장이 지금 contract version, HEAD와 같으면 0
  - 아니면 2와 `halt input_invalid`
  - mart 테이블의 카드가 없거나 contract에 없는 카드가 있어도 2
- `out/cards/<마트>/manifest.json`에 카드 목록과 글자 수를 남긴다. `out/`은 커밋하지 않는다
