from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml


ROOT = next((p for p in Path(__file__).resolve().parents if (p / "registry" / "_index.yaml").exists()), Path(__file__).resolve().parent)
POLICY_PATH = ROOT / "registry/providers/provider-cli-routing.yaml"


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{path} did not contain a YAML mapping")
    return data


def _as_mapping(policy: dict[str, Any], key: str, failures: list[str]) -> dict[str, Any]:
    value = policy.get(key)
    if not isinstance(value, dict):
        failures.append(f"{key} must be a mapping")
        return {}
    return value


def check_policy(policy: dict[str, Any]) -> dict[str, Any]:
    failures: list[str] = []
    warnings: list[str] = []

    if policy.get("contract") != "willind.provider_cli_routing":
        failures.append("contract must be willind.provider_cli_routing")

    for section in (
        "principle",
        "providers",
        "task_classes",
        "multi_agent_presets",
        "benchmark_metrics",
        "weekly_update",
        "decision_trace",
        "verification",
    ):
        if section not in policy:
            failures.append(f"missing section: {section}")

    providers = _as_mapping(policy, "providers", failures)
    tasks = _as_mapping(policy, "task_classes", failures)
    presets = _as_mapping(policy, "multi_agent_presets", failures)

    for provider_id, provider in providers.items():
        if not isinstance(provider, dict):
            failures.append(f"providers.{provider_id} must be a mapping")
            continue
        for key in ("kind", "status", "cost_posture", "strengths", "safety"):
            if key not in provider:
                failures.append(f"providers.{provider_id} missing {key}")
        weight = provider.get("default_weight")
        if not isinstance(weight, (int, float)) or not 0 <= float(weight) <= 1:
            failures.append(f"providers.{provider_id}.default_weight must be 0..1")

    known_providers = set(providers)
    known_presets = set(presets)
    for task_id, task in tasks.items():
        if not isinstance(task, dict):
            failures.append(f"task_classes.{task_id} must be a mapping")
            continue
        preset = task.get("preset")
        if preset not in known_presets:
            failures.append(f"task_classes.{task_id}.preset references unknown preset: {preset}")
        for group in ("primary", "reviewers", "implementers", "fallback"):
            values = task.get(group, [])
            if values is None:
                continue
            if not isinstance(values, list):
                failures.append(f"task_classes.{task_id}.{group} must be a list")
                continue
            for provider_id in values:
                if provider_id not in known_providers:
                    failures.append(f"task_classes.{task_id}.{group} references unknown provider: {provider_id}")
        for pattern in task.get("triggers", []):
            try:
                re.compile(str(pattern))
            except re.error as exc:
                failures.append(f"task_classes.{task_id}.triggers invalid regex: {exc}")
        if "risk_tier" not in task:
            failures.append(f"task_classes.{task_id} missing risk_tier")
        if "budget_tier" not in task:
            failures.append(f"task_classes.{task_id} missing budget_tier")

    for preset_id, preset in presets.items():
        if not isinstance(preset, dict):
            failures.append(f"multi_agent_presets.{preset_id} must be a mapping")
            continue
        if "shape" not in preset:
            failures.append(f"multi_agent_presets.{preset_id} missing shape")
        max_agents = preset.get("max_agents")
        if not isinstance(max_agents, int) or max_agents < 1:
            failures.append(f"multi_agent_presets.{preset_id}.max_agents must be positive int")

    metrics = policy.get("benchmark_metrics", [])
    if not isinstance(metrics, list) or len(metrics) < 5:
        failures.append("benchmark_metrics must contain at least 5 metrics")
    for required in ("cost", "quota_stability", "tool_call_reliability", "user_fit"):
        if required not in metrics:
            failures.append(f"benchmark_metrics missing: {required}")

    weekly_update = policy.get("weekly_update", {})
    if isinstance(weekly_update, dict):
        if not weekly_update.get("input_sources"):
            failures.append("weekly_update.input_sources missing")
        output = weekly_update.get("output")
        if not output:
            failures.append("weekly_update.output missing")
        elif not (ROOT / str(output)).exists():
            failures.append(f"weekly_update.output file missing: {output}")
    else:
        failures.append("weekly_update must be a mapping")

    trace = policy.get("decision_trace", {})
    required_fields = trace.get("required_fields", []) if isinstance(trace, dict) else []
    for field in ("task_class", "selected_preset", "primary_provider", "fallback_chain", "reason"):
        if field not in required_fields:
            failures.append(f"decision_trace.required_fields missing: {field}")

    verification = policy.get("verification", {})
    if isinstance(verification, dict):
        for key in ("routing_policy", "registry_policy"):
            script = str(verification.get(key, "")).split()[0]
            if not script:
                failures.append(f"verification.{key} missing")
                continue
            if not (ROOT / script).exists():
                failures.append(f"verification.{key} script missing: {script}")
    else:
        failures.append("verification must be a mapping")

    return {
        "ok": not failures,
        "failures": failures,
        "warnings": warnings,
        "counts": {
            "providers": len(providers),
            "task_classes": len(tasks),
            "presets": len(presets),
            "benchmark_metrics": len(metrics) if isinstance(metrics, list) else 0,
        },
    }


def main() -> int:
    try:
        policy = load_yaml(POLICY_PATH)
        report = check_policy(policy)
        if report["ok"]:
            route_result = subprocess.run(
                [sys.executable, str(ROOT / "scripts/operations/providers/suggest-provider-route.py"), "--self-test"],
                cwd=str(ROOT),
                text=True,
                capture_output=True,
                check=False,
            )
            report["suggest_provider_route_self_test"] = {
                "returncode": route_result.returncode,
                "stdout": route_result.stdout.strip(),
                "stderr": route_result.stderr.strip(),
            }
            if route_result.returncode != 0:
                report["ok"] = False
                report["failures"].append("suggest-provider-route.py --self-test failed")

        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["ok"] else 1
    except Exception as exc:  # noqa: BLE001 - CLI should report structured errors.
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
