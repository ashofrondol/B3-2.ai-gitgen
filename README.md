# ai-gitgen — Git 변경 사항으로 커밋 메시지·PR 초안 만들기

`git status` · `git diff` 결과를 모아 AI API(OpenAI 호환 Chat Completions)에 보내고,
돌아온 답을 **형식 규칙에 맞게 다듬어** 커밋 메시지와 PR 제목·본문 초안을 터미널에 출력하는 Python CLI 다.

- 결과는 **초안**이다. 커밋·push·GitHub PR 생성은 하지 않는다. 사람이 읽고 고친 뒤 직접 적용한다.
- AI API 는 SDK 없이 `requests` 로 REST 요청을 직접 만든다. 무엇을 보내고 받는지가 코드에 그대로 보인다.
- 한 번 실행할 때 AI API 호출은 **1회**, 형식 규칙을 어겼을 때만 **최대 2회**다.

## 1. 설치

Python 3.10 이상, Git 이 필요하다.

```bash
git clone https://github.com/ashofrondol/B3-2.ai-gitgen.git
cd B3-2.ai-gitgen
python3 -m venv .venv
source .venv/bin/activate          # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt    # 테스트까지 돌리려면 requirements-dev.txt
```

## 2. API Key 설정

키는 **환경변수로만** 받는다. 코드에 적지 않는다.

| 환경변수 | 필수 | 설명 |
|---|---|---|
| `API_KEY` | 예 | AI API 키 |
| `BASE_URL` | 아니오 | 비우면 `https://api.openai.com/v1`. 다른 OpenAI 호환 서버면 `/v1` 까지 적는다 |
| `MODEL` | 아니오 | 비우면 `gpt-4o-mini`. `--model` 옵션이 더 우선한다 |

방법 1 — 셸에서 설정:

```bash
export API_KEY="YOUR_KEY"
```

방법 2 — `.env` 파일 (프로젝트 루트, `.gitignore` 에 이미 들어 있다):

```bash
cp .env.example .env    # 그리고 API_KEY= 뒤에 키를 적는다
```

값을 찾는 순서는 **셸 환경변수 → 현재 폴더의 `.env` → 도구 폴더(`main.py` 옆)의 `.env`** 이고, 먼저 찾은 값이 이긴다.

## 3. 사용법

명령은 **Git 저장소의 루트**에서 실행한다. 하위 폴더에서 실행하면 오류로 멈춘다.
다른 저장소에 쓰려면 그 저장소 루트로 이동해 `python /경로/B3-2.ai-gitgen/main.py commit` 처럼 부른다
(키는 도구 폴더의 `.env` 에 둔 것을 그대로 쓴다).

```bash
git add -p                      # 커밋할 변경을 스테이징
python main.py commit           # 커밋 메시지 생성
python main.py pr               # 현재 브랜치 vs main 으로 PR 초안 생성
python main.py pr --base develop
python main.py commit --help    # 옵션 전체 보기
```

| 명령 | 무엇을 diff 하나 |
|---|---|
| `commit` | 스테이징된 변경(`git diff --cached`). 스테이징된 것이 없으면 작업 트리 변경(`git diff`) |
| `pr` | 기준 브랜치와 비교(`git diff main...HEAD`). 지금 기준 브랜치 위라면 커밋 전 변경(`git diff HEAD`) |

### 옵션

| 옵션 | 기본값 | 설명 |
|---|---|---|
| `--model` | `MODEL` 또는 `gpt-4o-mini` | 사용할 모델 |
| `--temperature` | commit `0.2` / pr `0.4` | 0.0~2.0. 낮을수록 매번 비슷한 표현 |
| `--max-tokens` | commit `400` / pr `1000` | 응답 최대 토큰 수 |
| `--timeout` | `60` | 요청 제한 시간(초) |
| `--no-retry` | 꺼짐 | 형식 위반이어도 다시 만들지 않고 후처리만 (호출 1회 고정) |
| `--dry-run` | 꺼짐 | AI 를 부르지 않고 **보낼 프롬프트만 출력** (API Key 불필요, 비용 0) |
| `--safe-mode` | 꺼짐 | 민감 파일 제외 + 키·이메일 등 마스킹 + 전송량 제한 |
| `--max-files` / `--max-lines` | `10` / `200` | 안전 모드에서 보낼 최대 파일 수 / diff 줄 수 |
| `--base` (pr) | `main` | PR 비교 기준 브랜치 |

