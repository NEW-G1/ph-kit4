"""대시보드 생성기 (진행표 4-15, 결정 71·72). dashboard_data.collect() 값으로 out/dashboard.html 1파일을 만든다.

  python scripts/metrics/dashboard.py            # 한 번 만들고 끝
  python scripts/metrics/dashboard.py --watch    # .dev/·docs/requirements/가 바뀔 때마다 다시 만든다(기본 5초 간격, 30초 미만)
  python scripts/metrics/dashboard.py --json     # collect() 결과를 out/dashboard.json으로도 쓴다
  python scripts/metrics/dashboard.py --no-sync  # git 머지 기록에서 결재 1·2를 보는 일(auto_approval.preview_all)을 끈다

- 명령줄 실행은 만들 때마다 git 머지 기록에서 아직 기록되지 않은 결재 1·2를 읽어 화면에만 더한다(--no-sync로 끔).
  파일은 쓰지 않는다(결정 71, 결정 80 ⑤). 기록은 루프가 시작할 때 남기고 커밋한다

- 보기 전용. 판정을 다시 계산하지 않고 collect()가 준 값만 그린다. 기록을 고치는 버튼이 없다
- 어느 파이프라인에도 쓴다: 마트·테이블·데이터셋·업무 이름을 이 파일에 쓰지 않고 모두 contract·기록에서 읽는다
- 화면: 위쪽 흰 막대(브랜드, 마트 탭, [용어]·보기 전용 배지·자동 갱신 표시·데이터 시각·커밋) + 본문(맨 위 목적 한 줄 PURPOSE, D-03).
  [용어]는 용어 서랍(render_terms, 화면 전체에 하나, 주소 #cell=terms)을 상세 서랍과 같은 규칙으로 연다(D-23). 첫 줄 FLOW,
  흐름·검사·측정 세 묶음(TERMS). 640px 이하에서 갱신 표시 묶음이 숨어도 [용어]·테마 토글은 보인다.
- 테마 (D-14·D-53): ① 주소 ?theme=dark|light ② localStorage 'dashboard-theme' ③ OS 설정. <html>에 data-theme을 하드코딩하지
  않고 head 첫 스크립트(HEAD_JS = JS_FLAG + THEME_HEAD, <style> 앞)가 ①·②일 때만 달아 첫 칠하기 전에 적용한다. ?theme=는
  저장값을 덮어쓰지 않는다. 막대 오른쪽 맨 끝 토글 [자동][밝게][어둡게](render_theme, role=group, aria-pressed, html.js일 때만):
  밝게·어둡게 = 저장 + 속성, 자동 = 저장값 지움 + 속성 뗌, 주소의 theme은 replaceState로 뺀다(해시 유지). 토큰은 두 벌(D-52 보류)
  탭 제목은 "(N) 검사·결재 진행 · <마트|전체> · pipeline-harness"(N = 그 보기의 사람 할 일, 0이면 없음)이고 보기를 바꾸면
  JS가 .view의 data-title로 바꾼다. JS가 없으면 전체 보기 문구(마트가 1개면 그 마트, D-17). 마트가 여럿이면
  "전체" 탭과 마트 탭을 주소 #mart=<이름>으로 고른다(JS가 없으면 모든 블록이 차례로 보인다). 마트가 1개면 그 마트 보기만 있다.
  처음 보기: ① #mart= ② 이 탭에 저장된 보기 ③ 사람 할 일이 있는 마트(저장된 보기가 없을 때만, 여럿이면 가장 오래 기다린 마트 =
  할 일 바로 앞 단계의 done_at이 가장 이른 마트, 시각이 없으면 마트 순서. <html data-first-mart>) ④ 전체 (D-04)
- CSS·JS는 파일 안에 넣는다. 외부 CDN·외부 글꼴·외부로 보내는 요청(fetch·이미지·분석)이 없다. 외부 링크(a href)는
  git remote에서 만든 GitHub 주소뿐이다(아래 다음 행동 링크)
- 다음 행동 링크 (D-05): 주소는 dashboard_data가 만든 header.repo_url(remote origin → https://github.com/<org>/<repo>,
  userinfo 제거·SSH 변환·github.com 밖은 None)과 마트별 links.{request_pr|impl_pr}({"number","url"} 또는 None, kind=approval
  기록 target의 "PR #숫자"만)뿐이다. --json에는 이 두 키만 더했다. 결재 1·2 대기면 그 PR을 상태 문구 [행동] 자리에 주요 링크로
  (act_link), 진행 단계 아래 "다음 행동" 카드(render_next, D-44)에 같은 주요 링크를 맨 위에 두고 그 아래 보조 링크(sub_links:
  요구서 PR · 구현 PR · 커밋 7자)를 한 줄에 하나씩(없으면 "링크 없음 · GitHub 주소를 읽지 못함"), 위쪽 막대 커밋도 링크(commit_url).
  외부 링크는 ext_link 하나로 만든다: 이동 모양 + i-ext + target=_blank + rel="noopener noreferrer" + .vh "새 탭에서 열림"(D-29),
  주소가 GITHUB로 시작하지 않으면 글자만. 결재 버튼은 없다(보기 전용)
- 누를 수 있는 것의 모양 다섯 가지 (D-24): .lk 이동(글 속) · .op 열기(덩어리, 오른쪽 --link ›) · .nd 사다리 원(hover 링) ·
  .more 조작(테두리 버튼) · summary.tw 펼치기(▸ 회전). 마트 탭은 탭 모양(D-25: nav + aria-current="page", 굵은 글자 + 2px
  --link 밑줄). 본문 용어 링크는 없다(D-30). 링 네 가지: 포커스 :focus-visible 2px --focus · hover --ring-hover · 선택 --fg ·
  지난 반려 --rail (사다리 원은 안쪽부터 지난 반려 → hover → 포커스 → 선택 순으로 바깥에 쌓는다)
- 숫자 카드 (D-27): 0건이 아니면 카드 전체가 button 하나(안쪽 span만, kpi_acts가 할 일을 정함), 0건이면 div. 위험 명령 차단은
  보던 마트 서랍의 칸 키 blocks(blocks_detail: 사유별·마트별 수, "전체 보기에서 보기"). 차단 카드 숫자 옆 "전체 마트" 태그(D-45)
- 참조 링크 (D-28): R-번호는 이동 모양 a, 지금 막힌 반려 카드의 한 줄은 열기 모양 a. href는 늘 HTML에 남는 id(칸
  c-<마트>-<task>-<L>, L6 한 줄 c-<마트>-L6, 행 r-<마트>-<task>, 진행 단계 행 s-<마트>-<순번>)를 가리키고 칸 키는 data-open(검사 줄은
  data-ck, 보기 밖이면 data-mart). JS가 클릭을 가로채 서랍을 열고, JS가 없으면 그 자리로 스크롤한다. C-번호는 서랍 반려 상자의
  "검사로 이동" 버튼. 반려 상세 카드(task 이름 링크 포함)는 없앴다(D-42)
- 키보드 (D-31): body 맨 앞 "본문으로 건너뛰기"(→ 지금 보기의 머리 h1). 사다리는 roving tabindex(정지점 1개, ←→↑↓ Home/End,
  들어올 때 마지막 칸 → 반려 이력·실패 칸 → 첫 칸, 마지막 칸은 상태 키 lad에 보기마다). JS가 보기 id(mart=<이름>)를 떼어 내
  주소 해시로 열어도 첫 Tab이 건너뛰기 링크다
- 자동 갱신 (D-08~D-11): 생성기는 HTML을 다 쓴 뒤 옆에 <이름>.version.js(out/dashboard.version.js)를 쓴다. 내용은 한 줄
  window.__dashVersion({"hash":…,"beat":…}). hash = collect() 값에서 생성 시각·L6 경과일을 뺀 것의 sha256 앞 16자(같은 기록이면
  같다, 페이지 <html data-hash>와 같은 값), beat = 그 파일을 쓴 시각(epoch ms). --watch는 기록이 안 바뀐 주기에도 version.js만
  다시 써서 beat를 올린다. 데이터 값·경로·SQL은 넣지 않는다(결정 71). 페이지는 CHECK_SEC(10초)마다 script 태그로 version.js?t=…를
  읽고(file://에서 fetch가 막히므로) hash가 다를 때만 다시 불러온다. beat가 STALE_SEC(30초) 넘게 오르지 않거나 파일을 못 읽으면
  "자동 갱신 꺼짐 · --watch로 실행하면 켜집니다". 상세 서랍이 열려 있거나, 마지막 입력(스크롤·키·클릭·포인터) 뒤 3초가 안 지났거나,
  키보드 포커스(:focus-visible)가 본문 요소에 있거나, 선택된 글자가 있거나, 탭이 숨어 있으면 미루고 "새 기록 있음 · 새로고침"
  (aria-live)을 띄운다(숨은 탭은 다시 보일 때 판단). 일시정지는 그 탭에서만. JS가 없으면 자동 갱신이 없고 noscript 안내 한 줄
- 다시 불러와도 펼친 칸·스크롤(세로·넓은 표 가로)·마트 보기·열린 서랍·키보드 포커스(data-open 키)·일시정지를 sessionStorage 키
  하나(dashboard-state)로 이어 간다(저장이 막혀도 화면은 정상). 열린 상세 서랍은 주소 #cell=<칸>(마트가 여럿이면
  #mart=<이름>&cell=<칸>)으로도 이어 간다. 사다리 접기의 펼친 구간(fold)·모두 보기(foldall)도 같은 키에 둔다(D-40).
  L6 마지막 확인 시각은 진행 단계 L6 행 둘째 줄에만 있고(D-42) data-t 원시 시각으로 JS가 "· N일 전"을 붙인다
- 마트 보기 (D-44): 머리 한 줄(contract 버전·요청자 역할·제목·상태 배지·상태 문구) → 2열(왼쪽 = 진행 단계 세로 타임라인 + 다음 행동
  카드, 화면 높이 조건일 때만 sticky / 오른쪽 = 숫자 카드 6장 → 지금 막힌 반려 카드(있을 때만, D-42) → 검사 사다리 → 접힘 상세)
  → 규칙(마트가 1개일 때, 여럿이면 보기 밖). 960px 미만은 한 열(다음 행동 → 진행 단계 → 숫자 카드 2열 → 사다리 → 세부, D-47).
  근거가 있는 진행 단계 행을 누르면 사다리와 같은 상세 서랍에 ① 하는 일 ② 상태 ③ 누가·언제 ④ 관련 PR(주소가 있을 때만)
  ⑤ 근거 파일이 보인다(제목 "결재 2 · 구현 PR 머지", D-13·D-39)
- 전체 보기 (D-46): 머리 한 줄(전체 상태 배지·마트별 사람 할 일) → 마트별 한 줄 카드(사람 할 일 → 막힘 → 진행 중 → 완료, 누르면 그
  마트 보기) → 합계 숫자 카드 5장(반려·개입 시간·결재·비용·차단, 반복 없음, 차단만 서랍) → 접힘 상세 → 규칙
- 빈 상태 (D-41): 없으면 줄 하나, 표는 없음(규칙 0건, 유지보수 개입 전부 0, 상세 표의 0 지표는 "0인 지표 N개" 펼치기, 서랍의 기록 없음
  줄). 숨긴 값의 data-k는 숨은 칸·details 안에 남는다
- 사다리 접기 (D-40): 모든 칸을 첫 시도에 통과한 연속 task 행을 "<task> · <task> 모두 첫 시도 통과" 한 줄로(JS가 있을 때만, html.js).
  접힌 줄은 사다리 roving 칸 하나, Enter로 펼치면 첫 행 0번 칸. 사다리 머리 "모두 보기". 접힌 행 안의 칸·행 id는 HTML에 그대로
- 상태 (D-19): 배지 안은 한 단어(완료·대기·멈춤, AI 진행 중이면 진행), 배지 뒤 문구는 "[마지막 완료 단계]까지 완료 · [다음 단계]
  대기 · 사람이 할 일 N건: [행동]"(지금 단계가 멈춤·반려면 "루프 멈춤 · …", 0건이면 "사람이 할 일 없음"). 단계 이름은 진행 단계
  카드 이름 그대로, 행동은 ACTION. 전체 보기는 같은 공식을 마트 합계로("마트 2개 모두 L6까지 완료 · 사람이 할 일 없음")
- 단계 이름은 RUNG_PLAIN 한 벌만 화면에 쓴다(사다리 열 제목은 두 줄 "L5" / "다시 돌려도 같은지", D-16)
- 검사 사다리: task마다 동그라미 6개(L0~L5, 모양·색과 반려 이력 고리·"반려 N"만), L6는 마트 전체 한 줄 버튼. 동그라미를 누르면
  오른쪽 서랍(뒤에 막)이 열린다. 제목 "<task> · L3 층별 품질 검사" + 상태 Badge, 그 아래 미니 사다리(그 task의 L0~L5, 누르면 서랍
  안에서 옆 칸, D-26, 서버는 자리만 두고 열릴 때 JS가 행의 원을 읽어 만든다), 본문 ① 확인하는 것 ② 결과(+ 반려 상자: 지금 막힌 것만 빨강, 지난 반려는 회색, now_index) ③ 통과 조건
  (아이콘 목록) ④ 시도 기록 ⑤ 검증에 쓴 SQL(통과 칸 포함: task SQL, 검사 파일, L5 내장 쿼리 = l5_idem.snapshot_sql) ⑥ 근거 파일(D-39).
  쉬운 말 사전(RUNG_PLAIN·ERROR_INFO 등)은 LABELS 옆에 둔다. 검사 SQL(l4·l5 포함)이 들어가므로 builder는 이 파일을 읽지 못한다
- 모든 글자는 html.escape를 거친다(속성 값 포함). 색만으로 구분하지 않고 글자·모양을 함께 쓴다(docs/design/DESIGN.md)
- 아이콘 (D-36): 인라인 SVG 한 벌(ICONS, viewBox 0 0 16 16, currentColor)을 icon(이름)으로 쓰고, body 맨 앞 숨은 SVG에 그 문서가
  실제로 쓴 <symbol>만 넣는다(icon_defs). 화면 글자에 상태 글리프(✓ ✗ ■ ● ○, 상태용 ! –)를 쓰지 않는다. 아이콘은 aria-hidden이고
  상태 글자는 옆의 보이는 글자·.vh·aria-label이 맡는다
- Badge 1종(badge(), .bd, D-35): variant 4개(pass·fail·todo·neutral), 크기 옵션 lg(머리 상태 배지, 14px·700, D-33). 상태 Badge는
  아이콘을 붙이고(state_badge), 분류 Badge(층·역할 칩, 범위, 보기 전용, 반려 유형·분류, 하네스 원인)는 아이콘 없는 neutral(tag).
  StatusDot 1종(status_dot(), .sd-dot): 진행 단계 행·마트 탭. 사다리 동그라미(.nd)는 별도 컴포넌트
- 색의 뜻 (D-34): 빨강 = 지금 막힌 것(현재 반려·멈춤)만(blocked·rejection_now), 주황 = 사람 할 일만(결재 1·2 대기, L6 재확인 —
  머리 배지·탭·진행 단계 노드가 같은 아이콘), 회색 = AI 진행 중(반쯤 찬 원)·대기(점선 빈 원)·지난 반려(회색 고리·중립 "반려 N").
  지금 막힌 것이 없으면 반려 수는 본문색, 지난 반려 카드는 --line-strong 띠
- CSS 값은 :root 토큰만 쓴다: 글자 크기 다섯 단계(13 캡션 전용·14·16·20·28)와 단계별 행간, 굵기 400·600·700,
  링크색 --link(--focus와 따로), 사다리 연결선 --rail. 규칙의 font-size·font-weight·color·background는 var()만(D-32·D-33·D-52)
- 글꼴 (D-01): --font-sans는 한글 글꼴 먼저(Pretendard·맑은 고딕·Apple SD Gothic Neo → system-ui …), 웹폰트 없음
- 대비 (D-37, 시험이 토큰 블록으로 계산): 글자 4.5:1, 비글자(링·탭 밑줄·연결선) 3:1, 흰 체크 × --pass-solid(밝게 #0A7357) 5:1.
  예외는 --line·--line-strong(장식선)과 어둡게 --ring-hover(링 네 색끼리 1.5:1 우선) — tests/test_dashboard.py CONTRAST_EXCEPTIONS
- 숫자·날짜 (D-38): 개수는 줄이지 않고 쉼표 원값(26,431), 단위는 숫자에 붙이고 영문 단위만 띄운다("1건", "161.7 MB",
  바이트는 2진 1 MB = 1,048,576바이트), 금액 "$1.23"·0.01달러 미만은 "< $0.01", 시각은 KST 24시간제 "11/4 08:48"(올해가
  아니면 연도). 원래 값은 data-v와 --json에 있다(시험의 역할은 이 머리말 끝 절)
- 내부 키는 LABELS로 사람이 읽는 말로 바꿔 보인다(데이터는 그대로, 원래 키는 --json)
- title (D-49): 시각의 전체 값("2026-11-02 15:44:40")만 둔다. 숫자·내부 키·용어 정의·통과 조건 title은 없다(설명은 서랍 본문)
- 화면 글자 (D-20~D-22): 문장은 "~합니다·~입니다", 라벨·배지·열 제목은 명사형. 화면 글자·title·aria에 결정 번호, 사전 등록 지표
  번호(M1~M12, data-k와 주석에는 남김), 문서 절 번호, 내부 파일 이름, 작업 메모를 쓰지 않는다. 숫자 카드에는 verifier·본 측정을
  쓰지 않고, 묶음 위 "결재 2까지 기준"(KPI_BASIS) 한 번 + 카드 아래 줄은 그 기준과 다른 것만 둔다
- collect()가 evidence·오류 원문을 빼고 자유 문장을 scrub한다. 이 파일은 그 밖의 값을 더하지 않는다
- OM API는 조회하지 않는다. L6 확인 시각은 l6_om.py가 남긴 결과 파일에서 온다

data-k 계약 (D-50). 화면 숫자마다 data-k(키)와 data-v(원래 값)를 둔다. 값의 출처는 --json 출력(public_data()) 하나다.
값 시험은 --json 출력만 보고, 화면 시험은 어느 자리에 어떤 data-k가 보이는지만 본다. 둘을 잇는 시험은 하나다
(tests/test_dashboard.py: 화면의 모든 data-k에서 data-v = 오른쪽 자리의 값). <마트>는 contract 마트 이름, {a|b}는 그중 하나,
그 밖의 <…>는 기록에 있는 이름 하나. 마트가 1개면 <마트>.queue.* 대신 queue.*만 있다. 키 꼴(왼쪽) → --json 자리(오른쪽):
  header.{generated_at|commit}                              header.<같은 키>
  queue.{approval_1|approval_2|halted|l6_reject}            len(queue.<같은 키>)
  queue.l6_recheck                                          marts.*.l6_check.recheck가 참인 마트 수
  queue.total                                               위 다섯 수의 합
  <마트>.queue.{approval_1|approval_2|halted|l6_reject|l6_recheck|total}   위 queue.* 계산을 그 마트로 좁힌 값
  rejections.count                                          len(marts.*.rejections)의 합
  rules.{learned|candidates|excluded}                       len(rules.<같은 키>)
  rules.promoted                                            rules.promoted
  rules.total                                               len(rules.learned) + len(rules.candidates)
  rules.m10.<규칙>.<마트>.{before|after|excluded}           rules.m10[rule_id=<규칙>].by_mart.<마트>.<같은 키>
  <마트>.ladder.{cells|passed|rejected}                     marts.<마트>.grid.summary.<같은 키>
  <마트>.l6.{checked_at|age_days}                           marts.<마트>.l6_check.<같은 키>
  <마트>.rejections.count                                   len(marts.<마트>.rejections)
  <마트>.rejections.harness                                 marts.<마트>.rejections 중 harness_cause가 참인 수
  <마트>.reused_upstream                                    len(marts.<마트>.summary.reused_upstream)
  <마트>.prep_bytes                                         marts.<마트>.summary.<같은 경로> (이 줄부터 <마트>. 줄 모두)
  <마트>.iterations.{judged|limit|streak}
  <마트>.M1.{main|maintenance|ops_run}.{count|minutes}
  <마트>.M1.{main|maintenance}.by_kind.<종류>.{count|minutes}
  <마트>.M1.{main|maintenance}.approval_by_stage.rule_promotion.count
  <마트>.M2.{total|post_approval}.count
  <마트>.M2.total.by_error_type.<유형>
  <마트>.M3.<task>.rejects
  <마트>.M4.{calls|<비용칸>}                                <비용칸>은 dashboard_data.COST_FIELDS
  <마트>.M12.{main|maintenance}.count
  <마트>.M12.main.by_stage.<단계>
  all.M11.count                                             summary.<같은 경로> (이 줄부터 all. 줄 모두)
  all.M11.by_reason.<이유>
  all.M11.by_mart.<이름>                                    <이름>은 마트 이름 또는 "마트 밖"
  all.{M1_minutes_main|M12_main}
  all.M2_by_error_type.<유형>
  all.M4.{calls|<비용칸>}
"""
import argparse
import copy
import hashlib
import html
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "log"))
import auto_approval  # noqa: E402  (명령줄 실행 때 기록되지 않은 결재 1·2를 화면에만, --no-sync로 끔)
import dashboard_data as dd  # noqa: E402
import l5_idem  # noqa: E402  (scripts/ladder/l5_idem.py, dashboard_data가 경로를 넣는다. L5 내장 쿼리 문장을 같은 함수로 만든다)

PROJECT = dd.PROJECT
OUT = PROJECT / "out" / "dashboard.html"
OUT_JSON = PROJECT / "out" / "dashboard.json"
CHECK_SEC = 10   # 페이지가 version.js를 다시 읽는 주기 (D-11)
STALE_SEC = 30   # beat가 이만큼 오르지 않으면 "자동 갱신 꺼짐" (D-11)
WATCH_SEC = 5.0
WATCH_DIRS = (".dev", "docs/requirements")
SECTIONS = (("header", "머리말"), ("queue", "사람 할 일"), ("stages", "진행 단계"), ("cards", "숫자 카드"),
            ("ladder", "검사 사다리"), ("summary", "상세 표"), ("rules", "규칙"))
# 아이콘 한 벌 (D-36). viewBox 하나(0 0 16 16), 색은 currentColor 하나(사람 할 일 원 안의 '!'만 --on-solid). 쓰는 곳은
# icon(이름)이고 render()가 문서에서 실제로 쓴 이름의 <symbol>만 body 맨 앞 숨은 SVG 하나에 넣는다(icon_defs). 상태 모양은
# 서로 모두 달라 색 없이도 구분된다: 통과 체크 · 반려 X · 멈춤 네모 · 대기 점선 빈 원 · 진행 반쯤 찬 원 · 사람 할 일 꽉 찬 원 + '!'.
# 정보는 테두리만 있는 원 + 'i'(14px에서 '!'와 'i'가 위아래만 뒤집힌 모양이라 채우기 방식으로 구분한다)
ICONS = {
    "pass": "<path d='M3.2 8.4l3.1 3.1 6.5-7' fill='none' stroke='currentColor' stroke-width='2' stroke-linecap='round' "
            "stroke-linejoin='round'/>",
    "fail": "<path d='M4.3 4.3l7.4 7.4M11.7 4.3l-7.4 7.4' fill='none' stroke='currentColor' stroke-width='2' "
            "stroke-linecap='round'/>",
    "halt": "<rect x='3.5' y='3.5' width='9' height='9' rx='1.5' fill='currentColor'/>",
    "wait": "<circle cx='8' cy='8' r='5.6' fill='none' stroke='currentColor' stroke-width='1.6' stroke-dasharray='2.2 1.8'/>",
    "run": "<circle cx='8' cy='8' r='5.6' fill='none' stroke='currentColor' stroke-width='1.6'/>"
           "<path d='M8 2.4a5.6 5.6 0 0 0 0 11.2z' fill='currentColor'/>",
    "todo": "<circle cx='8' cy='8' r='7' fill='currentColor'/><path d='M8 4.2v4.6' fill='none' stroke-width='2' "
            "stroke-linecap='round' style='stroke:var(--on-solid)' data-on/><circle cx='8' cy='11.6' r='1.15' "
            "style='fill:var(--on-solid)' data-on/>",
    "info": "<circle cx='8' cy='8' r='6.3' fill='none' stroke='currentColor' stroke-width='1.5'/><path d='M8 7.3v4.2' "
            "fill='none' stroke='currentColor' stroke-width='1.6' stroke-linecap='round'/><circle cx='8' cy='4.9' r='1' "
            "fill='currentColor'/>",
    "ext": "<path d='M6.5 3.5h6v6M12.5 3.5L4 12' fill='none' stroke='currentColor' stroke-width='1.6' stroke-linecap='round' "
           "stroke-linejoin='round'/>",
    "chev": "<path d='M6 3.5L10.5 8 6 12.5' fill='none' stroke='currentColor' stroke-width='1.8' stroke-linecap='round' "
            "stroke-linejoin='round'/>",
    "tri": "<path d='M5.5 3.8L11.5 8l-6 4.2z' fill='currentColor'/>",
    "sun": "<circle cx='8' cy='8' r='3' fill='currentColor'/><path d='M8 1.5v1.8M8 12.7v1.8M1.5 8h1.8M12.7 8h1.8M3.4 3.4l1.3 1.3"
           "M11.3 11.3l1.3 1.3M3.4 12.6l1.3-1.3M11.3 4.7l1.3-1.3' fill='none' stroke='currentColor' stroke-width='1.5' "
           "stroke-linecap='round'/>",
    "moon": "<path d='M13.2 10.2A5.8 5.8 0 0 1 5.8 2.8a5.8 5.8 0 1 0 7.4 7.4z' fill='currentColor'/>",
    "auto": "<rect x='1.8' y='2.8' width='12.4' height='8.4' rx='1.4' fill='none' stroke='currentColor' stroke-width='1.5'/>"
            "<path d='M5.5 13.6h5M8 11.2v2.4' fill='none' stroke='currentColor' stroke-width='1.5' stroke-linecap='round'/>",
    "pause": "<path d='M5.2 3.5v9M10.8 3.5v9' fill='none' stroke='currentColor' stroke-width='2.2' stroke-linecap='round'/>",
}
# Badge variant 4개 (D-35): 통과 · 막힘 · 사람 할 일 · 중립. 상태 Badge는 아이콘을 붙이고, 분류 Badge(층·역할·범위·유형 태그)는
# 아이콘 없이 neutral. variant를 늘리지 않고 이 규칙으로 상태와 분류를 구분한다
VARIANTS = ("pass", "fail", "todo", "neutral")
# 상태 글자 → (variant, 아이콘 이름). 아이콘은 글자와 함께 보인다(색만으로 구분하지 않음).
# 색의 뜻 (D-34): 민트 = 통과·완료, 빨강 = 지금 막힌 것(현재 반려·멈춤)만, 주황 = 사람 할 일만, 회색 = AI 진행 중·대기·지난 반려.
# 빨강과 주황은 명도가 비슷하므로 늘 아이콘을 함께 둔다(빨강 = X·네모, 주황 = 꽉 찬 원 + !)
STATE = {dd.DONE: ("pass", "pass"), "통과": ("pass", "pass"), dd.ACTIVE: ("neutral", "run"), dd.WAIT: ("neutral", "wait"),
         dd.HALT: ("fail", "halt"), dd.REJECT: ("fail", "fail"), "재확인 필요": ("todo", "todo"), dd.NONE: ("neutral", "wait"),
         "미실행": ("neutral", "wait")}
# 사다리 칸 표시: 상태 글자 → (.nd 종류, 아이콘 이름). 글자는 aria-label·.vh에 둔다. 미실행은 아이콘 대신 칸 자체가
# 대기 모양(점선 테두리 빈 원, --surface 면)이다
CELL = {"통과": ("pass", "pass"), dd.REJECT: ("fail", "fail"), dd.HALT: ("halt", "halt"), "미실행": ("none", None)}
RUNG_STATUS = {"pass": "통과", "fail": "반려"}
VERDICT = {"pass": "통과", "reject": "반려", "halt": "멈춤"}
ACTOR = {"결재 1": "사람", "PR": "사람", "결재 2": "사람", "루프": "AI", "운영": "결재 후", "L6": "결재 후"}
# 사람 할 일 5항목: (queue 키, 표시 글자, 종류)
TODO = (("approval_1", "결재 1 대기", "todo"), ("approval_2", "결재 2 대기", "todo"), ("halted", "루프 멈춤", "fail"),
        ("l6_recheck", "L6 재확인", "todo"), ("l6_reject", "L6 반려", "fail"))
TODO_ICON = {"approval_1": "todo", "approval_2": "todo", "l6_recheck": "todo", "halted": "halt", "l6_reject": "fail"}
# 상태 문구의 [행동] (D-19). 단계 이름은 진행 단계 카드의 이름 그대로 쓰고, 행동은 결재자가 할 일을 말한다. 링크는 T9(D-05)
ACTION = {"approval_1": "요구서 PR 머지", "approval_2": "구현 PR 머지", "halted": "멈춘 원인 확인",
          "l6_recheck": "L6 다시 확인", "l6_reject": "L6 반려 원인 확인"}
FLOW = "AI 기안 → 코드 검토(L0~L6) → 사람 결재"  # 용어 서랍 첫 줄 (D-18·D-23)
PURPOSE = "AI가 만든 데이터 파이프라인이 자동 검사(L0~L6)와 사람 결재를 어디까지 통과했는지 보는 화면입니다."  # D-03
TAB_TITLE = ("검사·결재 진행", "pipeline-harness")  # 탭 제목 앞·뒤 (D-17): "(N) 검사·결재 진행 · <마트|전체> · pipeline-harness"
READ_ONLY = "보기 전용 · 결재는 GitHub PR에서"  # D-06
SKIP = "본문으로 건너뛰기"  # body 맨 앞 링크, 누르면 지금 보기의 머리 제목(h1)으로 포커스 (D-31)
NO_JS = "자동 갱신은 JavaScript를 켜야 동작합니다. 모든 마트가 한 페이지에 이어서 보입니다. 새 기록은 F5로 봅니다."  # D-15
# 사람 할 일 → 그 할 일이 걸린 단계(None = 지금 단계). 기다리기 시작한 시각 = 이 단계 바로 앞 단계의 done_at (D-04)
WAIT_STAGE = {"approval_1": "결재 1", "halted": "루프", "approval_2": None, "l6_recheck": "L6", "l6_reject": "L6"}
MB = 1024 * 1024  # 사다리 스캔 상한 500 MB = 524288000과 같은 단위
# 08 M3 분류의 표시 문구. 일어난 결과만 말하고 원인을 단정하지 않는다. 분류 값은 그대로, 원래 이름은 title에 둔다
M3_LABELS = {"스스로 고침": "루프 안에서 통과", "연장 결재 뒤 통과": "상한 연장 뒤 통과", "반려 없음": "반려 없음",
             "멈춤": "통과 전 멈춤", "진행 중": "반려 뒤 진행 중"}
