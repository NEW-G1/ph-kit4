# 파이프라인 하네스 확산 키트

AI가 데이터 파이프라인을 기안하고, 코드가 검토하고, 사람이 결재하는 작업 환경의 최소 구성입니다. 다른 팀의 기록과 정답은 들어 있지 않습니다. 처음 쓰는 사람(테스터)은 `docs/kit/START.md` 하나만 위에서부터 따라 하면 됩니다(Windows 기준, 버튼 위치까지 적음). 이 문서는 키트를 나눠 주는 담당자용 개요입니다. 두 문서가 다르게 읽히면 START.md를 따르고 담당자에게 알려 주세요.

## 들어 있는 것

- `CLAUDE.md`, `.claude/`: 프로젝트 지도, 규칙, builder·verifier 에이전트, Hook 4종
- `scripts/`, `tests/`: 검증 사다리, 반복 루프, 기록 도구, 산출물 생성기와 시험
- `docs/architecture/`, `docs/ai/`, `docs/templates/`: 설계·SQL 규칙, 위임 기준, 납품 양식
- `docs/requirements/_template*`: 요구서·contract 빈 양식
- `dags/`: 빈 DAG(`UPSTREAM = {}`), 설정 파일, 빈 SQL 폴더
- `docs/kit/example_request.md`: 첫 시험에 쓰는 요청 문장, `docs/kit/source_checklist.md`: 원천 등록 PR에 붙이는 확인 목록

`CLAUDE.md`와 스크립트 설명이 가리키는 `docs/plan/`, `docs/domain/`, `docs/handover/`, `expertise/`, `docs/templates/standards_survey.md`, `scripts/kit/`는 키트에 없습니다. 필요해지면 팀이 만듭니다.

## 준비물

- Python 3.10 이상, Git, Claude Code, gcloud·bq(Google Cloud SDK)
- 별도 GCP 프로젝트와 그 안의 `ai_dev` 데이터셋. 원천과 같은 리전에, **기본 파티션 만료 없음 + 기본 테이블 만료 7일**로 만듭니다(결정 79). 기본 파티션 만료가 있으면 증분 적재(`load.mode` = `incremental`)의 과거 날짜 파티션이 쓰자마자 지워지고 사다리가 멈춥니다. snapshot 테이블은 DDL에 자체 만료가 있어 영향이 없습니다. 명령 예: ``ALTER SCHEMA `<project-id>.ai_dev` SET OPTIONS (default_partition_expiration_days = NULL, default_table_expiration_days = 7)`` (사람이 실행)
- 서비스 계정 `ai-builder@<project-id>.iam.gserviceaccount.com`: `ai_dev` 쓰기, 원천 읽기, 쿼리 실행 권한만 줍니다
- 결재용 원격 저장소 1개: 루프는 `origin/main`의 contract로만 시작합니다

## 새 팀이 바꿀 곳

| 곳 | 바꿀 내용 |
|---|---|
| `dags/harness_config.json` | 원천과 운영 데이터셋 이름, OM을 쓰면 `om.service`(자리 표시 `om-service`). 변경은 사람이 결재하고, PR 본문에 `docs/kit/source_checklist.md`를 붙입니다 |
| `.kit_local.json`, `.env` | 앞의 것은 `kit_setup.py`가 씁니다(프로젝트 ID, gcloud 설정 폴더, GitHub 아이디). `.env`는 운영 DAG의 `GCP_PROJECT_ID`. 둘 다 커밋하지 않고 AI에게 값을 보여 주지 않습니다 |
| 서비스 계정·데이터셋 | 위 준비물을 팀 프로젝트에 만듭니다 |
| `docs/architecture/pii_columns.md` | 팀 원천의 개인 식별 컬럼 목록. 원천을 바꾸면 표를 새 원천으로 다시 쓰고 `검토한 원천` 줄을 바꿉니다(다르면 L0가 멈춥니다) |

설정을 바꿔 시험할 때는 이 폴더의 사본을 만들고 사본의 `dags/harness_config.json`만 바꾼 뒤 사본에서 `python -m pytest tests/ -q -n auto`를 돌립니다. 원래 폴더의 설정은 결재로만 바꿉니다(`.claude/settings.json`의 deny 규칙이 AI의 수정을 막습니다).

## 지원 범위

- 같은 리전(운영·개발 데이터셋을 원천과 같은 리전에), 단일 원천 데이터셋, 쿼리당 500 MB 이하, 적재 방식은 마트마다 contract `load`로 고름: `snapshot`(기본값, raw가 매일 원천 전체를 복사) 또는 `incremental`(원천 날짜 파티션에서 그 날짜 조각만, 일 단위 지표만)
- 동결 뒤 과제: 증분 적재의 기간 지표(최근 N일·누적)와 운영(backfill·catchup), 여러 원천, 와일드카드 테이블, 운영 비용 상한, 중첩 컬럼의 L6 확인

