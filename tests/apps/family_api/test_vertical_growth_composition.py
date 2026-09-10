from backend.apps.family_api.main import create_app
from backend.intelligence.agi_vertical_runtime import EvaluationLedger, VerticalFamilyGrowthRuntime


class _Port:
    async def read(self, **kwargs):
        raise AssertionError("not called")


def test_create_app_installs_explicit_vertical_runtime() -> None:
    runtime = VerticalFamilyGrowthRuntime(
        gateway=_Port(),
        context=_Port(),
        knowledge=_Port(),
        feedback=_Port(),
        ledger=EvaluationLedger(),
    )

    app = create_app(vertical_family_growth_runtime=runtime)

    assert app.state.vertical_family_growth_runtime is runtime


def test_create_app_exposes_vertical_growth_draft_route() -> None:
    app = create_app()

    assert "/families/{family_id}/growth/ai-drafts" in app.openapi()["paths"]
