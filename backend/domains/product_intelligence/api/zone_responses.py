"""API response DTOs for the Product Zone governance endpoints. Same
convention as `api/responses.py`: this domain's `ProductZoneAssessment`
entity has no field that must be hidden from the API, so the entity is
reused directly as the response model rather than a separate DTO.
"""
from __future__ import annotations

from ..domain.zone_entities import ProductZoneAssessment

ZoneAssessmentResponse = ProductZoneAssessment
