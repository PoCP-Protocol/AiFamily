# ADR-0017: 能力级环境晋升门 —— dev / test 用合成数据，接真实家庭数据须过门

- **Status**: Accepted
- **Date**: 2026-08-29
- **Deciders**: project-owner（提出交付顺序）/ chief-architect（门的形状）
- **Supersedes**: null
- **Superseded By**: null

> **解释修正（2026-08-30）**：本 ADR 只规定不同环境的数据准入，不授权任何环境缺少业务功能。开发、测试、生产的功能、流程、规则和路由必须完全等价；相关约束见 ADR-0020。`SYNTHETIC_ONLY` 是数据类别门，不是功能成熟度或功能开关。

## Context

### 1. project-owner 的纠正，以及它纠正了什么

2026-08-29，project-owner 指出 chief-architect 反复表述的一个错误：

> 系统、平台的开发，是先建开发系统、再建测试系统，最后才是生产系统。
> 开发阶段、测试阶段都是用测试数据来做的，只有生产环境才接入真实数据。
> **前面不做好，怎么敢接真实的数据。**

被纠正的错误是：chief-architect 反复以
「34 屏可工作数 = 0 → 真实用户 = 0 → 学习信号 = 0」为由，
把「自我学习」判为受阻于交付进度，并在「不该现在做」清单里列入「不建学习管道」。

**该链条隐含一个危险主张**：要先接真实家庭数据才能建学习闭环。
对一个处理未成年人敏感个人信息的系统，这不仅工程上不对——
`docs/12_governance/COMPLIANCE_HARD_CONSTRAINTS.md` §2 要求处理前先做 DPIA，
未经验证的系统接入真实儿童数据本身即可能违法。**该条错误撤回。**

**同时撤回一个被引错的先例**：chief-architect 引用伯乐世界模型「结构全建但真实数据 = 0」
作为「不要先建结构」的论据。该先例的真实教训是
「**不要在有数据之前声称有效**」（问题出在只有结构却声称 `canDrive`），
**不是**「不要在有数据之前建」。两者差别重大，原引用是误读。

### 2. 但有一件事合成数据原理上做不到，这个区分是本 ADR 的支点

```text
验证正确性  代码是否按声明工作（schema / 契约 / 集成 / 失败模式 / 边界）
            → 合成数据完全够用，且必须用合成数据

验证有效性  这个干预对这个家庭真的有用吗？模型判断能否预测结果？
            → 合成数据原理上答不了：合成时就把因果写进去了，
              于是"验证"只会得出你假设的那个答案
```

第二件事**根本不是测试阶段的活动**，它只能在生产环境用真实数据完成。
把它安排进测试阶段，产出的是自我印证。

### 3. 这个区分本仓库已经写成规则，此前被违背

- `backend/packages/contracts/evidence.py:34-41`：
  `NON_ESTABLISHING_LEVELS = frozenset({"simulated", "inferred", "unverified", "unknown"})`
  —— 这些等级「可以生成假设 / 设验收门，但**永不能用于宣称成立**」。
- `backend/intelligence/design_copilot/simulation.py`：作者已做对同一切分——
  `run()`（需真实家庭数据校准参数）是 `NotImplementedError`，
  而 `promote_to_pilot()`（护栏，结构）**是真实实现的**。
  `MIGRATION_MANIFEST.yaml` 中该能力的 override 原文即
  「**structure first, guessed parameters never**」。

**结论**：管道现在就该建、就该用合成数据跑通；只是其产出在校准前一律 `simulated`，
不得用于建立任何结论。此前「不建学习管道」的判断错误，本 ADR 撤回它。

### 4. 该流程唯一的真实风险，恰好是本仓库的立仓病因

`governance/REPOSITORY_CONSTITUTION.md` R5 的伤疤原文：
源仓库 `dev-platform-surfaces.service.ts:26-33` 与 `dev-core-growth.service.ts:43-60`
在返回体里自述 `data_source: 'SYNTHETIC_DEV_ONLY'`、`model_gateway: 'NOOP_NOT_INVOKED'`，
内容是 24 张硬编码 UI 卡片与一本中文文案字典，
**却通过 `family.controller.ts:280,295,313,326` 挂在生产 HTTP 路由上**，前端因此渲染假数据。

**这就是测试数据泄进生产。** dev→test→prod 的流程是正确的，
而它的纪律要求是 R5 的**物理隔离**——合成资产在路径与命名上与业务代码分开，
不能靠开发者记得。

### 5. 实测缺口：环境概念只存在于供应商层，不存在于能力层

| 层 | 环境门 | 实况 |
|---|---|---|
| provider | `approved_environments` | **已存在**。`provider_registry.py` 中 FakeProvider 限 `("test","development")` |
| capability | — | **完全不存在**。没有任何机制阻止一个未验证的能力接真实家庭数据 |

`governance/CAPABILITY_REGISTRY.yaml` 的 `status` 词表描述的是**实现成熟度**
（`IMPLEMENTED_TESTED` 等），**不是数据准入资格**。二者不可互相替代：
一个能力可以「有测试」而仍然**不该**看真实儿童数据（例如尚未做 DPIA）。

