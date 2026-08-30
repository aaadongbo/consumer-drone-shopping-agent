"""Non-business smoke coverage for the test harness."""

from importlib import import_module

import pytest


@pytest.mark.unit
def test_backend_package_is_importable() -> None:
    backend = import_module("backend")

    assert backend.__name__ == "backend"
