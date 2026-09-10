"""Browser-asset smoke boundary for the credential-free Widget embed."""

from pathlib import Path

import pytest

pytestmark = pytest.mark.e2e


def test_widget_asset_contains_mobile_safe_mount_and_context_reset() -> None:
    root = Path(__file__).parents[2]
    javascript = (root / "storefront" / "assets" / "presales-widget.js").read_text()
    stylesheet = (root / "storefront" / "assets" / "presales-widget.css").read_text()
    assert "data-presales-widget" in javascript
    assert "presales:navigate" in javascript
    assert "contextGeneration" in javascript
    assert "requestGeneration !== contextGeneration" in javascript
    assert "storefrontOrigin" in javascript
    assert "root.dataset.productUrl = next.product_url" in javascript
    assert "max-width: 480px" in stylesheet
