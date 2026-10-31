"""AI 응답을 다듬고 형식 규칙을 검사한다.

순서: ① 후처리로 고칠 수 있는 것(코드 블록·라벨·불릿 기호·헤더 표기)은 바로 고친다.
② 그래도 남는 규칙 위반은 issues 로 돌려준다 → cli 가 1회 다시 생성한다.
③ 다시 만든 뒤에도 남으면 enforce_* 가 규칙을 강제로 맞춘다(자르기·자리표시).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.config import COMMIT_TITLE_MAX, COMMIT_TITLE_RECOMMENDED, PR_TITLE_MAX

SECTIONS = ("Why", "What", "How to Test")
PLACEHOLDER = "- (AI 가 채우지 못했습니다. 직접 작성하세요)"

_FENCE = re.compile(r"^\s*```[\w-]*\s*$")
_THINK = re.compile(r"<think>.*?</think>", re.S)
_BULLET = re.compile(r"^(?:[-*•·+]\s+|\d+[.)]\s+)")
_LABEL = re.compile(r"^(?:pr\s*title|title|제목|commit\s*message|커밋\s*메시지)\s*[:：]\s*", re.I)
_TYPE_PREFIX = re.compile(r"^(feat|fix|docs|style|refactor|test|chore|perf|build|ci)(\([^)]*\))?!?: ")
_SECTION = re.compile(
    r"^\s*(?:#{1,6}\s*)?(?:\*\*)?\s*(why|what|how\s+to\s+test)\s*(?:\([^)]*\))?\s*(?:\*\*)?\s*"
    r"(?::\s*(?:\*\*)?\s*(.*)|$)",
    re.I,
)


@dataclass
class CommitMessage:
    title: str
    body: list[str]

    def render(self) -> str:
        return self.title + ("\n\n" + "\n".join(self.body) if self.body else "")


@dataclass
class PRDraft:
    title: str
    sections: dict[str, list[str]]

    def render_body(self) -> str:
        return "\n\n".join(f"## {name}\n" + "\n".join(self.sections[name]) for name in SECTIONS)


@dataclass
class FormatResult:
    value: CommitMessage | PRDraft
    issues: list[str]    # 규칙 위반 → 다시 생성할 이유
    warnings: list[str]  # 참고용 경고 (권장 길이 초과 등)


def strip_noise(text: str) -> str:
    """추론 블록과 코드 블록 표시줄을 지운다."""
    text = _THINK.sub("", text.replace("\r\n", "\n"))
    return "\n".join(line for line in text.split("\n") if not _FENCE.match(line)).strip()


def to_bullet(line: str) -> str | None:
    """여러 불릿 기호를 "- " 로 통일한다. 기호가 없는 문장도 불릿으로 만든다."""
    text = _BULLET.sub("", line.strip()).strip()
    return f"- {text}" if text else None


def clean_title(line: str) -> str:
    title = line.strip().lstrip("#").strip()
    title = _LABEL.sub("", title)
    title = title.strip("*`\"' ").strip()
    return title.rstrip(".。").rstrip()


def fit_title(title: str, max_len: int) -> str:
    if len(title) <= max_len:
        return title
    cut = title[:max_len]
    space = cut.rfind(" ")
    if space > max_len * 0.6:
        cut = cut[:space]
    return cut.rstrip(" ,.:;-")


def validate_commit(msg: CommitMessage) -> tuple[list[str], list[str]]:
    issues: list[str] = []
    warnings: list[str] = []
    n = len(msg.title)
    if not msg.title:
        issues.append("커밋 제목이 비어 있습니다.")
    elif n > COMMIT_TITLE_MAX:
        issues.append(f"커밋 제목이 {n}자입니다(최대 {COMMIT_TITLE_MAX}자).")
    elif n > COMMIT_TITLE_RECOMMENDED:
        warnings.append(f"커밋 제목이 {n}자입니다(권장 {COMMIT_TITLE_RECOMMENDED}자 이내).")
    if msg.title and not _TYPE_PREFIX.match(msg.title):
        warnings.append("커밋 제목에 type 접두어(feat:, fix: 등)가 없습니다.")
    return issues, warnings


def format_commit(raw: str) -> FormatResult:
    lines = [line for line in strip_noise(raw).split("\n") if line.strip()]
    title = clean_title(lines[0]) if lines else ""
    body = [b for b in (to_bullet(line) for line in lines[1:]) if b]
    msg = CommitMessage(title, body)
    issues, warnings = validate_commit(msg)
    return FormatResult(msg, issues, warnings)


def enforce_commit(msg: CommitMessage) -> tuple[CommitMessage, list[str]]:
    notes: list[str] = []
    title = msg.title
    if not title:
        title = "chore: 변경 사항 정리"
        notes.append("커밋 제목이 비어 있어 기본 제목을 넣었습니다. 직접 고치세요.")
    elif len(title) > COMMIT_TITLE_MAX:
        title = fit_title(title, COMMIT_TITLE_MAX)
        notes.append(f"커밋 제목을 {COMMIT_TITLE_MAX}자 이내로 잘랐습니다.")
    return CommitMessage(title, msg.body), notes


def match_section(line: str) -> tuple[str, str] | None:
    """섹션 헤더면 (표준 이름, 헤더 뒤 남은 글) 을 돌려준다."""
    if _BULLET.match(line.strip()):
        return None
    m = _SECTION.match(line)
    if not m:
        return None
    key = re.sub(r"\s+", " ", m.group(1).lower())
    name = {"why": "Why", "what": "What", "how to test": "How to Test"}[key]
    rest = (m.group(2) or "").strip().strip("*").strip()
    return name, rest


def format_pr(raw: str) -> FormatResult:
    sections: dict[str, list[str]] = {name: [] for name in SECTIONS}
    title = ""
    first_line = ""
    current: str | None = None
    for line in strip_noise(raw).split("\n"):
        if not line.strip():
            continue
        header = match_section(line)
        if header:
            current, rest = header
            if rest and (bullet := to_bullet(rest)):
                sections[current].append(bullet)
        elif current:
            if bullet := to_bullet(line):
                sections[current].append(bullet)
        elif not title and _LABEL.match(line.strip().lstrip("#").strip()):
            title = clean_title(line)
        elif not first_line:
            first_line = line
    title = title or clean_title(first_line)

    issues: list[str] = []
    if not title:
        issues.append("PR 제목이 비어 있습니다.")
    elif len(title) > PR_TITLE_MAX:
        issues.append(f"PR 제목이 {len(title)}자입니다(최대 {PR_TITLE_MAX}자).")
    issues += [f"'## {name}' 섹션에 불릿이 없습니다." for name in SECTIONS if not sections[name]]
    return FormatResult(PRDraft(title, sections), issues, [])


def enforce_pr(draft: PRDraft) -> tuple[PRDraft, list[str]]:
    notes: list[str] = []
    title = draft.title
    if not title:
        title = "chore: 변경 사항 반영"
        notes.append("PR 제목이 비어 있어 기본 제목을 넣었습니다. 직접 고치세요.")
    elif len(title) > PR_TITLE_MAX:
        title = fit_title(title, PR_TITLE_MAX)
        notes.append(f"PR 제목을 {PR_TITLE_MAX}자 이내로 잘랐습니다.")
    sections = {name: list(bullets) for name, bullets in draft.sections.items()}
    for name in SECTIONS:
        if not sections[name]:
            sections[name] = [PLACEHOLDER]
            notes.append(f"'## {name}' 섹션이 비어 있어 자리표시 불릿을 넣었습니다.")
    return PRDraft(title, sections), notes
