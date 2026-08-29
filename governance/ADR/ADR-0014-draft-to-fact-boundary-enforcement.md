# ADR-0014: Draft → Fact 边界的执行机制（R9 靠审计与 AST，不靠类型）

- **Status**: Accepted
- **Date**: 2026-08-29
- **Deciders**: chief-architect（project-owner 可 override §5）
- **Supersedes**: null
- **Superseded By**: null

## Context

R9 是本仓库最重的一条红线：`Fact ≠ Perspective ≠ Recommendation ≠ Action`，
AI 推断永不得直接写入家庭权威事实。ADR-0005 §3 进一步定性：AI 原生使 R9
「不是边角规则，是**主数据模型的骨架**」。

一个自然的设计冲动是**让 R9 成为类型层属性**——把违规做成不可表达。
`backend/intelligence/model_gateway/contracts.py:20-25` 的模块 docstring 记录了作者朝这个方向的
努力与推理，而且推理本身是对的：

> `ModelDraft.may_mutate_business_state` is a property returning `False`. Not a field with a
> `False` default — a default can be overridden at construction; a frozen dataclass field can
> still be replaced via `dataclasses.replace`.

**但这个努力只覆盖了一个字段。我对当前落盘代码做了四项实测（`uv run python`，2026-08-29）：**

```text
baseline                    status = DRAFT   may_mutate = False
LEAK-1  ModelDraft(output={}, provenance=p, status="APPROVED").status
        → "APPROVED"      Literal 是 typing-only；ModelDraft 整个类没有 __post_init__
LEAK-2  dataclasses.replace(d, status="CONFIRMED").status
        → "CONFIRMED"     作者为 may_mutate 点名防住的危险，原样落在 status 上
LEAK-3  d.output["injected"] = "fact"
        → {'a': 1, 'injected': 'fact'}     frozen=True 不深冻结 payload，dict 是可变别名
LEAK-4  class Evil(ModelDraft): @property may_mutate_business_state → True
        → True            slots=True 不阻止继承；"无 setter 的 property"挡不住子类覆盖
```

四处全部复现。**结论：`may_mutate_business_state` 的 property 封印只挡住了作者点名的那一个
危险（`dataclasses.replace`），挡不住子类化；而 `status` 连那一个都没挡。**

比这四处更根本的一点：**Fact 不是一个对象的属性，而是「某一行落进了权威表」这个事件。**
调用方永远可以 `dict(draft.output)` 然后自己拼 dict 写库——类型系统对此原理上无话可说。

### 第二类证据：现有护栏的判据可以被参数名骗过

`tests/architecture/test_compliance_constraints.py` 有一条检查——晋升到
`VALIDATED` / `APPROVED` / `CONFIRMED` 的函数必须有「人类 actor 形状的参数」。
它是真 AST 检查，不是摆设。但它的判据是**参数名形状**，而：

- `backend/domains/assessment/service.py:149-156` 的 `decide()` 签名是
  `decide(self, actor_id: str, family_id: str, session_id: str, hypothesis_ref: str, decision_type: str)`；
- 它在 `:164` 执行 `hypothesis["status"] = "CONFIRMED" if decision_type == "CONFIRM" else "DISMISSED"`；
- **它通过了检查，因为有一个叫 `actor_id` 的参数——而那只是一个 `str`。**

同时 `backend/platform/identity/context.py:66-75` 的 `ActorContext.is_ai` 是 R9 唯一的密封缝
（该文件 docstring `:11-17` 自述「`ActorContext.is_ai` 是每个上层必须使用的 seam」），
而 **assessment 域全域不使用 `ActorContext`**，也不使用
`backend/platform/authorization/policy.py` 的 `PolicyEngine`
（对照 `backend/domains/membership/api/routes.py:85-107` 的 `_authorize`——那是仓库内唯一正确的接入模式）。

**净效果：当前没有任何东西阻止一个 AI actor 确认一个假设。**
`assessment/api.py:53-59` 的 `actor()` 只校验 Bearer token 与 family 匹配，不问 actor 类型。

### 第三类证据：AI Runtime 侧的红线也没有执行者

