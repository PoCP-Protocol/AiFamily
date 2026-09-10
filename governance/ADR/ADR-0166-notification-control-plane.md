---
id: ADR-0166
title: Notification Control Plane and Governed Delivery Boundary
status: Proposed
date: 2026-09-10
owner: chief-architect
---

# ADR-0166：通知总控与受治理投递边界

## Context

AiFamily 的通知来源会跨越成长行动、服务履约、合规事件、人工闸门和
Experience。现有 Experience achievement notification 只是家庭范围的读模型，
不能成为跨域通知总控，也不能直接代表真实外部投递。另建一套通知事实表或
让领域代码直接调用 Push/SMS/站内消息供应商，会造成第二套 Outbox、绕过
Consent 和审计，并把外部副作用混入业务事务。

通知必须服务于家庭成长与安全，不得用于向未成年人做自动化商业营销，不得
通过家庭排名、焦虑式频率或未经授权的画像推送制造压力。

## Decision

建立平台级 Notification Control Plane，canonical path 为
`backend/platform/notification`。该模块只拥有通知投递意图、策略裁决和投递
状态，不拥有家庭事实、成长事实、订单事实或 AI 事实。

1. 业务域只在 caller-owned transaction 中写入 canonical `outbox_events`；
   不得直接写通知表或调用外部通知供应商。
2. 总控消费已提交的领域事件，按 `tenant_id`、`family_id`、subject、purpose、
   consent snapshot、locale、timezone 和 correlation 生成不可变的
   `NotificationIntent`。同一 intent 必须由 tenant-scoped idempotency identity
   去重；payload 冲突必须 fail closed。
3. Consent、撤回、删除、家庭边界和免打扰策略在投递前重新读取。缺少实时
   authority、purpose 不匹配、撤回、超出留存或主体范围不明时，意图进入
   `SUPPRESSED`/`REJECTED`，不得降级为外发。
4. 总控只调用 provider-neutral `NotificationChannelPort`。Push、短信、邮件、
   站内和测试 fake 都是 adapter；adapter 不拥有业务事务，不得自行改变家庭
   事实。测试 adapter 必须显式标记 `external_effect=false`。
5. 每个投递尝试保存最小 metadata-only receipt，支持 bounded retry、lease
   takeover、dead-letter、人工重放和重启恢复。错误正文、儿童内容和模型输出
   不进入运维查询或告警 payload。
6. 高影响、面向未成年人、涉及安全事件或需要人工确认的通知必须经过既有
   Human Gate/Named Action 语义；通知总控不替代人工闸门，也不把 AI draft
   自动升级为事实或商业动作。
7. 通知读模型（包括现有 achievement inbox）可以由总控投影，但仍是 read
   model；事实来源仍是领域事务和 canonical outbox。不能创建第二个事实账或
   第二个审计/幂等语义。

## Required acceptance evidence

实现不得以单元测试、内存 adapter 或页面存在宣称生产完成。至少需要：

- fresh PostgreSQL migration/upgrade 与真实 HTTP boundary；
- tenant/family isolation、Consent grant/revoke、quiet-hours suppression、
  idempotent replay 和 payload-conflict negative cases；
- caller transaction rollback、provider failure retry、DLQ/replay、lease
  takeover 与 process/container restart readback；
- audit/outbox linkage、metadata-only operational query 和外部副作用证据；
- test/dev/staging/production 使用同一路由、状态机和错误契约，仅替换显式
  adapter 与数据分类。

## Consequences

通知总控成为 Platform 支撑能力，而不是任何单一业务域的私有实现。首个实现
切片应优先完成 provider-neutral contract、SQL durable intent/attempt seam
和 canonical outbox consumer；在真实 identity/consent、部署 scheduler 和
授权外发 adapter 接入前，生产状态必须保持 `EXPERIMENT` 或 `NO-GO`。
