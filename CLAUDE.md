# CLAUDE.md — AiFamily Agent 操作手册

AiFamily = AI 原生家庭成长平台的 **canonical 仓库**（Python 3.12 / FastAPI / PostgreSQL 后端 + Expo/React Native 前端）。
系统身份、边界、canonical 文档清单以 `docs/00_system/SYSTEM_MANIFEST.md` 为唯一真相。本文件只讲**怎么干活**。

## 强制阅读顺序（开工前，不可跳）

| # | 文件 | 读它是为了 |
|---|---|---|
| 1 | `docs/00_system/SYSTEM_MANIFEST.md` | 哪些文档算真相、系统边界在哪 |
| 2 | `docs/00_system/CURRENT_SYSTEM_BASELINE.md` | 系统**现在**是什么（含未完成项，别从别处推断） |
| 3 | `governance/REPOSITORY_CONSTITUTION.md` | 14 条工程宪章 R1–R14 + 第2节"强制执行状态"表 |
| 4 | 按任务类型加读 | 见下 |

按任务类型追加：
- 涉及 AI 行为 → `docs/05_ai/AI_NATIVE_PRINCIPLES.md`（5 条判据 + 反面清单）
- 涉及家庭/未成年人数据 → `docs/12_governance/COMPLIANCE_HARD_CONSTRAINTS.md`（法定硬约束，优先于产品与商业设计）
- 新增/改动 Domain → `governance/DOMAIN_REGISTRY.yaml`
- 从旧仓库迁入任何东西 → `governance/MIGRATION_MANIFEST.yaml`
- 找不到文档在哪 → `docs/00_system/DOCUMENTATION_MAP.md`
- 写文档 → `docs/12_governance/DOCUMENT_GOVERNANCE.md`

## 8 条铁律

1. **先读 SYSTEM_MANIFEST**，再动任何文件。它声明了什么是 canonical；不读就无法判断自己在改真相还是改草稿。
2. **永不把归档/研究文档当当前真相。**
   - `docs/99_archive/**` = History，必带 `ARCHIVED` / `SUPERSEDED_BY` / `DO_NOT_USE_FOR_IMPLEMENTATION`。只读、不引用为依据。
   - `docs/13_research/**` = Evidence，必带 `RESEARCH_ONLY` 或 `NOT_CANONICAL`。研究结论未经 ADR 不得当决策。
   - `docs/14_reference/**` = 旧系统审计参考，非当前真相。
   - 两条标记规则由 `tests/architecture/test_docs_truth_boundary.py` 强制。
3. **加 domain 代码前先查 `governance/DOMAIN_REGISTRY.yaml`**（R2）。一个 capability 只有一个 `canonical_path`。要新增就先加登记行；`status` 从 `NOT_STARTED` 改 `ACTIVE` 必须同时有测试（R4）。
4. **建 capability 前先查 `governance/CAPABILITY_REGISTRY.yaml`**——**该文件尚未建立**（另有任务在建）。它存在时，新 capability 必须先登记；不存在时，退回用 `DOMAIN_REGISTRY.yaml` + `MIGRATION_MANIFEST.yaml` 双查，并在 PR 里说明为何未登记。
5. **加 AI 行为前先查 `governance/AI_USE_CASE_REGISTRY.yaml`**——**同样尚未建立**。它存在时，每个 AI 用例（AIUC-NNN）必须登记 allowed_tools / context_policy / human_gate / `may_mutate_business_state: false`；不存在时，按 `AI_NATIVE_PRINCIPLES.md` 五问自检并把用例文档写入 `docs/05_ai/AI_USE_CASES/`。
6. **不创建重复的 canonical 实现**（R2）。禁止 `family` / `family_core` / `family_v2` / `family_new` 并存。发现已有实现就改它，不要旁开一份。
7. **架构变更必须同 PR 同步文档与 registry。** 改了 Domain 边界 / API / Event / AI 用例 / 授权 / 数据归属 → 同时改对应 canonical doc 与 registry 行。代码与 YAML 漂移是源仓库的原始事故（R14 的伤疤）。
8. **无 ADR 不做架构决策。** 技术选型、边界变更、推翻宪章某条 → 先写 `governance/ADR/ADR-NNNN-<kebab-slug>.md`（该目录当前为空，你可能是第一份）。禁止在实现 PR 里顺手改 `REPOSITORY_CONSTITUTION.md`。

