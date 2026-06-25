from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml


ROOT = next((p for p in Path(__file__).resolve().parents if (p / "registry" / "_index.yaml").exists()), Path(__file__).resolve().parent)
SKILL_HUB_PATH = ROOT / "registry/skills/skill-hub.yaml"
SOURCE_INVENTORY_PATH = ROOT / "registry/skills/skill-source-inventory.yaml"
SKILL_ROUTING_PATH = ROOT / "registry/hooks/skill-routing.yaml"
PROVIDER_ROUTING_PATH = ROOT / "registry/providers/skill-provider-routing.yaml"
PERMISSION_POLICY_PATH = ROOT / "registry/permissions/permission-gate-policy.yaml"
FILE_ROUTING_PATH = ROOT / "registry/files/file-routing-policy.yaml"

REQUIRED_CONCEPTS = {
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

REQUIRED_HOOKS = {
    "intent_detect",
    "planning",
    "pre_execution",
    "execution_review",
    "post_execution",
    "memory_update",
    "error_recovery",
}

REQUIRED_PROVIDER_POLICIES = {
    "codex_only",
    "claude_review_only",
    "gemini_research",
    "local_possible",
    "api_required",
    "common",
}

REQUIRED_SCENARIOS = {
    "bounded_experiment_loop",
    "external_skill_absorption",
    "small_code_bug",
    "architecture_review",
    "market_research",
    "screenshot_ui_judgement",
    "planning_idea_expansion",
    "app_purchase_preparation",
    "cart_or_reservation_gate",
    "payment_request",
    "external_email_send",
    "file_delete",
    "mid_coding_brainstorm",
    "design_with_code_review",
    "quick_school_question",
    "long_business_strategy",
}


def load_yaml(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def rel(path: Path) -> str:
    return str(path.relative_to(ROOT)).replace("\\", "/")


def add_failure(failures: list[dict[str, str]], path: Path, message: str) -> None:
    failures.append({"path": rel(path), "message": message})


def main() -> int:
    failures: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []

    required_files = [
        SKILL_HUB_PATH,
        SOURCE_INVENTORY_PATH,
        SKILL_ROUTING_PATH,
        PROVIDER_ROUTING_PATH,
        PERMISSION_POLICY_PATH,
        FILE_ROUTING_PATH,
    ]
    for path in required_files:
        if not path.exists():
            add_failure(failures, path, "required Skill Hub input missing")

    if failures:
        print(json.dumps({"ok": False, "failures": failures, "warnings": warnings}, ensure_ascii=False, indent=2))
        return 1

    hub = load_yaml(SKILL_HUB_PATH)
    inventory = load_yaml(SOURCE_INVENTORY_PATH)
    skill_routing = load_yaml(SKILL_ROUTING_PATH)
    provider = load_yaml(PROVIDER_ROUTING_PATH)
    permission = load_yaml(PERMISSION_POLICY_PATH)
    file_routing = load_yaml(FILE_ROUTING_PATH)

    concepts = set(hub.get("concepts", {}))
    missing_concepts = REQUIRED_CONCEPTS - concepts
    if missing_concepts:
        add_failure(failures, SKILL_HUB_PATH, f"missing concepts: {sorted(missing_concepts)}")

    hooks = hub.get("canonical_hook_lifecycle", {})
    missing_hooks = REQUIRED_HOOKS - set(hooks)
    if missing_hooks:
        add_failure(failures, SKILL_HUB_PATH, f"missing canonical hooks: {sorted(missing_hooks)}")

    legacy_hook_values = {
        hook
        for rule in skill_routing.get("hook_rules", [])
        for hook in rule.get("hook_timing", [])
    }
    for hook_id, data in hooks.items():
        aliases = set(data.get("aliases", []))
        if not aliases & legacy_hook_values:
            add_failure(failures, SKILL_HUB_PATH, f"{hook_id} has no alias in existing skill-routing hook_timing")

    policies = set(hub.get("provider_loading_policies", {}))
    missing_policies = REQUIRED_PROVIDER_POLICIES - policies
    if missing_policies:
        add_failure(failures, SKILL_HUB_PATH, f"missing provider loading policies: {sorted(missing_policies)}")

    inventory_ids = {item.get("id") for item in inventory.get("items", [])}
    for source_id, source in hub.get("skill_sources", {}).items():
        inventory_id = source.get("source_inventory_id")
        if inventory_id not in inventory_ids:
            add_failure(failures, SKILL_HUB_PATH, f"source {source_id} references unknown inventory id {inventory_id!r}")

    capability_ids = set(skill_routing.get("capability_registry", {}))
    lifecycle_ids = set(permission.get("action_lifecycle", {}))
    storage_intents = set(file_routing.get("intents", {}))
    profiles = hub.get("skill_profiles", [])
    profile_ids = {profile.get("id") for profile in profiles}
    missing_scenarios = REQUIRED_SCENARIOS - profile_ids
    if missing_scenarios:
        add_failure(failures, SKILL_HUB_PATH, f"missing required scenario profiles: {sorted(missing_scenarios)}")

    for profile in profiles:
        profile_id = str(profile.get("id"))
        for capability_id in profile.get("capabilities", []):
            if capability_id not in capability_ids:
                add_failure(failures, SKILL_HUB_PATH, f"profile {profile_id} references unknown capability {capability_id}")
        policy_id = profile.get("provider_policy")
        if policy_id not in policies:
            add_failure(failures, SKILL_HUB_PATH, f"profile {profile_id} references unknown provider policy {policy_id}")
        for hook_id in profile.get("hooks", []):
            if hook_id not in hooks:
                add_failure(failures, SKILL_HUB_PATH, f"profile {profile_id} references unknown hook {hook_id}")
        lifecycle = profile.get("permission_lifecycle")
        if lifecycle not in lifecycle_ids:
            add_failure(failures, SKILL_HUB_PATH, f"profile {profile_id} references unknown lifecycle {lifecycle}")
        storage_rule = profile.get("storage_rule")
        if storage_rule not in storage_intents:
            add_failure(failures, SKILL_HUB_PATH, f"profile {profile_id} references unknown storage rule {storage_rule}")

    for bundle_id, bundle in hub.get("skill_bundles", {}).items():
        for profile_id in bundle.get("profiles", []):
            if profile_id not in profile_ids:
                add_failure(failures, SKILL_HUB_PATH, f"bundle {bundle_id} references unknown profile {profile_id}")

    provider_role_ids = {
        data.get("canonical_id")
        for data in provider.get("provider_roles", {}).values()
        if isinstance(data, dict)
    }
    provider_role_ids.update({"openai_api", "willind_ai_rules", "local_policy"})
    for policy_id, policy in hub.get("provider_loading_policies", {}).items():
        primary = policy.get("primary_runner")
        if primary not in provider_role_ids:
            warnings.append(
                {
                    "path": rel(SKILL_HUB_PATH),
                    "message": f"provider policy {policy_id} primary runner {primary!r} is not in provider roles; treated as future runner",
                }
            )

    report = {
        "ok": not failures,
        "failures": failures,
        "warnings": warnings,
        "counts": {
            "concepts": len(concepts),
            "canonical_hooks": len(hooks),
            "provider_loading_policies": len(policies),
            "skill_sources": len(hub.get("skill_sources", {})),
            "skill_profiles": len(profiles),
            "skill_bundles": len(hub.get("skill_bundles", {})),
        },
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
