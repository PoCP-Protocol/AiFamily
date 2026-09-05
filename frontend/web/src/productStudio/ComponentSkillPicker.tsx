import { useMemo, useState } from "react";
import {
  validateCatalogSnapshot,
  type CatalogItemKind,
  type CatalogSelectionDraft,
  type VersionedCatalogSnapshot,
} from "./productPortfolioModels";

type Props = {
  catalog: VersionedCatalogSnapshot | null;
  disabled?: boolean;
  now?: () => number;
  selection: CatalogSelectionDraft | null;
  onSelectionChange: (selection: CatalogSelectionDraft) => void;
};

const ALL = "ALL";

function values(items: string[]): string[] {
  return [...new Set(items)];
}

export function ComponentSkillPicker({ catalog, disabled = false, now = Date.now, selection, onSelectionChange }: Props) {
  const [kind, setKind] = useState<CatalogItemKind | typeof ALL>(ALL);
  const [role, setRole] = useState(ALL);
  const [ageBand, setAgeBand] = useState(ALL);
  const [scenario, setScenario] = useState(ALL);
  const validation = useMemo(() => {
    try {
      return { catalog: catalog ? validateCatalogSnapshot(catalog) : null, error: null };
    } catch (error) {
      return { catalog: null, error: error instanceof Error ? error.message : "目录快照无效。" };
    }
  }, [catalog]);
  const validated = validation.catalog;
  const currentTime = now();
  const inactive = validated ? Date.parse(validated.generated_at) > currentTime || Date.parse(validated.expires_at) <= currentTime : true;
  const drifted = Boolean(validated && selection && (
    selection.catalog_snapshot_id !== validated.snapshot_id
    || selection.catalog_content_hash !== validated.content_hash
    || selection.target_context_hash !== validated.target_context_hash
  ));
  const items = validated?.items ?? [];
  const selectedRefs = selection ? [...selection.component_refs, ...selection.skill_refs] : [];
  const visible = items.filter((item) => (
    (kind === ALL || item.item_kind === kind)
    && (role === ALL || item.target_roles.includes(role))
    && (ageBand === ALL || item.age_bands.includes(ageBand))
    && (scenario === ALL || item.scenarios.includes(scenario))
  ));

  const toggle = (itemRef: string, checked: boolean) => {
    const toggleTime = now();
    if (!validated || disabled || drifted || Date.parse(validated.generated_at) > toggleTime || Date.parse(validated.expires_at) <= toggleTime) return;
    const item = validated.items.find((candidate) => candidate.item_ref === itemRef);
    if (!item || item.server_selection_state !== "REUSABLE") return;
    const nextRefs = checked ? [...new Set([...selectedRefs, itemRef])] : selectedRefs.filter((ref) => ref !== itemRef);
    onSelectionChange({
      catalog_snapshot_id: validated.snapshot_id,
      catalog_content_hash: validated.content_hash,
      target_context_hash: validated.target_context_hash,
      component_refs: nextRefs.filter((ref) => validated.items.find((candidate) => candidate.item_ref === ref)?.item_kind === "COMPONENT"),
      skill_refs: nextRefs.filter((ref) => validated.items.find((candidate) => candidate.item_ref === ref)?.item_kind === "SKILL"),
    });
  };

  return (
    <section aria-label="版本化 Component 与 Skill Picker" className="catalog-picker">
      <div className="section-heading-row">
        <div><p className="section-kicker">PDM · Server-authorized frozen references</p><h3>组件与 Skill 冻结引用选择</h3></div>
        {validated ? <code>{validated.snapshot_id}</code> : null}
      </div>
      <p className="muted">Web 只呈现服务端冻结的离散选择状态，不推断资格、不计算适配分、不排序赢家；最终提交仍需后端重验。</p>

      {validation.error ? <div className="callout" role="alert"><strong>INVALID_CATALOG_SNAPSHOT</strong><p>{validation.error}</p></div> : null}
      {!validated && !validation.error ? <div className="callout" role="note"><strong>Catalog Snapshot 尚未接入</strong><p>没有可信目录时不加载演示条目，也不允许把手填 ID 冒充 Picker。</p></div> : null}
      {validated && inactive ? <div className="callout" role="alert"><strong>CATALOG_SNAPSHOT_INACTIVE</strong><p>目录快照尚未生效或已经过期，旧选择只读保留。</p></div> : null}
      {validated && drifted ? <div className="callout" role="alert"><strong>CATALOG_SNAPSHOT_DRIFTED</strong><p>目录或目标上下文已变化，旧选择只读；需基于新快照重新选择。</p></div> : null}

      {validated ? (
        <>
          <dl className="compact-definition-list catalog-context">
            <div><dt>评估对象</dt><dd>{validated.evaluated_for.draft_id} · v{validated.evaluated_for.version}</dd></div>
            <div><dt>租户 / 策略</dt><dd>{validated.tenant_scope} / {validated.policy_version}</dd></div>
            <div><dt>目标上下文</dt><dd><code>{validated.target_context_hash}</code></dd></div>
          </dl>
          <fieldset className="catalog-filters" disabled={disabled}>
            <legend>仅筛选视图，不改变服务端资格</legend>
            <label>类型<select value={kind} onChange={(event) => setKind(event.target.value as CatalogItemKind | typeof ALL)}><option value={ALL}>全部</option><option value="COMPONENT">Component</option><option value="SKILL">Skill</option></select></label>
            <label>目标角色<select value={role} onChange={(event) => setRole(event.target.value)}><option value={ALL}>全部</option>{values(items.flatMap((item) => item.target_roles)).map((value) => <option key={value}>{value}</option>)}</select></label>
            <label>年龄段<select value={ageBand} onChange={(event) => setAgeBand(event.target.value)}><option value={ALL}>全部</option>{values(items.flatMap((item) => item.age_bands)).map((value) => <option key={value}>{value}</option>)}</select></label>
            <label>场景<select value={scenario} onChange={(event) => setScenario(event.target.value)}><option value={ALL}>全部</option>{values(items.flatMap((item) => item.scenarios)).map((value) => <option key={value}>{value}</option>)}</select></label>
          </fieldset>

          <div className="catalog-item-grid">
            {visible.map((item, index) => {
              const selectable = !disabled && !inactive && !drifted && item.server_selection_state === "REUSABLE";
              const descriptionId = `catalog-item-${index}-${item.item_ref.replace(/[^a-zA-Z0-9_-]/g, "-")}`;
              return (
                <article className="catalog-item" key={item.item_ref}>
                  <div className="catalog-item-title">
                    <label><input aria-describedby={descriptionId} checked={selectedRefs.includes(item.item_ref)} disabled={!selectable} onChange={(event) => toggle(item.item_ref, event.target.checked)} type="checkbox" /><span><strong>{item.title}</strong><code>{item.item_ref}</code></span></label>
                    <span className={`catalog-state catalog-state-${item.server_selection_state.toLowerCase()}`}>{item.server_selection_state}</span>
                  </div>
                  <div id={descriptionId}>
                    <p>{item.purpose}</p>
                    <dl className="compact-definition-list">
                      <div><dt>类型 / 来源生命周期</dt><dd>{item.item_kind} · {item.source_lifecycle_state}</dd></div>
                      <div><dt>服务端选择状态</dt><dd>{item.server_selection_state}</dd></div>
                      <div><dt>目标角色 / 执行角色</dt><dd>{item.target_roles.join("、")} / {item.executor_roles.join("、")}</dd></div>
                      <div><dt>场景 / 地域 / 语言</dt><dd>{item.scenarios.join("、")} / {item.regions.join("、")} / {item.locales.join("、")}</dd></div>
                      <div><dt>禁忌</dt><dd>{item.contraindications.length ? item.contraindications.join("、") : "无已登记禁忌"}</dd></div>
                      <div><dt>Reason codes</dt><dd>{item.reason_codes.length ? item.reason_codes.join("、") : "无"}</dd></div>
                      <div><dt>Admission receipts</dt><dd>{item.admission_receipts.map((receipt) => `${receipt.receipt_id} · ${receipt.outcome} · ${receipt.policy_version}`).join("；")}</dd></div>
                      <div><dt>Human handoff</dt><dd>{item.human_handoff_policy}</dd></div>
                    </dl>
                  </div>
                </article>
              );
            })}
          </div>
          {visible.length === 0 ? <p className="empty-state">当前筛选条件下没有目录条目。</p> : null}
          <div aria-live="polite" className="selection-draft" role="status"><strong>设计选择草案 · 未保存</strong><p>{selectedRefs.length ? selectedRefs.join("、") : "尚未选择冻结引用。"}</p></div>
        </>
      ) : null}
    </section>
  );
}
