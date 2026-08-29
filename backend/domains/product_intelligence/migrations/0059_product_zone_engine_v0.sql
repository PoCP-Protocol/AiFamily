-- FAMILY-AI-PRODUCT-OS-PR002 (Three-Zone Strategy Engine V0)
-- Frozen contract source: architecture/ADR_PRODUCT_ZONE_GOVERNANCE_V0.md and
-- architecture/ADR_PRODUCT_ZONE_SCORING_V0.md.
--
-- Two new tables for the ADR-accurate `domain/zone_entities.py` types
-- (`ZonePolicyVersion`, `ProductZoneAssessment`). These are DISTINCT from
-- the legacy placeholder `product_intelligence_zone_assessments` table
-- created in 0058_product_intelligence_domain.sql for the pre-ADR
-- `domain/entities.py::ProductZoneAssessment` shell — that table is not
-- touched, renamed, or dropped by this migration (Agent A's `zone_entities.py`
-- module docstring: "It intentionally does not replace or subclass the
-- placeholder ProductZoneAssessment in entities.py"). Table names below use
-- a `_v0_` infix specifically to avoid colliding with the 0058 name.
--
-- `dimension_assessments` (the six `DimensionAssessment` rows per
-- assessment) is stored as a single `jsonb` column, NOT a child table.
-- ADR-Governance §3 explicitly allows a separate table "if you have a
-- strong reason"; the default is JSONB. Reasons for keeping JSONB in V0:
--   1. `DimensionAssessment` has no independent identity/lifecycle of its
--      own — it is always read/written as a whole alongside its parent
--      `ProductZoneAssessment` (the application layer's
--      `score_zone_assessment` always replaces the entire list atomically,
--      never a partial per-dimension update — see `application/
--      zone_commands.py` module docstring). A child table would need its
--      own PK/FK plus an ordering column for no query benefit, since there
--      is no code path in this PR that queries a single dimension row
--      independently of its parent assessment.
--   2. The canonical-checksum/reproducibility invariant (ADR-Governance §3:
--      "same dimension inputs + same policy version -> same recommended_zone
--      and the same canonical calculation hash") is naturally whole-object,
--      which a single JSON blob models directly; splitting into six rows
--      adds a JOIN + ORDER BY just to reconstitute the same object.
--   3. Every other list-of-structured-data field in this domain (e.g.
--      `product_intelligence_customer_insights.evidence_refs`,
--      `product_intelligence_growth_hypotheses.assumptions`) already uses
--      jsonb for the same reason (see 0058's own precedent) — consistent
--      with the existing style this migration must match per the task
--      brief, not a new pattern invented here.
-- If Agent D/Portfolio-query needs efficient per-dimension filtering
-- (e.g. "find all assessments where network_effect < 40") in a future PR,
-- Postgres jsonb supports GIN-indexed containment/path queries without a
-- schema change, so this is not a closed door — just not built in V0.

CREATE TABLE IF NOT EXISTS product_intelligence_zone_policy_versions (
  id varchar(160) PRIMARY KEY,
  policy_id varchar(160) NOT NULL,
  version integer NOT NULL,
  dimension_definitions jsonb NOT NULL,
  weights jsonb NOT NULL,
  thresholds jsonb NOT NULL,
  classification_rules text NOT NULL,
  review_policy jsonb NOT NULL,
  effective_from timestamptz NOT NULL,
  status varchar(24) NOT NULL CHECK (status IN ('DRAFT', 'ACTIVE', 'RETIRED')),
  checksum varchar(160) NOT NULL,
  UNIQUE (policy_id, version)
);

-- ADR-Governance §3: "same policy version is verifiable" via `checksum` —
-- only one row may claim `status = 'ACTIVE'` per `policy_id` lineage at a
-- time is a business invariant, but per the "platform-wide, not tenant
-- scoped" note in `application/zone_ports.py` module docstring, V0 does
-- not enforce "exactly one ACTIVE row platform-wide" at the SQL level
-- either (no partial-unique-index on status='ACTIVE') — the fixture
-- policy setup in tests inserts exactly one ACTIVE row and
-- `load_active_zone_policy_version` picks the first status='ACTIVE' match;
-- enforcing global single-ACTIVE-row-ness is left to application-layer
-- discipline (a future policy-publish command) or a future migration once
-- multiple concurrent ACTIVE candidates become a real operational risk.

CREATE TABLE IF NOT EXISTS product_intelligence_zone_assessments_v0 (
  id varchar(160) PRIMARY KEY,
  version integer NOT NULL DEFAULT 1,
  created_at timestamptz NOT NULL,
  updated_at timestamptz NOT NULL,
  created_by varchar(160) NOT NULL,
  tenant_scope varchar(160) NOT NULL,
  status varchar(24) NOT NULL CHECK (
    status IN ('DRAFT', 'SCORED', 'UNDER_REVIEW', 'APPROVED', 'REJECTED', 'RETIRED')
  ),
  subject_type varchar(64) NOT NULL CHECK (subject_type = 'PRODUCT_CONCEPT'),
  -- ADR-Scoring §1.1: the only legal subject_type in V0 is PRODUCT_CONCEPT.
  -- `subject_ref` therefore references `product_intelligence_product_concepts.id`
  -- directly: a real foreign key, not a free-form string. This closes the
  -- "cross-tenant guessing" gap Agent B flagged in `application/
  -- zone_commands.py::create_zone_assessment`'s docstring at the database
  -- layer for "does subject_ref exist at all" — it does NOT, by itself,
  -- enforce "and belongs to the same tenant_scope as this assessment"; a
  -- plain FK cannot express a cross-table tenant-equality constraint in
  -- portable SQL. See the trigger below for the tenant-match half of that
  -- gap; if the trigger is ever dropped for portability, the tenant check
  -- reverts to being an application-layer-only guarantee, and integration/
  -- Agent G should be told explicitly rather than assuming the FK alone
  -- covers it.
  subject_ref varchar(160) NOT NULL REFERENCES product_intelligence_product_concepts(id),
  zone_policy_version_id varchar(160) NOT NULL,
  dimension_assessments jsonb NOT NULL,
  differentiation_index double precision NOT NULL,
  defensibility_index double precision NOT NULL,
  commodity_score double precision NOT NULL,
  advantage_score double precision NOT NULL,
  unique_score double precision NOT NULL,
  recommended_zone varchar(24) NOT NULL CHECK (recommended_zone IN ('COMMODITY', 'ADVANTAGE', 'UNIQUE')),
  approved_zone varchar(24) CHECK (approved_zone IS NULL OR approved_zone IN ('COMMODITY', 'ADVANTAGE', 'UNIQUE')),
  override_reason text,
  reviewed_by varchar(160),
  reviewed_at timestamptz,
  review_reason text,
  assessment_origin varchar(24) NOT NULL CHECK (assessment_origin IN ('HUMAN', 'RULE', 'AI_PROPOSAL'))
);

CREATE INDEX IF NOT EXISTS ix_product_intelligence_zone_assessments_v0_tenant_scope
  ON product_intelligence_zone_assessments_v0 (tenant_scope);

CREATE INDEX IF NOT EXISTS ix_product_intelligence_zone_assessments_v0_subject_ref
  ON product_intelligence_zone_assessments_v0 (subject_ref);

-- Best-effort tenant-match guard on top of the plain FK above. This is a
-- Postgres-only mechanism (PL/pgSQL trigger); the SQLite test engine used
-- by this PR's pytest suite (Override #6 item 4 — no real-Postgres
-- integration test in this PR) does not run triggers/functions defined
-- this way, so this guard is NOT exercised by `test_zone_persistence.py`/
-- `test_zone_api_endpoints.py` — it only takes effect once this migration
-- runs against real Postgres (Agent E/integration scope per the task
-- brief). It is intentionally "belt" on top of the FK's "suspenders": the
-- FK alone proves subject_ref points at a real ProductConcept row; this
-- trigger additionally proves that row's tenant_scope matches the
-- assessment's own tenant_scope, closing the exact gap Agent B's
-- `zone_commands.py::create_zone_assessment` docstring flags ("an
-- assessment could reference someone else's concept id by guessing/
-- reusing it"). Application-layer double-checking (loading ProductConcept
-- via ProductIntelligenceRepositoryPort before constructing the
-- assessment) remains the recommended primary fix per that docstring; this
-- trigger is a defense-in-depth backstop, not a replacement for it.
CREATE OR REPLACE FUNCTION product_intelligence_zone_assessment_subject_tenant_guard()
RETURNS trigger AS $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM product_intelligence_product_concepts pc
    WHERE pc.id = NEW.subject_ref
      AND pc.tenant_scope = NEW.tenant_scope
  ) THEN
    RAISE EXCEPTION
      'product_intelligence_zone_assessments_v0.subject_ref % does not belong to tenant_scope %',
      NEW.subject_ref, NEW.tenant_scope;
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_zone_assessment_subject_tenant_guard
  ON product_intelligence_zone_assessments_v0;

CREATE TRIGGER trg_zone_assessment_subject_tenant_guard
  BEFORE INSERT OR UPDATE ON product_intelligence_zone_assessments_v0
  FOR EACH ROW
  EXECUTE FUNCTION product_intelligence_zone_assessment_subject_tenant_guard();
