from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import yaml


ROOT = next((p for p in Path(__file__).resolve().parents if (p / "registry" / "_index.yaml").exists()), Path(__file__).resolve().parent)
SERVICE_REGISTRY = ROOT / "registry/services/provider-probe.yaml"
PROVIDER_ROUTING = ROOT / "registry/providers/provider-cli-routing.yaml"
SKILL_PROVIDER_ROUTING = ROOT / "registry/providers/skill-provider-routing.yaml"
PROVIDER_BOOTSTRAP = ROOT / "registry/providers/provider-bootstrap.yaml"
INDEX = ROOT / "registry/_index.yaml"
SERVICE_SOURCE = ROOT / "<your-backend>/services/provider_probe.py"
ROUTER_SOURCE = ROOT / "<your-backend>/routers/provider_probe.py"

EXPECTED_PROVIDERS = {
    "willind_ai_rules",
    "codex_cli",
    "claude_cli",
    "openai_api",
    "gemini_api_or_browser",
    "local_llm",
    "browser_session",
    "service_supervisor",
    "tool_slot_runtime",
}

OPTIONAL_PROVIDER_IDS = {"opencode_cli", "openhands_workspace"}


def load_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return data if isinstance(data, dict) else {}


def load_provider_probe_module() -> Any:
    spec = importlib.util.spec_from_file_location("willind_provider_probe_contract_subject", SERVICE_SOURCE)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {SERVICE_SOURCE}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def check_registry_boundaries(registry: dict[str, Any], failures: list[str]) -> None:
    if registry.get("contract") != "willind.provider_probe_service":
        failures.append("registry contract must be willind.provider_probe_service")

    boundaries = registry.get("boundaries")
    if not isinstance(boundaries, dict):
        failures.append("boundaries must be a mapping")
        return

    expected = {
        "read_only": True,
        "starts_services": False,
        "stops_services": False,
        "executes_provider": False,
        "reads_secret_files": False,
        "reads_env_values": False,
        "reads_env_key_names_only": True,
        "calls_paid_remote_api": False,
    }
    for key, value in expected.items():
        if boundaries.get(key) is not value:
            failures.append(f"boundaries.{key} must be {value!r}")

    routing = registry.get("routing_snapshot")
    if not isinstance(routing, dict):
        failures.append("routing_snapshot must be a mapping")
        return
    if routing.get("calls_paid_remote_api") is not False:
        failures.append("routing_snapshot.calls_paid_remote_api must be false")
    if routing.get("executes_provider") is not False:
        failures.append("routing_snapshot.executes_provider must be false")

    recovery = registry.get("runtime_recovery")
    if not isinstance(recovery, dict):
        failures.append("runtime_recovery must be a mapping")
        return
    expected_recovery = {
        "bounded_launcher": "scripts/operations/providers/ensure_required_provider_runtimes.py",
        "starts_services_by_default": False,
        "start_flag_required": "--start",
        "starts_only_required_local_providers": True,
        "owned_process_cleanup_on_failed_start": True,
    }
    for key, value in expected_recovery.items():
        if recovery.get(key) != value:
            failures.append(f"runtime_recovery.{key} must be {value!r}")


def check_provider_registry(failures: list[str], warnings: list[str]) -> None:
    routing = load_yaml(PROVIDER_ROUTING)
    providers = routing.get("providers") if isinstance(routing.get("providers"), dict) else {}
    missing = sorted(EXPECTED_PROVIDERS - set(providers))
    if missing:
        failures.append(f"provider-cli-routing missing providers: {', '.join(missing)}")

    for provider_id, provider in providers.items():
        if not isinstance(provider, dict):
            failures.append(f"providers.{provider_id} must be a mapping")
            continue
        safety = provider.get("safety")
        if not isinstance(safety, dict):
            failures.append(f"providers.{provider_id}.safety must be a mapping")
            continue
        if provider_id in {"openai_api", "gemini_api_or_browser"} and safety.get("paid_action") != "blocked":
            failures.append(f"providers.{provider_id}.safety.paid_action must stay blocked")

    missing_optional = sorted(OPTIONAL_PROVIDER_IDS - set(providers))
    if missing_optional:
        warnings.append(f"optional provider IDs not in provider-cli-routing: {', '.join(missing_optional)}")

    skill_provider = load_yaml(SKILL_PROVIDER_ROUTING)
    role_ids = set((skill_provider.get("provider_roles") or {}).keys())
    for expected in ("codex", "claude", "gemini", "local", "browser"):
        if expected not in role_ids:
            failures.append(f"skill-provider-routing missing provider role: {expected}")

    bootstrap = load_yaml(PROVIDER_BOOTSTRAP)
    profiles = bootstrap.get("profiles") if isinstance(bootstrap.get("profiles"), dict) else {}
    for expected in ("common", "codex_cli", "claude_cli", "openai_api", "gemini_api_or_browser", "local_llm", "browser_session"):
        if expected not in profiles:
            failures.append(f"provider-bootstrap missing profile: {expected}")


