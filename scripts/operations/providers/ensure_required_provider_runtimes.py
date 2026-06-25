from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import yaml


ROOT = Path(__file__).resolve().parents[3]
PROVIDER_ROUTING_PATH = ROOT / "registry" / "providers" / "provider-cli-routing.yaml"
STATE_DIR = ROOT / "runtime" / "provider-runtimes"
LOG_DIR = ROOT / "runtime" / "logs" / "provider-runtimes"
STATE_PATH = STATE_DIR / "required-provider-runtimes.json"

REQUIRED_REGISTRY_STATUSES = {"active", "limited"}


@dataclass(frozen=True)
class RuntimeSpec:
    id: str
    label: str
    cwd: Path
    argv: tuple[str, ...]
    health_url: str
    port: int


@dataclass
class OwnedProcess:
    pid: int

    def terminate(self) -> None:
        try:
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/PID", str(self.pid), "/T", "/F"],
                    text=True,
                    capture_output=True,
                    check=False,
                    timeout=4,
                )
                time.sleep(0.2)
                if not _pid_alive(self.pid):
                    return
            os.kill(self.pid, 15)
            time.sleep(0.2)
            if _pid_alive(self.pid):
                os.kill(self.pid, signal.SIGTERM)
        except Exception:
            pass


Starter = Callable[[RuntimeSpec], OwnedProcess]
HealthProbe = Callable[[str], dict[str, Any]]
Sleeper = Callable[[float], None]


def runtime_specs(python_executable: str | None = None) -> list[RuntimeSpec]:
    python_executable = python_executable or sys.executable
    return [
        RuntimeSpec(
            id="service_supervisor",
            label="서비스 감독기",
            cwd=ROOT / "projects" / "willind-service-supervisor",
            argv=(
                python_executable,
                "-m",
                "willind_service_supervisor.cli",
                "serve",
                "--host",
                "127.0.0.1",
                "--port",
                "18065",
            ),
            health_url="http://127.0.0.1:18065/health",
            port=18065,
        ),
        RuntimeSpec(
            id="tool_slot_runtime",
            label="도구 슬롯 런타임",
            cwd=ROOT / "projects" / "willind-tool-slot-registry",
            argv=(
                python_executable,
                "-m",
                "tool_slot_registry.cli",
                "serve",
                "--host",
                "127.0.0.1",
                "--port",
                "18075",
            ),
            health_url="http://127.0.0.1:18075/health",
            port=18075,
        ),
    ]


def load_provider_statuses(path: Path = PROVIDER_ROUTING_PATH) -> dict[str, str]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    providers = data.get("providers") if isinstance(data.get("providers"), dict) else {}
    statuses: dict[str, str] = {}
    for provider_id, meta in providers.items():
        if isinstance(meta, dict):
            statuses[str(provider_id)] = str(meta.get("status") or "")
    return statuses


def probe_health(url: str, timeout: float = 0.6) -> dict[str, Any]:
    start = time.perf_counter()
    request = Request(url, headers={"User-Agent": "willind-provider-runtime-launcher/0.1"})
    try:
        with urlopen(request, timeout=timeout) as response:
            latency_ms = round((time.perf_counter() - start) * 1000, 1)
            status_code = int(response.status)
            status = "available" if 200 <= status_code < 300 else "degraded"
            return {"status": status, "latencyMs": latency_ms, "reason": f"HTTP {status_code}"}
    except HTTPError as exc:
        latency_ms = round((time.perf_counter() - start) * 1000, 1)
        return {"status": "degraded", "latencyMs": latency_ms, "reason": f"HTTP {exc.code}"}
    except (TimeoutError, URLError, OSError) as exc:
        latency_ms = round((time.perf_counter() - start) * 1000, 1)
        return {"status": "unavailable", "latencyMs": latency_ms, "reason": type(exc).__name__}


def default_starter(spec: RuntimeSpec) -> OwnedProcess:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    out_path = LOG_DIR / f"{spec.id}.out.log"
    err_path = LOG_DIR / f"{spec.id}.err.log"
    stdout = out_path.open("ab")
    stderr = err_path.open("ab")
    creationflags = 0
    if os.name == "nt":
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
    try:
        proc = subprocess.Popen(
            list(spec.argv),
            cwd=str(spec.cwd),
            stdout=stdout,
            stderr=stderr,
            stdin=subprocess.DEVNULL,
            shell=False,
            creationflags=creationflags,
        )
    finally:
        stdout.close()
        stderr.close()
    return OwnedProcess(pid=int(proc.pid))


