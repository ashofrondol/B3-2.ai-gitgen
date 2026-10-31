"""공통 픽스처: 임시 Git 저장소."""

from __future__ import annotations

import subprocess

import pytest


def _git(*args: str) -> str:
    proc = subprocess.run(["git", *args], capture_output=True, text=True, check=True)
    return proc.stdout


@pytest.fixture(autouse=True)
def _ignore_tool_env(monkeypatch, tmp_path):
    """개발자가 도구 폴더에 둔 실제 .env(키)를 테스트가 읽지 않게 한다."""
    import app.config

    monkeypatch.setattr(app.config, "TOOL_ENV", str(tmp_path / "no-such.env"))


@pytest.fixture
def git():
    """현재 디렉터리에서 git 을 실행하는 함수."""
    return _git


@pytest.fixture
def git_repo(tmp_path, monkeypatch):
    """README.md 하나가 커밋된 main 브랜치 저장소로 이동한다."""
    monkeypatch.chdir(tmp_path)
    for name in ("API_KEY", "BASE_URL", "MODEL"):
        monkeypatch.delenv(name, raising=False)
    _git("init", "-q", "-b", "main")
    _git("config", "user.name", "Test")
    _git("config", "user.email", "test@example.com")
    (tmp_path / "README.md").write_text("# demo\n", encoding="utf-8")
    _git("add", "README.md")
    _git("commit", "-q", "-m", "init")
    return tmp_path
