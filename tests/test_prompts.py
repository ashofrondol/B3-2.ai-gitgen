from __future__ import annotations

from app.git_manager import FileChange, GitChanges
from app.prompts import (
    COMMIT_SYSTEM,
    PR_SYSTEM,
    build_commit_prompt,
    build_pr_prompt,
    build_retry_prompt,
)

CHANGES = GitChanges(
    branch="feature/x",
    files=[FileChange("M", "app/cli.py"), FileChange("?", "new.txt")],
    diff="diff --git a/app/cli.py b/app/cli.py\n+print(1)\n",
    source="스테이징된 변경 (git diff --cached)",
)


def test_system_prompts_state_rules():
    assert "72자" in COMMIT_SYSTEM and "feat" in COMMIT_SYSTEM
    for header in ("## Why", "## What", "## How to Test"):
        assert header in PR_SYSTEM
    assert "80자" in PR_SYSTEM


def test_commit_prompt_contains_context():
    prompt = build_commit_prompt(CHANGES, CHANGES.diff, ["민감정보는 가렸습니다"])
    assert prompt.system == COMMIT_SYSTEM
    assert "브랜치: feature/x" in prompt.user
    assert "- [수정] app/cli.py" in prompt.user
    assert "- [새 파일(미추적)] new.txt" in prompt.user
    assert "참고:\n- 민감정보는 가렸습니다" in prompt.user
    assert "```diff\ndiff --git" in prompt.user


def test_pr_prompt_names_base_and_handles_empty_diff():
    prompt = build_pr_prompt(CHANGES, "", [], base="develop")
    assert "'develop' 브랜치" in prompt.user
    assert "(diff 없음" in prompt.user
    assert "참고:" not in prompt.user


def test_retry_prompt_lists_issues():
    base = build_commit_prompt(CHANGES, CHANGES.diff, [])
    retry = build_retry_prompt(base, "너무 긴 제목", ["커밋 제목이 90자입니다(최대 72자)."])
    assert retry.system == base.system
    assert retry.user.startswith(base.user)
    assert "[이전 응답]\n너무 긴 제목" in retry.user
    assert "- 커밋 제목이 90자입니다(최대 72자)." in retry.user
