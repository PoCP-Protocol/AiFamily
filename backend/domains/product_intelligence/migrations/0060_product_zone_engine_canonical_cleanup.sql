-- FAMILY-AI-PRODUCT-OS-PR002R (chief-architect review on PR #37)
--
-- Ruling: `domain/zone_entities.py::ProductZoneAssessment` (the ADR-accurate
-- type from PR-002, backed by `product_intelligence_zone_assessments_v0`
-- from 0059) is the ONE canonical `ProductZoneAssessment` for the Product
-- Intelligence domain. The pre-ADR placeholder
-- `domain/entities.py::ProductZoneAssessment` (created in PR-001, never
-- actually used by any application-layer command/route/real caller — see
-- the PR-002R Agent A audit) has been deleted from the codebase. This
-- migration drops its corresponding table,
-- `product_intelligence_zone_assessments`, created by
-- 0058_product_intelligence_domain.sql.
--
-- This migration does NOT modify 0058 or 0059's historical content — it
-- only adds a new statement to retire what 0058 created. 0059's own
-- docstring already correctly described the (now-removed) placeholder as
-- "not touched, renamed, or dropped by this [0059] migration"; this is the
-- follow-up migration that does the dropping, now that the placeholder
-- type is gone from the code.
--
-- Why a hard DROP (not a rename/deprecate/archive path) is safe here, per
-- the chief architect's rule "if you cannot prove no data exists, do not
-- silently drop":
--   1. No app in this repository has ever mounted this domain's FastAPI
--      router. `domains/product_intelligence/api/dependencies.py` (as of
--      this PR) states: "Not included in any app yet — `apps/family_api`
--      ... has not been bootstrapped by any batch as of this PR" and
--      `_session_factory = None  # set by the owning app at startup; not
--      configured in this PR`. `get_repository()` raises `RuntimeError`
--      if called before an owning app configures that factory.
--   2. No application-layer command/handler in this domain ever called
--      `ProductIntelligenceRepositoryPort.save_product_zone_assessment`
--      (confirmed by full-repo search across `application/commands.py`,
--      `api/routes.py`, and all tests before deleting the method) — the
--      only callers of that method were the port/fake/SQLAlchemy
--      repository definitions themselves, never a real write path.
--   3. Therefore there has never been any code path — HTTP, CLI, or
--      otherwise — capable of writing a row into
--      `product_intelligence_zone_assessments` in any environment,
--      including production. An empty table with zero possible writers
--      is the one case where a hard DROP does not risk silent data loss,
--      so no rename/archive step is used here.
--
-- If a future audit ever disagrees with point 1 or 2 above (e.g. finds a
-- write path this review missed), do NOT re-run this migration's DROP
-- blindly — restore from the 0058 CREATE TABLE definition first.

DROP TABLE IF EXISTS product_intelligence_zone_assessments;

-- Agent C addendum (PR-002R closure, Portfolio Semantics + Active Policy
-- Uniqueness scope) — appended below Agent A's cleanup above; does not
-- modify or remove anything Agent A wrote.
--
-- 1. `scoring_algorithm_version` backfill. Agent B added
--    `domain/zone_entities.py::ZonePolicyVersion.scoring_algorithm_version`
--    (str, default `ZONE_SCORING_V0`) after `0059_product_zone_engine_v0.sql`
--    created `product_intelligence_zone_policy_versions` without this
--    column, which made `save_zone_policy_version` raise `TypeError` for any
--    real Postgres deployment of that table (SQLite test fixtures recreate
--    the table from the current `Base.metadata` on every test run, so they
--    never hit this — only a real Postgres instance that already ran 0059
--    would). `IF NOT EXISTS` makes this idempotent/safe to re-run; the
--    `DEFAULT` backfills any pre-existing row (there should be none in any
--    real environment per the same "never wired into an app yet" argument
--    Agent A's DROP above relies on, but the default costs nothing either
--    way and removes the need to prove that a second time here).
ALTER TABLE product_intelligence_zone_policy_versions
    ADD COLUMN IF NOT EXISTS scoring_algorithm_version varchar(64) NOT NULL DEFAULT 'ZONE_SCORING_V0';

-- 2. Active-policy-per-policy_id uniqueness, enforced at the database level
--    (not just in application/repository code — see
--    `infrastructure/zone_sqlalchemy_repository.py::load_active_zone_policy_version`
--    for the matching fail-closed read-side check). A partial unique index
--    scoped to `status = 'ACTIVE'` allows unlimited DRAFT/RETIRED rows per
--    `policy_id` (normal version history) while making it structurally
--    impossible for two rows sharing a `policy_id` to both be ACTIVE at once.
--    Deliberately scoped to `(policy_id)`, not global across all policy_ids
--    — this migration does not enforce "only one ACTIVE policy in the whole
--    table" (a stronger, platform-wide-single-lineage rule that is out of
--    this PR's task brief; a future PR could add that as a separate
--    constraint if a chief-architect ruling asks for it).
CREATE UNIQUE INDEX IF NOT EXISTS uq_zone_policy_active_per_id
    ON product_intelligence_zone_policy_versions (policy_id)
    WHERE status = 'ACTIVE';
