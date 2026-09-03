"""Reviewed, versioned locale artifacts keyed by canonical concepts.

The catalog is intentionally an in-memory boundary primitive for now.  It
stores no family data and never translates text.  A caller must ask for an
explicit artifact version; only ``REVIEWED`` entries can be returned, and
fallbacks come from the request's explicit :class:`LocaleContext`.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum

from backend.platform.localization.context import (
    LocaleContext,
    LocaleDimension,
    _canonicalize_locale,
)


class LocaleArtifactKind(StrEnum):
    """Kinds of text that require independent locale review."""

    PROMPT = "PROMPT"
    KNOWLEDGE = "KNOWLEDGE"
    ERROR_CODE = "ERROR_CODE"
    HUMAN_GATE = "HUMAN_GATE"


class LocaleReviewStatus(StrEnum):
    """Lifecycle status for a localized artifact version."""

    DRAFT = "DRAFT"
    REVIEWED = "REVIEWED"
    RETIRED = "RETIRED"


class LocaleCatalogError(ValueError):
    """Raised when a reviewed locale artifact cannot be resolved safely."""


@dataclass(frozen=True, slots=True)
class LocalizedArtifact:
    """A reviewed translation for one stable concept and artifact version."""

    concept_id: str
    artifact_kind: LocaleArtifactKind
    locale: str
    version: str
    text: str
    review_status: LocaleReviewStatus = LocaleReviewStatus.DRAFT

    def __post_init__(self) -> None:
        for field_name in ("concept_id", "version", "text"):
            value = getattr(self, field_name)
            if not isinstance(value, str):
                raise LocaleCatalogError("LOCALE_ARTIFACT_FIELDS_UNSUPPORTED")
            if not value:
                raise LocaleCatalogError("LOCALE_ARTIFACT_FIELDS_REQUIRED")
        object.__setattr__(self, "locale", _canonicalize_locale(self.locale, "locale"))
        try:
            object.__setattr__(self, "artifact_kind", LocaleArtifactKind(self.artifact_kind))
            object.__setattr__(self, "review_status", LocaleReviewStatus(self.review_status))
        except ValueError as exc:
            raise LocaleCatalogError("LOCALE_ARTIFACT_ENUM_UNSUPPORTED") from exc

    def as_dict(self) -> dict[str, str]:
        """Return the exact JSON contract shape used across runtimes."""

        return {
            "concept_id": self.concept_id,
            "artifact_kind": self.artifact_kind.value,
            "locale": self.locale,
            "version": self.version,
            "text": self.text,
            "review_status": self.review_status.value,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> LocalizedArtifact:
        """Parse one artifact while rejecting missing or unknown contract fields."""

        required = {
            "concept_id",
            "artifact_kind",
            "locale",
            "version",
            "text",
            "review_status",
        }
        if not isinstance(payload, Mapping):
            raise LocaleCatalogError("LOCALE_ARTIFACT_OBJECT_REQUIRED")
        keys = set(payload)
        if keys != required:
            if required - keys:
                raise LocaleCatalogError("LOCALE_ARTIFACT_FIELDS_REQUIRED")
            raise LocaleCatalogError("LOCALE_ARTIFACT_FIELDS_UNSUPPORTED")
        try:
            return cls(**payload)
        except TypeError as exc:
            raise LocaleCatalogError("LOCALE_ARTIFACT_FIELDS_UNSUPPORTED") from exc


@dataclass(frozen=True, slots=True)
class LocaleCoverageReport:
    """Deterministic coverage result for one versioned artifact set."""

    required_concepts: tuple[str, ...]
    required_locales: tuple[str, ...]
    missing: tuple[tuple[str, str], ...]

    @property
    def complete(self) -> bool:
        return not self.missing


class LocaleCatalog:
    """Resolve only reviewed artifacts through an explicit locale context."""

    def __init__(self, artifacts: Iterable[LocalizedArtifact] = ()) -> None:
        self._artifacts: dict[tuple[str, LocaleArtifactKind, str, str], LocalizedArtifact] = {}
        for artifact in artifacts:
            key = (artifact.concept_id, artifact.artifact_kind, artifact.locale, artifact.version)
            if key in self._artifacts:
                raise LocaleCatalogError("LOCALE_ARTIFACT_DUPLICATE")
            self._artifacts[key] = artifact

    def resolve(
        self,
        context: LocaleContext,
        dimension: LocaleDimension | str,
        *,
        concept_id: str,
        artifact_kind: LocaleArtifactKind,
        version: str,
    ) -> LocalizedArtifact:
        """Return a reviewed artifact or fail closed.

        The requested version is mandatory so model runs and human-review
        records never change meaning because a newer translation was added.
        """

        if not concept_id or not version:
            raise LocaleCatalogError("LOCALE_ARTIFACT_ID_AND_VERSION_REQUIRED")
        try:
            resolved_kind = LocaleArtifactKind(artifact_kind)
        except ValueError as exc:
            raise LocaleCatalogError("LOCALE_ARTIFACT_KIND_UNSUPPORTED") from exc

        for locale in context.candidates(dimension):
            artifact = self._artifacts.get((concept_id, resolved_kind, locale, version))
            if artifact and artifact.review_status is LocaleReviewStatus.REVIEWED:
                return artifact
        raise LocaleCatalogError("LOCALE_ARTIFACT_UNAVAILABLE")

    def __len__(self) -> int:
        return len(self._artifacts)

    def evaluate_coverage(
        self,
        *,
        concept_ids: Iterable[str],
        locales: Iterable[str],
        artifact_kind: LocaleArtifactKind,
        version: str,
    ) -> LocaleCoverageReport:
        """Check reviewed coverage without judging translation quality."""

        if not version:
            raise LocaleCatalogError("LOCALE_ARTIFACT_VERSION_REQUIRED")
        try:
            resolved_kind = LocaleArtifactKind(artifact_kind)
        except ValueError as exc:
            raise LocaleCatalogError("LOCALE_ARTIFACT_KIND_UNSUPPORTED") from exc

        required_concepts = tuple(dict.fromkeys(concept_ids))
        required_locales = tuple(
            dict.fromkeys(_canonicalize_locale(locale, "locale") for locale in locales)
        )
        missing = tuple(
            (concept_id, locale)
            for concept_id in required_concepts
            for locale in required_locales
            if (
                (artifact := self._artifacts.get((concept_id, resolved_kind, locale, version)))
                is None
                or artifact.review_status is not LocaleReviewStatus.REVIEWED
            )
        )
        return LocaleCoverageReport(required_concepts, required_locales, missing)


__all__ = [
    "LocaleArtifactKind",
    "LocaleCatalog",
    "LocaleCatalogError",
    "LocaleCoverageReport",
    "LocaleReviewStatus",
    "LocalizedArtifact",
]
