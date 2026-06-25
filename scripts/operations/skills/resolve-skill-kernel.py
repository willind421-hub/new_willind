from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = next((p for p in Path(__file__).resolve().parents if (p / "registry" / "_index.yaml").exists()), Path(__file__).resolve().parent)
sys.path.insert(0, str(ROOT))

from core.kernel.skill_kernel_resolver import resolve_to_json  # noqa: E402


def _force_utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


def main() -> int:
    _force_utf8_stdio()
    parser = argparse.ArgumentParser(description="Resolve a user input through the Willind Skill Kernel.")
    parser.add_argument("text", help="User input text to classify.")
    parser.add_argument("--channel", default="text", help="Input channel label. Default: text.")
    args = parser.parse_args()

    print(resolve_to_json(args.text, input_channel=args.channel))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
