"""Locale boundary primitives shared by API and AI runtime callers."""

from backend.platform.localization.catalog import (
    LocaleArtifactKind,
    LocaleCatalog,
    LocaleCatalogError,
    LocaleCoverageReport,
    LocaleReviewStatus,
    LocalizedArtifact,
)
from backend.platform.localization.context import (
    LocaleContext,
    LocaleContextError,
    LocaleDimension,
)
from backend.platform.localization.fastapi import (
    LocaleContextMiddleware,
    get_locale_context,
)

__all__ = [
    "LocaleArtifactKind",
    "LocaleCatalog",
    "LocaleCatalogError",
    "LocaleContext",
    "LocaleContextError",
    "LocaleCoverageReport",
    "LocaleContextMiddleware",
    "LocaleDimension",
    "LocaleReviewStatus",
    "LocalizedArtifact",
    "get_locale_context",
]
