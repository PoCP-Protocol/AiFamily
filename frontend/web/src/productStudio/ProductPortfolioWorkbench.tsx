import { useMemo, useState, type FormEvent } from "react";
import { ProductStudioApiError } from "./api";
import { ComponentSkillPicker } from "./ComponentSkillPicker";
import {
  HttpProductPackageReviewApiClient,
  type ProductPackageReviewApiClient,
  type ProductPackageReviewResponse,
} from "./productPackageReviewApi";
import { validateCatalogSnapshot, type CatalogSelectionDraft, type VersionedCatalogSnapshot } from "./productPortfolioModels";

type Props = {
  client?: ProductPackageReviewApiClient;
  catalog?: VersionedCatalogSnapshot | null;
  contractPreview?: boolean;
  initialPackages?: ProductPackageReviewResponse[];
};

function parseDraftIds(value: string): string[] {
  const items = value.split(/[\n,]/).map((item) => item.trim()).filter(Boolean);
  if (items.length === 0 || items.length > 12) {
    throw new ProductStudioApiError("INVALID_INPUT", "请输入 1–12 个 ProductPackage DRAFT ID。");
  }
  if (new Set(items).size !== items.length) {
    throw new ProductStudioApiError("INVALID_INPUT", "ProductPackage DRAFT ID 不能重复。");
  }
  return items;
}

function orderedReferenceCounts(packages: ProductPackageReviewResponse[], field: "component_ids" | "skill_ids") {
  const counts = new Map<string, number>();
  for (const item of packages) {
    for (const ref of item.draft[field]) counts.set(ref, (counts.get(ref) ?? 0) + 1);
  }
  return [...counts.entries()];
}

