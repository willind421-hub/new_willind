from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from github_release_prep_check import REQUIRED_IGNORE_GROUPS, format_text, scan_root


def write_release_gitignore(root: Path) -> None:
    patterns: list[str] = []
    for group_patterns in REQUIRED_IGNORE_GROUPS.values():
        patterns.extend(group_patterns)
    root.joinpath(".gitignore").write_text("\n".join(dict.fromkeys(patterns)) + "\n", encoding="utf-8")


def finding_codes(report) -> set[str]:
    return {finding.code for finding in report.findings}


def test_scan_reports_candidates_without_secret_content(tmp_path: Path) -> None:
    write_release_gitignore(tmp_path)
    tmp_path.joinpath(".env").write_text("TOKEN=SUPERSECRET_VALUE_SHOULD_NOT_LEAK\n", encoding="utf-8")
    tmp_path.joinpath("credentials.json").write_text('{"password":"SUPERSECRET_JSON"}\n', encoding="utf-8")
    tmp_path.joinpath("local.db").write_text("SUPERSECRET_DB_PAYLOAD\n", encoding="utf-8")
    tmp_path.joinpath("models").mkdir()

    report = scan_root(tmp_path, include_git_history=False)
    payload = json.dumps(report.to_dict(), ensure_ascii=False)

    assert report.status == "fail"
    assert "SUPERSECRET" not in payload
    assert ".env" in payload
    assert "credentials.json" in payload
    assert "local.db" in payload
    assert "models" in payload
    assert {
        "secret_filename_candidates",
        "database_candidates",
        "large_model_candidates",
    }.issubset(finding_codes(report))


def test_clean_tree_warns_when_git_metadata_is_unavailable(tmp_path: Path) -> None:
    write_release_gitignore(tmp_path)
    tmp_path.joinpath("README.md").write_text("# clean\n", encoding="utf-8")

    report = scan_root(tmp_path, include_git_history=False)

    assert report.status == "warn"
    assert finding_codes(report) == {"git_context"}


def test_text_output_uses_ok_warn_fail_labels(tmp_path: Path) -> None:
    write_release_gitignore(tmp_path)
    tmp_path.joinpath(".secrets").mkdir()

    report = scan_root(tmp_path, include_git_history=False)
    text = format_text(report)

    assert "status=fail" in text
    assert "FAIL secret_filename_candidates" in text
    assert "WARN git_context" in text
