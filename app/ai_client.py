"""OpenAI 호환 Chat Completions API 를 REST 로 직접 호출한다.

SDK 없이 requests 로 요청을 만들면 무엇을 보내고(JSON 본문·헤더) 무엇을 받는지
(choices·finish_reason·usage) 코드에 그대로 드러난다. 네트워크 오류는 자동으로 다시
보내지 않는다 — 비용이 드는 요청이라 사용자가 원인을 보고 다시 실행하게 한다.
"""

from __future__ import annotations

from dataclasses import dataclass

import requests

from app.config import API_KEY_ENV, DEFAULT_TIMEOUT


class AIClientError(Exception):
    """사용자에게 보여 줄 원인(message)과 대처법(hint)."""

    def __init__(self, message: str, hint: str | None = None):
        super().__init__(message)
        self.message = message
        self.hint = hint


@dataclass(frozen=True)
class Completion:
    text: str
    finish_reason: str | None
    prompt_tokens: int | None
    completion_tokens: int | None

    @property
    def truncated(self) -> bool:
        return self.finish_reason == "length"


# HTTP 상태 → (메시지 머리, 대처법)
_STATUS_MESSAGES = {
    401: ("인증 실패", "API_KEY 값과 권한을 확인하세요."),
    403: ("인증 실패", "API_KEY 값과 권한을 확인하세요."),
    404: ("요청 대상을 찾을 수 없습니다", "BASE_URL 과 --model 이름을 확인하세요."),
    400: ("잘못된 요청", "--model, --temperature, --max-tokens 값을 확인하세요."),
    422: ("잘못된 요청", "--model, --temperature, --max-tokens 값을 확인하세요."),
    429: ("요청 한도 초과", "잠시 후 다시 실행하고 사용량/요금제를 확인하세요."),
}


class AIClient:
    def __init__(self, api_key: str | None, base_url: str, model: str, temperature: float,
                 max_tokens: int, timeout: float = DEFAULT_TIMEOUT, session=None):
        if not api_key or not api_key.strip():
            raise AIClientError(
                f"{API_KEY_ENV} 환경변수가 설정되지 않았습니다.",
                hint=f'예) export {API_KEY_ENV}="YOUR_KEY"  (또는 .env 파일에 {API_KEY_ENV}=YOUR_KEY)',
            )
        self._api_key = api_key.strip()
        self.endpoint = base_url.rstrip("/") + "/chat/completions"
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout
        self._session = session or requests

    def build_payload(self, system: str, user: str) -> dict:
        return {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }

    def complete(self, system: str, user: str) -> Completion:
        headers = {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"}
        try:
            resp = self._session.post(self.endpoint, headers=headers,
                                      json=self.build_payload(system, user), timeout=self.timeout)
        except requests.exceptions.Timeout as exc:
            raise AIClientError(f"AI API 응답 시간 초과({self.timeout:g}초)",
                                hint="--timeout 값을 늘리거나 잠시 후 다시 실행하세요.") from exc
        except requests.exceptions.ConnectionError as exc:
            raise AIClientError(f"AI API 서버에 연결하지 못했습니다: {self.endpoint}",
                                hint="네트워크 연결과 BASE_URL 값을 확인하세요.") from exc
        except requests.exceptions.RequestException as exc:
            raise AIClientError(f"AI API 요청 실패: {type(exc).__name__}") from exc

        if not 200 <= resp.status_code < 300:
            raise self._http_error(resp)
        return self._parse(resp)

    def _http_error(self, resp) -> AIClientError:
        code = resp.status_code
        detail = self._error_detail(resp).replace(self._api_key, "***")
        if code in _STATUS_MESSAGES:
            head, hint = _STATUS_MESSAGES[code]
        elif code >= 500:
            head, hint = "AI API 서버 오류", "잠시 후 다시 실행하세요."
        else:
            head, hint = "AI API 요청 실패", None
        return AIClientError(f"{head}(HTTP {code}): {detail}", hint=hint)

    @staticmethod
    def _error_detail(resp) -> str:
        try:
            error = resp.json().get("error")
            if isinstance(error, dict) and error.get("message"):
                return str(error["message"])
            if isinstance(error, str) and error:
                return error
        except (ValueError, AttributeError):
            pass
        return (resp.text or "").strip()[:200] or "(응답 본문 없음)"

    @staticmethod
    def _parse(resp) -> Completion:
        try:
            data = resp.json()
            choice = data["choices"][0]
            content = choice["message"].get("content")
            finish_reason = choice.get("finish_reason")
            usage = data.get("usage") or {}
        except (ValueError, KeyError, IndexError, TypeError, AttributeError) as exc:
            raise AIClientError("AI API 응답 형식을 해석하지 못했습니다.") from exc

        if isinstance(content, list):  # 일부 서버는 [{"type":"text","text":...}] 로 준다
            content = "".join(p.get("text", "") for p in content if isinstance(p, dict))
        text = (content or "").strip()
        if not text:
            hint = "--max-tokens 값을 늘려 다시 실행하세요." if finish_reason == "length" else None
            raise AIClientError("AI 응답이 비어 있습니다.", hint=hint)
        return Completion(text, finish_reason, usage.get("prompt_tokens"), usage.get("completion_tokens"))
