from __future__ import annotations

import json
import re
from datetime import date, datetime
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


ROOT = next((p for p in Path(__file__).resolve().parents if (p / "registry" / "_index.yaml").exists()), Path(__file__).resolve().parent)


RULE_KEYWORDS: dict[str, list[str]] = {
    "quick_small_code_change": [
        "코딩",
        "코드",
        "코드 짜",
        "짜줘",
        "개발",
        "dev",
        "오류",
        "에러",
        "버그",
        "테스트",
        "빌드",
        "컴파일",
        "고쳐",
        "수정",
        "lint",
    ],
    "idea_or_thinking_review": [
        "이런 생각",
        "어떻게 생각",
        "어때",
        "생각",
        "아이디어",
        "브레인스토밍",
        "가능성",
        "방향",
        "고민",
    ],
    "structure_or_folder_decision": [
        "구조",
        "폴더",
        "척추",
        "registry",
        "레지스트리",
        "kernel",
        "커널",
        "설계",
        "아키텍처",
        "검토",
        "맞는지",
    ],
    "money_or_business_opportunity": [
        "돈",
        "수익",
        "사업",
        "시장",
        "가격",
        "고객",
        "매출",
        "외주",
        "기회",
        "랜딩",
    ],
    "external_reference_research": [
        "조사",
        "찾아",
        "검색",
        "서칭",
        "리서치",
        "벤치마킹",
        "레퍼런스",
        "공식문서",
    ],
    "idea_to_seed_convergence": [
        "웹사이트",
        "온라인으로 팔",
        "무언가 팔",
        "팔아보고",
        "팔고 싶",
        "뭘 팔",
        "뭐 팔",
        "아직 뭘",
        "아직 뭐",
        "뭘 할 수",
        "컴퓨터 안에서",
        "디지털 상품",
        "상품 아이디어",
        "스킬샵",
        "스킬 샵",
        "스킬팩",
        "ai 팩",
        "팩 판매",
        "팩을 만들",
        "ai가 대세",
        "구체화",
        "막연",
        "seed",
        "수렴",
    ],
    "bounded_experiment_loop": [
        "실험",
        "실험 돌려",
        "반복",
        "반복해서 개선",
        "개선 후보",
        "성능 개선",
        "metric",
        "메트릭",
        "지표",
        "keep/discard",
        "고정 예산",
        "밤새",
        "후보 돌려",
    ],
    "external_skill_absorption": [
        "스킬 흡수",
        "스킬 가져",
        "스킬 적용",
        "스킬 분류",
        "플러그인 흡수",
        "플러그인 적용",
        "원본 구조",
        "외부 스킬",
        "capabilities/imported",
        "adapter",
        "어댑터",
    ],
    "app_or_browser_action_preparation": [
        "사줘",
        "구매",
        "티케팅",
        "예매",
        "예약",
        "장바구니",
        "메일",
        "카카오",
        "앱",
        "브라우저",
    ],
    "permission_boundary_unclear": [
        "삭제",
        "지워",
        "제거",
        "보내",
        "전송",
        "결제",
        "계정",
        "비밀번호",
        "토큰",
        "api key",
        "api키",
    ],
    "visual_or_ui_issue": [
        "스샷",
        "스크린샷",
        "ui",
        "화면",
        "창",
        "패널",
        "다크모드",
        "라이트모드",
        "디자인",
        "시각",
        "브라우저",
    ],
    "compound_product_work": [
        "처음부터",
        "끝까지",
        "완성",
        "테스트까지",
        "외주",
        "프로젝트",
    ],
}


SEED_CONVERGENCE_CONTEXT_KEYWORDS = [
    "온라인으로 팔",
    "무언가 팔",
    "팔아보고",
    "팔고 싶",
    "뭘 팔",
    "뭐 팔",
    "웹사이트",
    "디지털 상품",
    "상품 아이디어",
    "스킬샵",
    "스킬 샵",
    "스킬팩",
    "ai 팩",
    "팩 판매",
    "팩관련 판매",
    "팩을 만들",
    "컴퓨터 안에서",
    "ai가 대세",
    "ai 관련",
]


SEED_CONVERGENCE_AMBIGUITY_KEYWORDS = [
    "뭔가",
    "아직",
    "모르",
    "뭘",
    "뭐",
    "싶어",
    "싶은데",
    "있을까",
    "재밌",
    "막연",
    "구체화",
]


LIFECYCLE_KEYWORDS: list[tuple[str, list[str]]] = [
    (
        "account_change",
        ["계정 설정", "비밀번호", "비번", "oauth", "api key", "api키", "토큰 생성", "토큰 삭제", "보안 설정"],
    ),
    (
        "preparation",
        ["결제 직전", "직전까지만", "준비", "후보", "비교", "가격 찾아", "정리만"],
    ),
    (
        "cart_or_reservation",
        ["장바구니", "담아", "담기", "티케팅", "예매", "좌석", "홀드", "예약 잡아", "예약만"],
    ),
    (
        "payment",
        ["결제", "구매", "사줘", "바로 구매", "예약 확정", "구독", "광고 집행", "계좌이체", "송금"],
    ),
    (
        "external_send",
        ["보내줘", "전송", "메일 보내", "댓글", "dm", "디엠", "게시", "업로드", "웹훅"],
    ),
    ("delete", ["삭제", "지워", "제거", "날려", "비워"]),
    (
        "execution",
        [
            "고쳐",
            "수정",
            "실행",
            "켜줘",
            "만들어",
            "짜줘",
            "구현",
            "빌드",
            "테스트",
            "재시작",
            "적용",
            "옮겨",
            "이동",
            "돌려",
            "실험 돌려",
            "개선해",
        ],
    ),
    ("draft", ["초안", "계획", "가격표", "문구", "작성"]),
    (
        "proposal",
        [
            "추천",
            "판단",
            "검토",
            "맞는지",
            "어떻게",
            "어때",
            "기획",
            "아이디어",
            "확장",
            "사업 전략",
            "길게 분석",
            "생각",
            "고민",
            "방향",
            "브레인스토밍",
            "스킬 흡수",
            "플러그인 흡수",
            "스킬 분류",
            "원본 구조",
        ],
    ),
]


