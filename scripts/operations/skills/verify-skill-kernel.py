from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml


ROOT = next((p for p in Path(__file__).resolve().parents if (p / "registry" / "_index.yaml").exists()), Path(__file__).resolve().parent)

REQUIRED_CAPABILITY_FIELDS = {
    "id",
    "purpose",
    "when_to_use",
    "when_not_to_use",
    "input_contract",
    "output_contract",
    "hook_timing",
    "permission_tier",
    "provider_preferences",
    "storage_policy",
    "tests_or_validation",
}

REQUIRED_CAPABILITIES = {
    "coding-lite",
    "architecture-review",
    "business-review",
    "research-synthesis",
    "app-action-draft",
    "permission-review",
    "visual-ui-review",
}

REQUIRED_PROVIDERS = {"codex", "claude", "gemini", "local"}
REQUIRED_LIFECYCLE = {
    "observation",
    "proposal",
    "draft",
    "preparation",
    "cart_or_reservation",
    "execution",
    "delete",
    "external_send",
    "payment",
    "account_change",
}
REQUIRED_PERMISSION_DOMAINS = {
    "app",
    "file",
    "money",
    "external_send",
    "account_change",
    "delete",
    "payment",
}
REQUIRED_SOURCE_DOCS = {
}

REQUIRED_RUNTIME_FILES = {
    "core/kernel/skill_kernel_resolver.py",
    "scripts/operations/skills/resolve-skill-kernel.py",
    "scripts/operations/skills/test-skill-kernel-runtime.py",
    "scripts/operations/skills/smoke-skill-kernel-runtime.py",
    "scripts/operations/skills/verify-skill-hub.py",
    "scripts/operations/skills/audit-planning-spec-docs.py",
}


