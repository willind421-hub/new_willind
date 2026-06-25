from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = next((p for p in Path(__file__).resolve().parents if (p / "registry" / "_index.yaml").exists()), Path(__file__).resolve().parent)
sys.path.insert(0, str(ROOT))

from core.kernel.skill_kernel_resolver import SkillKernelResolver  # noqa: E402


SMOKE_INPUTS = [
    "코딩 오류 고쳐줘",
    "시장 조사해줘",
    "물건 하나 사줘",
    "장바구니에 담아줘",
    "이 파일 삭제해",
    "스샷 보고 UI 판단해줘",
    "구조가 맞는지 검토해줘",
    "실험 돌려봐",
    "이 스킬 흡수해줘",
]


def main() -> int:
    resolver = SkillKernelResolver()
    results = [resolver.resolve(text) for text in SMOKE_INPUTS]

    failures: list[str] = []
    for result in results:
        text = result["input"]["text"]
        if not result["selected_capabilities"]:
            failures.append(f"{text}: no selected capabilities")
        if not result["provider_routes"]:
            failures.append(f"{text}: no provider routes")
        if result["would_execute"]:
            failures.append(f"{text}: resolver attempted execution")
        if not result["permission_decision"].get("lifecycle"):
            failures.append(f"{text}: no permission lifecycle")
        skill_hub = result.get("skill_hub") or {}
        if not skill_hub.get("available"):
            failures.append(f"{text}: skill hub unavailable")
        if not skill_hub.get("selected_profile", {}).get("id"):
            failures.append(f"{text}: no skill hub selected profile")
        if skill_hub.get("would_execute"):
            failures.append(f"{text}: skill hub attempted execution")
        baseline = result.get("baseline_rules") or {}
        if not baseline.get("available"):
            failures.append(f"{text}: baseline rules unavailable")
        if "epistemic_no_hallucination" not in baseline.get("must_rule_ids", []):
            failures.append(f"{text}: no hallucination baseline missing")
        provider_bootstrap = result.get("provider_bootstrap") or {}
        if not provider_bootstrap.get("available"):
            failures.append(f"{text}: provider bootstrap unavailable")
        if not provider_bootstrap.get("runner_targets"):
            failures.append(f"{text}: provider bootstrap targets missing")

    report = {
        "ok": not failures,
        "failures": failures,
        "cases": [
            {
                "text": result["input"]["text"],
                "capabilities": [capability["id"] for capability in result["selected_capabilities"]],
                "lifecycle": result["permission_decision"]["lifecycle"],
                "decision": result["permission_decision"]["default_decision"],
                "skill_hub_profile": result["skill_hub"]["selected_profile"]["id"],
                "skill_hub_hooks": result["skill_hub"]["canonical_hooks"],
                "baseline_rules": result["baseline_rules"]["must_rule_ids"],
                "provider_bootstrap_targets": result["provider_bootstrap"]["runner_targets"],
            }
            for result in results
        ],
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