진행 로그(`[INFO]` 등)는 stderr, 결과 블록은 stdout 으로 나간다. 그래서 결과만 파일로 받을 수 있다.

```bash
python main.py commit > /tmp/draft.txt   # 로그는 화면에, 결과는 파일에
```

## 4. 출력 예시

> 아래 커밋·PR 예시는 형식을 보여 주려고 **로컬 가짜 OpenAI 호환 서버**에 붙여 실행한 실제 터미널 출력이다.
> AI 가 쓰는 문구는 모델·diff·temperature 에 따라 매번 달라진다. 나머지 두 예시(키 없음·변경 없음)는 AI 와 무관한 실제 출력이다.

### 커밋 메시지

```text
$ python main.py commit
[INFO] 현재 브랜치: main
[INFO] Git status 수집 완료: 1개 파일 변경 감지
        A  app.py
[INFO] Git diff 수집 완료: 8줄 · 스테이징된 변경 (git diff --cached)
[INFO] AI API 요청 중... (model=gpt-4o-mini, temperature=0.2, max_tokens=400)
[DONE] 커밋 메시지 생성 완료
[INFO] AI API 호출 횟수: 1회 · 토큰 입력 321 / 출력 45
--- Commit Message ---
feat(app): 인사 함수 추가

- app.py 에 hello() 추가
- README 사용법 한 줄 보강
----------------------
[INFO] AI 가 만든 초안입니다. 실제 변경과 맞는지 검토한 뒤 사용하세요.
```

### PR 제목·본문

```text
$ python main.py pr
[INFO] 현재 브랜치: feature/greeting
[INFO] Git diff --name-status 수집 완료: 2개 파일 변경 감지
        M  README.md
        A  app.py
[INFO] Git diff 수집 완료: 15줄 · 브랜치 비교 (git diff main...HEAD)
[INFO] AI API 요청 중... (model=gpt-4o-mini, temperature=0.4, max_tokens=1000)
[DONE] PR 초안 생성 완료
[INFO] AI API 호출 횟수: 1회 · 토큰 입력 321 / 출력 45
--- PR Title ---
feat: 인사 함수와 사용법 추가

--- PR Body ---
## Why
- 예제 실행 방법이 없었음

## What
- app.py 에 hello() 추가
- README 에 실행 예시 추가

## How to Test
- `python app.py` 실행 후 인사 문구 확인
----------------------
[INFO] AI 가 만든 초안입니다. 실제 변경과 맞는지 검토한 뒤 사용하세요.
```

### 형식 규칙을 어긴 답이 왔을 때 (1회 재생성)

```text
[WARN] 형식 규칙 위반 1건 → 1회 다시 생성합니다: '## How to Test' 섹션에 불릿이 없습니다.
[DONE] PR 초안 생성 완료
[INFO] AI API 호출 횟수: 2회 · 토큰 입력 642 / 출력 90
```

### API Key 가 없을 때 / 변경 사항이 없을 때

```text
$ python main.py commit
[ERROR] API_KEY 환경변수가 설정되지 않았습니다.
        예) export API_KEY="YOUR_KEY"  (또는 .env 파일에 API_KEY=YOUR_KEY)

$ python main.py commit
[INFO] 현재 브랜치: main
[INFO] Git status 수집 완료: 0개 파일 변경 감지
[INFO] Git diff 수집 완료: 0줄 · 작업 트리 변경 (git diff, 스테이징된 변경 없음)
[INFO] 변경 사항이 없습니다. 커밋 메시지를 생성하지 않고 종료합니다.
```

## 5. 구조

```
main.py               진입점 (app.cli.main 호출)
app/config.py         기본값·길이 규칙·환경변수 읽기 — 숫자는 이 파일 한 곳에만
app/git_manager.py    git status / git diff 수집, 저장소 루트 확인
app/safety.py         안전 모드: 민감 파일 제외, 패턴 마스킹, 전송량 제한
app/prompts.py        system(규칙) / user(이번 변경) 프롬프트 만들기
app/ai_client.py      REST 호출, HTTP·네트워크 오류를 원인+대처법으로 변환
app/formatter.py      응답 후처리와 형식 검증
app/cli.py            옵션 처리와 전체 흐름, 출력
tests/                pytest 81개 (네트워크 없이 실행)
```

