import pytest

from backend.domains.product_intelligence.api.courseware_dependencies import (
    clear_courseware_gateway,
    get_courseware_gateway,
)


@pytest.mark.asyncio
async def test_courseware_gateway_dependency_fails_closed_when_unconfigured() -> None:
    clear_courseware_gateway()
    with pytest.raises(RuntimeError, match="not configured"):
        await get_courseware_gateway(object())  # type: ignore[arg-type]
