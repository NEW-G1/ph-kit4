# 처음 시작 안내 (따라 하기)

이 문서 하나만 위에서부터 차례로 따라 하면 됩니다.

- 명령은 회색 칸을 하나씩 복사해 붙여 넣고 Enter를 누릅니다
- 명령을 고쳐 쓸 필요는 없습니다. 내 값이 필요하면 명령이 화면에서 물어봅니다
- 예외는 하나입니다. 예시 데이터 대신 데이터를 직접 골라 해 보려면, 설정 파일에서 데이터 이름 한 곳을 직접 바꿉니다. 고르는 방법은 [부록 A-1](#a-1-공개-데이터-고르기-bigquery-콘솔), 바꾸는 방법은 [부록 A-3](#a-3-원천-설정-바꾸기-내가-직접)에 있습니다
- 막히면 억지로 풀지 말고, 몇 절에서 무엇을 하다 막혔는지 적은 뒤 키트를 준 담당자에게 물어봅니다

## 이 키트로 하는 일

AI가 데이터 파이프라인(원천 데이터를 읽어 분석용 테이블을 만드는 SQL 묶음)을 기안하고, 코드가 자동으로 검사하고, 사람은 결재만 합니다. 예시 요청 "일별 매출 마트가 필요해"로 처음부터 끝까지 한 번 만들어 보거나, 공개 데이터를 직접 골라 만들어 봅니다(부록 A).

| 말 | 뜻 |
|---|---|
| 원천 | 읽어 오는 원본 데이터. 이 키트의 기본값은 Google 공개 샘플 데이터(가상 쇼핑몰)이고, 부록 A를 따르면 직접 고른 공개 데이터로 바꿀 수 있습니다 |
| 공개 데이터 | Google이 BigQuery에 누구나 읽을 수 있게 올려 둔 데이터셋(`bigquery-public-data` 프로젝트 안). BigQuery 콘솔의 마켓플레이스에서 찾을 수 있습니다 |
| 마트 | 원천을 가공해 만든 분석용 결과 테이블 |
| 요구서 | 만들 마트의 정의와 완료 조건. AI가 인터뷰로 초안을 만들고 내가 답합니다 |
| 결재 | GitHub에서 PR을 머지하는 것. 요구서 PR 머지(결재 1)와 구현 PR 머지(결재 2) 두 번입니다. 기록은 자동으로 남습니다 |
| 루프 | AI가 SQL을 쓰고 자동 검사를 받는 일을 통과할 때까지 반복하는 실행 |
| 자동 검사 L0~L5 | 루프 안에서 코드가 SQL을 6단계로 검사하는 것. 모두 통과하면 끝 |
| ai_dev | AI가 시험 삼아 테이블을 만드는 개발용 데이터셋. 테이블은 7일 뒤 자동 삭제됩니다 |
| ai-builder | AI가 BigQuery를 쓸 때 쓰는 권한이 좁은 계정. 키 파일 없이 내 계정으로 로그인한 뒤 이 계정을 "가장"합니다 |

전체 순서: 0 준비물 받기 > 1 프로그램 설치 > 2 키트 풀기 > 3 GitHub 저장소와 설정 > 4 시험 > [예시 요청 / 데이터 직접 고르기(부록 A)] > 5 AI 인터뷰 > 6 결재 1 > 7 루프 > 8 결과 확인 > 9 결재 2

## 0. 준비물 받기

키트를 준 담당자에게 아래를 받습니다.
- 키트 zip 파일 `ph-kit.zip`
- 시험용 GCP 프로젝트 ID (3절에서 설정 스크립트가 물어볼 때 붙여 넣습니다)
- 내 Google 계정에 권한을 줬다는 확인

시작 시각을 적어 둡니다. 단계마다 끝난 시각도 적어 두면 좋습니다.

## 1. 프로그램 설치 (Windows)

모든 명령은 **PowerShell**에서 실행합니다. 화면 아래 작업 표시줄의 Windows 로고(시작 버튼)를 누르고 키보드로 `powershell`을 입력한 뒤, 목록 맨 위 **Windows PowerShell**을 누르면 파란(또는 검은) 창이 열립니다. 명령은 그 창에 붙여 넣습니다(마우스 오른쪽 클릭이 붙여 넣기입니다).

필요한 프로그램은 4개입니다.

| 프로그램 | 하는 일 |
|---|---|
| Git | 파일 변경 이력을 남기고 GitHub에 올리는 도구 |
| Python | 키트의 검사 스크립트를 돌리는 언어 |
| Google Cloud SDK | 내 PC에서 BigQuery를 쓰게 해 주는 명령어 도구 묶음(`gcloud`, `bq`) |
| Claude Code | 명령창에서 쓰는 AI. 인터뷰와 SQL 작성을 맡습니다 |

1. 이미 있는지 확인합니다. 하나씩 실행해 버전 숫자가 나오면 그 프로그램은 있는 것입니다.

```
git --version
```

```
python --version
```

```
gcloud --version
```

```
claude --version
```

2. "인식되지 않는" 같은 말이 나온 것만 설치합니다.

```
winget install -e --id Git.Git
```

```
winget install -e --id Python.Python.3.12
```

```
winget install -e --id Google.CloudSDK
```

```
irm https://claude.ai/install.ps1 | iex
```

- Claude Code 설치가 안 되면 공식 안내(https://docs.claude.com/claude-code)를 따릅니다
- 설치했다면 **PowerShell 창을 닫고 새로 연 뒤** 1번 확인을 다시 합니다. Python은 3.10 이상이면 됩니다

3. Claude Code에 로그인합니다. 아래를 실행하면 브라우저가 열리니 본인 Claude 계정으로 로그인합니다. 로그인되면 `/exit`를 입력해 닫습니다.

```
claude
```

4. Git을 처음 쓰는 PC라면 이름과 이메일을 한 번 등록합니다. 명령을 실행하면 물어보니 GitHub 아이디와 GitHub 이메일을 입력하고 Enter를 누릅니다. 전에 등록했다면 건너뜁니다.

```
git config --global user.name (Read-Host "GitHub 아이디")
```

```
git config --global user.email (Read-Host "GitHub 이메일")
```

## 2. 키트 풀기

1. 받은 `ph-kit.zip`을 **다운로드** 폴더에 둡니다(메신저로 받은 파일은 보통 여기 저장됩니다).
2. 아래를 실행하면 내 사용자 폴더에 `ph-kit` 폴더가 생깁니다.

```
Expand-Archive -Path "$HOME\Downloads\ph-kit.zip" -DestinationPath $HOME
```

3. 그 폴더로 갑니다.

```
cd $HOME\ph-kit
```

- `Expand-Archive`가 파일을 못 찾는다고 하면, 파일 탐색기(작업 표시줄의 노란 폴더 아이콘)에서 zip을 찾아 다운로드 폴더로 옮기고 이름이 `ph-kit.zip`인지 봅니다
- 이미 `ph-kit` 폴더가 있다고 나오면 이전 시험 폴더입니다. 담당자에게 물어봅니다

## 3. GitHub 저장소와 설정

1. 브라우저로 https://github.com 에 로그인하고 오른쪽 위 **+** > **New repository**를 누릅니다.
2. Repository name은 `ph-kit`, **Private**을 고릅니다. "Add a README file"은 **체크하지 않습니다**. **Create repository**를 누릅니다.
3. PowerShell에서 키트를 git에 올릴 준비를 합니다.

```
git init -b main
```

```
git add .
```

```
git commit -m "키트 첫 커밋"
```

4. 설정 스크립트를 실행합니다. 한 번만 하면 됩니다.

```
python scripts/setup/kit_setup.py
```

   - "프로젝트 ID"를 물으면 담당자에게 받은 값을 붙여 넣고 Enter
   - "GitHub 아이디"를 물으면 입력하고 Enter
   - 브라우저가 열리면 **권한을 받은 본인 Google 계정**을 고르고 허용
   - 이 스크립트가 BigQuery 로그인, ai-builder 가장, Claude Code 설정, GitHub 저장소 연결, 요구서 커밋 때 형식 검사 켜기를 대신 합니다
   - 마지막에 `ai-builder@...`가 보이면 성공입니다. 본인 이메일이나 권한 오류가 나오면 멈추고 담당자에게 알립니다

5. GitHub에 올립니다. 로그인 창이 뜨면 GitHub에 로그인합니다.

```
git push -u origin main
```

GitHub 저장소 페이지를 새로 고쳐 파일이 보이면 됩니다.

**PowerShell 창을 새로 열었을 때는** 아래 한 줄만 실행하면 됩니다. 로그인 설정은 저장돼 있어서 다시 하지 않습니다.

```
cd $HOME\ph-kit
```

## 4. 키트 시험

1. 키트가 쓰는 Python 도구를 설치합니다(1~2분).

```
python -m pip install -r requirements-dev.txt
```

2. 키트 자체 시험을 돌립니다(수 분). 키트가 내 PC에서 제대로 도는지 보는 것입니다.

```
python -m pytest tests/ -q -n auto
```

마지막 줄에 `passed`가 1,200개 넘게 나오고 `failed`가 없으면 됩니다. 이 줄을 적어 둡니다.

`skipped`가 수십 개 나와도 정상입니다. 대시보드 화면 시험은 브라우저(Chromium)가 없으면 건너뜁니다. 화면 시험까지 돌리려면 아래를 한 번 실행한 뒤 시험을 다시 돌립니다(선택).

```
python -m playwright install chromium
```

## 5. AI 인터뷰로 요구서 만들기

여기서 두 갈래 중 하나를 고릅니다.

- **예시 요청으로 해 보기**: 아래 1번부터 그대로 합니다
- **데이터 직접 고르기**: 문서 끝의 부록 A를 마치고 돌아와, 아래 2번 문장만 부록 A-6의 문장으로 바꿔 붙입니다

1. Claude Code를 켭니다.

```
claude
```

2. 아래 문장을 그대로 붙여 넣습니다.

```
docs/kit/example_request.md 의 요청을 받았어. docs/requirements/_template.md 기준으로 나에게 인터뷰해서 요구서와 contract 초안을 만들어 줘. 나는 요청자야. 다 만들면 contract.json을 scripts/ladder/l0_contract.py 로 형식 검사해서 통과시켜 줘.
```

3. AI가 원천을 조회해 근거를 보여 주며 질문합니다. **데이터를 받아 쓸 사람**으로서 답합니다.
   - AI가 기본안을 내면, 괜찮으면 "기본안대로"라고 답하고 아니면 바꿔 답합니다
   - Claude Code가 명령 실행이나 파일 쓰기를 허락해 달라고 물으면 창 아래에 `1. Yes`, `2. Yes, and don't ask again...`, `3. No` 같은 선택지가 나옵니다. 내용을 읽고 키보드 숫자 `1`을 누르면 허락입니다. 이상해 보이면 `3`(거절)을 누르고 적어 둡니다
   - **적재 방식**(매일 전체 복사 snapshot, 날짜별 추가 incremental)을 물으면 기본안대로 답해도 됩니다. incremental로 정했다면 "원천에 데이터가 있는 마지막 날짜가 언제야?"라고 물어 날짜를 적어 둡니다(7절에서 씁니다)
4. `docs/requirements/`에 파일 3개(요구서 .md, contract .json, 인터뷰 기록 .md)가 생기면 Claude Code를 닫습니다.

```
/exit
```

## 6. 결재 1 (요구서 PR 머지)

1. 요구서를 브랜치에 올립니다. 인터뷰가 만든 파일을 모두 올립니다.

```
git checkout -b req
```

```
git add -A
```

```
git commit -m "요구서"
```

```
git push -u origin req
```

2. GitHub 저장소 페이지(`ph-kit`)를 엽니다. 파일 목록 위에 노란 띠와 초록 **Compare & pull request** 버튼이 보이면 누릅니다(안 보이면 위쪽 탭 **Pull requests** > 초록 **New pull request** > 왼쪽 base는 `main`, 오른쪽 compare는 `req`로 고름). 요구서 내용을 읽어 보고 **Create pull request**, 이어서 **Merge pull request** > **Confirm merge**를 누릅니다. 이것이 결재 1입니다.
3. 내 PC를 맞춥니다.

```
git checkout main
```

```
git pull origin main
```

결재 기록은 따로 남기지 않아도 됩니다. 다음 절의 루프가 시작할 때 GitHub 머지 기록을 읽어 자동으로 남깁니다.

## 7. 루프 실행 (AI 작성과 자동 검사)

1. 작업 브랜치를 만듭니다.

```
git checkout -b build
```

2. 루프를 실행합니다. 마트가 하나뿐이라 마트 이름은 넣지 않아도 됩니다.

```
python scripts/loop/run_loop.py
```

   - 적재 방식이 incremental이면 위 대신 아래처럼 5절에서 적은 날짜를 붙입니다(예시 날짜를 그 날짜로 바꿉니다).

```
python scripts/loop/run_loop.py --ds 2026-11-10
```

3. 수십 분 걸릴 수 있습니다. 창을 닫지 말고 기다립니다. 기다리는 동안 8절의 대시보드를 켜 두면 진행을 화면으로 볼 수 있습니다.
4. 끝나는 경우는 두 가지입니다.
   - **통과**: `통과` 줄이 나옵니다. 시각과 반복 횟수를 적습니다. 통과하면 루프가 결과와 인수인계 초안을 로컬 커밋까지 합니다
   - **멈춤**: `멈춤:` 줄에 멈춘 이유가 나옵니다. 루프가 기록을 커밋하고 작업 파일을 정리한 뒤 끝나므로 git은 만지지 않습니다. 이유를 적고, 아래 "자주 막히는 곳"에 있는 이유면 거기를 따르고 없으면 담당자에게 알립니다. SQL은 사람이 고치지 않습니다
   - Claude 사용량 한도나 네트워크 문제로 멈췄다면, 풀린 뒤 같은 명령을 다시 실행하면 이어집니다

## 8. 결과 확인

1. **대시보드:** PowerShell 창을 하나 더 열고 아래를 차례로 실행합니다(부록 A를 `ph-kit2` 폴더에서 하는 경우 첫 줄은 부록 A-0의 `cd $HOME\ph-kit2`를 씁니다). 기록이 바뀔 때마다 화면이 새로 고쳐집니다(끌 때는 Ctrl+C).

```
cd $HOME\ph-kit
```

```
python scripts/metrics/dashboard.py --watch
```

```
start out\dashboard.html
```

   결재, 루프 반복, 검사 단계별 통과와 반려, 근거 SQL, 다음에 할 일이 보입니다.

2. **데이터 흐름도:** 통과한 뒤 실행합니다. 열린 폴더 안 마트 이름 폴더에 엑셀(xlsx)과 .md 파일이 생깁니다. 원천에서 raw, stg, mart로 이어지는 흐름을 봅니다. 데이터 카탈로그가 없는 환경이라 "OM 확인" 칸이 "미확인"인 것이 정상입니다.

```
python scripts/deliverables/flow_diagram.py
```

```
start out\deliverables
```

3. **BigQuery 콘솔:** AI가 만든 테이블을 직접 봅니다. 콘솔에서는 보기만 하고 아무것도 만들거나 지우지 않습니다.
   1. 브라우저 주소창에 https://console.cloud.google.com/bigquery 를 넣고 엽니다. 로그인 화면이 나오면 **권한을 받은 본인 Google 계정**으로 로그인합니다. 약관 동의 창이 뜨면 동의합니다
   2. 화면 맨 위 왼쪽, "Google Cloud" 글자 바로 오른쪽에 프로젝트 이름이 적힌 상자(처음이면 "프로젝트 선택")가 있습니다. 이것을 누릅니다
   3. 창이 뜨면 위쪽 탭에서 **전체**(또는 "모두")를 누르고, 검색 칸에 담당자에게 받은 프로젝트 ID를 붙여 넣습니다. 목록에 나온 이름을 누르면 창이 닫히고 맨 위 상자에 그 프로젝트가 보입니다
   4. 화면 왼쪽에 **탐색기** 칸이 있습니다. 거기서 프로젝트 이름 왼쪽의 작은 삼각형(▸)을 눌러 펼치고, 그 아래 `ai_dev` 왼쪽의 ▸도 눌러 펼칩니다. 이름이 `raw_`, `stg_`, `mart_`로 시작하는 테이블이 AI가 만든 것입니다. 탐색기 칸이 안 보이면 화면 왼쪽 끝 세로 아이콘 줄에서 맨 위 돋보기 모양이나 "탐색기"를 누릅니다
   5. 테이블 이름을 누르면 가운데에 탭이 생깁니다. **스키마** 탭에서 컬럼을, **미리보기** 탭에서 실제 값 몇 줄을 봅니다. 미리보기는 비용이 들지 않습니다. 마트 테이블의 날짜별 숫자가 말이 되는지 봅니다
   6. 화면이 영어로 보이면 "전체"는 ALL, "탐색기"는 Explorer, "스키마"는 SCHEMA, "미리보기"는 PREVIEW입니다

## 9. 결재 2 (구현 PR 머지)

루프가 통과했다면 AI가 만든 결과를 승인합니다.

1. 작업 브랜치를 올립니다.

```
git push -u origin build
```

2. GitHub 저장소 페이지에서 **Compare & pull request**를 누릅니다(안 보이면 **Pull requests** > **New pull request** > compare를 `build`로 고름). 바뀐 SQL과 인수인계 초안(`.dev/handover/`)을 훑어보고 **Create pull request** > **Merge pull request** > **Confirm merge**를 누릅니다. 이것이 결재 2입니다.
3. 내 PC를 맞추고 대시보드를 다시 만듭니다. 대시보드가 GitHub 머지 기록을 읽어 결재 2를 완료로 보여 줍니다(파일은 고치지 않습니다).

```
git checkout main
```

```
git pull origin main
```

```
python scripts/metrics/dashboard.py
```

"운영"과 "L6"는 이 키트 범위 밖이라 대기로 남는 것이 정상입니다.

## 자주 막히는 곳

| 증상 | 할 일 |
|---|---|
| `claude`, `gcloud`가 "인식되지 않음" | 설치 뒤 PowerShell 창을 닫고 새로 엽니다 |
| pip에서 한글 관련 오류 | 그대로 적고 담당자에게 알립니다 |
| 설정 스크립트 끝에 본인 이메일이 나옴 | 설정 스크립트를 한 번 더 실행합니다. 그래도 같으면 담당자에게 알립니다 |
| `git push` 거절 | GitHub에 만든 저장소 이름이 `ph-kit`인지, 로그인한 계정이 맞는지 봅니다 |
| `git commit`이 "커밋을 막음: ... 형식 검사(L0) 실패"로 안 됨 | 요구서 contract에 형식 오류가 있는 경우입니다. `claude`로 Claude Code를 켜고 오류 줄을 붙여 넣어 "이 오류를 고쳐 줘"라고 한 뒤, `git add -A`와 같은 `git commit` 명령을 다시 실행합니다 |
| 루프가 "형식 검사(L0)를 통과하지 못함"으로 시작하지 않음 | 결재된 요구서에 형식 오류가 있는 경우입니다. 아래 "요구서를 고친 뒤 다시 시작하기"를 따르고, 2번에서 Claude Code에 오류 줄을 붙여 넣어 "이 오류를 고쳐 줘"라고 합니다 |
| 루프가 "작업 트리가 깨끗하지 않다"로 시작하지 않음 | 메시지에 나온 파일이 `docs/requirements` 안이면 6절처럼 PR로 올립니다. 그 밖이면 적어서 담당자에게 알립니다 |
| 루프가 "리전이 다름: 원천(source.location) ..."으로 멈춤 | 고른 원천과 `ai_dev`의 리전이 다른 경우입니다(부록 A). 부록 A-1로 돌아가 `ai_dev`와 같은 리전의 데이터를 고릅니다. `ai_dev` 리전을 바꾸는 일은 담당자에게 알립니다 |
| 형식 검사(L0)가 "검토한 원천 ... 설정의 원천 ...과 다름"으로 멈춤 | 원천 설정만 바꾸고 개인정보 목록을 다시 검토하지 않은 경우입니다. 부록 A-4를 합니다 |
| 인터뷰에서 AI가 "읽는 양이 500 MB를 넘고 날짜 파티션이 없다"거나 "지원 범위 밖"이라고 함. 또는 루프가 "dry-run ... bytes > 상한"으로 멈춤 | 그 테이블은 이 키트로 다룰 수 없습니다. 다른 테이블이나 다른 데이터를 고르고, 원천이 바뀌면 부록 A-1부터 다시 합니다 |
| 부록 A-3 확인 명령이 "harness_config.json을 읽지 못함: JSONDecodeError"나 "...의 키는 [...]여야 함"으로 끝남 | 설정 파일의 따옴표, 쉼표, 중괄호가 깨졌거나 칸 이름이 바뀐 경우입니다. 부록 A-3의 "바꾼 뒤" 줄과 한 글자씩 비교해 고치고 확인 명령을 다시 실행합니다 |
| 루프가 "ai_dev 기본 파티션 만료(N일)보다 오래된 ds"로 멈춤 | 날짜별 추가 적재(incremental)에서 고른 날짜가 `ai_dev`의 자동 삭제 기간보다 오래된 경우입니다. `ai_dev` 설정은 담당자 권한이라 메시지를 담당자에게 알립니다 |
| 루프가 `input_invalid`로 멈춤 | 이유를 적고 담당자에게 알립니다 |
| 루프가 "rule 문장에 쓸 수 없는 글자"로 멈춤 | 요구서 검사 문장에 작은따옴표가 있는 경우입니다. 아래 "요구서를 고친 뒤 다시 시작하기"를 따르고, 2번에서 Claude Code에 "contract.json의 checks rule 문장에서 작은따옴표, 중괄호, 역슬래시를 빼 줘. 뜻은 바꾸지 마"라고 합니다 |
| 루프가 "요구서 절 번호 1~9여야 함"으로 멈춤 | 아래 "요구서를 고친 뒤 다시 시작하기"를 따르고, 2번에서 Claude Code에 "contract.json에서 requirements의 section 값을 그 요구의 근거가 된 요구서 절 번호(1~9, 따옴표 없는 숫자)로 고쳐 줘. 다른 곳은 고치지 마"라고 합니다 |
| 루프가 "iteration 0 커밋 이후 입력 파일이 바뀜" 또는 "새 작업 브랜치"로 멈춤 | 요구서를 다시 머지한 뒤 예전 `build` 브랜치에서 돌린 경우입니다. 아래 "요구서를 고친 뒤 다시 시작하기"의 4번만 하면 됩니다 |
| 대시보드에 결재가 대기로 남음 | `git pull origin main`을 했는지 봅니다. GitHub에서 "Squash and merge"나 "Rebase and merge"로 머지했다면 머지 기록이 남지 않아 자동으로 보이지 않습니다. 다음부터는 초록 **Merge pull request** 버튼(기본값)으로 머지하고, 이번 것은 담당자에게 알립니다 |

### 요구서를 고친 뒤 다시 시작하기

요구서가 바뀌면 검사 쿼리를 새로 써야 하므로, 예전 `build` 브랜치는 두고 최신 main에서 새 브랜치로 시작합니다. 루프는 멈출 때 작업 파일을 정리해 두므로 바로 옮길 수 있습니다.

1. 최신 main으로 옮깁니다.

```
git checkout main
```

```
git pull origin main
```

2. `claude`로 Claude Code를 켜고 위 표에 적힌 말을 붙여 넣어 요구서를 고칩니다. AI가 contract를 저장할 때마다 형식 검사가 자동으로 돌아, 오류가 있으면 AI가 그 자리에서 고칩니다. 고쳐지면 Claude Code를 닫습니다.

3. 고친 요구서를 다시 결재받습니다(브랜치 이름만 `req2`로 바꿔 6절과 같은 순서). GitHub에서 6절 2번처럼 PR을 만들고 머지합니다.

```
git checkout -b req2
```

```
git add -A
```

```
git commit -m "요구서 수정"
```

```
git push -u origin req2
```

4. 내 PC를 맞추고, 새 작업 브랜치에서 루프를 실행합니다(한 번 더 고치게 되면 `req3`, `build3`처럼 숫자를 올립니다).

```
git checkout main
```

```
git pull origin main
```

```
git checkout -b build2
```

```
python scripts/loop/run_loop.py
```

## 끝나고 담당자에게 보낼 것

1. 아래를 한 번 실행하고, 생긴 `out\dashboard.json` 파일을 담당자에게 보냅니다. 마트 이름, 단계별 완료 시각(결재 1, 루프, 결재 2), 루프 반복 수, 반려 수, 멈춤 이유가 이 파일에 자동으로 들어 있습니다. 적재 방식은 커밋된 요구서에 남습니다. 데이터 값, 오류 원문, 이메일은 들어 있지 않습니다.

```
python scripts/metrics/dashboard.py --json
```

2. (선택) 사람만 알 수 있는 것을 짧게 적어 줍니다. 데이터 값, 오류 원문, 이메일은 적지 않습니다.
   - 4절 키트 시험 결과 줄
   - 막힌 곳(절 번호)과 그때 물어본 것
   - 대시보드와 흐름도에서 이해하기 어려웠던 곳
   - 이 문서에서 고칠 점

## 부록 A. 데이터 직접 고르기

데이터는 내가 고르고, 이 키트로 되는지는 하네스(인터뷰와 자동 검사 L0, L1)가 판정합니다. 이 문서는 특정 데이터를 추천하지 않습니다.

### A-0. 어느 폴더에서 하나

- **처음부터 데이터를 직접 고르는 경우**: 2~4절에서 만든 `ph-kit` 폴더에서 그대로 A-1로 갑니다
- **예시 요청을 이미 끝낸 경우**: 예시 결과와 섞이지 않게 새 폴더 `ph-kit2`와 새 GitHub 저장소 `ph-kit2`에서 합니다. 아래 순서대로 한 뒤 A-1로 갑니다

1. 받은 zip을 임시 폴더에 풀고 `ph-kit2`라는 이름으로 옮긴 뒤 그 폴더로 갑니다.

```
Expand-Archive -Path "$HOME\Downloads\ph-kit.zip" -DestinationPath "$HOME\ph-kit2-unzip"
```

```
Move-Item "$HOME\ph-kit2-unzip\ph-kit" "$HOME\ph-kit2"
```

```
cd $HOME\ph-kit2
```

2. 3절을 처음부터 다시 합니다. 다른 점은 GitHub에서 만드는 저장소 이름이 `ph-kit2`라는 것 하나입니다. 설정 스크립트는 폴더 이름을 보고 `ph-kit2` 저장소에 연결합니다.
3. 4절 1번(도구 설치)은 건너뛰어도 됩니다. 이 문서에서 `cd $HOME\ph-kit`이 나오면 아래 명령을 대신 씁니다.

```
cd $HOME\ph-kit2
```

### A-1. 공개 데이터 고르기 (BigQuery 콘솔)

- **왜**: 어떤 데이터로 마트를 만들지 내가 정합니다. 콘솔(브라우저에서 쓰는 Google Cloud 관리 화면)에서 공개 데이터 목록을 보고 고릅니다
- **할 일**: 내 `ai_dev`의 리전을 확인하고, 콘솔의 마켓플레이스에서 같은 리전의 공개 데이터셋을 하나 고릅니다
- **성공하면 보이는 것**: 콘솔 왼쪽 탐색기에 `bigquery-public-data` 아래 고른 데이터셋이 보이고, 그 리전이 내 `ai_dev` 리전과 같음

1. 내 `ai_dev`의 리전(데이터가 저장된 지역)을 먼저 확인합니다. 키트 폴더의 PowerShell에서 아래 두 줄을 차례로 실행합니다. 첫 줄은 설정 스크립트가 만든 로그인 설정을 이 창에서 쓰게 합니다.

```
$env:CLOUDSDK_CONFIG = (Get-Content .kit_local.json | ConvertFrom-Json).cloudsdk_config
```

```
bq show --format=prettyjson ai_dev
```

   여러 줄 가운데 `"location": "US"` 같은 줄을 찾습니다. 따옴표 안의 값(예: `US`)이 내 `ai_dev` 리전입니다. 적어 둡니다.

2. 브라우저 주소창에 https://console.cloud.google.com/bigquery 를 넣고 엽니다. 로그인 화면이 나오면 **권한을 받은 본인 Google 계정**으로 로그인합니다. 맨 위 왼쪽 프로젝트 상자에 담당자에게 받은 프로젝트가 보이는지 봅니다. 다른 프로젝트면 8절 3번의 2~3번처럼 바꿉니다.
3. 화면 왼쪽 **탐색기** 칸의 위쪽에서 **+ 추가**(영어 화면은 **+ ADD**)를 누릅니다. 탐색기 칸이 안 보이면 화면 왼쪽 끝 세로 아이콘 줄에서 맨 위 돋보기 모양이나 "탐색기"를 누릅니다.
4. 오른쪽에 창이 열리면 **공개 데이터 세트**(Public datasets)를 누릅니다. 마켓플레이스(Google이 공개한 데이터 목록 화면)가 열립니다.
5. 목록에서 데이터를 고릅니다.
   - 위쪽 검색 칸에 관심 있는 주제를 영어로 넣으면 좁혀집니다(예: `taxi`, `weather`, `sales`)
   - 왼쪽 필터에 가격(Pricing)이 있으면 **무료**(Free)를 고릅니다
   - 카드를 누르면 설명 화면이 열립니다. 설명에 어떤 데이터인지, 얼마나 자주 바뀌는지가 나옵니다
6. 마음에 드는 데이터의 설명 화면에서 **데이터 세트 보기**(VIEW DATASET)를 누릅니다. BigQuery 화면으로 돌아오고, 왼쪽 탐색기에 `bigquery-public-data`가 생깁니다(별 모양으로 고정됨).
7. 탐색기에서 `bigquery-public-data` 왼쪽의 ▸를 눌러 펼치고, 방금 고른 데이터셋 이름을 찾습니다. 이 이름(예: `my_dataset`)이 A-2, A-3에서 쓰는 **데이터셋 이름**입니다. 적어 둡니다.
   - 탐색기에서 데이터셋이 `bigquery-public-data`가 아닌 다른 프로젝트 아래에 생겼다면 이 키트로 쓸 수 없습니다. 5번으로 돌아가 다른 데이터를 고릅니다
8. 데이터셋 이름을 누르면 가운데에 정보가 나옵니다. **데이터 위치**(Data location) 값이 1번에서 적은 `ai_dev` 리전과 같은지 봅니다. 다르면 5번으로 돌아가 다른 데이터를 고릅니다.
9. (선택) 데이터셋 왼쪽 ▸를 눌러 테이블 목록을 보고, 테이블을 눌러 **스키마**(SCHEMA) 탭에서 컬럼을, **세부정보**(DETAILS) 탭에서 크기와 파티션을 볼 수 있습니다. 이 확인은 A-2에서 AI가 대신 하므로 건너뛰어도 됩니다. **쿼리**(QUERY) 버튼은 누르지 않습니다(읽는 양만큼 비용이 듭니다).

화면 이름은 콘솔 업데이트에 따라 조금 다를 수 있습니다. 비슷한 이름의 버튼을 누르면 됩니다.

### A-2. 되는지 확인 (AI가 조회, 내가 판단)

- **왜**: 이 키트가 다룰 수 없는 데이터면 중간에 멈춥니다. 시작 전에 확인하면 시간을 아낍니다
- **할 일**: 지원 범위를 읽고, A-1에서 고른 데이터의 확인을 Claude Code에 맡깁니다
- **성공하면 보이는 것**: AI가 낸 표의 모든 칸이 "가능"

지원 범위입니다. 조건에 맞지 않으면 하네스가 아래 자리에서 멈추고 알려 줍니다.

| 조건 | 맞지 않으면 멈추는 곳 | 화면에 보이는 말 |
|---|---|---|
| `bigquery-public-data` 안의 공개 데이터셋 1개 | L0(형식 검사) | `sources[0]: bigquery-public-data.(데이터셋).<table> 형식이어야 함` |
| `ai_dev`와 같은 리전(데이터가 저장된 지역, 예: US) | 루프의 첫 BigQuery 조회 전(L1 앞) | `리전이 다름: 원천(source.location) ..., ai_dev ...` |
| 실제 테이블. 뷰(다른 테이블을 읽는 저장된 쿼리)는 쓸 컬럼만 읽는 양이 500 MB 이하일 때만 되고, 날짜별 추가 적재는 고를 수 없음 | 인터뷰 | AI가 범위 밖이라고 알려 줌 |
| 한 번에 읽는 양 500 MB 이하, 또는 날짜 파티션(날짜별로 나눠 저장한 구조) 테이블 | 인터뷰. 놓치면 L1 | AI가 범위 밖이라고 알려 줌. L1은 `dry-run ... bytes > 상한` |
| 고객 데이터나 개인정보가 담긴 데이터가 아님 | 하네스가 판정하지 못함. 내가 확인 | - |

1. Claude Code를 켭니다.

```
claude
```

2. 아래 문장을 붙여 넣기 전에 **`데이터셋이름` 부분을 A-1에서 적어 둔 데이터셋 이름으로 바꿉니다**(예: 데이터셋 이름이 `my_dataset`이면 `bigquery-public-data.my_dataset을`).

```
bigquery-public-data.데이터셋이름을 원천으로 쓰려고 해. 지원 범위에 맞는지 메타데이터 조회와 dry-run으로만 확인해서 표로 알려 줘. 쓸 테이블, 크기, 날짜 파티션, 뷰 여부, 리전, 개인정보 후보 컬럼을 보여 줘. 설정 파일은 고치지 마.
```

3. 표의 리전이 A-1 1번에서 본 `ai_dev` 리전과 같은지 봅니다. 모든 칸이 "가능"이면 A-3으로 갑니다. 하나라도 "불가"면 A-1로 돌아가 다른 데이터를 고른 뒤 이 절 2번부터 다시 합니다. 표의 데이터셋 이름, 리전, 개인정보 후보 컬럼은 A-3~A-5에서 쓰니 Claude Code 창을 닫지 않고 둡니다.

### A-3. 원천 설정 바꾸기 (내가 직접)

- **왜**: 원천을 바꾸는 일은 사람이 결재하는 일이라, AI는 이 파일을 고치지 못하게 막아 두었습니다
- **할 일**: 설정 파일의 원천 칸 하나(필요하면 둘)를 바꾸고 형식을 확인합니다
- **성공하면 보이는 것**: `원천 설정 형식 통과: bigquery-public-data.(고른 데이터셋 이름)`

1. Claude Code 창은 두고 PowerShell 창을 하나 더 열어 키트 폴더로 갑니다(`ph-kit2`에서 하면 A-0의 명령).

```
cd $HOME\ph-kit
```

2. 설정 파일을 메모장으로 엽니다.

```
notepad dags\harness_config.json
```

3. `"source"`로 시작하는 줄만 고칩니다. `"dataset"` 칸의 값을 A-1에서 고르고 A-2에서 확인한 데이터셋 이름으로 바꿉니다. `"location"` 칸은 A-2 표의 리전과 같아야 하며, 보통 그대로 둡니다. 따옴표, 쉼표, 중괄호는 지우지 않습니다.

바꾸기 전:

```
  "source": {"project": "bigquery-public-data", "dataset": "thelook_ecommerce", "location": "US"},
```

바꾼 뒤(데이터셋 이름이 `my_dataset`인 경우):

```
  "source": {"project": "bigquery-public-data", "dataset": "my_dataset", "location": "US"},
```

   - 다른 줄(`"schema_version"`, `"datasets"`, `"retired_datasets"`, `"om"`)은 건드리지 않습니다. `"datasets"`의 이름에 `thelook`이 남아 있어도 이 키트에서는 쓰지 않는 운영용 이름이라 괜찮습니다
   - Ctrl+S로 저장하고 메모장을 닫습니다

4. 형식을 확인합니다.

```
python -c "import sys; sys.path.insert(0, 'scripts/ladder'); import harness_config; harness_config.load(); print('원천 설정 형식 통과:', harness_config.source_prefix())"
```

   성공하면 `원천 설정 형식 통과: bigquery-public-data.my_dataset`처럼 고른 데이터셋 이름이 보입니다. 오류가 나면 마지막 줄을 보고 "자주 막히는 곳"을 따릅니다.

### A-4. 개인정보 목록 확정 (AI가 후보, 내가 결정)

- **왜**: `docs/architecture/pii_columns.md`(개인 식별 컬럼 목록)의 "검토한 원천" 줄이 설정의 원천과 다르면 L0가 일부러 멈춥니다. 개인정보를 검토하지 않은 채 진행하는 것을 막는 장치입니다
- **할 일**: AI가 낸 후보를 보고 개인정보로 볼 컬럼을 내가 정한 뒤, AI가 파일을 고칩니다
- **성공하면 보이는 것**: `원천 설정과 개인정보 목록 형식 통과: bigquery-public-data.(고른 데이터셋 이름)`

1. A-2의 Claude Code 창에 아래 문장을 붙여 넣습니다.

```
dags/harness_config.json의 원천을 바꿨어. docs/architecture/pii_columns.md를 새 원천 기준으로 다시 써야 해. 원천의 컬럼 이름만 조회해서(데이터 값은 보지 마) 개인 식별 컬럼 후보를 표로 먼저 보여 주고, 파일은 내가 승인한 뒤에 고쳐 줘. 고칠 때는 "검토한 원천" 줄을 설정의 source와 같게 바꾸고, 표에는 내가 고른 컬럼만 넣어. 내가 없다고 하면 표에 (없음) 행 하나만 둬.
```

2. 후보 표를 보고 개인정보로 볼 컬럼을 답합니다(이름, 이메일, 주소, 전화번호, 정밀한 위치 같은 컬럼). 없으면 "없음"이라고 답합니다. AI가 파일 고치기를 허락해 달라고 하면 `1`을 누릅니다.

   고친 뒤의 모습은 아래와 같습니다. 개인 식별 컬럼이 없으면 표에 `(없음)` 행 하나만 남고, 표가 그냥 비어 있으면 L0가 멈춥니다.

```
검토한 원천: `bigquery-public-data.my_dataset`

| 원천 테이블 | 컬럼 | 근거 |
|---|---|---|
| (없음) | | 모든 테이블의 컬럼 이름 검토, 개인 식별 컬럼 없음 |
```

   개인 식별 컬럼이 있으면 `(없음)` 행 대신 컬럼마다 `` | `테이블` | `컬럼` | 근거 | `` 행을 둡니다(두 종류를 함께 두면 L0가 멈춥니다).

3. A-3의 PowerShell 창에서 형식을 확인합니다.

```
python -c "import sys; sys.path.insert(0, 'scripts/ladder'); import harness_config, l0_contract; harness_config.load(); l0_contract.load_pii(); print('원천 설정과 개인정보 목록 형식 통과:', harness_config.source_prefix())"
```

   성공하면 `원천 설정과 개인정보 목록 형식 통과: bigquery-public-data.my_dataset`처럼 보입니다.

### A-5. 원천 변경 결재

- **왜**: 원천 변경은 사람이 PR 머지로 결재합니다. 확인한 내용은 원천 등록 체크리스트(`docs/kit/source_checklist.md`)에 남깁니다
- **할 일**: 체크리스트를 채우고, `source` 브랜치로 6절과 같은 순서로 PR을 만들어 머지합니다
- **성공하면 보이는 것**: GitHub에서 PR이 Merged(보라색)로 바뀌고, `git status`에 바뀐 파일이 3개뿐

1. A-2의 Claude Code 창에 아래 문장을 붙여 넣습니다. 다 채우면 `/exit`로 닫습니다.

```
docs/kit/source_checklist.md의 칸을 지금까지 확인한 결과(원천, 리전, 테이블 크기, 날짜 파티션, 개인정보 검토)로 채워 줘. 공개 데이터라 데이터 소유자 승인 칸은 "공개 데이터, 요청자 확인"으로, 운영 비용 칸은 "키트 범위 밖(운영 실행 없음)"으로 적어. 데이터 값은 적지 말고, 다른 파일은 고치지 마.
```

2. 브랜치를 만들고 바뀐 파일을 봅니다.

```
git checkout -b source
```

```
git status
```

   빨간 글씨 파일이 `dags/harness_config.json`, `docs/architecture/pii_columns.md`, `docs/kit/source_checklist.md` 세 개뿐이어야 합니다. `.dev/` 안의 기록 파일(AI 작업 기록)이 함께 보이는 것은 괜찮습니다. 그 밖의 파일이 보이면 멈추고 담당자에게 알립니다.

3. 올립니다.

```
git add -A
```

```
git commit -m "원천 변경"
```

```
git push -u origin source
```

4. 6절 2번처럼 GitHub에서 PR을 만들고 머지합니다(compare는 `source`). PR 화면의 **Files changed** 탭에서 세 파일을 한 번 훑어봅니다.
5. 내 PC를 맞춥니다.

```
git checkout main
```

```
git pull origin main
```

### A-6. 5절로 돌아가기

- **왜**: 원천이 결재됐으니 이제 고른 데이터로 요구서를 만듭니다
- **할 일**: 5절을 그대로 하되, 2번 문장만 아래 문장으로 바꿔 붙입니다
- **성공하면 보이는 것**: 5절 4번처럼 `docs/requirements/`에 파일 3개

아래 문장을 붙여 넣기 전에 **`데이터셋이름`, `테이블이름`, `원하는마트` 세 부분을 바꿉니다**(예: `bigquery-public-data.my_dataset의 my_table로 일별 건수 마트가 필요해`).

```
bigquery-public-data.데이터셋이름의 테이블이름으로 원하는마트가 필요해. docs/requirements/_template.md 기준으로 나에게 인터뷰해서 요구서와 contract 초안을 만들어 줘. 나는 요청자야.
```

- 적재 방식이 날짜별 추가 적재(incremental)로 정해지면 7절에서 `--ds`를 붙여 실행합니다(5절 3번 참고)
- 루프가 "ai_dev 기본 파티션 만료"로 멈추면 담당자에게 알립니다. 고른 날짜가 `ai_dev`의 자동 삭제 기간보다 오래돼 만든 테이블이 바로 지워지는 경우이고, `ai_dev` 설정은 담당자 권한입니다
