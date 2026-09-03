from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ARCHITECTURE = ROOT / "docs/05_ai/AI_TECHNICAL_ARCHITECTURE.md"
ADR = ROOT / "governance/ADR/ADR-0024-ai-technical-architecture-governed-runtime.md"


def test_ai_technical_architecture_is_a_draft_not_current_truth() -> None:
    text = ARCHITECTURE.read_text(encoding="utf-8")
    assert "status: draft" in text
    assert "AI 技术架构总设计" in text
    for reference in (
        "AI_NATIVE_PRINCIPLES.md",
        "AI_ARCHITECTURE.md",
        "COMPLIANCE_HARD_CONSTRAINTS.md",
        "docs/02_business",
        "docs/06_platform",
    ):
        assert reference in text


def test_architecture_defines_runtime_planes_and_required_components() -> None:
    text = ARCHITECTURE.read_text(encoding="utf-8")
    for plane in (
        "Domain Truth Plane",
        "Intelligence Data Plane",
        "AI Runtime Control Plane",
        "Experience & Operations Plane",
        "Governance & Evidence Plane",
    ):
        assert plane in text
    for component in (
        "Context Broker",
        "Memory System",
        "Growth Graph Projection",
        "Model Gateway",
        "Agent Runtime",
        "Tool Runtime",
        "Prompt Registry",
        "Schema Registry",
        "Safety Runtime",
        "Human Gate",
        "Evaluation",
        "Trace/Cost/Audit",
    ):
        assert component in text


def test_architecture_defines_all_five_agents_and_delays_multi_agent() -> None:
    text = ARCHITECTURE.read_text(encoding="utf-8")
    for agent in (
        "ParentAdvisor",
        "ChildCoach",
        "TeachingAssistant",
        "GrowthPlanner",
        "OperationsAssistant",
    ):
        assert agent in text
    assert "先让一个 Agent" in text
    assert "多 Agent 协同不是第一批任务" in text
    assert "may_mutate_business_state=false" in text


def test_architecture_preserves_fact_boundary_and_minor_safety() -> None:
    text = ARCHITECTURE.read_text(encoding="utf-8")
    for phrase in (
        "AI Runtime 不得 import Domain Repository/ORM",
        "AI Draft 不得写",
        "HumanDecision 必须由非 AI Actor 创建",
        "家庭总分/排名",
        "儿童画像商业营销",
        "主体级删除",
        "data_class=SYNTHETIC",
        "Evidence refs",
        "causation_id",
    ):
        assert phrase in text


def test_architecture_aligns_business_process_data_and_application_layers() -> None:
    text = ARCHITECTURE.read_text(encoding="utf-8")
    for flow in ("S04", "S05", "S06", "S07", "S08", "S09", "S10-S14", "O12"):
        assert flow in text
    for data_object in (
        "ContextSnapshot",
        "StateObservation",
        "EvidenceReference",
        "MemoryItem",
        "GrowthGraphEdge",
        "EmbeddingRef",
        "ModelDraft",
        "HumanTask",
        "HumanDecision",
    ):
        assert data_object in text
    for application in (
        "AssessmentApplication",
        "GrowthApplication",
        "JourneyApplication",
        "Service/FGCN Application",
        "OperationsGovernanceApplication",
    ):
        assert application in text


def test_architecture_requires_environment_parity_and_operational_evidence() -> None:
    text = ARCHITECTURE.read_text(encoding="utf-8")
    for phrase in (
        "dev/test/prod 必须使用相同",
        "仅允许替换",
        "Contract Eval",
        "Safety Eval",
        "Grounding Eval",
        "Workflow Eval",
        "Drift Eval",
        "Attempt 必须在外呼前登记",
        "automatic_retry=0",
        "完成证明",
    ):
        assert phrase in text


def test_ai_technical_architecture_has_a_corresponding_adr() -> None:
    text = ADR.read_text(encoding="utf-8")
    assert "id: ADR-0024" in text
    assert "status: proposed" in text
    assert "Family Growth Intelligence OS" in text
    assert "Model Gateway 是唯一供应商边界" in text
    assert "AI Runtime 只读业务投影，不读业务 ORM，不写业务事实" in text
    assert "PostgreSQL 是 AI 技术对象的首选持久化边界" in text
