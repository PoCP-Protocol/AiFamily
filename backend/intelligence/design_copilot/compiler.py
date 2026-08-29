"""ProductCompiler — STRUCTURE_ONLY, signatures only.

Method set and check names taken verbatim from the project-owner's original
proposal's compiler-check table (reconciled in
`architecture/FAMILY_PRODUCT_INTELLIGENCE_PLATFORM_TARGET_ARCHITECTURE_DRAFT_001.md`
§4, Composable Product Factory). Every method raises `NotImplementedError` —
this class is not called from anywhere; it exists so the 12-check surface is
agreed on in code before any check is actually implemented, which requires
Batch 7 authorization.

Imports `ProductDefinition` from `backend.domains.product_intelligence` —
that domain is the sole canonical source for this business entity (see
`governance/MIGRATION_MANIFEST.yaml` → `product_intelligence_v2`, and the
`packages_contracts_provenance` entry's note about `product_factory.py`
being retired as a duplicate canonical source).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # Type-only import. The AI Runtime isolation rule (MIGRATION_PLAN_V2.md §0)
    # is written about repositories and the persistence layer, and an entity type
    # is neither — but the direction of the dependency is still wrong: nothing
    # under backend/intelligence/ should require a business domain to be
    # importable in order to load.
    #
    # Under TYPE_CHECKING the arrow exists for type checkers and readers and does
    # not exist at runtime, which is the honest state for a module whose every
    # method raises NotImplementedError and which has zero callers.
    #
    # When this compiler is actually implemented (Batch 7 authorization), the
    # right shape is a Protocol or a shared contract type, not a domain entity.
    from backend.domains.product_intelligence.domain.entities import ProductDefinition


class CompilerCheckResult:
    def __init__(self, passed: bool, detail: str):
        self.passed = passed
        self.detail = detail


class ProductCompiler:
    """Validates a `ProductDefinition` (FPDL) before it can move from DRAFT
    to COMPILED status (`packages/contracts/versioned.py` `VersionStatus`).
    """

    def check_schema(self, product: ProductDefinition) -> CompilerCheckResult:
        """产品定义本身是否合法(Pydantic 校验通过之外的业务级 schema 规则)。"""
        raise NotImplementedError("待 Batch 7 授权后实现,当前仅占位签名")

    def check_component(self, product: ProductDefinition) -> CompilerCheckResult:
        """所需 Component 是否都在 Component Catalog 里存在。"""
        raise NotImplementedError("待 Batch 7 授权后实现,当前仅占位签名")

    def check_compatibility(self, product: ProductDefinition) -> CompilerCheckResult:
        """引用的 Component/Pattern 版本是否互相兼容。"""
        raise NotImplementedError("待 Batch 7 授权后实现,当前仅占位签名")

    def check_workflow(self, product: ProductDefinition) -> CompilerCheckResult:
        """stages 之间是否存在死循环/不可达状态。"""
        raise NotImplementedError("待 Batch 7 授权后实现,当前仅占位签名")

    def check_resource(self, product: ProductDefinition) -> CompilerCheckResult:
        """所需资源槽位(真人/专家)是否有可交付来源。"""
        raise NotImplementedError("待 Batch 7 授权后实现,当前仅占位签名")

    def check_ai_use_case(self, product: ProductDefinition) -> CompilerCheckResult:
        """引用的 AI Use Case 是否已在 AI Use Case Registry 里注册且有效。"""
        raise NotImplementedError("待 Batch 7 授权后实现,当前仅占位签名")

    def check_context_boundary(self, product: ProductDefinition) -> CompilerCheckResult:
        """Context 访问权限是否越界(跨家庭/跨租户)。"""
        raise NotImplementedError("待 Batch 7 授权后实现,当前仅占位签名")

    def check_safety(self, product: ProductDefinition) -> CompilerCheckResult:
        """是否违反未成年人相关规则。"""
        raise NotImplementedError("待 Batch 7 授权后实现,当前仅占位签名")

    def check_human_gate(self, product: ProductDefinition) -> CompilerCheckResult:
        """高风险场景是否配置了 human_trigger。"""
        raise NotImplementedError("待 Batch 7 授权后实现,当前仅占位签名")

    def check_cost(self, product: ProductDefinition) -> CompilerCheckResult:
        """预估 AI/人工成本是否超标。"""
        raise NotImplementedError("待 Batch 7 授权后实现,当前仅占位签名")

    def check_evaluation(self, product: ProductDefinition) -> CompilerCheckResult:
        """是否配置了 evaluation suite。"""
        raise NotImplementedError("待 Batch 7 授权后实现,当前仅占位签名")

    def check_sla(self, product: ProductDefinition) -> CompilerCheckResult:
        """服务承诺(响应时限等)是否可执行。"""
        raise NotImplementedError("待 Batch 7 授权后实现,当前仅占位签名")
