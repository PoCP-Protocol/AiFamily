---
id: FAMILY-NEEDS-PLATFORM-001
title: Family 家庭需求满足平台目标模型
type: target-architecture
status: draft
version: 0.1
owner: chief-architect
created: 2026-08-30
updated: 2026-08-30
canonical: false
---

# Family 家庭需求满足平台目标模型

## 1. 战略定位

Family 以家庭教育切入，但不以“卖课程”作为终点。它最终成为家庭需求满足操作系统：
教育是建立信任、理解家庭、验证
服务交付和沉淀方法论的第一入口；平台最终围绕家庭真实需求，组织高质量资源，提供
标准产品、真人服务和组合解决方案。

```text
家庭教育入口
  → 家庭需求理解
  → 需求分层与优先级
  → 产品/服务/解决方案选择
  → FGCN 资源组织
  → 高质量交付与验收
  → 结果证据与持续陪伴
  → 新需求与长期关系
```

### 1.1 三种供给形态

| 形态 | 定义 | 适用场景 | 权威事实 |
|---|---|---|---|
| 产品 Product | 标准化、可复用、可定价的内容/课程/工具/会员权益包 | 高频、低差异需求 | Product/Order/Entitlement |
| 服务 Service | 由人或受治理 AI 协助完成的交付过程 | 需要互动、陪伴、判断和补救 | ServiceCase/Task/Delivery/Quality |
| 解决方案 Solution | 围绕一个家庭需求组合多个产品、服务、资源和阶段 | 复杂、长期、跨角色需求 | SolutionBlueprint/JourneyPlan/Case |

解决方案不是“商品打包页面”，而是目标、边界、阶段、责任人、资源、SLA、验收和
失败补偿均明确的可执行蓝图。AI 可以帮助设计草案，但只能由业务/运营 Named Action
发布和接线。

## 2. 家庭需求闭环

```text
N0 需求信号
  → N1 需求澄清
  → N2 需求分级
  → N3 方案设计
  → N4 资源组织
  → N5 交付执行
  → N6 质量验收
  → N7 结果与关系
  → N8 新需求回流
```

| 节点 | 输入 | 活动 | 输出 | 规则 |
|---|---|---|---|---|
| N0 需求信号 | 测评、对话、主动搜索、服务反馈、家庭表达 | 记录来源、目的和原话 | NeedSignal | 原始信号与 AI 推断分开 |
| N1 需求澄清 | NeedSignal、家庭上下文、可见性 | 家庭/顾问确认场景和期望 | FamilyNeed | 不替家庭定义需求，不给家庭贴标签 |
| N2 需求分级 | FamilyNeed、风险、时效、复杂度 | 区分教育问题、关系问题、服务问题、生活支持问题 | NeedProfile | 高风险先人工；未授权主体不进入推荐 |
| N3 方案设计 | NeedProfile、组件、产品、服务、资源容量 | 生成方案草案和取舍 | SolutionDraft | 必须声明适用/排除条件、成本、SLA和验收 |
| N4 资源组织 | SolutionDraft、ProviderCapability、权限 | 建 ServiceCase、拆任务、授权匹配 | AssignmentPlan | 资源不足返回 RESOURCE_GAP，不伪造供给 |
| N5 交付执行 | AssignmentPlan、BlueprintVersion | 产品交付、真人服务、家庭行动和过程记录 | DeliveryRecord | 一任务一责任人；过程可暂停、改派、补救 |
| N6 质量验收 | DeliveryRecord、家庭反馈、专业验收 | 质量检查、返工、投诉和补偿 | QualityDecision | VERIFIED 后才产生贡献和结算依据 |
| N7 结果与关系 | OutcomeEvidence、Feedback、会员/权益 | 形成结果故事、后续建议和复购意向 | Outcome/NextNeed | 结果由家庭/服务人员确认，不是 AI 自判 |
| N8 新需求回流 | 新信号、未解决项、质量缺口 | 回到需求池、知识和产品改进 | NewNeed/ImprovementCandidate | 不把家庭私有内容直接写入公共知识 |

## 3. 五层架构映射

### 3.1 业务架构

```text
X0 Experience & Trust
B1 Family Education & Growth OS     # 教育入口和成长主线
N1 Family Need Orchestration        # 跨域需求理解、分级和解决方案编排
B2 FGCN Resource Collaboration      # 案件、任务、资源、质量、贡献
B3 Product & Service Commerce       # 产品、服务、会员、权益、订单
B4 Family Trust & Community         # 家庭关系、社区、权利和安全
B5 Platform Evolution               # 内容、知识、AI、运营、实验、治理
```

N1 是新增的跨域核心能力，但不取代 B1、B2、B3 或 B4：它负责需求到解决方案的编排，
具体事实仍由家庭、服务和商业域拥有。法咪莉校长跨越 X0/B1/B2/B5，负责理解、
解释、推荐和陪伴，不直接拥有需求、订单或交付事实。

### 3.2 流程架构

