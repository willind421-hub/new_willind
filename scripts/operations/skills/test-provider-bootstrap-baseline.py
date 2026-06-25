from __future__ import annotations

import sys
from pathlib import Path


ROOT = next((p for p in Path(__file__).resolve().parents if (p / "registry" / "_index.yaml").exists()), Path(__file__).resolve().parent)
sys.path.insert(0, str(ROOT))

from core.kernel.skill_kernel_resolver import SkillKernelResolver  # noqa: E402


def main() -> int:
    resolver = SkillKernelResolver()
    cases = [
        ("코딩 오류 고쳐줘", "codex_cli"),
        ("구조가 맞는지 검토해줘", "claude_cli"),
        ("시장 조사해줘", "gemini_api_or_browser"),
        ("스샷 보고 UI 판단해줘", "gemini_api_or_browser"),
        ("물건 하나 사줘", "browser_session"),
    ]
    failures: list[str] = []

    for text, expected_runner_hint in cases:
        result = resolver.resolve(text, input_channel="telegram")
        baseline = result.get("baseline_rules") or {}
        bootstrap = result.get("provider_bootstrap") or {}
        injection = result.get("skill_hub", {}).get("provider_injection_preview", {})

        if not baseline.get("always_on"):
            failures.append(f"{text}: baseline is not always_on")
        if "epistemic_no_hallucination" not in baseline.get("must_rule_ids", []):
            failures.append(f"{text}: anti-hallucination rule missing")
        if baseline.get("channel") != "telegram":
            failures.append(f"{text}: channel override not preserved")
        if (baseline.get("channel_override") or {}).get("noise_rejection") != "disabled":
            failures.append(f"{text}: Telegram typed text still treated like noisy voice")

        runner_targets = bootstrap.get("runner_targets") or []
        if expected_runner_hint not in runner_targets:
            failures.append(f"{text}: expected runner {expected_runner_hint}, got {runner_targets}")
        if not bootstrap.get("baseline_rule_ids"):
            failures.append(f"{text}: provider bootstrap has no baseline rule ids")

        provider_capsules = injection.get("provider_capsules") or []
        if not provider_capsules:
            failures.append(f"{text}: no provider capsules")
        for capsule in provider_capsules:
            if not capsule.get("baseline_rule_ids"):
                failures.append(f"{text}: provider capsule {capsule.get('runner')} lacks baseline ids")
        if injection.get("would_execute"):
            failures.append(f"{text}: injection preview attempted execution")

    if failures:
        raise AssertionError("\n".join(failures))
    print("PASS provider bootstrap baseline")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
