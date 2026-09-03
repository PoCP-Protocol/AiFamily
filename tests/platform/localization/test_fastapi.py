from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from backend.platform.localization import LocaleContextMiddleware, get_locale_context


def app() -> FastAPI:
    application = FastAPI()
    application.add_middleware(LocaleContextMiddleware)

    @application.get("/public")
    async def public() -> dict[str, str]:
        return {"status": "ok"}

    @application.get("/principal/route")
    async def principal(context=Depends(get_locale_context)) -> dict[str, str]:
        return {
            "user_locale": context.user_locale,
            "content_locale": context.content_locale,
            "model_locale": context.model_locale,
            "policy_locale": context.policy_locale,
            "fallback": ",".join(context.fallback_locales),
        }

    return application


def test_locale_dependency_fails_closed_when_middleware_did_not_attach_context() -> None:
    application = FastAPI()

    @application.get("/route")
    async def route(context=Depends(get_locale_context)) -> dict[str, str]:
        return {"locale": context.user_locale}

    response = TestClient(application).get("/route")

    assert response.status_code == 400
    assert response.json() == {"detail": "LOCALE_CONTEXT_REQUIRED"}


def test_non_ai_route_remains_compatible_without_locale_headers() -> None:
    response = TestClient(app()).get("/public")

    assert response.status_code == 200


def test_ai_route_requires_all_four_locale_dimensions() -> None:
    response = TestClient(app()).get("/principal/route")

    assert response.status_code == 400
    assert response.json() == {"detail": "LOCALE_CONTEXT_REQUIRED"}


def test_ai_route_rejects_partial_locale_context() -> None:
    response = TestClient(app()).get(
        "/principal/route",
        headers={"X-User-Locale": "zh-CN"},
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "LOCALE_CONTEXT_INCOMPLETE"}


def test_fallback_header_without_locale_dimensions_is_rejected() -> None:
    response = TestClient(app()).get(
        "/public",
        headers={"X-Locale-Fallback": "en-US"},
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "LOCALE_CONTEXT_INCOMPLETE"}


def test_ai_route_attaches_normalized_context_and_explicit_fallbacks() -> None:
    response = TestClient(app()).get(
        "/principal/route",
        headers={
            "X-User-Locale": "en-us",
            "X-Content-Locale": "zh-CN",
            "X-Model-Locale": "en-US",
            "X-Policy-Locale": "en-GB",
            "X-Locale-Fallback": "zh-CN, en-US",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "user_locale": "en-US",
        "content_locale": "zh-CN",
        "model_locale": "en-US",
        "policy_locale": "en-GB",
        "fallback": "zh-CN,en-US",
    }


def test_ai_route_rejects_invalid_locale_without_silent_replacement() -> None:
    response = TestClient(app()).get(
        "/principal/route",
        headers={
            "X-User-Locale": "not a locale",
            "X-Content-Locale": "zh-CN",
            "X-Model-Locale": "en-US",
            "X-Policy-Locale": "en-GB",
        },
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "user_locale_UNSUPPORTED"}


def test_similar_unprotected_path_is_not_treated_as_an_ai_route() -> None:
    response = TestClient(app()).get("/principalist")

    assert response.status_code == 404
