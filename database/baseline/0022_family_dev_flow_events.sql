-- FAMILY-DEV-FLOW-001
-- DEV synthetic scenario state for supplied UI-02..UI-34 plus the researched
-- UI-35 support surface. This table records
-- test interactions only; it is not an order, booking, entitlement, community
-- publication, outcome, model output, or external-effect queue.

create table if not exists family_dev_flow_events (
  event_id uuid primary key default gen_random_uuid(),
  family_id uuid not null references families(family_id),
  actor_person_id uuid not null references persons(person_id),
  ui_id varchar(16) not null,
  business_loop varchar(48) not null,
  command varchar(160) not null,
  event_state varchar(32) not null default 'DEV_CONFIRMED',
  data_source varchar(32) not null default 'SYNTHETIC_DEV_ONLY',
  external_effect boolean not null default false,
  model_gateway_status varchar(32) not null default 'NOOP_NOT_INVOKED',
  payload jsonb not null default '{}'::jsonb,
  correlation_id varchar(160) not null,
  idempotency_key varchar(160),
  created_at timestamptz not null default now(),
  constraint family_dev_flow_events_ui_id_check check (ui_id ~ '^UI-(0[1-9]|[1-2][0-9]|3[0-4]|35)$'),
  constraint family_dev_flow_events_external_effect_check check (external_effect = false),
  constraint family_dev_flow_events_model_gateway_check check (model_gateway_status = 'NOOP_NOT_INVOKED')
);

create unique index if not exists ux_family_dev_flow_events_idempotency
  on family_dev_flow_events(family_id, idempotency_key)
  where idempotency_key is not null;

create index if not exists ix_family_dev_flow_events_family_created
  on family_dev_flow_events(family_id, created_at desc);

comment on table family_dev_flow_events is 'DEV-only synthetic UI flow receipts. No real external effect, outcome, ranking, diagnosis, or model write.';
