from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = next((p for p in Path(__file__).resolve().parents if (p / "registry" / "_index.yaml").exists()), Path(__file__).resolve().parent)


def test_provider_probe_contract_verifier_passes() -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/operations/providers/verify_provider_probe_contract.py")],
        cwd=str(ROOT),
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["failures"] == []
