# ADR-0126：Outbox delivery attempt 的有界运维查询

- 状态：Accepted
- 日期：2026-08-30
- 范围：`backend/intelligence/experience/persistence.py`、
  `backend/apps/family_api/production_experience_outbox_wiring.py`

## 决策

为 scheduler、告警和 dashboard 提供 `delivery_attempts(limit, status)`、
`delivery_attempts_page(limit, status, after)` 和 `delivery_attempt_summary()` 只读端口。
查询只返回 `message_id/attempts/status/error/timestamps/lease metadata` 等运行
元数据，强制非负整数上限，并按最近更新时间和 message ID 稳定排序；cursor 使用
`updated_at + message_id` 组合保证同一时间戳下不漏读/重复读；不读取或返回 Experience
outbox 的 family scope、原始 payload、模型输出或家庭通知正文。状态筛选只接受已定义
的 `ExperienceDeliveryAttemptStatus`，未知状态 fail-closed。

该查询使用调用方新建的只读 SQL session，不参与投递事务，也不改变 lease、retry 或
dead-letter 状态。staging/production 共用同一实现，dashboard 可按 bounded page
轮询，部署平台负责进一步的访问控制、分页游标和指标聚合。

## 取舍

- 优点：运维可以观察积压、重试和死信而不接触家庭内容；有界查询避免 dashboard
  扫描无限数据。
- 限制：cursor 仍由调用方保存，跨服务传输需由平台封装签名/过期策略；高流量部署需在
  平台侧加入缓存与指标采集。
- 安全边界：只读、不调用模型、不发送通知、不执行领域命令，也不绕过 Human Gate。
