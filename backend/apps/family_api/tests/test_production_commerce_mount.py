
from backend.apps.family_api.main import create_app
from backend.apps.family_api.production_commerce_context import ProductionCommerceReadContext


class _Resolver:
    async def resolve(self, **kwargs):
        return ProductionCommerceReadContext("a", "t", kwargs["family_id"], "c", "k")


async def _repo():
    class Repo:
        async def list_products(self, *, tenant_id):
            return []

    return Repo()


def test_production_commerce_is_opt_in_at_composition_root() -> None:
    app = create_app(
        production_commerce_context_resolver=_Resolver(),
        production_commerce_repository_factory=_repo,
    )
    assert "/families/{family_id}/commerce/products" in app.openapi()["paths"]


def test_default_app_does_not_mount_production_commerce(monkeypatch) -> None:
    monkeypatch.setenv("AIFAMILY_ENV", "production")
    app = create_app()
    assert "/families/{family_id}/commerce/products" not in app.openapi()["paths"]
