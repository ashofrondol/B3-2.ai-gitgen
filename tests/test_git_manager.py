from __future__ import annotations

import pytest

from app.git_manager import (
    GitError,
    collect_commit_changes,
    collect_pr_changes,
    ensure_repo_root,
)


def test_clean_repo_is_empty(git_repo):
    assert collect_commit_changes().is_empty


def test_staged_change_uses_cached_diff(git_repo, git):
    (git_repo / "README.md").write_text("# demo\nhello\n", encoding="utf-8")
    (git_repo / "notes.txt").write_text("not staged\n", encoding="utf-8")
    git("add", "README.md")

    changes = collect_commit_changes()

    assert "--cached" in changes.source
    assert [f.path for f in changes.files] == ["README.md"]
    assert "+hello" in changes.diff
    assert changes.diff_line_count > 0


def test_unstaged_change_uses_working_tree(git_repo):
    (git_repo / "README.md").write_text("# demo\nedited\n", encoding="utf-8")

    changes = collect_commit_changes()

    assert "작업 트리" in changes.source
    assert "+edited" in changes.diff
    assert changes.files[0].status == "M"


def test_untracked_file_is_listed(git_repo):
    (git_repo / "new.py").write_text("print(1)\n", encoding="utf-8")

    changes = collect_commit_changes()

    assert not changes.is_empty
    assert changes.files[0].status == "?"
    assert changes.files[0].label == "새 파일(미추적)"


def test_rename_keeps_new_path(git_repo, git):
    git("mv", "README.md", "GUIDE.md")

    changes = collect_commit_changes()

    assert [(f.status, f.path) for f in changes.files] == [("R", "GUIDE.md")]


def test_not_a_repo(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(GitError, match="Git 저장소가 아닙니다"):
        ensure_repo_root()


def test_subdirectory_is_rejected(git_repo, monkeypatch):
    sub = git_repo / "sub"
    sub.mkdir()
    monkeypatch.chdir(sub)
    with pytest.raises(GitError, match="프로젝트 루트"):
        ensure_repo_root()


def test_pr_on_feature_branch_compares_with_base(git_repo, git):
    git("switch", "-q", "-c", "feature/x")
    (git_repo / "app.py").write_text("print('x')\n", encoding="utf-8")
    git("add", "app.py")
    git("commit", "-q", "-m", "add app")

    changes = collect_pr_changes("main")

    assert changes.branch == "feature/x"
    assert "main...HEAD" in changes.source
    assert [(f.status, f.path) for f in changes.files] == [("A", "app.py")]
    assert "+print('x')" in changes.diff


def test_pr_on_base_uses_uncommitted(git_repo):
    (git_repo / "README.md").write_text("# demo\nwip\n", encoding="utf-8")

    changes = collect_pr_changes("main")

    assert "git diff HEAD" in changes.source
    assert "+wip" in changes.diff
