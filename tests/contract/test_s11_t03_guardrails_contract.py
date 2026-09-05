"""Contract-shaped assertions for S11 guardrail outputs."""

import pytest

from backend.runtime import ReadOnlyOperationLedger, safe_error_body

pytestmark = pytest.mark.contract


def test_safe_error_contract_is_stable_and_minimal() -> None:
    body = safe_error_body("RATE_LIMITED", retryable=True)

    assert set(body) == {"error_code", "message", "retryable"}
    assert body["error_code"] == "RATE_LIMITED"
    assert body["retryable"] is True
    assert body["message"] == "The request could not be completed."


def test_read_ledger_contract_has_zero_write_calls() -> None:
    ledger = ReadOnlyOperationLedger(allowed_operations=frozenset({"read_product"}))
    ledger.record_read("read_product")

    assert ledger.operations == ("read_product",)
    assert ledger.read_count == 1
    assert ledger.write_call_count == 0
    assert "record_write" not in dir(ledger)
