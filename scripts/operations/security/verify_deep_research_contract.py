from __future__ import annotations

import asyncio
import importlib.util
import json
import shutil
import sys
from pathlib import Path
from typing import Any

import yaml


ROOT = next((p for p in Path(__file__).resolve().parents if (p / "registry" / "_index.yaml").exists()), Path(__file__).resolve().parent)
BACKEND = ROOT / "<your-backend>"
SERVICE_REGISTRY = ROOT / "registry/services/deep-research.yaml"
INDEX = ROOT / "registry/_index.yaml"
SERVICE_SOURCE = BACKEND / "services/deep_research.py"
ROUTER_SOURCE = BACKEND / "routers/deep_research.py"
FIXTURE_ROOT = ROOT / "runtime" / "contract-fixtures" / "deep-research-contract"


def load_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return data if isinstance(data, dict) else {}


def load_module() -> Any:
    sys.path.insert(0, str(BACKEND))
    spec = importlib.util.spec_from_file_location("willind_deep_research_contract_subject", SERVICE_SOURCE)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {SERVICE_SOURCE}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


async def fake_executor(query: str, limit: int) -> list[dict[str, Any]]:
    return [
        {"id": "fixture-1", "title": f"{query} 근거 1", "source": "roles"},
        {"id": "fixture-2", "title": f"{query} 근거 2", "source": "roles"},
    ][:limit]


async def failing_parallel_search(query: str, sources: list[str], limit: int, executors=None) -> dict[str, Any]:
    raise RuntimeError("fixture source offline")


def check_registry(registry: dict[str, Any], failures: list[str]) -> None:
    if registry.get("contract") != "willind.deep_research_service":
        failures.append("registry contract must be willind.deep_research_service")

    boundaries = registry.get("boundaries")
    if not isinstance(boundaries, dict):
        failures.append("boundaries must be a mapping")
        return
    expected = {
        "read_only_sources": True,
        "writes_runtime_job_files": True,
        "writes_memory_directly": False,
        "memory_store_status": "candidate_only",
        "supports_cancel": True,
        "supports_archive_restore": True,
        "supports_event_stream": True,
        "supports_retry": True,
        "supports_stale_running_guard": True,
        "external_send": "blocked",
        "mutation": "blocked",
        "payment": "blocked",
        "account_change": "blocked",
    }
    for key, value in expected.items():
        if boundaries.get(key) != value:
            failures.append(f"boundaries.{key} must be {value!r}")

    entrypoints = registry.get("entrypoints") if isinstance(registry.get("entrypoints"), dict) else {}
    api_paths = entrypoints.get("api_paths") if isinstance(entrypoints.get("api_paths"), list) else []
    for path in (
        "/api/deep-research/jobs",
        "/api/deep-research/jobs/{job_id}",
        "/api/deep-research/jobs/{job_id}/run",
        "/api/deep-research/jobs/{job_id}/start",
        "/api/deep-research/jobs/{job_id}/retry",
        "/api/deep-research/jobs/{job_id}/cancel",
        "/api/deep-research/jobs/{job_id}/archive",
        "/api/deep-research/jobs/{job_id}/restore",
        "/api/deep-research/jobs/{job_id}/events",
        "/api/deep-research/stale-running/mark-blocked",
        "/api/deep-research/results",
    ):
        if path not in api_paths:
            failures.append(f"deep-research registry missing API path: {path}")


def check_source(failures: list[str]) -> None:
    source = SERVICE_SOURCE.read_text(encoding="utf-8")
    for required in ("candidate_only", "wouldWriteExternal", "externalSend", "mutation", "memoryCandidates", "storeRequires"):
        if required not in source:
            failures.append(f"deep_research.py missing safety marker: {required}")
    for risky in ("sendMessage", "requests.post", "httpx.post", "subprocess", "os.environ"):
        if risky in source:
            failures.append(f"deep_research.py must not perform external send/launch/secret access: {risky}")

    router_source = ROUTER_SOURCE.read_text(encoding="utf-8")
    for route_fragment in (
        '@router.post("/jobs")',
        '@router.post("/jobs/{job_id}/start"',
        '@router.post("/jobs/{job_id}/retry"',
        '@router.post("/jobs/{job_id}/cancel")',
        '@router.get("/jobs/{job_id}/events")',
    ):
        if route_fragment not in router_source:
            failures.append(f"deep-research router missing route: {route_fragment}")


