"""Request-scoped bearer context for operator-only HTTP boundaries.

The context is deliberately in-memory and task-local.  It exists only for the
duration of one request and is never suitable as an audit or business value.
"""

from __future__ import annotations

from contextvars import ContextVar, Token

_operator_bearer: ContextVar[str | None] = ContextVar(
    "ai_family_operator_bearer", default=None
)


def parse_bearer_authorization(value: str | None) -> str:
    """Parse one non-empty bearer value without exposing it in errors."""

    if not isinstance(value, str):
        raise _error("IDENTITY_REQUEST_AUTHORIZATION_REQUIRED")
    scheme, separator, token = value.partition(" ")
    if scheme.lower() != "bearer" or separator != " " or not token or token != token.strip():
        raise _error("IDENTITY_REQUEST_AUTHORIZATION_INVALID")
    if any(character.isspace() for character in token):
        raise _error("IDENTITY_REQUEST_AUTHORIZATION_INVALID")
    return token


def bind_operator_bearer(token: str) -> Token[str | None]:
    """Bind an already parsed bearer and return its reset marker."""

    if not isinstance(token, str) or not token or token != token.strip():
        raise _error("IDENTITY_REQUEST_AUTHORIZATION_INVALID")
    return _operator_bearer.set(token)


def reset_operator_bearer(marker: Token[str | None]) -> None:
    """Clear a request bearer using the marker returned by ``bind``."""

    _operator_bearer.reset(marker)


def current_operator_bearer() -> str:
    """Return the current request bearer or fail closed when outside HTTP."""

    token = _operator_bearer.get()
    if token is None:
        raise _error("IDENTITY_REQUEST_TOKEN_REQUIRED")
    return token


def _error(code: str) -> Exception:
    # Import lazily because operator_identity imports this context adapter.
    from backend.intelligence.evaluation.operator_identity import OperatorIdentityError

    return OperatorIdentityError(code)


__all__ = [
    "bind_operator_bearer",
    "current_operator_bearer",
    "parse_bearer_authorization",
    "reset_operator_bearer",
]
