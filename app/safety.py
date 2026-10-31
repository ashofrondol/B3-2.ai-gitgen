"""diff 를 외부 AI 로 보내기 전의 안전장치.

안전 모드(--safe-mode)는 세 가지를 한다.
1. 민감 파일(.env, 키 파일 등)의 diff 는 통째로 뺀다.
2. 키·토큰·이메일·전화번호 같은 패턴을 [MASKED:...] 로 가린다.
3. 최대 N개 파일, N줄까지만 보낸다.
정규식은 알려진 형태만 잡는다. 보내기 전에 사람이 diff 를 보는 일을 대신하지 않는다.
"""

from __future__ import annotations

import fnmatch
import posixpath
import re
from dataclasses import dataclass, field

from app.config import MAX_DIFF_CHARS, SAFE_MAX_FILES, SAFE_MAX_LINES

SENSITIVE_FILE_GLOBS = (
    ".env", ".env.*", "*.pem", "*.key", "*.p12", "*.pfx", "id_rsa*",
    "id_ed25519*", "*.keystore", "credentials*.json", "secret.key",
)
ALLOWED_FILES = (".env.example",)  # 값이 빈 템플릿은 보내도 된다

_SECRET_NAME = r"\w*(?:api[_-]?key|secret|token|passw(?:or)?d)\w*"

# (이름, 정규식, 바꿀 문자열) — 위에서부터 차례로 적용한다.
MASK_RULES: list[tuple[str, re.Pattern[str], str]] = [
    ("PRIVATE_KEY", re.compile(
        r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S),
        "[MASKED:PRIVATE_KEY]"),
    ("API_KEY", re.compile(
        r"sk-ant-[A-Za-z0-9_\-]{20,}|sk-(?:proj-)?[A-Za-z0-9_\-]{20,}|AKIA[0-9A-Z]{16}"
        r"|gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{22,}|AIza[0-9A-Za-z_\-]{35}"
        r"|xox[baprs]-[A-Za-z0-9\-]{10,}"),
        "[MASKED:API_KEY]"),
    ("JWT", re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}"),
        "[MASKED:JWT]"),
    # 비밀처럼 보이는 이름 = "값" — 이름은 두고 값만 가린다. os.getenv("...") 같은 코드는 그대로.
    # (?!\[MASKED) : 앞 규칙이 이미 가린 값을 두 번 세지 않는다.
    ("SECRET", re.compile(
        rf"(?i)\b({_SECRET_NAME})([\"']?\s*[:=]\s*)([\"'])(?!\[MASKED)([^\"'\s]{{6,}})\3"),
        r"\1\2\3[MASKED:SECRET]\3"),
    # .env 형식: 줄 맨 앞의 NAME=value (diff 접두어 + - 공백 허용). = 양옆에 공백이 없고
    # 값 뒤가 공백·주석·줄끝이어야 한다 → 파이썬 코드 `api_key = os.getenv(...)` 는 걸리지 않는다.
    ("SECRET", re.compile(
        rf"(?im)^([+\- ]?(?:export\s+)?{_SECRET_NAME}=)(?!\[MASKED)([^\s\"'#()]{{6,}})(?=\s|#|$)"),
        r"\1[MASKED:SECRET]"),
    ("EMAIL", re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}"), "[MASKED:EMAIL]"),
    ("PHONE", re.compile(r"\b01[016789][-. ]?\d{3,4}[-. ]?\d{4}\b"), "[MASKED:PHONE]"),
    ("RRN", re.compile(r"\b\d{6}-[1-4]\d{6}\b"), "[MASKED:RRN]"),
]


@dataclass
class SafetyReport:
    masked: dict[str, int] = field(default_factory=dict)
    excluded_files: list[str] = field(default_factory=list)
    original_files: int = 0
    sent_files: int = 0
    original_lines: int = 0
    sent_lines: int = 0
    truncated: bool = False

    @property
    def masked_total(self) -> int:
        return sum(self.masked.values())


def split_sections(diff: str) -> list[tuple[str, str]]:
    """diff 를 파일별 (경로, 텍스트) 로 나눈다. 이어 붙이면 원문과 같다."""
    sections: list[tuple[str, list[str]]] = []
    for line in diff.splitlines(keepends=True):
        if line.startswith("diff --git "):
            path = line.rstrip("\n").rsplit(" b/", 1)[-1]
            sections.append((path, [line]))
        elif sections:
            sections[-1][1].append(line)
        else:
            sections.append(("", [line]))
    return [(path, "".join(lines)) for path, lines in sections
            if path or "".join(lines).strip()]


def is_sensitive_path(path: str) -> bool:
    name = posixpath.basename(path)
    if name in ALLOWED_FILES:
        return False
    return any(fnmatch.fnmatch(name, pattern) for pattern in SENSITIVE_FILE_GLOBS)


def mask_text(text: str) -> tuple[str, dict[str, int]]:
    counts: dict[str, int] = {}
    for name, pattern, repl in MASK_RULES:
        text, n = pattern.subn(repl, text)
        if n:
            counts[name] = counts.get(name, 0) + n
    return text, counts


def count_sensitive(text: str) -> int:
    return sum(mask_text(text)[1].values())


def apply_safe_mode(diff: str, max_files: int = SAFE_MAX_FILES,
                    max_lines: int = SAFE_MAX_LINES) -> tuple[str, SafetyReport]:
    sections = split_sections(diff)
    report = SafetyReport(original_files=sum(1 for p, _ in sections if p),
                          original_lines=len(diff.splitlines()))
    kept: list[str] = []
    for path, text in sections:
        if path and is_sensitive_path(path):
            report.excluded_files.append(path)
            continue
        masked, counts = mask_text(text)
        for name, n in counts.items():
            report.masked[name] = report.masked.get(name, 0) + n
        kept.append(masked)

    out: list[str] = []
    used_lines = 0
    for index, text in enumerate(kept):
        lines = text.splitlines(keepends=True)
        room = max_lines - used_lines
        if index >= max_files or room <= 0:
            report.truncated = True
            break
        out.extend(lines[:room])
        used_lines += min(len(lines), room)
        report.sent_files += 1
        if len(lines) > room:
            report.truncated = True
            break
    if report.truncated:
        omitted = sum(len(t.splitlines()) for t in kept) - used_lines
        if out and not out[-1].endswith("\n"):
            out[-1] += "\n"
        out.append(f"... (안전 모드: 이후 {omitted}줄 생략)\n")
    report.sent_lines = used_lines
    return "".join(out), report


def cap_diff(diff: str, max_chars: int = MAX_DIFF_CHARS) -> tuple[str, bool]:
    """너무 긴 diff 는 줄 경계에서 자른다. (잘린 텍스트, 잘렸는지)"""
    if len(diff) <= max_chars:
        return diff, False
    cut = diff.rfind("\n", 0, max_chars)
    cut = cut + 1 if cut > 0 else max_chars
    omitted = len(diff) - cut
    return diff[:cut] + f"... (diff 가 길어 이후 {omitted}자 생략)\n", True