`docs/11_delivery/TASK_BACKLOG.md` T-06 把「`backend/intelligence/` 下的代码**不得** import
任何业务域的 repository」写为红线，但其验收标准只要求**已有的**
`test_no_direct_provider_calls.py` 仍绿。`docs/05_ai/AI_NATIVE_PRINCIPLES.md` §5 自列的两项
「待补（Wave 2+）」检查——`may_mutate_business_state=false` 的静态检查、
AI 产出初始 status 检查——**至今未补**。

这正是 R7 伤疤的原始形状：源仓库把
`AI_GATEWAY_POLICY = { business_module_direct_provider_call: 'forbidden' }` 写成常量然后违反了它。
**红线写在任务卡里而没有护栏，与写成常量是同一种失效。**

## Decision

### 1. 放弃「让 R9 成为类型层属性」这个目标，改为三层机制

明确写下：**在 Python 中，把「AI 输出跨越为事实」做成不可表达是做不到的**（上述四项实测 + Fact 是事件而非属性）。
任何声称做到了的设计都在提供虚假安全感，按 R14 比承认缺口更有害。

替代为三层，各层职责不重叠：

```text
第 1 层  类型挡意外      —— 防手滑，不防绕过
第 2 层  PolicyEngine + AuditEvent 挡越权 —— R9 挂到 R6 上，是主承重层
第 3 层  AST 挡绕过      —— 防「自建 dict 写库」这条类型看不见的路
```

### 2. 第 1 层：补齐 `ModelDraft` 的四处封印（属 T-06 范围，本 ADR 只下规格）

| 泄漏 | 修法 |
|---|---|
| LEAK-1 / LEAK-2 | 加 `__post_init__`，`if self.status != "DRAFT": raise ValueError(...)`（`replace` 也走 `__post_init__`，一处修两个泄漏） |
| LEAK-3 | `output` 存 `MappingProxyType(deepcopy(raw))`，类型注解改 `Mapping[str, Any]` |
| LEAK-4 | `def __init_subclass__(cls, **kw): raise TypeError("ModelDraft is sealed")` |

同时修正 `contracts.py:53-57` 与 `:202-210` 的 docstring 措辞：
「there is no gateway-side transition out of it」**对 gateway 成立，对类型不成立**——
两件事必须分开陈述，否则下一个读者会以为类型已经封死。

**本 ADR 不执行这四处修改**：`contracts.py` 属 T-06 执行者的范围且当前为未提交 WIP，
按 `AGENTS.md` 第 1 条「别人的 WIP 一律不碰」，改为出具本规格 + 任务卡（见 §6）。

### 3. 第 2 层（主承重）：跨越 Fact 必须经 `PolicyEngine`，且 `HumanDecision` 只能由它产出

**这是本 ADR 对既有设计最重要的一处修正。**

一个看似合理的设计是「`HumanDecision` 只能从 `is_ai is False` 的 `ActorContext` 构造」。
**这是假门**——`ActorContext` 是公开的 frozen dataclass，`__post_init__`（`context.py:58-64`）
只校验三个字段非空，**任何调用方都能自己造一个 `actor_type=ActorType.HUMAN` 的实例**。

正确形态：

```python
# HumanDecision 不可由调用方直接构造。
# 唯一构造路径 = PolicyEngine.check() 返回 Decision(allowed=True) 后由引擎签发。
decision = policy.check(actor, action="assessment.confirm_hypothesis",
                        resource_type="GrowthHypothesis")
# 规则注册时 human_only=True → policy.py:100-105 在任何 allow 逻辑之前无条件拒绝 AI actor
```

理由：`PolicyEngine` 已经是**真的** fail-closed（`policy.py:94-98` 未注册即 DENY；
`:100-105` 的 `human_only` 检查位于 allow 逻辑之前，且**不存在注册 DENY 规则的接口**——
DENY 是结构性默认）。把 R9 挂在它上面，而非挂在类型上，收益是：
**引擎调用点必然产生 `AuditEvent`（R6），而审计是持久的、可查的、可事后复核的；类型不是。**

配套要求：`AuditRecorder.flush()` 目前是**明文 no-op**（`recorder.py:35-43` 自述），
审计只在进程内存。**在审计落库之前，第 2 层只有一半强度**——这一点必须在
`docs/06_platform/` 与 `CURRENT_SYSTEM_BASELINE.md` 如实记录，不得表述为「R6 已执行」。

