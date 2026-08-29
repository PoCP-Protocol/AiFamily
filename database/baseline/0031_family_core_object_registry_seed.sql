-- Family / 伐木累
-- Register core objects in the Oracle EBS-inspired object registry.
-- Registry metadata is not a substitute for row-level authorization.

insert into family_data_object_registry
  (object_type, physical_relation, object_layer, scope_level, business_key_definition, lifecycle_definition, audit_definition)
values
  ('Tenant', 'tenants', 'BASE', 'TENANT', '{"key":"tenant_ref"}', '{"status":["DRAFT","ACTIVE","SUSPENDED","RETIRED"],"effective_dates":true}', '{"who":true,"correlation_id":true}'),
  ('TenantFamilyBinding', 'tenant_family_bindings', 'BASE', 'TENANT_FAMILY', '{"key":"tenant_id+family_id"}', '{"status":["PENDING","ACTIVE","SUSPENDED","RETIRED"],"effective_dates":true}', '{"who":true,"correlation_id":true}'),
  ('Family', 'families', 'BASE', 'TENANT_FAMILY', '{"key":"tenant_id+family_ref"}', '{"status":["ACTIVE","SUSPENDED","ARCHIVED"],"effective_dates":false}', '{"who":true,"correlation_id":true}'),
  ('FamilySupportReport', 'family_support_report_snapshots', 'PROJECTION', 'TENANT_FAMILY', '{"key":"family_id+report_ref+version_no"}', '{"status":["DRAFT","ACTIVE","WITHDRAWN"],"effective_dates":false}', '{"who":true,"correlation_id":true}'),
  ('FamilyPageTask', 'family_page_task_items', 'BASE', 'TENANT_FAMILY', '{"key":"family_id+task_ref+version_no"}', '{"status":["OPEN","IN_PROGRESS","COMPLETED","DISMISSED"],"effective_dates":false}', '{"who":true,"correlation_id":true}'),
  ('TestExperienceOperation', 'test_experience_operations', 'BASE', 'TENANT_FAMILY', '{"key":"family_id+idempotency_key"}', '{"status":["REQUESTED","CONFIRMED","CANCELLED","BLOCKED"],"effective_dates":false}', '{"who":true,"correlation_id":true}'),
  ('FamilyLlmGatewayAudit', 'family_llm_gateway_audits', 'AUDIT', 'TENANT_FAMILY', '{"key":"trace_id+decision"}', '{"status":["APPEND_ONLY"],"effective_dates":false}', '{"provider_original":false,"secret_persistence":false}'),
  ('MultimodalAsset', 'multimodal_assets', 'INTERFACE', 'TENANT_FAMILY', '{"key":"asset_ref+content_hash"}', '{"status":["RECEIVED","AVAILABLE","REVOKED","EXPIRED","DELETED"],"effective_dates":false}', '{"raw_media_in_audit":false,"who":true}'),
  ('MultimodalDerivedArtifact', 'multimodal_derived_artifacts', 'PROJECTION', 'TENANT_FAMILY', '{"key":"artifact_ref+version_no"}', '{"status":["DRAFT","REVIEW_REQUIRED","REJECTED","EXPIRED","DELETED"],"effective_dates":false}', '{"write_back_core_facts":false,"who":true}'),
  ('FamilyAdmittedCatalogProjection', 'family_admitted_catalog_items', 'PROJECTION', 'TENANT_FAMILY', '{"key":"family_id+catalog_item_ref+version_no"}', '{"status":["VISIBLE","HIDDEN","RETIRED"],"effective_dates":true}', '{"source_ref":true,"who":true}')
on conflict (object_type, physical_relation, version_no) do update set
  object_layer = excluded.object_layer,
  scope_level = excluded.scope_level,
  business_key_definition = excluded.business_key_definition,
  lifecycle_definition = excluded.lifecycle_definition,
  audit_definition = excluded.audit_definition,
  updated_at = now();