同时，DPIA 是法定的那道门（PIPL 第 55/56 条，记录须留存 ≥3 年），
而它当前只是 `docs/12_governance/DPIA_MECHANISM_DESIGN.md` 一份设计文档，**不是一个门**。

## Decision

### 1. 三环境，且数据类别按环境硬性收窄

```text
development   仅合成数据（data_class = SYNTHETIC）
test          仅合成数据 + 对抗性夹具（矛盾证据 / 缺失数据 / 恶意输入 / 边界值）
production    真实数据。是唯一能回答"有效性"的环境
```

**任何 `data_class` 为 `FAMILY_PRIVATE_TEXT` 或 `MINOR_PERSONAL_DATA` 的请求，
在 development / test 环境一律拒绝**（fail-closed，不是警告）。
这条同时封住「用真实数据做开发调试」这条最常见的越界。

### 2. 新增 capability 的 `data_admission` 字段，与 `status` 正交

```text
data_admission:
  SYNTHETIC_ONLY      默认值。可跑，但只能见合成数据
  PILOT_REAL_DATA     可见真实数据，限定范围（受控试点，须有退出机制）
  PRODUCTION          可见真实数据，无范围限定
```

**必须与 `status` 正交，不得合并**：`status` 答「实现多成熟」，
`data_admission` 答「有没有资格看真实数据」。
一个 `IMPLEMENTED_TESTED` 的能力其 `data_admission` 完全可以是 `SYNTHETIC_ONLY`
——测试通过不等于获得数据准入资格。**把两者合并会使 DPIA 门被实现进度自动打开。**

### 3. 晋升到 `PILOT_REAL_DATA` / `PRODUCTION` 的前置条件（全满足，缺一不得晋升）

1. **DPIA 已完成并留档**（PIPL 第 55/56 条；记录留存 ≥3 年）。
2. **该能力的验收测试在 CI 中真实运行并通过**（R4 的字面要求：须能在 CI 中真实运行）。
3. **可解释性就绪**：若产出属自动化决策，`AiProvenance` 完整
   （`COMPLIANCE_HARD_CONSTRAINTS.md` §2）。
4. **删除路径就绪**：含派生数据（embedding / 向量 / 投影）的按主体级联删除已实现并测试
   （§6，法定义务，**不得「先上线再补」**）。
5. **同意粒度就绪**：按目的的同意与撤回路径存在（§5）。
6. **人类可否决路径就绪**：若属自动化决策，存在人工复核或拒绝路径（§2）。
7. **涉未成年人的能力额外要求**：明示留存期限 + 到期处理方式（§1）。

**晋升是一次显式动作，须记录在 registry 且注明依据。**
不得由「测试通过了」自动触发。

### 4. 有效性结论只能来自 production，且不得回填

在 `production` 之前产生的任何效果类结论，其 `Provenance.level` 一律为 `simulated`，
因此按 `evidence.py:34-41` **永不能用于宣称「成立」**。

**禁止回填**：不得在获得真实数据后，把此前基于合成数据的结论「升级」为已验证。
合成数据产出的假设仍是假设；真实数据须重新验证一次。

### 5. 撤回此前的错误判断

- **撤回**「不建学习管道」。学习闭环的**代码**应现在建、用合成数据跑通，
  属 development / test 阶段的正当工作。
- **保留**「不建空目录占位」（ADR-0015 §3、`CURRENT_AI_MAP.md` §6 的「目录名冒充能力」）
  —— 这两条不冲突：**建可运行且有测试的管道 ≠ 建一个全是 `NotImplementedError` 的目录。**
- **保留**「人类辅助提示流是冷启动期可得的学习信号」（ADR-0016 §4），
  但更正其定位：它**不是**替代真实数据的手段，而是 production 阶段真实信号的一部分；
  在 test 阶段它同样是合成的。

## Alternatives Considered

### A. 不设能力级门，靠 `CAPABILITY_REGISTRY.status` 与 code review
**支持理由**：少一个字段与一套流程；`status` 已经表达了成熟度，再加一维增加认知负荷；
团队规模小，谁能看真实数据靠沟通即可。

**否决理由**：**`status` 与数据准入是两个正交问题**，合并会造成一个具体危害——
DPIA 门被实现进度自动打开（测试一通过，能力"就绪"了，于是有人接上真实数据）。
而 DPIA 是法定前置，不是工程里程碑。
且「靠沟通」正是 R14 反复警告的形态：**未被机械检验的规则只是意图**。

### B. 只在部署层隔离（生产环境不给测试代码部署权限）
**支持理由**：运维层隔离最彻底，代码里不需要任何环境判断；符合十二要素应用的思路。

**否决理由**：**R5 的伤疤直接反驳它。** 源仓库的 `dev/*` 服务是**正式部署到生产的业务代码**
——它不是"测试代码被误部署"，而是合成数据服务被写成了业务能力并挂上生产路由。
部署隔离拦不住这种形态，因为违规代码本身就是"生产代码"。
门必须在**能力准入**这一层，而不只在部署管道。

