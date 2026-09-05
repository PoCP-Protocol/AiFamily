import json
from pathlib import Path

import pytest

from backend.platform.localization import LocaleContext, LocaleContextError, LocaleDimension


def context(**overrides) -> LocaleContext:
    values = {
        "user_locale": "zh-CN",
        "content_locale": "zh-CN",
        "model_locale": "zh-CN",
        "policy_locale": "zh-CN",
        "fallback_locales": (),
    }
    values.update(overrides)
    return LocaleContext(**values)


def test_context_keeps_four_language_dimensions_separate() -> None:
    value = context(
        user_locale="en-us",
        content_locale="zh-CN",
        model_locale="en-US",
        policy_locale="en-GB",
    )

    assert value.locale_for(LocaleDimension.USER) == "en-US"
    assert value.locale_for("content_locale") == "zh-CN"
    assert value.model_locale == "en-US"
    assert value.policy_locale == "en-GB"


@pytest.mark.parametrize(
    "field", ("user_locale", "content_locale", "model_locale", "policy_locale")
)
def test_invalid_locale_is_rejected(field: str) -> None:
    with pytest.raises(LocaleContextError, match="UNSUPPORTED"):
        context(**{field: "not a locale"})


def test_fallback_order_is_explicit_and_deduplicated() -> None:
    value = context(fallback_locales=("en-us", "zh-CN", "en-US"))

    assert value.candidates(LocaleDimension.POLICY) == ("zh-CN", "en-US")


def test_fallback_string_is_rejected_instead_of_being_split_into_characters() -> None:
    with pytest.raises(LocaleContextError, match="fallback_locale_UNSUPPORTED"):
        context(fallback_locales="en-US")


def test_resolution_requires_reliable_translation_and_never_silently_falls_back() -> None:
    value = context(user_locale="fr-FR", fallback_locales=("en-US",))

    assert (
        value.resolve_reliable(
            LocaleDimension.USER,
            supported_locales=("en-US",),
            reliable_locales=("en-US",),
        )
        == "en-US"
    )

    with pytest.raises(LocaleContextError, match="USER_LOCALE_UNAVAILABLE"):
        value.resolve_reliable(
            LocaleDimension.USER,
            supported_locales=("fr-FR", "en-US"),
            reliable_locales=(),
        )


def test_transport_contract_matches_json_schema() -> None:
    schema = json.loads(
        (
            Path(__file__).resolve().parents[3] / "contracts/schemas/locale-context.schema.json"
        ).read_text(encoding="utf-8")
    )
    value = context(fallback_locales=("en-US",)).as_dict()

    assert schema["required"] == [
        "user_locale",
        "content_locale",
        "model_locale",
        "policy_locale",
        "fallback_locales",
    ]
    assert set(value) == set(schema["properties"])


def test_transport_contract_round_trips_without_dropping_locale_dimensions() -> None:
    original = context(fallback_locales=("en-US",))

    restored = LocaleContext.from_dict(original.as_dict())

    assert restored == original


def test_transport_contract_rejects_missing_and_unknown_fields() -> None:
    payload = context().as_dict()

    with pytest.raises(LocaleContextError, match="FIELDS_REQUIRED"):
        LocaleContext.from_dict(
            {key: value for key, value in payload.items() if key != "policy_locale"}
        )
    with pytest.raises(LocaleContextError, match="FIELDS_UNSUPPORTED"):
        LocaleContext.from_dict({**payload, "unexpected": "value"})
