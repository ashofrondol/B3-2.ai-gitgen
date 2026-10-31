from __future__ import annotations

import pytest

import app.cli as cli
from app.ai_client import AIClientError, Completion

GOOD_COMMIT = "feat(app): 인사 함수 추가\n\n- app.py 에 hello() 추가"
GOOD_PR = ("Title: feat: 인사 함수 추가\n## Why\n- 예제가 없었음\n## What\n- app.py 추가\n"
           "## How to Test\n- `python app.py` 실행")
LONG_COMMIT = "feat: " + "아주 긴 제목 " * 15


@pytest.fixture
def fake_ai(monkeypatch):
    """AIClient 를 가짜로 바꾼다. replies 에 넣은 순서대로 응답한다 (예외 객체면 raise)."""
    state = {"replies": [], "calls": [], "init": None}

    class FakeClient:
        def __init__(self, api_key, base_url, model, temperature, max_tokens, timeout=60.0):
            state["init"] = {"model": model, "temperature": temperature, "max_tokens": max_tokens}

        def complete(self, system, user):
            state["calls"].append({"system": system, "user": user})
            reply = state["replies"].pop(0)
            if isinstance(reply, Exception):
                raise reply
            return Completion(reply, "stop", 100, 20)

    monkeypatch.setattr(cli, "AIClient", FakeClient)
    monkeypatch.setenv("API_KEY", "dummy")
    return state


@pytest.fixture
def staged(git_repo, git):
    (git_repo / "app.py").write_text("def hello():\n    return 'hi'\n", encoding="utf-8")
    git("add", "app.py")
    return git_repo


def test_commit_prints_block(staged, fake_ai, capsys):
    fake_ai["replies"] = [GOOD_COMMIT]
    assert cli.main(["commit"]) == 0
    out, err = capsys.readouterr()
    assert out == f"--- Commit Message ---\n{GOOD_COMMIT}\n{cli.LINE}\n"
    assert "Git status 수집 완료: 1개 파일" in err
    assert "AI API 호출 횟수: 1회" in err
    assert "+    return 'hi'" in fake_ai["calls"][0]["user"]


def test_pr_prints_title_and_sections(staged, fake_ai, capsys):
    fake_ai["replies"] = [GOOD_PR]
    assert cli.main(["pr"]) == 0
    out, _ = capsys.readouterr()
    assert out.startswith("--- PR Title ---\nfeat: 인사 함수 추가\n\n--- PR Body ---\n## Why\n")
    assert "## What\n- app.py 추가" in out and "## How to Test" in out


def test_missing_key_stops_before_git(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)  # Git 저장소가 아니어도 키 오류가 먼저 나온다
    monkeypatch.delenv("API_KEY", raising=False)
    assert cli.main(["commit"]) == 2
    err = capsys.readouterr().err
    assert "[ERROR] API_KEY 환경변수가 설정되지 않았습니다." in err
    assert "export API_KEY" in err


def test_no_changes_skips_api(git_repo, fake_ai, capsys):
    assert cli.main(["commit"]) == 0
    assert "변경 사항이 없습니다. 커밋 메시지를 생성하지 않고 종료합니다." in capsys.readouterr().err
    assert fake_ai["calls"] == []


def test_outside_repo_root(staged, fake_ai, monkeypatch, capsys):
    (staged / "sub").mkdir()
    monkeypatch.chdir(staged / "sub")
    assert cli.main(["commit"]) == 1
    assert "프로젝트 루트" in capsys.readouterr().err


def test_options_reach_client(staged, fake_ai):
    fake_ai["replies"] = [GOOD_COMMIT]
    cli.main(["commit", "--model", "m-x", "--temperature", "0.9", "--max-tokens", "50"])
    assert fake_ai["init"] == {"model": "m-x", "temperature": 0.9, "max_tokens": 50}


def test_defaults_per_command(staged, fake_ai):
    fake_ai["replies"] = [GOOD_PR]
    cli.main(["pr"])
    assert fake_ai["init"]["temperature"] == 0.4 and fake_ai["init"]["max_tokens"] == 1000


@pytest.mark.parametrize("argv", [
    ["commit", "--temperature", "3"], ["commit", "--max-tokens", "0"], ["pr", "--max-lines", "0"],
])
def test_invalid_options(argv):
    with pytest.raises(SystemExit) as exc:
        cli.parse_args(argv)
    assert exc.value.code == 2


def test_retry_once_on_violation(staged, fake_ai, capsys):
    fake_ai["replies"] = [LONG_COMMIT, GOOD_COMMIT]
    assert cli.main(["commit"]) == 0
    out, err = capsys.readouterr()
    assert len(fake_ai["calls"]) == 2
    assert "[수정 요청]" in fake_ai["calls"][1]["user"]
    assert "1회 다시 생성합니다" in err and "AI API 호출 횟수: 2회" in err
    assert GOOD_COMMIT in out


def test_no_retry_enforces_rules(staged, fake_ai, capsys):
    fake_ai["replies"] = [LONG_COMMIT]
    assert cli.main(["commit", "--no-retry"]) == 0
    out, err = capsys.readouterr()
    title = out.splitlines()[1]
    assert len(fake_ai["calls"]) == 1 and len(title) <= 72
    assert "후처리로 보정했습니다" in err


def test_api_error_is_reported(staged, fake_ai, capsys):
    fake_ai["replies"] = [AIClientError("인증 실패(HTTP 401): bad key", hint="API_KEY 값과 권한을 확인하세요.")]
    assert cli.main(["commit"]) == 1
    err = capsys.readouterr().err
    assert "[ERROR] 인증 실패(HTTP 401)" in err and "API_KEY 값과 권한" in err
    assert "AI API 호출 횟수: 1회" in err


def test_dry_run_needs_no_key(staged, monkeypatch, capsys):
    monkeypatch.delenv("API_KEY", raising=False)
    assert cli.main(["commit", "--dry-run", "--safe-mode"]) == 0
    out, err = capsys.readouterr()
    assert out.startswith("--- System Prompt ---") and "--- User Prompt ---" in out
    assert "호출 0회" in err and "안전 모드: 마스킹 0건" in err
