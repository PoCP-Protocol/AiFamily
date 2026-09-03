# ADR-0018: 移动端采用语义路由并保留 UI 编号兼容层

- **Status**: Accepted
- **Date**: 2026-08-30
- **Deciders**: project-owner / chief-architect
- **Supersedes**: null
- **Superseded By**: null

## Context

`frontend/mobile/app/ui/` 当前有 34 个 `UI-*.tsx` 文件，共约 8,412 行。编号来自原型和验收材料，无法表达 assessment、journey、commerce、service 等业务职责。

实测还有以下耦合：

- `frontend/mobile/app/`、`components/` 与 `lib/` 中有 73 处 `/ui/UI-xx` 字面量。
- 34 个页面全部内联 `StyleSheet.create`，31 个页面直接引用 `familyApi`，28 个页面自行管理 `useEffect` 请求，33 个页面直接调用 router。
- 45 个前端测试中有 34 个通过 `readFileSync` 检查页面源码或文案，而不是验证用户行为。
- `app/ui/[id].tsx` 与静态 `app/ui/UI-02.tsx` 至 `UI-34.tsx` 并存；真正的 UI-01 首页则位于 `app/(tabs)/index.tsx`。
- `app.config.ts` 已启用 `typedRoutes`，但动态拼接后大量使用 `as Href`，路由类型保护被分散绕过。

`UI-xx` 对功能清单、设计稿和迁移审计仍有稳定追踪价值，不能直接删除。与此同时，测试环境和生产环境必须保持相同功能、流程与路由语义；迁移不得成为阉割功能或建立测试专用页面的理由。

## Decision

1. 新的正式入口使用按业务能力命名的语义路由，例如 `/assessment/session`、`/catalog/products/[productRef]`、`/services/offerings/[offeringRef]`。
2. `UI-01` 至 `UI-34` 继续作为 `legacyUiId`、设计验收编号和文档追踪键，不再作为新增功能的组件名或首选导航地址。
3. 迁移期保留现有 `/ui/UI-xx` 路由。语义路由先以薄适配入口复用同一个页面实现，不复制业务逻辑。
4. 所有 UI 编号到语义路由的转换集中在一个类型化 route registry。页面不得新增散落的 `/ui/UI-xx` 字符串。
5. 最终页面实现按领域放入 `features/<domain>/screens|components|hooks|api`；Expo Router 的 `app/` 文件只负责路由参数和页面装配。
6. 按领域逐批迁移并保持旧深链可用。每批先增加语义入口和测试，再抽离组件，最后替换内部导航。
7. 迁移不得改变测试与生产的功能集合。环境差异只能存在于数据、凭据、基础设施地址和外部副作用适配器。

## Alternatives Considered

### A. 一次性重命名全部 34 个页面

**支持理由**：可立即消除编号路由，最终目录一次成形，避免长期兼容层。

**否决理由**：当前多 Agent 同时修改多个页面，34 屏又有大量源码字符串测试和硬编码跳转。一次性修改会形成难以审查的大型变更，并高概率覆盖并发 WIP、破坏深链或掩盖功能回归。

### B. 永久保留 `UI-xx` 作为正式路由

**支持理由**：与现有设计稿、测试及功能清单完全一致，无迁移成本。

**否决理由**：编号不表达领域与资源关系，无法形成稳定的深链、参数约束和功能模块边界；新增页面只能继续依赖外部编号分配。

### C. 仅保留一个 `/ui/[id]` 动态页面

**支持理由**：路由文件最少，所有页面配置可由 registry 驱动。

**否决理由**：34 屏并非同构模板。测评会话、计划状态机、服务预约和商品详情有不同参数与行为；强行统一会把类型差异隐藏在运行时分支中。

## Consequences

### 正面

- URL、目录和业务能力边界一致，页面用途可从路径直接理解。
- `UI-xx` 追踪链与既有深链不会立即失效。
- 动态路由断言集中到兼容层，typed routes 可以逐步恢复实际保护作用。
- 可以按领域提取 hooks、API 与组件，无需等待全部 34 屏同时完成。

### 负面 / 代价

- 迁移期同一页面存在语义路由与编号路由两个入口。
- route registry 在迁移完成前需要维护兼容映射。
- 部分源码字符串测试必须逐步替换为路由和交互测试。

### 需要接受的风险

- 若只增加别名而长期不抽离页面，会形成永久双路由。必须用测试和迁移清单持续收敛。
- 外部收藏的旧深链无法确定何时完全消失，因此兼容路由的删除需要单独决策和遥测证据。

## Enforcement

- `frontend/mobile/lib/navigation/family-routes.ts` 集中维护语义路由和兼容映射。
- 单元测试验证已迁移 UI 编号的映射唯一、路径为语义路径，未知编号仍回退到旧入口。
- 当前已完成 home、assessment、journey、commerce、service、growth、community 与 family profile 的语义入口，覆盖 UI-01 至 UI-34，并额外包含测评结果子页 `UI-02-result`；“禁止新增散落编号路由”尚未建立全仓机械门禁，后续应增加只允许兼容层出现 `/ui/UI-xx` 的架构测试。
- 每批迁移必须通过 TypeScript、相关交互测试和 Expo 构建；不能只靠源码文案断言。

## References

- `frontend/mobile/app.config.ts`（`typedRoutes: true`）
- `frontend/mobile/app/ui/[id].tsx`
- `frontend/mobile/lib/family/ui-registry.ts`
- `docs/03_product/FUNCTIONAL_DECOMPOSITION.md`
- `governance/ADR/ADR-0017-capability-environment-promotion-gate.md`
- `.cursor/rules/environment-parity.mdc`
