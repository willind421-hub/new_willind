from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterable


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
    ".rs",
    ".sql",
    ".ts",
    ".tsx",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
}

PRUNE_DIR_NAMES = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    ".worktrees",
    "__pycache__",
    "build",
    "dist",
    "htmlcov",
    "monaco",
    "node_modules",
    "sample_runs",
    "site-packages",
    "tests",
    "vendor",
}

PRIVATE_DIR_NAMES = {
    ".browser-profiles",
    ".claude",
    ".obsidian",
    ".secrets",
    "backup",
    "models",
    "runtime",
    "workspaces",
    "worktrees",
    "개인",
    "사진",
    "학교",
    "회사",
}

SECRET_NAME_RE = re.compile(
    r"(?i)(^|[._-])(secret|credential|credentials|token|tokens|passwd|password|private|client_secret|oauth|apikey|api_key)([._-]|$)"
)
PRIVATE_KEY_RE = re.compile(r"(?i)(id_rsa|id_ed25519|private.*key|\.pem$|\.p12$|\.pfx$)")
DATABASE_RE = re.compile(r"(?i)\.(db|sqlite|sqlite3)$|\.db-(wal|shm)$")
MODEL_RE = re.compile(r"(?i)\.(gguf|safetensors|pt|pth|onnx)$")

