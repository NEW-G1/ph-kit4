# CLAUDE.md — 프로젝트 지도

## 1. 목적과 결재 라인
AI가 데이터 파이프라인을 납품 산출물까지 짓는 작업 환경이다. **AI가 기안하고, 코드가 검토하고, 사람이 결재한다.**
- 기안 = builder 에이전트 (SQL, DAG task, 컬럼 설명 작성)
- 검토 = 검증 사다리 스크립트 `scripts/ladder/` + verifier 에이전트
- 결재 = 사람 (요구서(PRD)·contract 승인 = 요구서 PR 머지, push·PR·머지, 규칙 승격)

판정과 사실은 코드가, 설명은 AI가, 결정은 사람이 한다.

## 2. 폴더 지도
이 폴더는 확산 키트다. 세부(스크립트 옵션·종료 코드)는 각 스크립트 머리말에 있다. 사람용 안내는 `README.md`와 `docs/kit/START.md`.
스크립트 머리말의 "결정 N", "03 §" 같은 근거 번호는 원본 저장소의 기록이다. 키트에 그 문서가 없어도 멈추지 않고 이 파일과 머리말을 기준으로 한다.
- `docs/` — 사람이 관리하는 기준. 읽기 위주, 수정은 PR로 결재
  - `docs/requirements/` 요구서 = 완료 계약(템플릿 `_template.*`, `<마트>_interview.md`). `<마트>_checks/l3·l4·l5/` = verifier 검사
  - `docs/requirements/<마트>_checks/`는 verifier가 builder보다 먼저 쓴다. builder는 l4·l5를 읽지 못한다
  - `docs/architecture/` 설계 원칙·명명(`design_principles.md`), SQL(`sql_rules.md`), task 설계(`task_design.md`), 개인 식별 컬럼(`pii_columns.md`)
  - `docs/ai/` 위임 기준(`delegation_matrix.md`), AgentGo 카드 형식(`agentgo_card.md`)
  - `docs/templates/` 납품 양식. `docs/templates/unit_test/` 단위테스트 결과서 양식. 정의서·흐름도는 양식 파일 없이 생성기 출력
  - `docs/kit/` 따라 하기 안내(`START.md`), 예시 요청(`example_request.md`), 원천 등록 확인 목록(`source_checklist.md`)
- `.dev/` — AI 기록: `progress.md`, 반려·개입·비용·차단 로그(`*.jsonl`, 처음 기록할 때 생김), `ladder_results/`·`checks_hash/`·`agent_responses/`·`handover/`
- `.claude/` — `agents/`(builder·verifier), `settings.json`(권한 거부·Hook 등록), `loop.settings.json`(루프 전용 거부)
- `.claude/hooks/` — Hook 4종(check_bash 실행 전 차단, check_write 경로 차단, after_edit SQL dry-run·contract L0, on_stop 턴 끝 시험)
- `.claude/rules/` — 작업 규칙. `learned/` = 결재로 승격된 규칙(처음에는 비어 있음)
- `.githooks/pre-commit` — 커밋되는 contract를 L0로 검사(`scripts/setup/kit_setup.py`가 켬)
- `dags/harness_daily.py`, `dags/sql/{raw,stg,mart,dq}/` — 파이프라인. 처음에는 비어 있고 builder가 contract에 맞춰 채운다
- `dags/harness_config.json` — 원천·운영 데이터셋 설정. 변경은 사람 결재
- `scripts/` — `ladder/` 판정, `loop/` 반복 실행, `log/` 기록, `handover/`·`deliverables/`·`cards/` 산출물, `metrics/` 대시보드
  - `setup/kit_setup.py` 키트 설정 한 번(사람이 실행). 진입점은 CLOUDSDK_CONFIG가 없으면 `.kit_local.json` 값을 쓴다
  - `log/auto_approval.py` 결재 1·2를 git 머지 기록에서 자동 기록(run_loop 시작, 바로 커밋). 대시보드는 기록되지 않은 결재를 화면에만 보임
  - `--mart`는 contract가 1개면 생략 가능
- `tests/` — 하네스 스크립트 테스트
- `out/` — 생성된 납품 산출물과 카드 (커밋하지 않음)

## 3. 위임 기준
아래 세 가지를 모두 충족하는 작업만 반복 실행으로 처리한다. 하나라도 아니면 멈추고 사람에게 묻는다.
1. 자동 판정: 사람 없이 성공과 실패를 판정할 수 있다 (dry-run, ASSERT, 테스트)
2. 되돌리기: 실패해도 브랜치 폐기나 git revert로 끝난다
3. 비밀·외부 무관: 토큰, .env, 외부 전송, 권한 변경과 관계없다

