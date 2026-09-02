import { useRef, useState, type KeyboardEvent } from "react";
import { MarketEvidenceWorkbench } from "./MarketEvidenceWorkbench";
import { ProductConceptDecisionWorkbench } from "./ProductConceptDecisionWorkbench";
import { CourseContentWorkbench } from "./CourseContentWorkbench";
import { CourseContentGovernancePanel } from "./CourseContentGovernancePanel";
import { ProductDefinitionOperatorReviewWorkbench } from "./ProductDefinitionOperatorReviewWorkbench";
import { ProductFactoryComposer } from "./ProductFactoryComposer";
import { ProductPackageReviewWorkbench } from "./ProductPackageReviewWorkbench";
import { ProductPortfolioWorkbench } from "./ProductPortfolioWorkbench";
import { ProductStudio } from "./ProductStudio";
import { sandboxProductStudioState } from "./sandboxFixture";

const WORKSPACE_TABS = [
  { id: "demand", label: "Demand" },
  { id: "market-evidence", label: "Market Evidence" },
  { id: "concept-decision", label: "Concept Decision" },
  { id: "package-review", label: "Package Review" },
  { id: "portfolio-catalog", label: "Portfolio & Catalog" },
  { id: "pdm-review", label: "PDM Review" },
  { id: "course-content", label: "Course Content" },
  { id: "sandbox", label: "Sandbox" },
] as const;

type WorkspaceTabId = (typeof WORKSPACE_TABS)[number]["id"];

export function ProductStudioWorkspace() {
  const [activeTab, setActiveTab] = useState<WorkspaceTabId>("demand");
  const tabRefs = useRef<Array<HTMLButtonElement | null>>([]);

  const activateByIndex = (index: number) => {
    const normalizedIndex = (index + WORKSPACE_TABS.length) % WORKSPACE_TABS.length;
    setActiveTab(WORKSPACE_TABS[normalizedIndex].id);
    tabRefs.current[normalizedIndex]?.focus();
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    switch (event.key) {
      case "ArrowRight":
      case "ArrowDown":
        event.preventDefault();
        activateByIndex(index + 1);
        break;
      case "ArrowLeft":
      case "ArrowUp":
        event.preventDefault();
        activateByIndex(index - 1);
        break;
      case "Home":
        event.preventDefault();
        activateByIndex(0);
        break;
      case "End":
        event.preventDefault();
        activateByIndex(WORKSPACE_TABS.length - 1);
        break;
    }
  };

  return (
    <section aria-label="Product Studio Workspace" className="product-studio-workspace">
      <header className="product-studio-workspace-header">
        <p className="eyebrow">IPD · PDM · PLM</p>
        <h1>服务产品 AI 研发工作台</h1>
        <p className="muted">按阶段工作，切换不会丢失尚未提交的表单内容。</p>
      </header>

      <div aria-label="产品研发阶段" className="product-workspace-tabs" role="tablist">
        {WORKSPACE_TABS.map((tab, index) => {
          const selected = activeTab === tab.id;
          return (
            <button
              aria-controls={`workspace-panel-${tab.id}`}
              aria-selected={selected}
              id={`workspace-tab-${tab.id}`}
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              onKeyDown={(event) => handleKeyDown(event, index)}
              ref={(node) => { tabRefs.current[index] = node; }}
              role="tab"
              tabIndex={selected ? 0 : -1}
              type="button"
            >
              <span>{index + 1}</span>
              {tab.label}
            </button>
          );
        })}
      </div>

      <div aria-labelledby="workspace-tab-demand" hidden={activeTab !== "demand"} id="workspace-panel-demand" role="tabpanel" tabIndex={0}>
        <ProductFactoryComposer />
      </div>
      <div aria-labelledby="workspace-tab-market-evidence" hidden={activeTab !== "market-evidence"} id="workspace-panel-market-evidence" role="tabpanel" tabIndex={0}>
        <MarketEvidenceWorkbench />
      </div>
      <div aria-labelledby="workspace-tab-concept-decision" hidden={activeTab !== "concept-decision"} id="workspace-panel-concept-decision" role="tabpanel" tabIndex={0}>
        <ProductConceptDecisionWorkbench contractPreview />
      </div>
      <div aria-labelledby="workspace-tab-package-review" hidden={activeTab !== "package-review"} id="workspace-panel-package-review" role="tabpanel" tabIndex={0}>
        <ProductPackageReviewWorkbench contractPreview />
      </div>
      <div aria-labelledby="workspace-tab-portfolio-catalog" hidden={activeTab !== "portfolio-catalog"} id="workspace-panel-portfolio-catalog" role="tabpanel" tabIndex={0}>
        <ProductPortfolioWorkbench contractPreview />
      </div>
      <div aria-labelledby="workspace-tab-pdm-review" hidden={activeTab !== "pdm-review"} id="workspace-panel-pdm-review" role="tabpanel" tabIndex={0}>
        <ProductDefinitionOperatorReviewWorkbench />
      </div>
      <div aria-labelledby="workspace-tab-course-content" hidden={activeTab !== "course-content"} id="workspace-panel-course-content" role="tabpanel" tabIndex={0}>
        <div className="course-content-stage">
          <CourseContentWorkbench contractPreview />
          <CourseContentGovernancePanel contractPreview />
        </div>
      </div>
      <div aria-labelledby="workspace-tab-sandbox" hidden={activeTab !== "sandbox"} id="workspace-panel-sandbox" role="tabpanel" tabIndex={0}>
        <ProductStudio initialState={sandboxProductStudioState} environmentLabel="Sandbox · Product Studio · API seam" />
      </div>
    </section>
  );
}