### 4. 第 3 层：三个 AST 护栏（本批落地）

| 护栏 | 拦什么 | 关键判据 |
|---|---|---|
| `tests/architecture/test_ai_draft_boundary.py` | ① 晋升态字面量赋值出现在无 `HumanDecision` 类型注解的函数里；② `ModelDraft(...)` 在 `model_gateway/` 外被直接构造；③ `dataclasses.replace` 作用于类型名含 `Draft` 的对象 | **判据按类型注解，不按参数名**——这是与现有 compliance 检查的关键差异，正是为了不再被 `actor_id: str` 骗过 |
| `tests/architecture/test_ai_runtime_isolation.py` | `backend/intelligence/**` import 任何 `backend.domains.*`、任何 `*Repository`/`*UnitOfWork`/`sqlalchemy*` | **一条线，无例外**（见 §Alternatives C） |
| `tests/architecture/test_credential_boundary.py` | 凭据读取出现在 `model_gateway/` 之外 | 键名匹配 `(?i)(api_key|secret|token|credential|_key)$` 时**不给任何白名单** |

### 5. 附带裁决：GROWTH 屏幕（UI-08/11/12/29）保留文件，当前形态不得上线

`docs/00_system/TARGET_ARCHITECTURE.md` §6 第 3 项待裁决。这四屏被标 `GATE_BOUNDARY`
**不是技术缺口，是 R9 主动限制的结果**（`AI_ARCHITECTURE.md` §4.2 已如此定性）。

裁决：
- **不删文件。** 删除等于丢弃已迁入的 UI 资产；且它们不挂后端不会渲染假数据，留存无风险。
- **当前形态不得挂生产路由。**
- **重启判据**：该屏能在**不呈现家庭总分 / 排名 / 等级**的前提下表达「成长样态」。
  达不到这个判据的重设计方案不予通过。
- 排在 Batch 4 之后，不进任何近期批次。

**本条含产品面判断，project-owner 可 override。** 但 R9 红线本身不可 override
（它同时是 ADR-0006 记录的法定约束的一部分）。

### 6. 本 ADR 产出的任务卡（写入 `TASK_BACKLOG.md`）

- **T-16**：修 `ModelDraft` 四处封印（§2 规格）+ 修 docstring 措辞。归 T-06 执行者。
- **T-17**：assessment 域接 `ActorContext` + `PolicyEngine`（`human_only=True`），
  照 `membership/api/routes.py:85-107` 抄；`/auth/*` 寄居问题见 ADR-0011 §4。归 T-05。

（两卡原取号 T-11 / T-12，与并发会话 commit 消息中已使用的同号工作撞号，重编为 T-16 / T-17。）

## Alternatives Considered

### A. 坚持类型封印路线，把 `ModelDraft` 做成 pydantic 严格模型
**支持理由（不弱）**：pydantic v2 **会**在运行时校验 `Literal`，LEAK-1/LEAK-2 直接消失；
项目已依赖 pydantic（`pyproject.toml`），`backend/packages/contracts/evidence.py:44` 的
`Provenance` 就是 pydantic 模型，风格一致；`model_config = ConfigDict(frozen=True)` 亦可禁改。

**否决理由**：它修掉的是 LEAK-1/2，**修不掉根本问题**——
`model_copy(update={"status": "APPROVED"})` 是 pydantic 的正常 API；
`dict(draft.output)` 之后自己拼 dict 写库仍然畅通无阻；子类化仍可覆盖 property。
**换一个更严的类型系统不改变「Fact 是事件而非属性」这个事实。**
pydantic 化本身是好改进（应作为 §2 的可选实现方式），但把它当作 R9 的执行机制
仍然是虚假安全感。第 2/3 层不可省。

### B. 只靠 code review 与 ADR，不加 AST 护栏
**支持理由**：AST 护栏有假阳性维护成本；R9 的语义面（模型是否输出了像诊断的话）
本来就只能靠人；`test_compliance_constraints.py` 已有 8 个检查器，边际收益递减。

