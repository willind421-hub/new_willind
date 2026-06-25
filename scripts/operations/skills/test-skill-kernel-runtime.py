from __future__ import annotations

import sys
from pathlib import Path


ROOT = next((p for p in Path(__file__).resolve().parents if (p / "registry" / "_index.yaml").exists()), Path(__file__).resolve().parent)
sys.path.insert(0, str(ROOT))

from core.kernel.skill_kernel_resolver import SkillKernelResolver  # noqa: E402


def assert_contains(values: list[str], expected: str, label: str) -> None:
    if expected not in values:
        raise AssertionError(f"{label}: expected {expected!r}, got {values!r}")


def capability_ids(result: dict) -> list[str]:
    return [entry["id"] for entry in result["selected_capabilities"]]


def intent_ids(result: dict) -> list[str]:
    return [entry["id"] for entry in result["intent_candidates"]]


def run_case(
    resolver: SkillKernelResolver,
    text: str,
    *,
    expected_capability: str,
    expected_lifecycle: str,
    expected_profile: str,
    expected_decision_contains: str | None = None,
    expected_provider: str | None = None,
) -> None:
    result = resolver.resolve(text)
    assert result["read_only"] is True
    assert result["would_execute"] is False
    assert result["intent_candidates"], f"{text}: no intent candidates"
    assert_contains(capability_ids(result), expected_capability, f"{text}: capability")

    permission = result["permission_decision"]
    if permission["lifecycle"] != expected_lifecycle:
        raise AssertionError(f"{text}: expected lifecycle {expected_lifecycle}, got {permission['lifecycle']}")
    if expected_decision_contains and expected_decision_contains not in permission["default_decision"]:
        raise AssertionError(
            f"{text}: expected decision containing {expected_decision_contains!r}, "
            f"got {permission['default_decision']!r}"
        )

    if expected_provider:
        route = result["provider_routes"][expected_capability]
        if route["primary"] != expected_provider:
            raise AssertionError(f"{text}: expected provider {expected_provider}, got {route['primary']}")

    skill_hub = result.get("skill_hub") or {}
    if not skill_hub.get("available"):
        raise AssertionError(f"{text}: skill hub unavailable")
    profile_id = skill_hub.get("selected_profile", {}).get("id")
    if profile_id != expected_profile:
        raise AssertionError(f"{text}: expected profile {expected_profile}, got {profile_id}")
    if skill_hub.get("would_execute"):
        raise AssertionError(f"{text}: skill hub attempted execution")
    if not skill_hub.get("canonical_hooks"):
        raise AssertionError(f"{text}: no canonical hooks")
    baseline = result.get("baseline_rules") or {}
    if not baseline.get("available"):
        raise AssertionError(f"{text}: baseline rules unavailable")
    if "epistemic_no_hallucination" not in baseline.get("must_rule_ids", []):
        raise AssertionError(f"{text}: no hallucination baseline missing")
    provider_bootstrap = result.get("provider_bootstrap") or {}
    if not provider_bootstrap.get("available"):
        raise AssertionError(f"{text}: provider bootstrap unavailable")
    if not provider_bootstrap.get("runner_targets"):
        raise AssertionError(f"{text}: provider bootstrap targets missing")


