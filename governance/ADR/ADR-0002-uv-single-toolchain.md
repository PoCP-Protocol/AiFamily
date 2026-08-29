# ADR-0002: uv + pyproject.toml 作为唯一 Python 依赖工具链

- **Status**: Accepted
- **Date**: 2026-08-29
- **Deciders**: project-owner / chief-architect
- **Supersedes**: null
- **Superseded By**: null

## Context

源仓库 `D:\family-ai` 的依赖管理状态不是"用了某个不理想的工具"，而是**根本没有依赖声明**：

- **全域零个** `pyproject.toml`、零个 `requirements*.txt`、零个 lock 文件。
- 却有**两个 venv 躺在磁盘上**（其中一个是 `50_开发_dev/apps/ai-runtime/.venv`）。这意味着依赖集**只能靠翻 `site-packages` 下的 `.dist-info` 目录反推**——反推得到的是"某台机器上曾经装了什么"，不是"这个项目需要什么"，两者的差集无法确定。
- `50_开发_dev/apps/ai-runtime/.venv/Lib/site-packages/_editable_impl_family_ai_runtime.pth` 里**硬编码了绝对路径** `D:\family-ai\50_开发_dev\apps\ai-runtime\src`。换一台机器、甚至换一个 checkout 目录，即失效。
- 同一个应用（`apps/ai-runtime`）的 `.py` 源码已从磁盘删除只剩 `.pyc`。于是出现了最坏组合：**能力的唯一证据是编译产物，而运行它的环境唯一证据是一个含绝对路径的 `.pth`**。

与之配套的是导入方式的连带失败（另见 R12 / ADR 未单列）：`50_开发_dev/backend/domains/*` 全部使用 `from packages.contracts.evidence import Provenance` 这类裸顶层导入（如 `market_intelligence/domain/entities.py:22`、`membership/application/commands.py:17`），而 `packages/contracts` 既没被安装、也没有 `pyproject.toml` / `conftest.py` 声明 rootdir——**只有把 cwd 钉在 `50_开发_dev/backend` 才能跑**。依赖没声明和导入靠 cwd 是同一个病根：没有"可安装包"这个概念。

结论：源仓库的 Python 环境**不可复现**。这不是缺一个 lock 文件的问题，是"无法确定 5 个 Python 域到底依赖什么"的问题。

## Decision

Python 依赖只用 **uv + `pyproject.toml`**，单一工具链，仓库根一份。

1. 禁止 pip / poetry / pipenv / `requirements.txt` / `conda` 与之并存。允许存在的依赖声明文件只有 `pyproject.toml` 与 uv 生成的 lock。
2. 依赖必须能**从版本控制完整复现**：任何人 clone + `uv sync` 即得到与 CI 一致的环境。
3. 禁止不可移植的环境产物入仓：绝对路径 `.pth`、已构建的 venv 目录、`.pyc`。
4. 内部代码以**真实可安装包**的形式解析（`backend.packages.contracts.*` 这类绝对包路径），不依赖 cwd、不注入 `sys.path`、不靠目录深度。R12 与本决定互为前提。

本决定写入 `governance/REPOSITORY_CONSTITUTION.md` **R11 — 单一依赖管理**，并在 `MIGRATION_MANIFEST.yaml` → `dependency_management`（`status: DONE`）中登记为已完成。

## Alternatives Considered

### A. `pip` + `requirements.txt` + `requirements-dev.txt`
**支持理由**：最低认知成本，任何 Python 开发者与任何 CI 镜像都直接支持，无需额外安装工具。

**否决理由**：`requirements.txt` 不区分直接依赖与传递依赖，因此"我们真正需要什么"这个信息在文件里就丢失了——而这恰恰是源仓库故障的核心（反推 `site-packages` 得到的正是一份混合了传递依赖的清单）。要靠 `pip-compile` 补齐分层就已经是引入第二个工具，那不如直接选一个自带分层的。

### B. Poetry
**支持理由**：成熟、生态广、`pyproject.toml` + lock 的分层语义完整，是本决定的最接近替代品。

