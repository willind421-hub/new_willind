from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path


ROOT = next((p for p in Path(__file__).resolve().parents if (p / "registry" / "_index.yaml").exists()), Path(__file__).resolve().parent)
CHAT_LOG = ROOT / "docs/chat-log"
HISTORY = ROOT / "docs/history"


def _force_utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _target(kind: str, date: str) -> Path:
    root = CHAT_LOG if kind == "chat-log" else HISTORY
    root.mkdir(parents=True, exist_ok=True)
    return root / f"{date}.md"


def _append_once(path: Path, title: str, body: str) -> str:
    marker = f"## {title}"
    existing = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
    if marker in existing:
        return "duplicate_skipped"
    prefix = "" if not existing.strip() else "\n\n"
    path.write_text(existing.rstrip() + prefix + marker + "\n\n" + body.strip() + "\n", encoding="utf-8")
    return "appended"


def main(argv: list[str] | None = None) -> int:
    _force_utf8_stdio()
    parser = argparse.ArgumentParser(description="Append a Willind session closeout record.")
    parser.add_argument("--title", required=True, help="Section title without markdown ##.")
    parser.add_argument("--summary", required=True, help="Short work summary.")
    parser.add_argument("--changed", default="", help="Changed files or no-change reason.")
    parser.add_argument("--validation", default="", help="Tests, smoke, or validation result.")
    parser.add_argument("--followup", default="", help="Remaining follow-up or risk.")
    parser.add_argument("--date", default=_today(), help="YYYY-MM-DD. Default: today.")
    args = parser.parse_args(argv)

    body_lines = [f"- 요약: {args.summary}"]
    if args.changed:
        body_lines.append(f"- 변경/산출물: {args.changed}")
    if args.validation:
        body_lines.append(f"- 검증: {args.validation}")
    if args.followup:
        body_lines.append(f"- 후속/한계: {args.followup}")
    body = "\n".join(body_lines)

    chat_path = _target("chat-log", args.date)
    history_path = _target("history", args.date)
    chat_status = _append_once(chat_path, args.title, body)
    history_status = _append_once(history_path, args.title, body)
    print(
        {
            "ok": True,
            "chat_log": str(chat_path),
            "chat_log_status": chat_status,
            "history": str(history_path),
            "history_status": history_status,
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
