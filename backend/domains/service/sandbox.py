"""Runnable DEV-only S4 scene: offering -> slot -> booking -> delivery receipt.

Run with::

    uv run uvicorn backend.domains.service.sandbox:app --port 8765

The sandbox is synthetic and has no external side effects.  It composes the
canonical Service commands and the confirmed-human-help handoff; it is not a
second service backend and must never be mounted in the production app.
"""

# ruff: noqa: E501 -- the embedded, dependency-free demo page is intentionally compact.

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import timedelta

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from backend.platform.audit.recorder import AuditRecorder
from backend.platform.consent.models import ConsentGrant, ConsentPurpose, ConsentStatus

from .application import commands, queries
from .application.context import ActionContext
from .application.handoff import HumanHelpHandoffReceipt, submit_confirmed_human_help
from .domain.entities import utcnow
from .infrastructure.fake_repository import FakeConsentQuery, FakeServiceRepository

TENANT = "sandbox-tenant"
FAMILY = "sandbox-family"
GUARDIAN = "sandbox-guardian"
CHILD = "sandbox-child"
CONSENT = "sandbox-service-consent"


def _context(*, key: str | None = None) -> ActionContext:
    return ActionContext(
        tenant_id=TENANT,
        family_id=FAMILY,
        actor_person_id=GUARDIAN,
        actor=f"guardian:{GUARDIAN}",
        correlation_id="s4-sandbox-scene",
        environment="DEV",
        idempotency_key=key,
    )


@dataclass
class SandboxState:
    repo: FakeServiceRepository
    consent: FakeConsentQuery
    recorder: AuditRecorder
    offering_id: str
    slot_id: str


async def _seed() -> SandboxState:
    repo = FakeServiceRepository()
    consent = FakeConsentQuery()
    recorder = AuditRecorder()
    consent.add(
        ConsentGrant(
            consent_id=CONSENT,
            subject_person_id=CHILD,
            guardian_person_id=GUARDIAN,
            purpose=ConsentPurpose.SERVICE,
            status=ConsentStatus.GRANTED,
            granted_at=utcnow(),
        )
    )
    ctx = _context()
    provider = await commands.register_service_provider(
        repo,
        ctx,
        recorder,
        provider_ref="SYNTHETIC_PARENT_COACH",
        display_name="合成家庭行动教练",
        provider_kind="TEACHER",
        qualification_status="ACTIVE",
        admission_status="ADMITTED",
        source_ref="synthetic:s4-sandbox",
        qualification_ref="synthetic-qualification",
    )
    offering = await commands.publish_service_offering(
        repo,
        ctx,
        recorder,
        provider_id=provider.provider_id,
        service_offering_ref="EVENING_START_SUPPORT_45",
        title="晚间学习平稳启动支持（45分钟）",
        admission_status="ADMITTED",
        source_ref="synthetic:s4-sandbox",
    )
    starts_at = utcnow() + timedelta(days=1)
    slot = await commands.open_availability_slot(
        repo,
        ctx,
        recorder,
        service_offering_id=offering.service_offering_id,
        availability_slot_ref="SYNTHETIC-TOMORROW-1930",
        starts_at=starts_at,
        ends_at=starts_at + timedelta(minutes=45),
        channel="VIDEO",
    )
    return SandboxState(
        repo,
        consent,
        recorder,
        offering.service_offering_id,
        slot.availability_slot_id,
    )


