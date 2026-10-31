"""명령줄 진입점: 옵션을 읽고 수집 → 정리 → 프롬프트 → AI 호출 → 검증 → 출력 순서로 실행한다.

진행 로그([INFO] 등)는 stderr, 최종 결과 블록은 stdout 으로 내보낸다.
그래서 `python main.py commit > msg.txt` 처럼 결과만 따로 받을 수 있다.
"""

from __future__ import annotations

import argparse
import sys

from app.ai_client import AIClient, AIClientError
from app.config import (
    COMMAND_DEFAULTS,
    DEFAULT_TIMEOUT,
    SAFE_MAX_FILES,
    SAFE_MAX_LINES,
    load_env,
    read_api_settings,
)
from app.formatter import enforce_commit, enforce_pr, format_commit, format_pr, validate_commit
from app.git_manager import GitError, collect_commit_changes, collect_pr_changes, ensure_repo_root
from app.prompts import build_commit_prompt, build_pr_prompt, build_retry_prompt
from app.safety import apply_safe_mode, cap_diff, count_sensitive, is_sensitive_path, split_sections

LINE = "----------------------"
MAX_LOGGED_FILES = 20
WHAT = {"commit": "커밋 메시지", "pr": "PR 초안"}
WHAT_OBJECT = {"commit": "커밋 메시지를", "pr": "PR 초안을"}  # 조사까지 붙인 목적어


def log(level: str, message: str) -> None:
    print(f"[{level}] {message}", file=sys.stderr)


def log_error(error: Exception) -> None:
    log("ERROR", getattr(error, "message", str(error)))
    hint = getattr(error, "hint", None)
    if hint:
        print(f"        {hint}", file=sys.stderr)


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    group = common.add_argument_group("AI API 옵션")
    group.add_argument("--model", help="모델 이름 (기본: 환경변수 MODEL 또는 gpt-4o-mini)")
    group.add_argument("--temperature", type=float,
                       help="0.0~2.0, 낮을수록 일관된 표현 (기본: commit 0.2 / pr 0.4)")
    group.add_argument("--max-tokens", type=int,
                       help="응답 최대 토큰 수 (기본: commit 400 / pr 1000)")
    group.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT,
                       help=f"요청 제한 시간(초) (기본: {DEFAULT_TIMEOUT:g})")
    group.add_argument("--no-retry", action="store_true",
                       help="형식 위반이어도 다시 생성하지 않고 후처리만 (호출 1회 고정)")
    group.add_argument("--dry-run", action="store_true",
                       help="AI 를 호출하지 않고 보낼 프롬프트만 출력 (API Key 불필요)")
    safe = common.add_argument_group("안전 모드")
    safe.add_argument("--safe-mode", action="store_true",
                      help="민감 파일 제외 + 키·이메일 등 마스킹 + 전송량 제한")
    safe.add_argument("--max-files", type=int, default=SAFE_MAX_FILES,
                      help=f"안전 모드에서 보낼 최대 파일 수 (기본: {SAFE_MAX_FILES})")
    safe.add_argument("--max-lines", type=int, default=SAFE_MAX_LINES,
                      help=f"안전 모드에서 보낼 최대 diff 줄 수 (기본: {SAFE_MAX_LINES})")

    parser = argparse.ArgumentParser(
        prog="python main.py",
        description="Git 변경 사항으로 커밋 메시지와 PR 초안을 만듭니다. 결과는 초안이니 검토 후 쓰세요.",
    )
    sub = parser.add_subparsers(dest="command", required=True, metavar="{commit,pr}")
    sub.add_parser("commit", parents=[common], help="커밋 메시지 생성")
    pr = sub.add_parser("pr", parents=[common], help="PR 제목·본문 초안 생성")
    pr.add_argument("--base", default="main", help="비교할 기준 브랜치 (기본: main)")
    return parser


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.temperature is not None and not 0.0 <= args.temperature <= 2.0:
        parser.error("--temperature 는 0.0 ~ 2.0 사이여야 합니다.")
    for name in ("max_tokens", "max_files", "max_lines"):
        value = getattr(args, name)
        if value is not None and value < 1:
            parser.error(f"--{name.replace('_', '-')} 는 1 이상이어야 합니다.")
    if args.timeout <= 0:
        parser.error("--timeout 은 0 보다 커야 합니다.")
    return args


def prepare_diff(args: argparse.Namespace, diff: str) -> tuple[str, list[str]]:
    """안전 모드·길이 상한을 적용한 diff 와, 프롬프트에 붙일 참고 사항."""
    notes: list[str] = []
    if args.safe_mode:
        diff, report = apply_safe_mode(diff, args.max_files, args.max_lines)
        log("INFO", f"안전 모드: 마스킹 {report.masked_total}건, 제외 파일 {len(report.excluded_files)}개, "
                    f"전송 {report.sent_files}/{report.original_files}개 파일 · "
                    f"{report.sent_lines}/{report.original_lines}줄")
        if report.masked_total:
            notes.append("민감정보로 보이는 값은 [MASKED:...] 로 가렸습니다. 원래 값을 추측하지 마세요.")
        if report.excluded_files:
            notes.append(f"민감 파일 diff 제외: {', '.join(report.excluded_files)}")
        if report.truncated:
            notes.append("diff 일부만 보냈습니다. 잘린 부분은 추측하지 마세요.")
    else:  # 끄면 가리지는 않지만, 보이면 알려 준다
        found = count_sensitive(diff)
        risky = [path for path, _ in split_sections(diff) if path and is_sensitive_path(path)]
        if found:
            log("WARN", f"diff 에서 민감정보로 보이는 패턴 {found}건을 찾았습니다. --safe-mode 사용을 권장합니다.")
        if risky:
            log("WARN", f"민감 파일 diff 가 포함돼 있습니다: {', '.join(risky)} (--safe-mode 면 제외)")
    diff, capped = cap_diff(diff)
    if capped:
        log("WARN", "diff 가 길어 앞부분만 보냅니다.")
        notes.append("diff 가 길어 뒷부분을 잘랐습니다. 잘린 부분은 추측하지 마세요.")
    return diff, notes


