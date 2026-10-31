"""git status / git diff 결과를 모아 프로그램 입력으로 만든다.

AI 호출과 분리해 두면 Git 쪽은 실제 저장소로, AI 쪽은 가짜 응답으로 따로 시험할 수 있다.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass

STATUS_LABELS = {
    "M": "수정",
    "A": "추가",
    "D": "삭제",
    "R": "이름 변경",
    "C": "복사",
    "U": "충돌",
    "?": "새 파일(미추적)",
}


class GitError(Exception):
    """Git 명령 실패나 실행 위치 문제."""


@dataclass(frozen=True)
class FileChange:
    status: str  # 한 글자: M A D R C U ?
    path: str

    @property
    def label(self) -> str:
        return STATUS_LABELS.get(self.status, self.status)


@dataclass(frozen=True)
class GitChanges:
    branch: str
    files: list[FileChange]
    diff: str
    source: str  # 어떤 범위를 diff 했는지 사람이 읽는 설명

    @property
    def diff_line_count(self) -> int:
        return len(self.diff.splitlines())

    @property
    def is_empty(self) -> bool:
        return not self.files and not self.diff.strip()


def run_git(args: list[str], cwd: str | None = None) -> str:
    """git 을 실행하고 stdout 을 돌려준다. 실패하면 stderr 를 담아 GitError."""
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except FileNotFoundError as exc:
        raise GitError("git 명령을 찾을 수 없습니다. Git 이 설치되어 있는지 확인하세요.") from exc
    if proc.returncode != 0:
        raise GitError(f"git {' '.join(args)} 실패: {proc.stderr.strip()}")
    return proc.stdout


def ensure_repo_root(cwd: str | None = None) -> str:
    """현재 위치가 Git 저장소의 루트인지 확인한다."""
    try:
        top = run_git(["rev-parse", "--show-toplevel"], cwd).strip()
    except GitError as exc:
        raise GitError("Git 저장소가 아닙니다. git init 된 프로젝트 루트에서 실행하세요.") from exc
    here = cwd or os.getcwd()
    if os.path.realpath(top) != os.path.realpath(here):
        raise GitError(f"프로젝트 루트에서 실행하세요: {top}")
    return top


def has_ref(ref: str, cwd: str | None = None) -> bool:
    try:
        run_git(["rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"], cwd)
    except GitError:
        return False
    return True


def current_branch(cwd: str | None = None) -> str:
    # symbolic-ref 는 첫 커밋 전에도 브랜치 이름을 알려 준다.
    try:
        return run_git(["symbolic-ref", "--short", "HEAD"], cwd).strip()
    except GitError:
        return "(detached HEAD)"


def collect_status(cwd: str | None = None) -> list[FileChange]:
    """git status --porcelain -z 를 파일 목록으로 바꾼다."""
    out = run_git(["status", "--porcelain=v1", "-z", "--untracked-files=all"], cwd)
    entries = out.split("\0")
    files: list[FileChange] = []
    i = 0
    while i < len(entries):
        entry = entries[i]
        i += 1
        if len(entry) < 4:
            continue
        x, y, path = entry[0], entry[1], entry[3:]
        if "R" in (x, y) or "C" in (x, y):
            i += 1  # 다음 항목은 원래 경로라 건너뛴다
        status = "?" if x == "?" else (x if x != " " else y)
        files.append(FileChange(status, path))
    return files


def staged_paths(cwd: str | None = None) -> set[str]:
    out = run_git(["diff", "--cached", "--name-only", "-z"], cwd)
    return {p for p in out.split("\0") if p}


def _parse_name_status(out: str) -> list[FileChange]:
    """git diff --name-status -z 출력: 상태\\0경로\\0 (R/C 는 옛경로\\0새경로\\0)."""
    parts = [p for p in out.split("\0") if p]
    files: list[FileChange] = []
    i = 0
    while i < len(parts):
        status = parts[i][0]
        if status in ("R", "C"):
            files.append(FileChange(status, parts[i + 2]))
            i += 3
        else:
            files.append(FileChange(status, parts[i + 1]))
            i += 2
    return files


def collect_commit_changes(cwd: str | None = None) -> GitChanges:
    """커밋용: 스테이징된 변경을 우선 쓰고, 없으면 작업 트리 변경을 쓴다."""
    branch = current_branch(cwd)
    status = collect_status(cwd)
    staged = run_git(["diff", "--cached", "--no-color"], cwd)
    if staged.strip():
        paths = staged_paths(cwd)
        files = [f for f in status if f.path in paths]
        return GitChanges(branch, files, staged, "스테이징된 변경 (git diff --cached)")
    diff = run_git(["diff", "--no-color"], cwd)
    return GitChanges(branch, status, diff, "작업 트리 변경 (git diff, 스테이징된 변경 없음)")


def collect_pr_changes(base: str = "main", cwd: str | None = None) -> GitChanges:
    """PR용: 기준 브랜치와 비교하고, 기준 브랜치 위라면 커밋되지 않은 변경을 쓴다."""
    branch = current_branch(cwd)
    if branch != base and has_ref(base, cwd):
        diff = run_git(["diff", "--no-color", f"{base}...HEAD"], cwd)
        names = run_git(["diff", "--name-status", "-z", f"{base}...HEAD"], cwd)
        return GitChanges(branch, _parse_name_status(names), diff, f"브랜치 비교 (git diff {base}...HEAD)")
    if has_ref("HEAD", cwd):
        diff = run_git(["diff", "--no-color", "HEAD"], cwd)
    else:
        diff = run_git(["diff", "--cached", "--no-color"], cwd)
    return GitChanges(branch, collect_status(cwd), diff, "커밋되지 않은 변경 (git diff HEAD)")
