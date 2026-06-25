from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml


ROOT = next((p for p in Path(__file__).resolve().parents if (p / "registry" / "_index.yaml").exists()), Path(__file__).resolve().parent)
POLICY_PATH = ROOT / "registry/files/file-routing-policy.yaml"
TAGS_PATH = ROOT / "registry/files/path-tags.yaml"
SUGGEST_ROUTE_PATH = ROOT / "scripts/operations/files/suggest-file-route.py"


def _ensure_utf8() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")


def _load_suggest_module() -> Any:
    spec = importlib.util.spec_from_file_location("willind_suggest_file_route", SUGGEST_ROUTE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {SUGGEST_ROUTE_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{path} did not contain a YAML mapping")
    return data


def _slash(path: str | Path) -> str:
    return str(path).replace("\\", "/").strip("/")


def _normalized_stem(path: str) -> str:
    name = Path(path.replace("\\", "/")).name.lower()
    stem = re.sub(r"\.[^.]+$", "", name)
    stem = re.sub(r"(?i)([-_.]?(preview|screenshot|capture|render|derived|parsed|summary|notes|source|sources|ocr|export|final|draft|v\d+))+$", "", stem)
    stem = re.sub(r"[-_.]+", "-", stem).strip("-")
    return stem or Path(path.replace("\\", "/")).stem.lower()


def _bundle_id(paths: list[str], explicit: str | None) -> str:
    if explicit:
        return explicit
    joined = "\n".join(sorted(_slash(path) for path in paths))
    digest = hashlib.sha1(joined.encode("utf-8")).hexdigest()[:10]
    shared_stems = {_normalized_stem(path) for path in paths}
    prefix = next(iter(shared_stems))[:40] if len(shared_stems) == 1 else "mixed"
    return f"{prefix}-{digest}"


def _file_role(path: str, intent: str) -> str:
    suffix = Path(path.replace("\\", "/")).suffix.lower()
    if intent == "raw_data":
        return "raw"
    if intent in {"processed_data"}:
        return "derived"
    if intent in {"reference", "uiux_reference"}:
        return "sources"
    if intent in {"workflow", "composed_capability", "mcp_definition", "role_capability"}:
        return "synthesis"
    if intent in {"runtime_trace", "cleanup_log", "manual_review"}:
        return "derived"
    if suffix in {".md", ".txt"}:
        return "notes"
    if suffix in {".json", ".yaml", ".yml", ".csv"}:
        return "derived"
    return "raw"


def _bundle_reasons(paths: list[str], intents: list[str]) -> list[str]:
    reasons: list[str] = []
    stems = {_normalized_stem(path) for path in paths}
    parents = {_slash(Path(path.replace("\\", "/")).parent) for path in paths}
    extensions = {Path(path.replace("\\", "/")).suffix.lower() for path in paths}

    if len(paths) > 1 and len(stems) == 1:
        reasons.append("shared_normalized_stem")
    if len(paths) > 1 and len(parents) == 1:
        reasons.append("same_parent_drop")
    if len(extensions) > 1 and len(stems) <= max(1, len(paths) // 2):
        reasons.append("multi_format_derivatives")
    if {"raw_data", "processed_data"} & set(intents) and len(paths) > 1:
        reasons.append("raw_and_derived_may_share_source")
    if "manual_review" in intents:
        reasons.append("contains_unclear_item")
    return reasons


def suggest_bundle(
    paths: list[str],
    *,
    root: Path,
    policy: dict[str, Any],
    tags: dict[str, Any],
    bundle_id: str | None = None,
) -> dict[str, Any]:
    if not paths:
        raise ValueError("At least one path is required")

    route_module = _load_suggest_module()
    suggestions = [
        route_module.build_suggestion(path, root=root, policy=policy, tags=tags, requested_intent=None)
        for path in paths
    ]
    intents = [str(item["intent"]) for item in suggestions]
    reasons = _bundle_reasons(paths, intents)
    blocked = [item for item in suggestions if item.get("action") == "blocked"]
    bundle = _bundle_id(paths, bundle_id)
    review_policy = policy.get("review_queue_policy", {})
    bundle_policy = policy.get("bundle_policy", {})

    if blocked:
        recommendation = "blocked_mixed_bundle"
        action = "do_not_move"
    elif len(paths) == 1:
        recommendation = "single_route"
        action = suggestions[0].get("action", "review")
    elif reasons:
        recommendation = "bundle_review"
        action = "create_review_item"
    else:
        recommendation = "split_by_role"
        action = "route_individually"

    return {
        "ok": True,
        "action": action,
        "recommendation": recommendation,
        "bundle_id": bundle,
        "reason": reasons or ["no_strong_bundle_signal"],
        "review_item_path": f"{review_policy.get('item_root', 'runtime/cleanup/review-items')}/{bundle}/review.json",
        "manual_holding_path": f"{review_policy.get('manual_holding_root', 'runtime/generated-workspaces/manual-review')}/{bundle}",
        "manifest_required_fields": bundle_policy.get("bundle_manifest", {}).get("required_fields", []),
        "items": [
            {
                "source_path": item["source_path"],
                "intent": item["intent"],
                "role": _file_role(item["source_path"], item["intent"]),
                "suggested_path": item.get("suggested_path"),
                "action": item.get("action"),
                "reason": item.get("reason"),
            }
            for item in suggestions
        ],
    }


def self_test(root: Path, policy_path: Path, tags_path: Path) -> dict[str, Any]:
    policy = _load_yaml(policy_path)
    tags = _load_yaml(tags_path)
    cases = [
        {
            "paths": ["report.pdf", "report.md", "report_preview.png", "report.json"],
            "expected": "bundle_review",
        },
        {
            "paths": ["client_secret.json", "report.md"],
            "expected": "blocked_mixed_bundle",
        },
        {
            "paths": ["standalone-workflow.md"],
            "expected": "single_route",
        },
    ]
    results = []
    for case in cases:
        payload = suggest_bundle(case["paths"], root=root, policy=policy, tags=tags)
        results.append(
            {
                "paths": case["paths"],
                "expected": case["expected"],
                "actual": payload["recommendation"],
                "ok": payload["recommendation"] == case["expected"],
            }
        )
    return {"ok": all(item["ok"] for item in results), "cases": results}


def main() -> int:
    _ensure_utf8()
    parser = argparse.ArgumentParser(description="Suggest whether multiple files should be reviewed as a bundle.")
    parser.add_argument("paths", nargs="*", help="Files or directories to classify as one possible bundle.")
    parser.add_argument("--bundle-id", help="Explicit bundle id for review item output.")
    parser.add_argument("--root", default=str(ROOT), help="Willind root path.")
    parser.add_argument("--policy", default=str(POLICY_PATH), help="Routing policy YAML.")
    parser.add_argument("--tags", default=str(TAGS_PATH), help="Path tag YAML.")
    parser.add_argument("--self-test", action="store_true", help="Run built-in smoke checks.")
    args = parser.parse_args()

    root = Path(args.root)
    policy_path = Path(args.policy)
    tags_path = Path(args.tags)

    try:
        if args.self_test:
            payload = self_test(root, policy_path, tags_path)
        else:
            policy = _load_yaml(policy_path)
            tags = _load_yaml(tags_path)
            payload = suggest_bundle(
                args.paths,
                root=root,
                policy=policy,
                tags=tags,
                bundle_id=args.bundle_id,
            )
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0 if payload.get("ok") else 1
    except Exception as exc:  # noqa: BLE001 - CLI should report structured errors.
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
