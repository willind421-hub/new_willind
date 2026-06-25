"""
chat-log RAW 자동 추출 script

목적: willind.db `messages` 테이블 → docs/chat-log/YYYY-MM-DD-raw.md 자동 생성.
배경: 운영자 chat-log 수동 작성만 두면 자기 변호 risk. raw / interpretation 분리.

사용:
    python C:/new_willind/scripts/operations/logging/extract_chat_log_raw.py             # 어제 날짜 (자정 직후 실행 가정)
    python C:/new_willind/scripts/operations/logging/extract_chat_log_raw.py --date 2026-05-07
    python C:/new_willind/scripts/operations/logging/extract_chat_log_raw.py --date 2026-05-07 --force  # 기존 파일 덮어쓰기

PM2 cron 등록 예:
    pm2 start C:/new_willind/scripts/operations/logging/extract_chat_log_raw.py \\
      --name chat-log-raw --no-autorestart --interpreter python \\
      --cron "5 0 * * *"   # 매일 자정 5분 (자정 직후 잔여 메시지 흡수)
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import sqlite3
import sys
import traceback
from pathlib import Path

# ---------------------------------------------------------------------------
# 설정
# ---------------------------------------------------------------------------

WILLIND_ROOT = next((p for p in Path(__file__).resolve().parents if (p / "registry" / "_index.yaml").exists()), Path(__file__).resolve().parent)
WILLIND_MCP_ROOT = (
    WILLIND_ROOT / "projects" / "willind-mcp"
    if (WILLIND_ROOT / "projects" / "willind-mcp").exists()
    else WILLIND_ROOT / "willind-mcp"
)
DB_PATH = Path(os.getenv("WILLIND_DB_PATH", str(WILLIND_MCP_ROOT / "willind.db")))
OUTPUT_DIR = WILLIND_ROOT / "docs" / "chat-log"
LOG_FILE = WILLIND_ROOT / "docs" / "chat-log" / "_extract_raw.log"

USER = "사용자"

# 메시지 type 분류 (운영자 명세):
#   task_request / report / result → 역할 응답 섹션
#   broadcast / error              → 시스템 이벤트 섹션
DEPT_REPLY_TYPES = {"task_request", "report", "result"}
SYSTEM_EVENT_TYPES = {"broadcast", "error"}


# ---------------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------------


def fmt_ts(d: dt.datetime | None = None) -> str:
    if d is None:
        d = dt.datetime.now()
    return d.strftime("%Y-%m-%d %H:%M:%S")


def log_line(line: str) -> None:
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(line.rstrip("\n") + "\n")
    try:
        print(line, flush=True)
    except UnicodeEncodeError:
        try:
            sys.stdout.buffer.write((line + "\n").encode("utf-8", errors="replace"))
            sys.stdout.flush()
        except Exception:
            print(line.encode("ascii", errors="replace").decode("ascii"), flush=True)


def yesterday_kst() -> dt.date:
    return (dt.datetime.now() - dt.timedelta(days=1)).date()


def parse_date(s: str) -> dt.date:
    return dt.datetime.strptime(s, "%Y-%m-%d").date()


def time_only(created_at: str) -> str:
    """`'2026-05-07 14:39:24'` → `'14:39:24'`. SQLite CURRENT_TIMESTAMP 형식 가정."""
    if not created_at:
        return "??:??:??"
    parts = created_at.split(" ")
    if len(parts) >= 2:
        return parts[1][:8]
    return created_at[:8]


def sanitize_content(text: str) -> str:
    """
    메시지 내용을 한 항목 안에 가독성 있게 표시.
    - 줄바꿈 보존을 위해 다음 줄에 4-space 들여쓰기.
    - 최대 길이 제한 X (raw 는 진실 그대로).
    """
    if text is None:
        return ""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = text.split("\n")
    if len(lines) == 1:
        return lines[0]
    head = lines[0]
    tail = "\n".join("    " + ln for ln in lines[1:])
    return f"{head}\n{tail}"


# ---------------------------------------------------------------------------
# 메시지 조회
# ---------------------------------------------------------------------------


def fetch_messages_for_date(target: dt.date) -> list[dict]:
    """
    target 날짜의 모든 messages 조회.
    archived 무시 (raw = 진실 그대로). status 무시.
    SQLite busy_timeout 30s — 다른 writer 와 경합 시 대기.
    """
    if not DB_PATH.exists():
        raise FileNotFoundError(f"DB not found: {DB_PATH}")

    start = f"{target.isoformat()} 00:00:00"
    end = f"{target.isoformat()} 23:59:59"

    conn = sqlite3.connect(str(DB_PATH), timeout=30.0)
    conn.execute("PRAGMA busy_timeout=30000")
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT id, from_role, to_role, content, type, status,
                   reply_to_id, project, created_at
              FROM messages
             WHERE created_at >= ? AND created_at <= ?
          ORDER BY created_at ASC, id ASC
            """,
            (start, end),
        ).fetchall()
    finally:
        conn.close()

    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# 분류 / 렌더
