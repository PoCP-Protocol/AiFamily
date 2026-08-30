# AiFamily Customer Web

AiFamily 客户 Web 将移动端 UI 需求重新组织为面向家庭业务流程的 Web 工作空间，覆盖理解家庭、成长计划、今日行动、家庭时光、专业支持、家庭互助以及权益与家庭。视觉采用行动橙、信任蓝与成长绿，并在成长流中使用纵向单焦点内容、非竞争式成就和多模态记录。

## 本地运行

```bash
pnpm install --frozen-lockfile
pnpm dev
```

执行静态检查与生产构建：

```bash
pnpm check
pnpm build
```

## 运行边界

此目录目前是纯前端 React 19 应用。未设置 `VITE_FAMILY_API_BASE_URL` 时，页面显示“体验数据模式”，不会把家庭内容发送给后端。`client/src/lib/family-api.ts` 只声明当前 `family_api` 已挂载的 Assessment 路由，以及受 `VITE_ENABLE_DEV_SERVICE_CONTRACT=true` 显式门控的开发期 Service 路由。

多模态记录会调用浏览器媒体权限进行本地录音和预览。语音转写结果与图像场景标签是**明确标注的可用性测试模拟**；图片尺寸、格式和亮度在浏览器本地计算。模拟服务预约与 Consent 保存在浏览器 `localStorage`，不会扣款、锁定时段、联系顾问或写入生产系统。

## 主要目录

| 目录 | 职责 |
|---|---|
| `client/src/pages/` | 场景工作空间与客户流程 |
| `client/src/components/` | 客户壳、多模态记录与成就反馈组件 |
| `client/src/lib/family-api.ts` | 当前 FastAPI 强类型适配层 |
| `client/src/lib/mock-service.ts` | 可用性测试专用的模拟服务、Consent 与预约状态 |
| `docs/customer-web-scenario-blueprint.md` | 34 个 App UI 需求证据到 Web 业务场景的重设计蓝图 |
| `ideas.md` | 品牌、布局、动效和交互设计决策 |

## 视觉资产

当前图片使用 Manus WebDev 的持久化 `/manus-storage/...` 地址。在其他托管环境部署前，应把这些资源迁移到团队管理的对象存储或 CDN，并保持原 URL 映射。不得把家庭媒体、测试上传文件或浏览器本地数据提交到仓库。

## 后端联调建议

Assessment 可优先接入真实 API。服务预约目前仍使用模拟数据；切换到真实 Service API 时，必须保留 Bearer 身份、`Idempotency-Key`、`X-Correlation-Id`、Consent 引用、家庭范围校验和 `REQUESTED`/人工确认语义，不能把前端模拟状态视为权威记录。
