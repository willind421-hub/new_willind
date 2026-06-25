from __future__ import annotations

import importlib.util
import os
from pathlib import Path


ROOT = next((p for p in Path(__file__).resolve().parents if (p / "registry" / "_index.yaml").exists()), Path(__file__).resolve().parent)
SUBJECT_PATH = ROOT / "scripts/operations/providers/willind_provider_entry.py"


def _load_subject():
    spec = importlib.util.spec_from_file_location("willind_provider_entry_subject", SUBJECT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_provider_entry_prepends_existing_dll_paths_without_global_path_mutation(tmp_path):
    subject = _load_subject()
    extra = tmp_path / "dlls"
    extra.mkdir()
    original_process_path = os.environ.get("PATH")
    env = {
        "PATH": str(tmp_path / "bin"),
        "WILLIND_PROVIDER_EXTRA_DLL_PATHS": str(extra),
    }

    subject._prepend_existing_path_entries(env)

    parts = env["PATH"].split(os.pathsep)
    assert parts[0] == str(extra)
    assert str(tmp_path / "bin") in parts
    assert os.environ.get("PATH") == original_process_path
