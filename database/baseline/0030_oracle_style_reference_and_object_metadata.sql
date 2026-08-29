-- Family / 伐木累
-- Oracle EBS-inspired reference values and object metadata.
-- This migration does not rename historical tables or rewrite existing source refs.

create table if not exists family_reference_code_sets (
  reference_code_set_id uuid primary key default gen_random_uuid(),
  code_set_ref varchar(80) not null,
  tenant_id uuid null references tenants(tenant_id),
  code_set_name varchar(160) not null,
  description text null,
  status varchar(40) not null default 'ACTIVE',
  effective_from timestamptz not null default now(),
  effective_to timestamptz null,
  version_no integer not null default 1,
  source_system varchar(80) not null default 'FAMILY_PLATFORM',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint family_reference_code_sets_ref_scope_uk unique (tenant_id, code_set_ref, version_no),
  constraint family_reference_code_sets_dates_ck check (effective_to is null or effective_to > effective_from),
  constraint family_reference_code_sets_status_ck check (status in ('DRAFT','ACTIVE','RETIRED'))
);

create table if not exists family_reference_code_values (
  reference_code_value_id uuid primary key default gen_random_uuid(),
  reference_code_set_id uuid not null references family_reference_code_sets(reference_code_set_id),
  code varchar(80) not null,
  display_label varchar(240) not null,
  description text null,
  status varchar(40) not null default 'ACTIVE',
  effective_from timestamptz not null default now(),
  effective_to timestamptz null,
  sort_order integer not null default 0,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint family_reference_code_values_uk unique (reference_code_set_id, code),
  constraint family_reference_code_values_dates_ck check (effective_to is null or effective_to > effective_from),
  constraint family_reference_code_values_status_ck check (status in ('DRAFT','ACTIVE','RETIRED'))
);

create table if not exists family_reference_validation_rules (
  reference_validation_rule_id uuid primary key default gen_random_uuid(),
  rule_ref varchar(80) not null,
  tenant_id uuid null references tenants(tenant_id),
  object_type varchar(100) not null,
  field_name varchar(100) not null,
  rule_kind varchar(60) not null,
  rule_config jsonb not null default '{}'::jsonb,
  status varchar(40) not null default 'ACTIVE',
  effective_from timestamptz not null default now(),
  effective_to timestamptz null,
  version_no integer not null default 1,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint family_reference_validation_rules_uk unique (tenant_id, rule_ref, version_no),
  constraint family_reference_validation_rules_dates_ck check (effective_to is null or effective_to > effective_from),
  constraint family_reference_validation_rules_status_ck check (status in ('DRAFT','ACTIVE','RETIRED'))
);

create table if not exists family_data_object_registry (
  data_object_registry_id uuid primary key default gen_random_uuid(),
  object_type varchar(120) not null,
  physical_relation varchar(160) not null,
  object_layer varchar(20) not null,
  scope_level varchar(20) not null,
  business_key_definition jsonb not null default '{}'::jsonb,
  lifecycle_definition jsonb not null default '{}'::jsonb,
  audit_definition jsonb not null default '{}'::jsonb,
  status varchar(40) not null default 'ACTIVE',
  version_no integer not null default 1,
  effective_from timestamptz not null default now(),
  effective_to timestamptz null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint family_data_object_registry_uk unique (object_type, physical_relation, version_no),
  constraint family_data_object_registry_layer_ck check (object_layer in ('BASE','INTERFACE','PROJECTION','AUDIT')),
  constraint family_data_object_registry_scope_ck check (scope_level in ('PLATFORM','TENANT','FAMILY','TENANT_FAMILY')),
  constraint family_data_object_registry_status_ck check (status in ('DRAFT','ACTIVE','RETIRED')),
  constraint family_data_object_registry_dates_ck check (effective_to is null or effective_to > effective_from)
);

create index if not exists family_reference_code_values_set_status_idx
  on family_reference_code_values (reference_code_set_id, status, effective_from, effective_to);
create index if not exists family_reference_validation_rules_scope_idx
  on family_reference_validation_rules (tenant_id, object_type, field_name, status);
create index if not exists family_data_object_registry_layer_scope_idx
  on family_data_object_registry (object_layer, scope_level, status);

insert into family_reference_code_sets (code_set_ref, code_set_name, description)
values
  ('OBJECT_LAYER', '数据对象层', 'Family Base/Interface/Projection/Audit object layer'),
  ('SCOPE_LEVEL', '数据范围级别', 'Family platform, tenant and family scope'),
  ('LIFECYCLE_STATUS', '生命周期状态', 'Common draft/active/retired lifecycle')
on conflict (tenant_id, code_set_ref, version_no) do nothing;

insert into family_reference_code_values (reference_code_set_id, code, display_label, description)
select s.reference_code_set_id, v.code, v.display_label, v.description
from family_reference_code_sets s
join (values
  ('OBJECT_LAYER','BASE','正式基表','正式主数据或交易事实'),
  ('OBJECT_LAYER','INTERFACE','接口承载','外部/导入/模型输入 staging'),
  ('OBJECT_LAYER','PROJECTION','读模型投影','页面、目录或 LLM 只读投影'),
  ('OBJECT_LAYER','AUDIT','审计事实','不可变的状态/策略/调用摘要'),
  ('SCOPE_LEVEL','PLATFORM','平台级','平台共享对象'),
  ('SCOPE_LEVEL','TENANT','租户级','Tenant 私有或租户可见对象'),
  ('SCOPE_LEVEL','FAMILY','家庭级','Family 私有对象'),
  ('SCOPE_LEVEL','TENANT_FAMILY','租户家庭级','同时受 Tenant 与 Family 约束'),
  ('LIFECYCLE_STATUS','DRAFT','草稿','不可对普通用户生效'),
  ('LIFECYCLE_STATUS','ACTIVE','生效','当前可用版本'),
  ('LIFECYCLE_STATUS','RETIRED','退役','不再新建但保留历史')
) as v(code_set_ref, code, display_label, description)
  on v.code_set_ref = s.code_set_ref
on conflict (reference_code_set_id, code) do nothing;
