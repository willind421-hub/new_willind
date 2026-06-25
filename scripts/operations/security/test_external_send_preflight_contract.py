from __future__ import annotations

from scripts.operations.security import verify_external_send_preflight


def test_external_send_preflight_registry_contract_is_complete(capsys):
    exit_code = verify_external_send_preflight.main()
    captured = capsys.readouterr()

    assert exit_code == 0, captured.out + captured.err
