# ADR-0018: Media Avatar Provider 边界与 Gate1 Offline Benchmark

- **Status**: Accepted
- **Date**: 2026-09-03
- **Deciders**: project-owner / chief-architect（依据 FAMILY-MEDIA-001 审计）
- **Supersedes**: null
- **Superseded By**: null

## Context

FAMILY-MEDIA-001（`docs/13_research/technology/FAMILY_MEDIA_001_REALITY_AUDIT.md`，
`RESEARCH_ONLY`）确认：

1. AiFamily 内 **REAL_NEURAL_AVATAR_INFERENCE=ABSENT**。
2. 旧 Family 已建设 Avatar/Speech Gateway、Realtime Session、Viseme/Gaze、大量单测，
   但用户可见层停在 VBF-0 静态主图；`image + audio → neural avatar → talking-person`
   未打通。
3. 旧失败模式：`API PASS ∧ WebSocket PASS ∧ Unit Tests PASS` 被误读为数字人完成。
4. AUTOavantar（`D:\_reference\AUTOavantar`）是 offline 数字人视频工作流的
   **code-level reference**，根目录无明确 OSS LICENSE；内含 HeyGem/IndexTTS 硬绑定、
   SQLite、单线程 FIFO——不得整仓迁入。

需要一次架构冻结，使 Gate1 建设既落在 R10（唯一 AI Runtime），又不预押最终引擎，
也不把 Offline MediaJob 混入 Realtime 对话主链。

## Decision

1. **落点**：Offline Media Factory / Avatar Runtime 能力落在
   `backend/intelligence/media_factory/`（R10）。**不是**业务 Domain
   （禁止 `backend/domains/{avatar,ditto,musetalk,heygem,media}`）。
2. **Provider 化**：Avatar Engine 必须以 `AvatarProvider` 协议接入；禁止核心代码
   hard-bind 任一具体引擎（含 Ditto / EchoMimic / SadTalker / MuseTalk / HeyGem）。
3. **Offline ≠ Realtime**：Gate1 Offline Benchmark 与 Famili Realtime Runtime
   **永久分离**。禁止把 Offline MediaJob Queue 放入实时对话主链。
4. **引擎未决 + shortlist 可校正**：Gate1 ACTIVE shortlist 只接受能公平处理
   `static reference image + fixed audio → talking avatar video` 的引擎。
   当前 ACTIVE（FAMILY-MEDIA-002A）：Ditto / EchoMimicV3-Flash / SadTalker。
   MuseTalk / HeyGem 保留为 DEFERRED（非删除），因主路径分别偏向
   source-video lipsync 与 real-person video clone。
   `WINNER=UNKNOWN`，真实跑分前不得宣布胜出；shortlist 变更须有官方 upstream 证据。
5. **Human Visual Gate**：Gate1 最终裁决是人眼评审 schema；unit test 与 fixture
   通过 **不得** 等同于数字人 PASS。`IDENTITY_HARD_FAIL=true` 强制 GATE1=FAIL。
6. **AUTOavantar**：仅 REFERENCE + SELECTIVE REIMPLEMENTATION（checkpoint 概念、
   provider lifecycle、run isolation、artifact provenance 形态）。禁止搬入 SQLite、
   SimpleTaskScheduler、HeyGem/IndexTTS 引擎树。
7. **Identity 主参考**：Gate1 主 identity 输入为
   `FAMILI_V2_IDENTITY_MASTER_R01`（本机参考目录登记；见资产 registry）。
   旧 V1 smoke 图保留为历史冻结资产，不再作为主 identity。
8. **R9**：Media / Avatar Runtime **不得**写 Family canonical truth；产物是
   Artifact + Provenance，初始不可晋升为家庭事实。

## Consequences

- 本 ADR 只授权 **Gate1 Benchmark Foundation**（契约、runner、fixture、候选 manifest、
  人审 schema）。不授权完整 Media Workflow、队列、TTS 重设计、Realtime、模型安装。
- 新增代码必须登记 `MIGRATION_MANIFEST` + `DOMAIN_REGISTRY`；能力条目只登记本轮
  真实实现的 benchmark 能力，不得把未来 Media Factory 全景标成 IMPLEMENTED。
- FixtureAvatarProvider 必须自标 `gate1_eligible=false` / `real_neural_avatar=false`，
  且不得产出文件名 `FAMILI_REAL_AVATAR_V1.mp4`。

## Alternatives considered

### A. 把 Avatar 建成业务 Domain

否决：Avatar 是生成式推理 Provider，不是家庭权威状态所有者（R2/R10）。

### B. 先绑定 HeyGem（因 AUTOavantar 已跑通）

否决：许可有 MAU 阈值；硬绑定重复旧失败；Gate1 要求公平 static-image shortlist；
HeyGem 主路径为 real-person video clone（FAMILY-MEDIA-002A 归为 DEFERRED）。

### C. 用旧 Layered2D / 静图+音频作为 Gate1 输出

否决：直接违反 `NO VISIBLE FAMILI, NO DIGITAL-HUMAN PROGRESS` 与 HUMAN 视觉门。

## References

- `docs/13_research/technology/FAMILY_MEDIA_001_REALITY_AUDIT.md`
- `governance/REPOSITORY_CONSTITUTION.md` R7 / R9 / R10
- `docs/05_ai/AI_NATIVE_PRINCIPLES.md`
- ADR-0005（AI 原生）、ADR-0001（Python-only）