**否决理由**：R14 是宪章条款而非偏好，其伤疤就是「策略写成常量然后被违反」。
且**现成的反例正在仓库里**：assessment 的 `decide()` 通过了参数名启发式，
说明 review 与既有护栏都没拦住。假阳性的成本是一次 review 争论；
漏掉的成本是一个 AI actor 确认了关于某个真实儿童的判断。

### C. 允许 `backend/intelligence/` import `backend/domains/*/application/ports.py`（它们是 Protocol）
**支持理由**：Protocol 是抽象契约不是实现，import 它不引入持久化依赖；
AI Runtime 总要知道领域词汇；一条线无例外会导致大量词汇重复定义。

**否决理由**：**实测反驳。** `backend/domains/product_intelligence/application/ports.py`
顶部从 `..domain.entities` import 了 19 个业务实体
（`ContradictionModel` / `CustomerInsight` / `GrowthHypothesis` / `MarketSignal` …）。
放行 ports.py 等于把整张业务实体图拉进 AI Runtime，
`may_mutate_business_state=false` 的隔离立刻名存实亡。
正确做法是**反转依赖方向**：domain 自己定义 port 并 import gateway 的 `ModelDraft`
（这正是 R7 要求的方向），gateway 不知道 domain 存在。
共享词汇走 `backend/packages/contracts/`——已是仓库唯一真正跨域共享的原语。

### D. 建 `backend/intelligence/human_gate/` 作为独立的闸门组件
**支持理由**：`CURRENT_AI_MAP.md` §3 第 9 项把 Human Gate 列为 R10 的 12 个组件之一，
目标位置写的就是 `backend/intelligence/human_gate`；独立组件便于集中 R8 的过闸清单。

**否决理由**：`backend/platform/authorization/policy.py` 已经是一个真的 fail-closed 决策点，
且 `human_only=True` 正是为 R9 设计的（`policy.py:50-57` 的 docstring 明说）。
**R8 的闸门属平台能力而非 AI 能力**——它要闸住的不只是 AI，也包括权限不足的人类 actor。
再建一份就是 R10「各一份」的直接违反，且会重演源仓库「一份实现三套接入模式」的伤疤。
建议 `CURRENT_AI_MAP.md` 的该行目标位置改为
`backend/platform/authorization`（+ 说明），而不是新建目录。

## Consequences

### 正面
- R9 的执行从「一个字段的类型」变为「审计链 + fail-closed 引擎 + AST」，三者失效模式不相关。
- 四处泄漏被实测定位并有明确修法，不再是「大概挡住了」。
- 参数名启发式的漏洞被显式记录并有替代判据（类型注解）。
- T-06 那条无执行者的红线获得执行者。

### 负面 / 代价
- 三个新 AST 护栏是长期维护负担，会产生假阳性（尤其 §4 的判据 ①，
  一个合法的状态机迁移函数可能被误判）。缓释：豁免必须像
  `test_compliance_constraints.py` 的 `FIELD_TOKEN_EXEMPTIONS` 那样**写明理由**，不允许裸豁免。
- 第 2 层的强度取决于审计落库，而 `AuditRecorder.flush()` 当前是 no-op。
  **本 ADR 落地后 R6 仍未完整执行**，这是已知缺口不是遗漏。
- assessment 域接 `ActorContext` 会破坏
  `tests/domains/assessment/test_acceptance_chain.py`（全部位置实参调用）与
  `tests/apps/family_api/test_assessment_routes.py`，代价落在 T-12。

### 需要接受的风险
- **§4 的护栏落地时，第 3 层拦的是「以已知形状绕过」。** 一个足够有创意的绕过
  （反射、`exec`、字符串拼 ORM）不会被拦。这不是可修的，是静态分析的固有边界。
- 第 5 项的产品裁决可能与产品侧意图冲突。

## Enforcement

**分层记录，逐条说明真实状态——本 ADR 最不能含糊的一段。**

