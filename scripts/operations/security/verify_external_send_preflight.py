#!/usr/bin/env python
"""Verify the external-send preflight contract from the registry.

This check is intentionally metadata-only. It validates that known outbound
adapters are registered with a boundary, a local service file, and tests. It
does not send data, read attachment contents, inspect secrets, or contact
external services.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml


ROOT = next((p for p in Path(__file__).resolve().parents if (p / "registry" / "_index.yaml").exists()), Path(__file__).resolve().parent)
REGISTRY_PATH = ROOT / "registry/services/external-send-preflight.yaml"
PERMISSION_POLICY_PATH = ROOT / "registry/permissions/permission-gate-policy.yaml"
PERMISSION_MATRIX_PATH = ROOT / "docs/security/permission-matrix.json"
ACTION_RUNTIME_PATH = ROOT / "<your-backend>/services/action_runtime.py"
OWNER_SERVICE_PATH = ROOT / "<your-backend>/services/external_send_guard.py"

REQUIRED_EXPECTED_CALLERS = {
    "email_sender",
    "upload_adapter",
    "webhook_adapter",
    "git_push_or_pr_adapter",
    "external_review_exporter",
    "telegram_gateway_when_sending_outward",
    "youtube_automation_runner",
    "gdrive_bridge",
    "gcal_bridge",
    "memo_gcal_bridge",
    "willind_monitor_notifier",
    "willind_mcp_telegram_reply",
    "willind_mcp_discord_mirror",
    "dashboard_pwa_push_notification",
}

PRE_FLIGHT_MARKERS = (
    "preflight_external_send",
    "ExternalSendRequest",
    "preflightExternalSend",
    "assertExternalSendAllowed",
    "preflight_monitor_notification",
    "preflight_youtube_job",
    "external_send_preflight",
)

SENSITIVE_PATH_TOKENS = (
    ".env",
    ".secrets",
    "secret",
    "token",
    "credential",
    "client_secret",
    "private_key",
)


def load_yaml(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def rel(path: Path) -> str:
    return str(path.relative_to(ROOT)).replace("\\", "/")


def add_issue(issues: list[dict[str, str]], path: Path, message: str) -> None:
    issues.append({"path": rel(path), "message": message})


def resolve_under_project(project: str, candidate: str) -> Path:
    project_relative = ROOT / project / candidate
    if project_relative.exists():
        return project_relative
    root_relative = ROOT / candidate
    if root_relative.exists():
        return root_relative
    return project_relative


def safe_text_has_preflight_marker(path: Path) -> bool:
    """Read ordinary source/test files only; never open secret-like paths."""
    lowered = rel(path).lower()
    if any(token in lowered for token in SENSITIVE_PATH_TOKENS):
        return False
    text = path.read_text(encoding="utf-8", errors="ignore")
    return any(marker in text for marker in PRE_FLIGHT_MARKERS)


def endpoint_exists(matrix: dict[str, Any], method: str, path: str) -> bool:
    for router in (matrix.get("routers") or {}).values():
        for endpoint in router.get("endpoints") or []:
            if endpoint.get("method") == method and endpoint.get("path") == path:
                tags = set(endpoint.get("tags") or [])
                return "external_send" in tags and "preflight" in tags
    return False


def main() -> int:
    failures: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []

    for path in (REGISTRY_PATH, PERMISSION_POLICY_PATH, PERMISSION_MATRIX_PATH, ACTION_RUNTIME_PATH, OWNER_SERVICE_PATH):
        if not path.exists():
            add_issue(failures, path, "required external-send preflight contract file is missing")

    if failures:
        print(json.dumps({"ok": False, "failures": failures, "warnings": warnings}, ensure_ascii=False, indent=2))
        return 1

    registry = load_yaml(REGISTRY_PATH)
    permission = load_yaml(PERMISSION_POLICY_PATH)
    matrix = load_json(PERMISSION_MATRIX_PATH)

    owner = registry.get("owner") or {}
    runtime = registry.get("runtime_bridge") or {}
    tests = [str(item) for item in registry.get("tests") or []]
    connectors = owner.get("local_project_connectors") or []

    if registry.get("contract") != "willind.external_send_preflight_service":
        add_issue(failures, REGISTRY_PATH, "unexpected contract id")

    if registry.get("decision", {}).get("canonical_direction") != "inspect_before_any_external_send":
        add_issue(failures, REGISTRY_PATH, "canonical direction must stay inspect_before_any_external_send")

    must_not = set(runtime.get("must_not") or [])
    for forbidden in {"send_email", "publish_post", "call_webhook", "push_git", "upload_file", "read_attachment_content", "print_secret_value"}:
        if forbidden not in must_not:
            add_issue(failures, REGISTRY_PATH, f"runtime must_not is missing {forbidden}")

    expected_callers = set(runtime.get("expected_callers") or [])
    missing_callers = REQUIRED_EXPECTED_CALLERS - expected_callers
    if missing_callers:
        add_issue(failures, REGISTRY_PATH, f"expected_callers missing {sorted(missing_callers)}")

    if runtime.get("outbound_execution") is not False:
        add_issue(failures, REGISTRY_PATH, "preflight action must not execute outbound sends")

    action_text = ACTION_RUNTIME_PATH.read_text(encoding="utf-8", errors="ignore")
    for marker in ("preflight_external_send_candidate", "external_send_preflight_only", "preflight_external_send"):
        if marker not in action_text:
            add_issue(failures, ACTION_RUNTIME_PATH, f"action runtime missing marker {marker}")

    owner_service_text = OWNER_SERVICE_PATH.read_text(encoding="utf-8", errors="ignore")
    for marker in ("SECRET_CONTENT_PATTERNS", "ExternalSendRequest", "preflight_external_send", "_write_audit"):
        if marker not in owner_service_text:
            add_issue(failures, OWNER_SERVICE_PATH, f"external send guard missing marker {marker}")

    if not endpoint_exists(matrix, "POST", "/api/permission/external-send-preflight"):
        add_issue(failures, PERMISSION_MATRIX_PATH, "permission matrix missing tagged preflight endpoint")

    principles = permission.get("principles") or {}
    if principles.get("external_send_requires_content_sensitivity_classification") is not True:
        add_issue(failures, PERMISSION_POLICY_PATH, "external send sensitivity classification principle must be true")
    if principles.get("secret_policy_always_wins") is not True:
        add_issue(failures, PERMISSION_POLICY_PATH, "secret policy must always win")
    if permission.get("action_lifecycle", {}).get("external_send", {}).get("default_decision") != "confirm":
        add_issue(failures, PERMISSION_POLICY_PATH, "external_send lifecycle must default to confirm")
    if permission.get("domains", {}).get("external_send", {}).get("secret_or_credential_send") != "blocked":
        add_issue(failures, PERMISSION_POLICY_PATH, "secret/credential external send must be blocked")

    for test in tests:
        path = ROOT / test
        if not path.exists():
            add_issue(failures, path, "registered preflight test path is missing")

    test_projects = {test.split("/", 2)[0] + "/" + test.split("/", 2)[1] for test in tests if test.startswith("projects/")}
    for connector in connectors:
        project = str(connector.get("project") or "")
        service = str(connector.get("service") or "")
        boundary = str(connector.get("boundary") or "")
        scope = connector.get("scope")

        if not project or not (ROOT / project).exists():
            add_issue(failures, REGISTRY_PATH, f"connector has missing project path: {project!r}")
            continue
        if not service:
            add_issue(failures, REGISTRY_PATH, f"connector {project} is missing service")
            continue

        service_path = resolve_under_project(project, service)
        if not service_path.exists():
            add_issue(failures, service_path, "connector service file is missing")
        elif not safe_text_has_preflight_marker(service_path):
            add_issue(failures, service_path, "connector service does not contain a recognized preflight marker")

        if not boundary:
            add_issue(failures, REGISTRY_PATH, f"connector {project}/{service} is missing boundary")
        if "before" not in boundary and "metadata_only" not in boundary:
            add_issue(failures, REGISTRY_PATH, f"connector {project}/{service} boundary does not state before/metadata_only")
        if not scope:
            add_issue(failures, REGISTRY_PATH, f"connector {project}/{service} is missing scope")

        project_test_key = "/".join(project.split("/")[:2])
        if project_test_key not in test_projects:
            add_issue(failures, REGISTRY_PATH, f"connector {project} has no registered test path")

        for linked_key in ("runner", "router", "linked_service"):
            linked = connector.get(linked_key)
            if linked:
                linked_path = resolve_under_project(project, str(linked))
                if not linked_path.exists():
                    add_issue(failures, linked_path, f"connector {linked_key} path is missing")
        for linked in connector.get("linked_services") or []:
            linked_path = resolve_under_project(project, str(linked))
            if not linked_path.exists():
                add_issue(failures, linked_path, "connector linked service path is missing")

    report = {
        "ok": not failures,
        "failures": failures,
        "warnings": warnings,
        "counts": {
            "connectors": len(connectors),
            "expected_callers": len(expected_callers),
            "tests": len(tests),
            "must_not": len(must_not),
        },
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
