from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from core.kernel.skill_kernel_resolver import SkillKernelResolver


ROOT = next((p for p in Path(__file__).resolve().parents if (p / "registry" / "_index.yaml").exists()), Path(__file__).resolve().parent)
DEFAULT_OUTPUT_ROOT = ROOT / "runtime/provider-bootstrap"


PROVIDER_ALIASES = {
    "codex": "codex_cli",
    "codex_cli": "codex_cli",
    "claude": "claude_cli",
    "claude_cli": "claude_cli",
    "gemini": "gemini_api_or_browser",
    "gemini_api": "gemini_api_or_browser",
    "gemini_api_or_browser": "gemini_api_or_browser",
    "local": "local_llm",
    "local_llm": "local_llm",
    "openai": "openai_api",
    "openai_api": "openai_api",
    "browser": "browser_session",
    "browser_session": "browser_session",
    "opencode": "opencode_cli",
    "opencode_cli": "opencode_cli",
    "openhands": "openhands_workspace",
    "openhands_workspace": "openhands_workspace",
    "antigravity": "common",
    "google_antigravity": "common",
    "opensource": "common",
    "open_source": "common",
    "generic": "common",
    "common": "common",
}


def _force_utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


def _slug(value: str, fallback: str = "bootstrap") -> str:
    text = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip().lower()).strip("-._")
    return text[:80] or fallback


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _compact(items: list[Any], *, limit: int = 10) -> list[str]:
    return [str(item) for item in items[:limit] if str(item).strip()]


def canonical_provider(provider: str | None) -> str:
    if not provider:
        return "auto"
    key = provider.strip().lower().replace("-", "_")
    return PROVIDER_ALIASES.get(key, key)


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return {}
    return data if isinstance(data, dict) else {}


def _merge_provider_bootstrap(resolved_bootstrap: dict[str, Any]) -> dict[str, Any]:
    """Resolver returns the task-relevant provider subset. The bootstrap builder
    also needs the full registry so explicit providers such as common, browser,
    Gemini, OpenCode, or OpenHands can still receive their baseline packet."""
    registry_bootstrap = _load_yaml(ROOT / "registry/providers/provider-bootstrap.yaml")
    merged = dict(registry_bootstrap)
    merged.update(resolved_bootstrap)

    registry_profiles = _as_dict(registry_bootstrap.get("profiles"))
    resolved_profiles = _as_dict(resolved_bootstrap.get("profiles"))
    profiles = dict(registry_profiles)
    profiles.update(resolved_profiles)
    merged["profiles"] = profiles

    if not merged.get("load_order"):
        merged["load_order"] = registry_bootstrap.get("load_order") or []
    return merged


def _profile_for_provider(provider_bootstrap: dict[str, Any], provider_id: str) -> dict[str, Any]:
    profiles = _as_dict(provider_bootstrap.get("profiles"))
    if provider_id in profiles:
        return _as_dict(profiles[provider_id])
    return _as_dict(profiles.get("common"))


def _capsule_for_provider(injection: dict[str, Any], provider_id: str) -> dict[str, Any]:
    capsules = _as_list(injection.get("provider_capsules"))
    for capsule in capsules:
        item = _as_dict(capsule)
        if item.get("runner") == provider_id:
            return item
    if capsules:
        return _as_dict(capsules[0])
    return {}


def _selected_provider_targets(
    provider: str,
    skill_hub: dict[str, Any],
    provider_bootstrap: dict[str, Any],
) -> list[str]:
    injection = _as_dict(skill_hub.get("provider_injection_preview"))
    targets = [str(item) for item in _as_list(injection.get("runner_targets")) if str(item).strip()]
    bootstrap_targets = [
        str(item)
        for item in _as_list(provider_bootstrap.get("runner_targets"))
        if str(item).strip()
    ]
    if provider != "auto":
        return [provider]
    selected = targets or bootstrap_targets or ["common"]
    result: list[str] = []
    for target in selected:
        if target not in result:
            result.append(target)
    return result