| 层 | 机制 | 本 ADR 落地后的真实状态 |
|---|---|---|
| 1 类型挡意外 | `ModelDraft` 四处封印 | **未落地**，规格已出，属 T-11（他人范围） |
| 2 审计留痕 | `PolicyEngine`（`human_only=True`）+ `AuditEvent` | 引擎**已存在且真 fail-closed**；但 assessment 尚未接入（T-12），且 `flush()` 是 no-op → **半强度** |
| 3 AST 挡绕过 | 三个新测试 | **本批落地**，且每个都必须验证"会咬人"（植入违规→失败→移除）并在提交说明贴过程 |
| CI | 让上述护栏真正运行 | `.github/workflows/ci.yml:29-38` 当前只无条件跑 `tests/architecture`，`tests/platform`/`domains`/`apps`/`intelligence` **从未在 CI 跑过**，且无远端仓库 → **在 CI 修好之前，本 ADR 的第 3 层在 CI 中不生效** |

### 机械手段挡不住、必须靠 review / ADR 的（不得假装有护栏）

1. **AI 输出的语义**是否真的只是 Perspective——模型可以输出一句听起来像临床诊断的话，
   而所有类型检查与 AST 全绿。
2. **`data_class` 是否申报正确**——`contracts.py:88` 强制该字段无默认值，
   但把未成年人数据报成 `OPERATIONAL_TEXT` 没人能查。
3. **prompt 内容是否诱导打分/排名**——`test_no_scoring_or_ranking_fields_anywhere` 只看字段名。
4. **不得转委托**（provider 是否再分包给第三方云）——合同问题。
5. **凭据从外部 config 对象注入**——数据流问题，AST 原理上看不到。
   结构性缓释：`build_gateway()` 的签名不设 `api_key`/`credential`/`config` 形参，
   并加测试断言其 `inspect.signature`——把"能不能查出"变成"根本没有形参可传"。
6. **确定性 provider 是否可从生产路由到达**——Python 中不可静态证明
   （`getattr` / DI / 字符串 provider_id 查表均可绕过）。
   只能靠 `FakeProvider.__init__` 的运行时环境断言 + `provider_registry` 的
   `approved_environments` 不含 production。**这是"可测试 + 运行时拦截"，不是护栏，ADR 不得写成护栏。**
7. **人工确认是否实质审阅**——**这是全部约束中最危险的一条**，因为它会让其他所有护栏
   在形式上通过而实质失效。部分转化路径见
   `docs/05_ai/AI_PLATFORM_FORWARD_ARCHITECTURE.md` §5（闸门健康度可统计监测：
   审阅耗时分布 / 驳回率 / 批量确认比例。**一个驳回率为零的闸门是坏了的闸门**）。

## References

- 实测证据：本文件 §Context 的 LEAK-1..4，对 `backend/intelligence/model_gateway/contracts.py`
  当前落盘版本执行，2026-08-29
- `backend/intelligence/model_gateway/contracts.py:20-25, 53-57, 184-214`
- `backend/platform/authorization/policy.py:50-57, 91-115`（真 fail-closed 的证据）
- `backend/platform/identity/context.py:11-17, 58-64, 66-75`（`is_ai` 密封缝）
- `backend/platform/audit/recorder.py:35-43`（`flush()` 为 no-op）
- `backend/domains/assessment/service.py:149-156, 164`；`api.py:53-59`（绕过密封缝的实例）
- `backend/domains/membership/api/routes.py:85-107`（唯一正确的接入模式）
- `backend/domains/product_intelligence/application/ports.py`（Protocol 携带 19 个业务实体的证据）
- `tests/architecture/test_compliance_constraints.py`（参数名启发式的位置）
- `.github/workflows/ci.yml:29-38`
- `governance/REPOSITORY_CONSTITUTION.md` R6 / R7 / R9 / R10 / R14 及其伤疤
- `docs/05_ai/AI_NATIVE_PRINCIPLES.md` §5（两项待补检查）；`docs/05_ai/AI_ARCHITECTURE.md` §4.2 / §4.3
- `docs/00_system/TARGET_ARCHITECTURE.md` §6 第 3 项（GROWTH 屏幕裁决来源）
- `docs/11_delivery/TASK_BACKLOG.md` T-06（红线原文与其缺失的验收项）
- ADR-0005 §3（R9 是主数据模型骨架）、ADR-0006、ADR-0010、ADR-0011 §4
- `docs/05_ai/AI_PLATFORM_FORWARD_ARCHITECTURE.md` §5（闸门健康度）
