from pathlib import Path

import yaml

from backend.intelligence.principal.contracts import (
    PrincipalCapability,
    PrincipalEntryPoint,
    PrincipalRouteRequest,
)
from backend.intelligence.principal.router import (
    PrincipalCapabilityRouter,
    registered_capabilities,
)

ROOT = Path(__file__).resolve().parents[2]


def test_deep_ai_design_covers_the_full_platform_dimension_set() -> None:
    text = (ROOT / "docs/05_ai/AI_TECHNICAL_ARCHITECTURE_DEEP_DESIGN.md").read_text(
        encoding="utf-8"
    )
    for dimension in (
        "D01 战略与价值维度",
        "D03 Principal Soul 与人格维度",
        "D04 Context 与记忆维度",
        "D05 知识工程维度",
        "D06 Agent、Skill、Tool 与工作流维度",
        "D07 模型能力与供应链维度",
        "D10 安全、策略与内容护栏维度",
        "D12 评估与质量工程维度",
        "D14 数据治理、隐私与删除维度",
        "D16 可靠性、容量与成本维度",
        "D17 部署、基础设施与灾备维度",
        "D18 开发、测试、生产与组织治理维度",
    ):
        assert dimension in text
    assert "Model Gateway 是唯一模型供应商边界" in text
    assert "may_mutate_business_state` 恒为 `false`" in text
    assert "dev/test/prod" in text


def test_alignment_has_business_process_data_application_and_ai_layers() -> None:
    text = (ROOT / "docs/00_system/ARCHITECTURE_ALIGNMENT_V2.md").read_text(encoding="utf-8")
    for phrase in (
        "业务架构重构",
        "分级流程架构重构",
        "数据架构重构原则",
        "应用架构重构",
        "AI 技术架构重构",
        "法咪莉校长不是第六个业务域",
        "服务产品设计 AI 与校长的结合",
        "目标—五层架构对齐矩阵",
        "六引擎体验与商业修正",
        "拼多多：低门槛/社交传播/挑战营",
        "游戏化不能引入家庭总分",
    ):
        assert phrase in text


def test_core_blueprint_is_aligned_to_two_flywheels_and_global_scale() -> None:
    text = (ROOT / "docs/00_system/CORE_BLUEPRINT_GLOBAL_SCALE_ALIGNMENT.md").read_text(
        encoding="utf-8"
    )
    for phrase in (
        "家庭客户价值链",
        "平台商业增长飞轮",
        "FGCN 资源质量飞轮",
        "7 步是客户价值链；6 步是商业增长飞轮",
        "全局身份和租户边界",
        "多语言架构",
        "多租户架构",
        "千亿级家庭的规模设计",
        "Global Control Plane",
        "Regional Cell",
        "区域故障时",
    ):
        assert phrase in text


def test_benchmark_review_reorders_emotional_value_before_economic_value() -> None:
    text = (ROOT / "docs/00_system/ARCHITECTURE_BENCHMARK_REVIEW_V3.md").read_text(
        encoding="utf-8"
    )
    for phrase in (
        "对标可观察的产品机制",
        "被看见/被理解",
        "一个小胜利",
        "经济价值不能抢在情绪价值和成长证据之前",
        "P0 不是第八个业务域",
        "experience_curator",
        "CommercialGateService",
        "三环境功能等价",
    ):
        assert phrase in text
    adr_text = (ROOT / "governance/ADR/ADR-0026-emotional-first-gamified-experience.md").read_text(
        encoding="utf-8"
    )
    assert "experience_curator" in adr_text
    assert "禁止家庭总分" in adr_text


def test_family_needs_platform_extends_education_into_solution_orchestration() -> None:
    text = (ROOT / "docs/00_system/FAMILY_NEEDS_PLATFORM_TARGET_MODEL.md").read_text(
        encoding="utf-8"
    )
    for phrase in (
        "家庭教育切入",
        "家庭需求满足操作系统",
        "产品 Product",
        "服务 Service",
        "解决方案 Solution",
        "N0 需求信号",
        "N8 新需求回流",
        "N1 Family Need Orchestration",
        "SolutionBlueprintVersion",
        "高质量满足",
    ):
        assert phrase in text


def test_platform_spirit_is_a_governed_relationship_principle() -> None:
    text = (ROOT / "governance/ADR/ADR-0027-platform-spirit-we-are-family.md").read_text(
        encoding="utf-8"
    )
    for phrase in (
        "We are 伐木累！We are family！",
        "进入 Principal Soul",
        "家庭保留决定权",
        "AI 不能声称自己是家庭成员",
        "不能做总分、排名、比较",
        "无奈、疲惫",
        "伙伴资源聚合起来",
    ):
        assert phrase in text


