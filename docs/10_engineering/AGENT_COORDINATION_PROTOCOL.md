---
id: AGENT-COORDINATION-PROTOCOL-001
title: ADR-0158 Multi-Agent Coordination Protocol
type: engineering-governance
status: current
canonical: true
owner: chief-architect
---

# ADR-0158 多 Agent 协同协议

本协议把 ADR-0158 的讨论区变成可审计的交付流程。它不替代 ADR，也不把
线程、分支、worktree 或研究文档自动变成实现能力。

## 一、谁被视为“正在工作”

只有同时满足以下条件的 Agent 才可标记 `IN_PROGRESS`：

1. 有可识别的 task/thread id；
2. 有明确 owner；
3. 有唯一 base ref；
4. 有明确 `allowed_paths`；
5. 有当前主张、反证、阻塞和下一道门；
6. 最近一次心跳不超过协同窗口。

仅有分支名、worktree、历史 commit、测试输出或线程标题，不能证明 Agent 正在工作。

## 二、每轮讨论固定格式

```text
Agent:
Task:
Owner:
Base Ref:
Allowed Paths:
Current Truth:
Claim:
Challenge:
Counterexample:
Evidence:
Conflict:
Decision Needed:
Next Gate:
Status:
```

`Claim` 必须和 `Current Truth` 分开；`Evidence` 必须给出命令、ref、路径和结果。
没有反证、失败路径或下一道门的报告不能进入 `READY_FOR_REVIEW`。

## 三、集成门

总控只接收 `READY_FOR_REVIEW`。进入该状态前必须满足：

- exact ref 可复现；
- owner 和 pathspec 已登记；
- 没有与其他 Agent 重叠的写入范围，或已有明确裁决；
- 通过与任务相称的测试，且没有把 fixture/synthetic/单测冒充生产；
- 给出 Current Truth、反证、失败/回滚路径；
- 涉及 AI、家庭或儿童数据时，给出 Human Gate、scope、consent、audit、deletion 和跨家庭隔离证据。

缺少任一项时，状态为 `BLOCKED` 或 `UNOWNED`，不是“待合并”。

## 四、自动检查器的职责边界

`tools/governance/check_agent_coordination.py` 只读扫描：

- 当前 worktree、branch、HEAD 和 dirty 状态；
- 登记的 task、owner、base ref、allowed paths；
- 未登记 worktree、重复 branch、pathspec 重叠；
- 缺少证据或过期心跳。

检查器不得自动认领、合并、删除、重置、推送或改写其他 Agent 的工作。

## 五、协同结论

当前可确认的 Codex 任务应以登记文件中的 `observed_threads` 为准；仓库中更多
分支/worktree 只能视为候选或历史产物，直到有 owner 心跳和可复现交付证据。
