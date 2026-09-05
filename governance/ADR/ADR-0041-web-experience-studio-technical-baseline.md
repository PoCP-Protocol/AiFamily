---
id: ADR-0041
title: 独立 Web Experience Studio 技术基线与体验 API 边界
status: proposed
date: 2026-08-30
owner: project-manager
---

# ADR-0041：独立 Web Experience Studio 技术基线与体验 API 边界

- **Status**: Proposed
- **Date**: 2026-08-30
- **Deciders**: project-manager / chief-architect
- **Supersedes**: null
- **Superseded By**: null

## Context

本 ADR 只解决 Web 体验工作台的技术基线和边界，不代表 Web 工程已经完成。

仓库当前的正式系统清单仍将前端描述为 `TypeScript (Expo / React Native)`
（`docs/00_system/SYSTEM_MANIFEST.md:32`），而不是独立的 Web 应用。Web 体验契约明确记录：
当前没有 `frontend/web`，`frontend/mobile` 是 Expo/React Native 工程，不能用移动工程的
Web 输出替代 Web 产品（`docs/08_experience/WEB_EXPERIENCE_STUDIO_CONTRACT.md:17-18`）。
该契约同时冻结了首个纵向切片和 `ExperienceApiClient` seam（同文件 `:23-35`、`:66-84`），
并要求浏览器级测试只验证 Web UI 与 client seam，不把 fixture 结果宣称为模型质量
（同文件 `:119-126`）。

现有移动工程的 `frontend/mobile/package.json` 证实仓库已经使用 React 19.1、React DOM、
TypeScript 5.9 和 Vitest 2.1（`:58-60`、`:91-92`），但其入口是 `expo-router/entry`，
开发服务是 Expo Metro（`:5`、`:9`），同时包含 React Native、Expo Router 和原生模块。
这说明可以复用 React/TypeScript 的工程经验，却不能据此推导出一个独立 Web 构建链已经存在。

AI 原生原则要求 AI 是核心体验主路径，但输出不能自动成为业务事实，模型调用必须经统一
Model Gateway（`docs/05_ai/AI_NATIVE_PRINCIPLES.md` §1–§3；`governance/ADR/ADR-0024-ai-technical-architecture-governed-runtime.md`）。
因此浏览器不能携带供应商密钥、直接调用模型，或把 Draft 转换成 Family/Journey/Service/
Commerce 事实。体验应用边界和多模态供应商无关路由分别由 ADR-0031 与 ADR-0039 约束。

## Decision

### 1. 建立独立 Web 应用

新建 `frontend/web`，采用以下技术基线：

- React 19 + TypeScript 5.9；
- Vite 作为纯客户端构建与开发服务器，生产产物为静态 `dist`；
- pnpm 作为前端依赖管理工具（与现有移动工程的 `packageManager: pnpm@11.1.3` 保持一致），
  但 Web 与 Mobile 分别拥有 manifest、配置和测试入口；本 ADR 不创建或改造 workspace；
- Vitest 用于组件、状态机和 API client contract 测试；Playwright 用于桌面浏览器验收；
- 组件测试使用可注入 fake `ExperienceApiClient`，真实后端联调用 sandbox/测试环境完成。

Vite 只负责静态 Web 资源，不承载 AI 代理、供应商 SDK 或秘密。生产部署由现有 Web/API
入口提供静态资源，并通过同源或显式配置的 HTTPS API 调用 AiFamily 后端。

### 2. 以 `ExperienceApiClient` 作为唯一前后端 seam

Web 组件只依赖 `ExperienceApiClient` 语义接口，至少提供：

```text
createDraft(input, idempotencyKey)
decide(input, idempotencyKey)
submitFeedback(input, idempotencyKey)
requestHuman(input, idempotencyKey)
deleteRun(runId, idempotencyKey)
```

实现层分为三种可替换 client：

1. `FakeExperienceApiClient`：仅用于单元/组件测试，所有返回都标记为
   `SYNTHETIC_TEST`，不得挂载生产路由；
2. `SandboxExperienceApiClient`：调用后端 sandbox，验证权限、同意、幂等、错误语义和
   Model Gateway fail-closed 行为；
3. `HttpExperienceApiClient`：生产实现，只调用 AiFamily 的 Experience API，不直接知道
   Qwen、Gemini、OpenAI 或其他供应商 URL/SDK。

`ExpressionInput → RunStatus → DraftResult → DecisionActions` 是第一条 Web 纵向切片。
组件只展示 `DRAFT`、provenance、限制和人工确认状态；组件不得导入
`backend/intelligence/model_gateway`、领域 repository 或任何供应商包。

### 3. Web-only 与多模态边界

- `frontend/web` 不复制 `frontend/mobile` 的路由、主题、组件或状态实现；未来如需共享，
  只能先提取经过审计的无平台语义契约，并单独记录决策；
- 前端提交媒体引用和元数据（例如 `media_type`、`uri`、`mime_type`、`sha256`），不提交
  供应商格式对象，不在浏览器保存供应商凭据；
- 当前切片支持文本 + 图片引用；音频、视频和互动卡片只有在 Model Gateway、供应商准入、
  合规、评测及删除证明齐备后，按同一 client seam 增量开启；
- 前端永远不能把 AI 输出升级为 Fact、成长分数、家庭总分或家庭排名。确认动作只发起
  Named Action/Human Gate 请求，最终事实写入由后端领域流程完成。

### 4. 用户体验与可访问性基线

Web 工作台以“低摩擦、可解释、可恢复”为体验目标，允许游戏化表达但不制造焦虑或虚假成就：