TOKEN_RE = re.compile(r"[A-Za-z0-9가-힣_+#./-]{2,}")


@dataclass(frozen=True)
class ResolverPaths:
    root: Path = ROOT
    kernel: Path = ROOT / "core/kernel/kernel-routing.yaml"
    baseline_rules: Path = ROOT / "registry/kernel/baseline-rules.yaml"
    skill_routing: Path = ROOT / "registry/hooks/skill-routing.yaml"
    provider_routing: Path = ROOT / "registry/providers/skill-provider-routing.yaml"
    provider_bootstrap: Path = ROOT / "registry/providers/provider-bootstrap.yaml"
    permission_policy: Path = ROOT / "registry/permissions/permission-gate-policy.yaml"
    skill_hub: Path = ROOT / "registry/skills/skill-hub.yaml"
    knowledge_sources: Path = ROOT / "registry/knowledge/sources.yaml"
    knowledge_packs: Path = ROOT / "registry/knowledge/context-packs.yaml"


def _load_yaml(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def _rel(path: Path, root: Path = ROOT) -> str:
    return str(path.relative_to(root)).replace("\\", "/")


def _normalize(text: str) -> str:
    return " ".join(text.strip().lower().split())


def _tokens(text: str) -> set[str]:
    return set(TOKEN_RE.findall(_normalize(text)))


def _keyword_matches(text: str, keyword: str) -> bool:
    normalized = _normalize(text)
    keyword_norm = _normalize(keyword)
    if not keyword_norm:
        return False
    # Short ASCII tokens such as "DM" must not match inside unrelated words or
    # paths like README. Korean phrases and longer phrases still use substring
    # matching because spacing can vary in natural input.
    if re.fullmatch(r"[a-z0-9_+#.-]{1,3}", keyword_norm):
        return keyword_norm in _tokens(text)
    return keyword_norm in normalized


def _contains_any(text: str, keywords: list[str]) -> list[str]:
    return [keyword for keyword in keywords if _keyword_matches(text, keyword)]


class SkillKernelResolver:
    """Read-only resolver for Willind Skill Kernel registry contracts."""

    def __init__(self, paths: ResolverPaths | None = None) -> None:
        self.paths = paths or ResolverPaths()
        self.kernel = _load_yaml(self.paths.kernel)
        self.baseline_rules = _load_yaml(self.paths.baseline_rules) if self.paths.baseline_rules.exists() else {}
        self.skill_routing = _load_yaml(self.paths.skill_routing)
        self.provider_routing = _load_yaml(self.paths.provider_routing)
        self.provider_bootstrap = _load_yaml(self.paths.provider_bootstrap) if self.paths.provider_bootstrap.exists() else {}
        self.permission_policy = _load_yaml(self.paths.permission_policy)
        self.skill_hub = _load_yaml(self.paths.skill_hub) if self.paths.skill_hub.exists() else {}
        self.knowledge_sources = (
            _load_yaml(self.paths.knowledge_sources) if self.paths.knowledge_sources.exists() else {}
        )
        self.knowledge_packs = (
            _load_yaml(self.paths.knowledge_packs) if self.paths.knowledge_packs.exists() else {}
        )
        self.capabilities = self._load_capabilities()

    def resolve(self, input_text: str, *, input_channel: str = "text") -> dict[str, Any]:
        normalized = _normalize(input_text)
        intent_candidates = self._rank_intents(input_text)
        selected_capabilities = self._select_capabilities(intent_candidates)
        lifecycle = self._classify_lifecycle(input_text)
        permission_decision = self._permission_decision(lifecycle, input_text)
        provider_routes = self._provider_routes(selected_capabilities)
        storage_routes = self._storage_routes(selected_capabilities)
        skill_hub = self._skill_hub_resolution(
            input_text,
            intent_candidates,
            selected_capabilities,
            lifecycle,
            permission_decision,
            provider_routes,
            storage_routes,
        )
        knowledge_context = self._knowledge_context(intent_candidates, selected_capabilities)
        baseline_rules = self._baseline_rules_summary(input_channel)
        provider_bootstrap = self._provider_bootstrap_summary(skill_hub, provider_routes, baseline_rules)

        return {
            "contract": "willind.skill_kernel.runtime_resolution",
            "version": "0.1.1",
            "read_only": True,
            "would_execute": False,
            "input": {
                "text": input_text,
                "normalized_text": normalized,
                "channel": input_channel,
            },
            "intent_candidates": intent_candidates,
            "selected_capabilities": selected_capabilities,
            "provider_routes": provider_routes,
            "permission_decision": permission_decision,
            "storage_routes": storage_routes,
            "skill_hub": skill_hub,
            "baseline_rules": baseline_rules,
            "provider_bootstrap": provider_bootstrap,
            "knowledge_context": knowledge_context,
            "trace": {
                "registry_files": [
                    _rel(self.paths.kernel, self.paths.root),
                    *(
                        [_rel(self.paths.baseline_rules, self.paths.root)]
                        if self.paths.baseline_rules.exists()
                        else []
                    ),
                    _rel(self.paths.skill_routing, self.paths.root),
                    _rel(self.paths.provider_routing, self.paths.root),
                    *(
                        [_rel(self.paths.provider_bootstrap, self.paths.root)]
                        if self.paths.provider_bootstrap.exists()
                        else []
                    ),
                    _rel(self.paths.permission_policy, self.paths.root),
                    *([_rel(self.paths.skill_hub, self.paths.root)] if self.paths.skill_hub.exists() else []),
                    *(
                        [_rel(self.paths.knowledge_sources, self.paths.root)]
                        if self.paths.knowledge_sources.exists()
                        else []
                    ),
                    *(
                        [_rel(self.paths.knowledge_packs, self.paths.root)]
                        if self.paths.knowledge_packs.exists()
                        else []
                    ),
                ],
                "safe_runtime_boundary": "resolver_only_no_tool_execution",
            },
        }

    def _baseline_rules_summary(self, input_channel: str) -> dict[str, Any]:
        if not self.baseline_rules:
            return {
                "available": False,
                "read_only": True,
                "would_execute": False,
                "reason": "baseline_rules_registry_missing",
            }

        rules = self.baseline_rules.get("rules", [])
        channel_overrides = self.baseline_rules.get("channel_overrides", {})
        channel_override = channel_overrides.get(input_channel) or channel_overrides.get("default") or {}
        must_rules = [
            rule
            for rule in rules
            if isinstance(rule, dict) and str(rule.get("severity", "")).lower() == "must"
        ]
        return {
            "contract": self.baseline_rules.get("contract", "willind.kernel.baseline_rules"),
            "version": self.baseline_rules.get("version", "0.1.0"),
            "available": True,
            "read_only": True,
            "would_execute": False,
            "always_on": bool(self.baseline_rules.get("always_on", True)),
            "load_stage": self.baseline_rules.get("load_stage", "before_skill_selection"),
            "rule_ids": [str(rule.get("id")) for rule in rules if isinstance(rule, dict) and rule.get("id")],
            "must_rule_ids": [str(rule.get("id")) for rule in must_rules if rule.get("id")],
            "channel": input_channel,
            "channel_override": channel_override,
            "provider_injection": self.baseline_rules.get("provider_injection", {}),
            "trace": {
                "registry_file": _rel(self.paths.baseline_rules, self.paths.root),
                "safe_runtime_boundary": "baseline_metadata_only_no_tool_execution",
            },
        }

    def _provider_bootstrap_summary(
        self,
        skill_hub: dict[str, Any],
        provider_routes: dict[str, Any],
        baseline_rules: dict[str, Any],
    ) -> dict[str, Any]:
        if not self.provider_bootstrap:
            return {
                "available": False,
                "read_only": True,
                "would_execute": False,
                "reason": "provider_bootstrap_registry_missing",
            }

        profiles = self.provider_bootstrap.get("profiles", {})
        selected_policy = {}
        if isinstance(skill_hub, dict):
            selected_policy = skill_hub.get("provider_loading_policy", {})
            if not isinstance(selected_policy, dict):
                selected_policy = {}
        primary_runner = selected_policy.get("primary_runner") or "willind_ai_rules"
        runner_targets = self._provider_injection_targets(str(primary_runner), provider_routes)

        selected_profiles: dict[str, Any] = {}
        for target in runner_targets:
            selected_profiles[target] = profiles.get(target) or profiles.get("common") or {}

        return {
            "contract": self.provider_bootstrap.get("contract", "willind.provider_bootstrap"),
            "version": self.provider_bootstrap.get("version", "0.1.0"),
            "available": True,
            "read_only": True,
            "would_execute": False,
            "load_order": self.provider_bootstrap.get("load_order", []),
            "baseline_rule_ids": baseline_rules.get("must_rule_ids") or baseline_rules.get("rule_ids") or [],
            "primary_runner": primary_runner,
            "runner_targets": runner_targets,
            "profiles": {
                target: {
                    "id": profile.get("id", target),
                    "kind": profile.get("kind"),
                    "auto_read": profile.get("auto_read", []),
                    "situational_skill_loading": profile.get("situational_skill_loading"),
                    "default_capsule_ids": profile.get("default_capsule_ids", []),
                    "avoid_loading": profile.get("avoid_loading", []),
                }
                for target, profile in selected_profiles.items()
                if isinstance(profile, dict)
            },
            "trace": {
                "registry_file": _rel(self.paths.provider_bootstrap, self.paths.root),
                "safe_runtime_boundary": "provider_bootstrap_metadata_only_no_provider_start",
            },
        }

    def _load_capabilities(self) -> dict[str, dict[str, Any]]:
        capabilities: dict[str, dict[str, Any]] = {}
        for capability_id, relative_path in self.skill_routing.get("capability_registry", {}).items():
            path = self.paths.root / relative_path
            data = _load_yaml(path)
            data["_path"] = _rel(path, self.paths.root)
            capabilities[capability_id] = data
        return capabilities

    def _rank_intents(self, input_text: str) -> list[dict[str, Any]]:
        normalized = _normalize(input_text)
        input_tokens = _tokens(input_text)
        candidates: list[dict[str, Any]] = []

        for rule in self.skill_routing.get("hook_rules", []):
            rule_id = rule.get("id", "")
            score = 0
            matched: list[str] = []

            for example in rule.get("trigger_examples", []):
                example_norm = _normalize(example)
                if example_norm and example_norm in normalized:
                    score += 6
                    matched.append(f"example:{example}")
                for token in _tokens(example):
                    if token in input_tokens:
                        score += 1
                        matched.append(f"example_token:{token}")

            for keyword in RULE_KEYWORDS.get(rule_id, []):
                if _keyword_matches(input_text, keyword):
                    score += 3
                    matched.append(f"keyword:{keyword}")

            # Situation text is a weak hint. It prevents English registry terms
            # like provider/kernel/registry from being ignored in Korean input.
            for token in _tokens(rule.get("situation", "")):
                if token in input_tokens:
                    score += 1
                    matched.append(f"situation_token:{token}")

            if score > 0:
                candidates.append(
                    {
                        "id": rule_id,
                        "score": score,
                        "capabilities": rule.get("capabilities", []),
                        "hook_timing": rule.get("hook_timing", []),
                        "permission_hint": rule.get("permission_hint"),
                        "matched": sorted(set(matched)),
                    }
                )

        if not candidates:
            fallback = self.skill_routing.get("selection_policy", {}).get("fallback", {}).get(
                "unknown_intent", "research-synthesis"
            )
            candidates.append(
                {
                    "id": "unknown_intent",
                    "score": 1,
                    "capabilities": [fallback],
                    "hook_timing": ["intent_detected"],
                    "permission_hint": "unknown_intent",
                    "matched": ["fallback:unknown_intent"],
                }
            )

        return sorted(candidates, key=lambda candidate: (-candidate["score"], candidate["id"]))

    def _select_capabilities(self, intent_candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
        selected: list[dict[str, Any]] = []
        seen: set[str] = set()
        max_caps = int(
            self.skill_routing.get("selection_policy", {}).get("max_primary_capabilities_without_reason", 3)
        )
        selection_floor = 3

        for intent in intent_candidates:
            if intent.get("id") != "unknown_intent" and int(intent.get("score", 0)) < selection_floor:
                continue
            for capability_id in intent.get("capabilities", []):
                if capability_id in seen:
                    continue
                data = self.capabilities.get(capability_id, {})
                selected.append(
                    {
                        "id": capability_id,
                        "path": data.get("_path"),
                        "purpose": data.get("purpose", "").strip(),
                        "permission_tier": data.get("permission_tier", {}).get("default"),
                        "selected_by": intent.get("id"),
                    }
                )
                seen.add(capability_id)
                if len(selected) >= max_caps:
                    return selected

        if not selected:
            fallback = self.skill_routing.get("selection_policy", {}).get("fallback", {}).get(
                "unknown_intent", "research-synthesis"
            )
            data = self.capabilities.get(fallback, {})
            selected.append(
                {
                    "id": fallback,
                    "path": data.get("_path"),
                    "purpose": data.get("purpose", "").strip(),
                    "permission_tier": data.get("permission_tier", {}).get("default"),
                    "selected_by": "fallback",
                }
            )

        return selected

    def _classify_lifecycle(self, input_text: str) -> str:
        if self._is_seed_convergence_proposal(input_text):
            return "proposal"
        for lifecycle, keywords in LIFECYCLE_KEYWORDS:
            if _contains_any(input_text, keywords):
                return lifecycle
        return "observation"

    def _is_seed_convergence_proposal(self, input_text: str) -> bool:
        return bool(
            _contains_any(input_text, SEED_CONVERGENCE_CONTEXT_KEYWORDS)
            and _contains_any(input_text, SEED_CONVERGENCE_AMBIGUITY_KEYWORDS)
        )

    def _permission_decision(self, lifecycle: str, input_text: str) -> dict[str, Any]:
        lifecycle_policy = self.permission_policy.get("action_lifecycle", {}).get(lifecycle, {})
        default_decision = lifecycle_policy.get("default_decision", "confirm")
        confirmation_required = default_decision not in {"allow", "trace_required"}
        blocked = "block" in default_decision or default_decision == "blocked"

        matched_lifecycle_terms = []
        for candidate_lifecycle, keywords in LIFECYCLE_KEYWORDS:
            if candidate_lifecycle == lifecycle:
                matched_lifecycle_terms = _contains_any(input_text, keywords)
                break

        return {
            "lifecycle": lifecycle,
            "default_decision": default_decision,
            "confirmation_required": confirmation_required,
            "blocked": blocked,
            "trace": lifecycle_policy.get("trace", "required" if confirmation_required else "optional"),
            "reason": [
                f"matched_lifecycle:{lifecycle}",
                *[f"matched_term:{term}" for term in matched_lifecycle_terms],
            ],
            "safe_alternative": self._safe_alternative(lifecycle),
        }

    def _safe_alternative(self, lifecycle: str) -> str | None:
        alternatives = {
            "preparation": "후보, 입력값, 위험, 최종 확인 문구까지만 준비한다.",
            "cart_or_reservation": "결제 전 장바구니/예약 홀드는 추적 로그를 남기고 진행하되, 결제나 주문 확정은 별도 확인을 요청한다.",
            "payment": "가격/후보/위험을 정리하고 결제 전 확인을 요청한다.",
            "delete": "삭제 대신 대상 목록과 영향 범위를 먼저 보여준다.",
            "external_send": "전송 전 초안과 수신자/공개 범위를 먼저 보여준다.",
            "account_change": "설정 변경 전 현재 상태와 변경 결과를 먼저 설명한다.",
            "execution": "실행 전 dry-run 또는 변경 요약을 기록한다.",
        }
        return alternatives.get(lifecycle)

    def _provider_routes(self, selected_capabilities: list[dict[str, Any]]) -> dict[str, Any]:
        routes = self.provider_routing.get("capability_routes", {})
        provider_routes: dict[str, Any] = {}
        for capability in selected_capabilities:
            capability_id = capability["id"]
            route = routes.get(capability_id, {})
            provider_routes[capability_id] = {
                "primary": route.get("primary"),
                "reviewer": route.get("reviewer") or route.get("reviewers"),
                "implementer": route.get("implementer"),
                "fallback": route.get("fallback", []),
                "budget_tier": route.get("budget_tier"),
                "priority_reason": route.get("priority_reason"),
            }
        return provider_routes

    def _storage_routes(self, selected_capabilities: list[dict[str, Any]]) -> dict[str, Any]:
        writes: dict[str, str] = {}
        for step in self.kernel.get("flow", []):
            if step.get("step") == "record_and_route_outputs":
                writes.update(step.get("writes", {}))
                break

        capability_storage: dict[str, Any] = {}
        for capability in selected_capabilities:
            capability_id = capability["id"]
            capability_storage[capability_id] = self.capabilities.get(capability_id, {}).get("storage_policy", {})

        return {
            "kernel_writes": writes,
            "capability_storage": capability_storage,
        }

    def _skill_hub_resolution(
        self,
        input_text: str,
        intent_candidates: list[dict[str, Any]],
        selected_capabilities: list[dict[str, Any]],
        lifecycle: str,
        permission_decision: dict[str, Any],
        provider_routes: dict[str, Any],
        storage_routes: dict[str, Any],
    ) -> dict[str, Any]:
        if not self.skill_hub:
            return {
                "available": False,
                "read_only": True,
                "would_execute": False,
                "reason": "skill_hub_registry_missing",
            }

        candidates = self._rank_skill_hub_profiles(input_text, selected_capabilities, lifecycle)
        profile = candidates[0]["profile"] if candidates else {}
        profile_id = profile.get("id") or self.skill_hub.get("selection_policy", {}).get("fallback_profile")
        provider_policy_id = profile.get("provider_policy") or "common"
        provider_policy = self.skill_hub.get("provider_loading_policies", {}).get(provider_policy_id, {})
        selected_hooks = profile.get("hooks", [])
        hook_details = {
            hook_id: self.skill_hub.get("canonical_hook_lifecycle", {}).get(hook_id, {})
            for hook_id in selected_hooks
        }
        bundles = self._skill_hub_bundles_for_profile(str(profile_id))
        provider_runner_dry_run = self._provider_runner_dry_run(
            profile,
            provider_policy_id,
            provider_policy,
            selected_capabilities,
            lifecycle,
            permission_decision,
            provider_routes,
        )
        provider_injection_preview = self._provider_injection_preview(
            profile,
            provider_policy_id,
            provider_policy,
            selected_hooks,
            selected_capabilities,
            lifecycle,
            permission_decision,
            provider_routes,
            storage_routes,
        )

        return {
            "contract": "willind.skill_hub.runtime_selection",
            "version": self.skill_hub.get("version", "0.1.0"),
            "available": True,
            "read_only": True,
            "would_execute": False,
            "selected_profile": {
                "id": profile_id,
                "title": profile.get("title"),
                "notes": profile.get("notes"),
            },
            "matched_profiles": [
                {
                    "id": item["profile"].get("id"),
                    "title": item["profile"].get("title"),
                    "score": item["score"],
                    "matched": item["matched"],
                }
                for item in candidates[:3]
            ],
            "skill_bundle_candidates": bundles,
            "concepts": sorted(self.skill_hub.get("concepts", {}).keys()),
            "source_refs": profile.get("source_refs", []),
            "skill_sources": self._skill_hub_source_summary(profile.get("source_refs", [])),
            "capabilities": profile.get("capabilities", []),
            "provider_loading_policy": {
                "id": provider_policy_id,
                "primary_runner": provider_policy.get("primary_runner"),
                "may_read": provider_policy.get("may_read", []),
                "avoid_loading": provider_policy.get("avoid_loading", []),
                "description": provider_policy.get("description"),
            },
            "provider_runner_dry_run": provider_runner_dry_run,
            "provider_injection_preview": provider_injection_preview,
            "canonical_hooks": selected_hooks,
            "hook_details": hook_details,
            "permission": {
                "profile_lifecycle": profile.get("permission_lifecycle"),
                "runtime_lifecycle": lifecycle,
                "decision": permission_decision.get("default_decision"),
                "confirmation_required": permission_decision.get("confirmation_required"),
                "blocked": permission_decision.get("blocked"),
            },
            "storage": {
                "profile_storage_rule": profile.get("storage_rule"),
                "runtime_storage_routes": storage_routes,
            },
            "provider_routes": provider_routes,
            "intent_candidates": [item.get("id") for item in intent_candidates[:3]],
            "trace": {
                "registry_file": _rel(self.paths.skill_hub, self.paths.root),
                "safe_runtime_boundary": "skill_hub_selection_only_no_tool_execution",
            },
        }

    def _provider_runner_dry_run(
        self,
        profile: dict[str, Any],
        provider_policy_id: str,
        provider_policy: dict[str, Any],
        selected_capabilities: list[dict[str, Any]],
        lifecycle: str,
        permission_decision: dict[str, Any],
        provider_routes: dict[str, Any],
    ) -> dict[str, Any]:
        """Describe what would be routed without starting a provider or tool."""
        capability_ids = [str(item.get("id")) for item in selected_capabilities if item.get("id")]
        primary_runner = provider_policy.get("primary_runner") or "willind_ai_rules"
        blocked = bool(permission_decision.get("blocked"))
        confirmation_required = bool(permission_decision.get("confirmation_required"))
        return {
            "mode": "dry_run",
            "would_execute": False,
            "primary_runner": primary_runner,
            "provider_policy_id": provider_policy_id,
            "profile_id": profile.get("id"),
            "capabilities": capability_ids,
            "may_read": provider_policy.get("may_read", []),
            "avoid_loading": provider_policy.get("avoid_loading", []),
            "provider_routes": provider_routes,
            "permission_lifecycle": lifecycle,
            "permission_decision": permission_decision.get("default_decision"),
            "requires_approval": confirmation_required,
            "blocked": blocked,
            "handoff_boundary": "provider_selection_only_no_cli_or_api_call",
            "reason": "Skill Hub runner preview only. Provider execution must go through Action Runtime and Permission Gate.",
        }

    def _knowledge_context(
        self,
        intent_candidates: list[dict[str, Any]],
        selected_capabilities: list[dict[str, Any]],
    ) -> dict[str, Any]:
        # 읽기 전용: 작업 성격에 맞는 지식 pack을 "주입 후보"로만 표시한다.
        # 실제 요약 패킷 빌드/주입은 입구 다리(bridge) 책임. 여기서는 무엇을 붙일지 판정만.
        default = self.knowledge_packs.get("default", {}) or {}
        result: dict[str, Any] = {
            "decision": default.get("decision", "no_injection"),
            "reason": default.get("reason", "no knowledge pack registered"),
            "matched_packs": [],
            "boundary": "resolver_marks_candidates_only_no_packet_build",
        }
        packs = self.knowledge_packs.get("packs", {}) or {}
        if not packs:
            return result

        intent_score = {c.get("id"): int(c.get("score", 0)) for c in intent_candidates}
        capability_ids = {c.get("id") for c in selected_capabilities}

        for pack_id, pack in packs.items():
            triggers = pack.get("triggers", {}) or {}
            policy = pack.get("match_policy", {}) or {}
            min_score = int(policy.get("min_intent_score", 1))

            matched_intents = [
                i for i in triggers.get("intents", []) if intent_score.get(i, 0) >= min_score
            ]
            matched_caps = [c for c in triggers.get("capabilities", []) if c in capability_ids]

            if not (matched_intents or matched_caps):
                continue

            source_id = pack.get("source")
            source = (self.knowledge_sources.get("sources", {}) or {}).get(source_id, {})
            stale = self._knowledge_source_stale(source)
            result["matched_packs"].append(
                {
                    "pack": pack_id,
                    "source": source_id,
                    "inject": pack.get("inject", {}),
                    "matched_intents": matched_intents,
                    "matched_capabilities": matched_caps,
                    "stale": stale,
                    "source_paths": {
                        "index": source.get("index"),
                        "root": source.get("root"),
                    },
                }
            )

        if result["matched_packs"]:
            result["decision"] = "inject_candidate"
            result["reason"] = "task character matches registered knowledge pack(s)"
        return result

    @staticmethod
    def _knowledge_source_stale(source: dict[str, Any]) -> bool:
        freshness = source.get("freshness", {}) or {}
        last_entry = freshness.get("last_entry")
        stale_after = freshness.get("stale_after_days")
        if not last_entry or not stale_after:
            return False
        try:
            last = datetime.strptime(str(last_entry), "%Y-%m-%d").date()
        except ValueError:
            return False
        return (date.today() - last).days > int(stale_after)

    def _provider_injection_preview(
        self,
        profile: dict[str, Any],
        provider_policy_id: str,
        provider_policy: dict[str, Any],
        selected_hooks: list[str],
        selected_capabilities: list[dict[str, Any]],
        lifecycle: str,
        permission_decision: dict[str, Any],
        provider_routes: dict[str, Any],
        storage_routes: dict[str, Any],
    ) -> dict[str, Any]:
        """Build provider-specific instruction capsules without starting providers."""
        capability_ids = [str(item.get("id")) for item in selected_capabilities if item.get("id")]
        primary_runner = str(provider_policy.get("primary_runner") or "willind_ai_rules")
        runner_targets = self._provider_injection_targets(primary_runner, provider_routes)
        hooks = selected_hooks or ["intent_detect"]
        blocked = bool(permission_decision.get("blocked"))
        requires_approval = bool(permission_decision.get("confirmation_required"))
        boundary = (
            "read_profile_and_prepare_only"
            if requires_approval or blocked
            else "read_profile_prepare_then_action_runtime"
        )
        profile_id = str(profile.get("id") or "")
        response_contract = self._response_contract(profile_id, lifecycle, capability_ids)
        hook_capsules = [
            {
                "hook": hook_id,
                "instruction": self._hook_instruction(hook_id, lifecycle, profile_id),
            }
            for hook_id in hooks
        ]
        provider_capsules = [
            {
                "runner": target,
                "role": self._runner_role(target),
                "may_read": provider_policy.get("may_read", []),
                "avoid_loading": provider_policy.get("avoid_loading", []),
                "baseline_rule_ids": self._provider_baseline_rule_ids(target),
                "capabilities": capability_ids,
                "handoff": self._runner_handoff_line(target, profile.get("id"), lifecycle, boundary),
                "would_execute": False,
            }
            for target in runner_targets
        ]
        return {
            "contract": "willind.skill_hub.provider_injection_preview",
            "version": "0.1.0",
            "mode": "metadata_only",
            "profile_id": profile.get("id"),
            "profile_title": profile.get("title"),
            "provider_policy_id": provider_policy_id,
            "primary_runner": primary_runner,
            "runner_targets": runner_targets,
            "capabilities": capability_ids,
            "hooks": hooks,
            "hook_capsules": hook_capsules,
            "response_contract": response_contract,
            "provider_capsules": provider_capsules,
            "permission": {
                "lifecycle": lifecycle,
                "decision": permission_decision.get("default_decision"),
                "requires_approval": requires_approval,
                "blocked": blocked,
            },
            "storage": {
                "profile_storage_rule": profile.get("storage_rule"),
                "storage_routes": storage_routes,
            },
            "baseline": {
                "registry_file": _rel(self.paths.baseline_rules, self.paths.root)
                if self.paths.baseline_rules.exists()
                else None,
                "rule_ids": self._provider_baseline_rule_ids(primary_runner),
                "always_on": bool(self.baseline_rules.get("always_on", False)),
            },
            "safety_boundary": boundary,
            "would_execute": False,
            "reason": "Provider-specific skill instructions are selected, but no CLI/API/browser action is started here.",
        }

    def _response_contract(self, profile_id: str, lifecycle: str, capability_ids: list[str]) -> dict[str, Any]:
        if profile_id != "idea_to_seed_convergence":
            return {}
        return {
            "id": "idea_to_seed_interview_contract",
            "mode": "mandatory_when_profile_selected",
            "lifecycle": lifecycle,
            "source_methods": [
                "superpowers.brainstorming",
            ],
            "capabilities": capability_ids,
            "must_ask_8_to_12_interview_questions": True,
            "required": [
                "Use public research or market examples only to seed hypotheses; do not finalize one product before user preferences are collected.",
                "Open with a short diagnosis or 2-4 candidate directions, then ask 8-12 numbered active interview questions.",
                "Questions must narrow taste, skills, constraints, production format, buyer, channel, price comfort, proof, and fun/energy.",
                "After answers, converge to 1-3 seed options with offer, buyer, pack/service contents, sales channel, and first validation experiment.",
            ],
            "conditional": [
                "If the user gives an existing asset, listing, service page, or link, diagnose concrete conversion/positioning issues first, then ask 3-7 targeted follow-up questions.",
                "If the user explicitly asks for no questions or a direct draft, provide the draft and label the missing assumptions.",
            ],
            "forbidden": [
                "Do not end with only one generic question such as skills, interests, or available time.",
                "Do not answer as a generic recommendation list without an interview loop.",
                "Do not treat imported Superpowers or imported source bodies as globally active; use only this selected composed behavior.",
            ],
            "output_shape": [
                "short market signal or page diagnosis",
                "2-4 candidate directions or observed issues",
                "8-12 grouped interview questions for broad ambiguous requests",
                "what the next user answer will produce",
            ],
            "fallback_on_miss": "If the response drifts into generic advice, restart with the interview question set before recommending a final seed.",
        }

    def _provider_baseline_rule_ids(self, runner: str) -> list[str]:
        if not self.baseline_rules:
            return []
        rules = self.baseline_rules.get("rules", [])
        runner_key = runner.lower()
        result: list[str] = []
        for rule in rules:
            if not isinstance(rule, dict) or not rule.get("id"):
                continue
            applies_to = [str(item).lower() for item in rule.get("applies_to", [])]
            if "all" in applies_to:
                result.append(str(rule["id"]))
                continue
            if "codex" in runner_key and "codex" in applies_to:
                result.append(str(rule["id"]))
            elif "claude" in runner_key and "claude" in applies_to:
                result.append(str(rule["id"]))
            elif "gemini" in runner_key and "gemini" in applies_to:
                result.append(str(rule["id"]))
            elif "local" in runner_key and "local_model" in applies_to:
                result.append(str(rule["id"]))
            elif "api" in runner_key and "api_model" in applies_to:
                result.append(str(rule["id"]))
            elif "willind_ai" in runner_key and "willind_ai_rules" in applies_to:
                result.append(str(rule["id"]))
        return result

    def _provider_injection_targets(self, primary_runner: str, provider_routes: dict[str, Any]) -> list[str]:
        targets: list[str] = []
        if primary_runner:
            targets.append(primary_runner)
        for route in provider_routes.values():
            if not isinstance(route, dict):
                continue
            for key in ("primary", "implementer"):
                value = route.get(key)
                if isinstance(value, str) and value:
                    targets.append(value)
            reviewer = route.get("reviewer")
            if isinstance(reviewer, str) and reviewer:
                targets.append(reviewer)
            elif isinstance(reviewer, list):
                targets.extend(str(item) for item in reviewer if str(item).strip())
            fallback = route.get("fallback")
            if isinstance(fallback, list):
                targets.extend(str(item) for item in fallback if str(item).strip())
        unique: list[str] = []
        for target in targets:
            if target not in unique:
                unique.append(target)
        return unique[:5] or ["willind_ai_rules"]

    def _runner_role(self, target: str) -> str:
        lowered = target.lower()
        if "codex" in lowered:
            return "implementation_and_tests"
        if "claude" in lowered:
            return "reasoning_review_and_structure"
        if "gemini" in lowered or "browser" in lowered:
            return "research_and_source_check"
        if "local" in lowered:
            return "low_cost_classification"
        if "api" in lowered:
            return "paid_provider_fallback"
        return "willind_runtime_selection"

    def _hook_instruction(self, hook_id: str, lifecycle: str, profile_id: str | None = None) -> str:
        if profile_id == "idea_to_seed_convergence":
            instructions = {
                "intent_detect": "막연한 온라인 판매, AI 상품, 팩, 스킬샵, 디지털 상품 발화는 일반 조사보다 product-defining ambiguity로 본다.",
                "planning": "공개 근거로 시장 후보를 깔되 바로 결론내리지 말고 8-12개의 적극적 인터뷰 질문으로 취향, 제작 방식, 유통, 가격 감각을 좁힌다.",
                "pre_execution": "파일 생성, paid provider, 외부 게시, 판매 페이지 공개 전에는 seed 기획과 권한 경계를 먼저 확인한다.",
                "execution_review": "카테고리 나열에서 멈추지 말고 고객, offer, 팩 구성, 판매 채널, 첫 검증 실험이 들어간 seed로 수렴했는지 본다.",
                "post_execution": "조사 근거, 사용자 답변, 버린 후보, 남은 질문, 다음 실험을 짧게 분리한다.",
                "memory_update": "검증된 선호나 반복 가능한 상품화 패턴만 기록 후보로 남긴다.",
                "error_recovery": "조사만 반복되거나 질문 없이 추천만 반복되면 인터뷰 질문 세트로 되돌린다.",
            }
            if hook_id in instructions:
                return instructions[hook_id]
        instructions = {
            "intent_detect": "명령 의도와 위험 생명주기를 먼저 분류한다.",
            "planning": "목표, 후보, 빠른 길과 구조 수정 필요 여부를 나눈다.",
            "pre_execution": "실행 전 변경 범위, 권한, 되돌림 가능성을 확인한다.",
            "execution_review": "실행 결과와 테스트 근거를 검토한다.",
            "post_execution": "결과, 실패, 다음 행동을 짧게 정리한다.",
            "memory_update": "반복될 가치가 있는 규칙만 기록 후보로 남긴다.",
            "error_recovery": "실패 원인, 재시도 조건, 안전한 대안을 분리한다.",
        }
        return instructions.get(hook_id, f"{hook_id} 단계에서 {lifecycle} 요청을 검토한다.")

    def _runner_handoff_line(self, target: str, profile_id: str | None, lifecycle: str, boundary: str) -> str:
        return (
            f"{target} receives profile={profile_id or 'unknown'}, lifecycle={lifecycle}, "
            f"boundary={boundary}. Execute only after Action Runtime permission state is resolved."
        )

    def _rank_skill_hub_profiles(
        self,
        input_text: str,
        selected_capabilities: list[dict[str, Any]],
        lifecycle: str,
    ) -> list[dict[str, Any]]:
        normalized = _normalize(input_text)
        capability_ids = {str(item.get("id")) for item in selected_capabilities if item.get("id")}
        input_tokens = _tokens(input_text)
        ranked: list[dict[str, Any]] = []

        for profile in self.skill_hub.get("skill_profiles", []):
            score = 0
            matched: list[str] = []
            profile_capabilities = set(profile.get("capabilities", []))
            overlap = sorted(profile_capabilities & capability_ids)
            if overlap:
                score += len(overlap) * 5
                matched.extend(f"capability:{item}" for item in overlap)

            profile_lifecycle = profile.get("permission_lifecycle")
            if profile_lifecycle == lifecycle:
                score += 4
                matched.append(f"lifecycle:{lifecycle}")

            for keyword in profile.get("trigger_keywords", []):
                keyword_text = _normalize(str(keyword))
                if keyword_text and _keyword_matches(input_text, str(keyword)):
                    score += 3
                    matched.append(f"keyword:{keyword}")

            for example in profile.get("trigger_examples", []):
                example_norm = _normalize(str(example))
                if example_norm and example_norm in normalized:
                    score += 6
                    matched.append(f"example:{example}")
                else:
                    for token in _tokens(str(example)):
                        if token in input_tokens:
                            score += 1
                            matched.append(f"example_token:{token}")

            if score > 0:
                ranked.append(
                    {
                        "score": score,
                        "profile": profile,
                        "matched": sorted(set(matched)),
                    }
                )

        if not ranked:
            fallback_id = self.skill_hub.get("selection_policy", {}).get("fallback_profile")
            fallback = next(
                (
                    profile
                    for profile in self.skill_hub.get("skill_profiles", [])
                    if profile.get("id") == fallback_id
                ),
                {},
            )
            ranked.append(
                {
                    "score": 1,
                    "profile": fallback,
                    "matched": ["fallback:skill_hub"],
                }
            )

        return sorted(ranked, key=lambda item: (-int(item["score"]), str(item["profile"].get("id", ""))))

    def _skill_hub_bundles_for_profile(self, profile_id: str) -> list[dict[str, Any]]:
        bundles: list[dict[str, Any]] = []
        for bundle_id, bundle in self.skill_hub.get("skill_bundles", {}).items():
            profiles = bundle.get("profiles", [])
            if profile_id in profiles:
                bundles.append(
                    {
                        "id": bundle_id,
                        "title": bundle.get("title"),
                        "sequence": bundle.get("sequence", []),
                        "permission_lifecycle": bundle.get("permission_lifecycle"),
                        "storage_rule": bundle.get("storage_rule"),
                    }
                )
        return bundles

    def _skill_hub_source_summary(self, source_refs: list[str]) -> list[dict[str, Any]]:
        sources = self.skill_hub.get("skill_sources", {})
        result: list[dict[str, Any]] = []
        for inventory_id in source_refs:
            for source_id, source in sources.items():
                if source.get("source_inventory_id") != inventory_id:
                    continue
                result.append(
                    {
                        "id": source_id,
                        "source_inventory_id": inventory_id,
                        "class": source.get("class"),
                        "adapter_candidate": source.get("adapter_candidate"),
                        "composed_candidates": source.get("composed_candidates", []),
                        "useful_pieces": source.get("useful_pieces", []),
                        "do_not": source.get("do_not"),
                    }
                )
        return result


def resolve_to_json(input_text: str, *, input_channel: str = "text") -> str:
    result = SkillKernelResolver().resolve(input_text, input_channel=input_channel)
    return json.dumps(result, ensure_ascii=False, indent=2)
