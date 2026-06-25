from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


DEFAULT_ROOT = next((p for p in Path(__file__).resolve().parents if (p / "registry" / "_index.yaml").exists()), Path(__file__).resolve().parent)
SKIP_PARTS = {"source-chunks"}
FORBIDDEN_VERB_RE = re.compile(r"박(아|았|는|고|지|힌|혀|혔|음|으면|으면|은)")
ALLOWED_WORDS = ("반박", "심박", "압박", "임박", "박스", "박수")


def rel(path: Path, root: Path) -> str:
    return str(path.resolve().relative_to(root.resolve())).replace("\\", "/")


def is_skipped(path: Path) -> bool:
    return any(part in SKIP_PARTS for part in path.parts)


def audit(root: Path) -> dict:
    docs_dir = root / DOC_ROOT
    findings = []
    for path in docs_dir.rglob("*.md"):
        if is_skipped(path.relative_to(docs_dir)):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for line_no, line in enumerate(text.splitlines(), start=1):
            if any(word in line for word in ALLOWED_WORDS):
                scrubbed = line
                for word in ALLOWED_WORDS:
                    scrubbed = scrubbed.replace(word, "")
            else:
                scrubbed = line
            if FORBIDDEN_VERB_RE.search(scrubbed):
                findings.append({"path": rel(path, root), "line": line_no, "text": line.strip()})

    registry = root / "registry/docs/operations-willind-doc-status.yaml"
    readme = docs_dir / "README.md"
    return {
        "ok": not findings and registry.exists() and readme.exists(),
        "counts": {
            "forbidden_verb_lines": len(findings),
            "registry_present": int(registry.exists()),
            "readme_present": int(readme.exists()),
        },
        "findings": findings[:50],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(DEFAULT_ROOT))
    args = parser.parse_args()
    report = audit(Path(args.root))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