- 目标 WCAG 2.2 AA；所有核心动作支持键盘、屏幕阅读器和清晰焦点顺序；
- `RunStatus` 的每个状态都有可理解的文本和下一步操作；错误、拒绝、超时、重试、人工
  请求、删除与成功路径同等可见；
- 动效提供 `prefers-reduced-motion` 降级，成就文案只基于后端真实事件，不由前端计分或排名；
- 多模态输入展示受保护的引用和删除状态，不将儿童原始媒体复制到不受控缓存。

## Alternatives Considered

### A. 复用 `frontend/mobile` 的 Expo Web 输出

支持理由：已有 React、TypeScript、React DOM、路由和 Vitest，短期可以少建目录。

否决理由：正式契约已明确移动工程不能替代 Web 产品；Expo Router、Metro 和原生模块会把
移动生命周期、主题与依赖带入桌面 Web，违反 Web-only 独立演进和“不得复制移动端”的边界。

### B. Next.js（SSR/全栈 Web）

支持理由：路由、SSR、缓存和部署生态成熟，适合内容型站点。

否决理由：本子项目首要问题是受治理的体验 API seam，而不是服务端渲染；引入第二个服务端
运行时会模糊唯一 Python 后端与 Model Gateway 边界，并增加凭据、缓存和数据删除的审计面。
若未来有明确 SSR 证据，应通过新 ADR 重新评估，不能在实现中隐式切换。

### C. Vue 或其他前端框架

支持理由：同样可以实现纯 Web、组件化和可访问性。

否决理由：仓库已有 React/TypeScript 工程经验和 React DOM 依赖；换用新生态不能解决当前
缺失的 Web 工程和 API seam，反而增加团队学习与测试基线成本。该否决基于仓库证据，不是
对框架能力的普遍判断。

### D. 原生 HTML/少量脚本

支持理由：依赖最少、静态部署简单。

否决理由：体验工作台需要可测试的状态机、可注入 client、错误恢复、多人协作组件和后续
多模态扩展；没有组件运行时会把状态边界重新散落到页面脚本中，无法满足契约中的纵向切片。

## Consequences

### 正面

- Web UI 与移动端解耦，可以独立迭代桌面交互和多模态创作体验；
- `ExperienceApiClient` 把 AI、同意、幂等、人工闸门和删除语义集中在可替换 seam；
- Vitest + Playwright 将状态契约和浏览器体验分层验证，便于敏捷纵向交付；
- Vite 静态部署保持唯一后端和 Model Gateway 边界，前端不会成为第二个 AI 后端。

### 负面 / 代价

- 需要新建一套 Web manifest、构建配置、设计系统和测试基线；
- React 组件不能直接搬运 React Native 组件，前期需要建立 Web 语义组件；
- Playwright 与可访问性测试增加 CI 时间和维护成本；
- 首个 Sprint 必须先完成 client seam 和状态机，不能用静态 mock 页面冒充端到端能力。

### 需要接受的风险

- 当前没有 `frontend/web`，本 ADR 的技术可行性仍需首个纵向切片验证；
- 当前 Model Gateway 的生产供应商准入未完成，Sandbox 成功不代表生产模型能力已上线；
- 若未来共享类型直接从后端生成，需另行审计生成链和删除/隐私字段，不能直接导入 Python
  实现或供应商 schema。

## Enforcement

当前仅为 Proposed 决策，仓库尚无 `frontend/web` 代码，以下为必须随实现 PR 补齐的执行项：

1. `frontend/web/package.json`、Vite、TypeScript、Vitest 和 Playwright 配置必须独立存在，
   并在 CI 中执行 typecheck、unit/contract、browser tests；
2. 架构测试禁止 `frontend/web` 导入 `frontend/mobile`、供应商 SDK、模型密钥读取路径，
   并检查所有生产 API 调用经过 `ExperienceApiClient`；
3. 浏览器验收必须覆盖 consent 缺失、provider 未准入、超时重试、幂等、人工请求和删除，
   且明确标注 fake fixture 不代表模型质量；
4. 可访问性检查至少覆盖键盘路径、焦点管理、状态播报和 reduced-motion；
5. 任何新增模态或改变 AI 输出/人工闸门的行为，必须先更新相应契约、Model Gateway/合规
   评测证据，并按 ADR 规则记录架构变化。

在这些检查落地前，本 ADR 不能被解释为“Web 工程已完成”或“供应商已获准生产调用”。

## References

- `docs/00_system/SYSTEM_MANIFEST.md:32` —— 当前正式前端技术身份；
- `docs/00_system/CURRENT_SYSTEM_BASELINE.md` —— 当前系统四区基线与移动端未接后端事实；
- `docs/08_experience/WEB_EXPERIENCE_STUDIO_CONTRACT.md` —— Web-only 页面、client seam、状态和验收契约；
- `docs/05_ai/AI_NATIVE_PRINCIPLES.md` —— AI 原生、Draft-only 和 Model Gateway 约束；
- `governance/ADR/ADR-0005-ai-native-platform.md` —— AI 原生平台定位；
- `governance/ADR/ADR-0024-ai-technical-architecture-governed-runtime.md` —— 受治理 AI Runtime；
- `governance/ADR/ADR-0031-experience-gateway-application-boundary.md` —— Experience Gateway 边界；
- `governance/ADR/ADR-0039-multimodal-provider-neutral-routing.md` —— 多模态供应商无关路由；
- `frontend/mobile/package.json` —— 已存在的 React/TypeScript/Vitest/Expo 证据。
