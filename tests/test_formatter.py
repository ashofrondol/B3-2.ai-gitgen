from __future__ import annotations

import pytest

from app.formatter import (
    PLACEHOLDER,
    enforce_commit,
    enforce_pr,
    format_commit,
    format_pr,
    match_section,
)


def test_commit_strips_fences_think_and_label():
    raw = "<think>생각 중</think>\n```text\nCommit message: feat: 추가.\n\n* a\n1. b\nplain\n```"
    result = format_commit(raw)
    assert result.value.title == "feat: 추가"
    assert result.value.body == ["- a", "- b", "- plain"]
    assert result.issues == []
    assert result.value.render() == "feat: 추가\n\n- a\n- b\n- plain"


def test_commit_too_long_is_issue_and_enforce_trims():
    title = "feat: " + "아주 긴 제목 " * 12
    result = format_commit(title)
    assert any("최대 72자" in issue for issue in result.issues)
    fixed, notes = enforce_commit(result.value)
    assert len(fixed.title) <= 72 and not fixed.title.endswith(" ")
    assert notes and "72자" in notes[0]


def test_commit_recommended_length_and_prefix_are_warnings():
    result = format_commit("feat: " + "가" * 54)  # 60자
    assert result.issues == []
    assert any("권장" in w for w in result.warnings)
    result = format_commit("README 수정")
    assert any("접두어" in w for w in result.warnings)


def test_empty_commit():
    result = format_commit("```\n```")
    assert result.issues == ["커밋 제목이 비어 있습니다."]
    fixed, notes = enforce_commit(result.value)
    assert fixed.title.startswith("chore:") and notes


PR_RAW = """Title: **feat: PR 초안 생성 추가**
### why
* 리뷰 설명을 매번 손으로 쓰기 번거로움
**What**
• cli.py 에 pr 명령 추가
- formatter.py 에서 섹션 검사
How to test:
1. `python main.py pr` 실행
"""


def test_pr_normalizes_headers_and_bullets():
    result = format_pr(PR_RAW)
    draft = result.value
    assert result.issues == []
    assert draft.title == "feat: PR 초안 생성 추가"
    assert draft.render_body() == (
        "## Why\n- 리뷰 설명을 매번 손으로 쓰기 번거로움\n\n"
        "## What\n- cli.py 에 pr 명령 추가\n- formatter.py 에서 섹션 검사\n\n"
        "## How to Test\n- `python main.py pr` 실행"
    )


def test_pr_header_rest_becomes_bullet_and_title_from_first_line():
    raw = "fix: 버그 수정\n## Why: 오류가 남\n## What\n- a\n## How to Test\n- b"
    result = format_pr(raw)
    assert result.value.title == "fix: 버그 수정"
    assert result.value.sections["Why"] == ["- 오류가 남"]


def test_pr_missing_section_and_enforce():
    raw = "Title: " + "가" * 100 + "\n## Why\n- a\n## What\n- b"
    result = format_pr(raw)
    assert "'## How to Test' 섹션에 불릿이 없습니다." in result.issues
    assert any("최대 80자" in issue for issue in result.issues)
    fixed, notes = enforce_pr(result.value)
    assert len(fixed.title) <= 80
    assert fixed.sections["How to Test"] == [PLACEHOLDER]
    assert len(notes) == 2


@pytest.mark.parametrize("line, expected", [
    ("## Why", ("Why", "")),
    ("###what", ("What", "")),
    ("**How to Test**", ("How to Test", "")),
    ("**Why:**", ("Why", "")),
    ("Why: 배경 설명", ("Why", "배경 설명")),
    ("Why(변경 배경)", ("Why", "")),
    ("## How To Test", ("How to Test", "")),
    ("Whatever happens next", None),
    ("What is new here", None),
    ("- why not", None),
])
def test_match_section(line, expected):
    assert match_section(line) == expected