def test_ui_baseline_is_a_regression_floor_not_a_product_ceiling() -> None:
    text = (ROOT / "docs/03_product/FAMILY_UX_EXPERIENCE_ARCHITECTURE.md").read_text(
        encoding="utf-8"
    )
    plan_text = (ROOT / "docs/11_delivery/AGILE_REBUILD_PLAN_V1.md").read_text(encoding="utf-8")
    for phrase in (
        "不是产品上限",
        "可以新增、合并、",
        "家庭需求中心",
        "服务案件跟踪",
        "迁移映射",
    ):
        assert phrase in text
    assert "UI 体验闸门" in plan_text
    for phrase in (
        "多模态体验架构",
        "MediaSession",
        "文字 / 语音 / 图片 / 音频 / 视频 / 互动卡片",
        "原始音频和文本分开留存",
        "InteractiveCard",
    ):
        assert phrase in text


def test_family_memory_is_scoped_to_child_guardian_and_relationship() -> None:
    text = (ROOT / "docs/07_data/FAMILY_MEMORY_ARCHITECTURE.md").read_text(encoding="utf-8")
    for phrase in (
        "Child Memory",
        "Guardian Memory",
        "Relationship Memory",
        "MemoryCandidate",
        "MemoryRetrieval",
            "不记录诊断标签",
            "完成证明",
        "多模态记忆",
    ):
        assert phrase in text


def test_principal_data_and_application_specs_exist() -> None:
    data_text = (ROOT / "docs/07_data/PRINCIPAL_AI_DATA_ARCHITECTURE.md").read_text(
        encoding="utf-8"
    )
    app_text = (ROOT / "docs/06_platform/PRINCIPAL_AI_APPLICATION_ARCHITECTURE.md").read_text(
        encoding="utf-8"
    )
    for table in (
        "principal_soul_versions",
        "principal_sessions",
        "principal_route_decisions",
        "principal_responses",
        "principal_action_proposals",
        "principal_feedback",
    ):
        assert table in data_text
    for boundary_field in (
        "global_id",
        "region_id",
        "content_locale",
        "model_locale",
        "policy_locale",
        "tenant_policy_version",
        "correlation_id",
        "causation_id",
    ):
        assert boundary_field in data_text
    for phrase in (
        "PrincipalApplicationFacade",
        "POST /principal/sessions/{session_id}/messages",
        "Named Action",
        "dev/test/prod",
    ):
        assert phrase in app_text


def test_all_registered_use_case_routes_have_a_principal_route() -> None:
    registry = yaml.safe_load(
        (ROOT / "governance/AI_USE_CASE_REGISTRY.yaml").read_text(encoding="utf-8")
    )
    route_values = {capability.value for capability in registered_capabilities()}
    for use_case in registry["use_cases"]:
        assert use_case["capability_route"] in route_values, use_case["id"]


def test_registered_principal_routes_match_ai_use_case_governance() -> None:
    registry = yaml.safe_load(
        (ROOT / "governance/AI_USE_CASE_REGISTRY.yaml").read_text(encoding="utf-8")
    )
    router = PrincipalCapabilityRouter()
    for use_case in registry["use_cases"]:
        internal = "operations_console" in use_case.get("application_surface", ())
        decision = router.resolve(
            PrincipalRouteRequest(
                request_id=f"contract:{use_case['id']}",
                tenant_id="tenant-contract",
                actor_type="governance-contract",
                entry_point=(
                    PrincipalEntryPoint.OPERATIONS_WORKBENCH
                    if internal
                    else PrincipalEntryPoint.ASK_PRINCIPAL
                ),
                capability=PrincipalCapability(use_case["capability_route"]),
                purpose="governance_contract_validation",
                data_class="OPERATIONAL_TEXT",
                context_snapshot_ref="context:governance-contract",
                consent_granted=True,
                global_id=f"principal-contract:{use_case['id']}",
                consent_version="consent.contract.v1",
                correlation_id=f"correlation:{use_case['id']}",
                causation_id=f"causation:{use_case['id']}",
                family_id=None if internal else "family-contract",
                subject_id=None if internal else "subject-contract",
            )
        )
        assert decision.agent_id == use_case["agent"], use_case["id"]
        assert decision.output_type.value == use_case["output_type"], use_case["id"]
        assert decision.risk_level.value == use_case["risk_level"], use_case["id"]
        assert decision.human_gate.value == use_case["human_gate"], use_case["id"]
        assert set(decision.allowed_tools) == set(use_case["allowed_tools"]), use_case["id"]
