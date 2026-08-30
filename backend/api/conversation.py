"""Thin synchronous transport boundary for the Slice 1 application service."""

from typing import Any, Final, Protocol

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from backend.common import (
    SCHEMA_VERSION,
    TURN_REQUEST_VALIDATION_HTTP_STATUS,
    AnswerEnvelope,
    TurnRequest,
    TurnRequestValidationResponse,
)

CONVERSATION_TURN_PATH: Final = "/v1/conversation/turn"


class ConversationApplication(Protocol):
    """The only application capability visible to the transport layer."""

    def answer(self, request: TurnRequest) -> AnswerEnvelope: ...


class JsonResponse(Protocol):
    status_code: int

    def json(self) -> Any: ...


class SyncJsonTransport(Protocol):
    """Minimal surface implemented by FastAPI's in-process TestClient."""

    def post(self, url: str, *, json: dict[str, Any]) -> JsonResponse: ...


class ConversationTransportError(RuntimeError):
    """Stable client-side representation of a rejected TurnRequest."""

    def __init__(
        self,
        *,
        status_code: int,
        response: TurnRequestValidationResponse | None = None,
    ) -> None:
        super().__init__("Conversation transport rejected the request.")
        self.status_code = status_code
        self.response = response


class MinimalConversationClient:
    """Serialize requests and validate responses with the public wire contracts."""

    def __init__(self, transport: SyncJsonTransport) -> None:
        self._transport = transport

    def ask(self, request: TurnRequest) -> AnswerEnvelope:
        response = self._transport.post(
            CONVERSATION_TURN_PATH,
            json=request.to_wire(),
        )
        if response.status_code == TURN_REQUEST_VALIDATION_HTTP_STATUS:
            validation = TurnRequestValidationResponse.model_validate(response.json())
            raise ConversationTransportError(
                status_code=response.status_code,
                response=validation,
            )
        if response.status_code != 200:
            raise ConversationTransportError(status_code=response.status_code)
        return AnswerEnvelope.model_validate(response.json())


def create_conversation_api(application: ConversationApplication) -> FastAPI:
    """Build one injected endpoint without adding domain decisions to transport."""
    api = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    @api.exception_handler(RequestValidationError)
    async def reject_invalid_turn(
        _request: Request,
        _error: RequestValidationError,
    ) -> JSONResponse:
        rejection = TurnRequestValidationResponse(
            schema_version=SCHEMA_VERSION,
            error_code="INVALID_TURN_REQUEST",
            message="Request validation failed.",
        )
        return JSONResponse(
            status_code=TURN_REQUEST_VALIDATION_HTTP_STATUS,
            content=rejection.to_wire(),
        )

    @api.post(CONVERSATION_TURN_PATH, response_model=AnswerEnvelope)
    def answer_turn(request: TurnRequest) -> AnswerEnvelope:
        return application.answer(request)

    return api
