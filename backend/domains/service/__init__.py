"""SERVICE domain — 预约子链 (ServiceProvider → ServiceOffering →
AvailabilitySlot → BookingRequest → ServiceRecord).

Brought forward from Batch 5 to Batch 2 by
`docs/11_delivery/migration/MIGRATION_PLAN_V2.md` §3: the booking chain is the
one *already end-to-end verified* paid loop (UI-19 → UI-21 → UI-24), and
"晚做等于让已验证价值悬空".

Layering (`docs/10_engineering/ENGINEERING_ARCHITECTURE.md`): `domain/` holds
invariants and knows nothing about FastAPI or SQLAlchemy; `application/` holds
Named Actions and read models over a repository Port; `infrastructure/` has the
two Port implementations; `api/` is the only layer that may speak HTTP.
"""
