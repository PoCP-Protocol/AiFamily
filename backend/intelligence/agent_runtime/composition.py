"""Explicit composition helper for a governed Agent Runtime.

This factory is intentionally small: it loads the reviewed static Agent
definitions and requires both Prompt and Schema registries.  Identity,
consent, authorization leases, Model Gateway and transaction stores remain
explicit caller-owned dependencies; no permissive defaults are introduced.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from backend.intelligence.observability import TelemetrySink

from .authorization import AgentAuthorizer
from .context_bound import ContextBoundAgentRuntime
from .contracts import AgentExecutionPort
from .durable_runtime import DurableAgentRuntime
from .persistence import AgentRunPersistencePort
from .registry import AgentDefinitionRegistry
from .runtime import AgentRuntime


def build_agent_runtime(
    *,
    generation_port: AgentExecutionPort,
    registry_path: str | Path,
    prompt_registry: object,
    schema_registry: object,
    authorizer: AgentAuthorizer | None = None,
    clock: Callable[[], datetime] | None = None,
) -> AgentRuntime:
    """Build an explicit runtime from governed static and dynamic seams."""

    if not callable(getattr(prompt_registry, "resolve", None)) or not callable(
        getattr(schema_registry, "resolve", None)
    ):
        raise ValueError("prompt_and_schema_registries_required")
    definitions = AgentDefinitionRegistry.from_yaml(
        registry_path,
        runnable_only=True,
    ).all()
    return AgentRuntime(
        generation_port,
        definitions,
        authorizer=authorizer,
        clock=clock,
        prompt_registry=prompt_registry,
        schema_registry=schema_registry,
        require_registries=True,
    )


def build_durable_agent_runtime(
    *,
    generation_port: AgentExecutionPort,
    registry_path: str | Path,
    prompt_registry: object,
    schema_registry: object,
    run_store: AgentRunPersistencePort,
    authorizer: AgentAuthorizer | None = None,
    clock: Callable[[], datetime] | None = None,
    telemetry_sink: TelemetrySink | None = None,
) -> DurableAgentRuntime:
    """Build the production-shaped Agent Runtime with durable lifecycle state."""

    runtime = build_agent_runtime(
        generation_port=generation_port,
        registry_path=registry_path,
        prompt_registry=prompt_registry,
        schema_registry=schema_registry,
        authorizer=authorizer,
        clock=clock,
    )
    return DurableAgentRuntime(runtime, run_store, clock=clock, telemetry_sink=telemetry_sink)


def build_context_bound_agent_runtime(
    *,
    generation_port: AgentExecutionPort,
    registry_path: str | Path,
    prompt_registry: object,
    schema_registry: object,
    run_store: AgentRunPersistencePort,
    authorizer: AgentAuthorizer | None = None,
    clock: Callable[[], datetime] | None = None,
    telemetry_sink: TelemetrySink | None = None,
) -> ContextBoundAgentRuntime:
    """Build a durable Agent Runtime with an explicit ContextScope boundary."""

    return ContextBoundAgentRuntime(
        build_durable_agent_runtime(
            generation_port=generation_port,
            registry_path=registry_path,
            prompt_registry=prompt_registry,
            schema_registry=schema_registry,
            run_store=run_store,
            authorizer=authorizer,
            clock=clock,
            telemetry_sink=telemetry_sink,
        )
    )


__all__ = [
    "build_agent_runtime",
    "build_durable_agent_runtime",
    "build_context_bound_agent_runtime",
]
