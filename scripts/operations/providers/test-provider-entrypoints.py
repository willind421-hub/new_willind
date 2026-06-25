from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = next((p for p in Path(__file__).resolve().parents if (p / "registry" / "_index.yaml").exists()), Path(__file__).resolve().parent)
ENTRY = ROOT / "scripts/operations/providers/willind_provider_entry.py"


def _run(provider: str, text: str) -> dict[str, object]:
    result = subprocess.run(
        [
            sys.executable,
            str(ENTRY),
            provider,
            "--willind-print-bootstrap-only",
            text,
        ],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(f"{provider} failed: {result.stderr}\n{result.stdout}")
    marker = '{\n  "ok": true'
    start = result.stdout.rfind(marker)
    if start < 0:
        raise AssertionError(f"{provider} did not print JSON report:\n{result.stdout}")
    return json.loads(result.stdout[start:])


def main() -> int:
    cases = {
        "codex": "작은 코드 버그 고쳐줘",
        "claude": "구조가 맞는지 검토해줘",
        "gemini": "스샷 보고 UI 판단해줘",
        "opencode": "코딩 작업을 오픈소스 runner로 검토해줘",
    }
    reports = {}
    for provider, text in cases.items():
        payload = _run(provider, text)
        report = payload["report"]
        files = report.get("files", [])
        if not files:
            raise AssertionError(f"{provider} report has no files")
        for item in files:
            md = Path(item["markdown"])
            js = Path(item["json"])
            if not md.exists() or not js.exists():
                raise AssertionError(f"{provider} missing bootstrap files: {item}")
            content = md.read_text(encoding="utf-8")
            if "Willind Provider Bootstrap" not in content:
                raise AssertionError(f"{provider} markdown is not a provider bootstrap: {md}")
        reports[provider] = report["output_dir"]
    print(json.dumps({"ok": True, "reports": reports}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
