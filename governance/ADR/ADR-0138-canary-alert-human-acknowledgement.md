# ADR-0138：Canary 告警确认不构成回滚授权

## 状态

Accepted — 2026-08-31

## 背景

ADR-0137 已实现可审计 SLO 判定和预签名真人回滚，但 scheduler 还需要把“回滚已执行”与
“breach 已判定但回滚被阻断”交给运营处理。若告警只发往瞬时 paging 系统，进程重启后
无法确认责任闭环；若把告警确认当成回滚授权，又会混淆知悉与批准两个控制语义。

## 决策

1. 新增 metadata-only `CanaryAlert`，仅有 `ROLLBACK_EXECUTED` 与 `ROLLBACK_BLOCKED`
   两类，绑定 assessment、candidate、environment、rollback receipt 或稳定错误码。
2. 同一 assessment 只能绑定一个告警结果；append 幂等，结果漂移冲突拒绝。
3. 告警以 `OPEN → ACKNOWLEDGED` 单向推进。只有非 `ai:` 真人 actor 可确认；同一 actor
   重放幂等，不同 actor 不能覆盖既有确认责任人，确认时间不得早于 opened time。
4. `CanaryAlertingSupervisor` 在回滚成功后写 executed alert；当 breach 已落 assessment
   但预授权或部署执行失败时，使用携带 assessment/稳定错误码的
   `CanaryRollbackBlockedError` 写 blocked alert 后继续抛错，保持 fail-closed。
5. 告警确认只表示运营人员已知悉，不创建、替换或延长 ReleaseControl，不触发业务事实写入。
6. SQL alert ledger 由 Alembic 0042 建立；调用方拥有事务，外部 paging 作为后续可替换投递层。

## 结果与边界

- 运营可跨进程查询 OPEN 告警并形成明确确认责任链。
- 回滚授权、自动执行、告警知悉三个动作保持分离。
- 当前 bounded scheduler job/lease 与外部 paging adapter 尚未完成，不能宣称持续监控已上线。

## 验证

- `tests/intelligence/experience/test_canary_alerts.py`
- `tests/intelligence/experience/test_canary_supervision.py`