def main() -> int:
    resolver = SkillKernelResolver()

    run_case(
        resolver,
        "코딩 오류 고쳐줘",
        expected_capability="coding-lite",
        expected_lifecycle="execution",
        expected_profile="small_code_bug",
        expected_decision_contains="trace",
        expected_provider="codex_cli",
    )
    run_case(
        resolver,
        "이 코드 짜줘",
        expected_capability="coding-lite",
        expected_lifecycle="execution",
        expected_profile="small_code_bug",
        expected_decision_contains="trace",
        expected_provider="codex_cli",
    )
    run_case(
        resolver,
        "이런 생각하고 있는데 어떻게 생각해?",
        expected_capability="business-review",
        expected_lifecycle="proposal",
        expected_profile="planning_idea_expansion",
        expected_decision_contains="allow",
        expected_provider="browser_session",
    )
    run_case(
        resolver,
        "시장 조사해줘",
        expected_capability="research-synthesis",
        expected_lifecycle="observation",
        expected_profile="market_research",
        expected_decision_contains="allow",
        expected_provider="browser_session",
    )
    run_case(
        resolver,
        "조사해줘",
        expected_capability="research-synthesis",
        expected_lifecycle="observation",
        expected_profile="market_research",
        expected_decision_contains="allow",
        expected_provider="browser_session",
    )
    run_case(
        resolver,
        "리서치해줘",
        expected_capability="research-synthesis",
        expected_lifecycle="observation",
        expected_profile="market_research",
        expected_decision_contains="allow",
        expected_provider="browser_session",
    )
    run_case(
        resolver,
        "나 웹사이트 만들어서 뭔가 팔고 싶어",
        expected_capability="idea-to-spec-convergence",
        expected_lifecycle="proposal",
        expected_profile="idea_to_seed_convergence",
        expected_decision_contains="allow",
        expected_provider="claude_cli",
    )
    online_seed_result = resolver.resolve("뭔가 온라인으로 팔아보고 싶은데 아직 뭘 팔지 모르겠어")
    online_seed_capabilities = capability_ids(online_seed_result)
    assert_contains(
        online_seed_capabilities,
        "idea-to-spec-convergence",
        "vague online selling: seed convergence capability",
    )
    assert_contains(
        online_seed_capabilities,
        "business-review",
        "vague online selling: business review capability",
    )
    assert_contains(
        online_seed_capabilities,
        "research-synthesis",
        "vague online selling: research synthesis capability",
    )
    online_seed_profile = online_seed_result.get("skill_hub", {}).get("selected_profile", {}).get("id")
    if online_seed_profile != "idea_to_seed_convergence":
        raise AssertionError(f"vague online selling: expected idea_to_seed_convergence, got {online_seed_profile}")
    online_seed_hooks = (
        online_seed_result.get("skill_hub", {})
        .get("provider_injection_preview", {})
        .get("hook_capsules", [])
    )
    planning_hooks = [item for item in online_seed_hooks if item.get("hook") == "planning"]
    if not planning_hooks or "8-12" not in str(planning_hooks[0].get("instruction", "")):
        raise AssertionError("vague online selling: planning hook must request active interview questions")
    online_seed_contract = (
        online_seed_result.get("skill_hub", {})
        .get("provider_injection_preview", {})
        .get("response_contract", {})
    )
    if online_seed_contract.get("id") != "idea_to_seed_interview_contract":
        raise AssertionError("vague online selling: response contract missing")
    if online_seed_contract.get("must_ask_8_to_12_interview_questions") is not True:
        raise AssertionError("vague online selling: response contract must require 8-12 interview questions")
    contract_text = " ".join(str(item) for item in online_seed_contract.get("forbidden", []))
    if "generic recommendation list" not in contract_text:
        raise AssertionError("vague online selling: response contract must forbid generic recommendation lists")
    run_case(
        resolver,
        "스킬샵 같은 AI 팩을 만들어 팔 수 있을까?",
        expected_capability="idea-to-spec-convergence",
        expected_lifecycle="proposal",
        expected_profile="idea_to_seed_convergence",
        expected_decision_contains="allow",
        expected_provider="claude_cli",
    )
    run_case(
        resolver,
        "실험 돌려봐",
        expected_capability="bounded-experiment-loop",
        expected_lifecycle="execution",
        expected_profile="bounded_experiment_loop",
        expected_decision_contains="trace",
        expected_provider="codex_cli",
    )
    run_case(
        resolver,
        "이 스킬 흡수해줘",
        expected_capability="external-skill-absorption",
        expected_lifecycle="proposal",
        expected_profile="external_skill_absorption",
        expected_decision_contains="allow",
        expected_provider="codex_cli",
    )
    run_case(
        resolver,
        "물건 하나 사줘",
        expected_capability="app-action-draft",
        expected_lifecycle="payment",
        expected_profile="payment_request",
        expected_decision_contains="confirm",
        expected_provider="browser_session",
    )
    run_case(
        resolver,
        "결제 직전까지만 준비해줘",
        expected_capability="app-action-draft",
        expected_lifecycle="preparation",
        expected_profile="app_purchase_preparation",
        expected_decision_contains="trace",
        expected_provider="browser_session",
    )
    run_case(
        resolver,
        "장바구니 담기 전에 확인 받아",
        expected_capability="app-action-draft",
        expected_lifecycle="cart_or_reservation",
        expected_profile="cart_or_reservation_gate",
        expected_decision_contains="trace",
        expected_provider="browser_session",
    )
    run_case(
        resolver,
        "이 파일 삭제해",
        expected_capability="permission-review",
        expected_lifecycle="delete",
        expected_profile="file_delete",
        expected_decision_contains="confirm",
        expected_provider="local_policy",
    )
    run_case(
        resolver,
        "스샷 보고 UI 판단해줘",
        expected_capability="visual-ui-review",
        expected_lifecycle="proposal",
        expected_profile="screenshot_ui_judgement",
        expected_decision_contains="allow",
        expected_provider="browser_session",
    )
    run_case(
        resolver,
        "구조가 맞는지 검토해줘",
        expected_capability="architecture-review",
        expected_lifecycle="proposal",
        expected_profile="architecture_review",
        expected_decision_contains="allow",
        expected_provider="claude_cli",
    )

    structure_result = resolver.resolve("구조가 맞는지 검토해줘")
    assert_contains(intent_ids(structure_result), "structure_or_folder_decision", "structure intent")

    print("Skill Kernel runtime tests PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
