# Experience Gateway

`ExperienceGateway` 是 34 个 UI 共用的体验应用边界。它接收三类已冻结契约：

- `ExperienceEvent`：发生了什么；
- `RecommendationDecision`：为什么展示这些候选；
- `FeedbackSignal`：家庭接受、完成、跳过、暂停、投诉或请求人工。

Gateway 提供幂等追加和精确 scope 时间线读取。它不会调用模型，也不会写入 Family、
Journey、Service 或 Commerce 事实。AI 仍必须经 `backend/intelligence/model_gateway`，
事实确认仍必须经领域 Named Action、授权、同意、事务、审计和 Outbox。

当前实现是 dev/test 的内存适配器，用来保证三环境共享同一接口和拒绝规则。生产接入时替换
存储/Outbox/Projection 适配器即可，不应改变 UI 或体验契约。

## 特征与实验

`features.py` 保留停留时长、完成率和交易金额，但为每个信号绑定用途和粒度：金额服务
收入/容量分析，原始事件级停留时长不能直接调节推荐。`experiments.py` 提供稳定的家庭级
实验分流和退出标记；实验版本不改变业务事实，生产时可接入 Analytics/Ops 的持久化投影。

`pipeline.py` 提供 Outbox → Analytics Projection 的 dev/test 骨架：投影成功后才确认消息，
失败消息保持 pending 可重试，同一消息重放不会重复计数。生产只替换队列、事务和读模型适配器。

`achievement.py` 将真实行动事件投影为家庭自己的非比较成就，并保留 evidence/provenance；
暂停不会造成连胜惩罚，成就也不会自动改变订单、会员或服务事实。