## 本仓库特有的坑（都是真实踩过的，别重复）

- **不要给纯容器目录加 `__init__.py`**：`backend/`、`backend/domains/`、`backend/packages/`、`backend/intelligence/` 目前**故意没有** `__init__.py`。加上会让这些目录变成"含文件的目录"，而 `test_migration_manifest.py`（R3）要求每个含文件的目录都被 MIGRATION_MANIFEST 某条 `target` 覆盖 —— 纯容器目录没有也不该有 manifest 条目，于是 R3 直接失败。Python 3.12 命名空间包不需要它们。叶子包（真实有代码的）才加。
- **源仓库 `D:\family-ai` 是只读的**。其中有其他并发会话的未提交 WIP。禁止写入、禁止 `git` 操作、禁止"顺手清理"。只读取文件内容作参考。
- **迁入的 Python 必须改导入路径**（R12）：源仓库写 `from packages.contracts.evidence import Provenance`，靠把 cwd 钉在 `50_开发_dev/backend` 才能解析。本仓库必须写 `from backend.packages.contracts.evidence import Provenance`。`test_no_layout_coupling.py` 会拦裸 `packages.*` 导入、`sys.path.insert/append`、以及硬编码的 `50_开发_dev` / `D:\family-ai` 字面量（包括注释里的）。
- **本环境 Bash 工具禁用 `cp` / `tar` / `robocopy`**。复制文件用 Python `shutil.copy2` / `shutil.copytree`。
- **中文文件名在复合 bash 命令里可能触发安全拦截**（源仓库路径含 `50_开发_dev`，本仓库 `docs/01_strategy/source_materials/` 下也有中文文件名）。遍历/复制这类路径用 Python `pathlib`，不要拼 bash 一行流。
- **禁止整体复制旧仓库**（R3）：不得 `cp -R`，不得"先全迁再删"。逐 capability 走 manifest。

## 命令

```bash
uv run pytest tests/architecture -v   # 治理护栏，改任何结构后必跑（当前 12 passed）
uv run pytest -v                      # 全量
uv run ruff check .                   # lint（CI 会跑）
make help                             # 全部可用目标
```

`make arch` / `make test` / `make lint` / `make check` 是上述命令的等价封装。CI 见 `.github/workflows/ci.yml`（lint + 架构测试 + backend 测试）。

## 禁止事项

- **不做家庭总分、不做家庭排名**（R9 红线 + 与"家是港湾"定位直接冲突）。不计算、不存储、不暴露。
- **AI 输出不直写 canonical 事实**（R9）。AI 只产 `Perspective` / `Recommendation`，初始态 `DRAFT`/`PROPOSED`，跨到 `Fact` 必须过 Named Action + 人工闸门（R8）。
- **领域代码不直连模型供应商**（R7）。不得 import OpenAI/Anthropic/DeepSeek/Gemini SDK，不得裸 `new`/实例化会发外部请求的网关。一律经 `backend/intelligence/model_gateway`；凭据只由它读取。`test_no_direct_provider_calls.py` 强制。
- **不向未成年人做自动化决策商业营销** —— 法定绝对禁止（《未成年人网络保护条例》第24条第3款），无例外、不限14岁以下。
- **不做临床诊断**，不承诺疗效。
- **合成/演示/夹具数据不得挂生产路由**（R5）。自述 `SYNTHETIC` 的产物不是业务能力。
- **不引入第二个业务后端**（R1），不引入 pip/poetry/requirements.txt（R11，只用 uv + `pyproject.toml`）。
- **无测试不得声称能力可用**（R4）。行数不是成熟度，docstring 里声明的测试不算测试。

## 汇报纪律

- 面向用户的回复用**中文**；代码与标识符用英文。
- 如实报告未完成项与已知缺口。"迁移进来了"≠"能力存在"——MIGRATION_MANIFEST 里多条 `project_owner_override` 明确要求迁移时**原样带着已知缺口**，不得假装测试已存在。