실행 흐름: **옵션·키 확인 → Git 수집 → (변경 없으면 종료) → 안전 모드·길이 상한 → 프롬프트 → AI 호출 → 후처리·검증 → (위반 시 1회 재생성) → 출력**

- **Git 수집과 AI 호출을 나눈 이유**: 둘은 바뀌는 이유가 다르다. Git 쪽은 "어떤 범위를 diff 하나"가,
  AI 쪽은 "어느 서버에 어떤 형식으로 보내나"가 바뀐다. 나눠 두면 테스트도 따로 된다 —
  Git 은 임시 저장소로, AI 는 가짜 세션·가짜 클라이언트로 네트워크 없이 시험한다.
- **프롬프트와 형식 검증을 나눈 이유**: 프롬프트는 "이렇게 써 달라"는 부탁이고, 모델이 늘 지키지는 않는다.
  그래서 길이·섹션 규칙을 `formatter.py` 가 코드로 다시 검사한다. 규칙 숫자(50/72/80)는
  `config.py` 에 한 번만 두고 프롬프트와 검사가 같은 값을 쓴다.
- **API 설정을 CLI 옵션으로 둔 이유**: 같은 diff 에 `--temperature`, `--max-tokens`, `--model` 만 바꿔
  다시 돌려 보며 비교하기 쉽다. 쓴 값은 매번 `[INFO] AI API 요청 중... (model=..., temperature=..., max_tokens=...)`
  로그에 남아 같은 조건으로 재현할 수 있다.

## 6. 형식 규칙과 검증

| 대상 | 규칙 | 어기면 |
|---|---|---|
| 커밋 제목 | 1줄, 50자 이내 권장 | 경고만 |
| 커밋 제목 | 최대 72자 | 재생성 → 그래도 넘으면 단어 경계에서 자름 |
| 커밋 제목 | `feat:` `fix(scope):` 같은 type 접두어 | 경고만 |
| 커밋 본문 | 선택. 있으면 `- ` 불릿 (바뀐 파일·모듈 1~3개 언급을 프롬프트로 요구) | `*`, `1.` 등은 `- ` 로 통일 |
| PR 제목 | 1줄, 최대 80자 | 재생성 → 그래도 넘으면 자름 |
| PR 본문 | `## Why` `## What` `## How to Test` + 섹션마다 불릿 1개 이상 | 재생성 → 그래도 비면 자리표시 불릿을 넣고 경고 |

**재생성과 후처리를 섞은 이유**

1. 코드 블록 표시, `Title:` 같은 라벨, `### why`·`**What**` 같은 헤더 변형, 불릿 기호처럼 **뜻을 바꾸지 않고
   고칠 수 있는 것은 후처리**로 바로 고친다. 비용이 0 이고 결과가 항상 같다.
2. 섹션이 통째로 없거나 제목이 너무 긴 것은 **내용을 새로 써야** 해서 코드가 대신 지어낼 수 없다.
   그래서 어긴 규칙을 알려 주며 **딱 1회** 다시 요청한다 (과제 권장: 실행당 1~2회).
3. 두 번째도 어기면 더 부르지 않고 자르기·자리표시로 규칙을 강제로 맞춘 뒤 `[WARN]` 으로 알린다.
   비용을 예측할 수 있게 상한을 고정했다. `--no-retry` 면 1번과 3번만 한다.

## 7. temperature 와 max_tokens

- **temperature** 는 다음 단어를 고를 때 얼마나 모험할지다. 낮으면(0.0~0.3) 가장 그럴듯한 표현을 골라
  매번 비슷한 결과가, 높으면(0.8 이상) 표현이 다양해지는 대신 형식을 벗어나거나 엉뚱한 말이 늘 수 있다.
  커밋 메시지는 짧고 일정해야 해서 `0.2`, PR 본문은 문장이 길어 약간의 여유를 줘 `0.4` 로 정했다.
