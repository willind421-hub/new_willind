from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml


DEFAULT_ROOT = next((p for p in Path(__file__).resolve().parents if (p / "registry" / "_index.yaml").exists()), Path(__file__).resolve().parent)
DEFAULT_POLICY = DEFAULT_ROOT / "registry/files/file-routing-policy.yaml"
DEFAULT_TAGS = DEFAULT_ROOT / "registry/files/path-tags.yaml"


def _load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{path} did not contain a YAML mapping")
    return data


def _slash(path: str | Path) -> str:
    return str(path).replace("\\", "/").strip("/")


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def _relative_or_input(raw_path: str, root: Path) -> str:
    candidate = Path(raw_path)
    if candidate.is_absolute() and _is_relative_to(candidate, root):
        return _slash(candidate.resolve().relative_to(root.resolve()))
    return _slash(raw_path)


def _first_segment(path: str) -> str:
    return _slash(path).split("/", 1)[0]


def _known_path_tags(tags: dict[str, Any]) -> set[str]:
    entries = tags.get("paths", [])
    if not isinstance(entries, list):
        return set()
    return {str(item.get("path", "")).replace("\\", "/").strip("/") for item in entries if isinstance(item, dict)}


def _known_root_dirs(tags: dict[str, Any]) -> set[str]:
    coverage = tags.get("coverage", {})
    values = coverage.get("root_directories_expected", []) if isinstance(coverage, dict) else []
    return {str(value) for value in values}


def _join_target(target: str, source_path: str) -> str:
    name = Path(source_path.replace("\\", "/")).name
    if not name:
        return _slash(target)
    return f"{_slash(target)}/{name}"


def choose_intent(policy: dict[str, Any], source_path: str, requested_intent: str | None) -> tuple[str, str]:
    intents = policy.get("intents", {})
    blocked = policy.get("blocked_intents", {})
    if requested_intent:
        if requested_intent in intents or requested_intent in blocked:
            return requested_intent, "explicit_intent"
        raise ValueError(f"Unknown intent: {requested_intent}")

    first = _first_segment(source_path)
    if first in {".env", ".secrets", ".browser-profiles", ".claude", ".obsidian", "models", "backup"}:
        mapped = {
            ".env": "env",
            ".secrets": "secret",
            ".browser-profiles": "browser_profile",
            ".claude": "active_service_root",
            ".obsidian": "active_service_root",
            "models": "model_weight",
            "backup": "backup",
        }[first]
        return mapped, "protected_root"

    for rule in policy.get("name_patterns", []):
        if not isinstance(rule, dict):
            continue
        pattern = rule.get("pattern")
        intent = rule.get("intent")
        if not pattern or not intent:
            continue
        if re.search(str(pattern), source_path):
            return str(intent), f"name_pattern:{pattern}"

    return "manual_review", "fallback_unclear_intent"


def build_suggestion(
    source_path: str,
    *,
    root: Path,
    policy: dict[str, Any],
    tags: dict[str, Any],
    requested_intent: str | None = None,
) -> dict[str, Any]:
    rel_path = _relative_or_input(source_path, root)
    intent, reason = choose_intent(policy, rel_path, requested_intent)
    intents = policy.get("intents", {})
    blocked = policy.get("blocked_intents", {})
    known_tags = _known_path_tags(tags)
    known_roots = _known_root_dirs(tags)

    if intent in blocked:
        entry = blocked[intent]
        target = str(entry.get("target", ""))
        return {
            "ok": True,
            "action": "blocked",
            "source_path": rel_path,
            "intent": intent,
            "reason": reason,
            "target_base": target,
            "suggested_path": None,
            "safety": entry.get("safety"),
            "policy": entry.get("reason"),
        }

    if intent not in intents:
        raise ValueError(f"Intent {intent} is not defined in intents or blocked_intents")

    entry = intents[intent]
    target = str(entry.get("target", ""))
    first = _first_segment(target)
    target_known = target in known_tags or first in known_roots
    source_first = _first_segment(rel_path)
    already_under_target = rel_path == target or rel_path.startswith(f"{target}/")

    action = "keep" if already_under_target else "suggest_move"
    if source_first in known_roots and not already_under_target and intent == "manual_review":
        action = "review_in_place"

    payload = {
        "ok": True,
        "action": action,
        "source_path": rel_path,
        "intent": intent,
        "reason": reason,
        "target_base": target,
        "suggested_path": rel_path if already_under_target else _join_target(target, rel_path),
        "safety": entry.get("safety"),
        "target_registered": target_known,
        "notes": entry.get("notes", []),
    }
    if intent == "manual_review":
        review_policy = policy.get("review_queue_policy", {})
        payload["review_queue"] = {
            "status": "needs_decision",
            "queue_file": review_policy.get("queue_file", "runtime/cleanup/review-queue.jsonl"),
            "item_root": review_policy.get("item_root", "runtime/cleanup/review-items"),
            "manual_holding_root": review_policy.get(
                "manual_holding_root",
                "runtime/generated-workspaces/manual-review",
            ),
            "ttl_days": review_policy.get("ttl_days", {}).get("manual_review", 7),
            "required_fields": [
                "origin",
                "candidate_destinations",
                "confidence",
                "reason",
                "owner",
                "ttl_deadline",
                "decision",
            ],
        }
    return payload


def self_test(root: Path, policy_path: Path, tags_path: Path) -> dict[str, Any]:
    policy = _load_yaml(policy_path)
    tags = _load_yaml(tags_path)
    cases = [
        ("superpowers-plugin.zip", None, "imported_skill"),
        ("screen-recording.mp4", None, "raw_data"),
        ("client_secret.json", None, "secret"),
        ("new-feature-run.log", None, "runtime_trace"),
        ("stitch-ui-reference.png", None, "uiux_reference"),
        ("make-ppt-workflow.md", None, "workflow"),
        ("anything-unknown.xyz", None, "manual_review"),
        ("custom.md", "composed_capability", "composed_capability"),
    ]
    results = []
    for source, intent, expected in cases:
        suggestion = build_suggestion(source, root=root, policy=policy, tags=tags, requested_intent=intent)
        results.append(
            {
                "source": source,
                "expected": expected,
                "actual": suggestion["intent"],
                "ok": suggestion["intent"] == expected,
            }
        )
    ok = all(item["ok"] for item in results)
    return {"ok": ok, "cases": results}


def main() -> int:
    parser = argparse.ArgumentParser(description="Suggest a Willind file route without moving files.")
    parser.add_argument("path", nargs="?", help="File or directory path to classify.")
    parser.add_argument("--intent", help="Override inferred intent with a policy intent.")
    parser.add_argument("--root", default=str(DEFAULT_ROOT), help="Willind root path.")
    parser.add_argument("--policy", default=str(DEFAULT_POLICY), help="Routing policy YAML.")
    parser.add_argument("--tags", default=str(DEFAULT_TAGS), help="Path tag YAML.")
    parser.add_argument("--self-test", action="store_true", help="Run built-in smoke checks.")
    args = parser.parse_args()

    root = Path(args.root)
    policy_path = Path(args.policy)
    tags_path = Path(args.tags)

    try:
        if args.self_test:
            payload = self_test(root, policy_path, tags_path)
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return 0 if payload["ok"] else 1

        if not args.path:
            raise ValueError("path is required unless --self-test is used")

        policy = _load_yaml(policy_path)
        tags = _load_yaml(tags_path)
        payload = build_suggestion(
            args.path,
            root=root,
            policy=policy,
            tags=tags,
            requested_intent=args.intent,
        )
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:  # noqa: BLE001 - CLI should report structured errors.
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
