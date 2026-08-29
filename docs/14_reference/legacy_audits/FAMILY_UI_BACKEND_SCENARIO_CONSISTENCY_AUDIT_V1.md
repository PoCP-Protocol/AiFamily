# FAMILY UI ↔ BACKEND SCENARIO CONSISTENCY AUDIT V1

```text
DOC_KIND    = ARCHITECTURE_AUDIT_NOTE (SUPPLEMENTARY, NOT A NEW SSOT MATRIX)
DATE        = 2026-08-28
STATUS      = VERIFIED_FINDINGS_ONLY (unverifiable/incorrect draft claims removed or corrected below)
```

## 0. 关系声明（先于任何结论）

本文档**不是**第三份逐页一致性矩阵，也不取代：

- `../governance/FAMILY_CONSUMER_UI_FRONTEND_BACKEND_CONSISTENCY_MATRIX_001.md`（下称"矩阵001"）—— 已经是逐页 UI/Route/前端能力/后端契约/Named Action/测试现状/状态/下一步的权威矩阵，覆盖全部34页，且已有 Phase 2、服务预约两轮对象链实现记录的增补。
- `../governance/UI01_FUNCTION_CLOSURE_MATRIX_V1.md`（下称"UI01矩阵"）—— 已经是"UI01入口 → 目标UI → 核心对象状态 → 当前实现 → 下一验收门"的闭环矩阵，并已引用三份PPT的具体页码作为闭环依据。

一个只读调研 agent 在本文档写出之前，对同一课题做了一轮独立调研，产出了若干"疑似发现"。**这些发现在写入本文档前逐条用源代码核实**，核实结果分三类：

1. **与既有矩阵重复、无需记录**（如"UI-13/14/17/19 缺乏正式DTO"——矩阵001已逐条列出，UI-19 甚至已经从 GAP 升级为 `BACKEND_READY`，说明矩阵001比调研发现更新）。
2. **核实后发现不准确、必须纠正**（如"~20页存在 `.catch(() => undefined)` 静默失败"——实际代码模式不同，见第3节）。
3. **核实后确认真实存在、且矩阵001/UI01矩阵未记录到这一颗粒度的增量事实**（如 UI-05 的 phase-review 按钮已接线但 pause 按钮完全没有前端入口/客户端方法；UI-21 无取消入口；research/baselines 与 research/ppt-analysis 目录本身的完整性状态）。

本文档只保留第3类，并对第1、2类逐条标注"已被矩阵覆盖，不重复"或"核实后修正"。

## 1. PPT 业务闭环 → UI 映射（矩阵001/UI01矩阵未覆盖的角度）

`apps/mobile/research/ppt-analysis/{family-model-platform,new-business-model,strategy-whitepaper}/content/deck.md` 三份PPT收敛的核心叙事路径是：

测评/诊断入口 → 行为改变（21天/90天）→ 数据沉淀 → AI陪伴续费 → 会员/生态放大 → 分享裂变。

UI01矩阵第3节已经引用了三份PPT的具体页码（商业模式PPT第2/4/7/17/11/15/19页；战略白皮书第6/9/12/13-19/27-29页；平台合作方案第2/4/5/6页）作为闭环设计依据，这部分**不是本文档的新发现**，直接沿用 UI01矩阵的引注，不重复展开。

本文档唯一的增量是：把这条业务叙事拆成显式命名的六类闭环（ASSESSMENT / PLAN / GROWTH / SERVICE / COMMERCE / COMMUNITY），并标注每类闭环当前在矩阵001里落到哪些UI状态段——这一命名和分类颗粒度是 UI01矩阵没有显式做的（UI01矩阵只笼统写"六条业务闭环"作为基线声明，没有逐条命名并回指矩阵001状态）：

