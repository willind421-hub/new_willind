from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
OUTPUT = ROOT / "runtime" / "monitor" / "willind-monitor" / "latest.json"

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Willind deterministic monitor runner")
    parser.add_argument(
        "--mode",
        choices=("dry-run", "once"),
        default="dry-run",
        help="dry-run validates wiring only; once runs read-only probes.",
    )
    parser.add_argument("--json", action="store_true", help="Print JSON output.")
    parser.add_argument(
        "--write-output",
        action="store_true",
        help=f"Write latest JSON to {OUTPUT}.",
    )
    parser.add_argument(
        "--execute-command-center-health",
        action="store_true",
        help="Allow the command-center health wrapper to execute the existing health script.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = run_monitor(args.mode, args.execute_command_center_health)

    if args.write_output:
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"willind-monitor ok={result['ok']} mode={result['mode']}")
        for component in result["components"]:
            print(f"- {component['id']}: ok={component['ok']} status={component['status']}")

    return 0 if result["ok"] else 1


def run_monitor(mode: str, execute_command_center_health: bool) -> dict[str, Any]:
    components = [
        service_supervisor(mode),
        error_inbox(mode),
        body_health(mode),
        command_center_health(mode, execute_command_center_health),
    ]
    return {
        "ok": all(component["ok"] for component in components),
        "service": "willind-monitor",
        "mode": mode,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "root": str(ROOT),
        "components": components,
        "guards": {
            "starts_services": False,
            "stops_services": False,
            "deletes_files": False,
            "reads_secret_files": False,
        },
    }


def service_supervisor(mode: str) -> dict[str, Any]:
    project = ROOT / "projects" / "willind-service-supervisor"
    manifest = project / "manifests" / "services.json"
    command = [sys.executable, "-m", "willind_service_supervisor.cli", "status"]
    env = {"PYTHONPATH": str(project)}
    if mode == "dry-run":
        return dry_component("service-supervisor", project, command, extra={"manifest": str(manifest)})
    return run_component("service-supervisor", project, command, env)


def error_inbox(mode: str) -> dict[str, Any]:
    project = ROOT / "projects" / "willind-error-inbox"
    manifest = project / "config" / "log_sources.json"
    command = [
        sys.executable,
        "-m",
        "willind_error_inbox",
        "--manifest",
        str(manifest),
        "scan",
        "--json",
    ]
    env = {"PYTHONPATH": str(project / "src")}
    if mode == "dry-run":
        return dry_component("error-inbox", project, command, extra={"manifest": str(manifest)})
    return run_component("error-inbox", project, command, env)


def body_health(mode: str) -> dict[str, Any]:
    script = ROOT / "scripts" / "operations" / "monitor" / "willind_body_health.py"
    registry = ROOT / "registry" / "services" / "willind-body-health.yaml"
    command = [sys.executable, str(script), "--json"]
    if mode == "dry-run":
        return dry_component("willind-body-health", ROOT, command, extra={"registry": str(registry)})
    return run_component("willind-body-health", ROOT, command, {})


def command_center_health(mode: str, execute: bool) -> dict[str, Any]:
    wrapper = ROOT / "scripts" / "operations" / "command-center" / "monitor-command-center-health.ps1"
    target = ROOT / "scripts" / "operations" / "command-center" / "command-center-health.ps1"
    command = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(wrapper),
        "-DryRun",
    ]
    if mode == "dry-run" or not execute:
        return dry_component(
            "command-center-health",
            ROOT,
            command,
            extra={
                "wrapper": str(wrapper),
                "target": str(target),
                "execution_skipped": True,
                "skip_reason": "existing health script may read .env; smoke validates wrapper wiring only",
            },
        )

    command[-1] = "-Execute"
    return run_component("command-center-health", ROOT, command, {})


def dry_component(
    component_id: str,
    cwd: Path,
    command: list[str],
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    path_checks = [cwd.exists()]
    if extra:
        for key in ("manifest", "wrapper", "target", "registry"):
            value = extra.get(key)
            if value:
                path_checks.append(Path(value).exists())
    return {
        "id": component_id,
        "ok": all(path_checks),
        "status": "dry-run",
        "cwd": str(cwd),
        "command": command,
        **(extra or {}),
    }


def run_component(
    component_id: str,
    cwd: Path,
    command: list[str],
    env_extra: dict[str, str],
    timeout_seconds: int = 30,
) -> dict[str, Any]:
    if not cwd.exists():
        return {
            "id": component_id,
            "ok": False,
            "status": "missing-cwd",
            "cwd": str(cwd),
            "command": command,
        }

    env = os.environ.copy()
    env.update(env_extra)
    completed = subprocess.run(
        command,
        cwd=str(cwd),
        env=env,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=timeout_seconds,
    )
    return {
        "id": component_id,
        "ok": completed.returncode == 0,
        "status": "completed" if completed.returncode == 0 else "failed",
        "returncode": completed.returncode,
        "cwd": str(cwd),
        "command": command,
        "stdout": trim(completed.stdout),
        "stderr": trim(completed.stderr),
    }


def trim(value: str | None, limit: int = 6000) -> str:
    if value is None:
        return ""
    if len(value) <= limit:
        return value
    return value[:limit] + "\n...[trimmed]"


if __name__ == "__main__":
    raise SystemExit(main())