**否决理由**：解析速度与 CI 冷启动开销显著高于 uv；且 Poetry 历史上对 PEP 621 标准 `[project]` 表的支持长期滞后于自有 `[tool.poetry]` 表，容易再造一套非标准声明。选 uv 的关键理由是它**直接写标准 `[project]`**——即使将来换工具，`pyproject.toml` 本身仍然可读可用，迁出成本低。

### C. 每个 app / domain 各自一个 `pyproject.toml`（monorepo 多包）
**支持理由**：与 `backend/apps/*`、`backend/domains/*`、`backend/packages/*` 的物理结构对应，包边界更清晰，理论上能用依赖声明强制域间不互相 import。

**否决理由**：**源仓库的失败模式恰恰是"多个环境、无人知道哪个是真的"**（两个 venv）。在当前阶段（零业务路由、单一进程、5 个域全部处于 stub 或未测试状态）引入 N 个包边界，会把"环境唯一"这个刚建立的性质马上让掉。保留为未来选项：当 `family_api` / `ai_runtime` / `workflow_worker` 真的分成三个部署单元时，用 uv workspace 拆分，届时需新出一份 ADR。

### D. 不做强制，允许开发者自选
明确否决。R11 的伤疤说明的正是"没人规定"的结果：不是多种工具共存，而是**零种工具**。

## Consequences

### 正面
- 环境可复现，`uv sync` 是唯一入口，CI 与本地一致。
- `uv run pytest` 成为唯一测试入口，不存在"用哪个解释器跑"的歧义。
- 与 R12 联动：内部包以 `backend.*` 绝对路径导入，测试不需要 cwd 假设（`tests/architecture/conftest.py` 从 `__file__` 推导 repo root，正是这条的体现）。

### 负面 / 代价
- 引入一个**非标准库工具依赖**：CI 镜像与新机器必须先装 uv。这是真实的额外一步。
- uv 相对年轻，生态问题的解决路径不如 pip/poetry 成熟；遇到边缘 case 可参考资料较少。
- 单一根 `pyproject.toml` 意味着 dev 依赖（pytest / ruff）与运行时依赖（fastapi / sqlalchemy）装在同一环境，生产镜像需要显式排除 dev 组，否则会把测试工具打进部署产物。

### 需要接受的风险
- 若 uv 项目未来停止维护，需要迁出。缓释：坚持写标准 `[project]` 表，不使用 uv 专有语法，使迁往 pip/poetry 的成本限于 lock 文件重新生成。
- 单环境策略在多部署单元阶段会失效。这是**已知会到期的决定**，触发条件是三进程拆分开工，届时必须重开 ADR 而不是临时加第二个 `pyproject.toml`。

## Enforcement

**已由架构测试机械执行。**

- `tests/architecture/test_single_toolchain.py` — R11 的执行者：检查禁止的依赖声明文件（`requirements*.txt`、`Pipfile`、`poetry.lock` 等）不存在，且 `pyproject.toml` 存在。
- `tests/architecture/test_no_layout_coupling.py` — R12 的执行者：禁止 `sys.path` 注入与硬编码仓库物理路径，间接保证"包必须真的可安装"。
- 不可移植产物（venv / `.pyc` / 绝对路径 `.pth`）目前依赖 `.gitignore` 与人工评审，**尚无架构测试断言它们未被提交**。这是一个已知缺口：`.gitignore` 能防误提交但不能防有人显式 `git add -f`。补齐路径是在 `test_single_toolchain.py` 中加一条对 tracked file 的断言。

## References

- `governance/REPOSITORY_CONSTITUTION.md` R11（含伤疤段）、R12
- `governance/MIGRATION_MANIFEST.yaml` → `dependency_management`、`ai_runtime_app`
- `tests/architecture/test_single_toolchain.py`、`tests/architecture/test_no_layout_coupling.py`
- `pyproject.toml`
- `docs/00_system/CURRENT_TECHNOLOGY_BASELINE.md`