| 闭环 | 对应UI | 矩阵001当前状态 |
|---|---|---|
| ASSESSMENT | UI-02→UI-03 | `COMMERCIAL_SLICE_IMPLEMENTED_TESTED_DEV`（两页均已实测） |
| PLAN | UI-04→UI-05→UI-09 | UI-04/05 = `UI_READY_BACKEND_GAP`；UI-09 = `COMMERCIAL_SLICE_IMPLEMENTED_TESTED_DEV` |
| GROWTH | UI-08/UI-11/UI-12/UI-29 | 全部 `GATE_BOUNDARY`（成长效果/榜单/海报/成果均被产品边界限制，不可伪造事实） |
| SERVICE | UI-19→UI-20→UI-21→UI-24 | UI-19/20 = `BACKEND_READY`；UI-21/24 = `E2E_READY` |
| COMMERCE | UI-13/14/16/17/18 | UI-15/16 = `E2E_READY`；UI-13/14 = `UI_READY_BACKEND_GAP`；UI-17 = `GATE_BOUNDARY` |
| COMMUNITY | UI-25→UI-26→UI-27/28 | UI-26 = `E2E_READY`；UI-25/27/28 = `GATE_BOUNDARY`/`UI_READY_BACKEND_GAP` |

结论：六类闭环里，ASSESSMENT 已端到端打通，SERVICE 的预约子链（UI-21/24）已端到端打通，其余四类闭环（PLAN 的按钮接线、GROWTH 的效果类页面、COMMERCE 的目录/积分、COMMUNITY 的社区流）仍处在 GAP 或 GATE_BOUNDARY，与矩阵001的整体判断一致，不构成新的架构性发现，只是给了一个"按业务叙事而不是按UI编号"重新分组的视角。

## 2. research/baselines 与 research/ppt-analysis 目录完整性（矩阵001/UI01矩阵未记录的事实）

`apps/mobile/research/baselines/` 下只有 6 个子目录（`ui02`、`ui03`、`ui19-ui24`、`ui25-ui28`、`ui29-ui34`、`ui35-original`），且这些子目录里**只有一份**真正的文字设计文档：`ui02/assessment-step2-checklist.md`。其余子目录内容以 PNG 截图和文件名为线索，没有配套文字说明。

这是一个关于"设计基线本身完整性"的事实，矩阵001和UI01矩阵都不覆盖这个角度（它们讨论的是"UI实现↔后端契约"是否一致，不讨论"UI设计基线资料本身有没有配套文字说明"）。记录在此，供后续需要复原设计意图时知道要去找截图而不是文档。

## 3. 代码级核实结果（逐条纠正调研 agent 的疑似发现）

### 3a. UI-04/UI-05 与 `journey-plan.service.ts`（部分成立，需拆分）

后端 `apps/api/src/modules/family/journey-plan.service.ts` 确认存在 `pausePlan()`（178行）和 `reviewCurrentPhase()`（201行）两个真实方法，均走事务、状态转换与审计。

核实前端接线情况，与调研 agent 的笼统说法不同，**必须拆开看**：

- **phase-review 已经接线**：`apps/mobile/app/ui/UI-05.tsx` 第63-68行的 `reviewPhase()` 函数已经调用 `familyApi.reviewJourneyPhase(...)`，UI上有"继续下一阶段"/"先调整节奏"两个真实按钮（`reviewDue` 面板）。矩阵001把UI-05整体标为 `UI_READY_BACKEND_GAP` 掩盖了这一部分已经打通的事实。
- **pause 没有接线，且客户端方法本身缺失**：`apps/mobile/lib/family/family-api-client.ts` 里没有任何 `pausePlan`/`pauseJourney` 方法，`UI-04.tsx`/`UI-05.tsx` 都没有暂停按钮或对应调用。这不是"UI没接后端已有的能力"这么简单，而是**客户端SDK层从未生成/编写对应方法**，比"前端漏了个按钮"更靠前一步。

调研 agent 的原始说法("后端已支持pause/phase-review但前端UI没有接这些按钮")对 phase-review 是错的（已接线），对 pause 是对的（完全没有前端入口）。已在此纠正。

### 3b. UI-13/14/17/19/29 疑似 fixture/mock 数据（大部分已被矩阵001覆盖，逐条核实）

