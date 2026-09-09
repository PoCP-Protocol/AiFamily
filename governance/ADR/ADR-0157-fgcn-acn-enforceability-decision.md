---
id: ADR-0157
title: FGCN 的强制力设计——采纳贝壳 ACN 可迁移性研究
status: proposed
date: 2026-09-07
decision_owner: project-owner
research_basis: docs/13_research/market/RESEARCH-ACN-TRANSFERABILITY-TO-FGCN.md
---

# ADR-0157：FGCN 的强制力设计——采纳贝壳 ACN 可迁移性研究

## 背景

贝壳ACN研究已经证明FGCN现在的分账只是记账约定，缺四样东西才能真正有强制力：
规则自动结算、资金通道、争议裁决、绕单可观测性。ADR-0036/0037记录过这个缺口，
一直没人设计。现在设计。

## 要建的四样东西

### 1. AllocationPolicyVersion——分账规则版本化，参数不写死在代码里

角色权重表（主责教师/协作教师/复核人/AI辅助标注人各拿多少）存数据库，版本化、
可回放，改动走Named Action。`ServiceContribution → AllocationStatement`的计算
是幂等纯函数：同一组Contribution+同一个PolicyVersion，任何时候重算结果一致。

### 2. SettlementLedgerEntry——记账账本，先不接真实支付

一张追加账本，记"平台该付给谁、多少、依据哪笔AllocationStatement"。
`status`: `PENDING_PAYOUT` / `PAID_OUT`。`PAID_OUT`的实际转账逻辑现在留空——
真实支付网关接入时再补这一段，不用重新设计上层。

### 3. ContributionDispute——争议裁决，从人工仲裁起步

参与方可对某笔AllocationStatement提异议，异议冻结对应SettlementLedgerEntry
（不能先把钱付出去）。裁决人不能是本案任何参与角色。裁决结果写AuditEvent。
裁决人现在就是人工指定的运营角色，不用建自主报名/考核那套东西——网络规模
起来了再说。

### 4. 绕单声明——不做技术侦测，直接写清楚边界

`service_fgcn_collaboration`能力条目补一句：分账机制只覆盖通过平台
`ServiceCase`记录的协作；私下协作不产生Contribution，不进分账，不受裁决保护。

## 地基延续既有设计

`ServiceTask.VERIFIED`（ADR-0036/0037已有）就是分账的判定依据，不新增"给家庭
状态打分验真"这条路——那条本来就走不通。

## 后续实现任务

1. `AllocationPolicyVersion`领域对象+迁移+分配计算
2. `SettlementLedgerEntry`领域对象+迁移
3. `ContributionDispute`领域对象+迁移+冻结联动
4. `DOMAIN_REGISTRY.yaml`补绕单边界声明
5. `COMMERCIAL_VALUE_STRATEGY.md`第2节措辞更新，引用本ADR
