# Family AI 统一 App / Web 客户端

`apps/mobile` 现在是 Family AI 的统一跨端产品入口，同时输出：

- iOS / Android App；
- 响应式 Web；
- UI-01 至 UI-34 的同一套路由、状态和 Family API 能力。

## 交互模式

- 小于 `1080px`：移动端模式，底部五 Tab。
- 大于等于 `1080px`：桌面 Web 模式，左侧主导航、中央内容舞台、右侧家庭上下文。
- 两种模式只改变布局，不改变业务页面、账户、数据源、权限、状态机或动作契约。

## 五个等价入口

1. 今天：家庭首页、今日行动与成长帮助。
2. 成长：测评、计划、成长旅程与回顾。
3. 发现：课程、内容、活动和家庭经验。
4. 服务：专家、咨询、活动与服务记录。
5. 我的：家庭档案、会员、权益和私密记录。

## 工程边界

- Web 不复制 Mobile 页面。
- 开发/测试环境允许调用真实 API key，但只能通过 Family API 的 Model Gateway 入口；Mobile 端不得读取 provider key，不得绕过 Family API 直连模型。
- 新增家庭业务能力必须统一走 Family API：Mobile UI → Family API → Model Gateway → Policy / Consent / Safety → Provider Adapter。
- `apps/mobile/server` 是 `QUARANTINED_TEMPLATE_COMPATIBILITY_RUNTIME`，仅保留历史 Expo 模板调试能力；其中 tRPC/MySQL/Express/LLM helper 不得扩展为第二套 Family 业务后台、身份系统、规范数据库或客户端直连模型路径。
- 34 个产品页面必须全部登记在 `lib/family/ui-registry.ts`；UI-35 不再是产品页面、路由或验收基线。
- `tests/cross-platform-parity.test.ts` 负责验证 Web 与 App 共享全部注册能力。
- 原 `apps/web` 仅保留旧的确定性工作台与兼容入口；面向家庭用户的新 Web 以本客户端为准。
