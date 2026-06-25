from __future__ import annotations

import sys
from pathlib import Path


ROOT = next((p for p in Path(__file__).resolve().parents if (p / "registry" / "_index.yaml").exists()), Path(__file__).resolve().parent)
sys.path.insert(0, str(ROOT))

from core.kernel.provider_bootstrap_builder import build_provider_bootstraps, write_provider_bootstraps  # noqa: E402


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def packet_for(text: str, provider: str, channel: str = "telegram") -> dict:
    packets = build_provider_bootstraps(text, input_channel=channel, provider=provider)
    assert_true(len(packets) == 1, f"{text}: expected one provider packet for {provider}")
    return packets[0].packet


def built_for(text: str, provider: str, channel: str = "telegram"):
    packets = build_provider_bootstraps(text, input_channel=channel, provider=provider)
    assert_true(len(packets) == 1, f"{text}: expected one provider packet for {provider}")
    return packets[0]


def main() -> int:
    failures: list[str] = []

    cases = [
        ("코딩 오류 고쳐줘", "codex", "codex_cli", "small_code_bug", "coding-lite"),
        ("구조가 맞는지 검토해줘", "claude", "claude_cli", "architecture_review", "architecture-review"),
        ("시장 조사해줘", "gemini", "gemini_api_or_browser", "market_research", "research-synthesis"),
        ("코딩 오류 고쳐줘", "antigravity", "common", "small_code_bug", "coding-lite"),
        ("오픈코드로 코드 확인해줘", "opencode", "opencode_cli", "small_code_bug", "coding-lite"),
        ("오픈소스 러너로 일반 검토해줘", "open_source", "common", "architecture_review", "architecture-review"),
    ]

    for text, requested, expected_provider, expected_profile, expected_capability in cases:
        try:
            packet = packet_for(text, requested)
            assert_true(packet["provider"]["id"] == expected_provider, f"{text}: provider mismatch")
            assert_true(packet["selected_profile"]["id"] == expected_profile, f"{text}: profile mismatch")
            assert_true(packet["would_execute"] is False, f"{text}: packet must not execute")
            assert_true(packet["read_only"] is True, f"{text}: packet must be read-only")
            assert_true(
                "epistemic_no_hallucination" in packet["baseline"]["rule_ids"],
                f"{text}: anti-hallucination baseline missing",
            )
            assert_true(
                "permission_gate_first_for_side_effects" in packet["baseline"]["rule_ids"],
                f"{text}: permission baseline missing",
            )
            avoid = set(packet["baseline"]["avoid_loading"]) | set(packet["skill_loading"]["avoid_loading"])
            assert_true(
                "situational_skill_only_when_selected" in packet["baseline"]["rule_ids"],
                f"{text}: situational skill boundary missing",
            )
            assert_true(
                bool(avoid),
                f"{text}: provider avoidance boundary missing",
            )
            assert_true(
                bool(
                    avoid
                    & {
                        "all_external_skill_bodies",
                        "private_raw_data_without_redaction",
                        "raw_private_exports",
                        "raw_private_exports_without_redaction",
                        "provider_specific_prompt_body",
                        "account_action_context",
                        "payment_or_external_send_context",
                        "workspace_credentials",
                        "remote_runtime_config_without_gate",
                    }
                ),
                f"{text}: provider boundary avoidance missing",
            )
            if expected_capability:
                assert_true(
                    expected_capability in packet["skill_loading"]["capabilities"]
                    or expected_capability in packet["skill_loading"]["may_read"],
                    f"{text}: expected capability {expected_capability} missing",
                )
        except AssertionError as exc:
            failures.append(str(exc))

    try:
        text = "뭔가 온라인으로 팔아보고 싶은데 아직 뭘 팔지 모르겠어 100만원이라도 좋아 돈 벌고 싶어"
        built = built_for(text, "codex")
        packet = built.packet
        assert_true(packet["provider"]["id"] == "codex_cli", "seed convergence: provider mismatch")
        assert_true(
            packet["selected_profile"]["id"] == "idea_to_seed_convergence",
            "seed convergence: profile mismatch",
        )
        contract = packet.get("response_contract") or {}
        assert_true(
            contract.get("id") == "idea_to_seed_interview_contract",
            "seed convergence: response contract missing",
        )
        assert_true(
            contract.get("must_ask_8_to_12_interview_questions") is True,
            "seed convergence: response contract must require interview questions",
        )
        assert_true("## 응답 계약" in built.markdown, "seed convergence: markdown response contract missing")
        assert_true("8-12" in built.markdown, "seed convergence: markdown interview count missing")
    except AssertionError as exc:
        failures.append(str(exc))

    try:
        out_root = ROOT / "runtime/smoke/provider-bootstrap-packets"
        report = write_provider_bootstraps(
            "코딩 오류 고쳐줘",
            input_channel="telegram",
            provider="codex",
            output_root=out_root,
        )
        assert_true(report["ok"] is True, "write report not ok")
        for item in report["files"]:
            assert_true(Path(item["json"]).exists(), f"missing json: {item['json']}")
            assert_true(Path(item["markdown"]).exists(), f"missing markdown: {item['markdown']}")
    except AssertionError as exc:
        failures.append(str(exc))

    if failures:
        raise AssertionError("\n".join(failures))
    print("PASS provider bootstrap packets")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
