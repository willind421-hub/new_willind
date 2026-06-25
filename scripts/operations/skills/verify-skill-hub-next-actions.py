from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import yaml


ROOT = next((p for p in Path(__file__).resolve().parents if (p / "registry" / "_index.yaml").exists()), Path(__file__).resolve().parent)
NEXT_ACTIONS_PATH = ROOT / "registry/skills/skill-hub-next-actions.yaml"
ACTION_RUNTIME_DIR = ROOT / "<your-backend>"
REQUIRED_TRACK_FIELDS = {
    "order",
    "id",
    "title",
    "action_runtime_safe_action",
    "registry_refs",
    "dashboard_surface",
    "safe_now",
    "confirm_or_block",
}


def load_yaml(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def rel(path: Path) -> str:
    return str(path.relative_to(ROOT)).replace("\\", "/")


def main() -> int:
    failures: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []

    if not NEXT_ACTIONS_PATH.exists():
        failures.append({"path": rel(NEXT_ACTIONS_PATH), "message": "next actions registry missing"})
        print(json.dumps({"ok": False, "failures": failures, "warnings": warnings}, ensure_ascii=False, indent=2))
        return 1

    data = load_yaml(NEXT_ACTIONS_PATH)
    tracks = data.get("tracks", [])
    if not isinstance(tracks, list):
        failures.append({"path": rel(NEXT_ACTIONS_PATH), "message": "tracks must be a list"})
        tracks = []

    orders = [track.get("order") for track in tracks if isinstance(track, dict)]
    if sorted(orders) != list(range(1, 11)):
        failures.append({"path": rel(NEXT_ACTIONS_PATH), "message": f"track orders must be 1..10, got {orders}"})

    sys.path.insert(0, str(ACTION_RUNTIME_DIR))
    from services import action_runtime

    action_types = set(action_runtime.ACTION_DEFINITIONS)
    registered_safe_actions = set(action_runtime.POST_AUTORESEARCH_TRACK_ACTIONS)

    for track in tracks:
        if not isinstance(track, dict):
            failures.append({"path": rel(NEXT_ACTIONS_PATH), "message": "track entry must be a mapping"})
            continue
        missing = REQUIRED_TRACK_FIELDS - set(track)
        if missing:
            failures.append(
                {
                    "path": rel(NEXT_ACTIONS_PATH),
                    "message": f"track {track.get('id')} missing fields: {sorted(missing)}",
                }
            )
        action = track.get("action_runtime_safe_action")
        if action not in action_types:
            failures.append(
                {
                    "path": rel(NEXT_ACTIONS_PATH),
                    "message": f"track {track.get('id')} references unknown action {action}",
                }
            )
            continue
        if action not in registered_safe_actions:
            failures.append(
                {
                    "path": rel(NEXT_ACTIONS_PATH),
                    "message": f"track {track.get('id')} action {action} is not registered as post-autoresearch track",
                }
            )
        definition = action_runtime.ACTION_DEFINITIONS[action]
        if definition.effective_requires_permission():
            failures.append(
                {
                    "path": rel(NEXT_ACTIONS_PATH),
                    "message": f"track {track.get('id')} action {action} unexpectedly requires permission",
                }
            )
        if not track.get("safe_now"):
            failures.append({"path": rel(NEXT_ACTIONS_PATH), "message": f"track {track.get('id')} has empty safe_now"})
        if not track.get("confirm_or_block"):
            failures.append(
                {"path": rel(NEXT_ACTIONS_PATH), "message": f"track {track.get('id')} has empty confirm_or_block"}
            )
        for ref in track.get("registry_refs", []):
            ref_path = ROOT / str(ref)
            if not ref_path.exists():
                warnings.append(
                    {
                        "path": rel(NEXT_ACTIONS_PATH),
                        "message": f"track {track.get('id')} reference does not exist yet: {ref}",
                    }
                )

    report = {
        "ok": not failures,
        "failures": failures,
        "warnings": warnings,
        "counts": {
            "tracks": len(tracks),
            "action_runtime_track_actions": len(registered_safe_actions),
        },
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
