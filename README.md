# AiFamily

AI 原生家庭成长平台的 **canonical 仓库**。

服务中国家庭 —— 家长、孩子，以及为家庭提供服务的教师/专家/机构。解决的是孩子成长过程中反复出现的真实困境（亲子沟通、学习习惯、手机管理、自驱力不足），不是"卖课程"。

> 家是港湾，孩子是希望。We are family.

这句话是产品设计的**价值筛选器**，不是营销口号。因此本平台**不做家庭总分、不做家庭排名**。

## Current Status

治理体系与文档架构已建立，Python 平台内核骨架可运行（`/health`、`/ready`），**但尚无任何业务 API 可用** —— 34 个 UI 屏幕全部处于"代码在仓库内、后端未就绪"状态。

详细现状（含"哪些没完成"）见 [`docs/00_system/CURRENT_SYSTEM_BASELINE.md`](docs/00_system/CURRENT_SYSTEM_BASELINE.md) 第 5 节现状核对表。不要从架构图推断进度。

## Start Here

1. [`docs/00_system/SYSTEM_MANIFEST.md`](docs/00_system/SYSTEM_MANIFEST.md) —— **最高级文档**。系统是什么、边界在哪、哪些文档算正式真相
2. [`docs/00_system/CURRENT_SYSTEM_BASELINE.md`](docs/00_system/CURRENT_SYSTEM_BASELINE.md) —— 系统现在真实是什么
3. [`governance/REPOSITORY_CONSTITUTION.md`](governance/REPOSITORY_CONSTITUTION.md) —— 14 条工程宪章 R1–R14
4. [`docs/00_system/DOCUMENTATION_MAP.md`](docs/00_system/DOCUMENTATION_MAP.md) —— 文档体系导航（"我要的东西在哪"）
5. [`docs/00_system/CURRENT_AI_MAP.md`](docs/00_system/CURRENT_AI_MAP.md) —— AI 能力版图与各能力真实成熟度

AI Agent 请先读根目录 [`CLAUDE.md`](CLAUDE.md)（Claude Code）或 [`AGENTS.md`](AGENTS.md)（其它 Agent）。

## Developer Start

```bash
uv venv --python 3.12          # Python 3.12，见 .python-version
uv pip install -e ".[dev]"     # 唯一依赖工具链是 uv + pyproject.toml（R11）
uv run pytest                  # 全量测试
uv run pytest tests/architecture -v   # 只跑治理护栏
uv run ruff check .            # lint
make help                      # 全部可用目标（setup / test / arch / lint / fmt / check）
```

CI 见 [`.github/workflows/ci.yml`](.github/workflows/ci.yml)：ruff lint + 架构测试 + backend 测试。

## Repository Structure

```text
backend/          Python 后端（唯一业务后端，R1）
  apps/           进程入口：family_api（FastAPI）
  platform/       平台内核：identity / authorization / consent / audit / idempotency / persistence
  domains/        业务域（四层结构，Wave 2+）
  intelligence/   AI Runtime —— 所有 AI 能力收敛于此（R10）
  packages/       跨域共享契约原语
frontend/mobile/  Expo / React Native，34 个 UI 屏幕
contracts/        API 契约（openapi/）
database/         SQL 迁移
governance/       机器可执行治理：宪章、registry YAML、ADR
docs/             16 层文档体系，见 DOCUMENTATION_MAP
tests/            architecture/（治理护栏）+ platform/ + apps/
tools/            治理与构建脚本
```

## Canonical Documents

**只有 `SYSTEM_MANIFEST.md` 第 5 节列出的文档是正式真相。** 其余一切（研究、参考、归档、旧仓库文档）都不是。写作与归档规范见 [`docs/12_governance/DOCUMENT_GOVERNANCE.md`](docs/12_governance/DOCUMENT_GOVERNANCE.md)。

## Legacy Repository

`D:\family-ai`（`PoCP-Protocol/family-ai`）是**只读迁移源与历史证据库**，不是当前系统。

- 其文档**不得**作为 AiFamily 的当前真相引用
- 其代码进入本仓库必须先在 [`governance/MIGRATION_MANIFEST.yaml`](governance/MIGRATION_MANIFEST.yaml) 登记并获批 disposition（R3）
- 对本仓库工作**只读**。禁止修改（内有其他并发会话的未提交 WIP）

## Governance

| 文件 | 作用 |
|---|---|
| [`governance/REPOSITORY_CONSTITUTION.md`](governance/REPOSITORY_CONSTITUTION.md) | 14 条工程宪章，最高工程约束。第 2 节标注哪些规则已有护栏 |
| [`governance/DOMAIN_REGISTRY.yaml`](governance/DOMAIN_REGISTRY.yaml) | 每个 Domain 的唯一正式实现位置（R2 执行） |
| [`governance/MIGRATION_MANIFEST.yaml`](governance/MIGRATION_MANIFEST.yaml) | 每项能力的迁移处置（R3 执行：无登记不得入仓） |
| [`governance/ADR/`](governance/ADR/) | 架构决策记录（当前为空） |
| [`docs/12_governance/COMPLIANCE_HARD_CONSTRAINTS.md`](docs/12_governance/COMPLIANCE_HARD_CONSTRAINTS.md) | 未成年人与家庭数据法定硬约束，优先于产品与商业设计 |

**未被 `tests/architecture/` 覆盖的规则只是意图，不是护栏**（R14）。
