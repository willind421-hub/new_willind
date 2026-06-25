from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml


DEFAULT_ROOT = next((p for p in Path(__file__).resolve().parents if (p / "registry" / "_index.yaml").exists()), Path(__file__).resolve().parent)
DEFAULT_POLICY = DEFAULT_ROOT / "registry/providers/provider-cli-routing.yaml"


def _load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{path} did not contain a YAML mapping")
    return data


def _task_classes(policy: dict[str, Any]) -> dict[str, Any]:
    tasks = policy.get("task_classes", {})
    if not isinstance(tasks, dict):
        raise ValueError("task_classes must be a mapping")
    return tasks


def classify_task(policy: dict[str, Any], text: str, requested_task: str | None = None) -> tuple[str, str]:
    tasks = _task_classes(policy)
    if requested_task:
        if requested_task not in tasks:
            raise ValueError(f"Unknown task class: {requested_task}")
        return requested_task, "explicit_task_class"

    normalized = text.strip()
    best: tuple[int, str, str] | None = None
    for task_id, task in tasks.items():
        triggers = task.get("triggers", []) if isinstance(task, dict) else []
        for pattern in triggers:
            matches = re.findall(str(pattern), normalized)
            if matches:
                score = len(matches)
                if best is None or score > best[0]:
                    best = (score, str(task_id), str(pattern))

    if best is not None:
        score, task_id, pattern = best
        return task_id, f"trigger:{pattern};score:{score}"

    return "architecture_review", "fallback_general_judgment"


def _provider_summary(policy: dict[str, Any], provider_ids: list[str]) -> list[dict[str, Any]]:
    providers = policy.get("providers", {})
    result = []
    for provider_id in provider_ids:
        provider = providers.get(provider_id, {})
        if not isinstance(provider, dict):
            provider = {}
        result.append(
            {
                "id": provider_id,
                "kind": provider.get("kind"),
                "status": provider.get("status"),
                "cost_posture": provider.get("cost_posture"),
                "default_weight": provider.get("default_weight"),
                "strengths": provider.get("strengths", []),
            }
        )
    return result


def build_route(policy: dict[str, Any], text: str, requested_task: str | None = None) -> dict[str, Any]:
    task_id, reason = classify_task(policy, text, requested_task)
    tasks = _task_classes(policy)
    task = tasks[task_id]
    presets = policy.get("multi_agent_presets", {})
    preset_id = str(task.get("preset", "cheap_single"))
    preset = presets.get(preset_id, {})
    if not isinstance(preset, dict):
        preset = {}

    primary = list(task.get("primary", []))
    reviewers = list(task.get("reviewers", []))
    implementers = list(task.get("implementers", []))
    fallback = list(task.get("fallback", []))
    provider_order = primary + reviewers + implementers + fallback

    return {
        "ok": True,
        "input": text,
        "task_class": task_id,
        "label": task.get("label"),
        "reason": reason,
        "preset": {
            "id": preset_id,
            "shape": preset.get("shape"),
            "max_agents": preset.get("max_agents"),
            "coordinator": preset.get("coordinator"),
            "synthesis": preset.get("synthesis"),
            "permission_gate": preset.get("permission_gate"),
        },
        "provider_plan": {
            "primary": _provider_summary(policy, primary),
            "reviewers": _provider_summary(policy, reviewers),
            "implementers": _provider_summary(policy, implementers),
            "fallback": _provider_summary(policy, fallback),
        },
        "budget_tier": task.get("budget_tier"),
        "risk_tier": task.get("risk_tier"),
        "notes": task.get("notes"),
        "decision_trace_required": policy.get("decision_trace", {}).get("required_fields", []),
        "benchmark_inputs": policy.get("weekly_update", {}).get("input_sources", []),
        "provider_order": provider_order,
    }


def self_test(policy_path: Path) -> dict[str, Any]:
    policy = _load_yaml(policy_path)
    cases = [
        ("코딩모드에서 테스트 실패 고쳐줘", None, "coding_implementation", "codex_primary_review_optional"),
        ("이 폴더 구조가 맞는지 판단해줘", None, "architecture_review", "two_model_debate"),
        ("유튜브 레퍼런스 영상 보고 UI 분석해줘", None, "visual_ui_research", "multimodal_research_synthesis"),
        ("돈 벌 기회 후보랑 실험 계획 만들어줘", None, "money_opportunity", "research_debate_with_permission_gate"),
        ("서버 502 오류랑 포트 상태 확인해줘", None, "monitoring_ops", "local_probe_then_agent"),
        ("내 대화 export로 개인화 분석해줘", None, "private_memory_analysis", "private_local_first"),
        ("간단하게 이 단어 뜻만 알려줘", None, "quick_question", "cheap_single"),
        ("custom", "workflow_or_skill_intake", "workflow_or_skill_intake", "registry_first_review"),
    ]
    results = []
    for text, requested_task, expected_task, expected_preset in cases:
        route = build_route(policy, text, requested_task)
        results.append(
            {
                "text": text,
                "expected_task": expected_task,
                "actual_task": route["task_class"],
                "expected_preset": expected_preset,
                "actual_preset": route["preset"]["id"],
                "ok": route["task_class"] == expected_task and route["preset"]["id"] == expected_preset,
            }
        )
    ok = all(item["ok"] for item in results)
    return {"ok": ok, "cases": results}


def main() -> int:
    parser = argparse.ArgumentParser(description="Suggest a Willind provider/CLI route without running providers.")
    parser.add_argument("text", nargs="?", help="User request or task description.")
    parser.add_argument("--task-class", help="Explicit task class override.")
    parser.add_argument("--policy", default=str(DEFAULT_POLICY), help="Provider routing YAML.")
    parser.add_argument("--self-test", action="store_true", help="Run built-in smoke checks.")
    args = parser.parse_args()

    try:
        policy_path = Path(args.policy)
        if args.self_test:
            payload = self_test(policy_path)
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return 0 if payload["ok"] else 1

        if not args.text:
            raise ValueError("text is required unless --self-test is used")
        policy = _load_yaml(policy_path)
        payload = build_route(policy, args.text, args.task_class)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:  # noqa: BLE001 - CLI should report structured errors.
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
