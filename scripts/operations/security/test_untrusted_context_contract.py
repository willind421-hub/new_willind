from __future__ import annotations

from scripts.operations.security.verify_untrusted_context_contract import verify


def test_untrusted_context_contract_is_registered_and_used() -> None:
    result = verify()
    assert result["ok"], result["failures"]