def render(command: str, value) -> str:
    if command == "commit":
        return f"--- Commit Message ---\n{value.render()}\n{LINE}"
    return f"--- PR Title ---\n{value.title}\n\n--- PR Body ---\n{value.render_body()}\n{LINE}"


def main(argv: list[str] | None = None) -> int:
    load_env()
    args = parse_args(argv)
    command = args.command
    settings = read_api_settings(args.model)
    defaults = COMMAND_DEFAULTS[command]
    temperature = defaults.temperature if args.temperature is None else args.temperature
    max_tokens = args.max_tokens or defaults.max_tokens

    # 설정 오류(API Key 없음)는 Git 작업보다 먼저 알린다. --dry-run 은 키가 필요 없다.
    client = None
    if not args.dry_run:
        try:
            client = AIClient(settings.api_key, settings.base_url, settings.model,
                              temperature, max_tokens, timeout=args.timeout)
        except AIClientError as exc:
            log_error(exc)
            return 2

    try:
        ensure_repo_root()
        changes = collect_commit_changes() if command == "commit" else collect_pr_changes(args.base)
    except GitError as exc:
        log_error(exc)
        return 1

    log("INFO", f"현재 브랜치: {changes.branch}")
    log("INFO", f"{changes.files_from} 수집 완료: {len(changes.files)}개 파일 변경 감지")
    for f in changes.files[:MAX_LOGGED_FILES]:
        print(f"        {f.status}  {f.path}", file=sys.stderr)
    if len(changes.files) > MAX_LOGGED_FILES:
        print(f"        ... 외 {len(changes.files) - MAX_LOGGED_FILES}개", file=sys.stderr)
    log("INFO", f"Git diff 수집 완료: {changes.diff_line_count}줄 · {changes.source}")
    if changes.pending:
        log("WARN", f"커밋되지 않은 변경 {len(changes.pending)}개는 브랜치 비교에 들어가지 않습니다. "
                    "PR 에 넣으려면 먼저 커밋하세요.")

    if changes.is_empty:
        log("INFO", f"변경 사항이 없습니다. {WHAT_OBJECT[command]} 생성하지 않고 종료합니다.")
        return 0

    diff, notes = prepare_diff(args, changes.diff)
    if command == "commit":
        prompt = build_commit_prompt(changes, diff, notes)
    else:
        prompt = build_pr_prompt(changes, diff, notes, args.base)

    if client is None:  # --dry-run
        print(f"--- System Prompt ---\n{prompt.system}\n--- User Prompt ---\n{prompt.user}\n{LINE}",
              flush=True)
        log("INFO", "--dry-run: AI API 를 호출하지 않았습니다 (호출 0회)")
        return 0

    log("INFO", f"AI API 요청 중... (model={settings.model}, temperature={temperature:g}, "
                f"max_tokens={max_tokens})")
    # 형식 위반이면 1회만 다시 생성한다 (실행당 최대 2회 호출). --no-retry 면 후처리만.
    max_calls = 1 if args.no_retry else 2
    calls, tokens_in, tokens_out = 0, 0, 0
    request = prompt
    while True:
        try:
            calls += 1
            completion = client.complete(request.system, request.user)
        except AIClientError as exc:
            log_error(exc)
            log("INFO", f"AI API 호출 횟수: {calls}회")
            return 1
        tokens_in += completion.prompt_tokens or 0
        tokens_out += completion.completion_tokens or 0
        if completion.truncated:
            log("WARN", f"응답이 max_tokens({max_tokens}) 에서 잘렸습니다. --max-tokens 값을 늘려 보세요.")

        result = format_commit(completion.text) if command == "commit" else format_pr(completion.text)
        value = result.value
        if not result.issues:
            break
        if calls < max_calls:
            log("WARN", f"형식 규칙 위반 {len(result.issues)}건 → 1회 다시 생성합니다: "
                        + "; ".join(result.issues))
            request = build_retry_prompt(prompt, completion.text, result.issues)
            continue
        value, fixes = enforce_commit(value) if command == "commit" else enforce_pr(value)
        for note in fixes:
            log("WARN", f"후처리로 보정했습니다: {note}")
        if command == "commit":  # 잘라 낸 제목도 권장 길이·접두어 경고는 다시 본다
            result.warnings = validate_commit(value)[1]
        break

    log("DONE", f"{WHAT[command]} 생성 완료")
    usage = f" · 토큰 입력 {tokens_in} / 출력 {tokens_out}" if tokens_in or tokens_out else ""
    log("INFO", f"AI API 호출 횟수: {calls}회{usage}")
    for warning in result.warnings:
        log("WARN", warning)

    print(render(command, value), flush=True)  # stderr 로그와 순서가 섞이지 않게
    log("INFO", "AI 가 만든 초안입니다. 실제 변경과 맞는지 검토한 뒤 사용하세요.")
    return 0
