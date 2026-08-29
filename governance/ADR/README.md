# AiFamily 架构决策记录 (ADR Index)

> ADR 回答的问题只有一个：**为什么这样选，以及考虑过什么但没选。**
>
> 它不回答"现在是什么"（那是 `docs/00_system/CURRENT_*.md`），不回答"应该建成什么样"（那是 `docs/03_product/` / `docs/04_domains/` / `docs/06_platform/`），不回答"我们调研到什么"（那是 `docs/13_research/`）。见 `docs/12_governance/DOCUMENT_GOVERNANCE.md` §1 的五类信息区分。

`CLAUDE.md` 铁律第 8 条与 `governance/REPOSITORY_CONSTITUTION.md` 第 3 节（修宪程序）共同要求：**无 ADR 不做架构决策。** 本目录在 2026-08-29 之前是空的，而当时已经做出了 6 项重大架构决定——ADR-0001 至 ADR-0006 是对这一违规的补记。**补记本身是一次治理债务的偿还，不是常规流程**：正常情况下 ADR 应与决定同时产生，而不是事后补。

---

## ADR 列表

| # | 标题 | Status | Date | 一句话摘要 |
|---|---|---|---|---|
| [0001](ADR-0001-python-only-backend.md) | 后端单轨 Python | Accepted | 2026-08-29 | 源仓库四条并存后端血脉无一权威（NestJS 生产 API / 5 个无进程入口的 Python 域 / 只剩 `.pyc` 的 ai-runtime / 无 `@Module` 的 fes-api），收敛为唯一 Python 后端；前端不要求迁 Python |
| [0002](ADR-0002-uv-single-toolchain.md) | uv + pyproject.toml 单一工具链 | Accepted | 2026-08-29 | 源仓库零依赖声明文件却有两个 venv、`.pth` 硬编码 `D:\family-ai\...`；依赖必须可从版本控制完整复现 |
| [0003](ADR-0003-selective-migration-not-wholesale.md) | 精选式迁移取代全量搬家 | Accepted | 2026-08-29 | 引入 disposition 分类法，默认状态是 `REVIEW_REQUIRED` 而非 `MIGRATE`；含 project-owner 后续 override 为"先把所有 Python 代码都迁移过来"的记录 |
| [0004](ADR-0004-documentation-architecture-v1.md) | 文档体系 V1.0（16 层 + 五类信息） | Accepted | 2026-08-29 | 源仓库三份互相矛盾、各自声称"当前基线"的文档；按 L0–L4 系统真相层级重组，Current Truth / Decision / Specification / Evidence / History 强制区分 |
| [0005](ADR-0005-ai-native-platform.md) | AI 原生平台定位 | Accepted | 2026-08-29 | AI 是主干不是模块；5 条判据 + 核心域必须/支撑域不要求；关键推论：AI 原生 ≠ 放宽约束，因为破坏半径最大所以 R9/R7/R6 要加强 |
| [0006](ADR-0006-minor-data-compliance-constraints.md) | 未成年人数据合规约束进入架构 | Accepted | 2026-08-29 | 3 票核验确认的法定硬约束：14 岁以下全部敏感信息、AI 评估=自动化决策、绝对禁止向未成年人自动化营销、embedding 删除是法定义务、不得转委托；孩子端商业化路径被实质关闭 |

### 决定之间的关系

```text
ADR-0001 (Python-only)  ──前提──▶  ADR-0003 (精选式迁移)
ADR-0001 (Python-only)  ──理由之一──▶  ADR-0005 (AI 原生：Python 生态承载 AI 主干)
ADR-0002 (uv 单工具链)  ──与 R12 互为前提──▶  可安装包 / 无 cwd 耦合
ADR-0004 (文档体系)     ──定义了本目录的位置与晋升链──▶  ADR 全体
ADR-0005 (AI 原生)      ◀──实质张力──▶  ADR-0006 (合规：能力上限 vs 部署形态，尚未解决)
```

**当前无任何 ADR 被 Supersede。** Supersedes / Superseded By 链为空是正常初始状态。

---

## 何时必须写 ADR

**以下任一情形，改变发生前必须先有 ADR：**

1. **改变 Domain 边界** —— 新增 / 删除 / 合并 / 拆分 Domain；把一个能力从 A 域移到 B 域；改变某个聚合的所有者。
   典型触发：`growth_plan` stub 与 `journey` 域的语义重叠裁决（`DOMAIN_REGISTRY.yaml` → `growth_plan_python_stub.r2_overlap_risk`）；`platform_actor_tenant_context` 与 `auth_identity` 是否长期共用 `backend/platform/identity`。