def check_runtime_behavior(failures: list[str]) -> None:
    module = load_module()
    base = _fresh_fixture_root()
    try:
        module.RUNTIME_DIR = base / "deep-research"
        job = module.create_deep_research_job("Sample 계약 검증", sources=["roles"], limit=2)
        if job.get("wouldWriteExternal") is not False:
            failures.append("created research job must set wouldWriteExternal=false")
        if job.get("permission", {}).get("memoryStore") != "candidate_only":
            failures.append("created research job must keep memoryStore=candidate_only")
        if job.get("permission", {}).get("externalSend") != "blocked":
            failures.append("created research job must block externalSend")
        if job.get("permission", {}).get("mutation") != "blocked":
            failures.append("created research job must block mutation")

        done = asyncio.run(module.run_deep_research_job(job["id"], executors={"roles": fake_executor}))
        if done.get("status") != "done":
            failures.append("fixture research job should finish")
        if not done.get("memoryCandidates"):
            failures.append("fixture research job should produce memory candidates")
        if any(item.get("status") != "candidate_only" for item in done.get("memoryCandidates", [])):
            failures.append("all memory candidates must stay candidate_only")
        if not done.get("memoryCandidates") or "storeRequires" not in done.get("memoryCandidates", [{}])[0]:
            failures.append("memory candidates must require an explicit store API")
        if "Sample 계약 검증 근거 1" not in json.dumps(done, ensure_ascii=False):
            failures.append("fixture evidence was not represented in job result")

        module.run_parallel_search = failing_parallel_search
        blocked_job = module.create_deep_research_job("막힘 계약 검증", sources=["roles"], limit=2)
        blocked = asyncio.run(module.run_deep_research_job(blocked_job["id"]))
        if blocked.get("status") != "blocked":
            failures.append("failing research job should become blocked after retry")
        retry = module.retry_deep_research_job(blocked_job["id"], reason="contract retry")
        if retry.get("retryQueued") is not True:
            failures.append("blocked research job should allow manual retry queueing")

        running = module.create_deep_research_job("stale 계약 검증", sources=["roles"], limit=2)
        running["status"] = "running"
        running["worker"]["state"] = "running"
        running["worker"]["updatedAt"] = "2020-01-01T00:00:00+00:00"
        module._write_job(running)
        stale = module.mark_stale_running_jobs(older_than_seconds=60)
        if stale.get("changedCount") != 1:
            failures.append("stale running guard should mark old running jobs blocked")
    finally:
        shutil.rmtree(base, ignore_errors=True)


def _fresh_fixture_root() -> Path:
    resolved = FIXTURE_ROOT.resolve()
    runtime_root = (ROOT / "runtime" / "contract-fixtures").resolve()
    if runtime_root not in resolved.parents and resolved != runtime_root:
        raise RuntimeError(f"refusing to reset fixture path outside runtime fixtures: {resolved}")
    if resolved.exists():
        shutil.rmtree(resolved)
    resolved.mkdir(parents=True)
    return resolved


def check_index(failures: list[str]) -> None:
    index = load_yaml(INDEX)
    routes = index.get("route_by_intent") if isinstance(index.get("route_by_intent"), dict) else {}
    route = routes.get("deep_research_lifecycle")
    if not isinstance(route, dict):
        failures.append("registry/_index.yaml missing route_by_intent.deep_research_lifecycle")
        return
    files = route.get("read") if isinstance(route.get("read"), list) else []
    for expected in (
        "registry/services/deep-research.yaml",
        "<your-backend>/services/search_aggregator.py",
        "<your-backend>/services/untrusted_context.py",
        "<your-backend>/services/deep_research.py",
    ):
        if expected not in files:
            failures.append(f"deep_research_lifecycle route missing file: {expected}")


def run_checks() -> dict[str, Any]:
    failures: list[str] = []
    registry = load_yaml(SERVICE_REGISTRY)
    check_registry(registry, failures)
    check_source(failures)
    check_runtime_behavior(failures)
    check_index(failures)
    return {"ok": not failures, "failures": failures, "warnings": []}


def main() -> int:
    try:
        report = run_checks()
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["ok"] else 1
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
