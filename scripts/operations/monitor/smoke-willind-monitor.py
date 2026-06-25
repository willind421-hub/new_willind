from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
RUNNER = ROOT / "scripts" / "operations" / "monitor" / "willind_monitor_runner.py"
PM2_CONFIG = ROOT / "scripts" / "operations" / "monitor" / "willind-monitor.pm2.config.cjs"


def main() -> int:
    errors: list[str] = []

    dry_run = subprocess.run(
        [sys.executable, str(RUNNER), "--mode", "dry-run", "--json"],
        cwd=str(ROOT),
        text=True,
        capture_output=True,
        timeout=30,
    )
    if dry_run.returncode != 0:
        errors.append(f"runner dry-run failed: {dry_run.stderr.strip() or dry_run.stdout.strip()}")
    else:
        payload = json.loads(dry_run.stdout)
        component_ids = {component["id"] for component in payload["components"]}
        expected = {"service-supervisor", "error-inbox", "willind-body-health", "command-center-health"}
        if not payload.get("ok"):
            errors.append("runner dry-run returned ok=false")
        if component_ids != expected:
            errors.append(f"runner components mismatch: {sorted(component_ids)}")

    node = shutil.which("node")
    if not node:
        errors.append("node executable not found; PM2 config cannot be loaded")
    else:
        script = (
            "const c=require('./scripts/operations/monitor/willind-monitor.pm2.config.cjs');"
            "if(!c.apps||c.apps.length!==1) process.exit(2);"
            "const app=c.apps[0];"
            "if(app.name!=='willind-monitor') process.exit(3);"
            "if(!String(app.args).includes('--mode once')) process.exit(4);"
            "console.log(JSON.stringify({name:app.name,script:app.script,args:app.args,cron_restart:app.cron_restart}));"
        )
        config = subprocess.run(
            [node, "-e", script],
            cwd=str(ROOT),
            text=True,
            capture_output=True,
            timeout=30,
        )
        if config.returncode != 0:
            errors.append(f"PM2 config load failed: {config.stderr.strip() or config.stdout.strip()}")

    if errors:
        print("SMOKE FAIL")
        for error in errors:
            print(f"- {error}")
        return 1

    print("SMOKE PASS")
    print("runner=dry-run")
    print(f"pm2_config={PM2_CONFIG}")
    print("pm2_start_executed=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