# 표시 이름 사전. 데이터는 그대로 두고 화면 글자만 바꾼다. 없는 키는 그대로 보인다(Hook 차단 사유는 시험이 전부 있는지 본다).
# ops는 push·PR 생성이다(결재 후 운영 절차 ops_run의 "운영"과 다르다)
LABELS = {
    # Hook 차단 사유 (check_bash·check_write)
    "destructive_command": "파괴 명령", "git_push": "git push", "env_read": ".env 접근",
    "write_outside_ai_dev": "개발 데이터셋 밖 쓰기", "write_target_unknown": "쓰기 대상 불명",
    "cost_limit_missing": "비용 상한 누락", "cost_limit_exceeded": "비용 상한 초과",
    "bq_command_unknown": "알 수 없는 bq 명령", "parse_error": "명령 해석 실패",
    "loop_plan_read": "루프 중 기획 문서 읽기", "loop_approval_by_ai": "역할 밖 결재 명령",
    "builder_write_checks": "builder의 검사 파일 쓰기", "builder_write_dq": "builder의 게이트 파일 쓰기",
    "builder_write_config": "builder의 설정 파일 쓰기", "builder_write_rules": "builder의 규칙·제외 목록 쓰기",
    "builder_read_hidden_checks": "builder의 숨은 검사 읽기", "builder_read_dashboard": "builder의 대시보드 읽기",
    "verifier_write_outside_checks": "verifier의 검사 폴더 밖 쓰기",
    # 결재 단계·개입 종류
    "approval_1": "결재 1", "approval_2": "결재 2", "ops": "PR 올리기",
    "approval": "결재", "correction": "수정 요청", "manual_check": "수동 확인", "requirement_change": "요구 변경",
    # 비용 항목
    "input_tokens": "입력 토큰", "output_tokens": "출력 토큰", "cache_read_tokens": "캐시 읽기 토큰",
    "cache_write_tokens": "캐시 쓰기 토큰", "bq_bytes_processed": "BigQuery 스캔량",
    "total_cost_usd": "합계 (정가 환산 추정)",
    # 반려 유형·멈춤 이유
    "syntax": "문법 syntax", "contract_change": "contract 변경 필요", "infra_error": "인프라 오류",
    "builder_blocked": "builder 막힘",
}
# ----- 사다리 격자·상세 패널의 쉬운 말 사전 -----
# 단계 이름은 이 한 벌만 화면에 쓴다(열 제목·서랍 제목·반려 카드·aria, D-16). dry-run·멱등성 같은 다른 이름은 용어 서랍에만
RUNG_PLAIN = {"L0": "설계도 확인", "L1": "문법·비용 확인", "L2": "개발 환경 실행", "L3": "층별 품질 검사",
              "L4": "원천과 맞춰 보기", "L5": "다시 돌려도 같은지", "L6": "메타데이터 등록 확인"}
# 통과 조건(dd.PASS_RULES)을 화면 말로. 원래 문구는 --json의 rungs에 그대로 있다
PASS_PLAIN = {
    "L0": "contract 형식, DAG 구조(task 목록·의존성이 contract와 같고 SQL 파일과 task가 1:1), 검사 쿼리 머리말이 맞으면 통과합니다.",
    "L1": "실행하지 않고 확인한 SQL 문법이 맞고, 읽는 양이 500 MB 이하이고, SQL 원문에 운영 데이터셋 이름이 없으면 통과합니다.",
    "L2": "개발 데이터셋에서 실행이 성공하고 contract의 테이블이 생기면 통과합니다.",
    "L3": "운영 게이트 파일이 이 단계 검사 파일에서 만든 결과와 같고, 이 task의 검사 쿼리가 0행을 돌려주면 통과합니다.",
    "L4": "원천과 맞춰 보는 이 task의 검사 쿼리가 0행을 돌려주면 통과합니다.",
    "L5": "같은 날짜로 다시 실행한 전후의 행 수·체크섬이 같고, 이 task의 검사 쿼리가 0행을 돌려주면 통과합니다.",
    "L6": "카탈로그(OM)에 contract의 테이블이 있고, 컬럼 설명 누락이 0이고, 리니지 연결이 contract 기대값과 같으면 통과합니다.",
}
# 패널 ①: 이 단계가 무엇을 확인하나
RUNG_WHAT = {
    "L0": "만들 테이블과 task 구성이 결재된 설계도(contract)와 같은지, 파일 구성이 규칙에 맞는지 봅니다. 데이터는 아직 읽지 않습니다.",
    "L1": "BigQuery에 실제로 돌리지 않고 SQL 문법이 맞는지, 읽는 양이 상한(500 MB) 안인지 봅니다.",
    "L2": "운영이 아닌 개발 데이터셋에서 SQL을 실제로 실행해, 설계도에 적힌 테이블이 생기는지 봅니다.",
    "L3": "만든 테이블에 검사 쿼리를 돌려 문제 행(빈 파티션, 키 중복, 빈 값, 범위 위반 등)이 한 건도 없는지 봅니다. "
          "운영에서도 같은 검사가 층 사이 게이트로 돕니다.",
    "L4": "원천 데이터에서 따로 계산한 건수·합계와 만든 테이블의 값이 맞는지 검사 쿼리로 봅니다.",
    "L5": "같은 날짜로 한 번 더 실행해도 행 수와 내용(체크섬)이 그대로인지, 다시 돌린 뒤 중복 적재가 없는지 봅니다.",
    "L6": "결재 뒤 운영에서 돌린 다음, 데이터 카탈로그(OM)에 테이블·컬럼 설명·리니지가 설계도대로 등록됐는지 봅니다. "
          "task가 아니라 마트 전체를 한 번에 봅니다.",
}
# 패널 ③: 검사 파일이 없는 단계에서 사다리가 확인하는 항목 (03 §5.3, CLAUDE.md §5)
RUNG_ITEMS = {
    "L0": ("contract 파일 형식이 맞습니다", "DAG 파일 문법이 맞고 task 목록·의존성이 contract와 같습니다",
           "SQL 파일과 task가 1:1입니다", "비율 지표에 SAFE_DIVIDE를 씁니다", "개인 식별 컬럼이 정제 층 이후로 넘어가지 않습니다",
           "증분 적재면 SQL에 데이터 날짜 조건이 있습니다", "검사 쿼리 머리말(error_type·task) 형식이 맞습니다"),
    "L1": ("개발 데이터셋 리전이 원천 리전과 같습니다", "실행하지 않고 확인한 SQL 문법이 맞습니다", "읽는 양이 500 MB 이하입니다",
           "SQL 원문에 운영 데이터셋 이름을 직접 쓰지 않았습니다"),
    "L2": ("개발 데이터셋에서 SQL 실행이 성공합니다", "contract에 적힌 테이블이 생깁니다"),
    "L3": ("운영 게이트 파일이 이 검사 파일들에서 만든 결과와 같습니다",),
    "L5": ("같은 날짜로 2번 실행한 전후의 행 수·체크섬이 같습니다",),
    "L6": ("contract의 테이블이 카탈로그에 모두 있습니다", "컬럼 설명 누락이 없습니다", "리니지 연결이 contract 기대값과 같습니다"),
}
L6_COUNTS = {"tables_missing": "없는 테이블", "description_missing": "설명 누락 컬럼",
             "edges_missing": "빠진 리니지 연결", "edges_unexpected": "예상 밖 리니지 연결"}
# 층 이름: contract layer 값 → 쉬운 말 (없는 값은 그대로)
LAYER_PLAIN = {"raw": "원본 복사", "stg": "정제", "mart": "집계"}
LAYER_WHAT = {"raw": "원천 데이터를 개발 데이터셋으로 그대로 옮겨 오는 task입니다.",
              "stg": "원본을 정리해 분석에 쓸 수 있게 만드는 task입니다. 개인 식별 컬럼은 이 층에서 뺍니다.",
              "mart": "정제된 데이터를 지표로 모으는 task입니다."}
# 반려 유형(devlog.ERROR_TYPES) → (쉬운 이름, 한 줄 설명). 시험이 ERROR_TYPES 전부가 있는지 본다
ERROR_INFO = {
    "contract_invalid": ("설계도 형식 오류", "contract 파일의 형식이 규칙에 맞지 않음"),
    "dag_import_error": ("DAG 파일 오류", "DAG 파일을 문법상 읽을 수 없음"),
    "dag_structure_mismatch": ("구성 불일치", "task 목록·의존성 또는 만든 테이블이 설계도와 다름"),
    "syntax": ("SQL 문법 오류", "SQL 문법이 틀렸거나 쿼리를 해석할 수 없음"),
    "cost_exceeded": ("비용 상한 초과", "쿼리가 읽는 양이 상한(500 MB)을 넘음"),
    "runtime_error": ("실행 오류", "문법은 맞지만 실행 중에 실패함"),
    "type_mismatch": ("타입 불일치", "값의 타입이 설계도나 대상 테이블과 맞지 않음"),
    "null_violation": ("빈 값", "비면 안 되는 컬럼에 빈 값(NULL)이 있음"),
    "range_violation": ("범위 벗어남", "값이 허용 범위나 허용 목록 밖에 있음"),
    "duplicate_rows": ("키가 중복됨", "한 행이어야 하는 키가 여러 행에 있음"),
    "join_missing": ("원천과 안 맞음", "원천과 맞춰 본 건수·합계가 다르거나 짝이 없는 행이 있음"),
    "idempotency_break": ("다시 돌리면 달라짐", "같은 날짜로 다시 돌리면 결과가 달라짐"),
    "description_missing": ("설명 누락", "컬럼 설명이 비어 있음"),
    "lineage_missing": ("리니지 누락", "테이블 사이 연결(리니지)이 설계도와 다름"),
    "pii_column": ("개인 식별 컬럼", "개인 식별 컬럼이 정제 층 이후로 넘어감"),
    "hardcoded_dataset": ("데이터셋 이름 직접 씀", "SQL에 운영 데이터셋 이름을 자리 표시 대신 직접 씀"),
    "table_missing": ("테이블 미등록", "설계도의 테이블이 카탈로그(OM)에 없음"),
}
# 멈춤 이유(halt_reason) → 쉬운 말. 패널에서만 쓴다(없는 값은 LABELS, 그것도 없으면 그대로)
HALT_PLAIN = {"contract_change": "설계도(contract)를 바꿔야 해서 멈춤", "infra_error": "인프라 오류로 멈춤",
              "builder_blocked": "권한이 막혀 멈춤", "input_invalid": "사람·verifier 쪽 입력 파일 문제로 멈춤"}
LADDER_SUB = "task마다 6단계를 차례로 통과해야 결재로 넘어갑니다"
LADDER_HINT = "원을 누르면 검사 내용과 SQL이 열립니다"  # i-info 아이콘과 함께 (D-24)
# 사다리 범례 한 줄: [아이콘] 글자 · … · 고리 설명. 아이콘은 모양만 알려 주므로 본문 보조색(색의 뜻은 칸과 탭이 보인다)
# 사람 할 일은 사다리 칸에는 없지만 L6 재확인 한 줄·진행 단계·탭에 나오므로 넣는다
LEGEND_MARKS = (("pass", "통과"), ("fail", "반려"), ("halt", "멈춤"), ("wait", "미실행"), ("todo", "사람 할 일"))
LEGEND_RING = "회색 고리 = 지금은 통과지만 반려된 적이 있음"
# 칸 서랍 "검증에 쓴 SQL" 문구 (결과와 상관없이 모든 칸에 둔다)
SQL_HEAD = "검증에 쓴 SQL"
SQL_L0 = "이 단계는 SQL을 돌리지 않고 코드가 설계도·DAG·SQL 파일을 읽어 봅니다."
SQL_L5 = "같은 날짜로 2번 실행한 뒤 각각 돌려 행 수·체크섬을 비교한 쿼리 (사다리 내장)"
SQL_L6 = "이 단계는 SQL을 돌리지 않고 데이터 카탈로그(OM)에 등록된 내용을 읽어 봅니다."
SQL_NO_CHECK = ("이 task에는 이 단계 검사 쿼리 파일이 없습니다. "
                "verifier가 요구서·contract를 보고 이 task에는 검사를 두지 않았습니다.")
SQL_NOW = "SQL은 지금 파일 기준입니다(시도 당시와 다를 수 있음). 자리 표시({{ project }} 등)는 그대로 두고 프로젝트 ID는 가립니다."
SQL_UNREAD = "파일을 읽지 못했습니다"
HARNESS_CAUSE = "사람이 이 반려를 하네스 쪽 원인으로 분류했습니다(규칙 후보 집계에서 뺌). 반려 건수는 그대로 셉니다."
ITER0_NOTE = "1회차 전에 멈춘 경우는 이 화면에 나오지 않습니다."  # 상세 표 아래 (D-21)
# ----- 용어 서랍 (D-23). 제목은 화면 단어 그대로, 본문 1~2문장. 근거: CLAUDE.md §1·§5, DESIGN.md.
# 결정 번호·문서 절 번호·내부 파일 이름·데이터 값을 넣지 않는다. 본문 속 용어 링크는 두지 않는다(D-30) -----
TERMS_KEY = "terms"  # 서랍 칸 키(주소 #cell=terms)
BLOCKS_KEY = "blocks"  # 위험 명령 차단 서랍 칸 키(주소 #mart=<보던 마트>&cell=blocks, D-27). 마트 보기마다 같은 내용
BLOCKS_LEAD = "AI가 실행하려다 Hook이 막은 명령입니다. 마트에 속하지 않으므로 전체 마트 기준입니다."
# 단계의 다른 이름: 화면에는 RUNG_PLAIN만 쓰고 이 이름들은 용어 서랍에서만 보인다 (D-16)
RUNG_OTHER = {"L0": "계약·구조", "L1": "dry-run", "L2": "개발 실행", "L3": "레이어 게이트", "L4": "정합성",
              "L5": "멱등성", "L6": "OM 등록 확인"}
RUNG_TERM = {
    "L0": "만든 task와 파일 구성이 contract와 같은지 봅니다. 데이터는 아직 읽지 않습니다.",
    "L1": "BigQuery에 실제로 돌리지 않고 SQL 문법과 읽는 양(500 MB 이하)을 봅니다.",
    "L2": "운영이 아닌 개발 데이터셋에서 SQL을 실제로 실행해 테이블이 생기는지 봅니다.",
    "L3": "만든 테이블에 검사 쿼리를 돌려 빈 값·키 중복 같은 문제 행이 없는지 층마다 봅니다.",
    "L4": "원천에서 따로 계산한 건수·합계와 만든 테이블의 값이 맞는지 봅니다.",
    "L5": "같은 날짜로 한 번 더 실행해도 행 수와 내용이 그대로인지 봅니다.",
    "L6": "결재 뒤 운영에서 돌린 다음, 데이터 카탈로그(OM)에 테이블·컬럼 설명·리니지가 등록됐는지 마트 전체를 봅니다.",
}
TERMS = (
    ("흐름", (
        ("하네스", "AI가 데이터 파이프라인을 만들고, 코드가 검사하고, 사람이 결재하도록 묶은 작업 틀입니다. "
                 "이 화면은 하네스가 남긴 기록을 읽어 보여 줍니다."),
        ("마트", "결재자가 요청한 지표를 담는 최종 테이블과 그것을 만드는 파이프라인 한 벌입니다. 위쪽 탭 하나가 마트 하나입니다."),
        ("contract", "요구서와 함께 결재하는 설계도입니다. 만들 테이블·컬럼·task 구성과 완료 조건을 적고, 바꾸려면 다시 결재를 받습니다."),
        ("task", "파이프라인의 한 단계 작업입니다. SQL 파일 하나가 task 하나이고, 자동 검사는 task마다 합니다."),
        ("루프", "AI가 SQL을 쓰고 자동 검사를 받는 반복입니다. 반복 상한을 넘거나 같은 유형의 반려가 이어지면 멈추고 사람을 부릅니다."),
        ("결재 1·2", "결재 1은 요구서와 contract를 승인하는 요구서 PR 머지이고, 결재 2는 AI가 만든 결과를 승인하는 구현 PR 머지입니다. "
                    "둘 다 사람이 합니다."),
        ("PR", "GitHub에서 바뀐 내용을 검토하고 합치자는 요청입니다. 이 화면은 보기 전용이라 결재는 PR에서 합니다."))),
    ("검사", (
        ("사다리", "task마다 L0부터 L5까지 차례로 통과해야 하는 자동 검사 단계입니다. 모두 통과해야 결재 2로 넘어가고, L6는 결재 뒤에 봅니다."),
        *((f"{r} {RUNG_PLAIN[r]}", f"{RUNG_TERM[r]} 다른 이름: {RUNG_OTHER[r]}.") for r in RUNG_PLAIN),
        ("층", "데이터를 다듬는 차례입니다. task 이름 옆 칩 원본 복사·정제·집계가 층이고, L3 층별 품질 검사는 이 층마다 품질을 봅니다."),
        ("반려", "자동 검사가 실패로 판정해 AI에게 돌려보낸 것입니다. R-0001 같은 반려 번호로 남고 반복 수에 셉니다."),
        ("멈춤", "판정하지 않고 루프를 세운 것입니다. contract를 바꿔야 하거나 인프라 오류처럼 사람이 봐야 할 때 멈춥니다."),
        ("시도와 반복", "반복은 루프가 한 바퀴 돈 차례이고, 시도는 한 task가 검사를 받은 차례입니다. "
                      "\"2번째 시도 (루프 반복 3)\"처럼 함께 적습니다."))),
    ("측정", (
        ("본 측정·유지보수", "본 측정은 첫 결재 2까지의 사람 개입과 비용이고, 유지보수는 그 뒤에 생긴 개입입니다. 숫자 카드는 본 측정 기준입니다."),
        ("정가 환산", "AI 사용량(토큰)을 공개 정가로 계산한 추정 금액입니다. 실제 청구액이 아닙니다."),
        ("Hook", "AI가 명령을 실행하거나 파일을 쓰기 전에 규칙을 검사하는 자동 차단 장치입니다. 운영 데이터 쓰기 같은 위험한 명령을 막습니다."),
        ("builder·verifier", "builder는 SQL과 task를 만드는 AI이고, verifier는 요구서와 contract만 보고 검사 쿼리를 먼저 쓰는 AI입니다. "
                             "통과 판정은 둘 다 하지 않고 코드가 합니다."),
        ("승격", "되풀이된 실패에서 나온 규칙 후보를 사람이 결재해 팀 규칙으로 올리는 것입니다. 결재 전에는 규칙 후보로 남습니다."),
        ("MB", "바이트를 2진으로 센 단위입니다. 1 MB = 1,048,576바이트이고 BigQuery 콘솔과 같은 계산입니다."))),
)


def e(value):
    """모든 글자는 여기를 거친다. 따옴표도 바꾼다(속성 값에 써도 안전)."""
    return html.escape("" if value is None else str(value), quote=True)


def icon(name):
    """아이콘 1개 (D-36). 꾸밈이므로 aria-hidden이고, 상태 글자는 옆의 보이는 글자·.vh·aria-label 중 하나가 맡는다."""
    if name not in ICONS:
        raise KeyError(name)
    return f"<svg class='ic' aria-hidden='true' focusable='false'><use href='#i-{name}'/></svg>"


GITHUB = "https://github.com/"  # 외부 링크는 이 주소로 시작할 때만 만든다 (D-29, remote에서 만든 주소)
NEW_TAB = "새 탭에서 열림"  # 외부 링크 ↗ 옆 숨은 글자 (D-29)


def ext_link(url, html_, cls="lk ext"):
    """외부 링크(이동 모양 + ↗ 아이콘, 새 탭, rel="noopener noreferrer", .vh "새 탭에서 열림", D-24·D-29).
    html_은 이미 escape한 글자. 주소가 GitHub(remote에서 만든 주소)가 아니면 링크 없이 글자만."""
    if not isinstance(url, str) or not url.startswith(GITHUB):
        return html_
    return (f"<a class='{cls}' href='{e(url)}' target='_blank' rel='noopener noreferrer'>{html_}{icon('ext')}"
            f"<span class='vh'>{e(NEW_TAB)}</span></a>")


def commit_url(header):
    """기준 커밋의 GitHub 주소(전체 해시). remote가 없거나 해시가 아니면 None."""
    repo, commit = header.get("repo_url"), header.get("commit")
    if not repo or not isinstance(commit, str) or not re.fullmatch(r"[0-9a-f]{40}", commit):
        return None
    return f"{repo}/commit/{commit}"


def icon_defs(page):
    """page에서 실제로 쓴 아이콘의 <symbol>만 숨은 SVG 하나로(ICONS 순서). 쓰지 않는 symbol은 내보내지 않는다."""
    used = set(re.findall(r"<use href='#i-([a-z]+)'/>", page))
    syms = "".join(f"<symbol id='i-{k}' viewBox='0 0 16 16'>{v}</symbol>" for k, v in ICONS.items() if k in used)
    return f"<svg class='ic-defs' aria-hidden='true' focusable='false'>{syms}</svg>" if syms else ""


def badge(variant, html_, icon_name=None, size=None, cls="", attrs=""):
    """Badge 1종 (D-33·D-35): 알약, 13px·600(size="lg"면 14px·700), 옅은 바탕 + 진한 글자. html_은 이미 escape한 HTML.
    상태 Badge는 icon_name을 반드시 주고, 분류 Badge(tag)는 주지 않는다."""
    if variant not in VARIANTS:
        raise ValueError(variant)
    names = " ".join(x for x in ("bd", variant, "lg" if size == "lg" else "", cls) if x)
    return f"<span class='{names}'{attrs}>{icon(icon_name) if icon_name else ''}{html_}</span>"


def state_badge(state, text=None, extra="", size=None):
    """상태 글자의 Badge: STATE의 variant·아이콘 + 글자(색만으로 구분하지 않는다)."""
    variant, name = STATE.get(state, ("neutral", "wait"))
    return badge(variant, e(text or state) + (f" {e(extra)}" if extra else ""), name, size)


def tag(html_):
    """분류 Badge: 아이콘 없는 neutral (층 칩, 역할 칩, "전체 마트"(차단 카드), 반려 유형·분류, "하네스 원인" 등). html_은 escape한 HTML."""
    return badge("neutral", html_)


def status_dot(variant, icon_name):
    """StatusDot 1종 (D-35): 진행 단계 행·마트 탭·전체 보기 단계 표. 모양 = 아이콘, 색 = variant 색. 상태 글자는 옆 .vh."""
    if variant not in VARIANTS:
        raise ValueError(variant)
    return f"<span class='sd-dot {variant}'>{icon(icon_name)}</span>"


# ---------- 숫자 서식 (숫자가 아니면 그대로 돌려준다: "기록 없음") ----------

