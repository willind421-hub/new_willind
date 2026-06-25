from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = next((p for p in Path(__file__).resolve().parents if (p / "registry" / "_index.yaml").exists()), Path(__file__).resolve().parent)
SUBJECT_PATH = ROOT / "scripts" / "operations" / "providers" / "ensure_required_provider_runtimes.py"


def load_subject():
    spec = importlib.util.spec_from_file_location("required_provider_runtime_launcher_subject", SUBJECT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def fake_spec(module, service_id: str = "service_supervisor"):
    return module.RuntimeSpec(
        id=service_id,
        label="테스트 런타임",
        cwd=ROOT,
        argv=("python", "-m", "fake.service", "serve"),
        health_url=f"http://127.0.0.1:19999/{service_id}",
        port=19999,
    )


def test_dry_run_reports_would_start_without_calling_starter() -> None:
    module = load_subject()
    starter_called = False

    def starter(_spec):
        nonlocal starter_called
        starter_called = True
        raise AssertionError("dry-run must not start a process")

    payload = module.run(
        dry_run=True,
        specs=[fake_spec(module)],
        registry_statuses={"service_supervisor": "active"},
        health_probe=lambda _url: {"status": "unavailable", "reason": "fixture"},
        starter=starter,
    )

    assert payload["ok"] is True
    assert payload["mode"] == "dry_run"
    assert payload["services"][0]["action"] == "would_start"
    assert starter_called is False


def test_start_success_records_owned_pid_and_available_health() -> None:
    module = load_subject()
    health_states = iter(
        [
            {"status": "unavailable", "reason": "before"},
            {"status": "available", "reason": "after"},
        ]
    )

    payload = module.run(
        start=True,
        specs=[fake_spec(module)],
        registry_statuses={"service_supervisor": "active"},
        health_probe=lambda _url: next(health_states),
        starter=lambda _spec: module.OwnedProcess(pid=4242),
        sleeper=lambda _seconds: None,
    )

    service = payload["services"][0]
    assert payload["ok"] is True
    assert payload["counts"]["started"] == 1
    assert service["ownedPid"] == 4242
    assert service["action"] == "started_available"
    assert service["health"]["status"] == "available"


def test_start_failure_terminates_only_owned_process() -> None:
    module = load_subject()
    terminated: list[int] = []

    class FakeProcess(module.OwnedProcess):
        def terminate(self) -> None:
            terminated.append(self.pid)

    payload = module.run(
        start=True,
        timeout_seconds=0.01,
        specs=[fake_spec(module, "tool_slot_runtime")],
        registry_statuses={"tool_slot_runtime": "active"},
        health_probe=lambda _url: {"status": "unavailable", "reason": "fixture"},
        starter=lambda _spec: FakeProcess(pid=5151),
        sleeper=lambda _seconds: None,
    )

    service = payload["services"][0]
    assert payload["ok"] is False
    assert payload["counts"]["failedStart"] == 1
    assert service["action"] == "start_failed_cleaned"
    assert terminated == [5151]


def test_optional_or_unknown_registry_status_is_not_started() -> None:
    module = load_subject()
    payload = module.run(
        start=True,
        specs=[fake_spec(module, "opencode_cli")],
        registry_statuses={"opencode_cli": "optional"},
        health_probe=lambda _url: {"status": "unavailable", "reason": "fixture"},
        starter=lambda _spec: (_ for _ in ()).throw(AssertionError("optional runtime must not start")),
    )

    assert payload["ok"] is True
    assert payload["services"][0]["requiredForLive"] is False
    assert payload["services"][0]["action"] == "optional_or_not_required"
