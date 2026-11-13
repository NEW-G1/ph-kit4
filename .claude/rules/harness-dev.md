---
paths:
  - "tests/**"
  - ".claude/hooks/**"
  - "scripts/metrics/**"
  - "scripts/dev/**"
  - "scripts/kit/**"
---
# 하네스 개발 규칙 (scripts·tests·.claude/hooks 작업)
마트 작업(builder·verifier)에는 해당하지 않는다. 하네스 개발 PR은 인수인계 초안 대신 PR 본문의 요약·결정·검증으로 갈음한다.

## 시험
- 작업 중: `python .claude/hooks/related_tests.py --run <고친 파일들>` (관련 시험을 골라 -n auto. conftest.py를 고쳤거나 관련 시험이 없으면 전체, 직전 실패 파일 포함)
- 브라우저 시험(test_dashboard_render.py)이 골라지면 작업 중에는 -k로 관련된 것만 돌리고, 커밋 직전에 --run으로 1번 (실측 11/11: 순차 약 66초 → -n auto 약 27초)
- 실패한 시험만 다시: `python -m pytest --last-failed -q --tb=short -x` (다 고쳤다고 판단하기 전에는 `-x` 없이 1번)
- 전체 시험은 마지막 커밋 뒤 1번: `python .claude/hooks/related_tests.py --full --run` (= `python -m pytest tests/ -q -n auto -rf --junitxml=…`). 백그라운드로 돌리고 기다리는 동안 보고를 쓴다
  - 실패 기록은 `.claude/state/junit/` 최근 5개. pytest-xdist가 없으면 `-n` 없이 직접 돌린다. passed = 수집 수
  - Windows 실측(가장 최근): 11/11 병렬 1945개 371초
  - 대시보드를 바꾼 PR은 `REQUIRE_BROWSER=1`로 돌린다(브라우저 시험 건너뜀 0)

## 하네스 개발 세션
- on_stop의 progress.md·실행 로그 누락 알림은 마트 작업용이라 무시해도 된다(막지 않는 알림)
- 스크린샷을 찍지 않는다(검증·스크린샷은 대화형 Claude가 push된 브랜치로 한다)
- 대시보드 위쪽 막대 측정은 `scripts/dev/measure_topbar.py`를 실행하며 새로 짜지 않는다
  (`[--html out/dashboard.html] [--widths 1440,1280,…]`, 넘치거나 겹치면 종료 코드 1, 브라우저가 없으면 2, 막대 겹침 시험과 같은 코드, 키트 밖)
- 하네스 동작(Hook·스크립트·명령)을 바꾸면 CLAUDE.md와 docs/plan/03_harness_guide.md(원본 저장소 문서, 키트에 없음)의 설명도 같이 점검한다

## 대시보드 작업
- 기준은 `docs/design/DESIGN.md`(원본 저장소 문서, 키트에 없음)(색·용어·하지 말 것)
- `scripts/metrics/dashboard_data.py`는 기존 기록에서 읽기만 한다(데이터 값·오류 원문 없음)
- 생성기 `scripts/metrics/dashboard.py` → `out/dashboard.html`과 바뀜 감지 `out/dashboard.version.js` (`--watch`·`--json`)

## Hook 4종 (.claude/hooks/)
- `check_bash.py` 실행 전 차단. 셸이 읽지 않는 heredoc 본문의 "bq 명령"처럼 bq 뒤가 ASCII 밖 글자면 문장으로 본다.
  run_loop.py의 `--extend`·`--reset-streak`를 builder·verifier가 쓰면 막는다
- `check_write.py` builder·verifier 경로 차단. 읽기도 막는다(builder의 `_checks/l4·l5`, l4·l5 검사 SQL이 든 `out/dashboard.html·json`).
  `harness_config.json`·`learned/`·`rule_candidate_exclusions.md`·`claim_decisions.md` 쓰기 차단
- `after_edit.py` 수정 후 SQL dry-run, contract L0(결정 80), 고친 .py 경로 기록
- `.githooks/pre-commit` → `scripts/setup/precommit.py`: 커밋되는 contract L0 검사(kit_setup이 core.hooksPath로 켬)
- `on_stop.py` 턴 끝 관련 시험 1번·재시도 3회, 기록 누락 알림
- 공용 모듈 `related_tests.py` 관련 시험 고르기, 명령줄 입구 `--run`·`--full`

## 스크립트 (세부는 각 파일 머리말)
- `ladder/`: `l0_contract.py` L0 contract 형식 검사, `harness_config.py` 설정 읽기·형식 검사,
  `load_mode.py` 적재 방식(contract `load`, 없으면 snapshot)과 파티션 컬럼 공용 함수
- `ladder/` 결과는 `.dev/ladder_results/`(run_ladder.py), 결과서 검사 고정 해시는 `.dev/checks_hash/`(loop/state.py)
- `loop/run_loop.py --mart <마트> [--ds YYYY-MM-DD]`: `--ds`는 매 반복 사다리에 넘기는 판정 날짜. 증분 마트는 원천에 데이터가 있는 날짜,
  재시작 때 다시 준다. `--extend N`·`--reset-streak`는 사람 결재용(`--approver`·`--reason`·`--minutes`). 응답은 `.dev/agent_responses/`
- `log/devlog.py` `.dev/` 로그 기록 도구. `log/auto_approval.py` 결재 1·2를 git 머지 기록에서 자동 기록(run_loop 시작). 대시보드는 preview_all로 화면에만(쓰지 않음)
- `setup/kit_setup.py` 키트 설정 한 번(사람 실행), `setup/kit_local.py` `.kit_local.json`의 CLOUDSDK_CONFIG 적용·`--mart` 자동 선택
- `handover/` 인수인계 사실 부분. `publish.py`는 결재 뒤 docs/handover 반영·PR 본문, 사람이 실행
- `deliverables/`: 단위테스트 결과서 변환기 `unit_test_report.py`, 테이블·컬럼 정의서 `table_spec.py`, 데이터 흐름도 `flow_diagram.py`,
  공통 부분 `deliv_common.py`. 단위테스트 결과서는 검사 행에 iteration 0 고정 해시를 붙이고 '사다리 밖 항목' 시트(verifier 보고 원문,
  판정 아님)를 만든다. `--check`는 검사·게이트 파일이 해시 기록과 다르면 종료 코드 2
- `cards/make_cards.py` AgentGo용 카드 파일 생성(mart 테이블 1개 = 1장 → `out/cards/<마트>/`, `--check`, 업로드 없음)
- `metrics/report.py` → `docs/contest/measurement_report.md`(원본 저장소 문서, 키트에 없음) (`--check`, 사전 등록 v6 기준, 10절 멈춤 표는 참고·사전 등록 지표 아님,
  3절 사람 결정 줄은 docs/contest/claim_decisions.md(원본 저장소 문서, 키트에 없음)에서 읽음, 판정·수치 불변)
- `metrics/rule_candidates.py` 규칙 후보 집계, `--check`는 learned 규칙 형식 검사
- `modules/` 노하우 켜기 도구 자리
- `kit/make_kit.py` 확산 키트 생성(허용 목록, 우리 기록·정답 제외, `--out <폴더> [--check]`). 안내서·예시 요청·원천 등록 체크리스트 원본 `docs/kit/`
- `dev/measure_topbar.py` 대시보드 위쪽 막대 높이·겹침 측정(위 "하네스 개발 세션")