# ---------------------------------------------------------------------------


def classify(messages: list[dict]) -> dict:
    """
    분류 규칙:
      사용자 발화        : from_role == "사용자"
      역할 응답 (역할별): from_role != "사용자" AND type in {task_request, report, result}
      시스템 이벤트     : type in {broadcast, error}  (사용자 발화 우선 적용 후 잔여)
      기타            : 위 어디에도 안 들어가는 메시지 — 부록에 모음
    """
    user: list[dict] = []
    by_dept: dict[str, list[dict]] = {}
    system: list[dict] = []
    other: list[dict] = []

    for m in messages:
        f_dept = (m.get("from_role") or "").strip()
        m_type = (m.get("type") or "").strip()

        if f_dept == USER:
            user.append(m)
            continue

        if m_type in SYSTEM_EVENT_TYPES:
            system.append(m)
            continue

        if m_type in DEPT_REPLY_TYPES:
            by_dept.setdefault(f_dept or "(unknown)", []).append(m)
            continue

        other.append(m)

    return {
        "user": user,
        "by_dept": by_dept,
        "system": system,
        "other": other,
    }


def render_section_user(items: list[dict]) -> str:
    if not items:
        return "## [사용자 발화]\n- (없음)\n"
    lines = ["## [사용자 발화]"]
    for m in items:
        ts = time_only(m.get("created_at", ""))
        to = m.get("to_role") or "?"
        body = sanitize_content(m.get("content", ""))
        lines.append(f"- {ts} → {to} — {body}")
    return "\n".join(lines) + "\n"


def render_section_dept(by_dept: dict[str, list[dict]]) -> str:
    if not by_dept:
        return "## [역할 응답]\n- (없음)\n"
    out: list[str] = []
    for dept in sorted(by_dept.keys()):
        items = by_dept[dept]
        out.append(f"## [역할 응답 — {dept}]")
        for m in items:
            ts = time_only(m.get("created_at", ""))
            to = m.get("to_role") or "?"
            mtype = m.get("type") or "?"
            body = sanitize_content(m.get("content", ""))
            out.append(f"- {ts} → {to} ({mtype}) — {body}")
        out.append("")
    return "\n".join(out)


def render_section_system(items: list[dict]) -> str:
    if not items:
        return "## [시스템 이벤트]\n- (없음)\n"
    lines = ["## [시스템 이벤트]"]
    for m in items:
        ts = time_only(m.get("created_at", ""))
        f_dept = m.get("from_role") or "?"
        to = m.get("to_role") or "?"
        mtype = m.get("type") or "?"
        body = sanitize_content(m.get("content", ""))
        lines.append(f"- {ts} {f_dept} → {to} ({mtype}) — {body}")
    return "\n".join(lines) + "\n"


def render_section_other(items: list[dict]) -> str:
    if not items:
        return ""
    lines = ["## [기타 — 분류 미정]"]
    for m in items:
        ts = time_only(m.get("created_at", ""))
        f_dept = m.get("from_role") or "?"
        to = m.get("to_role") or "?"
        mtype = m.get("type") or "?"
        body = sanitize_content(m.get("content", ""))
        lines.append(f"- {ts} {f_dept} → {to} ({mtype}) — {body}")
    return "\n".join(lines) + "\n"