SECRET_VALUE_PATTERNS = [
    ("openai_key", re.compile(r"sk-[A-Za-z0-9_\-]{20,}")),
    ("anthropic_key", re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}")),
    ("github_pat", re.compile(r"gh[pousr]_[A-Za-z0-9_]{20,}")),
    ("telegram_bot_token", re.compile(r"\b\d{6,12}:[A-Za-z0-9_-]{25,}\b")),
    ("google_api_key", re.compile(r"AIza[0-9A-Za-z_\-]{25,}")),
    ("aws_access_key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("private_key_block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    (
        "generic_secret_assignment",
        re.compile(
            r"(?i)\b(secret|token|password|passwd|api[_-]?key|client[_-]?secret)\b\s*[:=]\s*['\"]?[A-Za-z0-9_\-./+=]{16,}"
        ),
    ),
]

RISK_PATTERNS = [
    ("python_shell_true", re.compile(r"\bshell\s*=\s*True\b")),
    ("python_tls_verify_false", re.compile(r"\bverify\s*=\s*False\b")),
    ("python_eval_exec", re.compile(r"\b(eval|exec)\s*\(")),
    ("cors_wildcard", re.compile(r"allow_origins\s*=\s*\[\s*['\"]\*['\"]\s*\]")),
    ("powershell_recursive_delete", re.compile(r"Remove-Item\b[^\n\r]*(?:-Recurse[^\n\r]*-Force|-Force[^\n\r]*-Recurse)", re.I)),
    ("bind_all_interfaces", re.compile(r"(?<![0-9])0\.0\.0\.0(?![0-9])")),
]


@dataclass
class Finding:
    severity: str
    category: str
    path: str
    detail: str
    line: int | None = None


@dataclass
class FolderReport:
    root_item: str
    kind: str
    files_seen: int = 0
    dirs_seen: int = 0
    text_files_scanned: int = 0
    content_skipped: int = 0
    pruned_dirs: int = 0
    bytes_seen: int = 0
    findings: list[Finding] = field(default_factory=list)


def rel(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def should_prune_dir(path: Path) -> str | None:
    name = path.name
    if name in PRUNE_DIR_NAMES:
        return "generated_or_dependency"
    if name in PRIVATE_DIR_NAMES:
        return "private_or_runtime_root"
    if path.is_symlink():
        return "symlink"
    return None


def should_skip_content(path: Path, size: int) -> str | None:
    name = path.name
    path_text = rel(path)
    if path.is_symlink():
        return "symlink"
    if SECRET_NAME_RE.search(name) or PRIVATE_KEY_RE.search(name):
        return "secret_filename"
    if DATABASE_RE.search(name):
        return "database"
    if MODEL_RE.search(name):
        return "model_or_weight"
    if any(part in PRIVATE_DIR_NAMES for part in path.parts):
        return "private_or_runtime_path"
    if size > 2_000_000:
        return "large_file"
    if path.suffix.lower() not in TEXT_SUFFIXES and path.suffix:
        return "non_text"
    if name == ".env" or name.startswith(".env.") or name == ".npmrc":
        return "env_file"
    return None


def read_text_lines(path: Path) -> Iterable[tuple[int, str]]:
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for idx, line in enumerate(handle, start=1):
            yield idx, line.rstrip("\n\r")


def scan_text_file(path: Path) -> list[Finding]:
    findings: list[Finding] = []
    path_text = rel(path)
    historical_or_data_path = path_text.startswith(("data/raw/", "data/processed/", "docs/", "handoff/"))
    for line_no, line in read_text_lines(path):
        for label, pattern in SECRET_VALUE_PATTERNS:
            if pattern.search(line):
                if label == "generic_secret_assignment" and any(
                    marker in line
                    for marker in (
                        "process.env",
                        "os.environ",
                        "getenv(",
                        "$env:",
                        "Get-EnvFileValue",
                        "request.headers.get",
                        "import.meta.env",
                        "localStorage.getItem",
                        "Authorization:",
                        "Bearer ${",
                        "Bearer ",
                    )
                ):
                    continue
                severity = "warn" if label == "generic_secret_assignment" else "fail"
                findings.append(
                    Finding(
                        severity=severity,
                        category="secret_value_pattern",
                        path=path_text,
                        line=line_no,
                        detail=f"redacted match: {label}",
                    )
                )
        for label, pattern in RISK_PATTERNS:
            if pattern.search(line):
                severity = "warn"
                if label == "python_tls_verify_false" and not historical_or_data_path:
                    severity = "fail"
                findings.append(
                    Finding(
                        severity=severity,
                        category="risky_code_pattern",
                        path=path_text,
                        line=line_no,
                        detail=label,
                    )
                )
    return findings


def audit_item(path: Path) -> FolderReport:
    kind = "directory" if path.is_dir() else "file"
    report = FolderReport(root_item=path.name, kind=kind)

    if path.is_file():
        size = path.stat().st_size
        report.files_seen += 1
        report.bytes_seen += size
        reason = should_skip_content(path, size)
        if reason:
            report.content_skipped += 1
            if reason in {"secret_filename", "env_file"}:
                report.findings.append(Finding("warn", "sensitive_file_present", rel(path), reason))
            return report
        report.text_files_scanned += 1
        report.findings.extend(scan_text_file(path))
        return report

    if path.is_dir():
        prune_reason = should_prune_dir(path)
        if prune_reason:
            report.pruned_dirs += 1
            report.findings.append(Finding("info", "root_item_not_content_scanned", rel(path), prune_reason))
            return report

        for current_text, dirs, files in os.walk(path):
            current = Path(current_text)
            report.dirs_seen += len(dirs)
            kept_dirs = []
            for directory in dirs:
                child = current / directory
                reason = should_prune_dir(child)
                if reason:
                    report.pruned_dirs += 1
                    report.findings.append(Finding("info", "directory_pruned", rel(child), reason))
                else:
                    kept_dirs.append(directory)
            dirs[:] = kept_dirs

            for filename in files:
                file_path = current / filename
                try:
                    size = file_path.stat().st_size
                except OSError as exc:
                    report.findings.append(Finding("warn", "file_stat_failed", rel(file_path), str(exc)))
                    continue
                report.files_seen += 1
                report.bytes_seen += size
                reason = should_skip_content(file_path, size)
                if reason:
                    report.content_skipped += 1
                    if reason in {"secret_filename", "database"}:
                        report.findings.append(Finding("warn", "sensitive_or_state_file_present", rel(file_path), reason))
                    continue
                report.text_files_scanned += 1
                try:
                    report.findings.extend(scan_text_file(file_path))
                except OSError as exc:
                    report.findings.append(Finding("warn", "file_read_failed", rel(file_path), str(exc)))
    return report


def severity_counts(reports: list[FolderReport]) -> dict[str, int]:
    counts = {"fail": 0, "warn": 0, "info": 0}
    for report in reports:
        for finding in report.findings:
            counts[finding.severity] = counts.get(finding.severity, 0) + 1
    return counts


def write_reports(reports: list[FolderReport]) -> tuple[Path, Path]:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    json_path = REPORT_DIR / f"root-folder-security-audit-{stamp}.json"
    md_path = REPORT_DIR / f"root-folder-security-audit-{stamp}.md"
    payload = {
        "root": str(ROOT),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "policy": {
            "secret_values": "redacted; only pattern labels are reported",
            "skipped_content": sorted(PRIVATE_DIR_NAMES | PRUNE_DIR_NAMES),
            "max_text_file_bytes": 2_000_000,
        },
        "counts": severity_counts(reports),
        "folders": [asdict(report) for report in reports],
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# Root Folder Security Audit",
        "",
        f"- Root: `{ROOT}`",
        f"- Generated: `{payload['generated_at']}`",
        "- Secret values are not printed. Matches are redacted to labels only.",
        "",
        "## Summary",
        "",
        f"- Fail: {payload['counts'].get('fail', 0)}",
        f"- Warn: {payload['counts'].get('warn', 0)}",
        f"- Info: {payload['counts'].get('info', 0)}",
        "",
        "## Root Items",
        "",
        "| Root item | Files | Text scanned | Skipped | Findings |",
        "|---|---:|---:|---:|---:|",
    ]
    for report in reports:
        lines.append(
            f"| `{report.root_item}` | {report.files_seen} | {report.text_files_scanned} | "
            f"{report.content_skipped + report.pruned_dirs} | {len(report.findings)} |"
        )
    lines.extend(["", "## Findings", ""])
    for report in reports:
        visible = [finding for finding in report.findings if finding.severity in {"fail", "warn"}]
        if not visible:
            continue
        lines.append(f"### {report.root_item}")
        for finding in visible:
            where = f"{finding.path}:{finding.line}" if finding.line else finding.path
            lines.append(f"- `{finding.severity}` `{finding.category}` `{where}`: {finding.detail}")
        lines.append("")
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return json_path, md_path


def main() -> int:
    global ROOT, REPORT_DIR
    parser = argparse.ArgumentParser(description="Folder-by-folder security audit for <your-willind-root>.")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--json", action="store_true", help="Print compact JSON summary.")
    args = parser.parse_args()

    ROOT = args.root.resolve()
    REPORT_DIR = ROOT / "runtime" / "security"

    root_items = sorted(ROOT.iterdir(), key=lambda item: item.name.lower())
    reports = [audit_item(item) for item in root_items]
    json_path, md_path = write_reports(reports)
    summary = {
        "ok": severity_counts(reports).get("fail", 0) == 0,
        "counts": severity_counts(reports),
        "json_report": str(json_path),
        "markdown_report": str(md_path),
        "root_items": len(reports),
    }
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(f"ok={summary['ok']}")
        print(f"counts={summary['counts']}")
        print(f"json_report={json_path}")
        print(f"markdown_report={md_path}")
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
