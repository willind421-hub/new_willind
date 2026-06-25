from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
REPORT_DIR = ROOT / "runtime" / "security"

TEXT_SUFFIXES = {
    ".bat",
    ".cmd",
    ".css",
    ".csv",
    ".html",
    ".ini",
    ".js",
    ".json",
    ".jsonl",
    ".jsx",
    ".log",
    ".md",
    ".mjs",
    ".ps1",
    ".py",
    ".sql",
    ".ts",
    ".tsx",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
}

PRUNE_DIR_NAMES = {
    ".browser-profiles",
    ".claude",
    ".git",
    ".mypy_cache",
    ".obsidian",
    ".pytest_cache",
    ".ruff_cache",
    ".secrets",
    ".venv",
    ".worktrees",
    "__pycache__",
    "backup",
    "build",
    "dist",
    "htmlcov",
    "models",
    "monaco",
    "node_modules",
    "runtime",
    "site-packages",
    "tests",
    "vendor",
    "workspaces",
    "worktrees",
}

HIGH_CONFIDENCE_PATTERNS = [
    ("OPENAI_KEY", re.compile(r"sk-[A-Za-z0-9_\-]{20,}")),
    ("ANTHROPIC_KEY", re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}")),
    ("GITHUB_PAT", re.compile(r"gh[pousr]_[A-Za-z0-9_]{20,}")),
    ("TELEGRAM_BOT_TOKEN", re.compile(r"\b\d{6,12}:[A-Za-z0-9_-]{25,}\b")),
    ("GOOGLE_API_KEY", re.compile(r"AIza[0-9A-Za-z_\-]{25,}")),
    ("AWS_ACCESS_KEY", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("PRIVATE_KEY_BLOCK", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
]


@dataclass
class Redaction:
    path: str
    replacements: dict[str, int]


def rel(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def should_prune_dir(path: Path) -> bool:
    return path.name in PRUNE_DIR_NAMES or path.is_symlink()


def should_skip_file(path: Path) -> bool:
    name = path.name
    if path.is_symlink():
        return True
    if name == ".env" or name.startswith(".env.") or name == ".npmrc":
        return True
    if path.suffix.lower() not in TEXT_SUFFIXES and path.suffix:
        return True
    try:
        if path.stat().st_size > 80_000_000:
            return True
    except OSError:
        return True
    return False


def redact_file(path: Path, dry_run: bool) -> Redaction | None:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None

    replacements: dict[str, int] = {}
    updated = text
    for label, pattern in HIGH_CONFIDENCE_PATTERNS:
        updated, count = pattern.subn(f"[REDACTED_{label}]", updated)
        if count:
            replacements[label] = count
    if not replacements:
        return None
    if not dry_run:
        path.write_text(updated, encoding="utf-8")
    return Redaction(path=rel(path), replacements=replacements)


def iter_files(root: Path):
    for current_text, dirs, files in os.walk(root):
        current = Path(current_text)
        dirs[:] = [directory for directory in dirs if not should_prune_dir(current / directory)]
        for filename in files:
            path = current / filename
            if not should_skip_file(path):
                yield path


def main() -> int:
    global ROOT, REPORT_DIR
    parser = argparse.ArgumentParser(description="Redact high-confidence secrets without printing values.")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    ROOT = args.root.resolve()
    REPORT_DIR = ROOT / "runtime" / "security"
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    redactions = [result for path in iter_files(ROOT) if (result := redact_file(path, args.dry_run))]
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    report_path = REPORT_DIR / f"high-confidence-redaction-{stamp}.json"
    report_path.write_text(
        json.dumps(
            {
                "root": str(ROOT),
                "dry_run": args.dry_run,
                "generated_at": datetime.now().isoformat(timespec="seconds"),
                "files_changed": 0 if args.dry_run else len(redactions),
                "files_matched": len(redactions),
                "redactions": [asdict(item) for item in redactions],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    summary = {
        "dry_run": args.dry_run,
        "files_matched": len(redactions),
        "files_changed": 0 if args.dry_run else len(redactions),
        "report": str(report_path),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2) if args.json else summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
