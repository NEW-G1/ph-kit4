# <마트 이름> 요구서

## 1. 목적과 사용자
- 누가, 어떤 의사결정에 쓰는가:

## 2. 원천과 레이어
- 원천 테이블 (<원천_프로젝트>.<원천_데이터셋>):
- 원천 전제 (인터뷰에서 원천을 조회해 확인, `docs/architecture/design_principles.md` §1):
  - 갱신 방식 (매일 전체 덮어쓰기 / 추가만 / 변경·삭제 있음):
  - 시간 컬럼 (생성·변경 시각 컬럼과 타입, 날짜 파티션 여부):
  - 리전 (`dags/harness_config.json`의 `source.location`과 같아야 함):
  - 테이블 크기 (테이블별 크기 또는 dry-run 바이트, 쿼리당 500 MB 이하인지. 뷰(`__TABLES__.type` 2)는 크기 대신 쓸 컬럼만 읽는 dry-run 바이트로 본다):
- 적재 방식 (contract `load`, 결정 79. 인터뷰 고정 조회 "원천 크기와 날짜 파티션 확인"의 기본안을 따르고 결재 1에서 승인):
  - mode: `snapshot`(기본값. 매일 원천 전체를 `snapshot_date` 파티션에 복사, 원천 500 MB 이하) / `incremental`(데이터 날짜 기준. 원천에 날짜 파티션이 있을 때, 일 단위 지표만. 뷰는 날짜 파티션이 없어 고를 수 없다)
  - incremental이면: date_column (원천의 시각·날짜 컬럼):, partition_column (우리 테이블 파티션 컬럼, 모든 테이블에 DATE로):, allow_empty_days (데이터가 없는 날을 통과로 볼지, 기본 false):
  - contract 예: `"load": {"mode": "incremental", "date_column": "created_at", "partition_column": "event_date", "allow_empty_days": false}`. snapshot이면 `{"mode": "snapshot"}` 또는 칸 생략
- 레이어: raw / stg / mart 중 신규·재사용 구분

## 3. 지표 정의
| 지표 | 계산식 | 단위 | 집계 기준일 | 제외 조건 |
|---|---|---|---|---|

## 4. 품질 기준 (ASSERT로 바꿀 수 있는 문장)
- 예: 금액은 음수가 아니다 / 키는 고유하다 / 일자별 행이 존재한다

## 5. 갱신 주기와 보관 기간

## 6. 난이도 지표 (기록용, 판정에 쓰지 않음)
| task 수 | 조인 수 | ASSERT 수 | 원천 테이블 수 | 재사용한 상류 task 수 |
|---|---|---|---|---|

## 7. 완료 조건 (모두 코드로 판정 가능해야 함)
- [ ] L0 계약·DAG 구조: contract.json 형식 검사 통과(인터뷰 필수 칸·`traces_to` 포함), DAG 파일 문법 검사(실제 import는 배포 때), SQL 파일과 task 1:1, task 목록·의존성이 contract와 일치
- [ ] L1 dry-run: 모든 신규 SQL 문법 통과, 쿼리당 스캔량 ≤ 500 MB (결정 46)
- [ ] L2 개발 데이터셋 실행: ai_dev 데이터셋에서 신규 SQL 전부 성공
- [ ] L3 레이어 게이트: raw/stg/mart 사이 ASSERT {목록} 전부 통과
- [ ] L4 원천 대비 정합성: 행 수 오차 0, {지표} 합계 오차 0, 고유 키 수 일치
- [ ] L5 멱등성: 2회 연속 실행 결과의 행 수·체크섬 동일
- [ ] (결재 후) L6 OM 등록: 운영 DAG 실행과 OM 에이전트 실행 뒤 contract의 만들 테이블이 모두 존재, 컬럼 설명 누락 0, 리니지 엣지가 contract 의존 관계에서 계산한 기대값과 일치(결정 47). 실패하면 후속 PR
- [ ] 산출물: 테이블·컬럼 정의서, 단위테스트 결과서, 데이터 흐름도(`flow_diagram.py`) 생성, 템플릿 필수 칸 누락 0
- [ ] 기록: .dev/ 에 반려·개입·비용 로그 기록

## 8. 사람 결재 지점
- 이 요구서와 contract.json 승인(요구서 PR 머지로 기록, 결정 44), push·PR·머지, 완료 조건 자체의 변경

## 9. 그레인·키, 가정, 범위 밖 (결정 42, 비면 L0 실패)
- 그레인(행 1개의 의미)과 키:
- 가정 목록 (AI가 스스로 채운 칸, 근거 쿼리 링크):
- 범위 밖 (이번에 하지 않을 것):

## 10. 요구 목록 (contract의 requirements, traces_to가 가리키는 요구 ID)
| 요구 ID | 요구 | 근거 절 (이 요구서의 절 번호 1~9 중 하나. contract `requirements[].section`에는 따옴표 없는 숫자로, 예: 3) |
|---|---|---|
| R-01 | | |
