from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from typing import Any

import yaml


ROOT = next((p for p in Path(__file__).resolve().parents if (p / "registry" / "_index.yaml").exists()), Path(__file__).resolve().parent)
BACKEND = ROOT / "<your-backend>"
TOOL_INDEX = ROOT / "registry/tools/tool-slot-index.yaml"
PERMISSION_GATEWAY = BACKEND / "services/permission_gateway.py"
INDEX_FILE = ROOT / "registry/_index.yaml"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _load_yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(_read(path)) or {}


def _load_permission_gateway():
    if str(BACKEND) not in sys.path:
        sys.path.insert(0, str(BACKEND))
    return importlib.import_module("services.permission_gateway")


def verify() -> dict[str, Any]:
    failures: list[str] = []

    for path in (TOOL_INDEX, PERMISSION_GATEWAY, INDEX_FILE):
        if not path.exists():
            failures.append(f"missing file: {path}")

    payload = _load_yaml(TOOL_INDEX) if TOOL_INDEX.exists() else {}
    policy = payload.get("visibility_policy") or {}
    slots = payload.get("tool_slots") or []

    if policy.get("contract") != "willind.tool_visibility_policy":
        failures.append("tool visibility registry contract mismatch")
    if policy.get("caller_model") != "permission_envelope_not_department":
        failures.append("tool visibility must use permission envelope, not department model")
    if policy.get("default_for_low_trust_callers") != "hide_or_block_dangerous_tools":
        failures.append("low-trust caller default must hide or block dangerous tools")

    expected_patterns = {
        "mcp__*",
        "shell",
        "powershell",
        "cmd",
        "bash",
        "python",
        "file.write",
        "file.delete",
        "manage_mcp",
        "send_email",
        "reply_to_email",
        "payment",
        "account",
    }
    configured_patterns = set(policy.get("public_block_patterns") or [])
    missing_patterns = sorted(expected_patterns - configured_patterns)
    failures.extend(f"registry missing public block pattern: {item}" for item in missing_patterns)

    expected_domains = {"filesystem", "action_execution", "device_mesh", "fabrication", "provider_config", "mcp_management", "external_send", "account", "payment"}
    configured_domains = set(policy.get("public_blocked_domains") or [])
    missing_domains = sorted(expected_domains - configured_domains)
    failures.extend(f"registry missing public blocked domain: {item}" for item in missing_domains)

    expected_permissions = {"confirm", "deny", "strong_confirm", "confirm_or_block", "strong_confirm_or_block"}
    configured_permissions = set(policy.get("public_blocked_permissions") or [])
    missing_permissions = sorted(expected_permissions - configured_permissions)
    failures.extend(f"registry missing public blocked permission: {item}" for item in missing_permissions)

    try:
        pg = _load_permission_gateway()
    except Exception as exc:  # pragma: no cover - reported in JSON
        failures.append(f"permission gateway import failed: {exc}")
        pg = None

    function_checks: dict[str, Any] = {}
    if pg is not None:
        checks = {
            "user_admin": pg.owner_is_admin_or_single_user("사용자") is True,
            "external_not_admin": pg.owner_is_admin_or_single_user("external") is False,
            "mcp_pattern_blocked": pg.is_public_blocked_tool("mcp__filesystem.read") is True,
            "python_blocked": pg.is_public_blocked_tool("python_exec") is True,
            "safe_search_visible": pg.is_public_blocked_tool("safe_search", {"domain": "research", "default_permission": "safe"}) is False,
            "filesystem_confirm_blocked": pg.is_public_blocked_tool("file", {"domain": "filesystem", "default_permission": "confirm"}) is True,
            "payment_blocked": pg.is_public_blocked_tool("checkout") is True,
            "external_send_blocked": pg.is_public_blocked_tool("send_email") is True,
        }
        for name, ok in checks.items():
            if not ok:
                failures.append(f"function check failed: {name}")
        function_checks = checks

        if isinstance(slots, list):
            external_view = pg.filter_visible_tools_for_owner("external", slots)
            user_view = pg.filter_visible_tools_for_owner("사용자", slots)
            visible_external = {tool.get("id") for tool in external_view.get("visible", [])}
            blocked_external = {tool.get("id") for tool in external_view.get("blocked", [])}
            user_visible = {tool.get("id") for tool in user_view.get("visible", [])}

            for required in ("file", "action-runtime", "secure-mesh", "3d-forge"):
                if required not in blocked_external:
                    failures.append(f"external caller should not see dangerous slot: {required}")
            if "browser" not in visible_external:
                failures.append("external caller should still see safe browser slot")
            slot_ids = {slot.get("id") for slot in slots if isinstance(slot, dict)}
            if user_visible != slot_ids:
                failures.append("user should see all registry tool slots")

            function_checks["external_visible_count"] = len(visible_external)
            function_checks["external_blocked_count"] = len(blocked_external)
            function_checks["user_visible_count"] = len(user_visible)

    index_text = _read(INDEX_FILE) if INDEX_FILE.exists() else ""
    if "tool_visibility_policy:" not in index_text:
        failures.append("registry index missing tool_visibility_policy route")

    return {
        "ok": not failures,
        "contract": "willind.tool_visibility_contract_verification",
        "failures": failures,
        "checked": {
            "tool_index": str(TOOL_INDEX),
            "permission_gateway": str(PERMISSION_GATEWAY),
            "slots": len(slots) if isinstance(slots, list) else 0,
            "function_checks": function_checks,
        },
    }


def main() -> int:
    result = verify()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