- **max_tokens** 는 응답 길이의 상한이다. 결과를 "더 길게" 만들지는 않고, 넘으면 중간에서 잘린다
  (`finish_reason=length` → `[WARN] 응답이 max_tokens(...) 에서 잘렸습니다`).
  커밋은 제목 1줄 + 불릿 3개 정도라 `400`, PR 은 세 섹션 불릿 2~4개씩이라 `1000` 으로 넉넉히 잡았다.
  한국어는 영어보다 글자당 토큰이 많이 들어 여유를 더 줬다. 추론(thinking) 모델은 생각에도 토큰을 쓰므로 더 크게 줘야 한다.
- 비교해 보는 법: 같은 diff 에서 값만 바꿔 실행한다.

```bash
python main.py pr --temperature 0.0
python main.py pr --temperature 1.2
python main.py pr --max-tokens 60     # 일부러 작게 → 잘림 경고와 재생성/후처리 확인
```

## 8. 오류 처리

| 상황 | 출력 | 종료 코드 |
|---|---|---|
| `API_KEY` 없음 | `[ERROR] API_KEY 환경변수가 설정되지 않았습니다.` + 설정 예시 (Git 작업 전에 바로) | 2 |
| 잘못된 옵션 값 (`--temperature 3` 등) | argparse 오류 | 2 |
| Git 저장소가 아님 / 루트가 아님 / git 없음 | `[ERROR] Git 저장소가 아닙니다...` / `프로젝트 루트에서 실행하세요: ...` | 1 |
| 변경 사항 없음 | `[INFO] 변경 사항이 없습니다...` (API 호출 안 함) | 0 |
| 인증 실패 401·403 | `[ERROR] 인증 실패(HTTP 401): <서버 메시지>` + `API_KEY 값과 권한을 확인하세요.` | 1 |
| 모델·주소 틀림 404 | `요청 대상을 찾을 수 없습니다(HTTP 404)` + `BASE_URL 과 --model 이름을 확인하세요.` | 1 |
| 요청 한도 429 / 서버 오류 5xx | `요청 한도 초과(HTTP 429)` / `AI API 서버 오류(HTTP 5xx)` + 대처법 | 1 |
| 네트워크 끊김 / 시간 초과 | `AI API 서버에 연결하지 못했습니다: <주소>` / `응답 시간 초과(60초)` | 1 |
| 응답이 비었거나 형식이 깨짐 | `AI 응답이 비어 있습니다.` / `응답 형식을 해석하지 못했습니다.` | 1 |

- 오류마다 **원인 + 다음에 할 일**을 같이 보여 준다. 서버 메시지에 키가 섞여 오면 `***` 로 가린다.
- 네트워크 오류를 **자동으로 다시 보내지 않는다.** 요청마다 돈이 들고, 키·주소가 틀린 경우는 몇 번을 보내도
  같다. 원인을 보고 사람이 다시 실행한다.

## 9. 민감정보와 안전 모드

`git diff` 에는 실수로 넣은 API 키, `.env`, 개인키, 이메일·전화번호가 섞일 수 있다. 그대로 보내면 외부 AI 서버로 나간다.

`--safe-mode` 가 하는 일 (정책은 `app/safety.py`):

| 단계 | 내용 | 숫자 기준 |
|---|---|---|
| 민감 파일 제외 | `.env`, `.env.*`, `*.pem`, `*.key`, `*.p12`, `*.pfx`, `id_rsa*`, `id_ed25519*`, `*.keystore`, `credentials*.json`, `secret.key` 의 diff 를 통째로 뺀다 (`.env.example` 은 허용) | — |
| 패턴 마스킹 | OpenAI·Anthropic·AWS·GitHub·Google·Slack 키, JWT, 개인키 블록, `비밀이름 = "값"`, `.env` 형식 `NAME=값`, 이메일, 휴대전화, 주민등록번호 → `[MASKED:종류]` | 비밀이름 규칙은 값 6자 이상 |
| 전송량 제한 | 앞에서부터 파일 N개, 줄 N개까지만 보내고 생략 줄 수를 표시 | 10개 파일 / 200줄 (`--max-files`, `--max-lines`) |
| 길이 상한 | 안전 모드와 **무관하게 항상** 너무 긴 diff 를 줄 경계에서 자른다 | 24,000자 |

