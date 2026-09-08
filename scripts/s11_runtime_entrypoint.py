"""Production ASGI entrypoint for the S11 closed-beta Conversation API.

The entrypoint is deliberately fail-closed.  It can expose liveness while a
deployment is being configured, but it never substitutes fixtures for missing
Shopify credentials, corpus metadata, or identity bindings.  Secret values and
source text stay in adapter process memory and are never included in responses
or logs.
"""

from __future__ import annotations

import json
import os
import threading
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from backend.api import install_cors_guardrail, install_safe_exception_handler
from backend.catalog import (
    PilotProductIdentity,
    PilotVariantIdentity,
    build_pilot_data_readiness_report,
)
from backend.rag import (
    CorpusScopeBindingRegistry,
    ExternalCorpusProductRetriever,
    ExternalCorpusReader,
    build_corpus_readiness_report,
    validate_corrected_chunk_baseline_manifest,
)
from backend.runtime import (
    ReleaseConfig,
    ReleaseConfigError,
    ReleaseDependencies,
    build_closed_beta_composition,
    build_health_report,
)
from backend.shopify import (
    MacOSKeychainAccessTokenProvider,
    RealShopifyReadAdapter,
    ShopifyCredentialError,
    ShopifyReadTransport,
    ShopifyTokenProvider,
    ShopifyTransportResult,
    UrllibShopifyReadTransport,
)
from scripts.s11_prepare_corpus_sidecars import prepare as prepare_corpus_sidecars

APPROVED_ORIGIN = "https://bys-user-store-578412-7a11gk0u.myshopify.com"
APPROVED_SHOPIFY_STORE_DOMAIN = "bys-user-store-578412-7a11gk0u.myshopify.com"
APPROVED_STORE_ID = "shopify-store:bys-user-store-578412-7a11gk0u"
APPROVED_PRODUCTS = (
    ("Mini 3", "9278439686282", "50107364802698"),
    ("Air 3", "9278460821642", "50107426603146"),
    ("Mavic 3", "9278439719050", "50107364901002"),
)


class RuntimeDependencyError(RuntimeError):
    """A required release dependency is absent or fails closed."""


class _CanonicalStoreTransport:
    """Translate the internal canonical store scope to Shopify's host key."""

    def __init__(
        self,
        delegate: ShopifyReadTransport,
        *,
        canonical_store_id: str,
        shopify_store_domain: str,
    ) -> None:
        self._delegate = delegate
        self._canonical_store_id = canonical_store_id
        self._shopify_store_domain = shopify_store_domain

    def _domain(self, store_id: str) -> str:
        if store_id != self._canonical_store_id:
            raise RuntimeDependencyError("request store is outside the pilot scope")
        return self._shopify_store_domain

    def read_product(self, *, store_id: str, product_id: str) -> ShopifyTransportResult:
        return self._delegate.read_product(
            store_id=self._domain(store_id), product_id=product_id
        )

    def read_variants(
        self, *, store_id: str, product_id: str
    ) -> ShopifyTransportResult:
        return self._delegate.read_variants(
            store_id=self._domain(store_id), product_id=product_id
        )

    def read_commerce_state(
        self, *, store_id: str, product_id: str, variant_id: str
    ) -> ShopifyTransportResult:
        return self._delegate.read_commerce_state(
            store_id=self._domain(store_id),
            product_id=product_id,
            variant_id=variant_id,
        )


class _EnvironmentAccessTokenProvider:
    """Read one hosted token without exposing it through diagnostics."""

    def __init__(self, environ: Mapping[str, str]) -> None:
        self._environ = environ

    def get_access_token(self) -> str:
        token = self._environ.get("DRONE_SHOPIFY_ACCESS_TOKEN", "").strip()
        # Shopify client-credentials access tokens are opaque values.  Unlike
        # legacy Admin API tokens, they are not guaranteed to use the
        # ``shpat_`` prefix.  Keep the startup gate limited to a safe, usable
        # value check; scope and validity are verified by the read-only
        # adapter when it performs its bounded Shopify request.
        if not token or any(char.isspace() or ord(char) < 0x20 for char in token):
            raise ShopifyCredentialError("Shopify access token is unavailable")
        return token