```text
L0 家庭需求价值流
  L1 需求进入 / 教育成长 / 方案编排 / 资源协作 / 交付验收 / 关系经营
    L2 N0-N8 需求闭环
      L3 产品化、服务化、解决方案化子流程
        L4 API / Command / Event / Job / Human Task
```

教育的 21 天、90 天和年度陪伴是 B1 的成熟场景；当家庭需求超出教育范围时，
由 B2 进入服务/产品/解决方案编排，而不是强行把所有需求包装成课程。

### 3.3 数据架构

主数据和业务数据建议增加：

```text
FamilyNeed
NeedSignal
NeedProfile
MediaAsset
MediaTranscript
MediaEvidence
SolutionDraft
SolutionBlueprintVersion
ProviderCapability
ResourceAvailability
AssignmentPlan
DeliveryRecord
QualityDecision
OutcomeEvidence
NextNeed
```

推荐关系：

```text
NeedSignal → FamilyNeed → NeedProfile → SolutionBlueprintVersion
  → ServiceCase → ServiceTask → Assignment → DeliveryRecord
  → QualityDecision → Contribution/Settlement
  → OutcomeEvidence → NextNeed
```

`SolutionBlueprintVersion` 冻结产品、服务、资源、角色、SLA、成本、验收和风险；
历史案件只引用版本，不被后续设计修改。所有对象继承 `tenant_id`、`region_id`、
`family_id`、`subject_ids`、`purpose`、`consent_version`、`data_class`、locale、
`provenance_ref` 和 `deletion_ref`。

多模态证据单独建模：原始语音/图片/视频是 `MediaAsset`，转写/OCR 是
`MediaTranscript`，经授权的引用才形成 `MediaEvidence`。三者不能混成一个文本字段，
也不能绕过删除、主体范围和内容安全直接进入 Context 或知识库。

### 3.4 应用架构

```text
Family Need Application
  ├─ NeedCaptureApplication       # 测评、搜索、对话、反馈
  ├─ MultimodalExperience         # 语音、图片、音频、视频、互动卡片
  ├─ NeedClarificationApplication # 家庭/顾问澄清和确认
  ├─ SolutionApplication          # 产品/服务/方案草案和比较
  ├─ ResourceOrchestration        # FGCN 案件、任务、授权、匹配
  ├─ DeliveryQualityApplication   # 交付、验收、补救、贡献
  └─ RelationshipApplication     # 结果、会员、复购、推荐和新需求
```

34 UI 仍是家庭体验基线：教育相关 UI 提供第一入口；服务、商城、会员、社区和资产
是需求满足的不同出口；运营端负责供给、产品、知识、质量和发布。任何新 UI 都必须
关联一个 N0-N8 节点、权威数据对象和 Named Action。

### 3.5 AI 技术架构

法咪莉校长增加四种受治理能力：

1. `need_interpreter`：把家庭表达整理成可讨论的需求假设，不给家庭贴诊断标签；
2. `solution_architect`：组合产品、服务、组件和资源形成解决方案草案；
3. `resource_coordinator`：解释资源匹配和缺口，不直接分派或承诺交付；
4. `service_guardian`：陪伴交付、识别风险、准备补救建议，不自行关闭投诉。

这些能力统一经过 Context、Knowledge、Capability Registry、多模态解析/生成能力、Model Gateway、Safety、
Human Gate 和 Provenance。AI 输出始终是 Perspective、Draft、Recommendation、
ActionProposal 或 HumanTask；家庭需求确认、资源分派、质量验收、订单权益和结果确认
必须由家庭/人工/业务 Named Action 完成。

## 4. 质量组织原则

- 家庭只有一个对外关系入口；内部可以由多个资源角色协作，但家庭不被迫理解平台组织结构。
- 一个家庭需求对应一个可追踪的 SolutionCase；一个任务对应一个责任人和交付物。
- 资源按能力、可用性、区域、语言、资质、SLA 和历史质量匹配，不按隐形关系或家庭排名分配。
- “高质量满足”必须有交付证据、验收、返工/补救和反馈闭环，不等同于 AI 给出好答案。
- 平台可以复用匿名化的组件质量和服务质量，但不能把家庭私有事实复制到公共资源或知识库。

## 5. 全球化与环境等价

多租户共享控制面、隔离数据面；多语言区分用户语言、内容语言、模型语言和政策语言；
区域 Cell 负责家庭数据、知识索引、人工运营和删除边界。开发、测试、生产必须拥有相同
的需求澄清、方案编排、资源匹配、交付、质量、商业闸门和错误码，测试只替换合成数据
和外部适配器。

## 6. 建设顺序

1. 以家庭教育为第一个需求模板，完成 N0-N8 的单家庭闭环。
2. 将 21 天/90 天教育方案抽象为 `SolutionBlueprintVersion`。
3. 接入 FGCN 资源能力、ServiceCase、Task、Quality 和 Contribution。
4. 扩展产品、服务和组合解决方案目录，形成需求到供给的编排应用。
5. 再建设跨区域、多语言、多租户和规模化 Cell，不以“先上商城”替代需求闭环。