안전 모드를 꺼도 민감 패턴이나 민감 파일이 보이면 `[WARN] ... --safe-mode 사용을 권장합니다.` 로 알린다.
`--dry-run` 으로 실제로 무엇이 나가는지 비용 없이 확인할 수 있다. 같은 변경(가짜 값을 넣은 `settings.py` + `server.pem`)을
두고 비교한 실제 출력에서 관련 줄만 뽑았다:

```text
$ python main.py commit --dry-run                 # 안전 모드 OFF (발췌)
[WARN] diff 에서 민감정보로 보이는 패턴 2건을 찾았습니다. --safe-mode 사용을 권장합니다.
[WARN] 민감 파일 diff 가 포함돼 있습니다: server.pem (--safe-mode 면 제외)
+API_KEY = "fake-value-123456"
+ADMIN_EMAIL = "hong@example.com"
+api_key = os.getenv("API_KEY")

$ python main.py commit --dry-run --safe-mode     # 안전 모드 ON (발췌)
[INFO] 안전 모드: 마스킹 2건, 제외 파일 1개, 전송 1/2개 파일 · 9/16줄
참고:
- 민감정보로 보이는 값은 [MASKED:...] 로 가렸습니다. 원래 값을 추측하지 마세요.
- 민감 파일 diff 제외: server.pem
+API_KEY = "[MASKED:SECRET]"
+ADMIN_EMAIL = "[MASKED:EMAIL]"
+api_key = os.getenv("API_KEY")
```

ON 에서 `server.pem` 의 diff 는 아예 빠지고, 값만 가려지며, 마지막 줄처럼 키를 **읽는 코드**는 그대로 남는다.

정규식은 **알려진 모양만** 잡는다. 안전 모드는 위험을 줄이는 장치이지 보안 경계가 아니다.
비밀이 들어간 변경은 애초에 커밋하지 말고, 보내기 전에 diff 를 직접 본다.

## 10. 비용과 요청 횟수

- `commit` / `pr` 은 각각 API **1회** 호출이 기본이고, 형식 위반일 때만 1회 더 (최대 2회). 횟수와 토큰 수는 매번 로그에 찍힌다.
- 변경이 없으면 API 를 부르지 않는다. 키가 없으면 Git 작업 전에 멈춘다.
- 프롬프트를 손볼 때는 `--dry-run` 으로 먼저 확인한다 (호출 0회).
- 큰 변경은 `--safe-mode --max-lines 200` 처럼 줄여 보내면 입력 토큰이 준다. 어차피 diff 는 24,000자에서 잘린다.
- 형식 오류 몇 글자는 다시 돌리기보다 직접 고치는 편이 싸다 (`--no-retry`).

## 11. 생성 결과를 그대로 쓰면 안 되는 이유

AI 는 diff 만 보고 쓰기 때문에 **왜** 바꿨는지는 추측이고, 돌려 보지 않은 테스트를 "통과"라고 쓰거나
없는 기능을 설명할 수 있다. 프롬프트로 막고는 있지만 보장은 못 한다. 적용 전에 확인할 것:

- [ ] 제목이 실제 변경을 맞게 요약하는가
- [ ] Why 가 실제 목적과 맞는가 (diff 에 없는 이유를 지어내지 않았는가)
- [ ] How to Test 의 명령이 실제로 돌아가는가, 실행하지 않은 결과를 주장하지 않는가
- [ ] 민감정보가 들어 있지 않은가

## 12. 테스트

```bash
pip install -r requirements-dev.txt
pytest
```

81개 테스트가 네트워크 없이 돈다. Git 은 임시 저장소를 만들어 실제 `git` 으로, AI 는 가짜 세션(HTTP 상태별 응답)과
가짜 클라이언트(정상·위반·오류 응답)로 시험한다. Python 3.10 / 3.12 에서 확인했다.

## 13. 팀에 적용한다면 먼저 할 것

1. **팀 컨벤션 설정 파일** — type 목록·scope 필수 여부·PR 템플릿 섹션을 설정으로 빼서 저장소마다 다르게.
   팀마다 규칙이 달라 이게 없으면 결과를 매번 손으로 고친다.
2. **안전 모드 기본값 켜기 + 사내 패턴 추가** — 사번·내부 도메인 같은 회사 고유 패턴은 기본 정규식이 모른다.
3. **`git commit -F` 로 바로 넘기는 출력 모드** — 지금은 사람이 복사한다. 검토 후 한 번에 적용하는 흐름.