## 인증

키 파일을 만들지 않고, 사람 계정으로 로그인한 뒤 `ai-builder@<project-id>.iam.gserviceaccount.com`을 가장합니다. 사람 계정에는 `ai-builder`에 대한 서비스 계정 토큰 생성자 역할이 필요합니다. 설정은 `python scripts/setup/kit_setup.py`가 한 번에 합니다: 프로젝트 ID와 GitHub 아이디(선택)를 묻고, 전용 gcloud 설정 폴더(기본 `~/.gcp/ai-builder-kit-config`)에 프로젝트와 가장 대상을 넣고, 로그인이 없으면 브라우저 로그인을 띄우고, `.claude/settings.local.json`의 `env`와 `.kit_local.json`에 그 폴더를 적고, 원격 origin이 없으면 `https://github.com/<아이디>/<폴더 이름>.git`으로 연결하고, 끝에 `SELECT SESSION_USER()`로 `ai-builder`인지 보여 줍니다.

새 창마다 `CLOUDSDK_CONFIG`를 칠 필요가 없습니다. Claude Code는 `settings.local.json`에서, 루프와 사다리는 `.kit_local.json`에서 읽습니다(창에 값이 있으면 그 값). 신원이 `ai-builder`가 아니면 사다리와 루프가 시작하지 않습니다.

## 순서

`--mart`는 마트(contract)가 하나면 생략할 수 있습니다(루프, 흐름도·정의서·결과서·카드 생성기).

1. 설치: `git init`, 첫 커밋 뒤 `python -m pip install -r requirements-dev.txt`
2. 설정: `python scripts/setup/kit_setup.py` 한 번(위 "인증"). Claude Code는 그 뒤에 켭니다
3. 시험: `python -m pytest tests/ -q -n auto`
4. 인터뷰: Claude Code에 `docs/kit/example_request.md`의 요청을 주고 `docs/requirements/_template.md` 기준으로 인터뷰를 요청합니다. AI는 원천을 조회한 근거와 기본안을 보여 주고, 요청자가 답합니다. 결과는 `<마트>.md`, `<마트>.contract.json`, `<마트>_interview.md`입니다
5. contract 결재: 요구서 PR을 사람이 머지합니다. 결재 기록은 루프가 시작할 때 git 머지 기록에서 자동으로 남기고 커밋합니다(결재 1·2, 분 = 머지 시각 - 브랜치 첫 커밋 시각). 대시보드는 아직 기록되지 않은 결재를 머지 기록에서 읽어 화면에만 보입니다
   - 담당자용: 스쿼시 머지처럼 머지 기록이 남지 않아 자동이 안 될 때 손으로 남기는 명령(테스터는 START.md대로 담당자에게 알립니다): `python scripts/log/devlog.py intervention --kind approval --stage approval_1 --mart <마트> --target "요구서 PR 머지" --minutes <분>`
6. 루프: `git pull` 뒤 작업 브랜치를 만들고 사람 창에서 `python scripts/loop/run_loop.py`를 실행합니다. verifier가 검증 쿼리를 먼저 쓰고, builder가 SQL과 DAG를 기안합니다. 증분 마트(contract `load.mode` incremental)는 `--ds YYYY-MM-DD`로 원천에 데이터가 있는 날짜를 줍니다(없으면 오늘 UTC, 멈춘 뒤 다시 실행할 때도 같은 값을 줍니다)
7. L0~L5: 루프가 사다리를 돌립니다. 통과하면 로컬 커밋까지 하고, 멈추면 이유가 `.dev/`에 남습니다. push와 PR은 사람이 하고, 머지하면 대시보드에 결재 2가 완료로 보입니다
8. 결과 확인: `python scripts/metrics/dashboard.py`로 `out/dashboard.html`을 열어 단계별 통과, 반려, 근거 SQL을 보고, `python scripts/deliverables/flow_diagram.py`로 `out/deliverables/<마트>/`의 흐름도(xlsx, .md)를 열어 원천 > raw > stg > mart 흐름을 봅니다(OM이 없으면 "OM 확인" 칸은 "미확인"이 정상). `ai_dev`의 테이블도 BigQuery 콘솔에서 직접 조회합니다

기록은 이 폴더의 `.dev/`에 쌓이고 함께 커밋됩니다. OM 연동, Airflow 실행, L6, 운영 배포는 이 키트의 범위 밖입니다.

## 하지 않는 것

- 서비스 계정 키 파일 만들기
- 운영 데이터셋 쓰기: 결재 전 쓰기는 `ai_dev`에만 합니다
- push 자동화: push, PR, 머지는 사람이 합니다