def build_sandbox_app() -> FastAPI:
    environment = os.getenv("AIFAMILY_ENV", "DEV").upper()
    if environment not in {"DEV", "TEST"}:
        raise RuntimeError("s4_service_sandbox_refuses_non_dev_environment")

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        application.state.s4 = await _seed()
        yield

    application = FastAPI(title="AiFamily S4 Synthetic Sandbox", lifespan=lifespan)

    @application.get("/", response_class=HTMLResponse)
    async def scene() -> str:
        return _HTML

    @application.get("/api/scene")
    async def read_scene():
        state: SandboxState = application.state.s4
        offerings = await queries.list_service_offerings(state.repo, tenant_id=TENANT)
        slots = await queries.list_availability_slots(
            state.repo, tenant_id=TENANT, service_offering_id=state.offering_id
        )
        return {
            "evidence_level": "SYNTHETIC_DEV_SANDBOX",
            "external_effect": False,
            "family_need": "希望晚间学习能平稳开始，减少催促冲突",
            "offerings": offerings,
            "slots": slots,
        }

    @application.post("/api/confirm-booking")
    async def confirm_booking():
        state: SandboxState = application.state.s4
        booking = await submit_confirmed_human_help(
            state.repo,
            _context(key="s4-sandbox-booking"),
            state.recorder,
            state.consent,
            receipt=HumanHelpHandoffReceipt(
                receipt_ref="sandbox-confirmed-need-001",
                tenant_id=TENANT,
                family_id=FAMILY,
                decision="HUMAN_HELP_CONFIRMED",
            ),
            service_offering_id=state.offering_id,
            availability_slot_id=state.slot_id,
            subject_person_id=CHILD,
            consent_ref=CONSENT,
        )
        confirmed, record = await commands.confirm_booking_request(
            state.repo,
            _context(),
            state.recorder,
            booking_request_id=booking.booking_request_id,
        )
        return {
            "evidence_level": "SYNTHETIC_DEV_SANDBOX",
            "external_effect": False,
            "booking": {
                "booking_request_id": confirmed.booking_request_id,
                "status": confirmed.status,
            },
            "delivery_record": {
                "booking_service_record_id": record.booking_service_record_id,
                "status": record.status,
            },
            "audit_actions": [event.action for event in state.recorder.all_events()],
        }

    return application


app = build_sandbox_app()


_HTML = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>AiFamily S4 DEV Sandbox</title><style>
body{margin:0;background:#f4f7fb;color:#172033;font:16px system-ui}.wrap{max-width:760px;margin:40px auto;padding:24px}
.badge{display:inline-block;padding:6px 10px;border-radius:999px;background:#fff0d9;color:#8a4b00;font-weight:700}
.card{margin-top:18px;padding:24px;border:1px solid #dbe3ef;border-radius:18px;background:white;box-shadow:0 8px 24px #24405b12}
h1{font-size:30px;margin:14px 0 8px}h2{font-size:21px}.muted{color:#667085}.row{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.item{padding:14px;border-radius:12px;background:#f7f9fc}button{margin-top:20px;width:100%;padding:14px;border:0;border-radius:12px;background:#2864dc;color:white;font-size:17px;font-weight:700;cursor:pointer}
button:disabled{background:#9eb4df}.result{margin-top:18px;padding:16px;border-radius:12px;background:#eaf7ef;color:#17633a;white-space:pre-wrap}
</style></head><body><main class="wrap"><span class="badge">DEV SYNTHETIC · 无外部副作用</span>
<h1>为晚间学习平稳启动请求真人帮助</h1><p class="muted" id="need">正在读取家庭明确需要…</p>
<section class="card"><h2 id="title">读取服务方案…</h2><div class="row"><div class="item"><b>服务人员</b><p id="provider">—</p></div><div class="item"><b>可选时间</b><p id="slot">—</p></div></div>
<button id="confirm" disabled>确认预约并查看交付记录</button><div id="result"></div></section></main>
<script>
const needEl=document.getElementById('need'),titleEl=document.getElementById('title');
const providerEl=document.getElementById('provider'),slotEl=document.getElementById('slot');
const confirmButton=document.getElementById('confirm'),resultEl=document.getElementById('result');
async function load(){const d=await fetch('/api/scene').then(r=>r.json());const o=d.offerings[0],s=d.slots[0];
needEl.textContent=d.family_need;titleEl.textContent=o.title;providerEl.textContent=o.provider_display_name;
slotEl.textContent=new Date(s.starts_at).toLocaleString()+' · '+s.channel;confirmButton.disabled=false}
confirmButton.addEventListener('click',async()=>{confirmButton.disabled=true;confirmButton.textContent='正在由人工确认…';
const d=await fetch('/api/confirm-booking',{method:'POST'}).then(r=>r.json());resultEl.className='result';
resultEl.textContent='预约状态：'+d.booking.status+'\\nDeliveryRecord：'+d.delivery_record.status+'\\nexternal_effect：'+d.external_effect;
confirmButton.textContent='已确认'});load();
</script>
</body></html>"""
