# task 설계 규칙

DAG task를 나누는 규칙 3개다. DAG task를 추가하거나 contract의 `dag.tasks`를 쓸 때 읽는다. L0가 이 규칙을 검사한다. (00 결정 44 ②)

1. **테이블 1개 = 적재 task 1개**
   - 왜: 실패한 task가 곧 문제의 테이블이다. 그래서 재실행과 장애 대응 범위가 테이블 하나로 좁혀진다. L0가 SQL 파일, task, 테이블을 1:1로 대조할 수도 있다.
2. **층마다 게이트 task 1개 (마트별)**
   - 왜: 품질 위반을 그 층에서 멈춰 다음 층으로 번지지 않게 한다. 배치와 방식은 [design_principles.md §5 레이어 게이트 배치](design_principles.md#5-레이어-게이트-배치-품질-검사)를 따른다.
   - 범위: 마트(contract)마다 적재 task가 있는 층에 게이트 1개다. 게이트 task id는 `gate_<층>_<마트>`이고 그 마트의 검사만 담는다. (00 결정 61 ①②)
   - 다른 마트의 task 빌려 쓰기 (00 결정 61 ④):
     - upstream에 `<마트>:<task>`로 적는다.
     - main에 있는(결재 1을 받은) contract의 task만 쓴다.
     - 빌린 task는 고치지 않는다. 고쳐야 하면 원래 마트의 contract v2로 간다.
   - 빌린 task의 준비 실행 (`scripts/ladder/prep_upstream.py`, 00 결정 61 ⑤, 70):
     - 대상은 빌린 task와 그 상류 load task다. contract를 넘어 재귀로 찾고, 게이트는 뺀다.
     - 사다리가 L0 통과 직후, L1 전에 ai_dev에 같은 ds로 실행한다.
     - 판정하지 않는다. 같은 ds 파티션에 행이 있으면 건너뛴다.
     - 작업 트리의 빌린 SQL이 origin/main과 다르면 멈춘다.
3. **mart는 raw를 직접 읽지 않는다 (raw > stg > mart)**
   - 왜: 정제와 개인정보 제거를 stg 한곳에 모아 mart가 같은 기준을 쓰게 한다. 리니지도 층 순서대로 이어진다.
