# Traceability 断链报告快照 (T-08)

- **状态**: SNAPSHOT — 不是 canonical 真相，是某一时刻的检查器输出
- **生成**: 2026-08-29
- **生成方式**: `uv run python tools/architecture/check_traceability.py`
- **快照 commit**: `5f17adc`，工作区有 77 个未提交改动

## 关于这份快照的诚实声明

生成时 T-01/T-03/T-04/T-06/T-07 多个会话在并发工作，`backend/domains/loyalty_points/`
与 `backend/intelligence/model_gateway/` 均为其他会话的未提交 WIP。因此 CODE_GAP 与
API_ORPHAN 的具体条数**会随并发工作变化**，本文件只如实记录生成时的快照，不追平。
判断信噪比请重跑检查器，不要引用本文件的数字。

检查器本身恒退出 0（报告模式）。转强制的顺序见脚本 docstring 与下方 PROMOTION PATH。

---

```text
==============================================================================
AiFamily Traceability Broken-Link Report  (report mode — never fails CI)
==============================================================================

Chain under test (DOCUMENT_GOVERNANCE.md §6):
  Strategy -> Business Capability -> Product Capability -> Domain
           -> Command/Event -> API -> Code -> Test -> Metric

Not re-checked here (already enforced by
tests/architecture/test_capability_registry.py): existence of declared
code/tests paths, status & actor enum legality, R4 tested-needs-tests.

------------------------------------------------------------------------------
SUMMARY
------------------------------------------------------------------------------
  UPSTREAM      0 finding(s)  [0 certain / 0 suspected]
  CODE_GAP     10 finding(s)  [0 certain / 10 suspected]
  API_ORPHAN   26 finding(s)  [26 certain / 0 suspected]
  TOTAL        36 finding(s)  [26 certain / 10 suspected]

------------------------------------------------------------------------------
1. UPSTREAM — capability has no business-capability attribution
------------------------------------------------------------------------------
  (none)

------------------------------------------------------------------------------
2. CODE_GAP — backend/ python dirs no capability claims
------------------------------------------------------------------------------
  [SUSPECTED] backend/apps/family_api
        descendants are covered but these modules in this directory are not
        claimed by any capability `code` entry: main.py
  [SUSPECTED] backend/domains/assessment
        contains .py files but no capability's `code` field covers it and it
        is not ledgered under not_yet_capabilities — either register a
        capability or add an honest not_yet_capabilities row
  [SUSPECTED] backend/domains/loyalty_points
        contains .py files but no capability's `code` field covers it and it
        is not ledgered under not_yet_capabilities — either register a
        capability or add an honest not_yet_capabilities row
  [SUSPECTED] backend/domains/loyalty_points/api
        contains .py files but no capability's `code` field covers it and it
        is not ledgered under not_yet_capabilities — either register a
        capability or add an honest not_yet_capabilities row
  [SUSPECTED] backend/domains/loyalty_points/application
        contains .py files but no capability's `code` field covers it and it
        is not ledgered under not_yet_capabilities — either register a
        capability or add an honest not_yet_capabilities row
  [SUSPECTED] backend/domains/loyalty_points/domain
        contains .py files but no capability's `code` field covers it and it
        is not ledgered under not_yet_capabilities — either register a
        capability or add an honest not_yet_capabilities row
  [SUSPECTED] backend/domains/loyalty_points/infrastructure
        contains .py files but no capability's `code` field covers it and it
        is not ledgered under not_yet_capabilities — either register a
        capability or add an honest not_yet_capabilities row
  [SUSPECTED] backend/domains/product_intelligence/api
        descendants are covered but these modules in this directory are not
        claimed by any capability `code` entry: dependencies.py, requests.py,
        responses.py, zone_requests.py, zone_responses.py, zone_routes.py
  [SUSPECTED] backend/intelligence/model_gateway
        contains .py files but no capability's `code` field covers it and it
        is not ledgered under not_yet_capabilities — either register a
        capability or add an honest not_yet_capabilities row
  [SUSPECTED] backend/intelligence/model_gateway/providers
        contains .py files but no capability's `code` field covers it and it
        is not ledgered under not_yet_capabilities — either register a
        capability or add an honest not_yet_capabilities row

------------------------------------------------------------------------------
3. API_ORPHAN — routes vs registry `api` field
------------------------------------------------------------------------------
  [CERTAIN] GET /auth/contexts
        declared in backend/domains/assessment/api.py but no capability in the
        registry claims this code or this endpoint — fully unregistered HTTP
        surface
  [CERTAIN] GET /auth/me
        declared in backend/domains/assessment/api.py but no capability in the
        registry claims this code or this endpoint — fully unregistered HTTP
        surface
  [CERTAIN] GET /families/{family_id}/ui/02/assessment
        declared in backend/domains/assessment/api.py but no capability in the
        registry claims this code or this endpoint — fully unregistered HTTP
        surface
  [CERTAIN] GET /families/{family_id}/ui/03/growth-hypothesis
        declared in backend/domains/assessment/api.py but no capability in the
        registry claims this code or this endpoint — fully unregistered HTTP
        surface
  [CERTAIN] GET /product-intelligence/product-concepts/{product_concept_id}/chain
        declared in backend/domains/product_intelligence/api/routes.py; the
        owning capability (product_intelligence_hypothesis) does not list this
        endpoint in its `api` field
  [CERTAIN] GET /product-intelligence/zone-assessments/{assessment_id}
        declared in backend/domains/product_intelligence/api/zone_routes.py
        but no capability in the registry claims this code or this endpoint —
        fully unregistered HTTP surface
  [CERTAIN] POST /auth/account-session
        declared in backend/domains/assessment/api.py but no capability in the
        registry claims this code or this endpoint — fully unregistered HTTP
        surface
  [CERTAIN] POST /auth/session/revoke
        declared in backend/domains/assessment/api.py but no capability in the
        registry claims this code or this endpoint — fully unregistered HTTP
        surface
  [CERTAIN] POST /families/{family_id}/assessments/sessions
        declared in backend/domains/assessment/api.py but no capability in the
        registry claims this code or this endpoint — fully unregistered HTTP
        surface
  [CERTAIN] POST /families/{family_id}/assessments/sessions/{session_id}/responses
        declared in backend/domains/assessment/api.py but no capability in the
        registry claims this code or this endpoint — fully unregistered HTTP
        surface
  [CERTAIN] POST /families/{family_id}/assessments/sessions/{session_id}/submit
        declared in backend/domains/assessment/api.py but no capability in the
        registry claims this code or this endpoint — fully unregistered HTTP
        surface
  [CERTAIN] POST /families/{family_id}/assessments/{session_id}/growth-hypothesis
        declared in backend/domains/assessment/api.py but no capability in the
        registry claims this code or this endpoint — fully unregistered HTTP
        surface
  [CERTAIN] POST /families/{family_id}/growth-hypotheses/decisions
        declared in backend/domains/assessment/api.py but no capability in the
        registry claims this code or this endpoint — fully unregistered HTTP
        surface
  [CERTAIN] POST /product-intelligence/customer-insights
        declared in backend/domains/product_intelligence/api/routes.py; the
        owning capability (product_intelligence_hypothesis) does not list this
        endpoint in its `api` field
  [CERTAIN] POST /product-intelligence/growth-hypotheses
        declared in backend/domains/product_intelligence/api/routes.py; the
        owning capability (product_intelligence_hypothesis) does not list this
        endpoint in its `api` field
  [CERTAIN] POST /product-intelligence/growth-hypotheses/{hypothesis_id}/validate
        declared in backend/domains/product_intelligence/api/routes.py; the
        owning capability (product_intelligence_hypothesis) does not list this
        endpoint in its `api` field
  [CERTAIN] POST /product-intelligence/growth-problems
        declared in backend/domains/product_intelligence/api/routes.py; the
        owning capability (product_intelligence_hypothesis) does not list this
        endpoint in its `api` field
  [CERTAIN] POST /product-intelligence/growth-strategies
        declared in backend/domains/product_intelligence/api/routes.py; the
        owning capability (product_intelligence_hypothesis) does not list this
        endpoint in its `api` field
  [CERTAIN] POST /product-intelligence/market-signals
        declared in backend/domains/product_intelligence/api/routes.py; the
        owning capability (product_intelligence_hypothesis) does not list this
        endpoint in its `api` field
  [CERTAIN] POST /product-intelligence/opportunities
        declared in backend/domains/product_intelligence/api/routes.py; the
        owning capability (product_intelligence_hypothesis) does not list this
        endpoint in its `api` field
  [CERTAIN] POST /product-intelligence/product-concepts
        declared in backend/domains/product_intelligence/api/routes.py; the
        owning capability (product_intelligence_hypothesis) does not list this
        endpoint in its `api` field
  [CERTAIN] POST /product-intelligence/product-concepts/{product_concept_id}/zone-assessments
        declared in backend/domains/product_intelligence/api/zone_routes.py
        but no capability in the registry claims this code or this endpoint —
        fully unregistered HTTP surface
  [CERTAIN] POST /product-intelligence/zone-assessments/{assessment_id}/approve
        declared in backend/domains/product_intelligence/api/zone_routes.py
        but no capability in the registry claims this code or this endpoint —
        fully unregistered HTTP surface
  [CERTAIN] POST /product-intelligence/zone-assessments/{assessment_id}/reject
        declared in backend/domains/product_intelligence/api/zone_routes.py
        but no capability in the registry claims this code or this endpoint —
        fully unregistered HTTP surface
  [CERTAIN] POST /product-intelligence/zone-assessments/{assessment_id}/score
        declared in backend/domains/product_intelligence/api/zone_routes.py
        but no capability in the registry claims this code or this endpoint —
        fully unregistered HTTP surface
  [CERTAIN] POST /product-intelligence/zone-assessments/{assessment_id}/submit-review
        declared in backend/domains/product_intelligence/api/zone_routes.py
        but no capability in the registry claims this code or this endpoint —
        fully unregistered HTTP surface

------------------------------------------------------------------------------
PROMOTION PATH (report mode -> enforced)
------------------------------------------------------------------------------
  Promote in this order once signal-to-noise is judged acceptable:
   1) API_ORPHAN / registry-claims-a-route-that-does-not-exist —
      zero judgement, a registry that lies about an endpoint has no
      legitimate case. Safe to enforce first.
   2) UPSTREAM — once every row carries business_capability. One line
      per capability to satisfy; it is the link the chain hangs from.
   3) API_ORPHAN / route-not-registered — after T-04 settles the API
      contract inventory, otherwise it fights concurrent route work.
   4) CODE_GAP — keep as report. It overlaps R3 in
      test_migration_manifest.py and its residue is a judgement call
      about what counts as 'a capability'.

Exit code is always 0. This tool reports; humans decide.

```
