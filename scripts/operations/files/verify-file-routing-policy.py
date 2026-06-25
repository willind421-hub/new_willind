from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml


ROOT = next((p for p in Path(__file__).resolve().parents if (p / "registry" / "_index.yaml").exists()), Path(__file__).resolve().parent)
POLICY_PATH = ROOT / "registry/files/file-routing-policy.yaml"
TAGS_PATH = ROOT / "registry/files/path-tags.yaml"


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{path} did not contain a YAML mapping")
    return data


def slash(value: str | Path) -> str:
    return str(value).replace("\\", "/").strip("/")


def known_roots(tags: dict[str, Any]) -> set[str]:
    coverage = tags.get("coverage", {})
    values = coverage.get("root_directories_expected", []) if isinstance(coverage, dict) else []
    return {str(value) for value in values}


def known_paths(tags: dict[str, Any]) -> set[str]:
    entries = tags.get("paths", [])
    if not isinstance(entries, list):
        return set()
    return {slash(item.get("path", "")) for item in entries if isinstance(item, dict)}


def target_ok(target: str, roots: set[str], paths: set[str]) -> bool:
    if not target:
        return False
    if target in {"projects_or_active_root"}:
        return True
    normalized = slash(target)
    first = normalized.split("/", 1)[0]
    return normalized in paths or first in roots


def check_policy(policy: dict[str, Any], tags: dict[str, Any]) -> dict[str, Any]:
    failures: list[str] = []
    warnings: list[str] = []
    roots = known_roots(tags)
    paths = known_paths(tags)

    if policy.get("contract") != "willind.file_routing_policy":
        failures.append("contract must be willind.file_routing_policy")

    for section in (
        "intents",
        "blocked_intents",
        "name_patterns",
        "ingress_lanes",
        "bundle_policy",
        "review_queue_policy",
        "verification",
    ):
        if section not in policy:
            failures.append(f"missing section: {section}")

    for section in ("intents", "blocked_intents"):
        entries = policy.get(section, {})
        if not isinstance(entries, dict):
            failures.append(f"{section} must be a mapping")
            continue
        for name, entry in entries.items():
            if not isinstance(entry, dict):
                failures.append(f"{section}.{name} must be a mapping")
                continue
            target = str(entry.get("target", ""))
            if not target_ok(target, roots, paths):
                failures.append(f"{section}.{name}.target is not covered by path tags: {target}")
            if "safety" not in entry:
                failures.append(f"{section}.{name} missing safety")

    pattern_intents = set(policy.get("intents", {})) | set(policy.get("blocked_intents", {}))
    for index, rule in enumerate(policy.get("name_patterns", [])):
        if not isinstance(rule, dict):
            failures.append(f"name_patterns[{index}] must be a mapping")
            continue
        pattern = rule.get("pattern")
        intent = rule.get("intent")
        if intent not in pattern_intents:
            failures.append(f"name_patterns[{index}] references unknown intent: {intent}")
        try:
            re.compile(str(pattern))
        except re.error as exc:
            failures.append(f"name_patterns[{index}] invalid regex: {exc}")

    for lane, entry in policy.get("ingress_lanes", {}).items():
        if not isinstance(entry, dict):
            failures.append(f"ingress_lanes.{lane} must be a mapping")
            continue
        target = str(entry.get("target", ""))
        if not target_ok(target, roots, paths):
            failures.append(f"ingress_lanes.{lane}.target is not covered by path tags: {target}")
        for promotion in entry.get("promotion_targets", []):
            if not target_ok(str(promotion), roots, paths):
                failures.append(f"ingress_lanes.{lane}.promotion_targets has unknown target: {promotion}")

    bundle_policy = policy.get("bundle_policy", {})
    if isinstance(bundle_policy, dict):
        manifest = bundle_policy.get("bundle_manifest", {})
        required_fields = manifest.get("required_fields", []) if isinstance(manifest, dict) else []
        for field in ("bundle_id", "origin", "source_paths", "candidate_destinations", "confidence", "ttl_deadline", "decision"):
            if field not in required_fields:
                failures.append(f"bundle_policy.bundle_manifest.required_fields missing: {field}")
        review_root = str(bundle_policy.get("default_review_root", ""))
        if review_root and not target_ok(review_root, roots, paths):
            warnings.append(f"bundle_policy.default_review_root is not directly covered by path tags: {review_root}")
    else:
        failures.append("bundle_policy must be a mapping")

    review_queue = policy.get("review_queue_policy", {})
    if isinstance(review_queue, dict):
        for key in ("queue_file", "item_root", "manual_holding_root"):
            value = str(review_queue.get(key, ""))
            if not value:
                failures.append(f"review_queue_policy.{key} missing")
        ttl_days = review_queue.get("ttl_days", {})
        if not isinstance(ttl_days, dict) or "manual_review" not in ttl_days:
            failures.append("review_queue_policy.ttl_days.manual_review missing")
        close_states = review_queue.get("close_states", [])
        for state in ("accepted", "reprocess", "archive", "discard"):
            if state not in close_states:
                failures.append(f"review_queue_policy.close_states missing: {state}")
    else:
        failures.append("review_queue_policy must be a mapping")

    verification = policy.get("verification", {})
    path_tag_script = ROOT / str(verification.get("path_tags", "")).split()[0]
    routing_script = ROOT / str(verification.get("routing_policy", "")).split()[0]
    bundle_script = ROOT / str(verification.get("bundle_policy", "")).split()[0]
    if not path_tag_script.exists():
        failures.append(f"verification.path_tags script missing: {path_tag_script}")
    if not routing_script.exists():
        failures.append(f"verification.routing_policy script missing: {routing_script}")
    if not bundle_script.exists():
        failures.append(f"verification.bundle_policy script missing: {bundle_script}")

    return {
        "ok": not failures,
        "failures": failures,
        "warnings": warnings,
        "counts": {
            "intents": len(policy.get("intents", {})),
            "blocked_intents": len(policy.get("blocked_intents", {})),
            "name_patterns": len(policy.get("name_patterns", [])),
            "ingress_lanes": len(policy.get("ingress_lanes", {})),
        },
    }


def main() -> int:
    try:
        policy = load_yaml(POLICY_PATH)
        tags = load_yaml(TAGS_PATH)
        report = check_policy(policy, tags)
        if report["ok"]:
            route_result = subprocess.run(
                [sys.executable, str(ROOT / "scripts/operations/files/suggest-file-route.py"), "--self-test"],
                cwd=str(ROOT),
                text=True,
                capture_output=True,
                check=False,
            )
            report["suggest_file_route_self_test"] = {
                "returncode": route_result.returncode,
                "stdout": route_result.stdout.strip(),
                "stderr": route_result.stderr.strip(),
            }
            if route_result.returncode != 0:
                report["ok"] = False
                report["failures"].append("suggest-file-route.py --self-test failed")

            bundle_result = subprocess.run(
                [sys.executable, str(ROOT / "scripts/operations/files/suggest-bundle-route.py"), "--self-test"],
                cwd=str(ROOT),
                text=True,
                capture_output=True,
                check=False,
            )
            report["suggest_bundle_route_self_test"] = {
                "returncode": bundle_result.returncode,
                "stdout": bundle_result.stdout.strip(),
                "stderr": bundle_result.stderr.strip(),
            }
            if bundle_result.returncode != 0:
                report["ok"] = False
                report["failures"].append("suggest-bundle-route.py --self-test failed")

        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["ok"] else 1
    except Exception as exc:  # noqa: BLE001 - CLI should report structured errors.
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
