---
id: RES-TECH-004A
title: 4a — Agent Runtime 工具注册与权限边界（含公开失败案例）
type: research
status: draft
version: 1.0
owner: chief-architect
created: 2026-08-29
updated: 2026-08-29
canonical: false
supersedes: null
superseded_by: null
---

```text
STATUS: RESEARCH_ONLY
NOT_CANONICAL: TRUE
本文件是证据，不是决定。晋升须走 ADR（docs/12_governance/DOCUMENT_GOVERNANCE.md §8.2）。
不得直接据此修改 docs/05_ai/AI_ARCHITECTURE.md。
```

# 4a — 生产环境如何防止 agent 越权调用工具

**被检验的对象**：`docs/05_ai/AI_ARCHITECTURE.md` §4.3（R7 + R10：AI Runtime 不得直接 import 业务域 repository，只能经 Named Action 写入）与 §4.4（R8 高影响行为过闸清单）。这两节目前是**内部自证的架构约束**，本节寻找外部证据判断它们是否足够。

**本轮拆分理由**：上一轮把 Agent Runtime / Context / guardrail / Gateway / eval 五个方面塞进一个问题，检索角度过宽。4a 单独聚焦"工具权限边界"，并要求必须找到**具名的、有 CVE 编号的生产失败案例**——这是让声明可 falsify 的最直接办法。

---

## 1. 具名生产失败案例：EchoLeak / CVE-2025-32711

### 声明 4a.1｜存在已编号的真实零点击 prompt injection 漏洞，攻击链跨越四层防御
**置信度：high（有 CVE 编号 + 学术论文复盘 + 厂商已修复）**

来源：arXiv `https://arxiv.org/html/2509.10540v1`（"EchoLeak: The First Real-World Zero-Click Prompt Injection Exploit in a Production LLM System"），标的为 Microsoft 365 Copilot，CVE 编号 **CVE-2025-32711**。

攻击链（四步，每一步都绕过一层已部署的防御）：

1. **绕过 XPIA 分类器**：攻击者把指令写成正常商务措辞的邮件，不含显式命令，规避微软的 prompt-injection 分类器
2. **绕过链接脱敏**：Copilot 会脱敏内联 Markdown 链接，攻击者改用 **reference-style Markdown 链接**，过滤器未覆盖
3. **图片自动加载外泄**：reference-style 图片标签指向攻击者 URL，客户端 UI 无需点击自动加载（零点击）——此步初始被 CSP 拦住
4. **绕过 CSP**：把图片 URL 走 **Microsoft Teams 异步预览 API**（该域在 Copilot CSP 白名单内），由服务端代取攻击者 URL，完成外泄

时间线：2025-01 Aim Labs 完成 PoC 并报 MSRC → 2025-04 开始修复 → 2025-05 服务端修复上线（无需客户操作）→ 2025-06-11 CVE 公开。论文称无野外利用证据。

**论文把失效的信任边界命名为 "LLM Scope Violation"**：不可信外部内容（一封邮件）被当作指令，并被允许触发跨越内部数据访问与外部网络出口的动作，可信内部上下文与不可信入站内容之间**没有隔离**。

**这条声明为什么可 falsify**：它有 CVE 编号、有厂商修复记录、有具体绕过手法。任何"我们做了输入过滤所以安全"的架构主张都被这条案例直接反驳——微软同时部署了分类器、链接脱敏和 CSP，三层全部被绕过。

### 声明 4a.2｜论文给出的可迁移设计教训是"内容来源标注 + 最小权限 + 出口独立管控"
**置信度：medium-high（论文建议，非实证测量）**

论文强调：把所有外部输入当作潜在对抗性指令，用 **content source tagging** 做隔离（把不可信文本包进 `<ExternalContent>…</ExternalContent>` 之类标记），使模型"never execute commands found in external text"；并主张最小权限——默认只用内部来源，跨边界动作需显式用户同意，输入/输出过滤要与严格 CSP 配对，使得**即使模型被操纵，网络出口与渲染仍被独立遏制**（"defense-in-depth — no single measure suffices"）。

