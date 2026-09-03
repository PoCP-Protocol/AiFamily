"""The adapter contract.

Kept to a single method returning raw text on purpose. Every guarantee the
platform depends on — admission, timeout accounting, JSON parsing, schema
validation, provenance, the attempt ledger — is applied by the gateway to *all*
adapters uniformly. An adapter that could return an already-parsed draft could
also return one that skipped validation, and then the guarantee would be
per-adapter discipline rather than a property of the system.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from backend.intelligence.model_gateway.contracts import StructuredRequest, TokenUsage


@dataclass(frozen=True, slots=True)
class ProviderResponse:
    """What an adapter returns: unparsed text plus reported model identity.

    `text` is raw and may be malformed — that is expected, and deciding what to do
    about it is the gateway's call (it fails closed; it never forwards the text).

    `model` / `model_version` are what the *provider* said it used, which can
    differ from what was requested when a vendor silently aliases or upgrades a
    model. Provenance must record what actually answered, so the reported values
    win over the configured ones.
    """

    text: str
    model: str
    model_version: str
    token_usage: TokenUsage | None = None
    confidence: float | None = None


class ProviderAdapter(Protocol):
    """A single vendor endpoint."""

    provider_id: str
    supported_modalities: frozenset[str]

    async def invoke(
        self, request: StructuredRequest, *, timeout_seconds: float
    ) -> ProviderResponse:
        """Perform one attempt.

        Must raise `ModelGatewayError` — never a vendor SDK exception, never a
        bare `TimeoutError` — so that the gateway's failure classification stays
        exhaustive and provider payloads never reach a log through an exception
        string. Must honour `timeout_seconds`; the gateway also enforces its own
        outer timeout, but an adapter that ignores the parameter would hold a
        connection open past the deadline.
        """
        ...
