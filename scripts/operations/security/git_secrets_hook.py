#!/usr/bin/env python
"""Git pre-commit hook — API 키/토큰 노출 차단.

2026-05-06 추가. willind cost ceiling 후속 — 키 git 유출이 진짜 비용 폭탄
(rotate 까지 시간 동안 unbounded 사용 가능).

설치:
  각 git repo 의 .git/hooks/pre-commit 파일에 다음 한 줄:
    python C:/new_willind/scripts/operations/security/git_secrets_hook.py

검출 패턴: OpenAI / Anthropic / Slack / GitHub PAT / Telegram bot / Google API /
Discord bot / AWS access key / private key block.

검출 시: exit code 1 + 어디서 검출됐는지 출력. commit 차단.

Bypass: 진짜 필요하면 `git commit --no-verify` 단, willind 룰 (CLAUDE.md) 에서 hooks
skip 금지 — 검출 패턴이 false positive 면 그 줄을 git secrets baseline 에 등록 후
commit (현재 미구현, 필요 시 추가).
"""
from __future__ import annotations

import re
import subprocess
import sys

PATTERNS: list[tuple[str, str]] = [
    ("OpenAI API key",        r"sk-[a-zA-Z0-9]{32,}"),
    ("Anthropic API key",     r"sk-ant-[a-zA-Z0-9_-]{20,}"),
    ("GitHub PAT (classic)",  r"ghp_[a-zA-Z0-9]{36,}"),
    ("GitHub PAT (fine-grained)", r"github_pat_[a-zA-Z0-9_]{50,}"),
    ("Slack bot token",       r"xoxb-[0-9]+-[0-9]+-[a-zA-Z0-9]{20,}"),
    ("Slack user token",      r"xoxp-[0-9]+-[0-9]+-[0-9]+-[a-f0-9]{32,}"),
    ("Slack app token",       r"xapp-[0-9]+-[A-Z0-9]+-[0-9]+-[a-f0-9]+"),
    ("Telegram bot token",    r"\b\d{8,12}:[A-Za-z0-9_-]{30,40}\b"),
    ("Google API key",        r"AIza[0-9A-Za-z_-]{35}"),
    ("AWS access key",        r"AKIA[0-9A-Z]{16}"),
    ("AWS secret key",        r"(?i)aws.{0,20}?(secret|access).{0,20}?['\"][a-zA-Z0-9/+=]{40}['\"]"),
    ("Private key block",     r"-----BEGIN (RSA |OPENSSH |EC |DSA |PGP )?PRIVATE KEY-----"),
    ("KIS account password",  r"(?i)KIS_[A-Z_]*PASSWORD\s*=\s*['\"]?[^\s'\"]{6,}"),
    ("Generic password env",  r"(?i)\b(password|passwd|secret|token|api_key)\s*=\s*['\"][^'\"$]{8,}['\"]"),
]

# 화이트리스트 — 검출돼도 무시할 파일/경로 (예: docs / 테스트 fixture)
WHITELIST_PATHS = (
    "docs/",
    "test/",
    "tests/",
    "fixtures/",
    "examples/",
    ".env.example",
    ".env.template",
    "git_secrets_hook.py",  # 자기 자신 (패턴 정의 자체)
)


def staged_files() -> list[str]:
    """git diff --cached --name-only — 이번 commit에 staged된 파일."""
    try:
        out = subprocess.check_output(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
            encoding="utf-8",
            errors="replace",
        )
        return [line.strip() for line in out.splitlines() if line.strip()]
    except subprocess.CalledProcessError:
        return []


def staged_diff(path: str) -> str:
    """staged 변경 내용 (추가된 줄)."""
    try:
        out = subprocess.check_output(
            ["git", "diff", "--cached", "--", path],
            encoding="utf-8",
            errors="replace",
        )
        # 추가된 줄만 (+로 시작, +++ 헤더 제외)
        added = []
        for line in out.splitlines():
            if line.startswith("+") and not line.startswith("+++"):
                added.append(line[1:])
        return "\n".join(added)
    except subprocess.CalledProcessError:
        return ""


def check_file(path: str) -> list[tuple[str, str, int]]:
    """staged diff 내 패턴 검출. Returns [(label, snippet, line_no)]."""
    if any(w in path.replace("\\", "/") for w in WHITELIST_PATHS):
        return []
    diff = staged_diff(path)
    if not diff:
        return []
    findings: list[tuple[str, str, int]] = []
    for line_no, line in enumerate(diff.splitlines(), start=1):
        for label, pattern in PATTERNS:
            m = re.search(pattern, line)
            if m:
                snippet = m.group(0)
                # 너무 길면 자르기
                if len(snippet) > 60:
                    snippet = snippet[:30] + "..." + snippet[-15:]
                findings.append((label, snippet, line_no))
    return findings


def main() -> int:
    files = staged_files()
    if not files:
        return 0

    total_findings: list[tuple[str, str, str, int]] = []
    for f in files:
        for label, snippet, line_no in check_file(f):
            total_findings.append((f, label, snippet, line_no))

    if not total_findings:
        return 0

    print("\n[git-secrets-hook] 비밀 키/토큰 검출 — commit 차단", file=sys.stderr)
    print("=" * 60, file=sys.stderr)
    for f, label, snippet, line_no in total_findings:
        print(f"  {f}:{line_no}", file=sys.stderr)
        print(f"    [{label}] {snippet}", file=sys.stderr)
    print("=" * 60, file=sys.stderr)
    print(
        "처리:\n"
        "  1. 키 제거 후 다시 commit\n"
        "  2. 키가 정말 필요하면 .env 로 분리 + .gitignore\n"
        "  3. false positive 면 운영자에게 보고 (whitelist 추가)\n",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())