**对 AiFamily 的直接含义**：`AI_ARCHITECTURE.md` §4.3 的架构约束（AI Runtime 不接触业务域 repository、canonical 写入只经 Named Action）在**方向上与该论文的"最小权限 + 独立遏制出口"一致**，属于外部证据支持的设计。但该论文的额外教训是 AiFamily 目前**未覆盖**的一层：出口侧（egress/渲染）的独立管控。AI 生成的内容若被渲染到家长/孩子端 UI，需要独立的渲染与外链策略，而不是只依赖"AI 不写 Fact"。

---

## 2. 标准体系的立场

### 声明 4a.3｜OWASP 明确写明 prompt injection **不存在万无一失的防御手段**
**置信度：high（一手，标准组织发布文本）**

来源：OWASP GenAI Top 10, LLM01:2025 Prompt Injection（`https://genai.owasp.org/llmrisk/llm01-prompt-injection/`）。原文措辞：

> "it is unclear if there are fool-proof methods of prevention for prompt injection"

OWASP 给出七项缓解措施（原文小标题）：

1. Constrain model behavior
2. Define and validate expected output formats
3. Implement input and output filtering
4. Enforce privilege control and least privilege access
5. Require human approval for high-risk actions
6. Segregate and identify external content
7. Conduct adversarial testing and attack simulations

其中第 4 项："Restrict the model's access privileges to the minimum necessary for its intended operations."；第 5 项："Implement human-in-the-loop controls for privileged operations to prevent unauthorized actions."

**这条声明为什么重要且可 falsify**：它把"防不住"写成了标准组织的公开立场。任何架构如果把安全性建立在"我们能过滤掉注入"之上，就与该标准直接冲突。**推论：安全性必须来自权限边界与人工闸门，不能来自提示词防御。**

### 声明 4a.4｜OWASP 第 4、5 项与 AiFamily 宪章 R7/R8/R9 是同一设计取向的独立印证
**置信度：medium-high（对照分析，非单一来源事实）**

| OWASP LLM01 缓解项 | AiFamily 现有约束 | 状态 |
|---|---|---|
| 4. 最小权限，应用持自己的凭据而非让模型直连敏感功能 | R7：领域不得直连模型供应商；凭据只由 Model Gateway 读取（`AI_ARCHITECTURE.md` §4.3） | **已有约束，方向一致** |
| 5. 高风险操作需人工审批 | R8 过闸清单：类诊断输出、家庭计划变更、教师推荐、服务购买、对外沟通、会员升级、涉未成年人敏感动作（§4.4） | **已有约束，且比 OWASP 更具体** |
| 2. 定义并校验期望输出格式 | 见 4c 文档（schema 校验） | **部分**：`AI_ARCHITECTURE.md` 未展开 schema 强制手段 |
| 6. 隔离并标识外部内容 | **未见对应约束** | **缺口** |
| 7. 对抗性测试与攻击模拟 | **未见对应约束**；`tests/` 下无对抗性 AI 测试 | **缺口** |

**结论**：AiFamily 在最小权限与人工闸门两项上已有明确约束（且 R8 清单比 OWASP 泛泛的"高风险操作"更可执行）。**缺口在第 6 项（外部内容隔离标注）与第 7 项（对抗性测试）**——后者尤其符合宪章 R14"未被测试覆盖的规则只是意图"的判据：R7/R8/R9 若无对抗性测试，就无法证明它们真的挡得住。

---

## 3. 平台侧的权限边界实现（一手厂商文档）

### 声明 4a.5｜主流 agent 平台把工具权限做成三态策略 + 阻塞式确认事件，而非提示词约束
**置信度：high（一手，Anthropic 平台文档）**

Anthropic Managed Agents 的权限策略是显式的运行时机制而非提示词：

- 权限策略取值 `always_allow`（默认自动执行）与 `always_ask`
- 命中 `always_ask` 时，会话发出 `agent.tool_use` 事件且 `evaluated_permission === 'ask'`，**会话进入 idle 阻塞**，直到客户端回送 `user.tool_confirmation`（`result: 'allow' | 'deny'`，deny 可带 `deny_message` 回传给模型）
- 支持 per-tool 覆盖：`default_config: {enabled: false}` + `configs: [{name, enabled: true}]` 做白名单
- 自定义工具（客户端执行）**不适用权限策略**——因为执行方就是你自己