### C. 允许在 development 环境使用真实数据的脱敏副本
**支持理由**：脱敏后的真实数据比合成数据更能暴露真实分布与边界情形；
业界常见做法；能显著提高测试有效性。

**否决理由**：对本平台**不采纳**。14 岁以下个人信息按 PIPL 第 28 条**按类别**属敏感信息，
脱敏是否充分是逐案判断且极易出错（家庭教育文本中的间接标识符密度很高——
学校、班级、就医经历、亲属关系）。收益（更真实的分布）不足以承担
「未成年人敏感信息进入开发环境」的风险。
**若将来确有必要，须单独出 ADR 并附法律意见**，不得以本 ADR 为依据放开。

## Consequences

### 正面
- 「怎么敢接真实数据」这个问题有了可执行答案：七条前置条件 + 一次显式晋升动作。
- 撤回了一条会导致过早暴露真实家庭数据的错误主张。
- 学习闭环的建设被解除阻塞——可以现在建、用合成数据验证正确性。
- 「验证正确性 / 验证有效性」的区分被写进 canonical，且与 `NON_ESTABLISHING_LEVELS` 对齐。

### 负面 / 代价
- 新增一个 registry 维度，认知负荷上升；且它与 `status` 容易被误用为同义词
  （已在 §2 显式禁止合并）。
- 七条前置条件会实质延后第一个能力接真实数据的时间。**这是本 ADR 有意接受的代价。**
- 合成数据的构造成本真实存在，尤其是对抗性夹具（矛盾证据、缺失数据）。
- 禁止回填意味着部分验证工作要做两次（合成一次、真实一次）。

### 需要接受的风险
- **合成数据的分布偏离真实分布**，因此 test 阶段全绿不代表 production 不出问题。
  本 ADR 不解决这一条，只要求不把它误读为已验证（靠 §4 的 `simulated` 等级）。
- **DPIA 的实质质量无法由架构保证。** 一份形式合规但草率的 DPIA 会打开这道门——
  与 ADR-0014 记录的「人工确认是否实质审阅」是同一类不可检验问题。
- 七条前置中的第 4 条（派生数据级联删除）在 `graph_projection.*` 尚不存在时无从测试，
  因此 Growth Graph 相关能力的晋升会被这一条实质阻塞。**这是正确的阻塞，不是缺陷。**

## Enforcement

| 裁决 | 机制 | 状态 |
|---|---|---|
| §1 dev/test 拒绝真实数据类别 | **可机械执行且成本极低**：`model_gateway` 的 admission 阶段按 `(environment, data_class)` 拒绝。`provider_registry` 已有 `approved_environments` 的同类先例可照抄 | **未落地** |
| §2 `data_admission` 字段存在且合法取值 | `tests/architecture/test_capability_registry.py` 已有 YAML 校验范式，加一条枚举断言即可 | **未落地** |
| §2 与 `status` 不得合并 | 可断言：`data_admission` 为 `SYNTHETIC_ONLY` 的条目允许任意 `status` | **未落地** |
| §3 七条前置 | **部分可检验**：第 2 条（CI 中真实运行）可查；第 4 条（删除路径）可查测试存在性；**第 1/3/5/6/7 条不可机械检验**，属人工审查 |
| §4 有效性结论只能来自 production | `NON_ESTABLISHING_LEVELS` **已在执行**（`product_strategy.promote_to_invest` 与 `SimulationLab.promote_to_pilot` 两处独立执行点） | **部分有效** |
| §4 禁止回填 | **不可机械检验** —— 「这个结论是否被回填」是语义判断 |
| §5 撤回项 | 文档性，无需执行者 |

**补齐路径**：§1 与 §2 的三条检查**应优先落地**，它们成本低且是本 ADR 唯一的机械执行者。
在它们落地之前，本 ADR 的门只是意图——而一个只是意图的数据准入门，
比没有门更危险（它提供虚假安全感，这是 R14 的原话）。
任务卡见 `TASK_BACKLOG.md`（下一个可用编号）。

## References
- project-owner 2026-08-29 会话：dev → test → prod 交付顺序的纠正
- `governance/REPOSITORY_CONSTITUTION.md` R4（须在 CI 中真实运行）、R5（含伤疤原文）、R14
- `backend/packages/contracts/evidence.py:34-41`（`NON_ESTABLISHING_LEVELS`）
- `backend/intelligence/design_copilot/simulation.py`（structure first / parameters never 的既有先例）
- `backend/intelligence/model_gateway/provider_registry.py`（`approved_environments`，本 ADR §1 照抄其形状）
- `governance/CAPABILITY_REGISTRY.yaml`（`status` 词表；本 ADR 新增正交维度）
- `docs/12_governance/COMPLIANCE_HARD_CONSTRAINTS.md` §1 / §2 / §5 / §6；`DPIA_MECHANISM_DESIGN.md`
- ADR-0006（未成年人合规硬约束）、ADR-0010 §派生数据级联删除、
  ADR-0014（不可检验项）、ADR-0015（领域模型证据缺口）、ADR-0016 §4（人类提示流的定位更正）