def check_source_boundaries(failures: list[str]) -> None:
    source = SERVICE_SOURCE.read_text(encoding="utf-8")
    banned_fragments = [
        "dotenv",
        "load_dotenv",
        "os.getenv",
        "os.environ.get",
        "os.environ[",
        "OPENAI_API_KEY\" in os.environ",
        "GEMINI_API_KEY\" in os.environ",
    ]
    for fragment in banned_fragments:
        if fragment in source:
            failures.append(f"provider_probe.py must not contain secret-value access fragment: {fragment}")

    if "os.environ.keys()" not in source:
        failures.append("provider_probe.py should only inspect environment key names via os.environ.keys()")
    if "httpx.get" not in source:
        failures.append("provider_probe.py should use bounded local HTTP health probes")
    if "timeout=timeout" not in source:
        failures.append("local HTTP probes must have an explicit timeout")

    module = load_provider_probe_module()
    endpoints = getattr(module, "LOCAL_HTTP_PROBES", {})
    if not isinstance(endpoints, dict):
        failures.append("LOCAL_HTTP_PROBES must be a mapping")
        return
    for provider_id, url in endpoints.items():
        if not str(url).startswith("http://127.0.0.1:"):
            failures.append(f"LOCAL_HTTP_PROBES.{provider_id} must be localhost-only, got {url}")


def check_runtime_behavior(failures: list[str]) -> None:
    module = load_provider_probe_module()

    payload = module.get_provider_runtime_probe(
        env_keys={"OPENAI_API_KEY"},
        command_resolver=lambda command: f"C:/fake/{command}.exe" if command == "codex" else None,
        http_probe=lambda url: {"status": "available", "latencyMs": 3, "reason": "fixture"},
    )
    if payload.get("secretPolicy", {}).get("envValuesRead") is not False:
        failures.append("runtime probe must report envValuesRead=false")
    if payload.get("secretPolicy", {}).get("secretFilesRead") is not False:
        failures.append("runtime probe must report secretFilesRead=false")
    if payload.get("secretPolicy", {}).get("paidRemoteApisCalled") is not False:
        failures.append("runtime probe must report paidRemoteApisCalled=false")

    providers = {item["id"]: item for item in payload.get("providers", []) if isinstance(item, dict)}
    if providers.get("openai_api", {}).get("env", {}).get("presentKeyNames") != ["OPENAI_API_KEY"]:
        failures.append("openai_api must expose present key names only")
    if "OPENAI_API_KEY" not in providers.get("openai_api", {}).get("env", {}).get("requiredKeyNames", []):
        failures.append("openai_api required key names missing")
    if providers.get("codex_cli", {}).get("status") != "available":
        failures.append("codex_cli fixture should be available")
    if providers.get("claude_cli", {}).get("status") != "unavailable":
        failures.append("claude_cli fixture should be unavailable")

    routing = module.get_provider_runtime_routing(
        "coding_implementation",
        env_keys=set(),
        command_resolver=lambda command: f"C:/fake/{command}.exe" if command == "codex" else None,
        http_probe=lambda url: {"status": "unavailable", "latencyMs": 900, "reason": "fixture unavailable"},
    )
    if routing.get("source", {}).get("remotePaidCalls") is not False:
        failures.append("routing source must report remotePaidCalls=false")
    if routing.get("recommended", {}).get("provider") != "codex_cli":
        failures.append("coding_implementation fixture should recommend codex_cli")
    candidates = {item["provider"]: item for item in routing.get("candidates", []) if isinstance(item, dict)}
    if candidates.get("openai_api", {}).get("cooldown", {}).get("reason") != "configuration_missing":
        failures.append("openai_api without key name should enter configuration_missing cooldown")
    if candidates.get("local_llm", {}).get("safeToRoute") is not False:
        failures.append("unavailable local_llm should not be safeToRoute")


def check_index_and_router(registry: dict[str, Any], failures: list[str]) -> None:
    index = load_yaml(INDEX)
    routes = index.get("route_by_intent") if isinstance(index.get("route_by_intent"), dict) else {}
    route = routes.get("provider_runtime_probe")
    if not isinstance(route, dict):
        failures.append("registry/_index.yaml missing route_by_intent.provider_runtime_probe")
    else:
        files = route.get("read") if isinstance(route.get("read"), list) else []
        for expected in (
            "registry/services/provider-probe.yaml",
            "registry/providers/provider-cli-routing.yaml",
            "registry/providers/skill-provider-routing.yaml",
            "registry/providers/provider-bootstrap.yaml",
        ):
            if expected not in files:
                failures.append(f"provider_runtime_probe route missing file: {expected}")

    entrypoints = registry.get("entrypoints") if isinstance(registry.get("entrypoints"), dict) else {}
    api_paths = entrypoints.get("api_paths") if isinstance(entrypoints.get("api_paths"), list) else []
    for path in ("/api/providers/probes", "/api/providers/probes/{provider_id}", "/api/providers/routing"):
        if path not in api_paths:
            failures.append(f"provider-probe registry missing API path: {path}")

    router_source = ROUTER_SOURCE.read_text(encoding="utf-8")
    for route_fragment in ('@router.get("/probes")', '@router.get("/routing")', '@router.get("/probes/{provider_id}")'):
        if route_fragment not in router_source:
            failures.append(f"provider router missing route: {route_fragment}")


def run_checks() -> dict[str, Any]:
    failures: list[str] = []
    warnings: list[str] = []
    registry = load_yaml(SERVICE_REGISTRY)
    check_registry_boundaries(registry, failures)
    check_provider_registry(failures, warnings)
    check_source_boundaries(failures)
    check_runtime_behavior(failures)
    check_index_and_router(registry, failures)
    return {
        "ok": not failures,
        "failures": failures,
        "warnings": warnings,
        "counts": {
            "expected_providers": len(EXPECTED_PROVIDERS),
            "optional_providers": len(OPTIONAL_PROVIDER_IDS),
        },
    }


def main() -> int:
    try:
        report = run_checks()
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["ok"] else 1
    except Exception as exc:  # noqa: BLE001 - operational verifier must return structured failure.
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
