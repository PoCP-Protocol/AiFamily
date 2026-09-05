"""Explicit locale context for the cross-language platform boundary.

The source architecture distinguishes the user's language from the language
of content, model capability, and policy or human review.  Keeping those
dimensions separate prevents a UI preference from silently selecting a policy
translation or a model that cannot safely serve the request.

This module resolves locale availability only.  It does not translate text and
does not silently fall back: callers must provide an explicit fallback order
and a set of reliable supported locales.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum


class LocaleContextError(ValueError):
    """Raised when locale metadata is malformed or cannot be served safely."""


class LocaleDimension(StrEnum):
    """The four independent language decisions carried by a request."""

    USER = "user_locale"
    CONTENT = "content_locale"
    MODEL = "model_locale"
    POLICY = "policy_locale"


_LOCALE_RE = re.compile(r"[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*")
_CONTEXT_FIELDS = frozenset(
    {
        "user_locale",
        "content_locale",
        "model_locale",
        "policy_locale",
        "fallback_locales",
    }
)


def _canonicalize_locale(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not _LOCALE_RE.fullmatch(value):
        raise LocaleContextError(f"{field_name}_UNSUPPORTED")

    parts = value.split("-")
    normalized = [parts[0].lower()]
    for part in parts[1:]:
        if len(part) == 4 and part.isalpha():
            normalized.append(part.title())
        elif (len(part) == 2 and part.isalpha()) or (len(part) == 3 and part.isdigit()):
            normalized.append(part.upper())
        else:
            normalized.append(part.lower())
    return "-".join(normalized)


def _normalize_fallbacks(values: Iterable[str]) -> tuple[str, ...]:
    if isinstance(values, str):
        raise LocaleContextError("fallback_locale_UNSUPPORTED")
    normalized: list[str] = []
    for value in values:
        locale = _canonicalize_locale(value, "fallback_locale")
        if locale not in normalized:
            normalized.append(locale)
    return tuple(normalized)


@dataclass(frozen=True, slots=True)
class LocaleContext:
    """The complete language envelope for one API/runtime request.

    ``fallback_locales`` is an ordered, explicit list shared by resolution
    callers.  It is intentionally not inferred from ``user_locale`` or from
    a process-wide default.
    """

    user_locale: str
    content_locale: str
    model_locale: str
    policy_locale: str
    fallback_locales: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for field_name in (
            "user_locale",
            "content_locale",
            "model_locale",
            "policy_locale",
        ):
            object.__setattr__(
                self,
                field_name,
                _canonicalize_locale(getattr(self, field_name), field_name),
            )
        object.__setattr__(self, "fallback_locales", _normalize_fallbacks(self.fallback_locales))

    def locale_for(self, dimension: LocaleDimension | str) -> str:
        """Return the primary locale for a named language dimension."""

        try:
            resolved_dimension = LocaleDimension(dimension)
        except ValueError as exc:
            raise LocaleContextError("LOCALE_DIMENSION_UNSUPPORTED") from exc
        return getattr(self, resolved_dimension.value)

    def candidates(self, dimension: LocaleDimension | str) -> tuple[str, ...]:
        """Return primary locale followed by the caller's explicit fallbacks."""

        primary = self.locale_for(dimension)
        return (primary, *(locale for locale in self.fallback_locales if locale != primary))

    def resolve_reliable(
        self,
        dimension: LocaleDimension | str,
        *,
        supported_locales: Iterable[str],
        reliable_locales: Iterable[str],
    ) -> str:
        """Resolve a reliable locale or fail closed.

        ``supported_locales`` describes technical availability.  The separate
        ``reliable_locales`` set represents reviewed content/policy/model
        support, so a technically available machine translation cannot be
        mistaken for a safe translation.
        """

        try:
            resolved_dimension = LocaleDimension(dimension)
        except ValueError as exc:
            raise LocaleContextError("LOCALE_DIMENSION_UNSUPPORTED") from exc

        supported = {_canonicalize_locale(value, "supported_locale") for value in supported_locales}
        reliable = {_canonicalize_locale(value, "reliable_locale") for value in reliable_locales}
        for candidate in self.candidates(resolved_dimension):
            if candidate in supported and candidate in reliable:
                return candidate
        raise LocaleContextError(f"{resolved_dimension.value.upper()}_UNAVAILABLE")

    def as_dict(self) -> dict[str, object]:
        """Return the transport shape used by the cross-language JSON contract."""

        return {
            "user_locale": self.user_locale,
            "content_locale": self.content_locale,
            "model_locale": self.model_locale,
            "policy_locale": self.policy_locale,
            "fallback_locales": list(self.fallback_locales),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> LocaleContext:
        """Parse the exact JSON contract without accepting silent extensions."""

        if not isinstance(payload, Mapping):
            raise LocaleContextError("LOCALE_CONTEXT_OBJECT_REQUIRED")
        keys = set(payload)
        if keys != _CONTEXT_FIELDS:
            missing = _CONTEXT_FIELDS - keys
            if missing:
                raise LocaleContextError("LOCALE_CONTEXT_FIELDS_REQUIRED")
            raise LocaleContextError("LOCALE_CONTEXT_FIELDS_UNSUPPORTED")

        fallback_locales = payload["fallback_locales"]
        if not isinstance(fallback_locales, (list, tuple)):
            raise LocaleContextError("fallback_locales_UNSUPPORTED")
        return cls(
            user_locale=payload["user_locale"],
            content_locale=payload["content_locale"],
            model_locale=payload["model_locale"],
            policy_locale=payload["policy_locale"],
            fallback_locales=fallback_locales,
        )