## 4. 절대 금지
- 운영 데이터셋(현재 값은 `dags/harness_config.json`의 `datasets`)에 쓰기. 결재 전 쓰기는 `ai_dev` 데이터셋에만 한다
- `ai-builder` 서비스 계정 설정이 아닌 인증으로 `bq`·`gcloud` 실행
- `.env`, 토큰, JWT 읽기·출력·붙여넣기
- `--dry_run` 없이, 또는 `--maximum_bytes_billed`(524288000 = 500 MB 이하) 없이 `bq query` 실행
- SQL에 데이터셋 이름을 직접 쓰기. `{{ dataset_raw }}` 같은 자리 표시를 쓴다 (`docs/architecture/sql_rules.md` §2)
- 결재 전에 Airflow에서 DAG 실행
- 데이터 값을 AgentGo나 외부로 전송. 카드와 산출물에는 메타데이터만 넣는다
- 고객사 실명, 개인정보, 대외비 사용. 결재된 공개·합성 원천만 쓴다(현재 값은 `dags/harness_config.json`의 `source`). 원천 변경은 `dags/harness_config.json` PR로 사람이 결재한다(PR 본문에 `docs/kit/source_checklist.md`를 붙인다)
- `git push`, 권한 변경, 완료 조건 변경. 모두 사람 결재 대상이다

## 5. 완료의 정의
**결재 전 검증 사다리 L0~L5 전 단계 통과 + `.dev/` 로그 기록 + 인수인계 초안(`.dev/handover/<브랜치>.md`) + 작업 브랜치 로컬 커밋**까지가 AI 작업의 완료다. push와 PR 생성은 사람이 한다.
- L0 계약·DAG 구조(contract.json 형식 검사, DAG 파일 문법, task 목록·의존성이 contract와 일치, SQL 파일과 task 1:1, 비율 지표 SAFE_DIVIDE 대조, contract `load`가 incremental이면 SQL 데이터 날짜 조건, 개인 식별 컬럼 차단, 검증 쿼리 머리말 검사), L1 dry-run, L2 `ai_dev` 실행, L3 레이어 게이트, L4 원천 대비 정합성, L5 멱등성
- 사다리를 통과하지 않은 작업을 "완료"라고 보고하지 않는다
- builder는 스스로 완료를 판정하지 않고 verifier에게 넘긴다
- 검증 쿼리(원천 비교, 불변 조건)는 verifier가 요구서와 contract만 보고 builder보다 먼저 작성한다
- 반복 상한(작업당 5회, 같은 유형 반려 3회 연속, 1회 30분)은 루프가 세고 넘으면 멈춰 사람을 부른다. 인프라 오류·권한 막힘은 반려로 세지 않으며, 그때는 고치지 말고 `.dev/progress.md`에 막힌 이유를 쓰고 멈춘다. 상한 연장·연속 수 초기화는 사람이 `run_loop.py --extend`·`--reset-streak`로 결재한다
- 고치려면 contract(grain·컬럼·타입·키·테이블 구성)를 바꿔야 하면 직접 바꾸지 않고 멈춘다: `.dev/progress.md`에 `halt_reason: contract_change`와 이유, 응답 마지막 줄에 `STATUS: contract_change`
- 같은 유형으로 다시 반려되면, 고치기 전에 `.dev/progress.md`의 `### <반려 id> 원인` 아래에 "왜 틀렸나 / 이번엔 무엇을 다르게 하나 / 어떻게 확인했나" 3줄을 먼저 쓴다

## 6. 상황별 참조
- 요구서 인터뷰 → `docs/requirements/_template.md`와 `_template.contract.json`. contract를 저장하면 Hook이 L0로 검사하니 오류가 나오면 그 자리에서 고친다
- 새 마트 요구서를 받으면 → `docs/requirements/<마트>.md`의 "완료 조건" 절을 먼저 읽는다
- SQL 작성 시 → `docs/architecture/sql_rules.md`의 멱등 3문장 패턴과 데이터셋 자리 표시 (`.claude/rules/sql-idempotent.md`는 dags/sql 파일을 Read·Write·Edit할 때 로드됨)
- 지표 계산 시 → contract `interview.metrics`가 기준
- DAG task 추가 시 → `docs/architecture/design_principles.md`의 DAG 공통 설정과 레이어 게이트 배치
- 검증 실패 시 → `.dev/rejections.jsonl`에서 같은 유형의 과거 반려를 먼저 검색(없으면 첫 반려)
- 납품 산출물 생성 시 → `docs/templates/`와 `.claude/rules/deliverables.md` (생성기 `scripts/deliverables/`)
- 마트의 모든 작업이 통과하면 → `.claude/rules/handover.md`에 따라 인수인계 초안 작성 (사실은 `scripts/handover/` 출력 그대로)
- 위임 범위가 애매하면 → `docs/ai/delegation_matrix.md`. 그래도 애매하면 멈추고 질문
- 맥락이 길어지면 → `.dev/progress.md`에 인계를 남기고 새 세션으로 이어간다
- 파일 수정은 Edit 도구로 한다. python heredoc으로 고치면 본문 문장 속 bq·.env·git push 언급을 check_bash가 판단하지 못해 막을 수 있다. 작업 중 확인은 인라인 python 대신 Grep·Read 도구로 한다

## 7. 멈춤 조건
- 문서끼리 다르거나 근거 없이 정해야 하는 것이 있으면 만들기 전에 멈추고 목록과 제안을 보고한다
