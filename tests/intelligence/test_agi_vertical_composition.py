from types import SimpleNamespace

from backend.intelligence.agi_vertical_composition import (
    VerticalFamilyGrowthComposition,
    install_vertical_family_growth_runtime,
)
from backend.intelligence.agi_vertical_runtime import EvaluationLedger, VerticalFamilyGrowthRuntime


class _Port:
    async def read(self, **kwargs):
        raise AssertionError("not called")


def test_composition_builds_one_explicit_runtime() -> None:
    composition = VerticalFamilyGrowthComposition(
        gateway=_Port(),
        context=_Port(),
        knowledge=_Port(),
        feedback=_Port(),
        ledger=EvaluationLedger(),
    )
    runtime = composition.build_runtime()
    assert isinstance(runtime, VerticalFamilyGrowthRuntime)


def test_installer_keeps_runtime_identity_on_application_state() -> None:
    application = SimpleNamespace(state=SimpleNamespace())
    runtime = VerticalFamilyGrowthComposition(
        gateway=_Port(),
        context=_Port(),
        knowledge=_Port(),
        feedback=_Port(),
        ledger=EvaluationLedger(),
    ).build_runtime()

    install_vertical_family_growth_runtime(application, runtime)

    assert application.state.vertical_family_growth_runtime is runtime