class _RuntimeState:
    def __init__(self, environ: Mapping[str, str]) -> None:
        self.config: ReleaseConfig | None = None
        self.composition = None
        self.failure_code: str | None = None
        self._initialization_started = False
        self._lock = threading.Lock()
        try:
            self.config = ReleaseConfig.from_env(environ)
        except (ReleaseConfigError, RuntimeDependencyError, ValueError):
            self.failure_code = "RUNTIME_NOT_READY"

        self._environ = environ

    def start_initialization(self) -> None:
        """Initialize external dependencies after Uvicorn can bind its port.

        Corpus validation is intentionally fail-closed, but it can involve a
        mounted source region.  It must not block Render's process/port
        detection.  Until initialization succeeds, ``/readyz`` and the turn
        endpoint retain their explicit unavailable behavior.
        """

        if self.config is None:
            return
        with self._lock:
            if self._initialization_started:
                return
            self._initialization_started = True
        threading.Thread(
            target=self._initialize_dependencies,
            name="s11-runtime-readiness",
            daemon=True,
        ).start()

    def _initialize_dependencies(self) -> None:
        assert self.config is not None
        try:
            # Render mounts persistent disks after image build/pre-deploy.  Do
            # this idempotent metadata-only linking step from the running
            # process, once the mount is available, before corpus validation.
            if self._environ.get("DRONE_CORPUS_ROOT"):
                prepare_corpus_sidecars()
            dependencies = _build_dependencies(self.config, self._environ)
            composition = build_closed_beta_composition(self.config, dependencies)
        except (
            OSError,
            ReleaseConfigError,
            RuntimeError,
            RuntimeDependencyError,
            ValueError,
        ):
            with self._lock:
                self.failure_code = "RUNTIME_NOT_READY"
            return
        with self._lock:
            self.composition = composition
            self.failure_code = None

    @property
    def ready(self) -> bool:
        with self._lock:
            return self.composition is not None and self.failure_code is None

    def current_api(self) -> FastAPI | None:
        with self._lock:
            return self.composition.api if self.composition is not None else None


class _CompositionDispatch:
    """Delegate non-health requests once the closed-beta composition is ready."""

    def __init__(self, state: _RuntimeState, unavailable_app: FastAPI) -> None:
        self._state = state
        self._unavailable_app = unavailable_app

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        application = self._state.current_api()
        if application is None:
            await self._unavailable_app(scope, receive, send)
            return
        await application(scope, receive, send)


def create_runtime_app(
    environ: Mapping[str, str] | None = None,
) -> FastAPI:
    """Create the production app and retain a safe, metadata-only readiness view."""

    source = os.environ if environ is None else environ
    state = _RuntimeState(source)
    api = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    install_cors_guardrail(api, _configured_origins(state.config))
    install_safe_exception_handler(api)

    @api.get("/healthz")
    def healthz() -> JSONResponse:
        return JSONResponse(
            status_code=200,
            content=_health_payload(state, ready=False),
        )

    @api.get("/readyz")
    def readyz() -> JSONResponse:
        return JSONResponse(
            status_code=200 if state.ready else 503,
            content=_health_payload(state, ready=True),
        )

    assets = Path(__file__).resolve().parents[1] / "storefront" / "assets"
    if assets.is_dir():
        api.mount(
            "/widget/assets", StaticFiles(directory=str(assets)), name="widget-assets"
        )

    api.mount("/", _CompositionDispatch(state, _unavailable_application()))
    state.start_initialization()

    return api


def _unavailable_application() -> FastAPI:
    """Return the stable unavailable response without exposing dependencies."""

    fallback = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    @fallback.post("/v1/conversation/turn")
    def unavailable_turn() -> JSONResponse:
        return JSONResponse(
            status_code=503,
            content={
                "error_code": "RUNTIME_NOT_READY",
                "message": "The conversation service is not ready.",
                "retryable": False,
            },
        )

    return fallback


def _configured_origins(config: ReleaseConfig | None) -> tuple[str, ...]:
    if config is None:
        return (APPROVED_ORIGIN,)
    return config.widget_origins


def _health_payload(state: _RuntimeState, *, ready: bool) -> dict[str, object]:
    config = state.config
    if config is None:
        return {
            "status": "not_ready" if ready else "ok",
            "checks": {
                "process": "ok",
                "configuration": "not_ready",
                "pilot_readiness": "not_ready",
            },
            "credential_values_exposed": False,
            "shopify_write_count": 0,
        }
    report = build_health_report(
        config,
        readiness_ok=state.ready,
        dependency_checks={
            "shopify": state.ready,
            "corpus": state.ready,
        },
    )
    payload = report.to_safe_dict()
    payload["credential_values_exposed"] = False
    payload["shopify_write_count"] = 0
    if not ready:
        payload["status"] = "ok"
    return payload