def load_yaml(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def rel(path: Path) -> str:
    return str(path.relative_to(ROOT)).replace("\\", "/")


def fail(failures: list[dict[str, str]], path: Path, message: str) -> None:
    failures.append({"path": rel(path), "message": message})


def main() -> int:
    failures: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []

    kernel_dir = ROOT / "core/kernel"
    kernel_contract = kernel_dir / "kernel-routing.yaml"
    kernel_readme = kernel_dir / "README.md"
    if not kernel_dir.exists() or not any(kernel_dir.iterdir()):
        fail(failures, kernel_dir, "core/kernel is empty or missing")
    for path in [kernel_contract, kernel_readme]:
        if not path.exists():
            fail(failures, path, "required kernel file missing")

    for runtime_file in REQUIRED_RUNTIME_FILES:
        path = ROOT / runtime_file
        if not path.exists():
            fail(failures, path, "required runtime resolver file missing")

    if kernel_contract.exists():
        kernel = load_yaml(kernel_contract)
        flow_steps = {entry.get("step") for entry in kernel.get("flow", []) if isinstance(entry, dict)}
        required_steps = {
            "input_intake",
            "intent_and_context_judgment",
            "capability_selection",
            "provider_selection",
            "permission_check",
            "execute_or_respond",
            "record_and_route_outputs",
        }
        missing_steps = required_steps - flow_steps
        if missing_steps:
            fail(failures, kernel_contract, f"kernel flow missing steps: {sorted(missing_steps)}")
        docs = set(kernel.get("source_documents", []))
        missing_docs = REQUIRED_SOURCE_DOCS - docs
        if missing_docs:
            fail(failures, kernel_contract, f"missing 122/123/124 source refs: {sorted(missing_docs)}")

    capability_root = ROOT / "capabilities/composed"
    capability_files = sorted(capability_root.glob("*/capability.yaml"))
    capability_ids: set[str] = set()
    for path in capability_files:
        data = load_yaml(path)
        cap_id = data.get("id")
        if cap_id:
            capability_ids.add(cap_id)
        missing = REQUIRED_CAPABILITY_FIELDS - set(data)
        if missing:
            fail(failures, path, f"missing fields: {sorted(missing)}")
        if data.get("id") != path.parent.name:
            fail(failures, path, "id must match folder name")
    if len(capability_files) < 7:
        fail(failures, capability_root, f"need at least 7 capability cards, found {len(capability_files)}")
    missing_caps = REQUIRED_CAPABILITIES - capability_ids
    if missing_caps:
        fail(failures, capability_root, f"missing required capabilities: {sorted(missing_caps)}")

    skill_routing_path = ROOT / "registry/hooks/skill-routing.yaml"
    if skill_routing_path.exists():
        skill_routing = load_yaml(skill_routing_path)
        registry_caps = set(skill_routing.get("capability_registry", {}))
        rules_caps: set[str] = set()
        for rule in skill_routing.get("hook_rules", []):
            rules_caps.update(rule.get("capabilities", []))
        for cap in REQUIRED_CAPABILITIES:
            if cap not in registry_caps:
                fail(failures, skill_routing_path, f"capability_registry missing {cap}")
            if cap not in rules_caps:
                fail(failures, skill_routing_path, f"hook_rules never select {cap}")
    else:
        fail(failures, skill_routing_path, "skill routing file missing")

    provider_path = ROOT / "registry/providers/skill-provider-routing.yaml"
    if provider_path.exists():
        provider = load_yaml(provider_path)
        provider_roles = set(provider.get("provider_roles", {}))
        missing_providers = REQUIRED_PROVIDERS - provider_roles
        if missing_providers:
            fail(failures, provider_path, f"missing provider roles: {sorted(missing_providers)}")
        routes = provider.get("capability_routes", {})
        for cap in REQUIRED_CAPABILITIES:
            if cap not in routes:
                fail(failures, provider_path, f"missing route for {cap}")
            else:
                route = routes[cap]
                if not route.get("primary") or not route.get("fallback"):
                    fail(failures, provider_path, f"route for {cap} needs primary and fallback")
    else:
        fail(failures, provider_path, "provider routing file missing")

    skill_hub_path = ROOT / "registry/skills/skill-hub.yaml"
    if skill_hub_path.exists():
        skill_hub = load_yaml(skill_hub_path)
        if skill_hub.get("contract") != "willind.skill_hub":
            fail(failures, skill_hub_path, "unexpected Skill Hub contract")
        required_concepts = {
            "imported_skill",
            "skill_adapter",
            "composed_capability",
            "provider_runner",
            "hook_rule",
            "permission_rule",
            "storage_rule",
            "skill_profile",
            "skill_bundle",
        }
        missing_concepts = required_concepts - set(skill_hub.get("concepts", {}))
        if missing_concepts:
            fail(failures, skill_hub_path, f"missing Skill Hub concepts: {sorted(missing_concepts)}")
        if len(skill_hub.get("skill_profiles", [])) < 10:
            fail(failures, skill_hub_path, "Skill Hub needs scenario profiles for baseline commands")
    else:
        fail(failures, skill_hub_path, "Skill Hub registry missing")

    permission_path = ROOT / "registry/permissions/permission-gate-policy.yaml"
    if permission_path.exists():
        permission = load_yaml(permission_path)
        lifecycle = set(permission.get("action_lifecycle", {}))
        domains = set(permission.get("domains", {}))
        missing_lifecycle = REQUIRED_LIFECYCLE - lifecycle
        missing_domains = REQUIRED_PERMISSION_DOMAINS - domains
        if missing_lifecycle:
            fail(failures, permission_path, f"missing lifecycle entries: {sorted(missing_lifecycle)}")
        if missing_domains:
            fail(failures, permission_path, f"missing permission domains: {sorted(missing_domains)}")
        for safe_lifecycle in ["observation", "proposal", "draft"]:
            decision = permission["action_lifecycle"].get(safe_lifecycle, {}).get("default_decision")
            if decision != "allow":
                fail(failures, permission_path, f"{safe_lifecycle} must default to allow")
        preparation_decision = permission["action_lifecycle"].get("preparation", {}).get("default_decision")
        if preparation_decision not in {"allow", "trace_required"}:
            fail(failures, permission_path, "preparation must default to allow or trace_required")
        cart_decision = permission["action_lifecycle"].get("cart_or_reservation", {}).get("default_decision", "")
        if cart_decision not in {"trace_required", "confirm"}:
            fail(failures, permission_path, "cart_or_reservation must default to trace_required or confirm")
        execution_decision = permission["action_lifecycle"].get("execution", {}).get("default_decision", "")
        if execution_decision not in {"trace_required", "confirm"}:
            fail(failures, permission_path, "execution must default to trace_required or confirm")
        for gated_lifecycle in ["delete", "external_send", "payment", "account_change"]:
            decision = permission["action_lifecycle"].get(gated_lifecycle, {}).get("default_decision", "")
            if "confirm" not in decision and "block" not in decision:
                fail(failures, permission_path, f"{gated_lifecycle} must require confirmation or block")
    else:
        fail(failures, permission_path, "permission policy file missing")

    index_path = ROOT / "registry/_index.yaml"
    if index_path.exists():
        index_text = index_path.read_text(encoding="utf-8", errors="replace")
        for required in [
            "registry/hooks/skill-routing.yaml",
            "registry/providers/skill-provider-routing.yaml",
            "registry/permissions/permission-gate-policy.yaml",
            "registry/skills/skill-hub.yaml",
            "core/kernel/kernel-routing.yaml",
        ]:
            if required not in index_text:
                fail(failures, index_path, f"registry index missing {required}")
    else:
        fail(failures, index_path, "registry index missing")

    if not doc_path.exists():
        fail(failures, doc_path, "operation doc missing")
    if not runtime_doc_path.exists():
        fail(failures, runtime_doc_path, "runtime resolver operation doc missing")

    planning_plans = list((ROOT / "docs").glob("**/planning/plans"))
    planning_plan_files = list((ROOT / "docs").glob("**/planning/**/*-plan.md"))
    planning_plan_files += list((ROOT / "projects").glob("*/docs/planning/**/*-plan.md"))
    if planning_plans:
        warnings.append({"path": "docs", "message": f"planning/plans dirs remain: {[rel(p) for p in planning_plans[:10]]}"})
    if planning_plan_files:
        warnings.append({"path": "planning-docs", "message": f"planning *-plan.md files remain: {[rel(p) for p in planning_plan_files[:10]]}"})

    report = {
        "ok": not failures,
        "failures": failures,
        "warnings": warnings,
        "counts": {
            "capability_cards": len(capability_files),
            "required_capabilities": len(REQUIRED_CAPABILITIES),
            "hook_rules": len(load_yaml(skill_routing_path).get("hook_rules", [])) if skill_routing_path.exists() else 0,
            "provider_roles": len(load_yaml(provider_path).get("provider_roles", {})) if provider_path.exists() else 0,
            "permission_lifecycle_entries": len(load_yaml(permission_path).get("action_lifecycle", {})) if permission_path.exists() else 0,
            "runtime_files": len([path for path in REQUIRED_RUNTIME_FILES if (ROOT / path).exists()]),
        },
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