def is_number(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def fmt_int(v):
    """개수는 줄이지 않고 쉼표 원값(26,431, D-38)."""
    return f"{v:,}" if is_number(v) else v


def fmt_mb(v):
    """바이트 → MB(2진, 1 MB = 1,048,576바이트). 영문 단위만 띄운다("161.7 MB")."""
    return f"{v / MB:,.1f} MB" if is_number(v) else v


def fmt_usd(v):
    """"$1.23". 0보다 크고 0.01달러 미만이면 "< $0.01"."""
    if not is_number(v):
        return v
    return "< $0.01" if 0 < v < 0.01 else f"${v:,.2f}"


def kst(v):
    """ISO 시각 → KST datetime. 시각이 아니면 None. 시간대가 없는 값은 KST로 본다."""
    try:
        t = datetime.fromisoformat(v)
    except (TypeError, ValueError):
        return None
    return t.astimezone(dd.KST) if t.tzinfo else t.replace(tzinfo=dd.KST)


def fmt_date(v):
    """ISO 시각 → "11/4"(올해가 아니면 "2025/11/4"). 시각이 아니면 그대로."""
    t = kst(v)
    if t is None:
        return v
    year = "" if t.year == datetime.now(dd.KST).year else f"{t.year}/"
    return f"{year}{t.month}/{t.day}"


def fmt_time(v):
    """ISO 시각 → KST 24시간제 "11/4 08:48"(시간대 표기 없음, 올해가 아니면 연도, D-38). 시각이 아니면 그대로."""
    t = kst(v)
    return v if t is None else f"{fmt_date(v)} {t:%H:%M}"


def fmt_full(v):
    """title에 남기는 시각의 전체 값 "2026-11-02 15:44:40"(KST, D-49). 시각이 아니면 그대로."""
    t = kst(v)
    return v if t is None else f"{t:%Y-%m-%d %H:%M:%S}"


def fmt_cost(field, v):
    return fmt_mb(v) if field.endswith("_bytes_processed") else fmt_usd(v) if field.endswith("_usd") else fmt_int(v)


def consecutive(ids):
    nums = [int(m.group(1)) for m in (re.fullmatch(r"[A-Z]+-(\d+)", x) for x in ids) if m]
    return len(ids) > 1 and len(nums) == len(ids) and nums == list(range(nums[0], nums[0] + len(nums)))


def id_range(ids):
    """뺀 id가 연속이면 "B-0003 ~ B-0010 (8건)"으로 줄인다."""
    if len(ids) > 2 and consecutive(ids):
        return f"{ids[0]} ~ {ids[-1]} ({len(ids)}건)"
    return ", ".join(ids)


def id_span(ids):
    """연속이면 "H-0008~H-0010", 아니면 쉼표로 잇는다."""
    return f"{ids[0]}~{ids[-1]}" if consecutive(ids) else ", ".join(ids)


# ---------- 작은 조각 ----------

def num(key, value, shown=None):
    """화면 숫자. key는 머리말 "data-k 계약"의 꼴 하나, value는 그 --json 자리의 값(data-v). 숫자 title은 두지 않는다(D-49)."""
    return (f"<span class='num' data-k='{e(key)}' data-v='{e(value)}'>"
            f"{e(fmt_int(value) if shown is None else shown)}</span>")


def hidden_num(key, value):
    return f"<span hidden data-k='{e(key)}' data-v='{e(value)}'></span>"


def label(key):
    """내부 키를 표시 이름으로(원래 키는 --json에 있다, title 없음 D-49)."""
    return e(LABELS.get(key, key))


def m3_label(value):
    """M3 분류(08)를 사람 말로. 분류가 없으면("기록 없음") 그대로 보인다. 분류 값은 --json에 그대로."""
    return e(M3_LABELS.get(value, value))


def tip_time(iso):
    """시각 title: 전체 값(D-49). 시각이 아니면(기록 없음) title을 두지 않는다."""
    full = fmt_full(iso)
    return f" title='{e(full)}'" if full != iso else ""


def when(iso):
    return f"<span{tip_time(iso)}>{e(fmt_time(iso))}</span>"


def when_rel(iso, shown=None):
    """절대 시각 + 원시 시각(data-t). "· 6일 전"은 JS가 그릴 때 붙인다(생성 때 HTML에 쓰지 않음, D-43)."""
    return f"<span{tip_time(iso)} data-t='{e(iso)}'>{e(fmt_time(iso) if shown is None else shown)}</span>"


def ident(value):
    """고정폭 글꼴은 이름·ID·파일 경로에만. 그 밖의 근거("반복 3", "기록 없음")는 본문 글꼴."""
    return e(value) if value == dd.NONE or value.startswith("반복") else f"<code>{e(value)}</code>"


def table(head, rows, right=(), total=False):
    """right는 오른쪽 정렬할 열 번호. total이면 마지막 행이 합계."""
    def cls(i):
        return " class='r'" if i in right else ""
    th = "<thead><tr>" + "".join(f"<th scope='col'{cls(i)}>{h}</th>" for i, h in enumerate(head)) + "</tr></thead>" \
        if head else ""
    trs = []
    for n, r in enumerate(rows):
        tr = " class='sum'" if total and n == len(rows) - 1 else ""
        trs.append(f"<tr{tr}>" + "".join(f"<td{cls(i)}>{c}</td>" for i, c in enumerate(r)) + "</tr>")
    return f"<div class='scroll'><table class='t'>{th}<tbody>{''.join(trs)}</tbody></table></div>"


def sid(key, mart, many):
    """구역 id. 마트가 여럿이면 마트 이름을 붙인다(data-section은 그대로)."""
    return f"{key}-{mart}" if many else key


def section(key, inner, aside="", title=None, ident_=None):
    side = f"<span class='aside'>{aside}</span>" if aside else ""
    return (f"<section id='{e(ident_ or key)}' data-section='{key}'><div class='sec-h'><h2>"
            f"{e(title or dict(SECTIONS)[key])}</h2>{side}</div>{inner}</section>")


def folded(key, inner, aside, ident_=None):
    """접힘 영역. 펼친 상태는 data-cell로 새로고침 뒤에도 이어진다."""
    name = ident_ or key
    return (f"<section id='{e(name)}' data-section='{key}' class='card fold'><details data-cell='section:{e(name)}'>"
            f"<summary class='tw'>{icon('tri')}{e(dict(SECTIONS)[key])}<span class='aside'>{e(aside)}</span></summary>"
            f"<div class='fold-body'>{inner}</div></details></section>")


def kv(pairs):
    return "<dl class='kv'>" + "".join(f"<dt>{e(k)}</dt><dd>{v}</dd>" for k, v in pairs) + "</dl>"


def requester(value, prefix=" · 요청자 "):
    """값이 없으면(-) 줄째 숨긴다."""
    return "" if value == dd.DASH else f"{prefix}{e(value)}"


# ---------- 사람 할 일 ----------

def todo_items(d):
    """사람 할 일을 마트 단위 한 줄씩. collect()의 queue·l6_check를 그대로 옮긴다."""
    q, out = d["queue"], []

    def add(key, mart, detail):
        out.append({"key": key, "mart": mart, "detail": detail})
    for x in q["approval_1"]:
        add("approval_1", x["mart"], requester(x["requested_by"], "요청자 "))
    for x in q["approval_2"]:
        add("approval_2", x["mart"], f"PR {e(x['pr'])}")
    for x in q["halted"]:
        add("halted", x["mart"], "이유: " + label(x["halt_reason"]))
    for m, x in d["marts"].items():
        if x["l6_check"]["recheck"]:
            add("l6_recheck", m, e("; ".join(x["l6_check"]["reasons"])))
    for x in q["l6_reject"]:
        add("l6_reject", x["mart"], "근거 " + ident(x["basis"]))
    return out


def todo_chips(items, prefix, mart=None):
    """상태 배지 옆 칩. 0이 아닌 항목만 보이고, 0건 항목의 수는 숨은 data 칸으로 남긴다."""
    zeros = "".join(hidden_num(f"{prefix}.{k}", 0) for k, *_ in TODO if not any(x["key"] == k for x in items))
    chips = []
    for key, name, kind in TODO:
        n = sum(1 for x in items if x["key"] == key)
        if n:
            attr = f" data-todo='{key}'" + (f" data-recheck='{e(mart)}'" if key == "l6_recheck" and mart else "")
            chips.append(badge(kind, f"{e(name)} {num(f'{prefix}.{key}', n)}", TODO_ICON[key], attrs=attr))
    return "".join(chips) + zeros


def head_line(ident_, loc, title, badge_html, chips, right="", why="", below=""):
    """머리 한 줄(flex-wrap): 위치 표시 · 제목 · 상태 배지(+칩) · 오른쪽 끝 마지막 확인. 이유는 바로 아래 한 줄.
    id·data-section='queue'(사람 할 일 구역)를 여기에 둔다."""
    tail = f"<span class='head-when'>{right}</span>" if right else ""
    reason = f"<p class='head-why'>{why}</p>" if why else ""
    return (f"<section id='{e(ident_)}' data-section='queue' class='head'><h2 class='vh'>{e(dict(SECTIONS)['queue'])}</h2>"
            f"<div class='head-row'><span class='head-loc'>{loc}</span><h1 class='head-t' tabindex='-1'>{title}</h1>"
            f"{badge_html}{chips}{tail}</div>{reason}{below}</section>")


FAIL_KEYS = ("halted", "l6_reject")


def fail_icon(keys):
    """막힌 할 일의 아이콘: 루프 멈춤이 있으면 멈춤(네모), L6 반려만이면 반려(X)."""
    return "halt" if "halted" in keys else "fail"


def band_word(m, items):
    """상태 배지 (종류, 모양, 한 단어) (D-19). 사람 할 일 중 멈춤·L6 반려 → 멈춤 / 그 밖의 사람 할 일 → 대기 / 모든 단계 완료 → 완료
    / 지금 단계가 멈춤·반려 → 멈춤 / AI 진행 중 → 진행 / 그 밖 → 대기. 모양·색은 그대로(아이콘은 T4)."""
    cur = next((s for s in m["stages"] if s["current"]), None)
    fails = [x["key"] for x in items if x["key"] in FAIL_KEYS]
    if fails:
        return "fail", fail_icon(fails), "멈춤"
    if items:
        return "todo", "todo", "대기"
    if cur is None:
        return "pass", "pass", "완료"
    if cur["state"] in (dd.HALT, dd.REJECT):
        return "fail", STATE[cur["state"]][1], "멈춤"
    return ("neutral", "run", "진행") if cur["state"] == dd.ACTIVE else ("neutral", "wait", "대기")  # 회색, 아이콘으로 구분


def progress_text(stages):
    """공식 앞부분 "[마지막 완료 단계]까지 완료 · [다음 단계] 대기/멈춤". 지금 단계가 멈춤·반려면 "루프 멈춤"만(D-19 예).
    단계 이름은 진행 단계 카드의 이름 그대로."""
    i = next((k for k, s in enumerate(stages) if s["current"]), None)
    if i is None:
        return f"{stages[-1]['name']}까지 완료" if stages else dd.NONE
    cur = stages[i]
    now = f"{cur['name']} {cur['state']}"
    if cur["state"] in (dd.HALT, dd.REJECT) or i == 0:
        return now
    return f"{stages[i - 1]['name']}까지 완료 · {now}"


LINK_OF = {"approval_1": "request_pr", "approval_2": "impl_pr"}  # 결재 대기 → 그 결재의 PR 링크 (D-05)
LINK_NAME = {"request_pr": "요구서 PR", "impl_pr": "구현 PR"}


def act_link(key, links):
    """[행동] 한 개. 결재 1·2 대기이고 그 PR의 주소가 있으면 주요 링크("구현 PR 머지 #38 ↗", D-05), 아니면 글자 그대로."""
    pr = (links or {}).get(LINK_OF.get(key))
    if pr and pr.get("url"):
        return ext_link(pr["url"], e(f"{ACTION[key]} #{pr['number']}"), "lk ext main")
    return e(ACTION[key])


def todo_text(items, key, links=None):
    """공식 뒷부분 "사람이 할 일 N건: [행동]"(0건이면 "사람이 할 일 없음"). N은 data-k key의 화면 숫자.
    links(마트의 links)가 있으면 결재를 기다리는 PR을 [행동] 자리에 주요 링크로 올린다(D-05)."""
    if not items:
        return e("사람이 할 일 없음") + hidden_num(key, 0)
    acts = [act_link(k, links) for k, *_ in TODO if any(x["key"] == k for x in items)]
    return f"사람이 할 일 {num(key, len(items))}건: {', '.join(acts)}"


def promoted(items):
    """주요 링크로 올라간 링크 이름(request_pr·impl_pr)."""
    return {LINK_OF[x["key"]] for x in items if x["key"] in LINK_OF}


NEXT_TITLE = "다음 행동"  # 진행 단계 아래 카드 (D-44)
NO_LINKS = "링크 없음 · GitHub 주소를 읽지 못함"  # 다음 행동 카드에 링크가 하나도 없을 때


def sub_links(header, links, skip=()):
    """보조 링크 (D-05): 요구서 PR · 구현 PR · 기준 커밋. 주요 링크로 올라간 것(skip)은 뺀다. 주소가 없는 링크는 칸째 없다."""
    bits = []
    for k in ("request_pr", "impl_pr"):
        pr = (links or {}).get(k)
        if k not in skip and pr and pr.get("url"):
            bits.append(ext_link(pr["url"], e(f"{LINK_NAME[k]} #{pr['number']}")))
    url = commit_url(header)
    if url:
        bits.append(ext_link(url, f"커밋 <code>{e(header['commit'][:7])}</code>"))
    return bits


def render_next(header, m, mine):
    """다음 행동 카드 (D-44 왼쪽, 진행 단계 카드 아래): 링크 세로 목록(한 줄에 하나). 할 일이 있으면 머리 상태 문구의 주요 링크와
    같은 링크를 맨 위에(이동 모양 그대로), 그 아래 보조 링크(요구서 PR · 구현 PR · 커밋, T9가 머리 아래 줄에 두던 것).
    링크가 하나도 없으면 NO_LINKS 한 줄. 데이터 값은 없다(PR 번호·커밋 해시만)."""
    links = m.get("links")
    main_ = [act_link(k, links) for k, *_ in TODO if k in LINK_OF and any(x["key"] == k for x in mine)]
    bits = [a for a in main_ if a.startswith("<a")] + sub_links(header, links, promoted(mine))
    body = (f"<ul class='nx-l' data-links>{''.join(f'<li>{b}</li>' for b in bits)}</ul>" if bits
            else f"<p class='note' data-no-links>{e(NO_LINKS)}</p>")
    return f"<section class='card nexts' aria-label='{e(NEXT_TITLE)}'><h2>{e(NEXT_TITLE)}</h2>{body}</section>"


def band_html(kind, mark, word, text):
    """상태 배지(Badge lg, 아이콘 + 한 단어, D-33) + 배지 뒤 상태 문구(이미 escape한 HTML)."""
    return (badge(kind, f"<span class='sb-t'>{e(word)}</span>", mark, "lg", attrs=f" data-band='{kind}' role='status'")
            + f"<span class='head-st' data-status>{text}</span>")


def mart_band(mart, m, items, prefix):
    """마트 하나의 상태 배지와 문구 (D-19). (배지·문구 HTML, 이유 HTML)"""
    kind, mark, word = band_word(m, items)
    text = f"{e(progress_text(m['stages']))} · {todo_text(items, prefix + '.total', m.get('links'))}"
    fails = [x for x in items if x["key"] in FAIL_KEYS]
    return band_html(kind, mark, word, text), (fails[0]["detail"] if fails else "")


def mart_rank(m, mine):
    """전체 보기 정렬 (D-46): 사람 할 일 0 → 막힘 1 → 진행 중(대기 포함) 2 → 완료 3. 같으면 마트 순서(sorted는 안정 정렬)."""
    if any(x["key"] not in FAIL_KEYS for x in mine):
        return 0
    kind = band_word(m, mine)[0]
    return 1 if kind == "fail" else 3 if kind == "pass" else 2


def overview_marts(d, items):
    """전체 보기 마트별 한 줄 카드 (D-46): 상태 배지 + 상태 문구(D-19, 할 일이 있고 PR 주소가 있으면 주요 링크) → 누르면 그 마트 보기.
    카드 안에 주요 링크가 있으면 카드 전체를 링크로 만들지 않고 마트 이름 링크(이동 모양) + 주요 링크, 없으면 카드 전체가
    열기 모양 링크다(링크 안 링크 금지, D-27)."""
    rows = []
    for mart, m in d["marts"].items():
        mine = [x for x in items if x["mart"] == mart]
        kind, mark, word = band_word(m, mine)
        status = f"{e(progress_text(m['stages']))} · {todo_text(mine, f'{mart}.queue.total', m.get('links'))}"
        bd = badge(kind, e(word), mark)
        if "<a " in status:
            inner = (f"<div class='ml-in'>{bd}<a class='lk ml-n' href='#mart={e(mart)}'><code>{e(mart)}</code></a>"
                     f"<span class='ml-s'>{status}</span></div>")
        else:
            inner = (f"<a class='op ml-in' href='#mart={e(mart)}'>{bd}<code class='ml-n'>{e(mart)}</code>"
                     f"<span class='ml-s'>{status}</span><span class='chev'>{icon('chev')}</span></a>")
        rows.append((mart_rank(m, mine), f"<li class='card mline' data-line='{e(mart)}'>{inner}</li>"))
    lis = "".join(html_ for _, html_ in sorted(rows, key=lambda x: x[0]))
    return f"<ul class='mlines' aria-label='마트별 상태'>{lis}</ul>"


def overview_cards(d):
    """전체 보기 합계 숫자 카드 (D-46): 더할 수 있는 지표만 — 반려 · 사람 개입 시간 · 사람 결재 · 비용 · 위험 명령 차단. 반복 횟수는
    마트별 비율이라 뺀다. 값은 collect()의 전체 값(all.*)과 반려 수(rejections.count)이고 새로 계산하지 않는다. 마트별로 나뉘는
    반려·개입·결재·비용은 누를 수 없고, 차단만 서랍(cell=blocks)."""
    g = d["summary"]
    rej = sum(len(m["rejections"]) for m in d["marts"].values())
    cost, m11 = g["M4"]["total_cost_usd"], g["M11"]["count"]
    hot = any(blocked(m) for m in d["marts"].values())
    blocks = f" data-open='{BLOCKS_KEY}' aria-haspopup='dialog'" if m11 else ""
    cards = (card("반려", f"{num('rejections.count', rej)}<small>건</small>", "", foot=e("자동 검사가 돌려보낸 횟수"), hot=hot),
             card("사람 개입 시간", f"{num('all.M1_minutes_main', g['M1_minutes_main'])}<small>분</small>", ""),
             card("사람 결재", f"{num('all.M12_main', g['M12_main'])}<small>건</small>", ""),
             card("비용", num("all.M4.total_cost_usd", cost, fmt_usd(cost)), "", foot=e("정가 환산 추정 · 실제 청구액 아님")),
             card("위험 명령 차단", f"{num('all.M11.count', m11)}<small>건</small>{tag(e(ALL_MARTS))}", "",
                  foot=e("AI가 실행하려다 Hook이 막은 명령"), act=blocks, ident_=safe_id("k", "all", 5)))
    return (f"<section id='cards-all' data-section='cards' aria-label='합계 숫자 카드' class='kpis'>"
            f"<p class='kpi-basis'>{e(KPI_BASIS)} · 마트 합계</p>{''.join(cards)}</section>")


def overall_band(d, items):
    """전체 보기의 상태 배지·문구(마트 합계, D-19). 마트별 한 줄은 overview_marts."""
    n = len(d["marts"])
    words = [band_word(m, [x for x in items if x["mart"] == mart]) for mart, m in d["marts"].items()]
    done = sum(1 for m in d["marts"].values() if not any(s["current"] for s in m["stages"]))  # 모든 단계 완료한 마트
    stopped = [mk for _, mk, w in words if w == "멈춤"]
    if stopped:
        kind, mark, word = "fail", ("halt" if "halt" in stopped else "fail"), "멈춤"
    elif items:
        kind, mark, word = "todo", "todo", "대기"
    elif done == n:
        kind, mark, word = "pass", "pass", "완료"
    else:
        kind, mark, word = ("neutral", "run", "진행") if any(w == "진행" for _, _, w in words) else ("neutral", "wait", "대기")
    last = dd.STAGE_NAMES[-1]
    head = f"마트 {n}개 모두 {last}까지 완료" if done == n else f"마트 {n}개 중 {done}개 {last}까지 완료"
    return band_html(kind, mark, word, f"{e(head)} · {todo_text(items, 'queue.total')}")


def todo_groups(items):
    """사람 할 일을 마트별로 묶어 보인다(전체 보기)."""
    names = dict((k, (n, kind)) for k, n, kind in TODO)
    marts = list(dict.fromkeys(x["mart"] for x in items))
    out = []
    for mart in marts:
        lis = []
        for x in (y for y in items if y["mart"] == mart):
            name, kind = names[x["key"]]
            attr = f" data-recheck='{e(mart)}'" if x["key"] == "l6_recheck" else ""
            lis.append(f"<li{attr}>{badge(kind, e(name), TODO_ICON[x['key']])} {x['detail']}</li>")
        out.append(f"<div class='card group' data-group='{e(mart)}'><h3><a class='lk' href='#mart={e(mart)}'><code>{e(mart)}</code>"
                   f"</a></h3><ul>{''.join(lis)}</ul></div>")
    return f"<div class='groups'>{''.join(out)}</div>" if out else ""


def waiting_since(m, key):
    """사람 할 일 key가 기다리기 시작한 시각 = 그 할 일이 걸린 단계 바로 앞 단계의 done_at. 못 찾으면 None."""
    stages = m["stages"]
    name = WAIT_STAGE.get(key) or next((s["name"] for s in stages if s["current"]), None)
    i = next((i for i, s in enumerate(stages) if s["name"] == name), 0)
    if i <= 0:
        return None
    try:
        return datetime.fromisoformat(stages[i - 1]["done_at"]).timestamp()
    except (TypeError, ValueError):
        return None


def first_mart(d, items):
    """처음 열 때(이 탭에 저장된 보기가 없을 때) 고를 마트 (D-04 ③). 마트가 여럿이고 사람 할 일이 있을 때만.
    가장 오래 기다린 마트(기다리기 시작한 시각이 가장 이른 것), 시각을 못 찾은 마트는 그 뒤에 마트 순서로."""
    if len(d["marts"]) < 2 or not items:
        return None
    order = list(d["marts"])
    since = {}
    for x in items:
        t = waiting_since(d["marts"][x["mart"]], x["key"])
        since.setdefault(x["mart"], [])
        if t is not None:
            since[x["mart"]].append(t)
    return min(since, key=lambda m: (not since[m], min(since[m], default=0), order.index(m)))


# ---------- 위쪽 막대 (브랜드 · 마트 탭 · 생성 시각) ----------

def tab_state(m, mine):
    """마트 탭의 (종류, 아이콘, 글자). 머리 한 줄의 상태 배지와 같은 다섯 경우: 멈춤(L6 반려는 반려) / 사람 할 일 / 완료 /
    진행 중 / 대기."""
    names = dict((k, n) for k, n, _ in TODO)
    fails = [x for x in mine if x["key"] in FAIL_KEYS]
    if fails:
        return "fail", fail_icon([x["key"] for x in fails]), names[fails[0]["key"]]
    if mine:
        return "todo", "todo", f"사람 할 일 {len(mine)}건"
    cur = next((s for s in m["stages"] if s["current"]), None)
    if cur is None:
        return "pass", "pass", dd.DONE
    kind, mark = STATE.get(cur["state"], ("neutral", "wait"))  # 멈춤·반려 = 빨강, 진행 중·대기 = 회색(아이콘으로 구분)
    return kind, mark, f"{cur['name']} {cur['state']}"


def render_terms():
    """용어 서랍 (D-23): 화면 전체에 하나(마트 보기 밖). 지금 서랍과 같은 div 패널·같은 열기/닫기/주소 규칙(#cell=terms)을 쓰고,
    다른 서랍이 열려 있으면 바꿔 연다(dialog는 T5). 첫 줄은 흐름 문구, 그 아래 흐름·검사·측정 세 묶음(가나다순 아님)."""
    groups = "".join(
        f"<section class='dp-sec' data-term-group='{e(name)}'><h4>{e(name)}</h4><dl class='terms'>"
        + "".join(f"<dt>{e(t)}</dt><dd>{e(body)}</dd>" for t, body in rows) + "</dl></section>"
        for name, rows in TERMS)
    detail_ = (f"<div class='detail' data-detail='{TERMS_KEY}' data-terms aria-label='용어'>"
               f"<h3 class='dp-t' tabindex='-1'>용어</h3><p class='lead' data-flow>{e(FLOW)}</p>{groups}</div>")
    return (f"<div class='dpanel' id='terms-panel' data-panel role='dialog' aria-modal='false' aria-label='용어'>"
            f"<div class='dp-bar'><span class='eyebrow'>용어</span><button type='button' class='dp-x more' data-close "
            f"aria-label='용어 닫기'>닫기</button></div>"
            f"<div class='dp-body'>{detail_}</div></div>")


THEMES = (("auto", "자동"), ("light", "밝게"), ("dark", "어둡게"))  # 테마 토글 (D-14): data-theme-set 값과 글자


def render_theme():
    """테마 토글 (D-14): 자동·밝게·어둡게 버튼 그룹(aria-pressed). JS가 있을 때만 보인다(html.js). aria-pressed는 head 테마
    스크립트가 고른 값을 본문 끝 JS가 단다(처음엔 모두 false)."""
    btns = "".join(f"<button type='button' class='more' data-theme-set='{k}' aria-pressed='false'>{t}</button>" for k, t in THEMES)
    return f"<span class='theme' role='group' aria-label='화면 테마'>{btns}</span>"


def render_header(d, items):
    """위쪽 막대 오른쪽: [용어] 버튼(D-23, 640px 이하에서도 보인다) · 보기 전용 배지(D-06) · 새 기록 안내(aria-live, 처음엔 비어 있음) · 자동 갱신 표시와 데이터 시각(D-10)
    · 일시정지 버튼 · 기준 커밋 · 테마 토글(D-14, 640px 이하에서도 보인다). 갱신 상태 글자와 버튼은 JS가 채우고 보인다(JS가 없으면 "데이터 … 기준"만).
    contract 버전과 전체 합계 건수는 숨은 글자·data 칸으로 남긴다."""
    h = d["header"]
    commit = h["commit"]
    short = commit[:12] if commit != dd.NONE else commit
    shown_commit = f"<code>{num('header.commit', commit, short)}</code>"  # remote가 있으면 GitHub 커밋 링크 (D-05)
    versions = ", ".join(f"{m} v{v}" for m, v in h["contracts"].items()) or dd.NONE
    at = h["generated_at"]
    rej = sum(len(m["rejections"]) for m in d["marts"].values())
    rules = len(d["rules"]["learned"]) + len(d["rules"]["candidates"])
    return (f"<section id='header' data-section='header' class='gen'>"
            f"<h2 class='vh'>{e(dict(SECTIONS)['header'])}</h2>"
            f"<button type='button' class='terms-btn more' data-open='{TERMS_KEY}' aria-haspopup='dialog' "
            f"aria-controls='terms-panel' aria-expanded='false'>용어</button>"
            f"{badge('neutral', e(READ_ONLY), attrs=' data-ro')}"  # 분류 Badge (D-06·D-35)
            f"<span class='newrec'><span class='live' data-live aria-live='polite'></span>"
            f"<button type='button' class='more' id='dash-refresh-now' data-refresh-now hidden>새로고침</button></span>"
            f"<span class='rstate'><span data-refresh-state></span>데이터 {num('header.generated_at', at, fmt_time(at))} 기준</span>"
            f"<button type='button' class='more' id='dash-pause' data-pause hidden>{icon('pause')}"
            f"<span data-pause-t>일시정지</span></button>"  # 일시정지 아이콘 (D-36), 다시 켜기는 글자만
            f"<span class='cm'>커밋 {ext_link(commit_url(h), shown_commit)}</span>"
            f"{render_theme()}"
            f"<span class='vh'>contract 버전 {e(versions)}</span>"
            f"{hidden_num('queue.total', len(items))}{hidden_num('rejections.count', rej)}{hidden_num('rules.total', rules)}"
            f"</section>")


def render_topbar(d, items):
    """흰 막대(sticky): 왼쪽 브랜드·흐름 문구, 가운데 마트 탭(마트가 여럿이면 "전체" 먼저), 오른쪽 보기 전용·자동 갱신·커밋."""
    many = len(d["marts"]) > 1
    tabs = []
    if many:
        tabs.append("<a href='#mart=all' class='tab' data-view-link='all'>전체</a>")
    for mart, m in d["marts"].items():
        kind, mark, text = tab_state(m, [x for x in items if x["mart"] == mart])
        cls, cur = ("tab", "") if many else ("tab on", " aria-current='page'")  # contract 버전·요청자는 머리에 보인다(title 없음)
        tabs.append(f"<a href='#mart={e(mart)}' class='{cls}'{cur} data-view-link='{e(mart)}'>"
                    f"<code>{e(mart)}</code>{status_dot(kind, mark)}"
                    f"<span class='vh'>{e(text)}</span></a>")
    nav = f"<nav class='tabs' aria-label='마트'>{''.join(tabs)}</nav>" if tabs else ""
    return (f"<header class='top'><div class='top-in'><div class='brand'><b>파이프라인 하네스</b></div>"
            f"{nav}{render_header(d, items)}</div></header>")


# ---------- 숫자 카드 ----------

def tags(prefix, mapping):
    """종류별 수(반려 유형 등)를 분류 Badge로."""
    return " ".join(tag(f"{e(LABELS.get(k, k))}&nbsp;{num(f'{prefix}.{k}', v)}") for k, v in mapping.items()) or e(dd.NONE)


def harness_note(prefix, rejections):
    """제외 목록에 있는 반려 수. M2 값은 그대로 두고 옆에 따로 보인다."""
    n = sum(1 for r in rejections if r["harness_cause"])
    return f" · 하네스 원인 {num(prefix + '.rejections.harness', n)}건" if n else ""


KPI_BASIS = "결재 2까지 기준"  # 숫자 카드 묶음 위 한 번 (D-20)
ALL_MARTS = "전체 마트"  # 차단 카드 숫자 옆 분류 태그(아이콘 없음, D-35·D-45)


def row_halted(row):
    return {v["iteration"] for v in row["verdicts"] if v["verdict"] == "halt"}


def blocked(m):
    """그 마트에 지금 막힌 것(현재 반려·멈춤)이 있는가 (D-34): 진행 단계가 멈춤·반려이거나 사다리 칸의 마지막 결과가 반려·멈춤."""
    if any(s["state"] in (dd.HALT, dd.REJECT) for s in m["stages"]):
        return True
    return any(cell_state(row["cells"][k], row_halted(row)) in (dd.REJECT, dd.HALT)
               for row in m["grid"]["rows"] for k in dd.LADDER_RUNGS)


def rejection_now(m, r):
    """반려 r이 지금 막고 있는가 (D-34): 그 칸의 마지막 결과가 이 반려(같은 반복)다. L6는 마지막 확인이 반려이고 r이 마지막
    L6 반려다. 아니면 지난 반려(회색)."""
    rung = r["caught_by_rung"]
    if rung not in dd.LADDER_RUNGS:
        l6 = [x for x in m["rejections"] if x["caught_by_rung"] == rung]
        return m["l6_check"]["verdict"] == "reject" and bool(l6) and l6[-1] is r
    row = next((x for x in m["grid"]["rows"] if x["task"] == r["task"]), None)
    items = row["cells"].get(rung, []) if row else []
    return bool(items) and cell_state(items, row_halted(row)) == dd.REJECT and items[-1]["iteration"] == r["iteration"]


def card(title, value, visual, detail="", foot="", count="", hot=False, act="", ident_=""):
    """숫자 카드 1장: 라벨 → 값 → 시각 막대 → 세부(종류별 수, 이미 escape한 HTML) → 아래 줄(묶음 기준 KPI_BASIS와 다른 것만,
    이미 escape한 HTML, D-20). count는 라벨 뒤 " · N건". hot이면 값이 --fail-ink(지금 막힌 것이 있을 때의 반려 수, D-34).
    카드·aria에 사전 등록 지표 번호·내부 말을 쓰지 않는다.
    act(누르면 할 일의 속성, D-27)가 있으면 카드 전체가 <button> 하나(열기 모양, 오른쪽 위 ›)이고, 없으면(0건) 누를 수 없는 div.
    button 안에는 블록 요소를 넣을 수 없으므로 안쪽은 모두 span이고(CSS로 줄을 나눈다) 카드 안에 다른 링크·버튼이 없다.
    스크린 리더는 카드를 "반려 1건 자동 검사가 돌려보낸 횟수"처럼 한 덩어리 이름으로 읽는다."""
    more = f" · {count}" if count else ""
    det = f"<span class='kdet'>{detail}</span>" if detail else ""
    low = f"<span class='foot'>{foot}</span>" if foot else ""
    inner = (f"<span class='label'><span>{e(title)}</span>{more}</span>"
             f"<span class='value{' is-blocked' if hot else ''}'>{value}</span>{visual}{det}{low}")
    if act:  # id = k-<마트>-<순번>: 자동 갱신 뒤 키보드 포커스 되살리기가 칸·단계 행과 구분한다
        idattr = f" id='{e(ident_)}'" if ident_ else ""
        return f"<button type='button' class='kpi op'{act}{idattr}>{inner}<span class='chev'>{icon('chev')}</span></button>"
    return f"<div class='kpi'>{inner}</div>"


def meter(judged, limit):
    if not is_number(limit) or limit <= 0:
        return ""
    cells = "".join(f"<i{' class=on' if i < judged else ''}></i>" for i in range(limit))
    return (f"<span class='meter' style='grid-template-columns:repeat({limit},1fr)' role='img' "
            f"aria-label='상한 {limit}회 중 {judged}회'>{cells}</span>")


def split_bar(by_kind):
    parts = [(k, v["minutes"]) for k, v in by_kind.items() if v["minutes"]]
    if not parts:
        return ""
    bars = "".join(f"<i style='flex:{v}'></i>" for _, v in parts)
    text = ", ".join(f"{LABELS.get(k, k)} {v}분" for k, v in parts)
    return f"<span class='split' role='img' aria-label='{e(text)}'>{bars}</span>"


def kpi_acts(d, mart, m, many):
    """숫자 카드를 누르면 할 일 (D-27). 0건(또는 갈 곳이 없음)이면 그 카드는 없다(누를 수 없음).
    반려: 1건이면 그 칸 서랍, 여러 건이면 사다리로 가서 반려 이력 칸을 잠깐 선택 링으로 강조 / 사람 결재: 진행 단계의 결재 행 서랍
    (결재 2 → 없으면 결재 1) / 위험 명령 차단: 보던 마트에 머문 채 서랍에 차단 내역(cell=blocks) / 반복·개입·비용: 아래 접힘 상세를
    펴고 그리로 간다."""
    s, out = m["summary"], {}
    fold = f" data-kpi='fold' data-fold='{e(sid('summary', mart, many))}'"
    if s["iterations"]["judged"]:
        out["iterations"] = fold
    if s["M2"]["total"]["count"]:
        rows = m["rejections"]
        t = rejection_target(mart, m, rows[0]) if len(rows) == 1 else None
        out["rejections"] = (f" data-open='{e(t[0])}' aria-haspopup='dialog'" if t
                             else f" data-kpi='ladder' data-ladder='{e(sid('ladder', mart, many))}'")
    if s["M1"]["main"]["count"]:
        out["m1"] = fold
    stages = {x["name"]: x for x in m["stages"]}
    st = next((stages[n] for n in ("결재 2", "결재 1") if stages.get(n, {}).get("basis", dd.NONE) != dd.NONE), None)
    if s["M12"]["main"]["count"] and st:
        out["m12"] = f" data-open='{e(stage_key(mart, st))}' aria-haspopup='dialog'"
    if is_number(s["M4"]["total_cost_usd"]) and s["M4"]["total_cost_usd"] > 0:
        out["cost"] = fold
    if d["summary"]["M11"]["count"]:
        out["blocks"] = f" data-open='{BLOCKS_KEY}' aria-haspopup='dialog'"
    return out


def render_cards(d, mart, m, many):
    s, p = m["summary"], mart
    it, m1, m12, total = s["iterations"], s["M1"]["main"], s["M12"]["main"], s["M2"]["total"]
    cost, m11 = s["M4"]["total_cost_usd"], d["summary"]["M11"]
    kinds = " · ".join(f"{label(k)} {num(f'{p}.M1.main.by_kind.{k}.minutes', v['minutes'])}분"
                       for k, v in m1["by_kind"].items() if v["minutes"])
    approvals = " · ".join(f"{label(k)}: {num(f'{p}.M12.main.by_stage.{k}', v)}건" for k, v in m12["by_stage"].items())
    loop = f"루프 판정 반복 · 상한 {num(p + '.iterations.limit', it['limit'])}회" + (" · 상한 연장 있음" if it["extended"] else "")
    # 카드 6장, 3열 × 2행. 순서: 반복 · 반려(M2) · 개입 시간(M1) / 결재(M12) · 비용(M4) · 차단(M11).
    # 차단 카드만 범위가 전체 마트다(사유별 수는 차단 서랍·상세 표·전체 보기의 차단 표에 있다)
    act = kpi_acts(d, mart, m, many)
    cards = (
        card("반복 횟수", f"{num(p + '.iterations.judged', it['judged'])}<small>/ "
                       f"{num(p + '.iterations.limit', it['limit'])}회</small>", meter(it["judged"], it["limit"]), foot=loop,
             act=act.get("iterations", ""), ident_=safe_id("k", mart, 1)),
        card("반려", f"{num(p + '.M2.total.count', total['count'])}<small>건</small>", "",
             tags(p + ".M2.total.by_error_type", total["by_error_type"]) + harness_note(p, m["rejections"]),
             e("자동 검사가 돌려보낸 횟수"), hot=blocked(m), act=act.get("rejections", ""), ident_=safe_id("k", mart, 2)),
        card("사람 개입 시간", f"{num(p + '.M1.main.minutes', m1['minutes'])}<small>분</small>", split_bar(m1["by_kind"]),
             kinds, count=f"{num(p + '.M1.main.count', m1['count'])}건", act=act.get("m1", ""), ident_=safe_id("k", mart, 3)),
        card("사람 결재", f"{num(p + '.M12.main.count', m12['count'])}<small>건</small>", "", approvals or e(dd.NONE),
             act=act.get("m12", ""), ident_=safe_id("k", mart, 4)),
        card("비용", num(p + ".M4.total_cost_usd", cost, fmt_usd(cost)), "", foot=e("정가 환산 추정 · 실제 청구액 아님"),
             act=act.get("cost", ""), ident_=safe_id("k", mart, 5)),
        card("위험 명령 차단", f"{num('all.M11.count', m11['count'])}<small>건</small>{tag(e(ALL_MARTS))}", "",
             foot=e("AI가 실행하려다 Hook이 막은 명령"), act=act.get("blocks", ""), ident_=safe_id("k", mart, 6)))
    # 반려 상세 섹션·task별 반려 표에만 있던 수는 숨은 data 칸으로 옮겼다 (D-42·D-50)
    moved = hidden_num(p + ".rejections.count", len(m["rejections"])) + "".join(
        hidden_num(f"{p}.M3.{t}.rejects", v["rejects"]) for t, v in s["M3"].items())
    return (f"<section id='{e(sid('cards', mart, many))}' data-section='cards' aria-label='숫자 카드' class='kpis'>"
            f"<p class='kpi-basis'>{e(KPI_BASIS)}</p>{''.join(cards)}{moved}</section>")


# ---------- 진행 단계 ----------

def stage_extra(s):
    bits = []
    if s.get("iterations"):
        bits.append(f"반복 {s['iterations']}")
    if s.get("halt_reason"):
        bits.append(LABELS.get(s["halt_reason"], s["halt_reason"]))
    return " · ".join(bits)


def stage_when(s, l6=None):
    """행 오른쪽 글자: 완료면 날짜(시각 전체 값은 title), 완료가 아니면(또는 날짜가 없으면) 상태 글자.
    L6 행은 확인 기록이 있으면 오른쪽을 비우고 아래 줄(l6_line)에 시각을 둔다(D-42)."""
    if s["name"] == "L6" and l6_line(l6) and s["state"] == dd.DONE:
        return ""
    if s["state"] == dd.DONE and s["done_at"] != dd.NONE:
        return f"<span{tip_time(s['done_at'])}>{e(fmt_date(s['done_at']))}</span>"
    return e(s["state"])


L6_AFTER = ("그 뒤 운영 실행 없음", "그 뒤 운영 실행 있음")  # 진행 단계 L6 행 끝 (D-43)


def l6_line(l6):
    """진행 단계 L6 행의 둘째 줄 "11/4 08:48 · 7일 전 · 그 뒤 운영 실행 없음" (D-42·D-43). L6 시각은 이 자리에만 있다.
    "7일 전"은 data-t 원시 시각으로 JS가 붙이고(JS가 없으면 절대 시각만), 있음/없음은 기록(l6_check.ops_after: L6 뒤 운영 실행)
    으로만 정한다. 날짜만으로 주의색을 쓰지 않는다. 확인 기록이 없으면 빈 글자."""
    if not l6 or l6.get("checked_at", dd.NONE) == dd.NONE:
        return ""
    return (f"<span class='sl6' data-l6-line>{when_rel(l6['checked_at'])} · "
            f"{e(L6_AFTER[1 if l6.get('ops_after') else 0])}</span>")


def stage_basis(name, basis):
    """근거 값: id·파일 이름만("근거" 접두어 없음). 기록의 자유 문장(target·note)은 서버 경로 같은 내부 값이 섞일 수 있어 넣지 않는다."""
    if isinstance(basis, str):
        return ident(basis)
    return f"{e(name)} 기록 {len(basis)}건 (<code>{e(id_span(basis))}</code>)"


def stage_key(mart, s):
    return f"{mart}:stage:{s['name']}"


def stage_detail(mart, s, links=None):
    """진행 단계 서랍 (D-39): ① 하는 일(STAGE_WHAT) ② 상태(Badge + 한 줄, 있으면 반복·멈춘 이유 키-값) ③ 누가·언제 ④ 관련 PR(기록에 PR 주소가
    있을 때만, 없으면 줄째 숨김 D-41) ⑤ 근거 파일. 기록의 자유 문장(target·note)은 넣지 않는다."""
    name = s["name"]
    more = ([("반복", e(s["iterations"]))] if s.get("iterations") else []) + \
           ([("멈춘 이유", label(s["halt_reason"]))] if s.get("halt_reason") else [])
    state = result_line(state_badge(s["state"]), STAGE_NOW.get(s["state"], s["state"])) + (kv(more) if more else "")
    who = kv([("누가", e(ACTOR.get(name, dd.DASH))),
              ("완료 시각", when(s["done_at"]) if s["done_at"] != dd.NONE else e(dd.NONE))])
    pr = (links or {}).get(STAGE_PR.get(name))
    pr_html = ""
    if pr and pr.get("url"):
        pr_name = f"{LINK_NAME[STAGE_PR[name]]} #{pr['number']}"
        pr_html = sub("관련 PR", f"<p>{ext_link(pr['url'], e(pr_name))}</p>", "dp-pr")
    inner = (sub("하는 일", f"<p class='lead'>{e(STAGE_WHAT.get(name, ''))}</p>")
             + sub("상태", state, "dp-res") + sub("누가·언제", who) + pr_html
             + sub("근거 파일", f"<p class='note'>{stage_basis(name, s['basis'])}</p>", "dp-src"))
    title = f"{e(stage_title(name))} {state_badge(s['state'])}"
    return detail(stage_key(mart, s), title, inner, "진행 단계", f"{stage_title(name)} {s['state']}")


# 진행 단계 서랍 ① 하는 일 (D-39): 1문장씩, 용어 서랍(TERMS)의 결재 1·2·루프·PR 문장과 같은 뜻
STAGE_WHAT = {
    "요구서": "결재자가 요청한 지표와 완료 조건을 요구서와 contract(설계도)로 적는 단계입니다.",
    "결재 1": "사람이 요구서와 contract를 승인하는 요구서 PR 머지입니다.",
    "루프": "AI가 SQL을 쓰고 자동 검사(L0~L5)를 받는 반복입니다.",
    "PR": "사람이 AI가 만든 결과를 GitHub에 올려 구현 PR을 만드는 단계입니다.",
    "결재 2": "사람이 AI가 만든 결과를 승인하는 구현 PR 머지입니다.",
    "운영": "결재 뒤 운영 환경에서 파이프라인을 실행하는 단계입니다.",
    "L6": RUNG_TERM["L6"],
}
STAGE_NOW = {dd.DONE: "끝난 단계입니다", dd.ACTIVE: "지금 진행 중인 단계입니다", dd.WAIT: "아직 시작하지 않은 단계입니다",
             dd.HALT: "멈춘 단계입니다"}  # 진행 단계 서랍 ② 상태 한 줄(반복·멈춘 이유가 없을 때)
STAGE_PR = {"결재 1": "request_pr", "PR": "impl_pr", "결재 2": "impl_pr"}  # 진행 단계 서랍 ④ 관련 PR (links 키)


# 진행 단계 이름 → 사람 할 일의 행동(ACTION) 키. 서랍 제목 "결재 2 · 구현 PR 머지"(D-13). 없는 단계는 이름만(새 용어를 만들지 않는다)
STAGE_ACTION = {"결재 1": "approval_1", "결재 2": "approval_2"}


def stage_title(name):
    act = ACTION.get(STAGE_ACTION.get(name))
    return f"{name} · {act}" if act else name


def todo_stages(m, mine):
    """사람 할 일이 걸린 진행 단계 이름(결재 1·결재 2 대기, L6 재확인). 막힌 할 일(루프 멈춤·L6 반려)은 막힘 색 그대로라 뺀다."""
    cur = next((s["name"] for s in m["stages"] if s["current"]), None)
    return {WAIT_STAGE.get(x["key"]) or cur for x in mine if x["key"] not in FAIL_KEYS}


def stage_mark(s, todo):
    """진행 단계 StatusDot의 (variant, 아이콘): 사람 할 일이 걸린 단계는 사람 할 일(탭·머리 배지와 같은 아이콘), 그 밖은 STATE."""
    return ("todo", "todo") if s["name"] in todo else STATE.get(s["state"], ("neutral", "wait"))


def stage_step(mart, s, pid, todo=frozenset(), n=0, l6=None):
    """세로 타임라인 한 행: 아이콘·이름·역할 칩·날짜·꺾쇠. 근거가 있으면 행 전체가 버튼이고 누르면 오른쪽 상세 서랍이 열린다.
    n = 순번(1~7), 행 id s-<마트>-<n>(D-28). L6 행은 아래 줄에 마지막 확인 시각과 그 뒤 운영 실행 여부(l6 = l6_check)."""
    kind, mark = stage_mark(s, todo)
    cur = " is-current" if s["current"] else ""
    actor = ACTOR.get(s["name"])
    who = tag(e(actor)) if actor else ""  # 역할 칩 = 분류 Badge. 요구서는 칩 없음
    below = l6_line(l6) if s["name"] == "L6" else ""
    inner = (f"{status_dot(kind, mark)}<span class='vh'>{e(s['state'])}</span>"
             f"<span class='sname'>{e(s['name'])}</span>{who}<span class='sdate'>{stage_when(s, l6)}</span>{below}")
    li = f"<li class='step is-{kind}{cur}' id='{e(stage_id(mart, n))}'>"
    if s["basis"] == dd.NONE:
        return f"{li}<div class='srow'>{inner}</div></li>"
    return (f"{li}<button type='button' class='srow sbtn op' data-open='{e(stage_key(mart, s))}' "
            f"aria-haspopup='dialog' aria-controls='{e(pid)}' aria-expanded='false' aria-label='{e(s['name'])} {e(s['state'])} · 근거 보기'>"
            f"{inner}<span class='chev'>{icon('chev')}</span></button></li>")


def render_stages(mart, m, many, mine=()):
    """진행 단계 카드(왼쪽 열, sticky). 근거 상세는 카드 아래에 두고 JS가 상세 서랍으로 옮긴다(JS가 없으면 타임라인 아래에 차례로 보인다)."""
    pid = sid("ladder-panel", mart, many)
    stages = m["stages"]
    done = sum(1 for s in stages if s["state"] == dd.DONE)
    todo = todo_stages(m, mine)
    steps = "".join(stage_step(mart, s, pid, todo, n, m["l6_check"]) for n, s in enumerate(stages, 1))
    details = "".join(stage_detail(mart, s, m.get("links")) for s in stages if s["basis"] != dd.NONE)
    return (f"<section id='{e(sid('stages', mart, many))}' data-section='stages' class='card stages'>"
            f"<div class='st-h'><h2>{e(dict(SECTIONS)['stages'])}</h2><span class='st-n'>"
            f"{done} / {len(stages)}<span class='vh'> 단계 완료</span></span></div>"
            f"<ol class='steps' aria-label='{e(mart)} 진행 단계'>{steps}</ol>"
            f"<div class='sdetails' data-sdetails>{details}</div></section>")


# ---------- 검사 사다리 ----------

def item_status(h, halted):
    """칸 이력 1건의 상태 글자. 멈춘 반복의 실패는 반려가 아니라 멈춤이다(collect()의 verdict 그대로)."""
    status = RUNG_STATUS.get(h.get("status"), h.get("status") or dd.NONE)
    return dd.HALT if status == dd.REJECT and h["iteration"] in halted else status


def ordinal(k):
    return "첫" if k == 1 else f"{k}번째"


def attempt_sentence(verdicts):
    """행의 시도 이력을 문장으로: "3번째 시도에 통과 (1번 반려, 1번 멈춤)". 시도 = 이 task의 결과 파일 순서."""
    if not verdicts:
        return "아직 시도 없음"
    k, last = len(verdicts), verdicts[-1]["verdict"]
    rej = sum(1 for v in verdicts if v["verdict"] == "reject")
    halt = sum(1 for v in verdicts if v["verdict"] == "halt")
    head = {"pass": f"{ordinal(k)} 시도에 통과", "reject": f"{ordinal(k)} 시도에서 반려됨",
            "halt": f"{ordinal(k)} 시도에서 멈춤"}.get(last, f"{ordinal(k)} 시도 {last}")
    if last == "reject":
        rej -= 1
    if last == "halt":
        halt -= 1
    tail = ", ".join(x for x in (f"{rej}번 반려" if rej else "", f"{halt}번 멈춤" if halt else "") if x)
    return head + (f" ({'앞서 ' if last != 'pass' else ''}{tail})" if tail else "")


def plain_error(error_type):
    """반려 유형을 쉬운 이름으로(원래 키는 --json)."""
    name = ERROR_INFO.get(error_type, (error_type or dd.NONE, ""))[0]
    return tag(e(name))


def halt_text(reason):
    return HALT_PLAIN.get(reason) or LABELS.get(reason, reason or "멈춤")


def detail_id(*parts):
    """패널 안 요소 id. 이름에 쓸 수 없는 글자는 바꾼다."""
    return "d-" + "-".join(re.sub(r"[^A-Za-z0-9_-]", "_", str(p)) for p in parts)


# ----- 안정된 id (D-28): T5 뒤에도 HTML에 남는 사다리 칸·사다리 행·진행 단계 행에만 둔다. 내부 이동 링크의 href는 이 id를
# 가리키고(JS가 없으면 그 자리로 스크롤), 칸 키는 data-open에 둔다(JS가 클릭을 가로채 서랍을 연다).
# 규칙: 칸 c-<마트>-<task>-<L0~L5>, L6 한 줄 c-<마트>-L6, 사다리 행 r-<마트>-<task>, 진행 단계 행 s-<마트>-<순번 1~7>.
# 이름에 쓸 수 없는 글자는 _로 바꾼다(한글 단계 이름은 넣지 않고 순번) -----

def safe_id(prefix, *parts):
    return prefix + "-" + "-".join(re.sub(r"[^A-Za-z0-9_-]", "_", str(p)) for p in parts)


def cell_id(mart, task, rung):
    return safe_id("c", mart, task, rung)


def l6_id(mart):
    return safe_id("c", mart, "L6")


def row_id(mart, task):
    return safe_id("r", mart, task)


def stage_id(mart, n):
    return safe_id("s", mart, n)


def rejection_target(mart, m, r):
    """반려 r의 칸: (칸 키, 칸 id). L6 반려는 L6 한 줄. 사다리에 그 task 행이 없으면 None."""
    rung = r.get("caught_by_rung")
    if rung in dd.LADDER_RUNGS and any(x["task"] == r.get("task") for x in m["grid"]["rows"]):
        return f"{mart}:{r['task']}:{rung}", cell_id(mart, r["task"], rung)
    if rung == "L6":
        return f"{mart}:L6", l6_id(mart)
    return None


def cell_link(html_, key, target, mart=None, ck=None):
    """글 속 참조 번호 링크(이동 모양, D-24·D-28): href = 늘 HTML에 남는 칸 id, data-open = 칸 키. ck면 그 검사 줄로 옮긴다.
    mart(규칙 구역처럼 보기 밖에서 누를 때 열 마트 보기)."""
    extra = (f" data-mart='{e(mart)}'" if mart else "") + (f" data-ck='{e(ck)}'" if ck else "")
    return f"<a class='lk' href='#{e(target)}' data-open='{e(key)}' aria-haspopup='dialog'{extra}>{html_}</a>"


def ref_map(d):
    """반려 id → (마트, 칸 키, 칸 id). 규칙 구역·서랍의 R-번호 링크에 쓴다."""
    out = {}
    for mart, m in d["marts"].items():
        for r in m["rejections"]:
            t = rejection_target(mart, m, r)
            if t:
                out[r["id"]] = (mart, *t)
    return out


def ref_ids(html_, refs):
    """escape한 글자 속 R-번호(R-0001)를 그 반려 칸 링크로. 모르는 번호는 그대로."""
    def one(mt):
        x = refs.get(mt.group(0))
        return cell_link(f"<code>{mt.group(0)}</code>", x[1], x[2], x[0]) if x else f"<code>{mt.group(0)}</code>"
    return re.sub(r"\bR-\d{4}\b", one, html_)


def open_btn(key, label_text, cls="more"):
    return (f"<button type='button' class='{cls}' data-open='{e(key)}' aria-haspopup='dialog'>"
            f"{e(label_text)}</button>")


def sub(title, inner, cls=""):
    return f"<section class='dp-sec {cls}'><h4>{e(title)}</h4>{inner}</section>"


def detail(key, title, inner, eyebrow="", name=None):
    """서랍에 들어갈 상세 1개. eyebrow는 이미 escape한 HTML, name은 화면 읽기 이름(없으면 제목 글자)."""
    head = f"<p class='dp-eb'>{eyebrow}</p>" if eyebrow else ""
    aria = name if name is not None else re.sub("<[^>]+>", "", title)
    return (f"<div class='detail' data-detail='{e(key)}' aria-label='{e(aria)}'>{head}"
            f"<h3 class='dp-t' tabindex='-1'>{title}</h3>{inner}</div>")


def check_result(c, last):
    """검사 1개의 결과(마지막 시도 기준). 판정을 다시 하지 않고 기록(metrics.checks·check)만 옮긴다."""
    if last is None:
        return state_badge(dd.NONE)
    ran = last.get("checks")
    if last.get("check") == c["id"]:
        v = last.get("violations", dd.NONE)
        if v != dd.NONE:
            return badge("fail", f"위반 {e(v)}", "fail")
        return badge("fail", "실행 실패", "fail") + "<span class='note'>오류 원문은 넣지 않습니다</span>"
    if isinstance(ran, list) and c["id"] in ran:
        return state_badge("통과")
    if last["status"] == "pass" and ran is None:
        return state_badge("통과", extra="(단계 통과)")
    if last["status"] == "fail":
        return badge("neutral", "실행 안 됨", "wait") + "<span class='note'>앞 검사에서 멈춤</span>"
    return state_badge(dd.NONE)


def sql_box(caption, path, sql):
    """검증에 쓴 SQL 1개: 설명(이미 escape한 HTML)·파일 경로·원문(접힘). sql은 collect()·scrub을 거친 글자."""
    where = f" <code>{e(path)}</code>" if path else ""
    body = (f"<details class='sql'><summary class='tw'>{icon('tri')}SQL 보기</summary><pre><code>{e(sql)}</code></pre></details>"
            if sql != dd.NONE else f"<p class='note'>{e(SQL_UNREAD)}</p>")
    return f"<div class='sqlbox'><p>{caption}{where}</p>{body}</div>"


def check_items(mart, task, rung, checks, last):
    """이 칸의 검사 파일마다 id·규칙 문장·마지막 시도 결과·원문(접힘)."""
    rows = []
    for c in checks:
        gives = ERROR_INFO.get(c["error_type"], (c["error_type"], ""))[0]
        rows.append(
            f"<li class='ck' id='{e(detail_id(mart, task, rung, c['id']))}' tabindex='-1'><div class='ck-h'>"
            f"<code>{e(c['id'])}</code><span class='ck-rule'>{e(c['rule'])}</span>"
            f"<span class='ck-r'>{check_result(c, last)}</span></div>"
            f"<div class='ck-m note'>걸리면 {e(gives)}으로 반려 · "
            f"<code>{e(c['file'])}</code></div>"
            f"<details class='sql'><summary class='tw'>{icon('tri')}SQL 보기</summary><pre><code>{e(c['sql'])}</code></pre></details></li>")
    when_ = f"<p class='note'>결과는 마지막 시도(반복 {e(last['iteration'])}) 기준</p>" if last else ""
    return f"{when_}<ul class='cks'>{''.join(rows)}</ul>"


def l5_builtin_sql(grid, row):
    """L5 내장 비교 쿼리. 사다리(l5_idem.snapshot_sql)와 같은 함수에 자리 표시를 넣어 부른다. 프로젝트 ID 가림을 거친다."""
    return dd.scrub(l5_idem.snapshot_sql("{{ project }}", dd.common.DEV_DATASET, row.get("table", dd.NONE),
                                         grid.get("partition_column", dd.NONE), "{{ ds }}"))


def verify_sql(mart, grid, row, rung, last):
    """"검증에 쓴 SQL": 결과와 상관없이 모든 칸(통과 칸 포함)에 둔다. L0는 SQL이 없다는 한 줄."""
    if rung == "L0":
        return sub(SQL_HEAD, f"<p class='note'>{e(SQL_L0)}</p>", "dp-sql")
    task_sql = row.get("task_sql") or {"file": "", "sql": dd.NONE}
    checks = row.get("checks", {}).get(rung, [])
    dev = "개발 데이터셋"
    parts = []
    if rung == "L1":
        parts.append(sql_box("BigQuery에 실행 없이 확인만 맡긴 task SQL", task_sql["file"], task_sql["sql"]))
    elif rung == "L2":
        parts.append(sql_box(f"{dev}에서 실행한 task SQL", task_sql["file"], task_sql["sql"]))
    elif rung == "L5":
        parts.append(sql_box(e(SQL_L5), "", l5_builtin_sql(grid, row)))
    if checks:
        parts.append(check_items(mart, row["task"], rung, checks, last))
    elif rung in ("L3", "L4"):
        parts.append(f"<p class='note'>{e(SQL_NO_CHECK)}</p>")
    parts.append(f"<p class='note sql-now'>{e(SQL_NOW)}</p>")
    return sub(SQL_HEAD, "".join(parts), "dp-sql")


def later_attempts(verdicts, n, by_iter, halted):
    """반려된 반복 n 뒤의 시도가 어떻게 끝났는지(이 칸 기준, 칸에 기록이 없으면 그 시도의 판정)."""
    out = []
    for k, v in enumerate(verdicts, 1):
        if not isinstance(v["iteration"], int) or not isinstance(n, int) or v["iteration"] <= n:
            continue
        h = by_iter.get(v["iteration"])
        if h is not None:
            what = f"이 단계 {item_status(h, halted)}"
        elif v["verdict"] == "halt":
            what = f"이 단계 전에 멈춤 · {halt_text(v.get('halt_reason'))}"
        else:
            what = f"이 단계까지 가지 않음 · 시도 {VERDICT.get(v['verdict'], v['verdict'])}"
        out.append(f"<li>{e(ordinal(k))} 시도 <span class='note'>(루프 반복 {e(v['iteration'])})</span>: {e(what)}</li>")
    return f"<ul class='later'>{''.join(out)}</ul>" if out else "<span class='note'>다음 시도 없음</span>"


def why_cls(now):
    """반려 이유 상자 class (D-34): 지금 막힌 반려·멈춤만 빨강(.why), 지난 것은 회색(.why.past)."""
    return "why" if now else "why past"


def why_boxes(mart, task, rung, items, verdicts, halted, checks, rejections, m3=None):
    """반려된 시도마다 상자(지금 막힌 것만 빨강, 지난 반려는 회색 .past — now_index): 유형 쉬운 이름·설명, 유형(·분류), 검사 규칙 문장, 잡은 검사 id(→ 그 검사로 이동), 위반 건수,
    처리 결과, 3줄 요약, 다음 시도, 하네스 원인. 기록 없음인 위반 건수·3줄 요약 줄은 숨긴다(D-41). 반려 상세 섹션에만 있던
    정보(검사 규칙 문장·처리 결과·R-번호(근거 파일 줄)·시각(머리 줄))가 모두 여기 있다(D-42). 오류 원문은 없다. 멈춘 시도는 멈춤 상자."""
    by_iter = {h["iteration"]: h for h in items}
    order = {v["iteration"]: k for k, v in enumerate(verdicts, 1)}
    known = {c["id"] for c in checks}
    ni = now_index([item_status(h, halted) for h in items])
    now_h = items[ni] if ni is not None else None
    blocks = []
    for h in items:
        if item_status(h, halted) != dd.REJECT:
            continue
        et = h.get("error_type")
        name, desc = ERROR_INFO.get(et, (et or dd.NONE, ""))
        chk = h.get("check", dd.NONE)
        if chk in known:
            hit = (f"<button type='button' class='goto lk' data-goto='{e(detail_id(mart, task, rung, chk))}'>"
                   f"<code>{e(chk)}</code> 검사로 이동</button>")
        else:
            hit = ident(chk) if chk != dd.NONE else e("검사 파일 밖 항목(사다리 자체 확인)")
        if h.get("violations", dd.NONE) != dd.NONE:
            said = f" · 위반 {e(h['violations'])}"
        elif h.get("ladder_note"):
            said = " · " + e(h["ladder_note"])
        else:  # 위반 건수가 기록 없음이면 그 말을 쓰지 않는다 (D-41)
            said = ""
        rej = next((r for r in rejections if r["task"] == task and r["iteration"] == h["iteration"]
                    and r["caught_by_rung"] == rung), None)
        cause = (f"<p class='why-m'>{tag('하네스 원인')} {e(HARNESS_CAUSE)}</p>"
                 if rej and rej.get("harness_cause") else "")
        extra = ""
        if rej:  # 반려 기록(rejections.jsonl)에서 온 줄 (D-42): 유형(=분류면 하나만) · 검사 규칙 · 처리 · 3줄 요약
            et_, ec_ = rej.get("error_type"), rej.get("error_class")
            kinds = f"유형 {tag(e(et_))}" + (f" 분류 {tag(e(ec_))}" if ec_ not in (None, et_) else "")
            extra += f"<p class='why-m why-k'>{kinds}</p>"
            if rej.get("rule", dd.NONE) != dd.NONE:
                extra += f"<p class='why-m'>검사 규칙 <span class='why-rule'>{e(rej['rule'])}</span></p>"
            if rej.get("rule_promoted"):
                extra += f"<p class='why-m'>승격 규칙 <code>{e(rej['rule_promoted'])}</code></p>"
        done = (m3 or {}).get(task, {}).get("class", dd.NONE)
        handled = f"<p class='why-m' data-handled>처리: {m3_label(done)}</p>" if rej and done != dd.NONE else ""
        lines = rej.get("three_lines", dd.NONE) if rej else dd.NONE
        para = " ".join(lines) if isinstance(lines, list) else lines
        three = (f"<p class='why-m'>3줄 요약 <span class='why-three'>{e(para)}</span></p>"
                 if para not in (None, dd.NONE, "") else "")
        k = order.get(h["iteration"])
        blocks.append(f"<div class='{why_cls(h is now_h)}'><div class='why-h'><b>{e(ordinal(k) if k else '')} 시도 반려 이유</b>"
                      f"<span class='note'>반복 {e(h['iteration'])} · {when(h.get('ts', dd.NONE))}</span></div>"
                      f"<p class='why-n'><strong>{e(name)}</strong> · {e(desc)}</p>{extra}"
                      f"<p class='why-m'>잡은 검사 {hit}{said}</p>{handled}{three}"
                      f"<div class='why-m'>다음 시도 {later_attempts(verdicts, h['iteration'], by_iter, halted)}</div>"
                      f"{cause}</div>")
    for h in items:  # 멈춘 반복의 실패: 반려가 아니라 멈춤이다
        if item_status(h, halted) == dd.HALT:
            v = next((x for x in verdicts if x["iteration"] == h["iteration"]), {})
            mark = state_badge(dd.HALT) if h is now_h else past_badge(dd.HALT)
            blocks.append(f"<div class='{why_cls(h is now_h)}'><div class='why-h'>{mark}<b>반복 {e(h['iteration'])}</b></div>"
                          f"<p>{e(halt_text(v.get('halt_reason')))}. 판정하지 않고 멈춘 시도라 반려로 세지 않습니다.</p></div>")
    return f"<section class='dp-why' aria-label='왜 반려됐나'>{''.join(blocks)}</section>" if blocks else ""


def evidence(files, checks, rejection_ids):
    """근거 파일: 사다리 기록 파일 이름, 검사 파일 경로, 반려 id (작게)."""
    bits = []
    if files:
        bits.append("사다리 기록 " + ", ".join(f"<code>{e(f)}</code>" for f in files))
    if checks:
        bits.append("검사 파일 " + ", ".join(f"<code>{e(c['file'])}</code>" for c in checks))
    if rejection_ids:  # (id, 칸 키, 칸 id)면 그 반려 칸 링크(D-28), 글자만이면 글자
        bits.append("반려 " + ", ".join(cell_link(f"<code>{e(x[0])}</code>", x[1], x[2]) if isinstance(x, tuple)
                                       else f"<code>{e(x)}</code>" for x in rejection_ids))
    return sub("근거 파일", f"<p class='note'>{' · '.join(bits) or e(dd.NONE)}</p>", "dp-src")


def attempt_label(k, iteration):
    """시도 기록의 이름: "첫 시도 (루프 반복 3)". 앞은 이 task의 몇 번째 시도, 괄호는 루프 반복 번호."""
    return f"{ordinal(k)} 시도 (루프 반복 {iteration})"


def tries_list(rows, now=None):
    """시도 기록 목록: [(시도 글자, 상태 글자, 시각, 덧붙임)]. now = 지금 막힌 줄의 차례(now_index). 반려·멈춤 줄 중 now가 아닌
    지난 줄은 회색(.fail.past, 중립 Badge, D-34)."""
    if not rows:
        return f"<p class='note'>{e(dd.NONE)}</p>"
    lis = []
    for i, (a, s, t, x) in enumerate(rows):
        kind = STATE.get(s, ("neutral",))[0]
        past = kind == "fail" and i != now
        lis.append(f"<li class='{kind}{' past' if past else ''}'><b>{e(a)}</b>{past_badge(s) if past else state_badge(s)}"
                   f"{f'<span class=note>{e(x)}</span>' if x else ''}<span class='note tr-t'>{when(t)}</span></li>")
    return f"<ol class='tries'>{''.join(lis)}</ol>"


def tries(rows, title="시도 기록", now=None):
    return sub(title, tries_list(rows, now))


def rung_what(rung, extra=""):
    """서랍 ① 확인하는 것(RUNG_WHAT 1~2문장). extra = 같은 묶음에 붙일 HTML(L6의 통과 조건 목록)."""
    return sub("확인하는 것", f"<p class='lead'>{e(RUNG_WHAT[rung])}</p>{extra}")


PASS_NOTE = "줄마다의 결과는 기록에 없어 칸 상태(마지막 시도)를 모든 줄에 같이 표시합니다."


def pass_items(rung, state):
    """통과 조건 목록 (D-39 ③): PASS_PLAIN 문장 + RUNG_ITEMS(사다리가 확인하는 항목)를 한 목록으로, 줄마다 칸 상태 아이콘
    (통과·반려·대기, 글리프 대신 icon()). 원래 조건 문구(dd.PASS_RULES)는 --json의 rungs에만 있다."""
    ic = {"통과": "pass", dd.REJECT: "fail"}.get(state, "wait")
    word = {"pass": "통과", "fail": dd.REJECT, "wait": dd.WAIT}[ic]
    lis = "".join(f"<li class='pc {ic}'>{icon(ic)}<span class='vh'>{e(word)} </span><span>{e(x)}</span></li>"
                  for x in (PASS_PLAIN[rung], *RUNG_ITEMS.get(rung, ())))
    return f"<ul class='pcs'>{lis}</ul><p class='note'>{e(PASS_NOTE)}</p>"


def now_index(statuses):
    """지금 막힌 것 (D-34): 상태 글자 목록의 마지막이 반려·멈춤이면 그 차례, 아니면 None. 사다리 원이 빨강인 조건(마지막 시도가
    반려·멈춤, cell_state)과 같은 규칙이고, 반려 상자(.why / .why.past)와 시도 기록 줄(.fail / .fail.past)이 이 함수 하나를 쓴다."""
    return len(statuses) - 1 if statuses and statuses[-1] in (dd.REJECT, dd.HALT) else None


def past_badge(s):
    """지난 반려·멈춤의 상태 Badge: 같은 아이콘, 중립(회색) variant (D-34)."""
    return badge("neutral", e(s), STATE.get(s, ("neutral", "wait"))[1])


def result_line(badge_html, text):
    """서랍 ② 결과·상태 한 줄: 상태 Badge + 짧은 문장."""
    return f"<p class='res'>{badge_html}<span>{e(text)}</span></p>"


def cell_result(items, verdicts, halted):
    """칸 결과 문장(마지막 시도 기준): "3번째 시도에 통과 (1번 반려)". 시도 번호 = 이 task의 시도 순서."""
    if not items:
        return "아직 이 단계까지 오지 않음"
    k_of = {v["iteration"]: k for k, v in enumerate(verdicts, 1)}
    st = [item_status(h, halted) for h in items]
    k = k_of.get(items[-1]["iteration"], len(items))
    head = {"통과": f"{ordinal(k)} 시도에 통과", dd.REJECT: f"{ordinal(k)} 시도에서 반려됨",
            dd.HALT: f"{ordinal(k)} 시도에서 멈춤"}.get(st[-1], f"{ordinal(k)} 시도 {st[-1]}")
    rej = st[:-1].count(dd.REJECT)
    return head + (f" ({'앞서 ' if st[-1] != '통과' else ''}{rej}번 반려)" if rej else "")


def rung_name(rung):
    """서랍 제목의 단계 이름 (D-13): "L3 층별 품질 검사"(사다리 열 제목과 같은 L 번호 + 쉬운 이름)."""
    return f"{rung} {RUNG_PLAIN[rung]}"


L6_SCOPE = "마트 전체"  # L6 서랍 제목 앞 (D-13): "마트 전체 · L6 메타데이터 등록 확인"


def cell_state(items, halted):
    """칸 겉모습의 상태 글자(마지막 시도 기준): 통과·반려·멈춤·미실행."""
    if not items:
        return "미실행"
    last = item_status(items[-1], halted)
    return last if last in CELL else "미실행"


MINI_SLOT = "<div class='dp-mini' data-mini-slot></div>"


def mini_ladder():
    """칸 서랍 머리의 미니 사다리 자리 (D-26). 서버는 빈 자리만 둔다(서랍 50개 × 6칸을 찍으면 약 93KB). 서랍이 열릴 때 JS(buildMini)가
    그 task 행(.lrow)의 L0~L5 원에서 모양(통과·반려·멈춤·미실행, 반려 이력 고리)·아이콘·상태 글자를 읽어 같은 6칸 버튼을 만든다.
    현재 칸은 선택 링 + aria-current. 칸 = data-open 버튼이라 기존 열기 경로를 그대로 쓴다(서랍 안에서 옆 칸으로 바꾸고 주소는
    replaceState). JS가 없으면 비어 있고 숨긴다(html.js일 때만 보임)."""
    return MINI_SLOT


def cell_detail(mart, grid, row, rung, items, halted, rejections, m3=None):
    """칸 서랍: 머리(task · 층) → 제목(단계 쉬운 이름 + 상태) → 확인하는 것 → 반려 상자 → 시도 기록
    → 사다리가 확인한 것 → 검증에 쓴 SQL → 근거 파일."""
    task, verdicts, layer = row["task"], row["verdicts"], row["layer"]
    checks = row.get("checks", {}).get(rung, [])
    k_of = {v["iteration"]: k for k, v in enumerate(verdicts, 1)}
    tl = []
    for v in verdicts:
        h = next((x for x in items if x["iteration"] == v["iteration"]), None)
        a = attempt_label(k_of[v["iteration"]], v["iteration"])
        if h is not None:
            tl.append((a, item_status(h, halted), h.get("ts", v.get("ts", dd.NONE)), h.get("note")))
        elif v["verdict"] == "halt":
            tl.append((a, dd.HALT, v.get("ts", dd.NONE), "이 단계 전에 멈춤 · " + halt_text(v.get("halt_reason"))))
        else:
            tl.append((a, "미실행", v.get("ts", dd.NONE), "이 단계까지 가지 않음"))
    last = items[-1] if items else None
    ni = now_index([item_status(h, halted) for h in items])
    now_row = next((i for i, v in enumerate(verdicts) if ni is not None and v["iteration"] == items[ni]["iteration"]), None)
    ids = [(r["id"], f"{mart}:{task}:{rung}", cell_id(mart, task, rung))
           for r in rejections if r["task"] == task and r["caught_by_rung"] == rung]
    files = [v.get("file") for v in verdicts if any(x["iteration"] == v["iteration"] for x in items)
             and v.get("file") not in (None, dd.NONE)]
    state = cell_state(items, halted)
    title = f"<span><code>{e(task)}</code> · {e(rung_name(rung))}</span> {state_badge(state)}"
    eyebrow = tag(e(LAYER_PLAIN.get(layer, layer)))
    result = (result_line(state_badge(state), cell_result(items, verdicts, halted))
              + why_boxes(mart, task, rung, items, verdicts, halted, checks, rejections, m3))
    inner = (mini_ladder() + rung_what(rung) + sub("결과", result, "dp-res")
             + sub("통과 조건", pass_items(rung, state)) + tries(tl, now=now_row)
             + verify_sql(mart, grid, row, rung, last) + evidence(files, checks, ids))
    return detail(f"{mart}:{task}:{rung}", title, inner, eyebrow, f"{task} · {rung_name(rung)} {state}")


def row_detail(mart, row, halted):
    """task 이름을 누르면: 이 task가 하는 일, 시도 기록, 단계별 결과(각 칸 상세로 이동), 근거 파일."""
    task, layer, verdicts = row["task"], row["layer"], row["verdicts"]
    tl = [(attempt_label(k, v["iteration"]), VERDICT.get(v["verdict"], v["verdict"]), v.get("ts", dd.NONE),
           halt_text(v.get("halt_reason")) if v["verdict"] == "halt" else "") for k, v in enumerate(verdicts, 1)]
    steps = []
    for rung in dd.LADDER_RUNGS:
        state = cell_state(row["cells"][rung], halted)
        steps.append(f"<li>{state_badge(state)}<span>{e(RUNG_PLAIN[rung])} <span class='rk'>{e(rung)}</span></span>"
                     f"{open_btn(f'{mart}:{task}:{rung}', '상세 보기', 'more sm')}</li>")
    files = [v["file"] for v in verdicts if v.get("file") not in (None, dd.NONE)]
    inner = (f"<p class='lead'>{e(LAYER_WHAT.get(layer, ''))} {e(attempt_sentence(verdicts))}.</p>"
             + tries(tl, now=now_index([s for _, s, _, _ in tl])) + sub("단계별 결과", f"<ul class='steps-list'>{''.join(steps)}</ul>") + evidence(files, [], []))
    title = f"<code>{e(task)}</code> {tag(e(LAYER_PLAIN.get(layer, layer)))}"
    return detail(f"{mart}:{task}", title, inner, "task 상세", f"{task} {LAYER_PLAIN.get(layer, layer)}")


def l6_detail(mart, grid_l6, check):
    hist = grid_l6["history"]
    tl = []
    for h in hist:
        counts = h.get("counts") or {}
        extra = ", ".join(f"{L6_COUNTS.get(k, k)} {v}건" for k, v in counts.items() if v)
        tl.append((h["iteration"], VERDICT.get(h.get("verdict"), dd.NONE), h.get("ts", dd.NONE), extra))
    age = check["age_days"]
    checked = (f"{num(mart + '.l6.checked_at', check['checked_at'], fmt_time(check['checked_at']))}"
               f" · {num(mart + '.l6.age_days', age)}{'일 전' if age != dd.NONE else ''}"
               + (" · 재확인 필요: " + e("; ".join(check["reasons"])) if check["recheck"] else ""))
    last = hist[-1] if hist else None
    status = VERDICT.get(last.get("verdict"), dd.NONE) if last else "미실행"
    now = now_index([s for _, s, _, _ in tl])
    why = []
    for k, h in enumerate(hist, 1):
        if h.get("verdict") != "reject":
            continue
        name, desc = ERROR_INFO.get(h.get("error_type"), (h.get("error_type") or dd.NONE, ""))
        counts = ", ".join(f"{L6_COUNTS.get(c, c)} {v}건" for c, v in (h.get("counts") or {}).items() if v)
        nxt = [VERDICT.get(x.get("verdict"), dd.NONE) for x in hist[k:]]
        pairs = [("유형", f"{plain_error(h.get('error_type'))} <span class='note'>{e(desc)}</span>"),
                 ("사다리 기록", e(counts or dd.NONE)),
                 ("다음 확인", e(" → ".join(nxt)) if nxt else e("다음 확인 없음"))]
        why.append(f"<div class='{why_cls(k - 1 == now)}'><div class='why-h'><b>{e(h['iteration'])} 반려 이유</b>"
                   f"<span class='note'>{when(h.get('ts', dd.NONE))}</span></div>"
                   f"<p class='why-n'><strong>{e(name)}</strong> · {e(desc)}</p>{kv(pairs)}</div>")
    why_html = f"<section class='dp-why' aria-label='왜 반려됐나'>{''.join(why)}</section>" if why else ""
    shown = status if status in STATE else dd.NONE
    said = f"{ordinal(len(hist))} 확인에서 {status}" if hist else "아직 확인하지 않음"
    # L6 서랍 (D-39): ① 확인하는 것(+ 통과 조건·SQL 없음) ② 상태 ③ 누가·언제(+ 확인 기록) ④ 관련 PR(L6는 없음, 줄 숨김) ⑤ 근거 파일
    inner = (rung_what("L6", pass_items("L6", status) + f"<p class='note'>{e(SQL_L6)}</p>")
             + sub("상태", result_line(state_badge(shown), said) + why_html, "dp-res")
             + sub("누가·언제", kv([("누가", e(ACTOR["L6"])), ("마지막 확인", checked)]) + tries_list(tl, now))
             + evidence([h["file"] for h in hist if h.get("file") not in (None, dd.NONE)], [], []))
    title = f"{e(L6_SCOPE)} · {e(rung_name('L6'))} {state_badge(shown)}"
    return detail(f"{mart}:L6", title, inner, tag("결재 후"), f"{L6_SCOPE} · {rung_name('L6')} {shown}")


def rej_badge(n, kind):
    """칸 위 작은 "반려 N" Badge(글자는 aria-label에 있으므로 aria-hidden). 위치는 사다리 CSS(.rej-n)가 정한다.
    지금 반려인 칸이면 fail, 지금은 통과·멈춤·미실행인데 반려된 적이 있으면 neutral(지난 반려는 회색, D-34)."""
    variant = "fail" if kind == "fail" else "neutral"
    return badge(variant, f"반려 {n}", "fail", cls="rej-n", attrs=f" data-rej='{n}' aria-hidden='true'") if n else ""


def cell_mark(mark):
    return icon(mark) if mark else ""


def ladder_node(mart, task, rung, items, halted):
    """동그라미 1개(button 30px): 마지막 시도 결과의 모양·색, 반려 이력이 있으면 바깥 고리와 "반려 N"(지금 반려면 빨강, 아니면 회색).
    약어(검사 id·error_type)는 넣지 않고 상태 글자는 aria-label·.vh에 둔다(title 없음, 유형은 서랍 본문). id = 칸 id(D-28)."""
    key = f"{mart}:{task}:{rung}"
    state = cell_state(items, halted)
    kind, mark = CELL[state]
    rejected = sum(1 for h in items if item_status(h, halted) == dd.REJECT)
    plain = RUNG_PLAIN[rung]
    hist = f", 반려 이력 {rejected}회" if rejected else ""
    ring = rej_badge(rejected, kind)
    return (f"<button type='button' class='cbtn nd {kind}{' had' if rejected else ''}' data-open='{e(key)}' "
            f"aria-haspopup='dialog' aria-expanded='false' aria-label='{e(f'{task} {plain} {state}{hist} · 상세 보기')}' "
            f"id='{e(cell_id(mart, task, rung))}'>"
            f"<span class='nd-mk'>{cell_mark(mark)}</span>{ring}"
            f"<span class='vh'>{e(state)}</span></button>")


def l6_row(mart, grid_l6, check):
    """L6는 task가 아니라 마트 전체를 보므로 task 행 아래 한 줄 버튼으로 둔다."""
    hist = grid_l6["history"]
    last = VERDICT.get(check["verdict"], "미실행")
    state = last if last in CELL else "미실행"
    kind, mark = CELL[state]
    rejected = sum(1 for h in hist if h.get("verdict") == "reject")
    recheck = " · 재확인 필요" if check["recheck"] else ""
    hist_t = f", 반려 이력 {rejected}회" if rejected else ""
    ring = rej_badge(rejected, kind)  # 마지막 확인 시각은 진행 단계 L6 행에만 (D-42)
    again = state_badge("재확인 필요") if check["recheck"] else ""
    return (f"<button type='button' class='cbtn l6row op {kind}{' had' if rejected else ''}' data-open='{e(mart)}:L6' "
            f"aria-haspopup='dialog' aria-expanded='false' "
            f"aria-label='{e(RUNG_PLAIN['L6'])} {e(state)}{e(recheck)}{e(hist_t)} · 마트 전체 · 상세 보기' id='{e(l6_id(mart))}'>"
            f"<span class='nd-mk'>{cell_mark(mark)}</span><span class='vh'>{e(state)}</span>"
            f"<b data-rung='L6'>L6 {e(RUNG_PLAIN['L6'])}</b>"
            f"{tag('결재 후 · 마트 전체')}{ring}{again}"
            f"<span class='chev'>{icon('chev')}</span></button>")


def ladder_summary(mart, s):
    """요약 한 줄. 수치는 collect()의 grid.summary 값 그대로."""
    kind = "pass" if s["passed"] == s["cells"] else "wait"
    variant, mark = ("pass", "pass") if kind == "pass" else ("neutral", "wait")
    count = f"{num(mart + '.ladder.cells', s['cells'])}칸 중 {num(mart + '.ladder.passed', s['passed'])}칸 통과"
    return (f"<div class='lad-sum'>{badge(variant, count, mark)}"
            f"<span>반려 이력 {num(mart + '.ladder.rejected', s['rejected'])}칸</span>"
            f"<span class='lad-hint' data-hint>{icon('info')}{e(LADDER_HINT)}</span></div>")


def legend():
    """범례 한 줄: "[통과] 통과  [반려] 반려  …  고리 설명"(대괄호 = 아이콘, D-36). 구분점 대신 간격(flex gap)으로 나눈다
    (아이콘 묶음과 점의 기준선이 달라 점이 마침표처럼 낮게 보이던 문제, DESIGN §3 위쪽 막대와 같은 방식)."""
    marks = "".join(f"<span class='lg-i'>{icon(k)}{e(t)}</span>" for k, t in LEGEND_MARKS)
    return f"<p class='legend' data-legend='marks'>{marks}<span class='lg-i'>{e(LEGEND_RING)}</span></p>"


def blocks_detail(d, many):
    """위험 명령 차단 서랍 (D-27): 사유별 수(LABELS의 쉬운 이름) · 마트별 수 · "전체 보기에서 보기"(마트가 여럿일 때, #mart=all로
    옮기고 서랍을 닫는다). 명령 원문·경로·오류 원문은 넣지 않는다(결정 71). dialog로 옮기는 것은 T5."""
    m11 = d["summary"]["M11"]
    reasons = [[label(k), num(f"all.M11.by_reason.{k}", v)] for k, v in m11["by_reason"].items()]
    marts = [[e(k), num(f"all.M11.by_mart.{k}", v)] for k, v in m11["by_mart"].items()]
    go = (f"<p class='dp-go'><a class='lk' href='#mart=all' data-close data-go='all'>전체 보기에서 보기</a></p>" if many else "")
    by_reason = sub("사유별", table(["사유", "건수"], reasons, right=(1,))) if reasons else f"<p class='note'>{e(dd.NONE)}</p>"
    by_mart = sub("마트별", table(["마트", "건수"], marts, right=(1,))) if marts else ""
    inner = f"<p class='lead'>{e(BLOCKS_LEAD)}</p>{by_reason}{by_mart}{go}"
    title = f"위험 명령 차단 {num('all.M11.count', m11['count'])}건"
    return detail(BLOCKS_KEY, title, inner, "전체 마트", f"위험 명령 차단 {m11['count']}건")


FOLD_ALL = "모두 보기"  # 사다리 머리 조작 버튼 (D-40)
FOLD_TAIL = "모두 첫 시도 통과"  # 접힌 줄 끝 (D-40): "<task> · <task> 모두 첫 시도 통과"


def first_try_pass(row):
    """L0~L5 모든 칸을 첫 시도에 통과한 행인가 (D-40): 시도 1번이 통과이고, 칸마다 기록 1건이 통과다.
    이력이 있거나 지금 막힌 행, 아직 안 돈 칸이 있는 행은 아니다."""
    v = row["verdicts"]
    if len(v) != 1 or v[0]["verdict"] != "pass":
        return False
    return all(len(row["cells"][k]) == 1 and item_status(row["cells"][k][0], set()) == "통과" for k in dd.LADDER_RUNGS)


def fold_groups(rows):
    """연속된 첫 시도 통과 행끼리 묶는다(task 순서 그대로). 행 번호 → 그 구간의 행 번호 목록. 접지 않는 행은 없다."""
    out, run = {}, []
    for i, r in enumerate([*rows, None]):
        if r is not None and first_try_pass(r):
            run.append(i)
            continue
        for j in run:
            out[j] = run
        run = []
    return out


def fold_line(mart, n, names):
    """접힌 줄 = 사다리 roving 칸 하나(펼치기 모양 ▸ + 본문색, D-24). JS가 없으면 보이지 않고 행이 모두 펼쳐져 있다(D-15)."""
    gid = safe_id("f", mart, n)
    text = " · ".join(names) + " " + FOLD_TAIL
    return (f"<li class='lfold' data-fold-line='{e(gid)}'><button type='button' class='lfold-b tw' data-unfold='{e(gid)}' "
            f"aria-expanded='false'>{icon('tri')}<span>{e(text)}</span></button></li>")


def render_ladder(d, mart, m, many):
    """검사 사다리: 열 제목 한 줄(L0~L5 쉬운 이름) + task마다 이름·층·시도 요약과 동그라미 6개 + L6 한 줄 + 범례 + 상세 서랍."""
    grid = m["grid"]
    tasks, rejections = grid["rows"], m["rejections"]
    # 열 제목 두 줄: "L5" / "다시 돌려도 같은지" (D-16). 통과 조건은 칸 서랍 본문에 있다
    cols = "".join(f"<span class='rung' data-rung='{e(r)}'><span class='rung-k'>{e(r)}</span>"
                   f"<span class='rung-n'>{e(RUNG_PLAIN[r])}</span></span>" for r in dd.LADDER_RUNGS)
    rows, details = [], []
    groups = fold_groups(tasks)
    for n, r in enumerate(tasks):
        task, layer = r["task"], r["layer"]
        halted = {v["iteration"] for v in r["verdicts"] if v["verdict"] == "halt"}
        nodes = "".join(ladder_node(mart, task, k, r["cells"][k], halted) for k in dd.LADDER_RUNGS)
        g = groups.get(n)
        if g and g[0] == n:  # 접힌 줄은 그 구간 첫 행 앞에 (D-40)
            rows.append(fold_line(mart, n, [tasks[i]["task"] for i in g]))
        fold = f" data-fold-g='{e(safe_id('f', mart, g[0]))}'" if g else ""
        rows.append(f"<li class='lrow' id='{e(row_id(mart, task))}'{fold}><button type='button' class='tbtn op' data-open='{e(mart)}:{e(task)}' aria-haspopup='dialog' "
                    f"aria-expanded='false' aria-label='{e(task)} {e(LAYER_PLAIN.get(layer, layer))} · {e(attempt_sentence(r['verdicts']))} · 상세 보기'>"
                    f"<span class='tn'><code>{e(task)}</code>{tag(e(LAYER_PLAIN.get(layer, layer)))}"
                    f"</span><span class='iters'>{e(attempt_sentence(r['verdicts']))}"
                    f"</span><span class='chev'>{icon('chev')}</span></button><div class='nodes'><span class='rail' aria-hidden='true'></span>{nodes}</div></li>")
        details.append(row_detail(mart, r, halted))
        details.extend(cell_detail(mart, grid, r, k, r["cells"][k], halted, rejections, m["summary"]["M3"])
                       for k in dd.LADDER_RUNGS)
    body = (f"<ol class='lrows' aria-label='{e(mart)} task별 검사'>{''.join(rows)}</ol>" if tasks
            else f"<p class='note lempty'>{e(dd.NONE)}</p>")
    details.append(l6_detail(mart, grid["l6"], m["l6_check"]))
    if d["summary"]["M11"]["count"]:
        details.append(blocks_detail(d, many))
    pid = sid("ladder-panel", mart, many)
    panel = (f"<div class='dpanel' id='{e(pid)}' data-panel role='dialog' aria-modal='false' aria-label='상세'>"
             f"<div class='dp-bar'><span class='eyebrow'>상세</span><button type='button' class='dp-x more' data-close "
             f"aria-label='상세 닫기'>닫기</button></div>"
             f"<div class='dp-body'>{''.join(details)}</div></div>")
    show_all = (f"<button type='button' class='more lad-all' data-fold-all aria-pressed='false'>{e(FOLD_ALL)}</button>"
                if groups else "")
    return (f"<section id='{e(sid('ladder', mart, many))}' data-section='ladder' class='card lad'>"
            f"<div class='lad-h'><h2>{e(dict(SECTIONS)['ladder'])}</h2><span class='aside'>{e(LADDER_SUB)}</span>{show_all}</div>"
            f"{ladder_summary(mart, grid['summary'])}"
            f"<div class='lhead' aria-hidden='true'><span></span><div class='lcols'>{cols}</div></div>{body}"
            f"{l6_row(mart, grid['l6'], m['l6_check'])}{legend()}"
            f"{panel}</section>")


# ---------- 지금 막힌 반려 카드 (D-42) ----------
# 반려는 숫자 카드(수)·사다리(고리)·서랍(내용) 세 곳에만 둔다. "반려 상세" 섹션과 상세 표의 "task별 반려" 표는 없앴다.
# 지금 막고 있는 반려(rejection_now)가 있을 때만 숫자 카드와 사다리 사이에 빨간 카드 1장. 한 건 = 한 줄 열기 모양 링크(그 칸 서랍)
NOW_MAX = 3  # 카드 한 장에 보이는 건수(넘으면 "외 N건")


def render_now_rejections(mart, m):
    rows = [r for r in m["rejections"] if rejection_now(m, r)]
    if not rows:
        return ""
    lis = []
    for r in rows[:NOW_MAX]:
        rung = r["caught_by_rung"]
        name = ERROR_INFO.get(r["error_type"], (r["error_type"] or dd.NONE, ""))[0]
        inner = (f"<code>{e(r['id'])}</code><span class='nr-w'><code>{e(r['task'])}</code> · {e(rung)} "
                 f"{e(RUNG_PLAIN.get(rung, ''))}</span><span class='nr-y'>{e(name)}</span>")
        t = rejection_target(mart, m, r)
        if t:
            lis.append(f"<li><a class='op nr-go' href='#{e(t[1])}' data-open='{e(t[0])}' aria-haspopup='dialog'>{inner}"
                       f"<span class='chev'>{icon('chev')}</span></a></li>")
        else:
            lis.append(f"<li><span class='nr-go'>{inner}</span></li>")
    more = f"<p class='note nr-more'>외 {len(rows) - NOW_MAX}건</p>" if len(rows) > NOW_MAX else ""
    return (f"<section class='card now-rej' aria-label='지금 막힌 반려'><h3>{state_badge(dd.REJECT, '지금 막힌 반려')}"
            f"<span class='note'>{len(rows)}건</span></h3><ul class='nr-l'>{''.join(lis)}</ul>{more}</section>")


# ---------- 규칙 ----------

def m10_table(rows):
    """규칙별·마트별 승격 전후 같은 유형 반려 (08 M10). 전후 건수만 보이고 효과를 단정하지 않는다."""
    if not rows:
        return ""
    body = [[f"<code>{e(x['rule_id'])}</code>", e(x["error_type"]), f"<code>{e(m)}</code>",
             num(f"rules.m10.{x['rule_id']}.{m}.before", v["before"]), num(f"rules.m10.{x['rule_id']}.{m}.after", v["after"]),
             "제외 목록 반려 " + num(f"rules.m10.{x['rule_id']}.{m}.excluded", v["excluded"]) + "건 포함"]
            for x in rows for m, v in x["by_mart"].items()]
    head = ["규칙", "유형", "마트", "전", "후", "참고"]
    return (f"<div class='card rule-box'><div class='hd'><b>승격 전후 같은 유형 반려</b></div>"
            f"<p>건수만 보입니다. 줄었어도 규칙의 효과를 증명하지는 않습니다.</p>{table(head, body, right=(3, 4))}</div>")


def render_rules(d):
    """규칙 구역. 글자 속 R-번호(근거 반려·뺀 반려)는 그 반려 칸 서랍 링크(D-28, 마트가 여럿이면 그 마트 보기로 옮겨 연다)."""
    r = d["rules"]
    refs = ref_map(d)
    learned = [[f"<code>{e(x['file'])}</code>", e(x["title"]), e(", ".join(x["paths"]) or "-"), ref_ids(e(x["source"]), refs),
                e(x["state"])] for x in r["learned"]]
    cands = [[f"<code>{e(x['id'])}</code>", e(x["title"]), e(x["error_type"]), ref_ids(e(x["basis"]), refs), e(x["checks"]),
              e(x["state"]) + (f" <span class='note'>(기록된 상태 {e(x['recorded_state'])})</span>"
                               if x["recorded_state"] != x["state"] else "")] for x in r["candidates"]]

    def box(title, key, rows, desc, head):
        body = table(head, rows) if rows else f"<div class='empty-state'>{e(dd.NONE)}</div>"
        return (f"<div class='card rule-box'><div class='hd'><b>{e(title)}</b><span class='cnt'>{num(key, len(rows))}</span>"
                f"<span class='note'>건</span></div><p>{e(desc)}</p>{body}</div>")
    promoted = num("rules.promoted", r["promoted"])
    status = f"실제로 승격된 규칙은 {promoted}건입니다."
    ids = ", ".join(ref_ids(e(x), refs) for x in r["excluded"])  # 모르는 번호는 링크 없이 글자만
    skipped = f"({ids})" if ids else ""
    if not learned and not cands:  # 빈 상태 = 줄 하나, 표 없음 (D-41). 0인 값도 data-k로 남긴다(D-50)
        n_ex = len(r["excluded"])
        ex = (f"집계 제외 {num('rules.excluded', n_ex)}건{skipped}" if n_ex
              else f"집계 제외 없음{hidden_num('rules.excluded', 0)}")
        line = (f"<p class='rules-empty' data-rules-status>승격된 규칙 없음{hidden_num('rules.learned', 0)} · "
                f"후보 없음{hidden_num('rules.candidates', 0)} · {ex}{hidden_num('rules.promoted', r['promoted'])}</p>")
        return section("rules", line + m10_table(r["m10"]), e("반복된 실패에서 사람이 결재해 만든 규칙"))
    inner = (box("승격 규칙", "rules.learned", learned, "사람이 결재해 팀 규칙이 된 것", ["파일", "제목", "적용 경로", "출처", "상태"])
             + box("규칙 후보", "rules.candidates", cands, "결재를 기다리는 후보",
                   ["id", "제목", "유형", "근거 반려", "검사 id", "상태"]))
    note = (f"<p class='note' data-rules-status>{status} 규칙 후보 집계에서 뺀 반려는 "
            f"{num('rules.excluded', len(r['excluded']))}건{skipped}입니다.</p>")
    return section("rules", f"<div class='rules'>{inner}</div>{note}{m10_table(r['m10'])}",
                   e("반복된 실패에서 사람이 결재해 만든 규칙"))


# ---------- 상세 표 ----------

def zero_list(pairs, ident_):
    """0인 지표 목록 (D-41): "0인 지표 N개"를 펼치기 모양(▸)으로, 안에 이름과 값(data-k 그대로)."""
    lis = "".join(f"<li>{e(k)} {v}</li>" for k, v in pairs)
    return (f"<details class='zeros' data-cell='zeros:{e(ident_)}'><summary class='tw'>{icon('tri')}0인 지표 {len(pairs)}개"
            f"</summary><ul class='zero-l'>{lis}</ul></details>")


def tally_rows(prefix, t):
    rows = [[label(k), num(f"{prefix}.by_kind.{k}.count", v["count"]), num(f"{prefix}.by_kind.{k}.minutes", v["minutes"])]
            for k, v in t["by_kind"].items()]
    rows.append(["합계", num(f"{prefix}.count", t["count"]), num(f"{prefix}.minutes", t["minutes"])])
    return rows


def cost_table(prefix, m4):
    rows = [[e("호출 수"), num(f"{prefix}.calls", m4["calls"])]]
    for k in sorted(dd.COST_FIELDS, key=lambda x: x == "total_cost_usd"):  # 합계 행이 맨 아래
        blank = m4[k + "_null"]
        tail = f" <span class='note'>빈 값 {e(blank)}건</span>" if blank else ""
        rows.append([label(k), num(f"{prefix}.{k}", m4[k], fmt_cost(k, m4[k])) + tail])
    return (table([], rows, right=(1,), total=True)
            + "<p class='note'>정가 환산 추정입니다. 실제 청구액이 아닙니다.</p>")


def hook_tables(m11):
    rows = [[label(k), num(f"all.M11.by_reason.{k}", v)] for k, v in m11["by_reason"].items()]
    rows += [[e(k), num(f"all.M11.by_mart.{k}", v)] for k, v in m11["by_mart"].items()]
    ids = m11["excluded"]
    tail = f"<p class='note'>뺀 id <code>{e(id_range(ids))}</code></p>" if ids else ""  # 연속일 때만 줄이므로 목록이 다 보인다
    return (f"<div><h3>위험 명령 차단 <span class='note'>시험 id 제외</span></h3>"
            f"{table([], rows, right=(1,))}{tail}</div>")


def render_summary(d, mart, m, many):
    s, p = m["summary"], mart
    it, m1, m12, m2 = s["iterations"], s["M1"], s["M12"], s["M2"]
    rp_main = m1["main"]["approval_by_stage"]["rule_promotion"]["count"]
    rp_maint = m1["maintenance"]["approval_by_stage"]["rule_promotion"]["count"]
    # (이름, 값 HTML, 0인가). 0인 지표는 숨기고 "0인 지표 N개"(펼치기 모양)로 이름을 연다. 값·data-k는 details 안에 남는다 (D-41·D-50)
    metrics = [("같은 유형 연속 반려", f"{num(p + '.iterations.streak', it['streak'])}회 {e(it['streak_key'] or '')}",
                it["streak"] == 0),
               ("결재 후 L6 반려", num(p + ".M2.post_approval.count", m2["post_approval"]["count"]) + "건",
                m2["post_approval"]["count"] == 0),
               ("재사용 상류 task", num(p + ".reused_upstream", len(s["reused_upstream"])) + "개 "
                + e(", ".join(s["reused_upstream"])), not s["reused_upstream"]),
               ("상류 준비 스캔량", num(p + ".prep_bytes", s["prep_bytes"], fmt_mb(s["prep_bytes"])), s["prep_bytes"] == 0),
               ("규칙 승격 결재 (사람 결재 수 밖)",
                num(p + ".M1.main.approval_by_stage.rule_promotion.count", rp_main) + "건 · 유지보수 "
                + num(p + ".M1.maintenance.approval_by_stage.rule_promotion.count", rp_maint) + "건",
                rp_main == 0 and rp_maint == 0)]
    shown = [(k, v) for k, v, zero in metrics if not zero]
    zeros = [(k, v) for k, v, zero in metrics if zero]
    head = (kv(shown) if shown else "") + (zero_list(zeros, sid("summary", mart, many)) if zeros else "")
    kinds = ["종류", "건수", "분"]
    maint, m12m = m1["maintenance"], m12["maintenance"]["count"]
    if maint["count"] == 0 and maint["minutes"] == 0 and m12m == 0:  # 전부 0이면 줄 하나 (D-41), 값은 숨은 data 칸
        keys = [(f"{p}.M1.maintenance.by_kind.{k}.{f}", v[f]) for k, v in maint["by_kind"].items() for f in ("count", "minutes")]
        keys += [(p + ".M1.maintenance.count", 0), (p + ".M1.maintenance.minutes", 0), (p + ".M12.maintenance.count", 0)]
        maint_html = (f"<p class='note' data-maint-empty>유지보수 개입 없음"
                      f"{''.join(hidden_num(k, v) for k, v in keys)}</p>")
    else:
        maint_html = (table(kinds, tally_rows(p + ".M1.maintenance", maint), right=(1, 2), total=True)
                      + f"<p class='note'>유지보수 결재 {num(p + '.M12.maintenance.count', m12m)}건</p>")
    cols1 = (f"<div class='cols'><div><h3>본 측정 개입 <span class='note'>첫 결재 2까지</span></h3>"
             + table(kinds, tally_rows(p + ".M1.main", m1["main"]), right=(1, 2), total=True) + "</div>"
             + "<div><h3>유지보수 개입 <span class='note'>첫 결재 2 뒤</span></h3>"
             + maint_html + "</div>"
             + "<div><h3>운영 <span class='note'>본 측정 밖</span></h3>"
             + table([], [["건수", num(p + ".M1.ops_run.count", m1["ops_run"]["count"])],
                          ["분", num(p + ".M1.ops_run.minutes", m1["ops_run"]["minutes"])]], right=(1,)) + "</div></div>")
    cols2 = ("<div class='cols'><div><h3>비용 세부 <span class='note'>정가 환산 추정</span></h3>" + cost_table(p + ".M4", s["M4"]) + "</div>"
             + ("" if many else hook_tables(d["summary"]["M11"])) + "</div>")
    note = f"<p class='note'>{e(ITER0_NOTE)}</p>"  # collect()의 notes.iteration0_halts를 사용자 말로 (D-21)
    return folded("summary", head + cols1 + cols2 + note, "개입·유지보수·운영·비용 세부·차단",
                  ident_=sid("summary", mart, many))


def overview_summary(d):
    g = d["summary"]
    m11 = g["M11"]
    inner = ("<div data-block='all'><h3>전체</h3>"
             + kv([("위험 명령 차단 합계", num("all.M11.count", m11["count"]) + "건"),
                   ("사람 개입 시간 합계", num("all.M1_minutes_main", g["M1_minutes_main"]) + "분"),
                   ("사람 결재 합계", num("all.M12_main", g["M12_main"]) + "건"),
                   ("반려 유형 합계", tags("all.M2_by_error_type", g["M2_by_error_type"]))])
             + "</div><div class='cols'><div><h3>비용 전체 <span class='note'>정가 환산 추정</span></h3>"
             + cost_table("all.M4", g["M4"]) + "</div>" + hook_tables(m11) + "</div>")
    return folded("summary", inner, "마트를 합친 값·차단", ident_="summary-all")


# ---------- 화면 조립 ----------

def mart_title(mart, m):
    ko = m.get("name_ko")
    return f"<code>{e(mart)}</code>" + (f" {e(ko)}" if ko else "")


def render_mart(d, i, mart, m, items):
    """마트 보기 (D-44): 머리 한 줄 → 2열(왼쪽 진행 단계 + 다음 행동, 오른쪽 숫자 카드 6장 → 지금 막힌 반려 → 검사 사다리 → 접힘 상세)
    → 규칙(마트 1개일 때). 모두 그 마트 것만 보인다."""
    many = len(d["marts"]) > 1
    mine = [x for x in items if x["mart"] == mart]
    eyebrow = f"contract v{e(m['version'])}{requester(m['requested_by'])}"  # "마트 N / M"은 없앴다 (D-18)
    prefix = f"{mart}.queue" if many else "queue"
    badge_html, why = mart_band(mart, m, mine, prefix)
    # L6 시각은 진행 단계 L6 행에만 둔다(D-42). 머리 오른쪽 묶음은 시각을 빼면 남는 글자가 없어 없앴다
    head = head_line(sid("queue", mart, many), eyebrow, mart_title(mart, m), badge_html, todo_chips(mine, prefix, mart),
                     "", why)  # 보조 링크 줄은 다음 행동 카드로 옮겼다 (D-44)
    # 왼쪽(sticky): 진행 단계 → 다음 행동. 오른쪽: 숫자 카드 → (지금 막힌 반려 카드) → 사다리 → 세부(접힘) (D-44)
    body = (f"<div class='mgrid'><div class='mleft'>{render_stages(mart, m, many, mine)}{render_next(d['header'], m, mine)}</div>"
            f"<div class='mcol'>{render_cards(d, mart, m, many)}{render_now_rejections(mart, m)}"
            f"{render_ladder(d, mart, m, many)}{render_summary(d, mart, m, many)}</div></div>")
    parts = [head, body]
    if not many:
        parts.append(render_rules(d))  # 규칙은 마트 보기 아래(마트가 여럿이면 보기 밖) 그대로
    return (f"<div class='view' id='mart={e(mart)}' data-view='{e(mart)}' data-title='{e(tab_title(mart, len(mine)))}'>"
            f"{''.join(parts)}</div>")


def tab_title(name, todo):
    """탭 제목 (D-17): "(N) 검사·결재 진행 · <마트 이름|전체> · pipeline-harness". N = 그 보기의 사람 할 일(0이면 없음)."""
    head = f"({todo}) " if todo else ""
    return f"{head}{TAB_TITLE[0]} · {name} · {TAB_TITLE[1]}"


def render_overview(d, items):
    """전체 보기 (D-46): 머리 한 줄(전체 상태 배지, 마트별 사람 할 일) → 마트별 한 줄 카드(사람 할 일 → 막힘 → 진행 중 → 완료)
    → 합계 숫자 카드 5장 → 접힘 상세. 규칙은 그 아래(보기 밖). 마트별 진행 단계 표는 없앴다. 차단 카드용 서랍이 이 보기에 있다."""
    badge_html = overall_band(d, items)
    head = head_line("queue", e(f"마트 {len(d['marts'])}개"), "전체 파이프라인", badge_html, todo_chips(items, "queue"),
                     below=todo_groups(items))
    panel = ""
    if d["summary"]["M11"]["count"]:
        panel = (f"<div class='dpanel' id='ladder-panel-all' data-panel role='dialog' aria-modal='false' aria-label='상세'>"
                 f"<div class='dp-bar'><span class='eyebrow'>상세</span><button type='button' class='dp-x more' data-close "
                 f"aria-label='상세 닫기'>닫기</button></div><div class='dp-body'>{blocks_detail(d, False)}</div></div>")
    parts = [head, overview_marts(d, items), overview_cards(d), overview_summary(d), panel]
    return (f"<div class='view' id='mart=all' data-view='all' data-title='{e(tab_title('전체', len(items)))}'>"
            f"{''.join(parts)}</div>")


def render_body(d, items):
    marts = list(d["marts"].items())
    if not marts:
        return f"<p class='note'>{e(dd.NONE)}</p>"
    views = "".join(render_mart(d, i, mart, m, items) for i, (mart, m) in enumerate(marts, 1))
    if len(marts) == 1:
        return views
    return render_overview(d, items) + views + render_rules(d)


CSS = """
/* ===== 1. 디자인 토큰 ===== */
:root{
  /* 글자 크기 다섯 단계 (D-32): 캡션 · 본문 · 소제목 · 섹션 제목 · 숫자. 13px은 캡션 전용 */
  --fs-cap:13px; --fs-body:14px; --fs-sub:16px; --fs-h:20px; --fs-num:28px;
  /* 줄 간격: 크기 단계마다 하나 */
  --lh-cap:1.45; --lh-body:1.55; --lh-sub:1.4; --lh-h:1.3; --lh-num:1.15;
  /* 굵기 세 가지 (D-33): 라벨·본문 400, 제목·task 이름·배지 600, 숫자 700 */
  --fw-regular:400; --fw-semibold:600; --fw-bold:700;
  /* 간격 (4px 단위) */
  --sp-1:4px; --sp-2:8px; --sp-3:12px; --sp-4:16px; --sp-5:20px; --sp-6:24px; --sp-8:32px; --sp-10:40px; --sp-12:48px;
  /* 모서리 */
  --r-sm:6px; --r-md:10px; --r-lg:14px; --r-pill:999px;
  /* 크기 */
  /* --top-h = 위쪽 막대의 실제 높이(켜짐·일시정지·꺼짐 × 새 기록 안내 유무 중 가장 높은 것). T3(테마 토글)에서 실데이터로
     scripts/dev/measure_topbar.py로 다시 잼: 960px 이상은 토글이 붙어 가장 긴 표시가 둘째 줄로 감겨 약 108px(1440px도 꺼짐 + 안내에서
     감김) → 112px 한 값. 900px 이하는 15. 반응형(약 141~169px → 172px). 진행 단계 sticky 위치·scroll-padding에 쓴다.
     --top-min = 막대 최소 높이 */
  --content-max:1160px; --top-h:112px; --top-min:60px; --stages-w:300px; --task-w:200px; --node:30px; --panel-w:460px;
  /* 글꼴 (D-01): 웹폰트 없이 한글 글꼴을 먼저 두어 한 글꼴이 한글·영문·숫자를 모두 그린다(영문 글꼴이 앞이면 섞여 보인다) */
  --font-sans:"Pretendard","Malgun Gothic","Apple SD Gothic Neo",system-ui,-apple-system,"Segoe UI",sans-serif;
  --font-mono:ui-monospace,Consolas,"D2Coding",monospace;

  /* 밝은 화면 색 */
  --bg:#F3F5F9; --surface:#FFFFFF; --surface-2:#F7F9FC; --line:#E1E6EE; --line-strong:#C9D2DE;
  --fg:#14213D; --fg-2:#3F4E66; --muted:#5A6982;
  --pass:#0F9D7A; --pass-ink:#0A7357; --pass-tint:#E2F4EE; --pass-solid:#0A7357;
  --fail:#D1242F; --fail-ink:#B01E28; --fail-tint:#FCE9EA;
  --ai:#D9730D;   --ai-ink:#9E5208;   --ai-tint:#FDF0E1;   --ai-solid:#B45F0A;
  --wait:#6B7280; --wait-ink:#555C69; --wait-tint:#EEF0F3;
  --on-solid:#FFFFFF;
  --shadow-sm:0 1px 2px rgba(16,24,40,.06),0 1px 3px rgba(16,24,40,.04);
  --shadow-md:0 4px 12px rgba(16,24,40,.08);
  --shadow-pop:-8px 0 24px rgba(20,33,61,.14);
  --scrim:rgba(11,20,36,.25);
  --focus:#2563EB; --link:#1D4ED8; --rail:#808B9D;
  /* 사다리 원 hover 링 (D-24). --link는 --focus와 1.3:1이라 링끼리 구분되지 않아 따로 둔다: 포커스·선택(--fg)·지난 반려(--rail)와
     모두 1.5:1 이상 */
  --ring-hover:#1E40AF;
}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){
  --bg:#0B1424; --surface:#122039; --surface-2:#172843; --line:#22375A; --line-strong:#2F4873;
  --fg:#E8EEF7; --fg-2:#BCC7D8; --muted:#97A6BE;
  --pass:#34C79B; --pass-ink:#5AD6AF; --pass-tint:#0F352F; --pass-solid:#34C79B;
  --fail:#FF6B6B; --fail-ink:#FF8F8F; --fail-tint:#3B1A24;
  --ai:#F59E42;   --ai-ink:#FFB46A;   --ai-tint:#3A2814;   --ai-solid:#F59E42;
  --wait:#9AA6B8; --wait-ink:#AEB8C8; --wait-tint:#1E2C45;
  --on-solid:#0B1424;
  --shadow-sm:0 1px 2px rgba(0,0,0,.4); --shadow-md:0 4px 14px rgba(0,0,0,.35); --shadow-pop:-8px 0 28px rgba(0,0,0,.55);
  --scrim:rgba(0,0,0,.45);
  --focus:#7AA7FF; --link:#8AB4FF; --rail:#6A80A2; --ring-hover:#3358B8;
}}
:root[data-theme="dark"]{
  --bg:#0B1424; --surface:#122039; --surface-2:#172843; --line:#22375A; --line-strong:#2F4873;
  --fg:#E8EEF7; --fg-2:#BCC7D8; --muted:#97A6BE;
  --pass:#34C79B; --pass-ink:#5AD6AF; --pass-tint:#0F352F; --pass-solid:#34C79B;
  --fail:#FF6B6B; --fail-ink:#FF8F8F; --fail-tint:#3B1A24;
  --ai:#F59E42;   --ai-ink:#FFB46A;   --ai-tint:#3A2814;   --ai-solid:#F59E42;
  --wait:#9AA6B8; --wait-ink:#AEB8C8; --wait-tint:#1E2C45;
  --on-solid:#0B1424;
  --shadow-sm:0 1px 2px rgba(0,0,0,.4); --shadow-md:0 4px 14px rgba(0,0,0,.35); --shadow-pop:-8px 0 28px rgba(0,0,0,.55);
  --scrim:rgba(0,0,0,.45);
  --focus:#7AA7FF; --link:#8AB4FF; --rail:#6A80A2; --ring-hover:#3358B8;
}

/* ===== 2. 기본 ===== */
*{box-sizing:border-box}
html{scroll-padding-top:calc(var(--top-h) + var(--sp-8))}  /* 주소 #mart= 앵커로 스크롤돼도 첫 화면이 위쪽 막대에 가리지 않게 */
body{margin:0;background:var(--bg);color:var(--fg);font:var(--fw-regular) var(--fs-body)/var(--lh-body) var(--font-sans);
  -webkit-font-smoothing:antialiased;word-break:keep-all;font-variant-numeric:tabular-nums}
h1,h2,h3,h4,p{margin:0}
code,.mono{font-family:var(--font-mono);font-size:1em}
button{font:inherit;color:inherit}
.num{font-variant-numeric:tabular-nums}
.vh{position:absolute;width:1px;height:1px;margin:-1px;padding:0;overflow:hidden;clip-path:inset(50%);white-space:nowrap}
/* 본문으로 건너뛰기 (D-31): 평소 화면 밖, 포커스를 받으면 왼쪽 위에 테두리 버튼 모양. position:absolute라 막대 높이에 영향 없다 */
.skip{position:absolute;left:var(--sp-4);top:var(--sp-2);z-index:60;transform:translateY(-300%)}
.skip:focus{transform:none}
/* 아이콘 한 벌 (D-36): 글자 크기의 1.15em, currentColor. 숨은 symbol 묶음은 자리를 차지하지 않는다 */
.ic-defs{position:absolute;width:0;height:0;overflow:hidden}
.ic{display:inline-block;flex:none;width:1.15em;height:1.15em;vertical-align:-.2em;overflow:visible}
/* Badge 1종 (D-33·D-35): 알약, 13px·600, 옅은 바탕 + 진한 글자. variant 4개(pass·fail·todo·neutral), 크기 옵션 lg 14px·700.
   상태 Badge는 아이콘을 붙이고 분류 Badge(층·역할·범위·유형 태그)는 아이콘 없이 neutral */
.bd{display:inline-flex;align-items:center;gap:4px;flex:none;min-height:22px;padding:1px 10px;border-radius:var(--r-pill);
  font-size:var(--fs-cap);line-height:var(--lh-cap);font-weight:var(--fw-semibold);white-space:nowrap;
  background:var(--wait-tint);color:var(--fg-2)}
.bd.pass{background:var(--pass-tint);color:var(--pass-ink)}
.bd.fail{background:var(--fail-tint);color:var(--fail-ink)}
.bd.todo{background:var(--ai-tint);color:var(--ai-ink)}
.bd.neutral{background:var(--wait-tint);color:var(--fg-2)}
.bd.lg{gap:6px;min-height:30px;padding:2px var(--sp-3) 2px 10px;font-size:var(--fs-body);line-height:var(--lh-body);font-weight:var(--fw-bold)}
/* StatusDot 1종 (D-35): 진행 단계 행·마트 탭·전체 보기 단계 표. 모양 = 아이콘, 색 = variant 색, 크기는 em */
.sd-dot{display:inline-grid;place-items:center;flex:none;line-height:1;color:var(--wait)}
.sd-dot.pass{color:var(--pass)}.sd-dot.fail{color:var(--fail)}.sd-dot.todo{color:var(--ai)}.sd-dot.neutral{color:var(--wait)}
a{color:inherit}
:focus-visible{outline:2px solid var(--focus);outline-offset:2px;border-radius:4px}
/* 누를 수 있는 것의 모양 다섯 가지 (D-24). 이 밖의 모양은 만들지 않는다.
   ① 글 속 = 이동 모양 .lk: --link 글자, hover·포커스 때 밑줄(task 이름·R-0001·C-01·외부 링크, 서랍을 열어도 글 속이면 이 모양)
   ② 덩어리 = 열기 모양 .op: 오른쪽 --link ›, hover 때 옅은 바탕(그림자는 카드에만)  ③ 사다리 원 .nd: hover 때 바깥 링
   ④ 조작 = 테두리 버튼 .more  ⑤ 펼치기 = summary.tw: ▸ + 본문색 글자, 펼치면 회전 */
.lk{color:var(--link);text-decoration:none;background:transparent;border:0;padding:0;font:inherit;cursor:pointer}
.lk:hover,.lk:focus-visible{text-decoration:underline;text-underline-offset:2px}
.lk code{color:inherit}
.lk.ext>.ic{margin-left:2px;width:1em;height:1em;vertical-align:-.1em}  /* 외부 링크 ↗ (D-29) */
.lk.main{font-weight:var(--fw-semibold)}  /* 주요 링크: 상태 문구의 [행동] 자리 (D-05) */
.op .chev,.chev{flex:none;color:var(--link);line-height:1}
summary.tw{display:flex;align-items:center;gap:6px;list-style:none;cursor:pointer;color:var(--fg)}
summary.tw::-webkit-details-marker{display:none}
summary.tw>.ic{width:14px;height:14px;transition:transform .15s}
details[open]>summary.tw>.ic{transform:rotate(90deg)}

/* ===== 3. 배치 ===== */
main{min-width:0;max-width:calc(var(--content-max) + 2 * var(--sp-4));margin:0 auto;padding:var(--sp-6) var(--sp-4) var(--sp-12)}
.purpose{margin-bottom:var(--sp-4);font-size:var(--fs-body);line-height:var(--lh-body);color:var(--muted)}  /* 목적 한 줄 (D-03), sticky 아님 */
.wrap{display:grid;grid-template-columns:minmax(0,1fr);gap:var(--sp-8)}
.wrap>*{min-width:0}
.sec-h{display:flex;align-items:baseline;justify-content:space-between;gap:var(--sp-4);flex-wrap:wrap;margin-bottom:var(--sp-4)}
.sec-h h2{font-size:var(--fs-h);font-weight:var(--fw-semibold);line-height:var(--lh-h);letter-spacing:-.01em}
.sec-h .aside{font-size:var(--fs-body);line-height:var(--lh-body);color:var(--muted)}
.card{background:var(--surface);border:1px solid var(--line);border-radius:var(--r-lg);box-shadow:var(--shadow-sm)}
.eyebrow{font-size:var(--fs-body);line-height:var(--lh-body);font-weight:var(--fw-regular);color:var(--muted);letter-spacing:.02em}

/* ===== 4. 위쪽 막대: 브랜드 · 마트 탭 · 생성 시각 ===== */
.top{position:sticky;top:0;z-index:30;background:var(--surface);border-bottom:1px solid var(--line)}
.top-in{max-width:calc(var(--content-max) + 2 * var(--sp-4));min-height:var(--top-min);margin:0 auto;padding:var(--sp-2) var(--sp-4);
  display:flex;flex-wrap:wrap;align-items:center;gap:var(--sp-2) var(--sp-5)}
/* 한 줄에 다 들어가지 않으면 오른쪽 묶음(.gen) 전체가 탭 아래 자기 줄로 내려간다. 어떤 요소도 줄어들어 겹치지 않는다 */
.brand{flex:none;display:grid}
.brand b{font-size:var(--fs-sub);line-height:var(--lh-sub);font-weight:var(--fw-semibold)}
.tabs{flex:none;display:flex;gap:var(--sp-1);min-width:0}
/* 탭 (D-25): 해시 링크라 role="tablist" 없이 nav + aria-current="page". 고른 탭 = 굵은 글자(600) + 2px --link 밑줄,
   나머지 = --fg-2 글자, hover 때 --surface-2 바탕. 상태 점(StatusDot)은 그대로 */
.tab{display:inline-flex;align-items:center;gap:6px;min-height:32px;padding:0 var(--sp-3);border-radius:var(--r-sm) var(--r-sm) 0 0;
  border-bottom:2px solid transparent;font-size:var(--fs-body);line-height:var(--lh-body);color:var(--fg-2);text-decoration:none;white-space:nowrap}
.tab:hover{background:var(--surface-2)}
.tab.on{font-weight:var(--fw-semibold);color:var(--fg);border-bottom-color:var(--link)}
.tab.on code{font-weight:var(--fw-semibold)}
.gen{margin-left:auto;flex:0 1 auto;max-width:100%;display:flex;flex-wrap:wrap;justify-content:flex-end;align-items:center;
  gap:var(--sp-1) var(--sp-3);font-size:var(--fs-cap);line-height:var(--lh-cap);color:var(--muted)}
.gen>*{white-space:nowrap}  /* 구분점 "·" 대신 간격으로 나눈다(줄 끝·처음에 점이 홀로 남지 않게) */
.newrec{display:inline-flex;align-items:center;gap:6px}  /* 새 기록 안내와 [새로고침]은 한 덩어리 */
.gen>.bd{padding:1px 6px}  /* 보기 전용 Badge(600): 1020px에서 막대가 두 줄이 되지 않게 옆 여백 6px */
.gen .more{padding:0 var(--sp-2)}  /* 막대 높이를 줄인다. 버튼 모양 통일은 T9 */
/* 테마 토글 (D-14): JS가 있을 때만(html.js). 고른 버튼 = 본문색 글자 + --surface-2 바탕 + --fg-2 테두리 */
.theme{display:none;gap:var(--sp-1)}
html.js .theme{display:inline-flex}
.theme .more[aria-pressed="true"]{color:var(--fg);background:var(--surface-2);border-color:var(--fg-2)}
.nojs{max-width:calc(var(--content-max) + 2 * var(--sp-4));margin:var(--sp-4) auto 0;padding:var(--sp-2) var(--sp-4);
  color:var(--fg-2)}

/* ===== 5. 머리 한 줄 (위치 · 제목 · 상태 배지 · 마지막 확인) ===== */
.head{display:grid;gap:var(--sp-2)}
.head-row{display:flex;flex-wrap:wrap;align-items:center;gap:var(--sp-2) var(--sp-3);min-width:0}
.head-loc{width:100%;font-size:var(--fs-body);line-height:var(--lh-body);font-weight:var(--fw-regular);color:var(--muted)}
.head-t{font-size:var(--fs-num);font-weight:var(--fw-bold);line-height:var(--lh-num);letter-spacing:-.01em;overflow-wrap:anywhere}
.head-when{margin-left:auto;font-size:var(--fs-cap);line-height:var(--lh-cap);color:var(--muted);white-space:nowrap}
.head-why{font-size:var(--fs-body);line-height:var(--lh-body);color:var(--fail-ink);overflow-wrap:anywhere}
.head-st{font-size:var(--fs-body);line-height:var(--lh-body);color:var(--fg-2);overflow-wrap:anywhere}  /* 배지 뒤 상태 문구 (D-19) */

/* ===== 6. 마트 본문 2열 (왼쪽 진행 단계 300px, 오른쪽 숫자 카드 → 검사 사다리) ===== */
.mgrid{display:grid;grid-template-columns:var(--stages-w) minmax(0,1fr);gap:var(--sp-4);align-items:start}
.mleft{display:grid;grid-template-columns:minmax(0,1fr);gap:var(--sp-4);align-content:start;min-width:0}
/* 왼쪽 칼럼(진행 단계 + 다음 행동) sticky는 화면이 그 칼럼보다 높을 때만 (D-44). 높이 조건 =
   --top-h + 위 여백 --sp-4 + 왼쪽 칼럼 높이 + 아래 여백 --sp-4, 10px 단위 올림. 왼쪽 칼럼 높이는 T10 실측(1280·960px 같음):
   실데이터·시험용 기록 중 가장 긴 것 603px(진행 단계 440 = L6 행 둘째 줄이 두 줄로 감김 + 간격 16 + 다음 행동 146, 링크 3개).
   960px 이상(T3 테마 토글 뒤 --top-h 한 값 112) 112 + 16 + 603 + 16 = 747 → 750px. 높이 768px 노트북은 1280·960px 모두 sticky */
/* 왼쪽 칼럼이 화면보다 길면(진행 단계 행 글자가 길어지는 경우) 화면 높이를 상한으로 두고 칼럼 안에서 스크롤한다. 실데이터(603px)는
   조건 높이에서 상한(화면 - --top-h - 2 × --sp-4) 안이라 스크롤바가 생기지 않는다 */
@media (min-width:960px) and (min-height:750px){.mleft{position:sticky;top:calc(var(--top-h) + var(--sp-4));
  max-height:calc(100vh - var(--top-h) - 2 * var(--sp-4));overflow-y:auto}}
.nexts{padding:var(--sp-4) var(--sp-5)}
.nexts h2{font-size:var(--fs-sub);line-height:var(--lh-sub);font-weight:var(--fw-semibold);margin-bottom:var(--sp-2)}
.nx-l{list-style:none;margin:0;padding:0;display:grid;gap:var(--sp-2);font-size:var(--fs-body);line-height:var(--lh-body)}  /* 한 줄에 하나 */
.mcol{display:grid;grid-template-columns:minmax(0,1fr);gap:var(--sp-4);min-width:0}

/* ===== 7. 숫자 카드: 6장, 3열 × 2행 ===== */
.kpis{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:var(--sp-3)}
.kpi{background:var(--surface);border:1px solid var(--line);border-radius:var(--r-lg);box-shadow:var(--shadow-sm);
  padding:14px 18px;display:flex;flex-direction:column;gap:var(--sp-1);min-width:0;overflow-wrap:anywhere}
.kpi .label,.kpi .value,.kpi .kdet,.kpi .foot{display:block}  /* 안쪽은 span(button 안에 블록 요소 금지, D-27) */
button.kpi{position:relative;width:100%;margin:0;text-align:left;font:inherit;color:inherit;cursor:pointer;padding-right:36px}
button.kpi:hover{box-shadow:var(--shadow-md)}  /* 덩어리 = 카드: hover 때 그림자(카드에만, D-24) */
button.kpi>.chev{position:absolute;top:14px;right:14px}  /* 오른쪽 위 › */
.kpi .label{font-size:var(--fs-sub);line-height:var(--lh-sub);font-weight:var(--fw-regular);color:var(--fg-2)}
.kpi .value{font-size:var(--fs-num);font-weight:var(--fw-bold);line-height:var(--lh-num);letter-spacing:-.01em}
.kpi .value.is-blocked{color:var(--fail-ink)}  /* 반려 수: 그 보기에 지금 막힌 것이 있을 때만 빨강, 아니면 본문색 (D-34) */
.kpi .value small{font-size:var(--fs-body);font-weight:var(--fw-regular);color:var(--muted);margin-left:2px;letter-spacing:0}
.kpi .value .bd{margin-left:var(--sp-2);vertical-align:.3em;letter-spacing:0}  /* 차단 카드 "전체 마트" 분류 태그 (D-45) */
.kpi .kdet,.kpi .foot{font-size:var(--fs-cap);color:var(--muted);line-height:var(--lh-cap);margin-top:2px;overflow-wrap:anywhere}
.kpi-basis{grid-column:1/-1;font-size:var(--fs-cap);line-height:var(--lh-cap);color:var(--muted)}  /* "결재 2까지 기준" 한 번 (D-20) */
.kpi .bd{white-space:normal;max-width:100%}
.meter{display:grid;grid-template-columns:repeat(5,1fr);gap:var(--sp-1);margin-top:2px;max-width:180px}
.meter i{height:5px;border-radius:3px;background:var(--line)}
.meter i.on{background:var(--fg-2)}
.split{display:flex;gap:2px;height:5px;margin-top:2px;border-radius:3px;overflow:hidden}
.split i{display:block;height:100%}
.split i:nth-child(1){background:var(--fg-2)}.split i:nth-child(2){background:var(--muted)}.split i:nth-child(3){background:var(--line-strong)}

/* ===== 8. 진행 단계: 세로 타임라인, 근거가 있는 행은 행 전체가 버튼 ===== */
.stages{padding:var(--sp-4) var(--sp-3)}
.st-h{display:flex;align-items:baseline;justify-content:space-between;gap:var(--sp-2);padding:0 var(--sp-2) var(--sp-2)}
.st-h h2{font-size:var(--fs-h);line-height:var(--lh-h);font-weight:var(--fw-semibold)}
.st-n{font-size:var(--fs-body);line-height:var(--lh-body);color:var(--muted)}
.steps{list-style:none;margin:0;padding:0}
.step{position:relative}
.step::after{content:"";position:absolute;left:calc(var(--sp-2) + 10px);top:calc(50% + 12px);height:calc(100% - 24px);width:2px;
  background:var(--rail);pointer-events:none}  /* 연결선은 상태가 아니므로 --rail 회색 (opacity 없음) */
.step:last-child::after{display:none}
.srow{width:100%;min-height:44px;display:flex;align-items:center;gap:10px;padding:6px var(--sp-2);margin:0;
  text-align:left;background:transparent;border:0;border-radius:var(--r-md)}
.sbtn{cursor:pointer}
.sbtn:hover,.step.is-current .srow{background:var(--surface-2)}
.sbtn[aria-expanded="true"]{box-shadow:inset 0 0 0 2px var(--fg)}
.step .sd-dot{position:relative;z-index:1;width:22px;height:22px;border-radius:50%}  /* 진행 단계 행의 StatusDot 약 22px */
.step .sd-dot .ic{width:1.6em;height:1.6em}
.step.is-current .sd-dot{box-shadow:0 0 0 2px var(--surface),0 0 0 4px var(--fg)}  /* 지금 단계: 행 바탕 + 점 테두리 */
.sname{font-weight:var(--fw-semibold);white-space:nowrap}
.sdate{margin-left:auto;font-size:var(--fs-cap);line-height:var(--lh-cap);color:var(--muted);white-space:nowrap}
.sdetails{display:none}
/* L6 행은 둘째 줄이 감겨도 ›를 다른 행처럼 오른쪽 가운데에 둔다(줄바꿈 흐름 밖, 오른쪽 여백 = 다른 행의 › 자리) */
.srow:has(.sl6){flex-wrap:wrap;position:relative;padding-right:calc(var(--sp-2) + 1.15em + 10px)}
.srow:has(.sl6)>.chev{position:absolute;right:var(--sp-2);top:50%;transform:translateY(-50%)}
.sl6{flex:1 1 100%;padding-left:32px;font-size:var(--fs-cap);line-height:var(--lh-cap);color:var(--muted)}  /* L6 행 둘째 줄 (D-42·D-43) */

/* ===== 9. 검사 사다리: task마다 동그라미 6개 + L6 한 줄 ===== */
.lad{padding:var(--sp-4) var(--sp-3) var(--sp-2)}
.lad-h{display:flex;align-items:baseline;justify-content:space-between;gap:var(--sp-1) var(--sp-4);flex-wrap:wrap;padding:0 var(--sp-2) var(--sp-2)}
.lad-h h2{font-size:var(--fs-h);line-height:var(--lh-h);font-weight:var(--fw-semibold)}
.lad-h .aside{font-size:var(--fs-body);line-height:var(--lh-body);color:var(--muted)}
.lad-sum{display:flex;align-items:center;gap:var(--sp-2) 10px;flex-wrap:wrap;padding:0 var(--sp-2) var(--sp-3);font-size:var(--fs-body);
  line-height:var(--lh-body);color:var(--fg-2)}
.lhead,.lrow{display:grid;grid-template-columns:var(--task-w) minmax(0,1fr);gap:var(--sp-3);align-items:center}
.lhead{padding:0 var(--sp-2) 6px;border-bottom:1px solid var(--line)}
.lcols,.nodes{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));text-align:center}
.rung{display:grid;align-content:end;font-size:var(--fs-body);font-weight:var(--fw-semibold);color:var(--muted);line-height:var(--lh-body);
  padding:0 var(--sp-1);word-break:keep-all}  /* 두 줄: "L5" / "다시 돌려도 같은지" (D-16) */
.lrows{list-style:none;margin:0;padding:0}
.lrow{padding:var(--sp-4) var(--sp-2) var(--sp-3);border-bottom:1px solid var(--line)}
.tbtn{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:2px var(--sp-2);min-width:0;margin:calc(-1 * var(--sp-1)) calc(-1 * var(--sp-2));
  padding:var(--sp-1) var(--sp-2);text-align:left;background:transparent;border:0;border-radius:var(--r-md);cursor:pointer}
.tbtn>.tn,.tbtn>.iters{grid-column:1}
.tbtn>.chev{grid-column:2;grid-row:1 / span 2;align-self:center}
.tbtn:hover{background:var(--surface-2)}
.tbtn[aria-expanded="true"]{box-shadow:inset 0 0 0 2px var(--fg)}
.tn{display:flex;align-items:center;gap:6px;flex-wrap:wrap;min-width:0}
.tn code{font-weight:var(--fw-semibold);overflow-wrap:anywhere}
.iters{font-size:var(--fs-body);line-height:var(--lh-body);color:var(--muted)}
.nodes{position:relative;align-items:center;justify-items:center;min-height:var(--node)}
.rail{position:absolute;left:calc(100% / 12);right:calc(100% / 12);top:calc(50% - 1px);height:2px;background:var(--rail)}
/* 사다리 원의 링 네 가지(D-24·D-26·D-31): 안쪽부터 지난 반려(--rail, 지금 반려면 --fail) → hover(--ring-hover) → 포커스(--focus,
   :focus-visible outline 2px, 2px 띄움) → 선택(서랍이 열린 칸, --fg). 있는 링만 차례로 바깥에 쌓는다(선택 > 포커스 > hover 순으로 바깥).
   --h·--v·--f·--s = 각 링이 있으면 1. 링마다 2px 띄우고(--surface) 2px(지난 반려는 3px 띄움)를 그린다. hover 때 크기는 바꾸지 않는다 */
.nd{position:relative;z-index:1;width:var(--node);height:var(--node);padding:0;border:0;border-radius:50%;display:grid;place-items:center;
  font-size:var(--fs-body);font-weight:var(--fw-bold);line-height:1;cursor:pointer;
  --h:0;--v:0;--f:0;--s:0;--had:var(--rail);
  --e1:calc(var(--h) * 5px);--e2:calc(var(--e1) + var(--v) * 4px);--e3:calc(var(--e2) + var(--f) * 4px);--e4:calc(var(--e3) + var(--s) * 4px);
  box-shadow:0 0 0 calc(var(--h) * 3px) var(--surface),0 0 0 var(--e1) var(--had),
    0 0 0 calc(var(--e1) + var(--v) * 2px) var(--surface),0 0 0 var(--e2) var(--ring-hover),
    0 0 0 var(--e3) transparent,
    0 0 0 calc(var(--e3) + var(--s) * 2px) var(--surface),0 0 0 var(--e4) var(--fg)}
.nd.pass{background:var(--pass-solid);color:var(--on-solid)}
.nd.fail,.nd.halt{background:var(--fail);color:var(--on-solid)}
.nd.none{background:var(--surface);border:1.5px dashed var(--wait)}  /* 미실행 = 대기 모양(점선 테두리 빈 원) */
/* 반려 이력 고리 (D-34): 지금은 통과·멈춤·미실행이면 회색(--rail), 지금 반려인 칸만 빨강 */
.nd.had{--h:1}
.nd.fail.had{--had:var(--fail)}
.nd:hover{--v:1}
.nd:focus-visible{--f:1;outline-offset:calc(var(--e2) + 2px);border-radius:50%}
.nd[aria-expanded="true"]{--s:1}
/* 반려 카드에서 여러 건으로 왔을 때 반려 이력 칸을 1.5초 선택 링으로 강조(깜빡임 3번, 움직임 줄이기면 깜빡임 없이 링만, D-27) */
.nd.flash{--s:1;animation:ring-blink .5s steps(1) 3}
.l6row.flash{box-shadow:inset 0 0 0 2px var(--fg)}
@keyframes ring-blink{50%{--s:0}}
.nodes .rej-n{position:absolute;bottom:calc(100% + 3px);left:50%;transform:translateX(-50%);min-height:0;padding:0 6px;line-height:18px}  /* "반려 N" Badge 자리 */
.l6row{position:relative;display:flex;align-items:center;flex-wrap:wrap;gap:var(--sp-2) 10px;width:calc(100% - 2 * var(--sp-2));
  margin:var(--sp-2);padding:10px var(--sp-3);border:1px solid var(--line);border-radius:var(--r-md);background:transparent;text-align:left;cursor:pointer}
.l6row:hover{background:var(--surface-2)}  /* 덩어리 = 열기 모양: hover 때 옅은 바탕만 (D-24) */
.l6row[aria-expanded="true"]{box-shadow:inset 0 0 0 2px var(--fg)}
.l6row b{font-weight:var(--fw-semibold)}
.l6row .nd-mk{flex:none;width:22px;height:22px;border-radius:50%;display:grid;place-items:center;font-size:var(--fs-cap);font-weight:var(--fw-bold);line-height:1}
.l6row.pass .nd-mk{background:var(--pass-solid);color:var(--on-solid)}
.l6row.fail .nd-mk,.l6row.halt .nd-mk{background:var(--fail);color:var(--on-solid)}
.l6row.none .nd-mk{background:var(--surface);border:1.5px dashed var(--wait)}
.l6row.had .nd-mk{box-shadow:0 0 0 2px var(--surface),0 0 0 4px var(--rail)}
.l6row.fail.had .nd-mk{box-shadow:0 0 0 2px var(--surface),0 0 0 4px var(--fail)}
/* 범례: 구분점 "·" 없이 간격으로 나눈다(아이콘 묶음과 점의 기준선이 달라 점이 낮게 보이던 문제, DESIGN §3) */
.legend{display:flex;flex-wrap:wrap;align-items:center;gap:var(--sp-1) var(--sp-4);padding:var(--sp-2) var(--sp-2) var(--sp-1);
  font-size:var(--fs-cap);line-height:var(--lh-cap);color:var(--muted)}
.lg-i{display:inline-flex;align-items:center;gap:3px;white-space:nowrap}
.lad-hint{display:inline-flex;align-items:center;gap:4px;color:var(--muted)}  /* "원을 누르면 …" + i-info (D-24) */
.lempty{padding:var(--sp-3) var(--sp-2)}
/* 사다리 접기 (D-40): JS가 있을 때만(html.js, head 첫 스크립트가 단다) 첫 시도 통과 행을 접힌 줄 하나로. JS가 없으면 모든 행이
   보이고 접힌 줄·"모두 보기"는 없다(D-15). 구간을 펼치면(.open) 접힌 줄이 숨고 행이 보인다. 모두 보기 = .lad.all */
.lfold,.lad-all{display:none}
html.js .lfold{display:block;border-bottom:1px solid var(--line)}
html.js .lad-all{display:inline-block;margin-left:auto}
html.js .lrow[data-fold-g]{display:none}
html.js .lrow[data-fold-g].unfold,html.js .lad.all .lrow[data-fold-g]{display:grid}
html.js .lfold.open,html.js .lad.all .lfold{display:none}
.lfold-b{display:flex;align-items:center;gap:6px;width:100%;min-height:44px;padding:var(--sp-2);margin:0;text-align:left;
  background:transparent;border:0;border-radius:var(--r-md);color:var(--fg);cursor:pointer}  /* 펼치기 모양 ▸ + 본문색 (D-24) */
.lfold-b:hover{background:var(--surface-2)}
.lfold-b>.ic{width:14px;height:14px}
.lfold-b code{font-weight:var(--fw-semibold)}
.more{font-size:var(--fs-body);line-height:var(--lh-body);font-weight:var(--fw-semibold);color:var(--fg-2);background:var(--surface);
  border:1px solid var(--line-strong);border-radius:var(--r-pill);padding:2px 10px;cursor:pointer}
.more:hover{background:var(--surface-2);color:var(--fg)}
.more>.ic{margin-right:4px}
.more.sm{margin:0 0 0 auto}

/* ===== 10. 상세 서랍: 오른쪽에서 겹쳐 나오고 뒤에 옅은 막. 한 번에 하나 ===== */
.scrim{display:none;position:fixed;inset:0;z-index:40;background:var(--scrim)}
.scrim.on{display:block;animation:fade-in .18s ease-out}
.dpanel{display:none;position:fixed;z-index:50;top:0;right:0;width:min(var(--panel-w),100%);height:100%;flex-direction:column;
  background:var(--surface);color:var(--fg);border-left:1px solid var(--line);box-shadow:var(--shadow-pop)}
.dpanel.on{display:flex;animation:slide-in .18s ease-out}
@keyframes slide-in{from{transform:translateX(100%)}to{transform:none}}
@keyframes fade-in{from{opacity:0}to{opacity:1}}
.dp-bar{display:flex;align-items:center;justify-content:space-between;gap:var(--sp-3);padding:var(--sp-3) var(--sp-5);border-bottom:1px solid var(--line)}
.dp-body{flex:1;overflow-y:auto;padding:var(--sp-4) var(--sp-5) var(--sp-8)}
.detail{display:none}.detail.on{display:block}
.dp-eb{font-size:var(--fs-body);line-height:var(--lh-body);color:var(--muted)}
.dp-t{display:flex;align-items:center;flex-wrap:wrap;gap:var(--sp-2);margin:2px 0 var(--sp-2);font-size:var(--fs-h);font-weight:var(--fw-semibold);
  line-height:var(--lh-h)}
/* 미니 사다리 (D-26): 칸 서랍 제목 아래 그 task의 L0~L5(서랍이 열릴 때 JS가 만든다). 원 20px, 사다리 원과 같은 색·아이콘·반려 이력 고리.
   현재 칸 = 선택 링(--fg 2px). 원과 글자 사이 10px = 가장 두꺼운 링(반려 이력 4px + 선택 4px) + 2px라 링이 글자를 덮지 않는다.
   JS가 없으면 숨긴다(누를 곳이 없다) */
.dp-mini{display:none}
html.js .dp-mini{display:flex;gap:var(--sp-2);margin:0 0 var(--sp-3)}
.nd.mn{width:auto;height:auto;display:grid;justify-items:center;gap:10px;padding:8px 6px 4px;background:transparent;border-radius:var(--r-sm);
  color:var(--muted);font-weight:var(--fw-regular)}  /* 사다리 원 모양(.nd: hover 링)을 버튼 상자에, 칸 모양은 안의 .mn-o */
.nd.mn:focus-visible{border-radius:var(--r-sm)}
.mn-o{width:20px;height:20px;border-radius:50%;display:grid;place-items:center;line-height:1;
  --h:0;--s:0;--had:var(--rail);--e1:calc(var(--h) * 4px);
  box-shadow:0 0 0 calc(var(--h) * 2px) var(--surface),0 0 0 var(--e1) var(--had),
    0 0 0 calc(var(--e1) + var(--s) * 2px) var(--surface),0 0 0 calc(var(--e1) + var(--s) * 4px) var(--fg)}
.mn-o .ic{width:12px;height:12px}
.mn-o.pass{background:var(--pass-solid);color:var(--on-solid)}
.mn-o.fail,.mn-o.halt{background:var(--fail);color:var(--on-solid)}
.mn-o.none{background:var(--surface);border:1.5px dashed var(--wait)}
.mn-o.rj{--h:1}
.mn-o.fail.rj{--had:var(--fail)}
.mn[aria-current="true"] .mn-o{--s:1}
.mn[aria-current="true"] .mn-k{color:var(--fg);font-weight:var(--fw-semibold)}
.mn-k{font-size:var(--fs-body);line-height:var(--lh-body)}
.rk{font-size:var(--fs-cap);line-height:var(--lh-cap);font-weight:var(--fw-semibold);color:var(--muted);border:1px solid var(--line);border-radius:4px;padding:0 6px}
.lead{color:var(--fg-2)}
.lead+.note{margin-top:2px}
.dp-sec{margin-top:18px}
.dp-go{margin-top:var(--sp-4)}  /* 차단 서랍의 "전체 보기에서 보기" */
.dp-sec h4{margin:0 0 6px;font-size:var(--fs-sub);line-height:var(--lh-sub);font-weight:var(--fw-semibold);color:var(--fg-2)}
.dp-src p{overflow-wrap:anywhere}
.dp-body .dp-sec>.kv,.sdetails .kv{display:block;margin-top:var(--sp-2)}
.dp-body .dp-sec>.kv dt,.sdetails .kv dt{float:left;clear:left;width:6.5em;padding:6px 0;color:var(--muted);font-size:var(--fs-body);
  line-height:var(--lh-body)}
.dp-body .dp-sec>.kv dd,.sdetails .kv dd{margin:0;padding:6px 0 6px 6.5em;border-bottom:1px solid var(--line);font-size:var(--fs-body);
  line-height:var(--lh-body);overflow-wrap:anywhere}
.terms{margin:0}  /* 용어 서랍 (D-23): 제목 = 화면 단어, 본문 1~2문장 */
.terms dt{margin-top:var(--sp-3);font-weight:var(--fw-semibold)}
.terms dd{margin:2px 0 0;color:var(--fg-2)}
.tries,.cks,.later,.steps-list{list-style:none;margin:0;padding:0;display:grid;gap:var(--sp-1)}
.tries li{display:flex;align-items:center;flex-wrap:wrap;gap:var(--sp-1) 10px;padding:6px 10px;border-radius:var(--r-sm);font-size:var(--fs-body);
  line-height:var(--lh-body)}
.tries li.fail{background:var(--fail-tint)}
.tries .tr-t{margin-left:auto}
.steps-list li{display:flex;align-items:center;gap:var(--sp-2);flex-wrap:wrap}
.why{margin-top:var(--sp-3);padding:10px var(--sp-3);border-left:4px solid var(--fail);background:var(--fail-tint);border-radius:0 var(--r-md) var(--r-md) 0}
/* 지난 반려·멈춤 (D-34): 빨강은 지금 막힌 것만. 지난 것은 회색 띠(--rail)·옅은 회색 바탕·보조 글자색 */
.why.past{border-left-color:var(--rail);background:var(--surface-2);color:var(--fg-2)}
.tries li.fail.past{background:var(--surface-2)}
.res{display:flex;align-items:center;flex-wrap:wrap;gap:var(--sp-2);margin:0}
.pcs{list-style:none;margin:0;padding:0;display:grid;gap:var(--sp-1)}
.pc{display:flex;align-items:flex-start;gap:6px;font-size:var(--fs-body);line-height:var(--lh-body);color:var(--fg-2)}
.pc>.ic{margin-top:.2em}
.pc.pass>.ic{color:var(--pass-ink)}.pc.fail>.ic{color:var(--fail-ink)}.pc.wait>.ic{color:var(--muted)}
.pcs+.note{margin-top:var(--sp-1)}
.why-h{display:flex;align-items:center;gap:var(--sp-2);flex-wrap:wrap}
.why-n{margin:4px 0 0}
.why-m{margin-top:2px;font-size:var(--fs-body);line-height:var(--lh-body);color:var(--fg-2);overflow-wrap:anywhere}
.why-m .later{display:inline;gap:0}.why-m .later li{display:inline}.why-m .later li+li::before{content:" · "}
.why .kv{font-size:var(--fs-body);line-height:var(--lh-body);gap:var(--sp-1) var(--sp-3)}
.why .kv dt{font-size:var(--fs-body)}
.items{margin:0;padding-left:18px;font-size:var(--fs-body);line-height:var(--lh-body);color:var(--fg-2)}
.sqlbox+.sqlbox,.sqlbox+.note,.sqlbox+.cks,.cks+.note{margin-top:var(--sp-2)}
.sqlbox p{font-size:var(--fs-body);line-height:var(--lh-body);overflow-wrap:anywhere}
.sql-now{margin-top:var(--sp-2)}
.ck{padding:var(--sp-2) var(--sp-3);border:1px solid var(--line);border-radius:var(--r-md);background:var(--surface-2)}
.ck.hit{box-shadow:0 0 0 2px var(--fg)}  /* C-01로 옮겨 온 검사 줄 = 선택 링(--fg). 포커스 링은 :focus-visible 한 가지 */
.ck-h{display:flex;align-items:flex-start;gap:var(--sp-2);flex-wrap:wrap;font-size:var(--fs-body);line-height:var(--lh-body)}
.ck-rule{flex:1;min-width:12em}
.ck-r{display:inline-flex;align-items:center;gap:6px;flex-wrap:wrap}
.ck-m{margin-top:2px;overflow-wrap:anywhere}
details.sql{margin-top:6px}
details.sql>summary{font-size:var(--fs-body);line-height:var(--lh-body);font-weight:var(--fw-semibold)}
details.sql pre{margin:6px 0 0;padding:10px;max-height:360px;overflow:auto;background:var(--surface-2);border:1px solid var(--line);
  border-radius:var(--r-sm);font-size:var(--fs-body);line-height:var(--lh-body);white-space:pre-wrap;overflow-wrap:anywhere}

/* ===== 11. 지금 막힌 반려 카드 (D-42): 지금 막고 있는 반려가 있을 때만, 왼쪽 4px --fail 띠. 한 건 = 열기 모양 한 줄 ===== */
.now-rej{padding:var(--sp-3) var(--sp-4);border-left:4px solid var(--fail)}
.now-rej h3{display:flex;align-items:center;gap:var(--sp-2);font-size:var(--fs-sub);line-height:var(--lh-sub);font-weight:var(--fw-semibold)}
.nr-l{list-style:none;margin:var(--sp-2) 0 0;padding:0;display:grid;gap:var(--sp-1)}
.nr-go{display:flex;align-items:center;flex-wrap:wrap;gap:var(--sp-1) var(--sp-3);min-height:44px;padding:6px var(--sp-2);
  border-radius:var(--r-md);text-decoration:none;color:var(--fg)}
a.nr-go:hover{background:var(--surface-2)}
.nr-go>.chev{margin-left:auto}
.nr-w{font-weight:var(--fw-semibold)}
.nr-y{color:var(--fg-2)}
.nr-more{margin-top:var(--sp-1)}
.kv{display:grid;grid-template-columns:max-content 1fr;gap:var(--sp-2) var(--sp-5);margin:0}
.kv dt{color:var(--muted);font-size:var(--fs-body);line-height:var(--lh-body);padding-top:2px}
.kv dd{margin:0}

/* ===== 12. 규칙 ===== */
.rules{display:grid;grid-template-columns:1fr 1fr;gap:var(--sp-4)}
.rule-box{padding:var(--sp-5) var(--sp-6)}
.rule-box .hd{display:flex;align-items:baseline;gap:var(--sp-3);margin-bottom:var(--sp-2)}
.rule-box .hd b{font-size:var(--fs-sub);line-height:var(--lh-sub);font-weight:var(--fw-semibold)}
.rule-box .cnt{font-size:var(--fs-num);line-height:var(--lh-num);font-weight:var(--fw-bold)}
.rule-box p{font-size:var(--fs-body);line-height:var(--lh-body);color:var(--muted)}
.rule-box .empty-state{margin-top:var(--sp-3);padding:var(--sp-4);border-radius:var(--r-md);background:var(--surface-2);text-align:center;color:var(--muted)}

/* ===== 13. 접힘 영역·표 ===== */
.fold{padding:0}
.fold>details>summary{gap:var(--sp-2);padding:var(--sp-5) var(--sp-6);
  font-size:var(--fs-h);line-height:var(--lh-h);font-weight:var(--fw-semibold)}  /* 펼치기 모양(summary.tw, ▸ 회전, D-24) */
.fold>details>summary .aside{margin-left:auto;font-size:var(--fs-body);line-height:var(--lh-body);font-weight:var(--fw-regular);color:var(--muted)}
.fold-body{padding:0 var(--sp-6) var(--sp-6);display:grid;gap:var(--sp-6)}
.fold-body h3{font-size:var(--fs-sub);line-height:var(--lh-sub);font-weight:var(--fw-semibold);margin-bottom:var(--sp-3)}
.cols{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:var(--sp-6)}
/* 빈 상태 (D-41): 0인 지표는 펼치기 모양 한 줄, 안은 이름 목록. 규칙 0건은 한 줄 */
.zeros>summary{font-size:var(--fs-body);line-height:var(--lh-body)}
.zero-l{margin:var(--sp-2) 0 0;padding-left:var(--sp-6);font-size:var(--fs-body);line-height:var(--lh-body);color:var(--fg-2)}
.rules-empty{font-size:var(--fs-body);line-height:var(--lh-body);color:var(--fg-2)}
.scroll{overflow-x:auto;max-width:100%}
table.t{width:100%;border-collapse:collapse;font-size:var(--fs-body);line-height:var(--lh-body)}
.t th,.t td{padding:10px var(--sp-3);border-bottom:1px solid var(--line);text-align:left}
.t thead th{font-size:var(--fs-body);font-weight:var(--fw-regular);color:var(--muted);background:var(--surface-2);border-bottom-color:var(--line-strong)}
.t td.r,.t th.r{text-align:right}
.t tr.sum td{font-weight:var(--fw-semibold);border-bottom:0;border-top:1px solid var(--line-strong)}
.note{font-size:var(--fs-body);line-height:var(--lh-body);color:var(--muted)}

/* ===== 14. 전체 보기 ===== */
[hidden]{display:none!important}
.view{display:grid;grid-template-columns:minmax(0,1fr);gap:var(--sp-4)}.view>*{min-width:0}
.view>*+*:not(.mgrid){margin-top:var(--sp-4)}  /* 구역 사이 32px, 머리 → 2열(.mgrid)만 16px (음수 margin 없이, D-52) */
/* 마트별 한 줄 카드 (D-46): 주요 링크가 없으면 카드 전체가 열기 모양 링크(오른쪽 ›, hover 옅은 바탕) */
.mlines{list-style:none;margin:0;padding:0;display:grid;gap:var(--sp-2)}
.ml-in{display:flex;align-items:center;flex-wrap:wrap;gap:var(--sp-1) var(--sp-3);min-height:52px;padding:var(--sp-2) var(--sp-4);
  border-radius:var(--r-lg);color:var(--fg);text-decoration:none}
a.ml-in:hover{background:var(--surface-2)}
a.ml-in>.chev{margin-left:auto}
.ml-n{font-weight:var(--fw-semibold)}
.ml-s{color:var(--fg-2);overflow-wrap:anywhere}
.groups{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:var(--sp-4);margin-top:var(--sp-4)}
.group{padding:var(--sp-4) var(--sp-5)}.group h3{font-size:var(--fs-sub);line-height:var(--lh-sub);margin-bottom:var(--sp-2)}
.group ul{list-style:none;margin:0;padding:0;display:grid;gap:var(--sp-2)}

/* ===== 15. 반응형·인쇄·접근성 ===== */
@media (max-width:1180px){.cols{grid-template-columns:1fr 1fr}}
/* 960px 미만 (D-47, 최소 대응): 한 열 + sticky 끔(위 sticky 조건이 960px 이상이라 걸리지 않는다). 순서 상태 → 다음 행동 → 진행 단계
   → 숫자 카드(2열) → 사다리 → 세부. DOM은 진행 단계 → 다음 행동(Tab 순서 D-31)이고 여기서만 CSS order로 다음 행동을 올린다 */
@media (max-width:959px){
  .mgrid{grid-template-columns:minmax(0,1fr)}
  .nexts{order:-1}
  .kpis{grid-template-columns:repeat(2,minmax(0,1fr))}
}
@media (max-width:900px){
  :root{--top-h:172px}  /* 탭이 셋째 줄로, 갱신 표시·테마 토글이 감겨 막대가 높다(T3 실측: 899·900px 약 141px, 641~760px 약 169px) */
  .top-in{flex-wrap:wrap;gap:var(--sp-2) var(--sp-4)}
  .tabs{order:3;flex:1 1 100%;overflow-x:auto;padding-bottom:2px}
  main{padding:var(--sp-5) var(--sp-4) var(--sp-10)}
  .wrap{gap:var(--sp-6)}.view{gap:var(--sp-2)}
  .rules,.cols{grid-template-columns:1fr}
}
@media (max-width:640px){
  .gen>:not(.terms-btn):not(.theme){display:none}  /* 갱신 표시 묶음은 숨기고 [용어]·테마 토글만 남긴다 */
  .lhead{display:none}
  .lrow{grid-template-columns:minmax(0,1fr);gap:var(--sp-5)}
  .kpi{padding:var(--sp-3)}
  .rule-box{padding:var(--sp-4)}
  .fold>details>summary{padding-left:var(--sp-4);padding-right:var(--sp-4)}
  .fold-body{padding:0 var(--sp-4) var(--sp-4)}
}
@media print{.top,.mleft{position:static}.card,.head,.kpi{break-inside:avoid;box-shadow:none}
  .dpanel,.scrim,.more,.dp-x,.chev{display:none!important}.view>.mgrid{margin-top:var(--sp-4)}.sbtn{border:0;box-shadow:none}
  .vh{position:static;width:auto;height:auto;margin:0;clip-path:none;white-space:normal;font-size:var(--fs-body)}}
@media (prefers-reduced-motion:reduce){*{transition:none!important;animation:none!important}}
@media (forced-colors:active){.nd,.nd-mk,.bd,.kpi,.tab,.dpanel,.ck,.why{border:1px solid CanvasText}
  .nd.none,.l6row.none .nd-mk{border-style:dashed}
  .step::after,.rail{background:CanvasText}
  [data-on]{fill:Canvas!important;stroke:Canvas!important}}  /* 아이콘은 currentColor라 시스템 글자색으로 보인다. '!'만 바탕색 */
"""

# head의 첫 스크립트: JS가 켜졌다는 표시만(<html class="js">, T3와 같은 이름). 사다리 접기 CSS가 이 아래에서만 걸려 첫 화면이
# 깜빡이지 않고, JS가 없으면 모든 행이 보인다(D-15·D-40)
JS_FLAG = "document.documentElement.classList.add('js')"

# 같은 head 스크립트(style보다 앞, D-53)의 테마 고르기 (D-14): ① 주소 ?theme=dark|light ② 저장값 localStorage
# 'dashboard-theme'(dark|light) ③ 없으면 data-theme을 달지 않는다(CSS의 OS 미디어 쿼리가 고른다). 칠하기 전에 달려 첫 화면이
# 깜빡이지 않는다. ?theme=는 저장값을 덮어쓰지 않는다. 저장소가 막혀도 화면은 정상(try)
THEME_KEY = "dashboard-theme"
THEME_HEAD = ("(function(){var t=null,s=null;try{t=new URLSearchParams(location.search).get('theme')}catch(x){}"
              f"if(t!=='dark'&&t!=='light'){{try{{s=localStorage.getItem('{THEME_KEY}')}}catch(x){{}}t=s==='dark'||s==='light'?s:null}}"
              "if(t){document.documentElement.setAttribute('data-theme',t)}})()")
HEAD_JS = f"{JS_FLAG};{THEME_HEAD}"

# JS가 없으면 상세 서랍을 사다리 아래에 펼쳐 모든 칸의 상세가 차례로 보인다(진행 단계 근거는 타임라인 아래)
NOSCRIPT_CSS = ("<style>.dpanel{display:block;position:static;width:auto;height:auto;margin:var(--sp-4) var(--sp-2) var(--sp-2);"
                "box-shadow:none;border:1px solid var(--line);border-radius:var(--r-lg)}.detail{display:block;padding-bottom:var(--sp-4)}"
                ".dp-x,.more:not(.skip),.scrim{display:none}.sdetails{display:block;margin-top:var(--sp-3);padding:0 var(--sp-2);"
                "border-top:1px solid var(--line)}.chev{display:none}</style>")

# 구역 순서: 상태 보존(해시·보기) → 서랍 → 상대 시각 → 갱신(마지막에 시작). 상대 시각·갱신 구역은 try로 감싸고 실패하면
# console.error('[dashboard] <구역>')만 남긴다(다른 구역은 그대로 동작, D-53).
# 상태 보존: 펼친 칸·스크롤(세로·넓은 표 가로)·마트 보기·열린 서랍·키보드 포커스·일시정지를 sessionStorage 키 하나
# (dashboard-state)의 키-값으로 이어 간다(저장이 막혀도 화면은 정상). 마트 보기는 ① #mart= ② 저장된 보기 ③ data-first-mart
# (저장된 보기가 없을 때만) ④ 전체 순서로 고른다(D-04).
# 상세 서랍은 한 번에 하나만 열고 Esc·닫기·막(scrim) 클릭으로 닫는다(닫으면 누른 버튼으로 초점이 돌아가고, 열면 초점은 닫기 버튼).
# 갱신: CHECK마다 version.js를 script 태그로 읽고, hash가 이 페이지와 다를 때만 다시 불러온다. 미루는 조건은 refresh 구역 busy()
JS = """
(function(){
/* ===== 상태 보존: 키 하나(dashboard-state)에 모은다. 새 항목은 키 하나만 더한다 ===== */
var SK='dashboard-state',S=null,st={};
try{S=window.sessionStorage;st=JSON.parse(S.getItem(SK)||'{}')}catch(x){S=null;st={}}
if(!st||typeof st!=='object'||Array.isArray(st)){st={}}
function get(k){return Object.prototype.hasOwnProperty.call(st,k)?st[k]:null}
function keep(){try{if(S){S.setItem(SK,JSON.stringify(st))}}catch(x){}}
function put(k,v){st[k]=v;keep()}
function drop(k){if(k in st){delete st[k];keep()}}
var open=Array.isArray(get('open'))?get('open'):[],xs=get('x');if(!xs||typeof xs!=='object'){xs={}}
function all(){return document.querySelectorAll('details[data-cell]')}
function save(){var ids=[];all().forEach(function(x){if(x.open){ids.push(x.getAttribute('data-cell'))}});put('open',ids)}
all().forEach(function(d){if(open.indexOf(d.getAttribute('data-cell'))>=0){d.open=true}d.addEventListener('toggle',save)});
/* 주소 해시: #mart=<이름>&cell=<칸> (마트 1개면 #cell=<칸>) */
function hp(){var o={};location.hash.replace(/^#/,'').split('&').forEach(function(p){var i=p.indexOf('=');if(i>0){
try{o[p.slice(0,i)]=decodeURIComponent(p.slice(i+1))}catch(x){}}});return o}
function hs(o){var a=[];if(o.mart){a.push('mart='+encodeURIComponent(o.mart))}if(o.cell){a.push('cell='+encodeURIComponent(o.cell))}
return a.length?'#'+a.join('&'):location.pathname+location.search}
function setHash(o){try{history.replaceState(null,'',hs(o))}catch(x){}}
var views=document.querySelectorAll('[data-view]');
/* 보기 id(mart=<이름>)는 JS가 없을 때 #mart= 앵커가 그 블록으로 가게 하는 것이다. JS가 보기를 고르므로 떼어 낸다: 남겨 두면
   브라우저가 불러올 때 주소 해시의 그 id로 스크롤하며 Tab 시작점을 보기 안으로 옮겨 첫 Tab이 "본문으로 건너뛰기"가 아니게 된다 (D-31) */
views.forEach(function(v){if(/^mart=/.test(v.id)){v.removeAttribute('id')}});
function known(n){var ok=false;views.forEach(function(v){if(v.getAttribute('data-view')===n){ok=true}});return ok}
/* 처음 보기: ① 주소 #mart= ② 저장된 보기 ③ 사람 할 일이 있는 마트(저장된 보기가 없을 때만) ④ 전체 (D-04) */
var want=null;
if(views.length>1&&!hp().mart){var sv=get('view'),fm=document.documentElement.getAttribute('data-first-mart');
if(sv===null&&fm&&known(fm)){sv=fm}
if(sv&&sv!=='all'&&known(sv)){want=sv;var h0=hp();h0.mart=sv;setHash(h0)}}
var shown=null;
/* 마트 탭: 고른 보기만 보이고 탭에 on·aria-current */
function show(){if(views.length<2){return}
var n=hp().mart||want||'all';
if(!known(n)){n='all'}
put('view',n);shown=n;
views.forEach(function(v){v.hidden=v.getAttribute('data-view')!==n;if(!v.hidden&&v.getAttribute('data-title')){document.title=v.getAttribute('data-title')}});
document.querySelectorAll('[data-view-link]').forEach(function(a){var on=a.getAttribute('data-view-link')===n;
a.classList.toggle('on',on);if(on){a.setAttribute('aria-current','page')}else{a.removeAttribute('aria-current')}})}
show();
/* ===== 사다리 접기 (D-40): 펼친 구간(상태 키 fold: 구간 id 목록)과 모두 보기(키 foldall: 보기 → true)를 이어 간다 ===== */
var fo=Array.isArray(get('fold'))?get('fold'):[],fa=get('foldall');if(!fa||typeof fa!=='object'||Array.isArray(fa)){fa={}}
function ladView(l){var v=l.closest('[data-view]');return v?v.getAttribute('data-view'):''}
function unfold(g){var li=document.querySelector('[data-fold-line="'+g+'"]');if(!li){return null}li.classList.add('open');
var rows=[].slice.call(document.querySelectorAll('.lrow[data-fold-g="'+g+'"]'));rows.forEach(function(r){r.classList.add('unfold')});
if(fo.indexOf(g)<0){fo.push(g);put('fold',fo)}return rows[0]||null}
function setAll(l,on){l.classList.toggle('all',on);var b=l.querySelector('[data-fold-all]');if(b){b.setAttribute('aria-pressed',on?'true':'false')}
if(!on){l.querySelectorAll('.lfold.open').forEach(function(x){x.classList.remove('open');var g=x.getAttribute('data-fold-line');
fo=fo.filter(function(y){return y!==g})});l.querySelectorAll('.lrow.unfold').forEach(function(r){r.classList.remove('unfold')});put('fold',fo)}
fa[ladView(l)]=on;put('foldall',fa);
var s0=l.querySelector('[tabindex="0"]');if(s0&&typeof vis==='function'&&!vis(s0)){var v0=cellsOf(l).filter(vis)[0];if(v0){stop(l,v0)}}}
/* 링크·주소 해시가 접힌 행 안을 가리키면 그 구간을 먼저 펼친다 */
function reveal(el){var r=el&&el.closest&&el.closest('.lrow[data-fold-g]');if(r){unfold(r.getAttribute('data-fold-g'))}}
fo.slice().forEach(function(g){unfold(g)});
document.querySelectorAll('.lad').forEach(function(l){if(fa[ladView(l)]===true){setAll(l,true)}});
/* 진행 단계 근거를 같은 보기의 상세 서랍으로 옮긴다(서랍 1개를 사다리와 함께 쓴다). JS가 없으면 타임라인 아래에 남는다 */
document.querySelectorAll('[data-sdetails]').forEach(function(s){var v=s.closest('[data-view]');
var b=v&&v.querySelector('[data-panel] .dp-body');if(!b){return}while(s.firstChild){b.appendChild(s.firstChild)}});
/* 상세 서랍: 동그라미·task 이름·L6 한 줄·진행 단계·[용어]의 [data-open]을 누르면 열고, Esc·닫기·막 클릭으로 닫는다. 한 번에 하나 */
var opener=null,scrim=document.querySelector('[data-scrim]');
function panels(){return document.querySelectorAll('[data-panel].on')}
function find(key){var ds=document.querySelectorAll('.detail[data-detail]');
for(var i=0;i<ds.length;i++){if(ds[i].getAttribute('data-detail')===key){var v=ds[i].closest('[data-view]');
if(!v||!v.hidden){return ds[i]}}}return null}
function mark(key){document.querySelectorAll('[data-open][aria-expanded]').forEach(function(b){
b.setAttribute('aria-expanded',b.getAttribute('data-open')===key?'true':'false')})}
function closeDetail(back){panels().forEach(function(p){p.classList.remove('on')});document.body.classList.remove('dp-open');
if(scrim){scrim.classList.remove('on')}
document.querySelectorAll('.detail.on').forEach(function(d){d.classList.remove('on')});mark(null);
var o=hp();if(o.cell){delete o.cell;setHash(o)}drop('detail');
if(back&&opener&&document.contains(opener)){opener.focus()}opener=null}
function openDetail(key,focus){var d=find(key);if(!d){return false}
document.querySelectorAll('.lrow [data-open]').forEach(function(b){if(b.getAttribute('data-open')===key){reveal(b)}});
var p=d.closest('[data-panel]');panels().forEach(function(q){if(q!==p){q.classList.remove('on')}});
document.querySelectorAll('.detail.on').forEach(function(x){if(x!==d){x.classList.remove('on')}});
buildMini(d,key);d.classList.add('on');p.classList.add('on');document.body.classList.add('dp-open');if(scrim){scrim.classList.add('on')}
p.setAttribute('aria-label',d.getAttribute('aria-label'));
p.querySelector('.dp-body').scrollTop=0;mark(key);
var o=hp();o.cell=key;if(views.length>1&&!o.mart&&shown){o.mart=shown}setHash(o);put('detail',key);
if(focus){var c=p.querySelector('[data-close]');if(c){c.focus()}}return true}
/* 검사 줄(li.ck)로: 선택 링(hit)·SQL 펼침·스크롤·포커스 (C-01, D-28) */
function goCheck(id){var c=document.getElementById(id);if(!c){return}
document.querySelectorAll('.ck.hit').forEach(function(x){x.classList.remove('hit')});c.classList.add('hit');
var s=c.querySelector('details.sql');if(s){s.open=true}c.scrollIntoView({block:'nearest'});c.focus()}
/* 잠깐 강조: 1.5초 뒤 flash를 뗀다(움직임 줄이기면 CSS가 깜빡임 없이 링만) */
function flash(els){els.forEach(function(x){x.classList.add('flash')});setTimeout(function(){els.forEach(function(x){x.classList.remove('flash')})},1500)}
function focusCell(c){try{c.focus({preventScroll:true})}catch(x){c.focus()}}
/* 숫자 카드 (D-27): fold = 아래 접힘 상세를 펴고 그리로(포커스는 summary), ladder = 사다리로 가서 반려 이력 칸 강조 */
function kpi(k){var w=k.getAttribute('data-kpi');
if(w==='fold'){var s=document.getElementById(k.getAttribute('data-fold')),dt=s&&s.querySelector('details');if(!dt){return}
dt.open=true;s.scrollIntoView({block:'start'});var su=dt.querySelector('summary');if(su){focusCell(su)}}
else if(w==='ladder'){var l=document.getElementById(k.getAttribute('data-ladder'));if(!l){return}
l.scrollIntoView({block:'start'});flash([].slice.call(l.querySelectorAll('.nd.had,.l6row.had')))}}
document.addEventListener('click',function(e){var t=e.target;if(!t.closest){return}
if(t.closest('[data-skip]')){e.preventDefault();  /* 본문으로 건너뛰기: 지금 보기의 머리 제목(h1), 없으면 main (D-31) */
var h=null;document.querySelectorAll('.view .head-t,main .head-t').forEach(function(x){if(!h&&x.getClientRects().length){h=x}});
(h||document.getElementById('main')).focus();return}
var fb=t.closest('[data-unfold]');if(fb){var f0=unfold(fb.getAttribute('data-unfold')),c0=f0&&f0.querySelector('.tbtn');  /* 접힌 줄: 펼치고 첫 행 0번 칸으로 (D-40) */
if(c0){focusCell(c0)}return}
var fl=t.closest('[data-fold-all]');if(fl){var l0=fl.closest('.lad');setAll(l0,!l0.classList.contains('all'));return}
var b=t.closest('[data-open]');if(b){e.preventDefault();
var vm=b.getAttribute('data-mart');  /* 보기 밖(규칙 구역)의 R-번호: 그 마트 보기로 옮겨 연다 */
if(vm&&views.length>1&&vm!==shown&&known(vm)){var o0=hp();o0.mart=vm;delete o0.cell;setHash(o0);show();keepX()}
if(!b.closest('[data-panel]')){opener=b}
else if(b.hasAttribute('data-mini')){miniGo(b.getAttribute('data-open'));return}
var ck=b.getAttribute('data-ck');if(openDetail(b.getAttribute('data-open'),!ck)&&ck){goCheck(ck)}return}
var cl=t.closest('[data-close]');if(cl){closeDetail(!cl.hasAttribute('data-go'));return}  /* data-go 링크는 주소(#mart=all)로 옮긴다 */
var g=t.closest('[data-goto]');if(g){goCheck(g.getAttribute('data-goto'));return}
var k=t.closest('[data-kpi]');if(k){kpi(k);return}
if(panels().length&&!t.closest('[data-panel]')){closeDetail(true)}});
document.addEventListener('keydown',function(e){if(e.key==='Escape'&&panels().length){closeDetail(true)}});
/* 미니 사다리 (D-26): 칸을 누르면 서랍 안에서 그 칸으로 바꾼다(주소는 setHash = replaceState라 뒤로 가기 한 번이면 닫힌다).
   사다리 본체의 선택 링(aria-expanded)은 mark()가 옮기고, Esc 뒤 포커스가 돌아갈 곳(opener)도 본체의 그 칸으로 바꾼다.
   ←→는 미니 사다리 안 옆 버튼으로 포커스만 옮긴다(Tab 순서는 버튼 6개 그대로) */
function bodyCell(key){var c=null;document.querySelectorAll('.lrow .nd').forEach(function(x){if(!c&&x.getAttribute('data-open')===key){
var v=x.closest('[data-view]');if(!v||!v.hidden){c=x}}});return c}
/* 서버는 칸 서랍 머리에 자리(data-mini-slot)만 둔다. 처음 열릴 때 그 task 행의 L0~L5 원(.cbtn.nd)에서 모양 클래스(pass·fail·halt·none,
   반려 이력 had → rj)·아이콘(.nd-mk)·상태 글자(.vh)를 읽어 버튼 6개를 만든다. 칸 key = "마트:task:L번호" */
var RUNG_PLAIN=__RUNG_PLAIN__;
function buildMini(d,key){var s=d.querySelector('[data-mini-slot]'),n0=s&&!s.firstChild&&bodyCell(key),r=n0&&n0.closest('.lrow');if(!r){return}
var ks=key.split(':'),now=ks.pop(),task=ks.pop();s.setAttribute('role','group');s.setAttribute('aria-label',task+' 단계');
r.querySelectorAll('.cbtn.nd[data-open]').forEach(function(n){var k=n.getAttribute('data-open').split(':').pop(),st=n.querySelector('.vh'),
mk=n.querySelector('.nd-mk'),b=document.createElement('button'),o=document.createElement('span'),t=document.createElement('span');
b.type='button';b.className='nd mn';b.setAttribute('data-mini','');b.setAttribute('data-open',n.getAttribute('data-open'));
if(k===now){b.setAttribute('aria-current','true')}
b.setAttribute('aria-label',task+' '+k+' '+(RUNG_PLAIN[k]||'')+' '+(st?st.textContent:''));
o.className='mn-o '+(['pass','fail','halt','none'].filter(function(c){return n.classList.contains(c)})[0]||'none')+(n.classList.contains('had')?' rj':'');
o.innerHTML=mk?mk.innerHTML:'';t.className='mn-k';t.setAttribute('aria-hidden','true');t.textContent=k;
b.appendChild(o);b.appendChild(t);s.appendChild(b)})}
function miniGo(key){var n=bodyCell(key);if(n){opener=n}if(!openDetail(key,false)){return}
var d=find(key),m=d&&d.querySelector('[data-mini][aria-current="true"]');if(m){m.focus()}}
document.addEventListener('keydown',function(e){var c=e.target;if(!c.hasAttribute||!c.hasAttribute('data-mini')||(e.key!=='ArrowRight'&&e.key!=='ArrowLeft')){return}
var s=[].slice.call(c.parentNode.querySelectorAll('[data-mini]')),to=s[s.indexOf(c)+(e.key==='ArrowRight'?1:-1)];e.preventDefault();if(to){to.focus()}});
function restore(){var key=hp().cell||get('detail');if(!key||!openDetail(key,false)){if(panels().length){closeDetail(false)}}}
restore();
var wide=[].slice.call(document.querySelectorAll('.scroll'));
function keepX(){wide.forEach(function(w,i){if(xs[i]>0){w.scrollLeft=xs[i]}})}
keepX();
window.addEventListener('hashchange',function(){var before=shown;show();if(shown!==before){keepX();window.scrollTo(0,0)}
var key=hp().cell;if(key){openDetail(key,false)}else if(panels().length){closeDetail(false)}});
/* 세로 스크롤은 위쪽 막대 글자(갱신 표시)를 채운 뒤 맨 끝에서 되살린다(막대 높이가 바뀌어 위치가 밀리지 않게) */
var y0=Number(get('y'));function keepY(){try{if(y0>0){window.scrollTo(0,y0)}}catch(x){}}
try{history.scrollRestoration='manual'}catch(x){}
window.addEventListener('scroll',function(){put('y',window.scrollY)},{passive:true});
window.addEventListener('pagehide',function(){put('y',window.scrollY)});
document.addEventListener('scroll',function(e){var t=e.target,i=wide.indexOf(t);
if(i>=0){xs[i]=t.scrollLeft;put('x',xs)}},{capture:true,passive:true});
/* ===== 사다리 키보드 (D-31): roving tabindex. 사다리마다 Tab 정지점은 하나이고 화살표로 움직인다 =====
   행마다 0번 칸 = task 이름 버튼, 1~6번 = L0~L5 원, L6 한 줄은 마지막 행(칸 1개). ←→ 같은 행, ↑↓ 행 사이(같은 열, 없으면 그 행의
   마지막 칸), Home/End 그 행의 처음·끝. Enter·Space는 버튼이라 서랍. Tab으로 들어올 때의 칸: 마지막으로 포커스했던 칸(보기마다
   상태 키 lad) → 반려 이력이 있거나 지금 실패한 칸(위에서부터 첫 번째) → 첫 칸 */
try{
var CELLS='.lrow .tbtn,.lrow .nd,.l6row,.lfold-b';
function cellsOf(l){return [].slice.call(l.querySelectorAll(CELLS))}
/* 접힌 행 안의 칸은 접혀 있는 동안, 접힌 줄은 펼친 뒤 이동 대상이 아니다 (D-40). 숨은 보기에서도 같게 보도록 화면 크기가 아니라 상태로 본다 */
function vis(x){var l=x.closest('.lad'),a=l&&l.classList.contains('all'),r=x.closest('.lrow[data-fold-g]'),f=x.closest('.lfold');
if(r&&!a&&!r.classList.contains('unfold')){return false}return !(f&&(a||f.classList.contains('open')))}
function gridOf(l){var g=[];l.querySelectorAll('.lrows>li').forEach(function(r){if(!vis(r)){return}
var c=[].slice.call(r.querySelectorAll('.tbtn,.nd,.lfold-b'));if(c.length){g.push(c)}});
var six=l.querySelector('.l6row');if(six){g.push([six])}return g}
function viewOf(l){var v=l.closest('[data-view]');return v?v.getAttribute('data-view'):''}
function stop(l,c){cellsOf(l).forEach(function(x){x.setAttribute('tabindex',x===c?'0':'-1')})}
function lad(){var m=get('lad');return m&&typeof m==='object'&&!Array.isArray(m)?m:{}}
document.querySelectorAll('.lad').forEach(function(l){var cs=cellsOf(l).filter(vis),k=lad()[viewOf(l)],c=null;
if(k){cs.forEach(function(x){if(!c&&x.getAttribute('data-open')===k){c=x}})}
if(!c){c=cs.filter(function(x){return x.matches('.nd.had,.nd.fail,.nd.halt,.l6row.had,.l6row.fail,.l6row.halt')})[0]||cs[0]||null}
if(c){stop(l,c)}});
document.addEventListener('focusin',function(e){var c=e.target;if(!c.matches||!c.matches(CELLS)){return}
var l=c.closest('.lad');stop(l,c);var m=lad();m[viewOf(l)]=c.getAttribute('data-open');put('lad',m)});
document.addEventListener('keydown',function(e){var c=e.target;if(!c.matches||!c.matches(CELLS)||e.altKey||e.ctrlKey||e.metaKey){return}
var g=gridOf(c.closest('.lad')),r=-1,i=-1,k=e.key,to=null;
g.forEach(function(row,ri){var j=row.indexOf(c);if(j>=0){r=ri;i=j}});if(r<0){return}
if(k==='ArrowRight'){to=g[r][i+1]}else if(k==='ArrowLeft'){to=g[r][i-1]}else if(k==='Home'){to=g[r][0]}
else if(k==='End'){to=g[r][g[r].length-1]}
else if(k==='ArrowDown'||k==='ArrowUp'){var n=g[r+(k==='ArrowDown'?1:-1)];if(n){to=n[i]||n[n.length-1]}}
else{return}
e.preventDefault();if(to){to.focus()}});
}catch(x){console.error('[dashboard] ladder-keys',x)}
/* 키보드 포커스 되살리기: 다시 불러오기 전에 :focus-visible이던 요소(data-open 키 또는 id) */
var fk=get('focus');drop('focus');
if(fk&&typeof fk==='object'){var fe=null;
if(fk.id){fe=document.getElementById(fk.id)}
else if(fk.open){document.querySelectorAll('[data-open]').forEach(function(b){if(!fe&&b.getAttribute('data-open')===fk.open&&b.getClientRects().length){fe=b}})}
if(fe){try{fe.focus({preventScroll:true})}catch(x){}}}/* ===== 상대 시각: [data-t]의 원시 시각으로 "· 방금·N분 전·N시간 전·N일 전"을 붙인다(D-43) ===== */
var rel=function(){};
try{
rel=function(){var now=Date.now();document.querySelectorAll('[data-t]').forEach(function(s){var t=Date.parse(s.getAttribute('data-t'));
if(isNaN(t)){return}var r=s.querySelector('.rel');if(!r){r=document.createElement('span');r.className='rel';s.appendChild(r)}
var m=Math.floor((now-t)/60000);
r.textContent=' · '+(m<1?'방금':m<60?m+'분 전':m<1440?Math.floor(m/60)+'시간 전':Math.floor(m/1440)+'일 전')})};
rel();
}catch(x){console.error('[dashboard] relative-time',x)}
/* ===== 테마 토글 (D-14): 밝게·어둡게 = 저장 + data-theme, 자동 = 저장값 지움 + 속성 뗌. 주소에 ?theme=가 있으면 theme만 빼고
   (해시 유지) 누른 값이 이긴다. aria-pressed = 지금 적용된 선택(head 스크립트가 단 data-theme, 없으면 자동) ===== */
try{
var thB=document.querySelectorAll('[data-theme-set]'),de=document.documentElement;
function thShow(){var c=de.getAttribute('data-theme')||'auto';thB.forEach(function(b){b.setAttribute('aria-pressed',String(b.getAttribute('data-theme-set')===c))})}
thB.forEach(function(b){b.addEventListener('click',function(){var v=b.getAttribute('data-theme-set');
try{if(v==='auto'){localStorage.removeItem(__THEME_KEY__)}else{localStorage.setItem(__THEME_KEY__,v)}}catch(x){}
if(v==='auto'){de.removeAttribute('data-theme')}else{de.setAttribute('data-theme',v)}
var q=new URLSearchParams(location.search);if(q.has('theme')){q.delete('theme');q=q.toString();
try{history.replaceState(history.state,'',location.pathname+(q?'?'+q:'')+location.hash)}catch(x){}}
thShow()})});
thShow();
}catch(x){console.error('[dashboard] theme',x)}
/* ===== 갱신 (D-08~D-11): 마지막에 시작한다 ===== */
try{
var R=document.documentElement,HASH=R.getAttribute('data-hash'),SRC=R.getAttribute('data-version-src')||'dashboard.version.js',
CHECK=Number(R.getAttribute('data-check-ms'))||10000,STALE=Number(R.getAttribute('data-stale-ms'))||30000;
var stEl=document.querySelector('[data-refresh-state]'),live=document.querySelector('[data-live]'),
nowB=document.querySelector('[data-refresh-now]'),pauseB=document.querySelector('[data-pause]'),
pauseT=pauseB.querySelector('[data-pause-t]'),pauseI=pauseB.querySelector('.ic'),
gen=document.querySelector('[data-k="header.generated_at"]');
var mode='on',pending=false,last=0,seen=0;
function saw(){R.setAttribute('data-version-seen',String(++seen))}  /* 확인 횟수(시험이 기다리는 표시) */
function two(n){return (n<10?'0':'')+n}
if(gen){var g=new Date(Date.parse(gen.getAttribute('data-v')));
if(!isNaN(g.getTime())&&g.toDateString()===new Date().toDateString()){gen.textContent=two(g.getHours())+':'+two(g.getMinutes())}}
['scroll','keydown','click','pointerdown','wheel'].forEach(function(n){document.addEventListener(n,function(){last=Date.now()},{capture:true,passive:true})});
function paused(){return get('paused')===true}
function kbFocus(){var a=document.activeElement;if(!a||a===document.body||a===R){return false}try{return a.matches(':focus-visible')}catch(x){return false}}
function selected(){try{return String(window.getSelection()||'')!==''}catch(x){return false}}
/* 미루는 조건: 서랍이 열림 · 마지막 입력 뒤 3초 안 · 키보드 포커스가 본문 요소에 · 선택된 글자 · 탭이 숨음 */
function busy(){return panels().length>0||Date.now()-last<3000||kbFocus()||selected()||document.hidden}
function persist(){put('y',window.scrollY);var a=document.activeElement,k=null;
if(kbFocus()){k=a.id?{id:a.id}:a.getAttribute('data-open')?{open:a.getAttribute('data-open')}:null}  /* id 먼저(숫자 카드는 칸·단계와 data-open 키를 함께 쓴다) */
if(k){put('focus',k)}else{drop('focus')}}
function reload(){persist();location.reload()}
function paint(){var off=mode==='off',p=paused();
stEl.textContent=off?'자동 갱신 꺼짐 · --watch로 실행하면 켜집니다 · ':p?'자동 갱신 일시정지 · ':'자동 갱신 중 · ';
pauseB.hidden=off;pauseT.textContent=p?'다시 켜기':'일시정지';pauseI.toggleAttribute('hidden',p);
var t=pending?'새 기록 있음 · ':'';if(live.textContent!==t){live.textContent=t}nowB.hidden=!pending}
function decide(){if(pending&&!paused()&&!busy()){reload();return}paint()}
window.__dashVersion=function(v){if(!v||typeof v!=='object'){return}
var b=Number(v.beat);mode=isFinite(b)&&Date.now()-b<=STALE?'on':'off';
if(typeof v.hash==='string'&&v.hash!==HASH){pending=true}saw();decide()};
function check(){var s=document.createElement('script');
s.onload=function(){s.remove()};s.onerror=function(){mode='off';s.remove();saw();paint()};
s.src=SRC+'?t='+Date.now();document.head.appendChild(s)}
nowB.addEventListener('click',reload);
pauseB.addEventListener('click',function(){if(paused()){drop('paused')}else{put('paused',true)}decide()});
document.addEventListener('visibilitychange',function(){if(!document.hidden){decide()}});
paint();check();
setInterval(function(){rel();check()},CHECK);
}catch(x){console.error('[dashboard] refresh',x)}
keepY();
})();
""".replace("__RUNG_PLAIN__", json.dumps({k: RUNG_PLAIN[k] for k in dd.LADDER_RUNGS}, ensure_ascii=False)).replace(
    "__THEME_KEY__", json.dumps(THEME_KEY))


def render(d, version_hash_="", version_src="dashboard.version.js", check_sec=CHECK_SEC, stale_sec=STALE_SEC):
    """페이지 HTML. <html>의 data 속성: hash(바뀜 감지, version.js와 같은 값)·version.js 이름·확인 주기·꺼짐 기준(ms)·
    첫 화면 후보 마트(D-04 ③, 있을 때만). 주기는 시험에서 줄일 수 있다."""
    items = todo_items(d)
    fm = first_mart(d, items)
    attrs = (f" data-hash='{e(version_hash_)}' data-version-src='{e(version_src)}'"
             f" data-check-ms='{int(check_sec * 1000)}' data-stale-ms='{int(stale_sec * 1000)}'"
             + (f" data-first-mart='{e(fm)}'" if fm else ""))
    marts = list(d["marts"])
    static = tab_title(marts[0], len(items)) if len(marts) == 1 else tab_title("전체", len(items))  # JS가 없을 때 (D-17)
    body = (f"{render_topbar(d, items)}<noscript><p class='nojs'>{e(NO_JS)}</p></noscript>"
            f"<main id='main' tabindex='-1'><p class='purpose'>{e(PURPOSE)}</p><div class='wrap'>{render_body(d, items)}</div></main>{render_terms()}"
            f"<div class='scrim' data-scrim></div>")
    return (f"<!doctype html><html lang='ko'{attrs}><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width, initial-scale=1'>"
            f"<title>{e(static)}</title><script>{HEAD_JS}</script><style>{CSS}</style><noscript>{NOSCRIPT_CSS}</noscript></head><body>"
            f"<a class='skip more' href='#main' data-skip>{e(SKIP)}</a>"  # 첫 Tab 정지점 (D-31)
            f"{icon_defs(body)}{body}<script>{JS}</script></body></html>")


# ---------- 쓰기·감시 ----------

def write_atomic(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def public_data(data):
    """--json으로 내보낼 값. 화면과 같은 규칙으로 단계의 자유 문장(target·note)을 뺀다. collect() 결과는 바꾸지 않는다."""
    out = copy.deepcopy(data)
    for m in out["marts"].values():
        for s in m["stages"]:
            for key in ("target", "targets", "note"):
                s.pop(key, None)
    return out


def version_hash(data):
    """바뀜 감지 해시(D-11): collect() 값에서 생성 시각과 그 시각으로 계산한 L6 경과일만 뺀 것의 sha256 앞 16자.
    같은 기록이면 몇 번을 만들어도 같고, 기록이 바뀌면 달라진다."""
    d = copy.deepcopy(data)
    d["header"].pop("generated_at", None)
    for m in d["marts"].values():
        m["l6_check"].pop("age_days", None)
    text = json.dumps(d, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def version_path(out):
    """HTML 옆 바뀜 감지 파일: out/dashboard.html → out/dashboard.version.js."""
    out = Path(out)
    return out.with_name(out.stem + ".version.js")


def write_version(out, hash_, beat_ms=None):
    """version.js 한 줄. hash와 beat(이 파일을 쓴 시각, epoch ms)만 넣는다(데이터 값·경로·SQL 없음, 결정 71)."""
    beat = int(time.time() * 1000) if beat_ms is None else int(beat_ms)
    body = json.dumps({"hash": hash_, "beat": beat}, separators=(",", ":"))
    write_atomic(version_path(out), f"window.__dashVersion({body})\n")


def build(root=PROJECT, out=OUT, json_out=None, now=None, check_sec=CHECK_SEC, stale_sec=STALE_SEC, extra=()):
    """HTML을 다 쓴 뒤 version.js를 쓴다(둘 다 원자적 쓰기). 페이지가 새 hash를 볼 때는 HTML이 이미 새것이다.
    extra: 기록에 더해 보일 결재 줄(auto_approval.preview_all). 파일에는 쓰지 않는다"""
    data = dd.collect(root, now=now, extra_interventions=extra)
    h = version_hash(data)
    write_atomic(out, render(data, h, version_path(out).name, check_sec, stale_sec))
    if json_out:
        write_atomic(json_out, json.dumps(public_data(data), ensure_ascii=False, indent=2, default=str))
    write_version(out, h)
    return data


def snapshot(root=PROJECT):
    """감시 대상 파일의 (경로, 수정 시각 ns, 크기). 파일이 생기거나 지워져도 달라진다."""
    out = {}
    for sub in WATCH_DIRS:
        folder = Path(root) / sub
        if not folder.is_dir():
            continue
        for f in folder.rglob("*"):
            try:
                if f.is_file():
                    st = f.stat()
                    out[str(f)] = (st.st_mtime_ns, st.st_size)
            except OSError:  # 읽는 사이 지워진 파일
                continue
    return out


def watch(make, snap, interval=WATCH_SEC, sleep=time.sleep, rounds=None, beat=None):
    """처음 한 번 만들고, interval마다 snap()이 달라졌을 때만 다시 만든다(make = HTML 다음 version.js).
    달라지지 않은 주기에는 beat()로 version.js만 다시 써서 beat를 올린다(D-11). rounds는 시험용(None이면 끝없이)."""
    last = snap()
    make()
    builds, n = 1, 0
    while rounds is None or n < rounds:
        sleep(interval)
        n += 1
        now = snap()
        if now != last:
            last = now
            make()
            builds += 1
        elif beat is not None:
            beat()
    return builds


def main(argv=None):
    p = argparse.ArgumentParser(description="대시보드 HTML 생성 (진행표 4-15, 결정 71·72)")
    p.add_argument("--watch", nargs="?", type=float, const=WATCH_SEC, default=None, metavar="초",
                   help=f".dev/·docs/requirements/가 바뀌면 다시 만든다 (기본 {WATCH_SEC:g}초 간격)")
    p.add_argument("--json", action="store_true", help=f"collect() 결과를 {OUT_JSON.relative_to(PROJECT)}로도 쓴다")
    p.add_argument("--out", type=Path, default=OUT)
    p.add_argument("--root", type=Path, default=PROJECT)
    p.add_argument("--no-sync", action="store_true",
                   help="git 머지 기록에서 아직 기록되지 않은 결재 1·2를 화면에 더하는 일(auto_approval.preview_all)을 하지 않는다")
    a = p.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")
    json_out = a.out.with_suffix(".json") if a.json else None
    state = {}

    def approvals():
        """아직 기록되지 않은 결재 1·2(화면에만, 쓰지 않음). 읽지 못하면 기록만으로 그린다."""
        if a.no_sync:
            return ()
        try:
            return auto_approval.preview_all(a.root)
        except (auto_approval.devlog.DevlogError, OSError, ValueError) as e:
            print(f"경고: git 머지 기록을 읽지 못함 ({e})", file=sys.stderr)
            return ()

    def make():
        state["hash"] = version_hash(build(a.root, a.out, json_out, extra=approvals()))
        print(f"{time.strftime('%H:%M:%S')} 생성: {a.out}, {version_path(a.out).name}"
              + (f", {json_out}" if json_out else ""), flush=True)

    if a.watch is None:
        make()
        return 0
    if not 0 < a.watch < STALE_SEC:  # 감시 주기마다 beat를 올린다. 꺼짐 기준보다 길면 켜져 있어도 "꺼짐"으로 보인다
        p.error(f"--watch 간격은 0보다 크고 {STALE_SEC}초보다 짧아야 한다")
    try:
        watch(make, lambda: snapshot(a.root), a.watch, beat=lambda: write_version(a.out, state["hash"]))
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