def _build_dependencies(
    config: ReleaseConfig,
    environ: Mapping[str, str],
) -> ReleaseDependencies:
    if config.store_id != APPROVED_STORE_ID:
        raise RuntimeDependencyError("pilot store is not approved")
    scope = environ.get("DRONE_CREDENTIAL_SCOPE", "")
    if scope != "read_products,read_inventory":
        raise RuntimeDependencyError("read-only credential scope is not verified")

    token_provider: ShopifyTokenProvider
    if config.environment.value == "local":
        service = config.keychain_service
        account = environ.get("DRONE_KEYCHAIN_ACCOUNT", "")
        if not service or not account:
            raise RuntimeDependencyError("local credential references are incomplete")
        token_provider = MacOSKeychainAccessTokenProvider(
            service=service,
            account=account,
        )
    else:
        token_provider = _EnvironmentAccessTokenProvider(environ)
    transport = UrllibShopifyReadTransport(
        token_provider=token_provider,
        api_version=environ.get("DRONE_SHOPIFY_API_VERSION", "2026-07"),
        timeout_seconds=config.shopify_request_timeout_ms / 1000,
        proxy_url=environ.get("DRONE_HTTPS_PROXY") or None,
        ca_bundle=environ.get("DRONE_CA_BUNDLE") or None,
    )
    canonical_transport = _CanonicalStoreTransport(
        transport,
        canonical_store_id=config.store_id,
        shopify_store_domain=APPROVED_SHOPIFY_STORE_DOMAIN,
    )
    approved_variant_ids = {
        product_id: variant_id for _name, product_id, variant_id in APPROVED_PRODUCTS
    }
    shopify = RealShopifyReadAdapter(
        transport=canonical_transport,
        approved_store_id=config.store_id,
        approved_variant_ids=approved_variant_ids,
        max_read_calls=config.max_shopify_read_calls_per_turn,
        max_attempts=1,
    )

    corpus_root = _required_path(environ, "DRONE_CORPUS_ROOT")
    chunk_manifest_path = _required_path(environ, "DRONE_CHUNK_MANIFEST_PATH")
    bindings_path = _required_path(environ, "DRONE_CORPUS_BINDINGS_PATH")
    expected_manifest_sha256 = environ.get("DRONE_CORPUS_MANIFEST_SHA256", "")
    if len(expected_manifest_sha256) != 64:
        raise RuntimeDependencyError("corpus manifest identity is missing")
    corpus_report = build_corpus_readiness_report(corpus_root)
    chunk_report = validate_corrected_chunk_baseline_manifest(chunk_manifest_path)
    if chunk_report.manifest_sha256 != expected_manifest_sha256:
        raise RuntimeDependencyError("corpus manifest identity does not match")
    bindings = CorpusScopeBindingRegistry.model_validate(_read_json(bindings_path))
    reader = ExternalCorpusReader(corpus_root=corpus_root)
    static_retriever = ExternalCorpusProductRetriever(
        reader=reader,
        chunk_manifest_path=str(chunk_manifest_path),
        binding_registry=bindings,
        manifest_sha256=expected_manifest_sha256,
        max_action_rounds=config.max_action_rounds,
        turn_deadline_ms=config.request_timeout_ms,
    )
    products = tuple(
        PilotProductIdentity(
            product_name=name,
            store_id=config.store_id,
            product_id=product_id,
            variants=(
                PilotVariantIdentity(
                    store_id=config.store_id,
                    product_id=product_id,
                    variant_id=variant_id,
                ),
            ),
        )
        for name, product_id, variant_id in APPROVED_PRODUCTS
    )
    readiness = build_pilot_data_readiness_report(
        store_id=config.store_id,
        products=products,
        credential_read_only=True,
        corpus_report=corpus_report,
        chunk_baseline_report=chunk_report,
        approved_product_names=tuple(name for name, _pid, _vid in APPROVED_PRODUCTS),
    )
    if not readiness.ready:
        raise RuntimeDependencyError("pilot readiness is not accepted")
    return ReleaseDependencies(
        shopify=shopify,
        static_retriever=static_retriever,
        readiness=readiness,
    )


def _required_path(environ: Mapping[str, str], key: str) -> Path:
    value = environ.get(key, "").strip()
    if not value:
        raise RuntimeDependencyError(f"{key} is required")
    path = Path(value)
    if not path.exists():
        raise RuntimeDependencyError(f"{key} is unavailable")
    return path


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RuntimeDependencyError("runtime metadata is invalid") from error
    if not isinstance(value, dict):
        raise RuntimeDependencyError("runtime metadata must be an object")
    return value


app = create_runtime_app()


__all__ = ["APPROVED_ORIGIN", "APPROVED_PRODUCTS", "app", "create_runtime_app"]
