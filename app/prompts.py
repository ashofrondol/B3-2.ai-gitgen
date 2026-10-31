"""AI 에게 보낼 프롬프트를 만든다.

system 에는 매번 같은 규칙(형식·길이·금지 사항)을, user 에는 이번 변경 사항(브랜치·파일 목록·diff)을
넣는다. 형식을 지켰는지는 여기서 믿지 않고 formatter.py 가 다시 검사한다.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.config import COMMIT_TITLE_MAX, COMMIT_TITLE_RECOMMENDED, PR_TITLE_MAX
from app.git_manager import GitChanges

MAX_LISTED_FILES = 50


@dataclass(frozen=True)
class Prompt:
    system: str
    user: str


COMMIT_SYSTEM = f"""\
당신은 git diff 를 읽고 그 변경에 맞는 커밋 메시지 하나를 쓰는 시니어 개발자입니다.

[형식]
1줄: 제목. "<type>(<scope>): <요약>" 또는 "<type>: <요약>"
  - type 은 feat, fix, docs, style, refactor, test, chore, perf, build, ci 중 하나
  - scope 는 선택. 바뀐 모듈 이름 (예: cli, git, safety)
  - {COMMIT_TITLE_RECOMMENDED}자 이내 권장, 절대 {COMMIT_TITLE_MAX}자를 넘기지 않는다
  - 한국어, 간결한 명사형 끝맺음 (예: "~추가", "~수정"), 끝에 마침표 없음
본문(선택): 빈 줄 하나 뒤에 "- " 불릿 1~3개
  - 무엇을 왜 바꿨는지, 바뀐 파일·모듈 1~3개를 이름으로 언급

[규칙]
- diff 에 보이는 사실만 쓴다. 테스트 결과·이슈 번호·변경 이유를 지어내지 않는다.
- 커밋 메시지만 출력한다. 코드 블록(```), 따옴표, 머리말·설명 문장을 붙이지 않는다.

[예시]
feat(cli): 커밋 메시지 생성 명령 추가

- cli.py 에 commit 하위 명령과 --temperature 옵션 추가
- 변경 사항이 없으면 API 를 호출하지 않고 종료
"""

PR_SYSTEM = f"""\
당신은 git diff 를 읽고 Pull Request 제목과 본문 초안을 쓰는 시니어 개발자입니다.

[출력 형식 — 이 모양 그대로]
Title: <PR 제목>
## Why
- <변경 배경·목적>
## What
- <핵심 변경 사항>
## How to Test
- <리뷰어가 직접 해 볼 확인 절차>

[규칙]
- 제목은 한 줄, {PR_TITLE_MAX}자 이내. "feat: ..." 처럼 type 접두어를 권장한다.
- Why: 불릿 1~3개. 왜 이 변경이 필요한지.
- What: 불릿 1~4개. 무엇이 바뀌었는지, 파일·모듈 이름을 언급.
- How to Test: 불릿 1~4개. 실제로 실행할 수 있는 절차, 명령어는 `백틱` 으로 감싼다.
- 세 섹션 모두 "- " 불릿이 최소 1개 있어야 한다. 다른 섹션을 만들지 않는다.
- diff 에 보이는 사실만 쓴다. 테스트를 실행했다거나 통과했다고 쓰지 않는다.
- 코드 블록(```)이나 머리말·설명 문장을 붙이지 않는다. 한국어로 쓴다.
"""


def describe_changes(changes: GitChanges, diff_text: str, notes: list[str]) -> str:
    """두 명령이 함께 쓰는 user 메시지 본문."""
    lines = [
        f"브랜치: {changes.branch}",
        f"diff 범위: {changes.source}",
        f"변경 파일 ({len(changes.files)}개):",
    ]
    lines += [f"- [{f.label}] {f.path}" for f in changes.files[:MAX_LISTED_FILES]]
    if len(changes.files) > MAX_LISTED_FILES:
        lines.append(f"- ... 외 {len(changes.files) - MAX_LISTED_FILES}개")
    if notes:
        lines.append("")
        lines.append("참고:")
        lines += [f"- {note}" for note in notes]
    lines.append("")
    if diff_text.strip():
        lines.append(f"```diff\n{diff_text.rstrip()}\n```")
    else:
        lines.append("(diff 없음 — 파일 목록만 참고)")
    return "\n".join(lines)


def build_commit_prompt(changes: GitChanges, diff_text: str, notes: list[str]) -> Prompt:
    user = "아래 변경 사항으로 커밋 메시지를 작성하세요.\n\n" + describe_changes(changes, diff_text, notes)
    return Prompt(COMMIT_SYSTEM, user)


def build_pr_prompt(changes: GitChanges, diff_text: str, notes: list[str], base: str) -> Prompt:
    user = (f"아래 변경 사항으로 '{base}' 브랜치에 올릴 PR 제목과 본문을 작성하세요.\n\n"
            + describe_changes(changes, diff_text, notes))
    return Prompt(PR_SYSTEM, user)


def build_retry_prompt(prompt: Prompt, previous: str, issues: list[str]) -> Prompt:
    """규칙을 어긴 응답과 어긴 내용을 함께 보내 한 번 더 쓰게 한다."""
    problems = "\n".join(f"- {issue}" for issue in issues)
    user = (f"{prompt.user}\n\n[이전 응답]\n{previous}\n\n"
            f"[수정 요청]\n이전 응답이 다음 규칙을 어겼습니다:\n{problems}\n"
            "같은 변경 사항으로, 규칙을 모두 지켜 처음부터 다시 작성하세요.")
    return Prompt(prompt.system, user)
