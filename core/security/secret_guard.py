#!/usr/bin/env python
"""Willind 중앙 비밀값 가드 — 도구 무관 단일 진실원본.

어느 AI 러너(Claude Code / Codex / Gemini / 로컬 API)든 도구 실행 직전에
이 스크립트를 호출하면, 비밀값이 들어있는 파일(.env, credentials, key 등)을
읽거나 값까지 출력하려는 시도를 차단한다.

차단 규칙을 바꾸려면 이 파일 하나의 BLOCK_PATTERNS만 고치면
연결된 모든 도구에 동시에 반영된다.

입력(관용적 — 러너 버전/종류 무관):
  1) stdin JSON  : 현재 Claude Code 방식 {"tool_name":..,"tool_input":{..}}
  2) env CLAUDE_TOOL_INPUT : 구버전 방식 (tool_input JSON 직접)
  3) argv        : 범용 호출. 검사할 텍스트(명령/경로)를 인자로 직접 전달

판정 규약(Claude Code PreToolUse deny 호환):
  - 차단 : stderr에 사유 출력 + exit code 2
  - 통과 : 침묵 + exit code 0
"""
import io
import json
import os
import re
import sys

if hasattr(sys.stderr, "buffer"):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# 비밀값이 담긴 파일/경로 — 경로 맥락에서만 매치(코드의 process.env 등 오탐 방지)
BLOCK_PATTERNS = [
    r"(?:^|[\s\"'=:(/\\])\.env(?:\.[\w-]+)?(?:[\"'\s);|&>]|$)",  # .env / .env.local ...
    r"(?:^|[\s\"'=:(/\\])\.secrets?\b",                          # .secret / .secrets
    r"\bcredentials?\.json\b",                                    # credentials.json
    r"\bid_rsa\b",                                                # ssh private key
    r"\b[\w./\\-]+\.pem\b",                                       # *.pem
    r"\b[\w./\\-]+\.(?:p12|pfx)\b",                               # *.p12 / *.pfx
    r"\b[\w./\\-]*\.credentials\.json\b",                         # .credentials.json
]

_COMPILED = [re.compile(p, re.IGNORECASE) for p in BLOCK_PATTERNS]

# 값 없이 '변수 이름'만 뽑는 검증된 형식 — 이 호출에 한해 비밀파일 인자를 허용한다.
# 판정 방식: 아래 안전 리더 호출을 명령에서 떼어낸 뒤, 남은 부분에 비밀파일 접근이
# '더는 없을 때만' 통과시킨다. 따라서 `grep -o '^[^=]*' .env && cat .env` 같은
# 체이닝은 두 번째 .env 접근이 남아 그대로 차단된다(값 노출 불가).
SAFE_NAME_READER_PATTERNS = [
    # 전용 검증 스크립트: env_keys.py <file> [filter]  (= 앞만 출력, 값 물리적 불가)
    r"\S*env_keys\.py(?:\s+\S+){1,2}",
    # grep -o '^[^=]*' <file>  (등호 앞만)
    r"grep\s+-o\S*\s+['\"]?\^?\[\^=\]\*['\"]?\s+\S+",
    # cut -d= -f1 <file>
    r"cut\s+-d\s*['\"]?=['\"]?\s+-f\s*1\b(?:\s+\S+)?",
    # awk -F= '{print $1}' <file>
    r"awk\s+-F\s*['\"]?=['\"]?\s+['\"]?\{?\s*print\s+\$1[^'\"]*['\"]?(?:\s+\S+)?",
]
_SAFE_COMPILED = [re.compile(p, re.IGNORECASE) for p in SAFE_NAME_READER_PATTERNS]


def _strip_safe_name_readers(text: str) -> str:
    """검증된 '이름만' 리더 호출을 명령에서 제거한 잔여 텍스트를 돌려준다."""
    out = text
    for rx in _SAFE_COMPILED:
        out = rx.sub(" ", out)
    return out

DENY_MESSAGE = (
    "🔒 Willind 보안 가드: 비밀값 파일 접근 차단.\n"
    "이 도구 호출이 .env / credentials / key 같은 비밀 파일의 값을 노출할 수 있어 막았습니다.\n"
    "키 '이름'만 필요하면 값 없이: grep -o '^[^=]*' <파일>  (= 등호 앞만 출력)\n"
    "정말 값이 필요하면 사용자에게 직접 설정을 요청하세요 — 채팅/로그에 평문 노출 금지."
)


def _path_fields(ti):
    """도구 입력에서 '파일 경로/명령' 필드만 추출.

    설명(description)·내용(content/old_string/new_string)·검색어(pattern) 등
    텍스트 필드는 제외해, 문서나 설명에 비밀파일명을 '언급'만 한 경우의
    과차단을 방지한다. 알 수 없는 구조면 안전하게 전체를 검사한다.
    """
    if not isinstance(ti, dict):
        return str(ti)
    relevant = ("file_path", "path", "command", "notebook_path", "glob", "file_paths")
    vals = [str(ti[k]) for k in relevant if ti.get(k)]
    return " ".join(vals) if vals else json.dumps(ti, ensure_ascii=False)


def _gather_haystack() -> str:
    parts = []

    # 1) stdin (현재 Claude Code: 전체 hook payload JSON)
    raw_stdin = ""
    try:
        if not sys.stdin.isatty():
            raw_stdin = sys.stdin.read()
    except Exception:
        raw_stdin = ""
    if raw_stdin.strip():
        try:
            data = json.loads(raw_stdin)
            ti = data.get("tool_input", data) if isinstance(data, dict) else data
            parts.append(_path_fields(ti))
        except Exception:
            parts.append(raw_stdin)

    # 2) env CLAUDE_TOOL_INPUT (구버전 러너)
    env_raw = os.environ.get("CLAUDE_TOOL_INPUT", "")
    if env_raw.strip():
        try:
            parts.append(_path_fields(json.loads(env_raw)))
        except Exception:
            parts.append(env_raw)

    # 3) argv (범용 호출 — Codex/Gemini/로컬이 직접 텍스트 전달)
    if len(sys.argv) > 1:
        parts.append(" ".join(sys.argv[1:]))

    return "\n".join(parts)


def is_blocked(text: str) -> bool:
    return any(rx.search(text) for rx in _COMPILED)


def main() -> int:
    haystack = _gather_haystack()
    if haystack and is_blocked(haystack):
        # 값 없이 '이름만' 뽑는 검증된 형식이면, 그 호출을 떼고 남은 명령에
        # 비밀파일 접근이 더 없을 때만 통과(값 노출 불가). 그 외엔 차단.
        if not is_blocked(_strip_safe_name_readers(haystack)):
            return 0
        sys.stderr.write(DENY_MESSAGE + "\n")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())

