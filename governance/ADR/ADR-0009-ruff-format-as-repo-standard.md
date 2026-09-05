# ADR-0009: 采纳 ruff format 为仓库统一格式化标准

- **Status**: Accepted
- **Date**: 2026-08-29
- **Deciders**: chief-architect
- **Supersedes**: null
- **Superseded By**: null

## Context

T-01（清理 ruff 错误）执行后暴露一个结构性问题，由执行者主动升报而非隐藏——这一点本身值得记录。

**事实经过**：任务开始时 `backend/` 有 388 个 ruff 错误，其中 **334 个是 E501（行过长）**，占 86%。执行者用两步处理：
1. `ruff check --fix` 自动修掉 70 处（UP017 / UP037 / I001 / F401 / SIM300）
2. 对**当时确实有 E501 的 35 个文件**定向跑 `ruff format`，一次吃掉 322 个 E501

第 2 步的动机是合理的：当时有 8 个 agent 并发写代码，全量 `ruff format` 会给别人的文件制造大面积无关 diff。定向跑压低了冲突面。

**但结果是仓库进入混合态**：35 个文件已被 format 规范化，其余未被 format。执行者判断这是三种状态里最差的一种，并拒绝自行决定是否固化——因为这需要 ADR。该判断正确。

**为什么混合态最差**：
- 下一个人全量跑一次 `ruff format`，会产生一大坨与其改动无关的 diff，淹没真实变更
- 每个新文件的格式取决于作者是否手动跑过 format，同一仓库内风格不一致
- E501 会持续复发：手写长行 → CI 报错 → 手工折行 → 折法因人而异。这是本轮 334 个 E501 的成因，不修根因就会重演

## Decision

**采纳 `ruff format` 为 AiFamily 唯一的 Python 格式化标准。**

具体：
1. `ruff format` 的输出即为规范格式，不接受手工折行风格的并存
2. CI 增加 `ruff format --check`（只检查、不自动改），格式不符即失败
3. `Makefile` 的 `fmt` target 已存在（`ruff format .`），保持
4. `CLAUDE.md` 的命令区加入格式化命令，让后续 agent 有明确指引
5. **禁止用 `# noqa: E501` 规避**——T-01 全程零 noqa，这个标准要守住

**全量 sweep 的时机（重要）**：本 ADR 决定标准，但**不立即执行全量格式化**。当前有 8 个并发 agent 在写代码（T-03/T-04/T-06/T-07/T-08/T-09/T-10 及其他会话），此刻全量重排会造成大面积冲突并可能覆盖他人未提交的工作。

全量 sweep 的前置条件：
- 所有在飞任务收工
- 单独一次提交，提交信息标明"格式化 sweep，无语义变更"
- 提交前用 AST 比对验证无语义漂移（T-01 已建立此做法的先例，见 Consequences）

在 sweep 完成前，CI 的 `ruff format --check` 应设为**警告而非失败**，否则会立刻把仓库变红。

## Alternatives Considered

### A1. 不用 ruff format，只靠 `ruff check` + 手工折行
**支持理由**：格式化会改动大量既有代码，diff 噪声大；手工折行能针对语义做更可读的断行（如把逻辑分组对齐）。

**否决理由**：这正是产生 334 个 E501 的现状。手工折行的一致性依赖每个作者的自觉，而本仓库是**多 AI 并发写作**环境——指望 8 个 agent 手工折出一致风格不现实。且"更可读的断行"是主观判断，会引入 review 争论，而格式化的全部价值就是消灭这类争论。

### A2. 放宽 `line-length` 到 120 或去掉 E501
**支持理由**：一行放宽到 120 能让 334 个错误里的大多数直接消失，零改动成本。

**否决理由**：这是把问题藏起来而非解决。T-01 的任务卡明确禁止"改 pyproject 放宽规则来让错误消失"，执行者也确实没这么做（`pyproject.toml` 全程未动）。若现在由架构师放宽，等于推翻自己给出的纪律，且下次超过 120 时同样的争论会重来一次。line-length 100 是既有决定，不因为违规多就改规则。

### A3. 采纳 black 而非 ruff format
**支持理由**：black 更成熟、生态更广、社区约定更强。

**否决理由**：违反 R11（单一依赖工具链）。ruff 已在依赖里承担 lint 职责，`ruff format` 与 black 高度兼容（ruff 官方以 black 兼容为设计目标），再引入 black 就是为同一件事装两个工具。源仓库的教训正是工具链发散（零个 pyproject 却有两个 venv）。

### A4. 立即全量 sweep
**支持理由**：一次性解决，避免混合态持续。

**否决理由**：8 个 agent 在飞。全量重排会与他们的未提交改动冲突，最坏情况是覆盖他人工作——而本仓库 `AGENTS.md` 的并发纪律第一条就是"只改自己负责的文件"。架构师不该带头违反自己定的纪律。故决定标准、推迟执行。

## Consequences

### 正面
- E501 类争论一次性终结，后续 agent 不需要判断"这行怎么折"
- 格式一致性由工具保证，不依赖 8 个并发写作者的自觉
- CI 可机械执行，符合 R14（写成文档不算执行）