export function ProductPortfolioWorkbench({
  client = new HttpProductPackageReviewApiClient(),
  catalog = null,
  contractPreview = false,
  initialPackages = [],
}: Props) {
  const [draftIds, setDraftIds] = useState(initialPackages.map((item) => item.draft.draft_id).join("\n"));
  const [packages, setPackages] = useState(initialPackages);
  const [selection, setSelection] = useState<CatalogSelectionDraft | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ProductStudioApiError | null>(null);
  const [historical, setHistorical] = useState(false);

  const zones = useMemo(() => ({
    COMMODITY: packages.filter((item) => item.draft.approved_zone === "COMMODITY").length,
    ADVANTAGE: packages.filter((item) => item.draft.approved_zone === "ADVANTAGE").length,
    UNIQUE: packages.filter((item) => item.draft.approved_zone === "UNIQUE").length,
  }), [packages]);
  const componentCounts = useMemo(() => orderedReferenceCounts(packages, "component_ids"), [packages]);
  const skillCounts = useMemo(() => orderedReferenceCounts(packages, "skill_ids"), [packages]);
  const boundCatalog = useMemo(() => {
    if (!catalog) return null;
    try {
      const validated = validateCatalogSnapshot(catalog);
      return packages.some((item) => item.draft.draft_id === validated.evaluated_for.draft_id
        && item.draft.version === validated.evaluated_for.version
        && item.draft.content_hash === validated.evaluated_for.content_hash) ? validated : null;
    } catch {
      return catalog;
    }
  }, [catalog, packages]);

  const load = async (event?: FormEvent) => {
    event?.preventDefault();
    setError(null);
    let ids: string[];
    try {
      ids = parseDraftIds(draftIds);
    } catch (cause) {
      setError(cause as ProductStudioApiError);
      return;
    }
    setBusy(true);
    try {
      const next = await Promise.all(ids.map((draftId) => {
        const current = packages.find((item) => item.draft.draft_id === draftId);
        return client.get(draftId, current?.draft.content_hash);
      }));
      setPackages(next);
      setHistorical(false);
    } catch (cause) {
      setHistorical(packages.length > 0);
      setError(cause instanceof ProductStudioApiError
        ? cause
        : new ProductStudioApiError("INVALID_RESPONSE", "Portfolio 快照返回异常。"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section aria-busy={busy} aria-label="Evidence to selected ProductPackage comparison" className="panel product-portfolio-workbench">
      <p className="section-kicker">Evidence → Opportunity contract gap → ProductPackage DRAFT → Selected comparison</p>
      <h2>证据到选定产品包对照工作台</h2>
      <p className="muted">
        读取已经严格校验的 ProductPackage v1.2 冻结快照，仅对当前选定集合展示离散三区、证据与引用关系；这不是权威 Portfolio，不计算综合分，不做家庭评分或排名。
      </p>

      {contractPreview ? (
        <div className="callout" role="note">
          <strong>合同预览，尚未接入生产 Opportunity/Portfolio/Catalog 运行时</strong>
          <p>严格 ProductPackage 路由、身份会话与可信 Catalog Snapshot 未正式挂载前，不发网络请求，也不加载演示产品或组件。</p>
        </div>
      ) : null}

      <form className="portfolio-load-form" onSubmit={(event) => void load(event)}>
        <fieldset disabled={busy || contractPreview}>
          <legend>加载不可变 ProductPackage DRAFT</legend>
          <label>
            DRAFT ID（每行一个，保持输入顺序）
            <textarea onChange={(event) => setDraftIds(event.target.value)} rows={4} value={draftIds} />
          </label>
          <button className="primary-button" type="submit">{packages.length ? "按内容哈希刷新快照" : "加载选定集合"}</button>
        </fieldset>
      </form>

      {error ? <div className="callout" role="alert"><strong>{error.code}</strong><p>{error.message}</p></div> : null}

      {packages.length ? (
        <section aria-label="ProductPackage DRAFT 选定集合" className="portfolio-snapshot">
          <div className="section-heading-row">
            <div><p className="section-kicker">只读 · 非权威 Portfolio</p><h3>ProductPackage DRAFT 选定集合</h3></div>
            <span>{packages.length} 个冻结版本</span>
          </div>
          {historical ? <div className="callout" role="status"><strong>HISTORICAL_SNAPSHOT</strong><p>刷新失败；下方保留的是上次已知只读快照，不代表当前状态。</p></div> : null}

          <div className="portfolio-zone-buckets" aria-label="已批准三区评估分布">
            {Object.entries(zones).map(([zone, count]) => <article key={zone}><span>{zone}</span><strong>{count}</strong><small>已批准评估快照</small></article>)}
          </div>

          <div className="portfolio-package-grid">
            {packages.map((item) => (
              <article className="portfolio-package-card" key={item.draft.draft_id}>
                <div className="portfolio-card-heading">
                  <div><span className="draft-badge">DRAFT · v{item.draft.version}</span><h4>{item.draft.product_kind} · {item.draft.duration_days} 天</h4></div>
                  <span>{item.review_task.status}</span>
                </div>
                <p><strong>已审核矛盾假设（INFERENCE）：</strong>{item.draft.primary_contradiction}</p>
                <dl className="compact-definition-list">
                  <div><dt>Draft / Concept</dt><dd>{item.draft.draft_id} / {item.draft.concept_id}</dd></div>
                  <div><dt>已批准三区评估</dt><dd>{item.draft.approved_zone} · {item.draft.zone_assessment_id}</dd></div>
                  <div><dt>需求 / 市场</dt><dd>{item.draft.demand_ref} / {item.draft.market_insight_refs.join("、")}</dd></div>
                  <div><dt>组件冻结不透明引用</dt><dd>{item.draft.component_ids.join("、")}</dd></div>
                  <div><dt>Skill 冻结不透明引用</dt><dd>{item.draft.skill_ids.join("、")}</dd></div>
                  <div><dt>未知项</dt><dd>{item.draft.unknowns.join("、")}</dd></div>
                  <div><dt>下一步验证建议（RECOMMENDATION）</dt><dd>{item.draft.next_validation}</dd></div>
                </dl>
                <details>
                  <summary>查看 {item.draft.concept_id} 的 receipt-backed 证据血缘</summary>
                  {item.draft.evidence_admissions.map((admission) => (
                    <section className="portfolio-evidence-lineage" key={admission.receipt_id}>
                      <strong>{admission.claim_type} · {admission.admission_status}</strong>
                      <p>Receipt：{admission.receipt_id} · {admission.receipt_outcome} · {admission.integrity_check}</p>
                      <p>Evidence：{admission.evidence_id} · v{admission.evidence_version} · {admission.relevance}</p>
                      <p>Claim：{admission.required_claim_refs.join("、")}</p>
                      <p>Applicability：{admission.required_applicability_refs.join("、")}</p>
                      <p>有效至：{new Date(admission.valid_until).toLocaleString()}</p>
                    </section>
                  ))}
                </details>
              </article>
            ))}
          </div>

          <section aria-label="组件与 Skill 复用引用" className="portfolio-reuse-map">
            <h3>冻结引用复用关系</h3>
            <p className="muted">数量表示被多少个已加载 ProductPackage DRAFT 引用，不表示质量、效果或推荐顺序。</p>
            <div>
              <article><h4>Components</h4>{componentCounts.map(([ref, count]) => <p key={ref}><code>{ref}</code><span>{count} 个 DRAFT</span></p>)}</article>
              <article><h4>Skills</h4>{skillCounts.map(([ref, count]) => <p key={ref}><code>{ref}</code><span>{count} 个 DRAFT</span></p>)}</article>
            </div>
          </section>
        </section>
      ) : (
        <p className="empty-state">尚未加载可信 ProductPackage 选定集合。</p>
      )}

      <ComponentSkillPicker
        catalog={boundCatalog}
        disabled={contractPreview}
        onSelectionChange={setSelection}
        selection={selection}
      />
    </section>
  );
}
