-- Family / 伐木累
-- Read-only views for reference values and object metadata.
-- Application writes continue to use Named Actions and base tables.

create or replace view family_active_reference_values_v as
select
  s.code_set_ref,
  s.tenant_id,
  v.code,
  v.display_label,
  v.description,
  v.sort_order,
  v.metadata,
  s.version_no as code_set_version,
  v.effective_from,
  v.effective_to
from family_reference_code_sets s
join family_reference_code_values v
  on v.reference_code_set_id = s.reference_code_set_id
where s.status = 'ACTIVE'
  and v.status = 'ACTIVE'
  and s.effective_from <= now()
  and (s.effective_to is null or s.effective_to > now())
  and v.effective_from <= now()
  and (v.effective_to is null or v.effective_to > now());

create or replace view family_data_object_catalog_v as
select
  object_type,
  physical_relation,
  object_layer,
  scope_level,
  business_key_definition,
  lifecycle_definition,
  audit_definition,
  version_no,
  effective_from,
  effective_to,
  status,
  updated_at
from family_data_object_registry
where status = 'ACTIVE'
  and effective_from <= now()
  and (effective_to is null or effective_to > now());