### 负面 / 代价
- 全量 sweep 那次提交的 diff 会很大，且横跨几乎所有 Python 文件。必须单独成一次提交、标明无语义变更，否则会污染 git blame 的可用性
- 混合态会持续到 sweep 完成，期间格式一致性无保证
- `ruff format` 的某些断行选择可能不如人工排版可读，这是采纳自动格式化的固有代价

### 需要接受的风险
- **格式化改动语义的风险**：理论上格式化器不改语义，但 T-01 期间执行者主动写了 AST 比对脚本验证（归一化字符串空白后逐文件对比 HEAD 与工作区），结论是全部差异都能归因到已知的 `--fix` 规则与 6 处手工编辑，无不可解释的语义变动。**全量 sweep 时应重复这一验证**，不要因为"格式化器不会改语义"就跳过。
- 长字符串字面量的处理：T-01 遇到 10 个 E501 是长字符串，用隐式拼接拆行且**字符串值逐字节不变**。`ruff format` 不会自动拆字符串，这类仍需手工处理，sweep 后可能残留少量 E501。

## Enforcement

| 项 | 状态 |
|---|---|
| `Makefile` 的 `fmt` target | 已存在（`ruff format .`） |
| `Makefile` 的 `fmt-check` target | **已加**（2026-08-29）；刻意**不**进 `check` 依赖，与 CI 的警告级保持一致 |
| `CLAUDE.md` 命令区加入格式化指引 | **已完成**（见「格式化纪律（ADR-0009）」一节） |
| CI 加 `ruff format --check` | **已加**（2026-08-29）；按本 ADR 要求为**警告级**（`|| true` + `::warning`） |
| Lint 债务棘轮 | **已加**（2026-08-29）`tests/architecture/test_lint_debt_ratchet.py`，BASELINE=0，已用注入违规验证会咬人 |
| 全量 sweep | **部分完成**（2026-08-29）：`ruff check` 全仓 401 → 0；`ruff format` 覆盖 337/362 文件。剩 25 文件因并发写作跳过，见下 |
| 禁止 `# noqa: E501` | 当前靠人工 review；无机械检查，属意图 |

### 2026-08-29 sweep 执行记录（QA 角色）

**动因**：远端 CI 从第一次推送起连续三次全红（run 33244397013 / 33244790062 / 33244977302），
因 `Lint (ruff)` 报 401 个错误，**无人发现**。详见 `docs/11_delivery/PROJECT_MANAGEMENT_CHARTER.md` §0 第 1、2 条。

**已 sweep**：`backend/domains/assessment/`、`tests/domains/assessment/`、`tests/architecture/`、
`backend/domains/product_intelligence/`、`backend/intelligence/`、`tests/domains/loyalty_points/`、
`_superseded_assessment_v1_backup/`。401 个错误中有 378 个集中在 assessment 域（迁入后从未格式化）。

**因并发写作跳过**（本 ADR「只改自己负责的文件」纪律）：`backend/platform/`、`backend/apps/`、
`backend/domains/{service,membership}/`、`tests/platform/`。这些目录在 sweep 期间有其他 agent
的未提交改动（T-14 等），重排会覆盖他人工作。它们是剩余 25 个未格式化文件的主要来源。

**语义验证**（本 ADR「需要接受的风险」段要求）：对 65 个改动文件逐一比对 HEAD 与工作区的 AST，
全部差异归因到已知规则，**0 处不可解释**：

| 归因层级 | 文件数 |
|---|---|
| AST 完全一致（字符串逐字节不变） | 56 |
| 仅 import 集合变化（I001 排序 / F401 删除） | 2 |
| 加 UP017（`timezone.utc` → `UTC`） | 2 |
| 加 SQL 空白重排（换行替代空格 / 逗号后换行） | 3 |
| 手工声明改动（UP042 `StrEnum`、SIM105 `contextlib.suppress`） | 2 |

SQL 重排的额外保证：抽取全部 74 个 `'...'` SQL 引号字面量做多重集比对，**逐字节一致** ——
换行只落在引号字面量之外，字面量内部空白未被触碰。长字符串一律用隐式拼接拆行，
并用 AST 相等证明拼接后的值不变（Python 在解析期折叠隐式拼接）。全程 **0 个 `# noqa`**，
`pyproject.toml` 未改动。

**诚实标注**：`ruff format --check` 仍是警告级，因为 sweep 未完成 —— 设为失败级会立刻制造
一个新的长期红灯，与本次任务的目的相反。真正阻止债务无声反弹的是那个**棘轮测试**（BASELINE=0，
在 CI 的架构测试步骤里跑），它比格式检查更贴合上次的失效模式：上次不是格式不统一导致 CI 红，
而是错误数从 0 涨回 401 且没有任何机制在第一次增长时喊停。

## References

- `governance/REPOSITORY_CONSTITUTION.md` R11（单一依赖工具链）、R14（架构测试强制）
- `docs/11_delivery/TASK_BACKLOG.md` T-01 任务卡与其执行报告
- `pyproject.toml` `[tool.ruff]`（line-length = 100，`exclude = ["frontend"]`）
- `Makefile` `fmt` / `lint` / `check` targets
