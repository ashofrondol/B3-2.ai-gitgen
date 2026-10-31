from __future__ import annotations

import pytest
import requests

from app.ai_client import AIClient, AIClientError
from app.config import DEFAULT_BASE_URL, read_api_settings

KEY = "test-key-123456"


class FakeResponse:
    def __init__(self, status_code=200, body=None, text=""):
        self.status_code = status_code
        self._body = body
        self.text = text

    def json(self):
        if self._body is None:
            raise ValueError("no json")
        return self._body


class FakeSession:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def post(self, url, headers=None, json=None, timeout=None):
        self.calls.append({"url": url, "headers": headers, "json": json, "timeout": timeout})
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def ok(content="feat: 추가", finish_reason="stop", usage=None):
    body = {"choices": [{"message": {"content": content}, "finish_reason": finish_reason}]}
    if usage:
        body["usage"] = usage
    return FakeResponse(200, body)


def make(result, **kw):
    session = FakeSession(result)
    client = AIClient(KEY, kw.pop("base_url", "https://api.example.com/v1/"), "m-1", 0.3, 123,
                      timeout=5, session=session)
    return client, session


def test_missing_key():
    with pytest.raises(AIClientError) as err:
        AIClient(None, DEFAULT_BASE_URL, "m", 0.2, 10)
    assert "API_KEY" in err.value.message and err.value.hint


def test_request_shape():
    client, session = make(ok())
    client.complete("SYS", "USER")
    call = session.calls[0]
    assert call["url"] == "https://api.example.com/v1/chat/completions"
    assert call["headers"]["Authorization"] == f"Bearer {KEY}"
    assert call["json"]["model"] == "m-1"
    assert call["json"]["temperature"] == 0.3 and call["json"]["max_tokens"] == 123
    assert [m["role"] for m in call["json"]["messages"]] == ["system", "user"]
    assert call["timeout"] == 5


def test_success_parses_text_and_usage():
    client, _ = make(ok("  feat: x  ", usage={"prompt_tokens": 10, "completion_tokens": 3}))
    result = client.complete("s", "u")
    assert result.text == "feat: x"
    assert (result.prompt_tokens, result.completion_tokens) == (10, 3)
    assert not result.truncated


def test_truncated_and_content_parts():
    client, _ = make(ok([{"type": "text", "text": "a"}, {"type": "text", "text": "b"}], "length"))
    result = client.complete("s", "u")
    assert result.text == "ab" and result.truncated


def test_auth_error_hides_key():
    body = {"error": {"message": f"Incorrect API key provided: {KEY}"}}
    client, _ = make(FakeResponse(401, body))
    with pytest.raises(AIClientError) as err:
        client.complete("s", "u")
    assert "인증 실패(HTTP 401)" in err.value.message
    assert KEY not in err.value.message and "***" in err.value.message


@pytest.mark.parametrize("code, words", [
    (404, "찾을 수 없습니다"), (429, "요청 한도 초과"), (500, "서버 오류"), (418, "요청 실패"),
])
def test_http_errors(code, words):
    client, _ = make(FakeResponse(code, None, text="oops"))
    with pytest.raises(AIClientError) as err:
        client.complete("s", "u")
    assert words in err.value.message and "oops" in err.value.message


@pytest.mark.parametrize("exc, words", [
    (requests.exceptions.Timeout(), "시간 초과"),
    (requests.exceptions.ConnectionError(), "연결하지 못했습니다"),
])
def test_network_errors(exc, words):
    client, _ = make(exc)
    with pytest.raises(AIClientError) as err:
        client.complete("s", "u")
    assert words in err.value.message and err.value.hint


def test_bad_body_and_empty_content():
    client, _ = make(FakeResponse(200, None, text="<html>"))
    with pytest.raises(AIClientError, match="응답 형식"):
        client.complete("s", "u")
    client, _ = make(ok("", "length"))
    with pytest.raises(AIClientError, match="비어 있습니다") as err:
        client.complete("s", "u")
    assert "--max-tokens" in err.value.hint


def test_load_env_priority(tmp_path, monkeypatch):
    import app.config as config

    for name in ("API_KEY", "MODEL", "BASE_URL"):
        monkeypatch.setenv(name, "x")  # 테스트 뒤 원래 상태(없음)로 되돌리게 기록
        monkeypatch.delenv(name)
    tool_dir, work_dir = tmp_path / "tool", tmp_path / "work"
    tool_dir.mkdir()
    work_dir.mkdir()
    (tool_dir / ".env").write_text("API_KEY=from-tool\nMODEL=tool-model\n", encoding="utf-8")
    (work_dir / ".env").write_text("API_KEY=from-work\n", encoding="utf-8")
    monkeypatch.setattr(config, "TOOL_ENV", str(tool_dir / ".env"))
    monkeypatch.setenv("BASE_URL", "https://shell.example/v1")
    monkeypatch.chdir(work_dir)

    config.load_env()
    settings = read_api_settings()

    assert settings.api_key == "from-work"         # 현재 폴더 .env 가 도구 폴더보다 우선
    assert settings.model == "tool-model"          # 현재 폴더에 없으면 도구 폴더 값
    assert settings.base_url == "https://shell.example/v1"  # 셸 환경변수가 가장 우선


def test_read_api_settings(monkeypatch):
    monkeypatch.setenv("API_KEY", " k ")
    monkeypatch.setenv("BASE_URL", "  ")
    monkeypatch.setenv("MODEL", "env-model")
    settings = read_api_settings()
    assert (settings.api_key, settings.base_url, settings.model) == ("k", DEFAULT_BASE_URL, "env-model")
    assert read_api_settings("cli-model").model == "cli-model"