def render_document(target: dt.date, messages: list[dict]) -> str:
    classified = classify(messages)
    header = f"# {target.isoformat()} chat-log RAW (자동 추출)\n"
    meta = (
        f"- 추출 시각: {fmt_ts()}\n"
        f"- 메시지 수: {len(messages)}\n"
        f"- 출처: `{DB_PATH.relative_to(WILLIND_ROOT)}` (messages 테이블)\n"
        "- 분류 규칙: 사용자 발화 = `from_role = 사용자` / "
        "역할 응답 = type in {task_request, report, result} / "
        "시스템 이벤트 = type in {broadcast, error}\n"
        "- 본 파일은 자동 생성됨. 운영자 자필 해석은 같은 날짜 `*-interpretation.md` 별도 파일에 작성.\n"
    )
    body_parts = [
        header,
        meta,
        "",
        render_section_user(classified["user"]),
        render_section_dept(classified["by_dept"]),
        render_section_system(classified["system"]),
        render_section_other(classified["other"]),
    ]
    return "\n".join(body_parts).rstrip() + "\n"


# ---------------------------------------------------------------------------
# 운영자 알림 (실패 시)
# ---------------------------------------------------------------------------


def notify_president_failure(summary: str) -> bool:
    """willind.db messages 에 직접 INSERT — db_backup.py 패턴 동일."""
    try:
        if not DB_PATH.exists():
            return False
        conn = sqlite3.connect(str(DB_PATH), timeout=30.0)
        conn.execute("PRAGMA busy_timeout=30000")
        try:
            with conn:
                conn.execute(
                    """
                    INSERT INTO messages (from_role, to_role, content, type, status, project)
                    VALUES (?, ?, ?, ?, 'pending', ?)
                    """,
                    ("backend", "운영자", summary, "error", "chat-log-raw"),
                )
        finally:
            conn.close()
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# 메인
# ---------------------------------------------------------------------------


def run(target: dt.date, force: bool) -> int:
    """
    반환값: 0 정상, 1 skip (이미 존재), 2 실패.
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / f"{target.isoformat()}-raw.md"

    if out_path.exists() and not force:
        log_line(f"{fmt_ts()} SKIP {out_path.name} 이미 존재 (--force 로 덮어쓰기)")
        return 1

    try:
        messages = fetch_messages_for_date(target)
    except Exception as e:
        log_line(f"{fmt_ts()} ERROR fetch — {type(e).__name__}: {e}")
        notify_president_failure(
            f"[chat-log raw 실패] {target.isoformat()} fetch — {type(e).__name__}: {e}"
        )
        return 2

    doc = render_document(target, messages)
    try:
        # 원자성 — 임시 파일에 쓰고 rename
        tmp = out_path.with_suffix(".md.tmp")
        with tmp.open("w", encoding="utf-8", newline="\n") as f:
            f.write(doc)
        tmp.replace(out_path)
    except Exception as e:
        log_line(f"{fmt_ts()} ERROR write — {type(e).__name__}: {e}")
        notify_president_failure(
            f"[chat-log raw 실패] {target.isoformat()} write — {type(e).__name__}: {e}"
        )
        return 2

    log_line(
        f"{fmt_ts()} OK {out_path.name} msg={len(messages)} bytes={out_path.stat().st_size}"
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="willind chat-log RAW 자동 추출")
    parser.add_argument(
        "--date",
        help="추출 대상 날짜 (YYYY-MM-DD). 미지정 시 어제.",
        default=None,
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="기존 raw 파일 존재해도 덮어쓰기.",
    )
    args = parser.parse_args()

    target = parse_date(args.date) if args.date else yesterday_kst()
    log_line(f"{fmt_ts()} === EXTRACT START date={target.isoformat()} force={args.force} ===")

    try:
        rc = run(target, args.force)
    except Exception as e:
        tb = traceback.format_exc()
        log_line(f"{fmt_ts()} FATAL {type(e).__name__}: {e}")
        log_line(tb)
        notify_president_failure(
            f"[chat-log raw FATAL] {target.isoformat()} {type(e).__name__}: {e}"
        )
        rc = 2

    log_line(f"{fmt_ts()} === EXTRACT END date={target.isoformat()} rc={rc} ===")
    return rc


if __name__ == "__main__":
    sys.exit(main())