2. **改变技术栈** —— 后端语言/框架、依赖工具链、数据库、AI 供应商接入形态、部署单元划分（例如把单进程拆为 `family_api` / `ai_runtime` / `workflow_worker`）。
3. **改变数据所有权** —— 哪个域拥有哪张表；跨域读写策略；保留期限；删除级联范围。**涉未成年人派生数据（embedding 等）的任何所有权变更必须同时引用 ADR-0006。**
4. **改变 AI 能力边界** —— AI 可以写什么层级的数据（Fact / Perspective / Recommendation）；新增 Agent 或工具；放宽或收紧 Human Gate；改变某个域的 AI 原生要求等级。
5. **改变文档体系** —— 增删 `docs/` 层级；改变五类信息的判据；改变 canonical 文档的优先序。
6. **修改宪章 `governance/REPOSITORY_CONSTITUTION.md`** —— 强制。且若削弱某条规则，必须说明**对应的伤疤为何不再适用**（宪章第 3 节），并在同一 PR 更新其第 2 节执行状态表。
7. **推翻或修改一份既有 ADR** —— 不得原地编辑已 Accepted 的 ADR 的 Decision 段。写新 ADR，填 `Supersedes`，并回填被取代者的 `Superseded By`。
8. **把调研结论晋升为架构** —— `docs/13_research/` 的内容不得直接晋升为 canonical 文档，必须经 ADR（ADR-0004 的三级晋升链）。

**不需要写 ADR 的**：实现细节选择（用哪个 pytest fixture）、单个函数的算法、文案、bug 修复、不改变边界的重构、纯粹补充既有决定的执行机制（例如给已存在的 ADR 补一个架构测试）。

判断标准：**如果一年后有人问"当初为什么不用 X"，且答案不写下来就会丢失，那就需要 ADR。**

---

## 编号规则

- 格式：`ADR-NNNN-kebab-case-slug.md`，`NNNN` 为四位零填充十进制序号。
- **严格顺序分配，永不复用。** 下一个可用编号 = 本目录现有最大编号 + 1（当前为 **0007**）。
- 编号一经分配即永久绑定该决定，**即使 ADR 后来被 Superseded 也不回收、不删除文件**。被取代的 ADR 保留在原位，改 `Status: Superseded` 并填 `Superseded By`——历史决定的存在本身是信息。
- slug 描述决定的对象，不描述结论的方向（`python-only-backend` 而非 `dont-use-nestjs`）。
- 并发写作时若两人取到同号，后合并者改号。**不允许 `ADR-0007a` 之类的分号形式。**

## 统一模板

```markdown
# ADR-NNNN: 标题

- **Status**: Proposed | Accepted | Superseded
- **Date**: YYYY-MM-DD
- **Deciders**: project-owner / chief-architect
- **Supersedes**: ADR-NNNN 或 null
- **Superseded By**: ADR-NNNN 或 null

## Context
（为什么要做这个决定。**必须包含具体的实测证据与文件路径**——行号、实测数字、grep 命中数。
 不要泛泛而谈"为了更好的可维护性"。）

## Decision
（决定了什么。可执行的表述，不是原则宣言。）

## Alternatives Considered
（考虑过的其他方案，及为什么没选。**这是 ADR 最有价值的部分，不得省略。**
 每个替代方案先写"支持理由"再写"否决理由"——如果一个方案连支持理由都写不出来，
 它就不是真的被考虑过，删掉它别充数。）

## Consequences
### 正面
### 负面 / 代价
### 需要接受的风险

## Enforcement
（这个决定由什么机制执行？架构测试？registry 字段？还是目前只是意图？
 **如果没有执行机制，必须如实写"当前仅为意图"，并给出补齐路径。**
 按 R14：写成文档的策略等于没有策略。）

## References
（相关文件路径、法源、被本决定修正的上游文档）
```

### 写作纪律（这几条是 ADR 变成废纸的常见死法）

1. **ADR 的价值在"为什么"和"考虑过什么但没选"，不是决定的复述。** 如果 Decision 段写完就没别的可写，说明这不需要一份 ADR。
2. **Context 段的每个主张要有可核验的锚点**——文件路径 + 行号、grep 结果、测试数字。"源仓库架构混乱"是判断；"全仓库零个 `FastAPI()` 首方调用，唯一 `APIRouter` 自述 'Not mounted into any app yet'"是证据。
3. **Enforcement 段必须诚实。** 写"由架构测试执行"却没有测试，比写"当前仅为意图"更有害——后者是已知缺口，前者是虚假安全感（R14 伤疤：源仓库把策略写成 TS 常量然后违反了它）。
4. **不得原地重写已 Accepted 的 ADR 的 Decision。** 决定变了就写新 ADR。但**记录后续 override 是允许且必要的**——见 ADR-0003 的"后续变更：project-owner override"段，它记录了决定被部分回退的事实与附带约束，而不是把原决定悄悄改掉。
5. **禁止在实现 PR 中顺手改 ADR 或宪章**（宪章第 3 节）。

---

## References

- `governance/REPOSITORY_CONSTITUTION.md` 第 3 节（修宪程序）、R14（架构测试强制）
- `docs/12_governance/DOCUMENT_GOVERNANCE.md` §1（五类信息区分）、§末（三级晋升链）
- `docs/00_system/SYSTEM_MANIFEST.md`（canonical 文档入口）
- `CLAUDE.md` 铁律第 8 条
