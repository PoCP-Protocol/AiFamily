"""Minimal provider-neutral Agent Runtime execution loop."""

from __future__ import annotations

import inspect
from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from uuid import uuid4

from backend.intelligence.agent_runtime.authorization import AgentAuthorizer
from backend.intelligence.agent_runtime.contracts import (
    AgentAuthorization,
    AgentDefinition,
    AgentExecutionPort,
    AgentRun,
    AgentTask,
)
from backend.intelligence.experience.asset_digest import (
    family_experience_contract_asset_digest,
)
from backend.intelligence.experience.execution_materials import ExecutionMaterialError
from backend.intelligence.model_gateway.contracts import (
    KnowledgeExecutionPayload,
    PromptExecutionPlan,
    StructuredRequest,
)
from backend.intelligence.prompt_registry.registry import PromptRegistryError
from backend.intelligence.schema_registry.registry import SchemaRegistryError


class AgentRuntimeError(RuntimeError):
    """Raised when an execution result violates the Draft-only runtime boundary."""


class AgentRuntime:
    """Execute authorized tasks through an injected Model Gateway port.

    Registration and authorization are explicit.  Missing definitions or
    leases fail before constructing a model request, guaranteeing provider
    invocation count remains zero on denied paths.
    """

    def __init__(
        self,
        generation_port: AgentExecutionPort,
        definitions: Iterable[AgentDefinition] = (),
        *,
        authorizer: AgentAuthorizer | None = None,
        clock: Callable[[], datetime] | None = None,
        prompt_registry: object | None = None,
        schema_registry: object | None = None,
        execution_material_resolver: object | None = None,
        require_registries: bool = False,
    ) -> None:
        self._generation_port = generation_port
        self._definitions = {definition.agent_id: definition for definition in definitions}
        self._authorizer = authorizer if authorizer is not None else AgentAuthorizer()
        self._clock = clock if clock is not None else lambda: datetime.now(UTC)
        self._prompt_registry = prompt_registry
        self._schema_registry = schema_registry
        self._execution_material_resolver = execution_material_resolver
        if require_registries and (prompt_registry is None or schema_registry is None):
            raise AgentRuntimeError("prompt_and_schema_registries_required_for_production")
        if execution_material_resolver is not None and not callable(
            getattr(execution_material_resolver, "resolve", None)
        ):
            raise AgentRuntimeError("execution_material_resolver_invalid")

    def register(self, definition: AgentDefinition) -> None:
        if definition.agent_id in self._definitions:
            raise ValueError(f"agent definition already registered: {definition.agent_id}")
        self._definitions[definition.agent_id] = definition

    async def execute(self, task: AgentTask, authorization: AgentAuthorization | None) -> AgentRun:
        definition = self._definitions.get(task.agent_id)
        now = self._clock()
        self._authorizer.require(definition, authorization, task, now=now)
        output_schema = task.output_schema
        prompt_execution_plan = None
        if self._prompt_registry is not None or self._schema_registry is not None:
            if self._prompt_registry is None or self._schema_registry is None:
                raise AgentRuntimeError("prompt_and_schema_registries_are_required_together")
            try:
                prompt = await _resolve_registry(
                    self._prompt_registry,
                    task.use_case,
                    task.agent_id,
                    prompt_ref=task.prompt_ref,
                    version=task.prompt_version,
                    at=now,
                )
                schema = await _resolve_registry(
                    self._schema_registry,
                    task.use_case,
                    task.agent_id,
                    schema_ref=task.schema_ref,
                    version=task.schema_version,
                    at=now,
                )
            except (PromptRegistryError, SchemaRegistryError) as error:
                raise AgentRuntimeError("prompt_or_schema_resolution_failed") from error
            if prompt.status != "PUBLISHED" or schema.status != "PUBLISHED":
                raise AgentRuntimeError("prompt_or_schema_must_be_published")
            if prompt.output_schema_ref != schema.schema_ref:
                raise AgentRuntimeError("prompt_schema_binding_mismatch")
            output_schema = _jsonable(schema.json_schema)
            if not output_schema:
                raise AgentRuntimeError("published_schema_json_schema_required")
            if self._execution_material_resolver is not None:
                try:
                    materials = await _resolve_execution_materials(
                        self._execution_material_resolver,
                        system_policy_ref=prompt.system_policy_ref,
                        knowledge_refs=prompt.knowledge_refs,
                        use_case=task.use_case,
                        agent_id=task.agent_id,
                        at=now,
                    )
                except (ExecutionMaterialError, TypeError, ValueError) as error:
                    raise AgentRuntimeError("execution_material_resolution_failed") from error
                prompt_execution_plan = PromptExecutionPlan(
                    prompt_ref=prompt.prompt_ref,
                    prompt_version=prompt.version,
                    template=prompt.template,
                    system_policy_ref=prompt.system_policy_ref,
                    safety_policy_version=prompt.safety_policy_version,
                    knowledge_refs=prompt.knowledge_refs,
                    asset_digest=family_experience_contract_asset_digest(
                        prompt=prompt,
                        schema=schema,
                        system_policy=materials.system_policy,
                        knowledge=materials.knowledge,
                    ),
                    system_policy=materials.system_policy.content,
                    system_policy_digest=materials.system_policy.content_digest,
                    knowledge_materials=tuple(
                        KnowledgeExecutionPayload(
                            knowledge_ref=item.knowledge_ref,
                            content=item.content,
                            source_ref=item.source_ref,
                            license_ref=item.license_ref,
                            evidence_level=item.evidence_level,
                            content_digest=item.content_digest,
                        )
                        for item in materials.knowledge
                    ),
                    material_digest=materials.material_digest,
                )
        started = now
        request = StructuredRequest(
            use_case=task.use_case,
            prompt_version=task.prompt_version,
            schema_version=task.schema_version,
            data_class=task.data_class,
            payload=dict(task.payload),
            output_schema=output_schema,
            context_snapshot_ref=task.context_snapshot_ref,
            input_refs=task.input_refs,
            request_id=task.request_id,
            tenant_id=task.tenant_id,
            family_id=task.family_id,
            prompt_execution_plan=prompt_execution_plan,
        )
        draft = await self._generation_port.generate_structured(request)
        if draft.status != "DRAFT" or draft.may_mutate_business_state is not False:
            raise AgentRuntimeError("generation port returned a non-DRAFT or mutable result")
        return AgentRun(
            run_id=f"agent-run-{uuid4().hex}",
            request_id=task.request_id,
            agent_id=task.agent_id,
            tenant_id=task.tenant_id,
            family_id=task.family_id,
            use_case=task.use_case,
            draft=draft,
            started_at=started,
            completed_at=self._clock(),
        )


async def _resolve_registry(
    registry: object,
    use_case: str,
    agent_id: str,
    **kwargs: object,
) -> object:
    resolver = getattr(registry, "resolve", None)
    if not callable(resolver):
        raise AgentRuntimeError("prompt_or_schema_registry_invalid")
    resolved = resolver(use_case, agent_id, **kwargs)
    return await resolved if inspect.isawaitable(resolved) else resolved


async def _resolve_execution_materials(
    resolver: object,
    **kwargs: object,
) -> object:
    resolve = getattr(resolver, "resolve", None)
    if not callable(resolve):
        raise AgentRuntimeError("execution_material_resolver_invalid")
    resolved = resolve(**kwargs)
    return await resolved if inspect.isawaitable(resolved) else resolved


def _jsonable(value: object) -> object:
    if isinstance(value, dict) or hasattr(value, "items"):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list, set, frozenset)):
        return [_jsonable(item) for item in value]
    return value