def run(
    *,
    start: bool = False,
    dry_run: bool = False,
    timeout_seconds: float = 8.0,
    specs: list[RuntimeSpec] | None = None,
    registry_statuses: dict[str, str] | None = None,
    health_probe: HealthProbe = probe_health,
    starter: Starter = default_starter,
    sleeper: Sleeper = time.sleep,
) -> dict[str, Any]:
    specs = specs or runtime_specs()
    registry_statuses = registry_statuses or load_provider_statuses()
    mode = "start" if start else "dry_run" if dry_run else "status"
    services: list[dict[str, Any]] = []
    started: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []

    for spec in specs:
        registry_status = registry_statuses.get(spec.id, "")
        required = registry_status in REQUIRED_REGISTRY_STATUSES
        before = health_probe(spec.health_url)
        action = _action_for(before, required, start=start, dry_run=dry_run)
        item: dict[str, Any] = {
            "id": spec.id,
            "label": spec.label,
            "registryStatus": registry_status,
            "requiredForLive": required,
            "health": before,
            "port": spec.port,
            "cwd": str(spec.cwd.relative_to(ROOT)),
            "commandPreview": _command_preview(spec),
            "action": action,
            "logPaths": {
                "stdout": str((LOG_DIR / f"{spec.id}.out.log").relative_to(ROOT)),
                "stderr": str((LOG_DIR / f"{spec.id}.err.log").relative_to(ROOT)),
            },
        }
        if start and required and before.get("status") != "available":
            _start_and_wait(
                item,
                spec,
                timeout_seconds=timeout_seconds,
                health_probe=health_probe,
                starter=starter,
                sleeper=sleeper,
                started=started,
                failed=failed,
            )
        services.append(item)

    counts = {
        "services": len(services),
        "required": sum(1 for item in services if item["requiredForLive"]),
        "available": sum(1 for item in services if item["health"].get("status") == "available"),
        "attention": sum(1 for item in services if item["requiredForLive"] and item["health"].get("status") != "available"),
        "started": len(started),
        "failedStart": len(failed),
    }
    payload = {
        "ok": not failed,
        "contract": "willind.required_provider_runtime_launcher",
        "version": "0.1.0",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "mode": mode,
        "wouldExecute": bool(start),
        "timeoutSeconds": timeout_seconds,
        "readSecretValues": False,
        "startsOnlyRequiredLocalProviders": True,
        "services": services,
        "counts": counts,
    }
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def _start_and_wait(
    item: dict[str, Any],
    spec: RuntimeSpec,
    *,
    timeout_seconds: float,
    health_probe: HealthProbe,
    starter: Starter,
    sleeper: Sleeper,
    started: list[dict[str, Any]],
    failed: list[dict[str, Any]],
) -> None:
    process = starter(spec)
    item["ownedPid"] = process.pid
    deadline = time.monotonic() + max(timeout_seconds, 0.1)
    latest = item["health"]
    while time.monotonic() < deadline:
        sleeper(0.35)
        latest = health_probe(spec.health_url)
        if latest.get("status") == "available":
            item["health"] = latest
            item["action"] = "started_available"
            started.append({"id": spec.id, "pid": process.pid})
            return
    item["health"] = latest
    item["action"] = "start_failed_cleaned"
    process.terminate()
    failed.append({"id": spec.id, "pid": process.pid, "reason": latest.get("reason")})


def _action_for(health: dict[str, Any], required: bool, *, start: bool, dry_run: bool) -> str:
    if health.get("status") == "available":
        return "already_available"
    if not required:
        return "optional_or_not_required"
    if start:
        return "start_pending"
    if dry_run:
        return "would_start"
    return "attention_required"


def _command_preview(spec: RuntimeSpec) -> list[str]:
    preview = list(spec.argv)
    if preview:
        preview[0] = Path(preview[0]).name
    return preview


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    except PermissionError:
        return True
    return True


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ensure required Willind provider runtimes with bounded startup.")
    parser.add_argument("--start", action="store_true", help="Start unavailable required local runtimes.")
    parser.add_argument("--dry-run", action="store_true", help="Report what would start without starting processes.")
    parser.add_argument("--timeout-seconds", type=float, default=8.0)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    payload = run(start=args.start, dry_run=args.dry_run, timeout_seconds=args.timeout_seconds)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
