---
id: COURSE-PRODUCT-INTEGRATION-001
title: 24节课程融入服务产品设计平台的产品与课件体系
type: product
status: draft
version: 0.1
owner: chief-architect
created: 2026-09-08
updated: 2026-09-08
canonical: false
---

# 24节课程融入服务产品设计平台

## 1. 定位

24节课程不是独立的课程后台数据，而是一个可被 IPD 决策、PDM 复用、PLM 发布的
`CourseProduct`。它同时承担三种角色：

1. **知识结构**：24 个可编排的学习单元，按 6 个阶段、每阶段 4 节组织；
2. **服务产品骨架**：每节课必须连接家庭问题、行动任务、服务角色、验收证据和暂停/升级路径；
3. **课件资产容器**：PPT、图片、视频、音频、工作表等都是可版本化的 `CoursewareArtifact`，而不是课程正文里的附件。

## 2. 平台对象关系

```text
MarketInsight / DemandFrame
        ↓
ProductPackage (21天 / 90天 / 专题服务产品)
        ↓
CourseSystemVersion (6阶段 × 24课时)
        ↓
CourseContentVersion (每节的知识点、行动、教练与结果指标)
        ↓
CoursewareBOM (每节课引用的课件资产版本)
        ↓
Pilot / ReleaseBaseline / LifecycleDecision
```

`CourseSystem` 是产品级课程地图，`CourseContent` 是教学内容聚合，`Courseware BOM`
是资产配置清单。三者必须分开版本，才能做到局部换课件、整套回滚和跨产品复用。

## 3. 24节课程的最小主数据

每个课时除现有 `lesson_id/sequence/title/knowledge_point/action_task` 外，产品平台
必须能追溯以下关系（可先通过 `stage_id`、`bom_line_ref` 和版本引用承载）：

- `problem_refs`：来自需求/市场洞察的授权问题证据；
- `learning_outcome`：可观察的家庭行动结果，不是家庭总分；
- `component_refs`：复用的成长组件与版本；
- `skill_refs`：AI 教练、内容生成、反馈解释等技能版本；
- `service_role` 与 `human_gate_policy`：谁交付、何时必须人工确认；
- `asset_bundle_version_ref`：课件资产包版本；
- `evidence_refs`：事实、方法和内容准确性凭证；
- `pilot_metrics`：采纳、完成、质量、成本和安全指标；
- `pause_rule/rollback_rule`：风险或质量异常时的停止与回退。

## 4. 课程产品化方式

同一套 24 节课通过不同 `ProductPackage` 形成不同服务产品，而不是复制课程：

| 产品形态 | 课程使用方式 | 课件交付 |
|---|---|---|
| 7天探索试点 | 选择 4 节（一个阶段）验证问题与行动 | 讲义 + 行动卡 |
| 21天成长营 | 选择 3 个阶段或 21 节，保留每日行动与复盘 | PPT + 图片卡 + 工作表 |
| 90天成长计划 | 6 阶段完整 24 节，绑定教师/教练服务 | 全部课件包 + 服务手册 + 复盘报告 |
| 专题服务 | 从 24 节中按问题证据组合 Pattern | 针对场景的资产变体 |

产品包引用课程版本，不能修改已发布课程；任何调整生成新的 `CourseSystemVersion` 或
`CourseContentVersion`，由 PLM 进行试点、发布、暂停、回滚或退役。

## 5. AI 在体系中的职责

AI 经 Model Gateway 运行以下可审计技能：

- 根据 DemandFrame 选择候选课时组合，输出 Draft；
- 为每节课生成 PPT/图片/视频等课件变体，保留模型、提示词、知识和素材 provenance；
- 检查课时输入输出、阶段覆盖、课件 BOM、版权、安全和事实引用；
- 基于试点反馈提出 REVISE/SCALE/KILL 建议。

AI 不直接发布课程、不写入家庭成长事实、不替代教师或产品闸门。发布和敏感内容必须通过
人工 Gate，结果进入 PLM 生命周期记录。

## 6. 当前代码落位与下一切片

- `backend/domains/product_intelligence/domain/course_system.py`：6阶段、24课时覆盖和课件 BOM；
- `backend/domains/product_intelligence/domain/course_content.py`：课程内容与人工审核生命周期；
- `backend/intelligence/product_management/course_release_baseline.py`：将24课时、技能、资产和证据编译为 PLM ReleaseBaseline；
- `frontend/web/src/productStudio/`：课程设计、课时编辑、课件治理与发布工作台。

下一纵向切片是 **“课程目录 → 产品包绑定 → 课件 BOM 预览 → 发布基线”**：Web UI 读取已发布
课程系统，允许产品经理选择课程阶段和课件版本，调用编译器生成 DRAFT ReleaseBaseline，
再由人工 Gate 决定是否进入试点。该切片不新增家庭事实，也不绕过现有课程审核。

## 7. 验收标准

1. 24 节课能在一个 `CourseSystemVersion` 中按阶段完整覆盖且无重复；
2. 一个课时能绑定多个课件资产版本，重新生成不覆盖已发布版本；
3. 21 天和 90 天产品包可复用同一课程组件但引用不同的产品包版本；
4. 发布基线包含课程、课件、技能、知识/证据、回滚和运行手册引用；
5. 课程发布、课件发布和家庭交付事实三者权限边界清晰并可审计。
