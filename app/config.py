"""기본 설정값과 환경변수 읽기. 숫자 규칙은 이 파일 한 곳에만 둔다."""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

DEFAULT_BASE_URL = "https://api.openai.com/v1"
DEFAULT_MODEL = "gpt-4o-mini"
DEFAULT_TIMEOUT = 60.0
API_KEY_ENV, BASE_URL_ENV, MODEL_ENV = "API_KEY", "BASE_URL", "MODEL"


@dataclass(frozen=True)
class GenerationDefaults:
    temperature: float
    max_tokens: int


# commit: 짧고 매번 비슷해야 한다 → 낮은 temperature, 작은 토큰 예산
# pr: 세 섹션에 불릿을 채운다 → 표현 여유를 조금 주고 예산을 넉넉히
COMMAND_DEFAULTS = {
    "commit": GenerationDefaults(temperature=0.2, max_tokens=400),
    "pr": GenerationDefaults(temperature=0.4, max_tokens=1000),
}

COMMIT_TITLE_RECOMMENDED = 50
COMMIT_TITLE_MAX = 72
PR_TITLE_MAX = 80

SAFE_MAX_FILES = 10
SAFE_MAX_LINES = 200
MAX_DIFF_CHARS = 24000  # 안전 모드와 무관하게 항상 적용하는 상한 (비용·컨텍스트 보호)


@dataclass(frozen=True)
class ApiSettings:
    api_key: str | None
    base_url: str
    model: str


TOOL_ENV = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")


def load_env(path: str = ".env") -> None:
    """현재 폴더의 .env, 그다음 도구 폴더의 .env 를 읽는다. 먼저 정해진 값이 이긴다.

    셸 환경변수 > 현재 폴더 .env > 도구 폴더 .env 순서. 다른 저장소 루트에서
    `python /경로/main.py commit` 으로 불러도 도구 폴더에 둔 키를 쓸 수 있다.
    """
    for candidate in dict.fromkeys((os.path.abspath(path), TOOL_ENV)):
        if os.path.isfile(candidate):
            load_dotenv(candidate, override=False)


def _env(name: str) -> str | None:
    value = os.environ.get(name, "").strip()
    return value or None


def read_api_settings(model_override: str | None = None) -> ApiSettings:
    return ApiSettings(
        api_key=_env(API_KEY_ENV),
        base_url=_env(BASE_URL_ENV) or DEFAULT_BASE_URL,
        model=model_override or _env(MODEL_ENV) or DEFAULT_MODEL,
    )
