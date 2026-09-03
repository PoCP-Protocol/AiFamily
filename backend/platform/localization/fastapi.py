"""FastAPI/Starlette adapter for the shared :mod:`context` contract.

The adapter is deliberately separate from the value object so the platform
contract can be tested without making the localization module depend on an
application factory.  A later API composition change can install the
middleware once, while business and AI routes consume ``request.state``.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import HTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from backend.platform.localization.context import LocaleContext, LocaleContextError

_LOCALE_HEADERS = {
    "user_locale": "x-user-locale",
    "content_locale": "x-content-locale",
    "model_locale": "x-model-locale",
    "policy_locale": "x-policy-locale",
}
_FALLBACK_HEADER = "x-locale-fallback"
_PROTECTED_PREFIXES = ("/principal", "/ai")


def _is_protected_path(path: str) -> bool:
    return any(path == prefix or path.startswith(f"{prefix}/") for prefix in _PROTECTED_PREFIXES)


def _fallback_locales(request: Request) -> tuple[str, ...]:
    value = request.headers.get(_FALLBACK_HEADER, "")
    return tuple(item.strip() for item in value.split(",") if item.strip())


def _error(detail: str) -> JSONResponse:
    return JSONResponse(status_code=400, content={"detail": detail})


class LocaleContextMiddleware:
    """Parse explicit locale headers and attach a validated context to a request.

    Existing non-AI routes remain compatible when no locale headers are sent.
    AI-facing paths are protected and require all four dimensions.  Any
    partially supplied or malformed context is rejected rather than filled
    from a process-wide default.
    """

    def __init__(self, app: Callable[[dict, Callable, Callable], Awaitable[Response]]) -> None:
        self.app = app

    async def __call__(self, scope: dict, receive: Callable, send: Callable) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive=receive)
        supplied = {field: request.headers.get(header) for field, header in _LOCALE_HEADERS.items()}
        protected = _is_protected_path(request.url.path)
        fallback_header_supplied = _FALLBACK_HEADER in request.headers
        if not any(supplied.values()) and not fallback_header_supplied:
            if protected:
                response = _error("LOCALE_CONTEXT_REQUIRED")
                await response(scope, receive, send)
                return
            await self.app(scope, receive, send)
            return

        if any(value is None for value in supplied.values()):
            response = _error("LOCALE_CONTEXT_INCOMPLETE")
            await response(scope, receive, send)
            return

        try:
            context = LocaleContext(
                **supplied,
                fallback_locales=_fallback_locales(request),
            )
        except LocaleContextError as exc:
            response = _error(str(exc))
            await response(scope, receive, send)
            return

        scope.setdefault("state", {})["locale_context"] = context
        await self.app(scope, receive, send)


def get_locale_context(request: Request) -> LocaleContext:
    """Return the middleware-provided context as an explicit route dependency.

    Keeping retrieval in one dependency prevents handlers from treating a
    missing middleware installation as an implicit default locale.  The
    dependency is useful for both protected routes and future composition
    tests before the main application mounts the middleware.
    """

    context = getattr(request.state, "locale_context", None)
    if not isinstance(context, LocaleContext):
        raise HTTPException(status_code=400, detail="LOCALE_CONTEXT_REQUIRED")
    return context
