from __future__ import annotations

from scripts.operations.security.verify_tool_visibility_contract import verify


def test_tool_visibility_contract_hides_dangerous_tools_for_low_trust_callers() -> None:
    result = verify()
    assert result["ok"], result["failures"]