- **UI-19（名师专区）**：调研 agent 怀疑是mock数据。核实代码：`UI-19.tsx` 通过 `serviceOfferingsForDisplay(projection?.offerings)` 读取真实投影字段，矩阵001"服务预约对象链实现记录"一节也已经把 UI-19 状态从早期GAP更新为 `BACKEND_READY`（真实 `GET /services/offerings` API）。**该发现不准确，已被矩阵001的后续记录纠正，不是遗漏**。
- **UI-13（商城首页）**：本页主要是导航分类瓦片，本身没有价格/积分等需要后端支撑的具体数值字段；矩阵001已将其标为 `UI_READY_BACKEND_GAP`（缺catalog DTO）。**无新增量**。
- **UI-17（积分商城）**：核实代码，`DAILY_TASKS`/`REWARDS` 数组里的积分数值（`+50`/`99 积分`/`200 积分`等）确认是硬编码常量，且 `pointsBalance = membership?.dev_points?.balance ?? 1280` 有硬编码兜底值 1280。矩阵001已经把UI-17标为 `GATE_BOUNDARY`（"尚无积分ledger/兑换DTO"、"不得写真实权益/兑换"），**方向上矩阵001已经覆盖，但矩阵001没有点出这个1280兜底值和具体积分数字是硬编码这一实现细节**——算轻量增量，不构成新架构结论。
- **UI-29（成长成果）**：核实代码，`BADGES` 是页面内硬编码数组，与矩阵001"仅家庭自有记录"/`GATE_BOUNDARY` 的判断一致。**无新增量**。

### 3c. UI-21 预约取消入口缺失（成立，矩阵001已列为待办但未点明"完全没有"）

核实 `UI-21.tsx` 全文和 `family-api-client.ts`：页面没有任何取消相关文案或按钮，客户端也没有 `cancelBooking` 方法。矩阵001"下一步"一栏已写"增加取消与服务记录投影"，说明矩阵001已经知道这是待办项，但没有明确写出当前状态是"入口完全不存在"（而不是"入口存在但半成品"）。这是一个精确度上的小增量，不是新发现。

### 3d. `.catch(() => undefined)` 静默失败模式（不成立，已纠正）

调研 agent 声称约20个页面存在 `.catch(() => undefined)` 掩盖"无数据"与"请求失败"的区别。逐字搜索 `apps/mobile/app/ui` 下 `catch(() => undefined)` 精确模式：**0命中**。

放宽为搜索所有 `.catch(` 调用，命中 26 处，但实际模式是 `.catch((error) => { console.error("UIxx remote projection failed", error); })` 或设置一个 `fallback`/`syncMessage` 状态字符串——即请求失败**会**被 `console.error` 记录，不是完全静默。是否等价于调研 agent 所说的问题，要看颗粒度：

- 从**日志**角度看，请求失败和无数据不是不可区分的（有 `console.error`），调研 agent 的说法不准确。
- 从**用户可见UI状态**角度看，多数页面确实是把"失败"和"无数据"折叠成同一个兜底文案/空态展示，用户看不出区别——这一点在方向上可能有道理，但不能用调研 agent 给出的具体代码模式（`.catch(() => undefined)`）来支撑，因为那个模式在代码里不存在。

**结论：该条发现的具体代码证据不成立，已删除对应的"20个页面"精确断言；如需继续跟踪"失败态与空态在UI上不可区分"这一更谨慎的表述，需要另开一轮逐页UI状态审查，本轮不下结论。**

### 3e. Python迁移状态确认（非新发现，按任务要求明确写出以避免混淆）

UI-02/UI-03 当前生产路径仍是 NestJS；`PYTHON_READY` 状态目前只在 test/staging 环境生效，尚未达到 `NEST_REMOVED`。这与 Batch 1 当前实际状态一致，**不是本次调研的新发现**，只是在此明确写出，避免把"迁移代码已完成（Batch 1 已完成）"和"生产流量已切到Python（尚未发生）"这两件事混为一谈。

## 4. 总体结论

矩阵001和UI01矩阵已经覆盖了"逐页UI状态"和"闭环入口设计"两个核心角度，且矩阵001本身就在持续增补（Phase 2对象链、服务预约对象链两轮记录）。本文档唯一站得住的、且未被前两份文档覆盖的增量是：

1. 六类业务闭环的显式命名与矩阵001状态回指（第1节）。
2. `research/baselines`/`research/ppt-analysis` 设计基线资料本身的完整性事实（第2节）。
3. UI-05 phase-review 已接线但 pause 完全无前端入口（且客户端SDK层缺方法）的精确拆分（3a）。
4. UI-21 取消入口"完全不存在"而非"部分实现"的精确度纠正（3c）。

其余疑似发现（UI-13/14/17/19/29 mock数据、20页静默失败模式）经核实后大部分已被矩阵001覆盖或直接不成立，已在第3节逐条注明，不作为独立结论保留。
