"""T09 browser asset contract checks without network or browser dependencies."""

from pathlib import Path

import pytest

from storefront import StorefrontWidget, WidgetEmbedConfig, WidgetStatus

pytestmark = pytest.mark.unit
ASSETS = Path(__file__).parents[2] / "storefront" / "assets"


def test_assets_are_credential_free_and_conversation_only() -> None:
    js = (ASSETS / "presales-widget.js").read_text(encoding="utf-8")
    css = (ASSETS / "presales-widget.css").read_text(encoding="utf-8")
    assert "/v1/conversation/turn" in js
    assert "Authorization" not in js
    assert "admin.shopify.com" not in js
    assert '"*"' not in js
    assert "presales:navigate" in js
    assert "@media" in css


def test_widget_navigation_clears_old_product_context() -> None:
    config = WidgetEmbedConfig(
        current_origin="https://shop.example",
        allowed_origins=("https://shop.example",),
        store_id="store",
        product_id="p1",
        variant_id="v1",
    )
    widget = StorefrontWidget(
        config=config, transport=_NoopTransport(), conversation_id="c"
    )
    assert (
        widget.update_context(
            config.model_copy(update={"product_id": "p2", "variant_id": "v2"})
        ).status
        is WidgetStatus.IDLE
    )
    assert widget._turn_request("hello").page_context.product_id == "p2"
    assert widget._turn_request("hello").page_context.variant_id == "v2"


class _NoopTransport:
    def post(self, url: str, *, json: dict[str, object]):
        raise AssertionError("asset unit test must not call the Conversation API")
