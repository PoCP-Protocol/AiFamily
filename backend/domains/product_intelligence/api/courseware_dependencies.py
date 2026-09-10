"""Explicit application wiring for the courseware Model Gateway."""

from __future__ import annotations

from fastapi import Request

from backend.intelligence.model_gateway.gateway import ModelGateway

_gateway: ModelGateway | None = None


def configure_courseware_gateway(gateway: ModelGateway | None) -> None:
    global _gateway
    if gateway is not None and not isinstance(gateway, ModelGateway):
        raise TypeError("courseware gateway must be a ModelGateway")
    _gateway = gateway


def clear_courseware_gateway() -> None:
    configure_courseware_gateway(None)


async def get_courseware_gateway(request: Request) -> ModelGateway:
    del request
    if _gateway is None:
        raise RuntimeError("courseware Model Gateway is not configured")
    return _gateway


__all__ = ["clear_courseware_gateway", "configure_courseware_gateway", "get_courseware_gateway"]
