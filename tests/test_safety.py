from __future__ import annotations

import pytest

from app.safety import (
    apply_safe_mode,
    cap_diff,
    count_sensitive,
    is_sensitive_path,
    mask_text,
    split_sections,
)

# 테스트 파일 자체에 비밀처럼 보이는 문자열이 남지 않도록 실행 중에 만든다.
OPENAI_KEY = "sk-" + "a1" * 12
AWS_KEY = "AKIA" + "B" * 16
GITHUB_TOKEN = "ghp_" + "c" * 36
JWT = "eyJ" + "h" * 12 + "." + "p" * 12 + "." + "s" * 12
PEM = "-----BEGIN RSA PRIVATE KEY-----\nMIIabc\nxyz\n-----END RSA PRIVATE KEY-----"


def section(path: str, *added: str) -> str:
    body = "".join(f"+{line}\n" for line in added)
    return f"diff --git a/{path} b/{path}\n--- a/{path}\n+++ b/{path}\n@@ -0,0 +1 @@\n{body}"


@pytest.mark.parametrize("raw, tag, rule", [
    (f"key = {OPENAI_KEY}", "[MASKED:API_KEY]", "API_KEY"),
    (f"aws={AWS_KEY}", "[MASKED:API_KEY]", "API_KEY"),
    (GITHUB_TOKEN, "[MASKED:API_KEY]", "API_KEY"),
    (f"Authorization: Bearer {JWT}", "[MASKED:JWT]", "JWT"),
    (PEM, "[MASKED:PRIVATE_KEY]", "PRIVATE_KEY"),
    ("작성자 hong@example.com", "[MASKED:EMAIL]", "EMAIL"),
    ("연락처 010-1234-5678", "[MASKED:PHONE]", "PHONE"),
    ("주민번호 900101-1234567", "[MASKED:RRN]", "RRN"),
])
def test_known_patterns_are_masked(raw, tag, rule):
    masked, counts = mask_text(raw)
    assert tag in masked
    assert counts == {rule: 1}


def test_secret_assignment_keeps_name():
    masked, counts = mask_text('API_KEY = "abcdef123456"\n+DB_PASSWORD=abcdef123456\n')
    assert 'API_KEY = "[MASKED:SECRET]"' in masked
    assert "+DB_PASSWORD=[MASKED:SECRET]" in masked
    assert counts == {"SECRET": 2}


def test_already_masked_value_is_not_counted_twice():
    _, counts = mask_text(f"+API_KEY={OPENAI_KEY}\n")
    assert counts == {"API_KEY": 1}


def test_plain_code_is_untouched():
    code = 'api_key = os.getenv("API_KEY")\nprint("hello")\n'
    assert mask_text(code) == (code, {})
    assert count_sensitive(code) == 0


def test_split_sections_round_trip():
    diff = section("app/a.py", "x") + section("docs/b.md", "y")
    sections = split_sections(diff)
    assert [p for p, _ in sections] == ["app/a.py", "docs/b.md"]
    assert "".join(t for _, t in sections) == diff


@pytest.mark.parametrize("path, expected", [
    (".env", True), ("config/.env.local", True), ("certs/server.pem", True), ("id_rsa", True),
    (".env.example", False), ("app/cli.py", False),
])
def test_is_sensitive_path(path, expected):
    assert is_sensitive_path(path) is expected


def test_safe_mode_excludes_and_masks():
    diff = section(".env", "API_KEY=abcdef123456") + section("app/a.py", "mail = 'a@b.co'")
    text, report = apply_safe_mode(diff)
    assert report.excluded_files == [".env"]
    assert ".env" not in text and "abcdef123456" not in text
    assert "[MASKED:EMAIL]" in text
    assert (report.original_files, report.sent_files, report.truncated) == (2, 1, False)
    assert report.masked_total == 1


def test_safe_mode_limits_files():
    diff = "".join(section(f"f{i}.py", "x") for i in range(5))
    text, report = apply_safe_mode(diff, max_files=2, max_lines=100)
    assert report.sent_files == 2 and report.truncated
    assert "f2.py" not in text
    assert "안전 모드: 이후 15줄 생략" in text


def test_safe_mode_limits_lines():
    diff = section("big.py", *[f"line{i}" for i in range(20)])  # 머리 4줄 + 20줄
    text, report = apply_safe_mode(diff, max_files=10, max_lines=10)
    assert report.sent_lines == 10 and report.original_lines == 24
    assert text.splitlines()[-1] == "... (안전 모드: 이후 14줄 생략)"


def test_cap_diff():
    assert cap_diff("short\n", max_chars=100) == ("short\n", False)
    long = "".join(f"line {i}\n" for i in range(100))
    text, cut = cap_diff(long, max_chars=50)
    assert cut
    head, marker = text.rsplit("\n... ", 1)
    assert len(head) <= 50 and long.startswith(head)
    assert "자 생략" in marker
