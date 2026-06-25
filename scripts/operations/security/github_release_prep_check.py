#!/usr/bin/env python
"""GitHub release prep scanner for path metadata.

The scanner is intentionally conservative:
- It reads path names, directory names, sizes, .gitignore, and git path metadata.
- It does not open candidate secret/token/credential/private-key files.
- It does not rewrite history, delete files, transmit data, or change accounts.
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable


DEFAULT_ROOT = next((p for p in Path(__file__).resolve().parents if (p / "registry" / "_index.yaml").exists()), Path(__file__).resolve().parent)

SEVERITY_RANK = {"ok": 0, "warn": 1, "fail": 2}

SAFE_ENV_NAMES = {
    ".env.example",
    ".env.sample",
    ".env.template",
    ".env.defaults",
}

SECRET_DIR_NAMES = {
    ".secrets",
    "secrets",
    ".aws",
    ".azure",
    ".gcloud",
    ".kube",
    ".ssh",
}

PRIVATE_KEY_NAMES = {
    "id_rsa",
    "id_dsa",
    "id_ecdsa",
    "id_ed25519",
    "known_hosts",
    "authorized_keys",
}

PRIVATE_KEY_SUFFIXES = {
    ".pem",
    ".key",
    ".p12",
    ".pfx",
    ".ppk",
}

SECRET_CONFIG_SUFFIXES = {
    ".env",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".cfg",
    ".conf",
    ".txt",
}

SECRET_NAME_RE = re.compile(
    r"(?i)(^|[._-])"
    r"(token|tokens|secret|secrets|credential|credentials|client_secret|oauth|api_key|apikey|passwd|password)"
    r"([._-]|$)"
)

DATABASE_SUFFIXES = {
    ".db",
    ".sqlite",
    ".sqlite3",
    ".duckdb",
    ".mdb",
}

DATABASE_EXTRA_SUFFIXES = {
    ".db-shm",
    ".db-wal",
    ".sqlite-shm",
    ".sqlite-wal",
}

MODEL_SUFFIXES = {
    ".gguf",
    ".ggml",
    ".safetensors",
    ".pt",
    ".pth",
    ".onnx",
    ".tflite",
}

DEPENDENCY_DIR_NAMES = {
    "node_modules",
    ".venv",
    "venv",
    ".venv-",
    "__pypackages__",
}

BROWSER_PROFILE_DIR_NAMES = {
    ".browser-profiles",
    "browser-profiles",
    "chrome-user-data",
    "user-data-dir",
}

UPLOAD_LOG_DIR_NAMES = {
    "uploads",
    "upload",
    "logs",
    "log",
}

PRUNE_DIR_NAMES = (
    SECRET_DIR_NAMES
    | DEPENDENCY_DIR_NAMES
    | BROWSER_PROFILE_DIR_NAMES
    | UPLOAD_LOG_DIR_NAMES
    | {"models", ".git", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
)

REQUIRED_IGNORE_GROUPS: dict[str, tuple[str, ...]] = {
    "env_and_secret_files": (
        ".env",
        ".env.*",
        ".secrets/",
        "*.pem",
        "*.key",
        "*.p12",
        "*.pfx",
        "*.tokens.json",
        "*token*.json",
        "*secret*.json",
        "*credential*.json",
        "client_secret*.json",
        ".npmrc",
    ),
    "databases": ("*.db", "*.sqlite", "*.sqlite3", "*.db-shm", "*.db-wal"),
    "browser_profiles": (".browser-profiles/", "browser-profiles/", "**/browser-profiles/"),
    "dependencies": ("node_modules/", "**/node_modules/", ".venv/", "**/.venv/", "**/*_venv/"),
    "uploads_and_logs": ("uploads/", "**/uploads/", "logs/", "**/logs/", "*.log"),
    "large_models": ("models/", "**/*.gguf", "**/*.safetensors", "**/*.pt", "**/*.pth", "**/*.onnx"),
}


@dataclass
class PathMeta:
    rel: str
    is_dir: bool
    is_file: bool
    is_symlink: bool
    size: int = 0


@dataclass
class Finding:
    code: str
    status: str
    message: str
    count: int = 0
    paths: list[str] = field(default_factory=list)
    detail: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "code": self.code,
            "status": self.status,
            "message": self.message,
            "count": self.count,
            "paths": self.paths,
            "detail": self.detail,
        }


@dataclass
class Report:
    root: str
    status: str
    scanned_paths: int
    findings: list[Finding]

    def to_dict(self) -> dict[str, object]:
        return {
            "root": self.root,
            "status": self.status,
            "scanned_paths": self.scanned_paths,
            "findings": [finding.to_dict() for finding in self.findings],
        }


def normalize_rel(path: str | Path) -> str:
    value = str(path).replace("\\", "/")
    while value.startswith("./"):
        value = value[2:]
    return value or "."


def redact_path(rel: str) -> str:
    safe = normalize_rel(rel)
    return re.sub(r"(?<![A-Za-z0-9])[A-Za-z0-9_-]{32,}(?![A-Za-z0-9])", "<redacted-id>", safe)


def lower_parts(rel: str) -> tuple[str, ...]:
    return tuple(part.lower() for part in normalize_rel(rel).split("/") if part)


def suffix_of(base: str) -> str:
    lower = base.lower()
    for extra in DATABASE_EXTRA_SUFFIXES:
        if lower.endswith(extra):
            return extra
    return Path(lower).suffix


def is_safe_env_name(base: str) -> bool:
    lower = base.lower()
    if lower in SAFE_ENV_NAMES:
        return True
    return lower.startswith(".env.") and lower.endswith((".example", ".sample", ".template", ".defaults"))


def is_secret_filename(rel: str, is_dir: bool | None = None) -> bool:
    parts = lower_parts(rel)
    if not parts:
        return False
    base = parts[-1]
    if base in SAFE_ENV_NAMES or is_safe_env_name(base):
        return False
    if base == ".env" or base.startswith(".env."):
        return True
    if base in {".npmrc", ".pypirc", ".netrc", "_netrc", ".mcp.json"}:
        return True
    if any(part in SECRET_DIR_NAMES for part in parts):
        return True
    if base.startswith("client_secret") and base.endswith(".json"):
        return True
    suffix = suffix_of(base)
    return suffix in SECRET_CONFIG_SUFFIXES and bool(SECRET_NAME_RE.search(base))


def is_private_key_filename(rel: str) -> bool:
    parts = lower_parts(rel)
    if not parts:
        return False
    base = parts[-1]
    return base in PRIVATE_KEY_NAMES or suffix_of(base) in PRIVATE_KEY_SUFFIXES


def is_database_filename(rel: str) -> bool:
    suffix = suffix_of(lower_parts(rel)[-1]) if lower_parts(rel) else ""
    return suffix in DATABASE_SUFFIXES or suffix in DATABASE_EXTRA_SUFFIXES


def is_model_candidate(rel: str, size: int, large_file_bytes: int) -> bool:
    parts = lower_parts(rel)
    if not parts:
        return False
    base = parts[-1]
    if "models" in parts:
        return True
    if suffix_of(base) in MODEL_SUFFIXES:
        return True
    return size >= large_file_bytes and suffix_of(base) == ".bin" and any(
        part in {"model", "models", "llm", "weights"} or "model" in part for part in parts
    )


def is_browser_profile(rel: str) -> bool:
    parts = lower_parts(rel)
    return any(part in BROWSER_PROFILE_DIR_NAMES for part in parts)


def is_dependency_cache(rel: str) -> bool:
    parts = lower_parts(rel)
    return any(
        part in {"node_modules", ".venv", "venv", "__pypackages__"}
        or part.startswith(".venv-")
        or part.endswith("_venv")
        or part.endswith("-venv")
        for part in parts
    )


def is_upload_or_log(rel: str) -> bool:
    parts = lower_parts(rel)
    if any(part in UPLOAD_LOG_DIR_NAMES for part in parts):
        return True
    return bool(parts and parts[-1].lower().endswith(".log"))


def path_categories(rel: str, *, is_dir: bool | None, size: int = 0, large_file_bytes: int) -> set[str]:
    categories: set[str] = set()
    if is_secret_filename(rel, is_dir):
        categories.add("secret_filename_candidates")
    if is_private_key_filename(rel):
        categories.add("private_key_filename_candidates")
    if is_database_filename(rel):
        categories.add("database_candidates")
    if is_model_candidate(rel, size, large_file_bytes):
        categories.add("large_model_candidates")
    if is_browser_profile(rel):
        categories.add("browser_profile_candidates")
    if is_dependency_cache(rel):
        categories.add("dependency_cache_candidates")
    if is_upload_or_log(rel):
        categories.add("upload_log_candidates")
    return categories


def should_prune(meta: PathMeta) -> bool:
    if not meta.is_dir or meta.is_symlink:
        return True
    parts = lower_parts(meta.rel)
    if not parts:
        return False
    base = parts[-1]
    return (
        base in PRUNE_DIR_NAMES
        or base.startswith(".venv-")
        or base.endswith("_venv")
        or base.endswith("-venv")
    )


def iter_metadata(root: Path, max_paths: int) -> tuple[list[PathMeta], list[str], bool]:
    metas: list[PathMeta] = []
    errors: list[str] = []
    limit_hit = False
    stack = [root]
    root_str = str(root)

    while stack:
        current = stack.pop()
        try:
            entries = list(os.scandir(current))
        except OSError as exc:
            rel = os.path.relpath(current, root_str)
            errors.append(f"{redact_path(rel)}: {exc.__class__.__name__}")
            continue

        for entry in entries:
            if len(metas) >= max_paths:
                limit_hit = True
                return metas, errors, limit_hit
            try:
                stat_result = entry.stat(follow_symlinks=False)
            except OSError as exc:
                rel = os.path.relpath(entry.path, root_str)
                errors.append(f"{redact_path(rel)}: {exc.__class__.__name__}")
                continue

            rel = normalize_rel(os.path.relpath(entry.path, root_str))
            is_symlink = entry.is_symlink()
            is_dir = entry.is_dir(follow_symlinks=False)
            is_file = entry.is_file(follow_symlinks=False)
            meta = PathMeta(rel=rel, is_dir=is_dir, is_file=is_file, is_symlink=is_symlink, size=stat_result.st_size)
            metas.append(meta)
            if is_dir and not should_prune(meta):
                stack.append(Path(entry.path))

    return metas, errors, limit_hit


def run_git(root: Path, args: list[str]) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=str(root),
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )
    except OSError as exc:
        return 127, "", str(exc)
    return proc.returncode, proc.stdout, proc.stderr


def git_is_available(root: Path) -> bool:
    code, _, _ = run_git(root, ["rev-parse", "--is-inside-work-tree"])
    return code == 0


def git_path_list(root: Path, args: list[str], *, nul: bool) -> list[str]:
    code, stdout, _ = run_git(root, args)
    if code != 0:
        return []
    if nul:
        return [normalize_rel(item) for item in stdout.split("\0") if item]
    return [normalize_rel(line.strip()) for line in stdout.splitlines() if line.strip()]


def load_gitignore(root: Path) -> tuple[list[str], bool]:
    path = root / ".gitignore"
    if not path.exists():
        return [], False
    text = path.read_text(encoding="utf-8", errors="replace")
    patterns: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("!"):
            continue
        patterns.append(normalize_rel(stripped))
    return patterns, True


def pattern_present(patterns: Iterable[str], expected: str) -> bool:
    expected_norm = normalize_rel(expected)
    expected_tail = expected_norm.removeprefix("**/")
    for pattern in patterns:
        norm = normalize_rel(pattern)
        if norm == expected_norm or norm == expected_tail:
            return True
        if fnmatch.fnmatch(expected_tail, norm) or fnmatch.fnmatch(expected_norm, norm):
            return True
    return False


def gitignore_missing_groups(root: Path) -> tuple[dict[str, list[str]], bool]:
    patterns, present = load_gitignore(root)
    missing: dict[str, list[str]] = {}
    for group, expected_patterns in REQUIRED_IGNORE_GROUPS.items():
        group_missing = [pattern for pattern in expected_patterns if not pattern_present(patterns, pattern)]
        if group_missing:
            missing[group] = group_missing
    return missing, present


def append_category_findings(
    findings: list[Finding],
    bucket: dict[str, list[str]],
    messages: dict[str, str],
    max_examples: int,
) -> None:
    for code in (
        "secret_filename_candidates",
        "private_key_filename_candidates",
        "database_candidates",
        "large_model_candidates",
        "browser_profile_candidates",
        "dependency_cache_candidates",
        "upload_log_candidates",
    ):
        paths = sorted(set(bucket.get(code, [])))
        if not paths:
            continue
        findings.append(
            Finding(
                code=code,
                status="fail",
                message=messages[code],
                count=len(paths),
                paths=[redact_path(path) for path in paths[:max_examples]],
                detail={"examples_limited": len(paths) > max_examples},
            )
        )


def risky_paths_from_list(paths: Iterable[str], large_file_bytes: int) -> list[str]:
    risky: list[str] = []
    for rel in paths:
        if path_categories(rel, is_dir=None, large_file_bytes=large_file_bytes):
            risky.append(rel)
    return sorted(set(risky))


def scan_root(
    root: Path,
    *,
    max_examples: int = 20,
    max_paths: int = 200_000,
    large_file_mb: int = 100,
    include_git_history: bool = True,
) -> Report:
    root = root.resolve()
    large_file_bytes = large_file_mb * 1024 * 1024
    findings: list[Finding] = []

    if not root.exists():
        return Report(
            root=str(root),
            status="fail",
            scanned_paths=0,
            findings=[
                Finding(
                    code="root_missing",
                    status="fail",
                    message="scan root does not exist",
                    count=1,
                    paths=[redact_path(str(root))],
                )
            ],
        )

    metas, errors, limit_hit = iter_metadata(root, max_paths)
    bucket: dict[str, list[str]] = {}
    symlinks: list[str] = []

    for meta in metas:
        if meta.is_symlink:
            symlinks.append(meta.rel)
        for category in path_categories(
            meta.rel,
            is_dir=meta.is_dir,
            size=meta.size if meta.is_file else 0,
            large_file_bytes=large_file_bytes,
        ):
            bucket.setdefault(category, []).append(meta.rel)

    append_category_findings(
        findings,
        bucket,
        {
            "secret_filename_candidates": "secret/env/token/credential path names require removal or strict local-only handling",
            "private_key_filename_candidates": "private key path names require removal and key rotation review",
            "database_candidates": "database files should not be part of the public release tree",
            "large_model_candidates": "large model or model-like assets should stay outside the public release tree",
            "browser_profile_candidates": "browser profiles may contain cookies, sessions, cache, or account state",
            "dependency_cache_candidates": "dependency caches and virtual environments should not be released",
            "upload_log_candidates": "uploads and logs can contain user data, traces, or local state",
        },
        max_examples,
    )

    if symlinks:
        findings.append(
            Finding(
                code="symlink_candidates",
                status="warn",
                message="symlinks need manual review before public release",
                count=len(symlinks),
                paths=[redact_path(path) for path in sorted(symlinks)[:max_examples]],
                detail={"examples_limited": len(symlinks) > max_examples},
            )
        )

    if errors:
        findings.append(
            Finding(
                code="path_read_errors",
                status="warn",
                message="some paths could not be inspected at metadata level",
                count=len(errors),
                paths=errors[:max_examples],
                detail={"examples_limited": len(errors) > max_examples},
            )
        )

    if limit_hit:
        findings.append(
            Finding(
                code="scan_limit",
                status="warn",
                message="path scan stopped at max path limit",
                count=max_paths,
                detail={"max_paths": max_paths},
            )
        )

    missing_groups, gitignore_present = gitignore_missing_groups(root)
    if not gitignore_present:
        findings.append(
            Finding(
                code="gitignore_missing",
                status="fail",
                message=".gitignore is missing; release exclusions cannot be verified",
                count=1,
            )
        )
    elif missing_groups:
        findings.append(
            Finding(
                code="gitignore_release_guards",
                status="warn",
                message=".gitignore is missing one or more release guard patterns",
                count=sum(len(items) for items in missing_groups.values()),
                detail=missing_groups,
            )
        )

    if git_is_available(root):
        tracked_paths = git_path_list(root, ["ls-files", "-z"], nul=True)
        tracked_risky = risky_paths_from_list(tracked_paths, large_file_bytes)
        if tracked_risky:
            findings.append(
                Finding(
                    code="git_tracked_risk_paths",
                    status="fail",
                    message="git currently tracks path names that match release risk criteria",
                    count=len(tracked_risky),
                    paths=[redact_path(path) for path in tracked_risky[:max_examples]],
                    detail={"examples_limited": len(tracked_risky) > max_examples},
                )
            )

        if include_git_history:
            history_paths = git_path_list(root, ["log", "--all", "--name-only", "--pretty=format:"], nul=False)
            history_risky = risky_paths_from_list(history_paths, large_file_bytes)
            if history_risky:
                findings.append(
                    Finding(
                        code="git_history_risk_paths",
                        status="fail",
                        message="git history contains path names that match release risk criteria; rewrite is manual only",
                        count=len(history_risky),
                        paths=[redact_path(path) for path in history_risky[:max_examples]],
                        detail={"examples_limited": len(history_risky) > max_examples},
                    )
                )
    else:
        findings.append(
            Finding(
                code="git_context",
                status="warn",
                message="scan root is not a git working tree; tracked files and history path checks were not verified",
                count=1,
            )
        )

    status = "ok"
    for finding in findings:
        if SEVERITY_RANK[finding.status] > SEVERITY_RANK[status]:
            status = finding.status

    return Report(root=str(root), status=status, scanned_paths=len(metas), findings=findings)


def format_text(report: Report) -> str:
    lines = [
        f"status={report.status}",
        f"root={report.root}",
        f"scanned_paths={report.scanned_paths}",
    ]
    if not report.findings:
        lines.append("OK no release-risk path metadata found")
        return "\n".join(lines)

    for finding in report.findings:
        lines.append("")
        lines.append(f"{finding.status.upper()} {finding.code} count={finding.count}")
        lines.append(f"  {finding.message}")
        for path in finding.paths:
            lines.append(f"  - {path}")
        if finding.detail:
            lines.append(f"  detail={json.dumps(finding.detail, ensure_ascii=False, sort_keys=True)}")
    return "\n".join(lines)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Pre-GitHub release path metadata scanner")
    parser.add_argument("--root", default=str(DEFAULT_ROOT), help="release root to scan")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument("--max-examples", type=int, default=20)
    parser.add_argument("--max-paths", type=int, default=200_000)
    parser.add_argument("--large-file-mb", type=int, default=100)
    parser.add_argument("--skip-git-history", action="store_true", help="skip git history path-name check")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    report = scan_root(
        Path(args.root),
        max_examples=max(1, args.max_examples),
        max_paths=max(1, args.max_paths),
        large_file_mb=max(1, args.large_file_mb),
        include_git_history=not args.skip_git_history,
    )
    if args.format == "json":
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(format_text(report))
    return 0 if report.status in {"ok", "warn"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
