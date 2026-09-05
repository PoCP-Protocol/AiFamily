# AiFamily Web Experience Studio

独立的 Web-only 体验工作台首个纵向切片。当前页面用文本和受保护图片引用创建一份
`DRAFT` 理解草案；所有模型/体验调用都经过 `ExperienceApiClient` seam。

## 本地运行

```bash
pnpm install
pnpm dev
pnpm test
pnpm typecheck
pnpm build
```

开发模式默认注入 `FakeExperienceApiClient`，返回值标记为 `SYNTHETIC_TEST`，只用于本地
开发和测试。生产构建使用 fail-closed 的 `HttpExperienceApiClient` 占位，不在浏览器读取
供应商密钥或直接调用模型；后端 Experience API 接入须保持同一 client 接口。

## 目录边界

- `src/api/client.ts`：前后端语义契约和状态/错误类型；
- `src/api/fakeClient.ts`：测试夹具，覆盖同意、准入、超时、人工和删除；
- `src/api/httpClient.ts`：未来同源 Experience API 接入点；
- `src/components/`：四个 Web 语义组件；
- `src/state/`：可测试的工作台状态机。

页面不导入 `frontend/mobile`、后端实现或任何供应商 SDK。