def _build_markdown(packet: dict[str, Any]) -> str:
    selected = _as_dict(packet.get("selected_profile"))
    provider = _as_dict(packet.get("provider"))
    permission = _as_dict(packet.get("permission"))
    storage = _as_dict(packet.get("storage"))
    baseline = _as_dict(packet.get("baseline"))
    skill = _as_dict(packet.get("skill_loading"))
    hooks = _as_list(packet.get("hooks"))
    response_contract = _as_dict(packet.get("response_contract"))
    trace = _as_dict(packet.get("trace"))

    lines: list[str] = [
        "# Willind Provider Bootstrap",
        "",
        "이 파일은 provider가 시작할 때 읽는 짧은 작업별 지침이다.",
        "외부 스킬 원본 전체를 읽는 파일이 아니며, 실제 실행 권한도 아니다.",
        "",
        "## 작업",
        "",
        f"- 입력: {packet.get('input_text', '')}",
        f"- 입력 채널: `{packet.get('input_channel', 'text')}`",
        f"- 선택 프로필: `{selected.get('id', 'unknown')}` / {selected.get('title', '')}",
        f"- provider: `{provider.get('id', 'common')}`",
        f"- provider 역할: {provider.get('role', '')}",
        "",
        "## 항상 적용",
        "",
    ]
    for rule in _compact(_as_list(baseline.get("compact_prompt")), limit=8):
        lines.append(f"- {rule}")
    if not _as_list(baseline.get("compact_prompt")):
        lines.append("- Registry를 먼저 보고, 사실/추정/미확인을 분리한다.")
        lines.append("- 권한 게이트 전에는 결제, 삭제, 외부 전송, 계정 변경을 실행하지 않는다.")
    lines.extend(
        [
            "",
            "## 이번 작업에서 읽을 것",
            "",
            f"- provider auto-read: {', '.join(_compact(_as_list(provider.get('auto_read')), limit=8)) or '없음'}",
            f"- 선택 능력: {', '.join(_compact(_as_list(skill.get('capabilities')), limit=10)) or '없음'}",
            f"- 읽어도 되는 스킬 조각: {', '.join(_compact(_as_list(skill.get('may_read')), limit=10)) or '없음'}",
            f"- 읽지 말 것: {', '.join(_compact(_as_list(skill.get('avoid_loading')), limit=10)) or '없음'}",
            "",
            "## 훅",
            "",
        ]
    )
    if hooks:
        for hook in hooks[:8]:
            hook_item = _as_dict(hook)
            lines.append(f"- `{hook_item.get('hook', 'unknown')}`: {hook_item.get('instruction', '')}")
    else:
        lines.append("- 기본 훅 없음. 공통 운영 규칙만 적용한다.")
    if response_contract:
        lines.extend(
            [
                "",
                "## 응답 계약",
                "",
                f"- 계약: `{response_contract.get('id', 'unknown')}`",
                f"- 모드: `{response_contract.get('mode', 'unknown')}`",
                f"- 방법 렌즈: {', '.join(_compact(_as_list(response_contract.get('source_methods')), limit=4)) or '없음'}",
            ]
        )
        if response_contract.get("must_ask_8_to_12_interview_questions"):
            lines.append("- 필수: 넓고 애매한 상품화 요청에는 8-12개의 번호 매긴 적극적 인터뷰 질문을 포함한다.")
        for item in _compact(_as_list(response_contract.get("required")), limit=6):
            lines.append(f"- 해야 함: {item}")
        for item in _compact(_as_list(response_contract.get("conditional")), limit=4):
            lines.append(f"- 조건부: {item}")
        for item in _compact(_as_list(response_contract.get("forbidden")), limit=4):
            lines.append(f"- 금지: {item}")
        shape = _compact(_as_list(response_contract.get("output_shape")), limit=6)
        if shape:
            lines.append(f"- 출력 형태: {' -> '.join(shape)}")
        fallback = str(response_contract.get("fallback_on_miss", "")).strip()
        if fallback:
            lines.append(f"- 이탈 시 복구: {fallback}")
    lines.extend(
        [
            "",
            "## 권한과 실행 경계",
            "",
            f"- 생명주기: `{permission.get('lifecycle', 'unknown')}`",
            f"- 결정: `{permission.get('decision', 'unknown')}`",
            f"- 확인 필요: `{permission.get('requires_approval', False)}`",
            f"- 차단: `{permission.get('blocked', False)}`",
            "- 이 파일은 실행 권한이 아니다. 실제 실행은 Action Runtime과 Permission Gate 상태를 따른다.",
            "",
            "## 저장 위치",
            "",
            f"- 저장 규칙: `{storage.get('profile_storage_rule', 'default')}`",
            f"- runtime route: `{storage.get('runtime_storage_routes', {})}`",
            "",
            "## 추적",
            "",
            f"- resolver: `{trace.get('resolver', 'core/kernel/skill_kernel_resolver.py')}`",
            f"- registry: `{trace.get('skill_hub_registry', 'registry/skills/skill-hub.yaml')}`",
            f"- would_execute: `{packet.get('would_execute', False)}`",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


@dataclass(frozen=True)
class BuiltProviderBootstrap:
    provider_id: str
    packet: dict[str, Any]
    markdown: str


def build_provider_bootstraps(
    input_text: str,
    *,
    input_channel: str = "text",
    provider: str | None = "auto",
) -> list[BuiltProviderBootstrap]:
    resolver = SkillKernelResolver()
    resolved = resolver.resolve(input_text, input_channel=input_channel)
    skill_hub = _as_dict(resolved.get("skill_hub"))
    provider_bootstrap = _merge_provider_bootstrap(_as_dict(resolved.get("provider_bootstrap")))
    baseline_rules = _as_dict(resolved.get("baseline_rules"))
    injection = _as_dict(skill_hub.get("provider_injection_preview"))
    selected = _as_dict(skill_hub.get("selected_profile"))
    provider_policy = _as_dict(skill_hub.get("provider_loading_policy"))
    permission = _as_dict(injection.get("permission")) or _as_dict(skill_hub.get("permission"))
    storage = _as_dict(injection.get("storage")) or _as_dict(skill_hub.get("storage"))

    provider_id = canonical_provider(provider)
    targets = _selected_provider_targets(provider_id, skill_hub, provider_bootstrap)
    compact_prompt = []
    provider_injection = _as_dict(baseline_rules.get("provider_injection"))
    if provider_injection:
        compact_prompt = _as_list(provider_injection.get("compact_prompt"))

    built: list[BuiltProviderBootstrap] = []
    for target in targets:
        target_id = canonical_provider(target)
        provider_profile = _profile_for_provider(provider_bootstrap, target_id)
        capsule = _capsule_for_provider(injection, target_id)
        packet = {
            "contract": "willind.provider_bootstrap_packet",
            "version": "0.1.0",
            "created_at": _utc_stamp(),
            "input_text": input_text,
            "input_channel": input_channel,
            "read_only": True,
            "would_execute": False,
            "selected_profile": selected,
            "provider": {
                "id": target_id,
                "requested": provider,
                "profile_id": provider_profile.get("id", target_id),
                "kind": provider_profile.get("kind"),
                "role": provider_profile.get("default_role") or capsule.get("role"),
                "auto_read": _as_list(provider_profile.get("auto_read")),
                "situational_skill_loading": provider_profile.get("situational_skill_loading"),
            },
            "baseline": {
                "always_on": baseline_rules.get("always_on"),
                "rule_ids": baseline_rules.get("must_rule_ids") or baseline_rules.get("rule_ids") or [],
                "compact_prompt": compact_prompt,
                "avoid_loading": _as_list(provider_profile.get("avoid_loading")),
            },
            "skill_loading": {
                "policy_id": provider_policy.get("id"),
                "primary_runner": provider_policy.get("primary_runner"),
                "may_read": _as_list(capsule.get("may_read")) or _as_list(provider_policy.get("may_read")),
                "avoid_loading": _as_list(capsule.get("avoid_loading"))
                or _as_list(provider_policy.get("avoid_loading"))
                or _as_list(provider_profile.get("avoid_loading")),
                "capabilities": _as_list(capsule.get("capabilities")) or _as_list(skill_hub.get("capabilities")),
            },
            "hooks": _as_list(injection.get("hook_capsules")),
            "response_contract": _as_dict(injection.get("response_contract")),
            "permission": {
                "lifecycle": permission.get("lifecycle") or permission.get("runtime_lifecycle"),
                "decision": permission.get("decision"),
                "requires_approval": bool(permission.get("requires_approval") or permission.get("confirmation_required")),
                "blocked": bool(permission.get("blocked")),
            },
            "storage": {
                "profile_storage_rule": _as_dict(skill_hub.get("storage")).get("profile_storage_rule"),
                "runtime_storage_routes": _as_dict(skill_hub.get("storage")).get("runtime_storage_routes")
                or storage.get("storage_routes"),
            },
            "trace": {
                "resolver": "core/kernel/skill_kernel_resolver.py",
                "provider_bootstrap_registry": "registry/providers/provider-bootstrap.yaml",
                "skill_hub_registry": "registry/skills/skill-hub.yaml",
                "permission_registry": "registry/permissions/permission-gate-policy.yaml",
                "safe_boundary": "bootstrap_packet_only_no_execution",
            },
        }
        built.append(BuiltProviderBootstrap(target_id, packet, _build_markdown(packet)))
    return built


def write_provider_bootstraps(
    input_text: str,
    *,
    input_channel: str = "text",
    provider: str | None = "auto",
    output_root: Path = DEFAULT_OUTPUT_ROOT,
) -> dict[str, Any]:
    built = build_provider_bootstraps(input_text, input_channel=input_channel, provider=provider)
    digest = hashlib.sha1(f"{input_channel}:{provider}:{input_text}".encode("utf-8")).hexdigest()[:10]
    run_dir = output_root / f"{_utc_stamp()}-{_slug(input_text)}-{digest}"
    run_dir.mkdir(parents=True, exist_ok=True)

    files: list[dict[str, str]] = []
    for item in built:
        base = f"{_slug(item.provider_id)}"
        json_path = run_dir / f"{base}.json"
        md_path = run_dir / f"{base}.md"
        json_path.write_text(json.dumps(item.packet, ensure_ascii=False, indent=2), encoding="utf-8")
        md_path.write_text(item.markdown, encoding="utf-8")
        files.append(
            {
                "provider": item.provider_id,
                "json": str(json_path),
                "markdown": str(md_path),
            }
        )

    index = {
        "ok": True,
        "contract": "willind.provider_bootstrap_run",
        "created_at": _utc_stamp(),
        "input_text": input_text,
        "input_channel": input_channel,
        "provider": provider or "auto",
        "output_dir": str(run_dir),
        "files": files,
    }
    (run_dir / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    return index


def main(argv: list[str] | None = None) -> int:
    _force_utf8_stdio()
    parser = argparse.ArgumentParser(description="Build Willind provider bootstrap packets for a task.")
    parser.add_argument("text", help="User task or utterance.")
    parser.add_argument("--channel", default="text", help="Input channel. Default: text.")
    parser.add_argument("--provider", default="auto", help="Provider id or auto. Examples: codex, claude, gemini.")
    parser.add_argument("--out", default=str(DEFAULT_OUTPUT_ROOT), help="Output root directory.")
    parser.add_argument("--json-only", action="store_true", help="Print JSON report only.")
    args = parser.parse_args(argv)

    report = write_provider_bootstraps(
        args.text,
        input_channel=args.channel,
        provider=args.provider,
        output_root=Path(args.out),
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not args.json_only:
        for item in report.get("files", []):
            print(f"{item['provider']}: {item['markdown']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
