# ADR-0142：模型外呼前预算预留与独立运行账本事务

- 状态：Accepted
- 日期：2026-09-01
- 范围：Model Gateway、Family Experience 生产组合根

## 背景

多模态请求的 token 提示来自客户端，不能作为成本控制依据；供应商超时或返回 5xx
时仍可能已经产生费用。原有 SQL Attempt、SafetyDecision 和 Telemetry sink 只 flush
到草稿事务，模型调用失败会使调用前审计记录一并回滚，也会与独立预算事务形成锁与
可见性冲突。

## 决策

1. Model Gateway 根据规范化请求 JSON 的 UTF-8 字节数、服务端 completion 上限和
   实际媒体条目数保守估算成本；路由复用同一服务端估算，不信任客户端 token 提示。
   客户端 cost 上限只允许收紧选择，不能提高服务端预算上限。
2. 每次供应商尝试（包括 fallback）在外呼前，从 tenant/environment/day 预算账户中
   原子预留完整单次上限；成功按供应商 usage 核销，usage 缺失、超时、网络错误或
   5xx 按完整预留额记为 `CONSUMED_UNCERTAIN`。
3. 预算、Attempt start/finish、SafetyDecision 和 Telemetry start/finish 使用各自的
   session-per-call 短事务。草稿注册仍使用请求级业务事务；运行证据不得因草稿失败
   回滚。
4. 预算账户未配置、费率卡失效、策略版本不一致、额度不足或账本不可用时均 fail
   closed，错误归类为 `BUDGET_REJECTED`，不得触发供应商 fallback。
5. staging/production 只接受 durable budget store；synthetic runtime 通过相同
   reserve/reconcile 状态机，仅替换存储和供应商适配器。

## 后果

- 并发请求不能超卖租户预算；fallback 的每次真实外呼分别计费。
- 外呼前 STARTED、输入 Safety 与 IN_PROGRESS span 已提交，进程或供应商失败后仍可审计。
- 保守估算会牺牲少量额度利用率，换取未成年人数据场景下更确定的成本边界。
- Release Bundle 尚需在后续变更中绑定 route、rate-card 和 budget-policy 版本；在该
  绑定完成前，此能力保持 EXPERIMENT，不宣称生产就绪。

## 验证

- `tests/intelligence/model_gateway/test_budget.py`
- `tests/intelligence/model_gateway/test_budget_gateway.py`
- `tests/intelligence/model_gateway/test_attempt_persistence.py`
- `tests/intelligence/safety/test_persistence.py`
- `tests/intelligence/observability/test_persistence.py`
- `tests/apps/family_api/test_production_experience_wiring.py`
