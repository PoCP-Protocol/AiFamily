"""Errors raised by the fail-closed Human Gate."""

from __future__ import annotations


class HumanGateError(ValueError):
    """A policy, scope, lifecycle, or validation failure at the gate."""

    def __init__(self, code: str, detail: str | None = None) -> None:
        self.code = code
        message = detail or code
        super().__init__(f"{code}: {message}")


__all__ = ["HumanGateError"]
