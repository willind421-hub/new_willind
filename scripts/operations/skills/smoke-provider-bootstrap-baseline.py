from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = next((p for p in Path(__file__).resolve().parents if (p / "registry" / "_index.yaml").exists()), Path(__file__).resolve().parent)
sys.path.insert(0, str(ROOT))

from core.kernel.skill_kernel_resolver import SkillKernelResolver  # noqa: E402


SMOKE_INPUTS = [
    "안녕 윌린드",
    "코딩 오류 고쳐줘",
    "구조가 맞는지 검토해줘",
    "시장 조사해줘",
    "물건 하나 사줘",
]


def main() -> int:
    resolver = SkillKernelResolver()
    cases = []
    failures: list[str] = []
    for text in SMOKE_INPUTS:
        result = resolver.resolve(text, input_channel="telegram")
        baseline = result.get("baseline_rules") or {}
        bootstrap = result.get("provider_bootstrap") or {}
        case = {
            "text": text,
            "baseline_available": bool(baseline.get("available")),
            "always_on": bool(baseline.get("always_on")),
            "must_rules": baseline.get("must_rule_ids", []),
            "provider_bootstrap_available": bool(bootstrap.get("available")),
            "runner_targets": bootstrap.get("runner_targets", []),
            "would_execute": bool(result.get("would_execute")),
        }
        cases.append(case)

        if not case["baseline_available"] or not case["always_on"]:
            failures.append(f"{text}: baseline unavailable")
        if "epistemic_no_hallucination" not in case["must_rules"]:
            failures.append(f"{text}: epistemic baseline missing")
        if not case["provider_bootstrap_available"] or not case["runner_targets"]:
            failures.append(f"{text}: provider bootstrap unavailable")
        if case["would_execute"]:
            failures.append(f"{text}: resolver attempted execution")

    report = {
        "ok": not failures,
        "failures": failures,
        "cases": cases,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