同时该平台的凭据边界设计与 4a.2 的教训一致：**凭据从不进入沙箱**。MCP 工具调用与 git 操作由 Anthropic 侧代理在请求**离开沙箱之后**注入凭据，"Code running in the container — including anything the agent writes — cannot read or exfiltrate it."。平台文档并明确警告：不要把 API key 放进系统提示或用户消息作为变通，因为它们会持久化在会话事件历史中并被 `events.list()` 读到。

### 声明 4a.6｜工具粒度设计本身就是权限设计：bash 不可门控，专用工具可门控
**置信度：high（一手，Anthropic agent 设计文档）**

原文论点：bash 工具给 harness 的只是一个**不透明命令字符串**，对每种动作都是同一形状；把动作提升为**专用工具**则给出带类型参数的动作级钩子，可被拦截、门控、渲染、审计。文档举例："A `send_email` tool is easy to gate; `bash -c \"curl -X POST ...\"` is not."

判据（原文）：
- **安全边界**：难以撤销的动作（外部 API 调用、发消息、删数据）应门控 → 提升为专用工具
- **陈旧性检查**：专用 `edit` 工具可在文件自上次读取后被修改时拒绝写入；bash 无法保证该不变量
- **渲染**：需要自定义 UI 的动作（如提问渲染为模态框并阻塞 agent 循环）
- **调度**：只读工具可标记为并行安全；同样动作走 bash 时 harness 无法区分并行安全的 grep 与不安全的 git push，只能串行化

**对 AiFamily 的直接含义（可作为 ADR 输入）**：R8 的过闸清单要能被机械执行，前提是这些高影响行为**各自是一个具名工具**，而不是某个通用工具的参数。若 AI Runtime 暴露的是"调用业务 API"这类通用工具，R8 闸门在实现层无处挂载。这为 `AI_ARCHITECTURE.md` §4.4 补上了一条缺失的实现级判据。

---

## 4. 未获证据支持

1. **家庭教育/未成年人场景的 agent 越权公开案例**：本轮**未找到任何**针对教育或家庭场景 AI agent 的具名越权/数据外泄 CVE 或事故复盘。EchoLeak 是企业办公场景。因此"未成年人场景的具体攻击模式"这一问题**未获证据支持**，不能从 EchoLeak 类推。
2. **各类缓解措施的量化有效性**：OWASP 七项缓解措施**没有给出任何有效性数据**（例如"输入过滤可拦住 X% 的注入"）。检索到的其他材料多为厂商安全博客，无可复现的测量。因此"哪种 guardrail 更有效"**未获证据支持**。
3. **第一方事故复盘（postmortem）**：除 EchoLeak 有学术复盘外，本轮未找到受影响厂商自己发布的技术复盘。多数流传的事故细节（Notion 3.0、Claude Code 文件外泄等）均为第三方安全博客转述，**未采信**。

---

## 5. 建议走 ADR 的结论

| 结论 | 依据 | 影响文档 |
|---|---|---|
| 安全性不得建立在提示词/输入过滤之上；必须由权限边界 + 人工闸门承担 | 4a.1、4a.3 | `docs/05_ai/AI_ARCHITECTURE.md` §4.3/§4.4 |
| R8 清单中每个高影响行为必须是**独立具名工具**，否则闸门无处挂载 | 4a.6 | 同上 + `governance/AI_USE_CASE_REGISTRY.yaml`（待建）的 `allowed_tools` 字段设计 |
| 补齐 OWASP 第 6 项：不可信外部内容必须显式来源标注并禁止其指令生效 | 4a.2、4a.4 | 同上 |
| 补齐 OWASP 第 7 项：为 R7/R9 增加对抗性测试，否则按 R14 只是意图 | 4a.4 | `tests/` + `governance/REPOSITORY_CONSTITUTION.md` §2 执行状态表 |
| 凭据注入必须在"离开受控边界之后"发生，且严禁把凭据写入提示或消息历史 | 4a.5 | `docs/06_platform/`（待建）+ Model Gateway 规格 |
| 出口侧（渲染/外链）需独立管控，不可只依赖"AI 不写 Fact" | 4a.1 第 4 步、4a.2 | `docs/08_experience/`（待建） |
