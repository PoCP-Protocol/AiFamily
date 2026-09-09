"""Governed capability catalogue for AGI growth-path proposals."""

from .contracts import CapabilityOffer, CapabilityStatus
from .registry import CapabilityRegistry

__all__ = ["CapabilityOffer", "CapabilityRegistry", "CapabilityStatus"]
