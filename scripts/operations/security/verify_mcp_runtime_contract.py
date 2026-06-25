from __future__ import annotations

import importlib.util
import json
import shutil
import sqlite3
import sys
from pathlib import Path
from typing import Any

import yaml


ROOT = next((p for p in Path(__file__).resolve().parents if (p / "registry" / "_index.yaml").exists()), Path(__file__).resolve().parent)
BACKEND = ROOT / "<your-backend>"
SERVICE_REGISTRY = ROOT / "registry/services/mcp-runtime-state.yaml"
INDEX = ROOT / "registry/_index.yaml"
SERVICE_SOURCE = BACKEND / "services/mcp_runtime_state.py"
ROUTER_SOURCE = BACKEND / "routers/mcp_runtime.py"
FIXTURE_ROOT = ROOT / "runtime" / "contract-fixtures" / "mcp-runtime-contract"


def load_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return data if isinstance(data, dict) else {}


def load_module() -> Any:
    sys.path.insert(0, str(BACKEND))
    spec = importlib.util.spec_from_file_location("willind_mcp_runtime_contract_subject", SERVICE_SOURCE)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {SERVICE_SOURCE}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def check_registry(registry: dict[str, Any], failures: list[str]) -> None:
    if registry.get("contract") != "willind.mcp_runtime_state_service":
        failures.append("registry contract must be willind.mcp_runtime_state_service")

    boundaries = registry.get("boundaries")
    if not isinstance(boundaries, dict):
        failures.append("boundaries must be a mapping")
        return
    expected = {
        "read_only": True,
        "starts_services": False,
        "stops_services": False,
        "mutates_db": False,
        "writes_local_control_state": True,
        "executes_mcp_tools": False,
        "reads_message_bodies": False,
        "reads_secret_files": False,
        "reads_env_values": False,
        "db_schema_and_counts_only": True,
    }
    for key, value in expected.items():
        if boundaries.get(key) is not value:
            failures.append(f"boundaries.{key} must be {value!r}")

    entrypoints = registry.get("entrypoints") if isinstance(registry.get("entrypoints"), dict) else {}
    api_paths = entrypoints.get("api_paths") if isinstance(entrypoints.get("api_paths"), list) else []
    for path in ("/api/mcp-runtime/state", "/api/mcp-runtime/control", "/api/action-runtime/actions/request_mcp_service_control"):
        if path not in api_paths:
            failures.append(f"mcp-runtime registry missing API path: {path}")


def check_source(failures: list[str]) -> None:
    source = SERVICE_SOURCE.read_text(encoding="utf-8")
    for fragment in ("load_dotenv", "os.getenv", "os.environ", "subprocess", "pm2", "server.tool("):
        if fragment in source:
            failures.append(f"mcp_runtime_state.py must not contain execution/secret fragment: {fragment}")
    if "SELECT COUNT(*)" not in source:
        failures.append("mcp_runtime_state.py must count rows instead of reading message bodies")
    if "PRAGMA table_info" not in source:
        failures.append("mcp_runtime_state.py must inspect schema only")
    if "write_text" not in source:
        failures.append("mcp_runtime_state.py should only write local control state for control actions")

    router_source = ROUTER_SOURCE.read_text(encoding="utf-8")
    for route_fragment in ('@router.get("/state")', '@router.post("/control")'):
        if route_fragment not in router_source:
            failures.append(f"mcp router missing route: {route_fragment}")


def check_runtime_behavior(failures: list[str]) -> None:
    module = load_module()
    base = _fresh_fixture_root()
    try:
        project = base / "willind-mcp"
        source_dir = project / "src" / "mcp"
        source_dir.mkdir(parents=True)
        (project / "package.json").write_text('{"name":"fixture"}', encoding="utf-8")
        (source_dir / "server.ts").write_text(
            "server.tool('send_message', 'x', {}, async () => {})\n"
            "server.tool('get_messages', 'x', {}, async () => {})\n",
            encoding="utf-8",
        )
        db_path = project / "willind.db"
        connection = sqlite3.connect(db_path)
        try:
            connection.execute(
                "CREATE TABLE messages (id INTEGER PRIMARY KEY, content TEXT, from_capability TEXT, "
                "to_capability TEXT, capability_envelope TEXT)"
            )
            connection.execute("INSERT INTO messages (content) VALUES ('private body must not leak')")
            connection.commit()
        finally:
            connection.close()

        module.CONTROL_STATE_PATH = base / "control-state.json"
        control = module.apply_mcp_runtime_control(
            action="disable_tool",
            tool_name="send_message",
            reason="contract check",
        )
        if control.get("permission", {}).get("serviceRestart") is not False:
            failures.append("MCP control must not restart services")
        if control.get("permission", {}).get("secretRead") is not False:
            failures.append("MCP control must not read secrets")

        payload = module.get_mcp_runtime_state(
            project_path=project,
            db_path=db_path,
            http_probe=lambda url: {"status": "available", "statusCode": 200, "latencyMs": 1},
            port_probe=lambda host, port: {"status": "available", "latencyMs": 1},
        )
        if payload.get("privacy", {}).get("messageBodiesRead") is not False:
            failures.append("MCP state must report messageBodiesRead=false")
        if payload.get("privacy", {}).get("dbSchemaAndCountsOnly") is not True:
            failures.append("MCP state must report dbSchemaAndCountsOnly=true")
        if "private body must not leak" in json.dumps(payload, ensure_ascii=False):
            failures.append("MCP state leaked a message body")
        if payload.get("tools", {}).get("disabledToolNames") != ["send_message"]:
            failures.append("MCP control-state override was not reflected in tool state")
    finally:
        shutil.rmtree(base, ignore_errors=True)


def _fresh_fixture_root() -> Path:
    resolved = FIXTURE_ROOT.resolve()
    runtime_root = (ROOT / "runtime" / "contract-fixtures").resolve()
    if runtime_root not in resolved.parents and resolved != runtime_root:
        raise RuntimeError(f"refusing to reset fixture path outside runtime fixtures: {resolved}")
    if resolved.exists():
        shutil.rmtree(resolved)
    resolved.mkdir(parents=True)
    return resolved


def check_index(failures: list[str]) -> None:
    index = load_yaml(INDEX)
    routes = index.get("route_by_intent") if isinstance(index.get("route_by_intent"), dict) else {}
    route = routes.get("mcp_runtime_state")
    if not isinstance(route, dict):
        failures.append("registry/_index.yaml missing route_by_intent.mcp_runtime_state")
        return
    files = route.get("read") if isinstance(route.get("read"), list) else []
    for expected in (
        "registry/services/mcp-runtime-state.yaml",
        "registry/tools/tool-slot-index.yaml",
        "projects/willind-mcp/src/mcp/server.ts",
        "<your-backend>/services/mcp_runtime_state.py",
    ):
        if expected not in files:
            failures.append(f"mcp_runtime_state route missing file: {expected}")


def run_checks() -> dict[str, Any]:
    failures: list[str] = []
    registry = load_yaml(SERVICE_REGISTRY)
    check_registry(registry, failures)
    check_source(failures)
    check_runtime_behavior(failures)
    check_index(failures)
    return {"ok": not failures, "failures": failures, "warnings": []}


def main() -> int:
    try:
        report = run_checks()
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["ok"] else 1
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
