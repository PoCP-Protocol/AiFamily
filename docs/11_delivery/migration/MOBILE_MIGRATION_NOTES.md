# Mobile 前端迁移记录 (frontend_mobile)

- **日期**: 2026-08-29
- **来源**: `D:\family-ai\50_开发_dev\apps\mobile`（只读，未做任何修改/删除）
- **目标**: `D:\AiFamily\frontend\mobile`
- **依据**: `governance/MIGRATION_MANIFEST.yaml` 中 `frontend_mobile` 条目的
  `project_owner_override`（2026-08-29，project-owner 明确指示整体迁移，推翻此前
  "KEEP_NON_PYTHON 留在源仓库"的处置），以及 `REPOSITORY_CONSTITUTION.md` R1
  （唯一后端是 Python，但前端不要求 Python 化，继续 TypeScript / React Native）。

## 迁移范围与验证

- 复制文件数：**411 个文件，35.62 MB**（源目录与目标目录逐字节比对一致：文件数、
  总大小完全相等）。
- **不包含** `node_modules/`（源目录里是 pnpm 符号链接，直接 `copytree` 会把链接
  展开成 196MB 的真实依赖树，属于可重装的构建产物，已在拷贝后从目标里删除）与
  `dist/`（esbuild 构建产物）。这两者按任务要求本轮不做 `npm install`/构建，因此
  不迁移，未来在目标位置执行 `pnpm install` 即可重新生成。
- 保留了全部源代码子目录：`app/`（含 `(tabs)/`、`dev/`、`oauth/`、`ui/[id].tsx`）、
  `lib/`（含 `lib/family/*`、`lib/_core/*`）、`server/`、`components/`、`tests/`、
  `assets/`、`research/`（含 `research/baselines/*` 设计基线图与
  `research/ppt-analysis/*`）、`hooks/`、`constants/`、`drizzle/`、`scripts/`、
  `shared/`、以及根级配置文件（`package.json`、`pnpm-lock.yaml`、
  `app.config.ts`、`babel.config.js`、`metro.config.js`、`tailwind.config.js`、
  `drizzle.config.ts`、`eslint.config.js` 等）。
- 测试文件：**35 个**（`.test.`/`.spec.` 命名或位于 `tests/` 目录），与
  `MIGRATION_MANIFEST.yaml` 里登记的证据一致。
- 图片资产：实测 **87 个 PNG + 12 个 WEBP = 99 个图片文件**（含
  `research/baselines/*` 下的设计基线图）。Manifest 证据字段写的"202 PNG
  baseline"与本次静态点数不一致，本轮迁移未改动 manifest 该处描述文字，仅记录
  于此以供后续核实（可能是不同统计口径，例如包含了历史 commit 或子模块中已被
  清理的图片，或是引用了别处审计报告的数字）。

## workspace 依赖检查

- `package.json` 的 `name` 是独立的 `"app-template"`，**没有**任何
  `"workspace:*"` 协议依赖；全文搜索 `workspace:` 与 `@family/contracts` 在整个
  `frontend/mobile` 目录（含 `pnpm-lock.yaml`）**零命中**。
- 结论：这个 Mobile 应用本身不依赖 monorepo 内部包（不像 web 端会 import
  `@family/contracts`），是一个可独立安装的 pnpm 项目。**依赖缺口清单为空**——
  没有需要标注"包不存在、无法直接 install"的 workspace 内部包引用。
- 仍需注意：`pnpm-lock.yaml` 里锁定的第三方包版本是否能在无 monorepo 根
  `pnpm-workspace.yaml` 的独立目录下正常解析，未做验证（任务要求本轮不跑
  `npm install`/`pnpm install`）。

## Base URL 配置检查

- `lib/family/family-api-client.ts` 第 101 行：
  `constructor(baseUrl = process.env.EXPO_PUBLIC_FAMILY_API_BASE_URL, ...)`——
  完全由环境变量驱动，**没有硬编码指向源仓库或任何具体后端地址**。未配置时
  `configured` 为 `false`，请求前会先短路抛 `FAMILY_API_NOT_CONFIGURED`，不会
  意外打到旧地址。

## 硬编码路径检查结果

全仓搜索 `family-ai` / `50_开发_dev` 字符串，命中 30 个文件。绝大多数是**字符串
标识符**而非文件系统路径，不影响可移植性，包括：

- `x-source: "family-ai-mobile"`（HTTP 请求头里的来源标识，`family-api-client.ts`
  多处）、`appSlug: "family-ai-mobile"`（`app.config.ts`）、
  `STORAGE_KEY = "family-ai-mobile-state-v1"`（`family-state.tsx`）、
  `DEV_EXTERNAL_REF ... "family-ai-mobile-dev"`（`family-api-session.tsx`）——
  这些是应用内部命名约定，不是路径，无需修改。
- `research/*.md`、`todo.md`、`design.md` 里大量出现"family-ai"是对源项目/历史
  同步记录的文字叙述（例如"同步至 PoCP-Protocol/family-ai main"的历史提交记
  录），属于历史文档内容，不是代码依赖。

**发现的真正硬编码绝对路径（1 处，非运行时代码，不影响 App 本身）**：

- `scripts/crop_ui01_baseline_assets.py` 第 6-7 行：
  ```python
  SOURCE = Path("/home/ubuntu/family-ai-github/50_开发_dev/apps/web/public/bangyang-reference/home-screen-ui-crop.png")
  TARGET = Path("/home/ubuntu/family-ai-mobile/assets/images/ui01")
  ```
  这是原开发环境（云端 sandbox，Linux `/home/ubuntu/...`）里一次性裁图脚本的硬
  编码路径，不属于 App 运行时代码，也不会被 `pnpm dev`/`expo start`/`vitest`
  调用。按任务要求本轮不修，先记录在此。若未来需要重跑该脚本，需改成相对路径或
  Windows 路径。

## 未做的事（按任务要求）

- 未执行 `npm install` / `pnpm install`。
- 未执行任何 build / test / lint 命令。
- 未修改或删除源仓库 `D:\family-ai\50_开发_dev\apps\mobile` 下的任何文件。

## 下一步

等 Python `family_api` 的 Batch 1 Assessment 域和 Batch 2 SERVICE 预约域上线
后，回来对齐这 35 个测试文件里的 API contract。
