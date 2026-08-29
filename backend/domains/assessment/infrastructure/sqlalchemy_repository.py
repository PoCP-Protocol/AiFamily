"""Real repository — asyncpg/SQLAlchemy Core against the EXISTING PostgreSQL
schema owned by NestJS SQL migrations
(`database/migrations/0040_ui02_versioned_family_assessment.sql`,
`0041_ui03_growth_hypothesis_confirmation.sql`). Per migration plan section 5
("single migration owner per schema... Pre-existing schemas get an Alembic
baseline revision rather than being rewritten from scratch"), this file does
NOT create a new schema or new migrations — it reads/writes the tables the
NestJS service already owns, using raw parameterized SQL that mirrors
`assessment.service.ts` / `growth-hypothesis.service.ts` statement-by-statement.
Alembic ownership of this schema only begins at cutover (`NEST_ACTIVE →
PYTHON_READY → CUTOVER`), not before — this repository is the "PYTHON_READY"
stage: correct against the existing schema, not yet the sole writer.
"""
from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncConnection

from ..application.ports import AssessmentRepositoryPort
from ..domain.entities import AssessmentResponse, AssessmentSession, GrowthHypothesisEvidence
from ..domain.errors import AssessmentConflictError, AssessmentForbiddenError, AssessmentNotFoundError
from ..domain.permission_policy import CREATE_FAMILY_ACTION, FAMILY_MANAGE_ROLES
from ..domain.value_objects import AssessmentSessionStatus, AssessmentTool, AssessmentToolBoundary, AssessmentToolItem


def _decode_jsonb(raw):
    """SQLAlchemy `text()` queries with asyncpg return jsonb columns as raw
    JSON text (not pre-decoded, unlike some ORM-mapped column types) — but
    a jsonb scalar string value like `"COMMUNICATION"` round-trips through
    Postgres as the bare text `COMMUNICATION` (asyncpg strips the JSON
    string quoting for jsonb scalars in some codec paths), which is not
    valid JSON on its own. Try strict JSON decode first (covers objects/
    arrays/numbers/booleans); fall back to the raw string for bare jsonb
    string scalars. Used for every jsonb column this repository reads.
    """
    if not isinstance(raw, str):
        return raw
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def _map_tool_row(row) -> AssessmentTool:
    item_schema = _decode_jsonb(row.item_schema)
    boundary = _decode_jsonb(row.boundary)
    return AssessmentTool(
        tool_ref=row.tool_ref,
        version_no=row.version_no,
        title=row.title,
        purpose=row.purpose,
        schema_ref=row.schema_ref,
        items=[AssessmentToolItem(**item) for item in item_schema["items"]],
        boundary=AssessmentToolBoundary(**boundary),
    )


def _map_response_row(row) -> AssessmentResponse:
    value = _decode_jsonb(row.response_value)
    return AssessmentResponse(
        assessment_response_id=str(row.assessment_response_id),
        item_ref=row.item_ref,
        response_type=row.response_type,
        response_value=value,
        revision=row.revision,
        captured_at=row.captured_at,
        visibility=row.visibility,
    )


