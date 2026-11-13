---
paths:
  - "scripts/deliverables/**"
  - "scripts/cards/**"
---
# 납품 산출물 규칙
- 산출물에는 집계값(행 수·검사 위반 행 수·합계)·바이트·판정과 메타데이터(설명, 컬럼, 리니지, 담당 task, 갱신 주기)만 넣는다. 행 단위 데이터 값과 evidence 행은 넣지 않는다.
- 프로젝트 ID·계정은 가린다(scripts/handover/make_facts.py의 scrub()).
- 원천이 없는 필수 칸은 지어내지 않고 비운 뒤 manifest.json의 missing_fields로 센다.
- 모든 산출물에 도장(contract_version·생성 시각·기준 커밋)을 찍는다. 최신성 검사(--check)가 다르면 halt input_invalid (결정 64 ⑤).
- 판정(pass/fail)은 사다리 결과만 옮기고 손으로 고치지 않는다. 틀렸으면 검사를 고치고 사다리를 다시 돌린다.
- 생성물(out/)은 커밋하지 않는다. 양식은 docs/templates/에 있고 고객사 전용 양식은 쓰지 않는다.
- 테이블·컬럼 정의서는 scripts/deliverables/table_spec.py --mart <마트>로 만든다(standards_survey.md §2, S2 [별표 4] 항목). 칸 값은 손으로 고치지 않고 contract·pii_columns.md·검사 쿼리를 고친 뒤 다시 만든다.
- 데이터 흐름도는 scripts/deliverables/flow_diagram.py --mart <마트>로 만든다(결정 69, standards_survey.md §5.1). 그림은 contract에서 그리고 OM 리니지는 L6 결과로 대조만 한다. L6 전에는 OM 확인 칸이 deferred다.
- AgentGo용 카드는 scripts/cards/make_cards.py --mart <마트>로 만든다(결정 78, docs/ai/agentgo_card.md). 위 규칙과 달리 행 수 같은 집계값도 넣지 않고 메타데이터만 넣는다. 업로드는 하지 않는다(결정 29).