class SqlAlchemyAssessmentRepository(AssessmentRepositoryPort):
    """One instance per request/transaction — mirrors the NestJS pattern of
    `this.repository.withTransaction(async (client) => {...})`: the caller
    (FastAPI dependency) is responsible for opening/committing/rolling back
    `connection`, this class only issues statements against it.
    """

    def __init__(self, connection: AsyncConnection):
        self._connection = connection

    async def assert_tenant_family_scope(self, tenant_id: str, family_id: str, actor_id: str) -> None:
        # Port of AssessmentService.assertScope: the tenant_family_bindings
        # check, followed by assertFamilyManagePermission (family-permission.ts).
        result = await self._connection.execute(
            text(
                """
                select 1 from tenant_family_bindings
                where tenant_id=:tenant_id and family_id=:family_id and status='ACTIVE'
                  and effective_from<=now() and (effective_to is null or effective_to>now())
                limit 1
                """
            ),
            {"tenant_id": tenant_id, "family_id": family_id},
        )
        if result.first() is None:
            raise AssessmentForbiddenError("tenant_family_scope_denied")

        await self._assert_family_manage_permission(family_id, actor_id)

    async def _assert_family_manage_permission(self, family_id: str, actor_id: str) -> None:
        # Port of `assertFamilyManagePermission` (family-permission.ts).
        # Pass condition 1 (legacy): actor is the audited SUCCESS actor of
        # this family's `CreateFamily` action.
        audit = await self._connection.execute(
            text(
                """
                select 1 from audit_logs
                where family_id=:family_id and actor_id=:actor_id and action_name=:action and result='SUCCESS'
                limit 1
                """
            ),
            {"family_id": family_id, "actor_id": actor_id, "action": CREATE_FAMILY_ACTION},
        )
        if audit.first() is not None:
            return

        # Pass condition 2 (tenancy): actor (a trusted personId, per
        # FamilyScopeGuard) holds an ACTIVE OWNER_GUARDIAN/GUARDIAN
        # family_membership for this family. `person_id::text = :actor_id`
        # mirrors the Nest cast — a non-UUID legacy actor_id simply fails to
        # match instead of erroring.
        membership = await self._connection.execute(
            text(
                """
                select 1 from family_memberships
                where family_id=:family_id and person_id::text=:actor_id and status='ACTIVE'
                  and role in :roles
                limit 1
                """
            ).bindparams(bindparam("roles", expanding=True)),
            {"family_id": family_id, "actor_id": actor_id, "roles": list(FAMILY_MANAGE_ROLES)},
        )
        if membership.first() is not None:
            return

        raise AssessmentForbiddenError("actor_has_family_manage_permission")

    async def assert_subject_consent(self, family_id: str, subject_person_id: str, purpose: str) -> None:
        result = await self._connection.execute(
            text(
                """
                select 1 from persons p
                where p.person_id=:subject_id and p.family_id=:family_id and p.person_type='CHILD'
                  and exists(
                    select 1 from consents c
                    where c.family_id=p.family_id and c.subject_person_id=p.person_id
                      and c.purpose=:purpose and c.status='GRANTED'
                  )
                limit 1
                """
            ),
            {"subject_id": subject_person_id, "family_id": family_id, "purpose": purpose},
        )
        if result.first() is None:
            raise AssessmentForbiddenError("assessment_subject_or_consent_unavailable")

    async def load_active_tool(self, tool_ref: str) -> AssessmentTool | None:
        result = await self._connection.execute(
            text(
                """
                select tool_ref,version_no,title,purpose,evidence_level,schema_ref,item_schema,boundary
                from family_assessment_tools
                where tool_ref=:tool_ref and status='ACTIVE' and admission_status='ADMITTED'
                  and effective_from<=now() and (effective_to is null or effective_to>now())
                order by version_no desc limit 1
                """
            ),
            {"tool_ref": tool_ref},
        )
        row = result.first()
        return _map_tool_row(row) if row else None

    async def load_tool_version(self, tool_ref: str, version_no: int) -> AssessmentTool:
        result = await self._connection.execute(
            text(
                "select tool_ref,version_no,title,purpose,evidence_level,schema_ref,item_schema,boundary "
                "from family_assessment_tools where tool_ref=:tool_ref and version_no=:version_no"
            ),
            {"tool_ref": tool_ref, "version_no": version_no},
        )
        row = result.first()
        if row is None:
            raise AssessmentNotFoundError("assessment_tool_version_not_found")
        return _map_tool_row(row)

    async def load_assessable_subjects(self, family_id: str) -> list[dict]:
        result = await self._connection.execute(
            text(
                """
                select p.person_id, p.display_name,
                       exists(
                         select 1 from consents c where c.family_id=p.family_id
                           and c.subject_person_id=p.person_id and c.purpose='ASSESSMENT' and c.status='GRANTED'
                       ) consent_granted
                from persons p
                where p.family_id=:family_id and p.person_type='CHILD'
                order by p.created_at, p.person_id
                """
            ),
            {"family_id": family_id},
        )
        return [
            {"person_id": str(row.person_id), "display_name": row.display_name, "consent_granted": row.consent_granted}
            for row in result
        ]

    async def load_recent_sessions(self, tenant_id: str, family_id: str, limit: int = 10) -> list[AssessmentSession]:
        result = await self._connection.execute(
            text(
                """
                select assessment_session_id from family_assessment_sessions
                where tenant_id=:tenant_id and family_id=:family_id
                order by updated_at desc, assessment_session_id desc limit :limit
                """
            ),
            {"tenant_id": tenant_id, "family_id": family_id, "limit": limit},
        )
        return [await self.load_session(family_id, str(row.assessment_session_id)) for row in result]

    async def load_session(self, family_id: str, session_id: str) -> AssessmentSession:
        result = await self._connection.execute(
            text(
                """
                select assessment_session_id,family_id,subject_person_id,tool_ref,tool_version,status,
                       started_at,submitted_at,row_version
                from family_assessment_sessions where assessment_session_id=:session_id and family_id=:family_id
                """
            ),
            {"session_id": session_id, "family_id": family_id},
        )
        row = result.first()
        if row is None:
            raise AssessmentNotFoundError("assessment_session_not_found")
        return AssessmentSession(
            assessment_session_id=str(row.assessment_session_id),
            family_id=str(row.family_id),
            subject_person_id=str(row.subject_person_id),
            tool_ref=row.tool_ref,
            tool_version=row.tool_version,
            status=AssessmentSessionStatus(row.status),
            started_at=row.started_at,
            submitted_at=row.submitted_at,
            row_version=row.row_version,
            responses=await self._load_responses(session_id),
        )

    async def load_session_for_update(self, family_id: str, tenant_id: str, session_id: str) -> AssessmentSession:
        # Port of loadSessionRowForUpdate — `for update` row lock; caller's
        # transaction must remain open for the lock to hold, same as the
        # NestJS withTransaction block.
        result = await self._connection.execute(
            text(
                """
                select status,subject_person_id,tool_ref,tool_version
                from family_assessment_sessions
                where assessment_session_id=:session_id and family_id=:family_id and tenant_id=:tenant_id
                for update
                """
            ),
            {"session_id": session_id, "family_id": family_id, "tenant_id": tenant_id},
        )
        if result.first() is None:
            raise AssessmentNotFoundError("assessment_session_not_found")
        return await self.load_session(family_id, session_id)

    async def find_in_progress_session(self, tenant_id, family_id, subject_person_id, tool_ref, tool_version) -> str | None:
        result = await self._connection.execute(
            text(
                """
                select assessment_session_id from family_assessment_sessions
                where tenant_id=:tenant_id and family_id=:family_id and subject_person_id=:subject_id
                  and tool_ref=:tool_ref and tool_version=:tool_version and status='IN_PROGRESS'
                order by updated_at desc limit 1 for update
                """
            ),
            {
                "tenant_id": tenant_id,
                "family_id": family_id,
                "subject_id": subject_person_id,
                "tool_ref": tool_ref,
                "tool_version": tool_version,
            },
        )
        row = result.first()
        return str(row.assessment_session_id) if row else None

    async def insert_session(self, tenant_id, family_id, subject_person_id, tool_ref, tool_version, started_by) -> str:
        result = await self._connection.execute(
            text(
                """
                insert into family_assessment_sessions(tenant_id,family_id,subject_person_id,tool_ref,tool_version,started_by_person_id)
                values (:tenant_id,:family_id,:subject_id,:tool_ref,:tool_version,:started_by)
                returning assessment_session_id
                """
            ),
            {
                "tenant_id": tenant_id,
                "family_id": family_id,
                "subject_id": subject_person_id,
                "tool_ref": tool_ref,
                "tool_version": tool_version,
                "started_by": started_by,
            },
        )
        return str(result.first().assessment_session_id)

    async def upsert_response(self, session_id, item_ref, response_type, response_value, actor_id) -> None:
        previous = await self._connection.execute(
            text(
                "select revision from family_assessment_responses "
                "where assessment_session_id=:session_id and item_ref=:item_ref and is_current=true for update"
            ),
            {"session_id": session_id, "item_ref": item_ref},
        )
        previous_row = previous.first()
        await self._connection.execute(
            text(
                "update family_assessment_responses set is_current=false,superseded_at=now() "
                "where assessment_session_id=:session_id and item_ref=:item_ref and is_current=true"
            ),
            {"session_id": session_id, "item_ref": item_ref},
        )
        await self._connection.execute(
            text(
                """
                insert into family_assessment_responses(assessment_session_id,item_ref,response_type,response_value,author_person_id,revision)
                values (:session_id,:item_ref,:response_type,cast(:response_value as jsonb),:actor_id,:revision)
                """
            ),
            {
                "session_id": session_id,
                "item_ref": item_ref,
                "response_type": response_type,
                "response_value": json.dumps(response_value),
                "actor_id": actor_id,
                "revision": (previous_row.revision if previous_row else 0) + 1,
            },
        )
        await self._connection.execute(
            text("update family_assessment_sessions set row_version=row_version+1,updated_at=now() where assessment_session_id=:session_id"),
            {"session_id": session_id},
        )

    async def mark_session_submitted(self, session_id: str) -> None:
        await self._connection.execute(
            text(
                "update family_assessment_sessions set status='SUBMITTED',submitted_at=now(),"
                "row_version=row_version+1,updated_at=now() where assessment_session_id=:session_id"
            ),
            {"session_id": session_id},
        )

    async def insert_assessment_evidence(self, family_id: str, session_id: str, payload: dict) -> str:
        result = await self._connection.execute(
            text(
                """
                insert into evidence_records(family_id,evidence_type,source_ref,payload,observed_at,source,evidence_level)
                values (:family_id,'ASSESSMENT_RESPONSE_SET',:session_id,cast(:payload as jsonb),now(),'PARENT','E1')
                returning evidence_id
                """
            ),
            {"family_id": family_id, "session_id": session_id, "payload": json.dumps(payload)},
        )
        return str(result.first().evidence_id)

    async def tenant_allows_page(self, tenant_id: str, page_id: str) -> bool:
        result = await self._connection.execute(
            text(
                "select allowed_pages from tenant_policy_profiles where tenant_id=:tenant_id and status='ACTIVE' "
                "order by created_at desc limit 1"
            ),
            {"tenant_id": tenant_id},
        )
        row = result.first()
        allowed_pages = row.allowed_pages if row else None
        return page_id in (allowed_pages or [])

    async def lock_operation(self, tenant_id: str, family_id: str, action: str, idempotency_key: str) -> None:
        await self._connection.execute(
            text("select pg_advisory_xact_lock(hashtextextended(:lock_key,0))"),
            {"lock_key": f"{tenant_id}:{family_id}:{action}:{idempotency_key}"},
        )

    async def load_operation_replay(self, tenant_id, family_id, action, idempotency_key, request_hash) -> dict | None:
        result = await self._connection.execute(
            text(
                "select request_hash,response_body from family_assessment_operations "
                "where tenant_id=:tenant_id and family_id=:family_id and action_name=:action and idempotency_key=:key"
            ),
            {"tenant_id": tenant_id, "family_id": family_id, "action": action, "key": idempotency_key},
        )
        row = result.first()
        if row is None:
            return None
        if row.request_hash != request_hash:
            raise AssessmentConflictError("idempotency_key_payload_mismatch")
        body = _decode_jsonb(row.response_body)
        return body

    async def persist_operation(self, tenant_id, family_id, session_id, actor_id, action, request_hash, receipt, correlation_id, idempotency_key) -> None:
        await self._connection.execute(
            text(
                """
                insert into family_assessment_operations(tenant_id,family_id,assessment_session_id,action_name,actor_person_id,idempotency_key,request_hash,response_body,correlation_id)
                values (:tenant_id,:family_id,:session_id,:action,:actor_id,:idempotency_key,:request_hash,cast(:receipt as jsonb),:correlation_id)
                """
            ),
            {
                "tenant_id": tenant_id,
                "family_id": family_id,
                "session_id": session_id,
                "action": action,
                "actor_id": actor_id,
                "idempotency_key": idempotency_key,
                "request_hash": request_hash,
                "receipt": json.dumps(receipt),
                "correlation_id": correlation_id,
            },
        )

    async def write_audit_and_outbox(self, family_id, actor_id, session_id, action, event_name, receipt, correlation_id, idempotency_key, source) -> None:
        await self._connection.execute(
            text(
                """
                insert into audit_logs(family_id,actor_type,actor_id,action_name,resource_type,resource_id,correlation_id,idempotency_key,result,metadata)
                values (:family_id,'PERSON',:actor_id,:action,'ASSESSMENT_SESSION',:session_id,:correlation_id,:idempotency_key,'SUCCESS',cast(:metadata as jsonb))
                """
            ),
            {
                "family_id": family_id,
                "actor_id": actor_id,
                "action": action,
                "session_id": session_id,
                "correlation_id": correlation_id,
                "idempotency_key": idempotency_key,
                "metadata": json.dumps(
                    {
                        "source": source,
                        "tool_ref": receipt["session"]["tool_ref"],
                        "tool_version": receipt["session"]["tool_version"],
                        "boundary": receipt["boundary"],
                    }
                ),
            },
        )
        await self._connection.execute(
            text(
                """
                insert into outbox_events(aggregate_type,aggregate_id,event_name,event_version,event_id,correlation_id,payload,occurred_at)
                values ('ASSESSMENT_SESSION',:session_id,:event_name,1,gen_random_uuid(),:correlation_id,cast(:payload as jsonb),now())
                """
            ),
            {
                "session_id": session_id,
                "event_name": event_name,
                "correlation_id": correlation_id,
                "payload": json.dumps(
                    {
                        "family_id": family_id,
                        "assessment_session_id": session_id,
                        "status": receipt["session"]["status"],
                        "tool_ref": receipt["session"]["tool_ref"],
                        "tool_version": receipt["session"]["tool_version"],
                        "evidence_id": receipt.get("evidence_id"),
                        "boundary": receipt["boundary"],
                    }
                ),
            },
        )

    async def load_hypothesis_evidence(self, family_id, tenant_id, session_id=None) -> GrowthHypothesisEvidence | None:
        result = await self._connection.execute(
            text(
                """
                select s.assessment_session_id,s.subject_person_id,p.display_name subject_display_name,s.submitted_at,
                       s.tool_ref,s.tool_version,
                       r.assessment_response_id,r.response_value #>> '{}' focus_ref,e.evidence_id assessment_evidence_id,
                       nt.need_type_ref,nt.version_no need_type_version,nt.title,nt.description,nt.required_capability_keys,
                       jsonb_agg(jsonb_build_object('item_ref',ar.item_ref,'response_type',ar.response_type,'response_value',ar.response_value) order by ar.item_ref) response_set
                from family_assessment_sessions s
                join persons p on p.person_id=s.subject_person_id and p.family_id=s.family_id
                join family_assessment_responses r on r.assessment_session_id=s.assessment_session_id and r.item_ref='FOCUS' and r.is_current=true
                join family_assessment_responses ar on ar.assessment_session_id=s.assessment_session_id and ar.is_current=true
                join evidence_records e on e.family_id=s.family_id and e.source_ref=s.assessment_session_id::text and e.evidence_type='ASSESSMENT_RESPONSE_SET'
                join family_need_types nt on nt.source_focus_ref=(r.response_value #>> '{}') and nt.status='ACTIVE' and nt.admission_status='ADMITTED'
                     and nt.effective_from<=now() and (nt.effective_to is null or nt.effective_to>now())
                where s.family_id=:family_id and s.tenant_id=:tenant_id and s.status='SUBMITTED'
                  and (cast(:session_id as uuid) is null or s.assessment_session_id=cast(:session_id as uuid))
                group by s.assessment_session_id,s.subject_person_id,p.display_name,s.submitted_at,s.tool_ref,s.tool_version,
                         r.assessment_response_id,r.response_value,e.evidence_id,nt.need_type_ref,nt.version_no,nt.title,nt.description,nt.required_capability_keys
                order by s.submitted_at desc,nt.version_no desc,e.created_at desc limit 1
                """
            ),
            {"family_id": family_id, "tenant_id": tenant_id, "session_id": session_id},
        )
        row = result.first()
        if row is None:
            return None
        response_set = _decode_jsonb(row.response_set)
        return GrowthHypothesisEvidence(
            assessment_session_id=str(row.assessment_session_id),
            subject_person_id=str(row.subject_person_id),
            subject_display_name=row.subject_display_name,
            submitted_at=row.submitted_at,
            tool_ref=row.tool_ref,
            tool_version=row.tool_version,
            assessment_response_id=str(row.assessment_response_id),
            focus_ref=row.focus_ref,
            assessment_evidence_id=str(row.assessment_evidence_id),
            need_type_ref=row.need_type_ref,
            need_type_version=row.need_type_version,
            title=row.title,
            description=row.description,
            required_capability_keys=list(row.required_capability_keys),
            response_set=response_set,
        )

    async def load_or_create_growth_intent(
        self, *, family_id, subject_person_id, need_type, goal_text, required_capability_keys, confirmed_by, source_ref, evidence_refs
    ) -> dict:
        existing = await self._connection.execute(
            text(
                "select intent_id,need_type,status,required_capability_keys,evidence_refs,boundary "
                "from growth_intents where family_id=:family_id and source_type='ASSESSMENT_HYPOTHESIS' and source_ref=:source_ref limit 1 for update"
            ),
            {"family_id": family_id, "source_ref": source_ref},
        )
        row = existing.first()
        if row is not None:
            return _map_intent_row(row)

        inserted = await self._connection.execute(
            text(
                """
                insert into growth_intents(family_id,subject_person_id,signal_ref,need_type,goal_text,required_capability_keys,status,confirmed_by,source_type,source_ref,evidence_refs,boundary)
                values (:family_id,:subject_id,null,:need_type,:goal_text,:capability_keys,'OPEN',:confirmed_by,'ASSESSMENT_HYPOTHESIS',:source_ref,:evidence_refs,'HUMAN_CONFIRMED_INTENT_NOT_OUTCOME')
                returning intent_id,need_type,status,required_capability_keys,evidence_refs,boundary
                """
            ),
            {
                "family_id": family_id,
                "subject_id": subject_person_id,
                "need_type": need_type,
                "goal_text": goal_text,
                "capability_keys": required_capability_keys,
                "confirmed_by": confirmed_by,
                "source_ref": source_ref,
                "evidence_refs": evidence_refs,
            },
        )
        return _map_intent_row(inserted.first())

    async def lock_hypothesis_decision(self, tenant_id: str, family_id: str, hypothesis_ref: str) -> None:
        await self._connection.execute(
            text("select pg_advisory_xact_lock(hashtextextended(:lock_key,0))"),
            {"lock_key": f"{tenant_id}:{family_id}:{hypothesis_ref}"},
        )

    async def load_hypothesis_decision_replay(self, tenant_id, family_id, decision_type, idempotency_key) -> dict | None:
        result = await self._connection.execute(
            text(
                "select request_hash,response_body from family_growth_hypothesis_decisions "
                "where tenant_id=:tenant_id and family_id=:family_id and decision_type=:decision_type and idempotency_key=:key"
            ),
            {"tenant_id": tenant_id, "family_id": family_id, "decision_type": decision_type, "key": idempotency_key},
        )
        row = result.first()
        if row is None:
            return None
        body = _decode_jsonb(row.response_body)
        return {"request_hash": row.request_hash, "response_body": body}

    async def persist_hypothesis_decision(
        self, *, tenant_id, family_id, session_id, hypothesis_ref, decision_type, actor_id, intent_id, idempotency_key, request_hash, receipt, correlation_id
    ) -> None:
        await self._connection.execute(
            text(
                """
                insert into family_growth_hypothesis_decisions(tenant_id,family_id,assessment_session_id,hypothesis_ref,decision_type,actor_person_id,intent_id,idempotency_key,request_hash,response_body,correlation_id)
                values (:tenant_id,:family_id,:session_id,:hypothesis_ref,:decision_type,:actor_id,:intent_id,:idempotency_key,:request_hash,cast(:receipt as jsonb),:correlation_id)
                """
            ),
            {
                "tenant_id": tenant_id,
                "family_id": family_id,
                "session_id": session_id,
                "hypothesis_ref": hypothesis_ref,
                "decision_type": decision_type,
                "actor_id": actor_id,
                "intent_id": intent_id,
                "idempotency_key": idempotency_key,
                "request_hash": request_hash,
                "receipt": json.dumps(receipt),
                "correlation_id": correlation_id,
            },
        )

    async def _load_responses(self, session_id: str) -> list[AssessmentResponse]:
        result = await self._connection.execute(
            text(
                "select assessment_response_id,item_ref,response_type,response_value,revision,captured_at,visibility "
                "from family_assessment_responses where assessment_session_id=:session_id and is_current=true "
                "order by captured_at,assessment_response_id"
            ),
            {"session_id": session_id},
        )
        return [_map_response_row(row) for row in result]


def _map_intent_row(row) -> dict:
    return {
        "intent_id": str(row.intent_id),
        "need_type": row.need_type,
        "status": row.status,
        "required_capability_keys": list(row.required_capability_keys),
        "evidence_refs": [str(ref) for ref in row.evidence_refs],
        "boundary": row.boundary,
    }
