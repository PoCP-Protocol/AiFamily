# ADR-0019: Realtime Avatar Provider 与 GPU Media Compute Node 边界

- **Status**: Accepted
- **Date**: 2026-09-04
- **Deciders**: project-owner / chief-architect（依据 FAMILY-REALTIME-001）
- **Supersedes**: null
- **Superseded By**: null

## Context

### 已核验的事实（FAMILY-MEDIA-003 之后）

1. Ditto Gate1 **真实神经推理已在远端 RTX 4090D 成功**。人审结论：identity 保持可接受、
   头部运动自然、**确认是真实 neural avatar**；牙齿/口部时序一致性仍有质量问题，
   `smo_k_d=3` 与 `5` 无实质差异。
2. 裁决：`DITTO_GATE1=CONDITIONAL_PASS` / `REAL_NEURAL_AVATAR=YES` /
   `PRODUCTION_READY=NO` / `WINNER=NOT_DECIDED`。口部问题冻结为 **Q-MOUTH-001**，
   本轮不继续调参。
3. 上述全部属于 **offline** 形态：`static image + 完整 wav → mp4`。
   `backend/intelligence/media_factory/providers/ditto.py:271-321` 的实现是
   `subprocess.run(inference.py ... --output_path raw.mp4)` 一次性批处理，
   `AvatarProviderCapabilities.realtime` 字段在同文件 `:89` 硬编码为 `False`。

### 触发本决定的结构性问题

Famili Principal 的目标不是离线视频生成器，而是**实时交互的长期陪伴 Super Agent**。
最终链路是：浏览器麦克风 → VAD → 流式 ASR → Principal Runtime → LLM/Memory/Tools →
流式 TTS → **Realtime Avatar Runtime** → 浏览器音视频 → 打断/下一轮。

ADR-0018 §3 已经冻结「Offline Gate1 Benchmark 与 Famili Realtime Runtime 永久分离」，
但当时**没有任何 realtime 侧的落点、契约或执行机制**——该条只是一句禁令。
本轮要建 realtime 垂直切片的地基，必须先回答落点、契约形态与 GPU 节点边界，否则
两种最坏路径都会自然发生：

- **路径 A（引擎硬绑）**：直接在应用代码里调 Ditto。ADR-0018 §2 已禁止，但 offline
  侧禁令不自动覆盖 realtime 侧；且 Ditto 只是 `CONDITIONAL_PASS`，`WINNER=NOT_DECIDED`，
  硬绑一个未胜出的引擎就是重复源仓库的 HeyGem 事故形状。
- **路径 B（复用 offline 管线）**：把 `BenchmarkRunner` 塞进对话主链。offline runner
  的语义是「写 run 目录 + 等 mp4 + 人审 schema」，与「20ms 一帧、首帧延迟决定体验」
  不相容；混用会让 `run_avatar_benchmark` 的 `IMPLEMENTED_TESTED` 被读成实时可用。

### 旧失败模式必须显式防住

ADR-0018 §Context 第 3 点记录了源仓库的具体失效：
`API PASS ∧ WebSocket PASS ∧ Unit Tests PASS` 被误读为数字人完成。
realtime 侧比 offline 侧**更容易**复现这个错误——一个按时到达的假帧流从外部看就是成功。
所以 realtime 的 fixture 必须比 offline 的 fixture 更强地自证无效。

### 本轮的硬限制

FAMILY-REALTIME-001 明确：不 vendor Ditto、不下载权重、不启动 AutoDL、不 SSH、
不跑推理。因此 realtime provider 必须在**无 GPU、无引擎源码**的机器上可运行、可测试。
本轮**未能在本机查阅 pinned Ditto 源码**（`c3e47ee`，本机无 clone；工作区
`stream_pipeline_online.py` / `run_chunk` / `chunksize` 全部零命中），
该限制与后果记录在
`docs/13_research/technology/FAMILY_REALTIME_001_DITTO_ONLINE_AUDIT.md`（`RESEARCH_ONLY`）。

## Decision

1. **落点与分离**：Realtime Avatar Runtime 落在
   `backend/intelligence/media_factory/realtime/`（R10：唯一 AI Runtime）。
   **`Offline Media Factory != Realtime Avatar Runtime` 在本 ADR 再次冻结，并首次获得执行机制**：
   两侧不得互相 import 对方的管线，`media_factory/__init__.py` **不得** re-export
   realtime 包。由 `tests/architecture/test_realtime_boundaries.py` 强制。
   共享 `media_factory/contracts.py` 的冻结资产哈希与 upstream pin 是**允许**的——
   复制一份哈希才是 R14 伤疤的形状。

2. **Provider 中立契约**：realtime 引擎一律经 `RealtimeAvatarProvider` /
   `RealtimeAvatarSession` 接入。契约只有九个动词：`capabilities` / `health` /
   `prepare_identity` / `start_session` / `close`（provider 侧）与
   `push_audio_chunk` / `end_turn` / `read_frame` / `cancel` / `close` / `metrics` /
   `events`（session 侧）。**契约中不得出现任何引擎特定配置**——Ditto 的
   `chunksize` / `smo_k_d` / backend 选择属 provider 自身配置，不进
   `RealtimeSessionSpec`。

3. **Identity 走不透明 locator**：`IdentitySpec.image_locator` 与
   `PreparedIdentity.identity_handle` 对调用方不透明。通用应用代码**不得**知道任何
   引擎的文件系统布局；这是「Ditto 可替换」从口号变成结构性事实的关键字段。

4. **音频形状唯一**：`AudioChunk` 强制 PCM16 / mono / 16000 Hz，带
   `sequence` / `presentation_time_ms` / `turn_id` / `is_final`。Provider 可声明
   接受更多格式，**不得**声明接受更少。乱序、重复、越窗三种到达由
   `AudioChunkSequencer` 统一处理（provider 中立），不由各引擎各自定义。

5. **显式会话状态机**：`CREATED → PREPARING → READY → RECEIVING_AUDIO → GENERATING
   → TURN_COMPLETING → READY`，加 `CANCELLED` / `CLOSED` / `ERROR`。
   转移表是数据，**未列出的转移一律非法并显式抛错**，无宽松默认。
   `cancel()` 在 V0 是**会话级**动词：`CANCELLED` 的唯一出路是 `CLOSED`。

6. **Realtime Protocol V0 与 Transport 分离**：八个 provider 中立事件
   （`session.started` / `audio.accepted` / `avatar.first_frame` / `avatar.frame` /
   `turn.completed` / `session.cancelled` / `session.closed` / `provider.error`）。
   每个 envelope 必带 `session_id` / `turn_id` / `trace_id` / `sequence`——
   **禁止把协议退化为 `success=true`**。Transport 绑定（WebSocket 控制通道 + 二进制
   载荷通道；WebRTC 为 `PLANNED`）单独放 `transport.py`，**provider 契约模块不得
   import 它**，由架构测试强制。这一条直接针对上文的旧失败模式：让
   「WebSocket 能连」在结构上无法冒充「avatar 可用」。

7. **Real neural inference 由远端节点 attest，不由适配器假设**：
   `DittoRealtimeAvatarProvider` 只在 `RemoteEngineAttestation` 同时声明
   `reachable ∧ online_mode ∧ real_neural_inference` 时，才把帧标为
   `real_neural_inference=True`，才允许 `realtime_gate_eligible=True`。
   测试替身因此**无法**制造真实推理声明。`online_mode` 与
   `real_neural_inference` 是两个独立字段：真引擎跑离线批处理对实时轮次同样无用。

8. **引擎与权重永久在 worktree 之外**：路径只从
   `DITTO_ENGINE_ROOT` / `DITTO_MODEL_ROOT` / `DITTO_PYTHON` / `DITTO_DEVICE` /
   `DITTO_REALTIME_ENDPOINT` 读取。**不得**把 Ditto 的 GPU 依赖
   （torch / tensorrt / onnxruntime / librosa / cv2 / numpy）写进 AiFamily 的
   `pyproject.toml`，realtime 包内亦不得 import 它们（架构测试强制）。
   AiFamily 侧契约测试必须在无 GPU 机器上通过。

9. **GPU Media Compute Node 边界**：AutoDL 及未来任何 GPU 节点**只是** GPU Media
   Compute Node。
   - **允许**（全部 ephemeral）：avatar 引擎、模型权重、临时会话状态、临时音频块、
     临时帧缓冲、运行时指标、临时缓存。
   - **禁止作为 canonical 状态**：user memory、family profile、course state、
     assessment state、authorization state、business truth、Principal 长期记忆。
     这些的 canonical 位置永远在 AiFamily 内，且每一项在
     `gpu_node_boundary.py::CANONICAL_OWNER` 里指名 owner——「留在 AiFamily」
     不指名 owner 是不可证伪的声明。
   - 节点可接收的载荷只有两类：identity 参考图、当轮音频块。
   - 保留期：`EPHEMERAL_PER_SESSION`。节点**不得**写 Family canonical truth（R9）。

10. **指标不得编造**：`RealtimeMetrics` 的每个字段默认 `NOT_RUN`。
    `NOT_RUN`（从未测量）与 `UNKNOWN`（测了但取不到值）语义不同，不得互换，
    不得用 0 代替。`source` 字段强制：fixture 的墙钟时间是**假生成器的真实耗时**，
    必须与神经推理耗时在数据上可区分。只有 `source=REMOTE_GPU_NODE_ATTESTED ∧
    real_neural_inference` 才可支撑 realtime gate 主张。

11. **Fixture 自证无效**：`FixtureRealtimeAvatarProvider` 恒报
    `REAL_NEURAL_INFERENCE=FALSE` / `REALTIME_GATE_ELIGIBLE=FALSE`，且其帧的
    `frame_format` 就叫 `FIXTURE_SYNTHETIC`——`AvatarFrame.__post_init__` 禁止
    `FIXTURE_SYNTHETIC` 帧声明 `real_neural_inference=True`。
    **fixture 测试通过永不等于 realtime avatar PASS。**

12. **本 ADR 只授权 Realtime Avatar 垂直切片地基**。不授权 ASR/TTS/LLM 选型、
    浏览器 UI、完整 WebRTC、多 GPU 调度、大规模并发，也不授权执行 GPU smoke。

13. **帧发布只有一条路径；轮次收尾的顺序与边界是契约的一部分**
    （FAMILY-REALTIME-001P 补充）。一帧可能在三个时刻出现——推音频之后、消费者
    `read_frame()` 之时、轮次收尾排空之中。三处各自计数、各自判首帧、各自发事件，
    就是「首帧报两次或一次都不报」的成因，因此三条路径一律汇入
    `BaseRealtimeAvatarSession._publish_frames`，帧计数 / 首帧语义 /
    `avatar.first_frame` / `avatar.frame` / queue depth 只有一处定义。
    - **渐进 poll 缝**：`_poll_progressive_frames()` 默认返回空（同步 provider 无
      需实现）。远端 provider 在此向节点索取「上次之后新产出的帧」。没有这条缝，
      推送返回 30 ms 后才完成的推理只能等下一次无关的推送来顺带取走——而在一段
      回复的末尾，那次推送永远不会来。
    - **收尾顺序**：flush 本地乱序缓冲 → 把最后的音频交给引擎 → `_finalize_turn()`
      通知引擎本轮结束 → `_poll_final_frames()` 有界排空 → 发 `turn.completed`。
      **`turn.completed` 不得早于引擎收到收尾信号**；同样地，`_finalize_turn()`
      不得早于 flush，否则最后几个乱序音频块会被推给一个已经关闭的轮次。
    - **排空必须有界**：`while not complete` 在会话层等于产品挂死。上限为
      `DEFAULT_MAX_FINAL_DRAIN_POLLS = 8`（Ditto 侧 `DITTO_FINAL_DRAIN_MAX_POLLS`）。
      **这个数字未经任何测量**——本包从未排空过真实引擎——它是安全上限，不是生产
      最优值，待 FAMILY-REALTIME-002 有真实 transport 后以真实 deadline 取代。
    - **排空未确认不得伪装成功**：节点在上限内未确认本轮已排空时，
      `TurnCompletion.drain_complete=False`，且同时发 `provider.error`
      （`REMOTE_DRAIN_INCOMPLETE`）。三个面向引擎的调用抛错时一律走同一条显式失败
      路径——会话进入 `ERROR`、发 `provider.error`、抛
      `AUDIO_PUSH_FAILED` / `PROGRESSIVE_POLL_FAILED` / `TURN_FINALIZATION_FAILED`
      之一，**不产出 `turn.completed`**。三条里放过任何一条，那一条就会静默失败。
    - **传输层需要区分「暂时没有」与「本轮已排空」**：`poll_frames` 的空结果在轮中
      是正常的，在轮尾却无法决定何时停止追问，故 `DittoRealtimeTransport` 增加
      `drain_turn() -> RemoteFrameBatch{frames, turn_complete}`。`RemoteFrameBatch`
      是 **provider 内部类型**，不得进入 `RealtimeAvatarProvider` 通用契约。
    - **终态会话不得继续占用 provider 容量**：`CANCELLED` / `CLOSED` / `ERROR` 时
      session 通过 `bind_owner()` 注册的回调把自己交还 provider。释放**按对象身份
      比较**而非按 `session_id`：持有旧句柄的调用方不得因关闭一个同名旧会话而把
      现役会话踢出登记表。`health()["open_sessions"]` 因此是活跃会话数，不是历史
      创建数。原缺陷的形状是：会话关闭后仍被计入并发上限，第二轮对话被
      `SESSION_LIMIT` 拒绝。
    - `TurnCompletion` 因此新增 `drain_complete` 字段。该字段 **engine-neutral**，
      任何 provider 都可能排空不尽；它不是 Ditto 特定配置，不违反本 ADR 决定 2。

### 目标架构

```text
AiFamily
  |
  +-- Principal Runtime            (尚未建设)
  |
  +-- Realtime Orchestrator        (尚未建设 — FAMILY-REALTIME-002+)
          |
          +-- RealtimeAvatarProvider          ← 本 ADR 冻结的替换缝
                  |
                  +-- DittoRealtimeAvatarProvider   (远端优先骨架)
                  +-- Future Avatar Providers

Remote GPU Media Compute Node
  |
  +-- Avatar Engine        (引擎在 worktree 外)
  +-- Model Weights        (权重在 worktree 外)
  +-- Session Buffer       (ephemeral)
  +-- Frame Stream         (ephemeral)
  +-- Ephemeral Metrics
```

替换 Ditto 必须**不需要改写 Principal Runtime**：Principal 只认
`RealtimeAvatarProvider`，不认引擎。

## Alternatives Considered

### A. 直接在 realtime 链路里调 Ditto（不做 provider 层）

**支持理由**：Ditto 是目前唯一验证过真实神经推理的引擎，多一层抽象就多一层延迟与
维护成本；realtime 对延迟敏感，抽象在此处的代价比 offline 更实在。

**否决理由**：Ditto 是 `CONDITIONAL_PASS` 且 `WINNER=NOT_DECIDED`，Q-MOUTH-001 未解。
硬绑一个已知有质量缺陷、尚未胜出的引擎，与 ADR-0018 §2 直接冲突，也是源仓库
HeyGem 硬绑事故的同一形状。抽象成本是一次函数调用；重写成本是整条 Principal 链路。

### B. 复用 offline `BenchmarkRunner` + MediaJob 队列做 realtime

**支持理由**：现成、已测（`run_avatar_benchmark=IMPLEMENTED_TESTED`），不必新建包；
「一个 media 落点」听起来比两个更符合 R2。

**否决理由**：语义不相容。offline runner 的成功判据是「run 目录里有通过 ffprobe 的
mp4 + 人审 schema」，realtime 的成功判据是「首帧延迟与帧间隔」；offline 没有 turn、
没有乱序音频、没有打断。ADR-0018 §3 已冻结分离，本轮只是给该冻结补上执行机制。
R2 要求「一个能力一个实现」，而这是**两个能力**，不是一个能力两份实现。

### C. 先做 WebSocket 服务端，把 realtime 定义为「WS 能连上」

**支持理由**：能最快产出可演示的东西——浏览器连上、有帧回来，看起来就是实时数字人。

**否决理由**：这正是 ADR-0018 §Context 第 3 点记录的源仓库失效路径
（`WebSocket PASS` 被读成数字人完成）。所以本轮反向决策：**先冻结 provider 契约，
transport 只声明绑定形状、不实现服务端**，并用架构测试让 provider 无法 import
transport。可演示性推迟，可证伪性提前。

### D. 让 provider 自己判断是否为真实推理（不引入 attestation）

**支持理由**：少一个字段、少一个 Protocol 方法；provider 知道自己连的是 Ditto，
声明 `real_neural_inference=True` 看起来是同义反复。

**否决理由**：适配器只知道自己**打算**连什么，不知道对面**实际**在跑什么。
没有 attestation 时，一个返回假帧的测试替身会被适配器标成真实推理——
`REAL_NEURAL_AVATAR` 是本项目最贵的一个字段（FAMILY-MEDIA-001 审计的全部起因就是
它曾被误报），它必须由远端声明、不由本地假设。

### E. 把 GPU 节点也当作一个可存业务状态的部署单元（允许放会话记忆）

**支持理由**：把短期对话记忆放在 GPU 节点上可省一次网络往返，对首帧延迟有直接好处。

**否决理由**：租用 GPU 节点在 AiFamily 的 consent / audit / 删除机制之外。家庭或
未成年人数据一旦落在那里，平台就无法证明自己能删除它——与 ADR-0006 记录的法定
删除义务直接冲突。延迟可以另想办法（预取、就近部署），合规无法事后补。

## Consequences

### 正面

- Ditto 可替换成为结构性事实：应用代码不知引擎路径、不见引擎参数。
- realtime 的 gate 主张从此需要远端 attestation，无法用 fixture 或替身伪造。
- `Offline != Realtime` 首次有了会咬人的检查，而不只是 ADR 里的一句话。
- GPU 节点边界是可断言的列表而非 runbook 散文，业务真值越界会在测试里失败。

### 负面 / 代价

- 多一层 provider 抽象与一个 attestation 往返，realtime 首帧延迟预算上多一笔开销
  （具体数字 `NOT_RUN`，尚未测量）。
- `LOCAL_SUBPROCESS` 模式被识别但拒绝执行：本地开发者无法在无远端节点时跑真实
  realtime，只能跑 fixture。这是有意的取舍——假的本地 realtime 比没有更危险。
- realtime 与 offline 有两套 provider registry 与两套 provider 概念，新人需要理解
  两者的区别。

### 需要接受的风险

- **Ditto online 契约未在本机核验**（见 Context 末段）。本 ADR 冻结的是 AiFamily
  侧的抽象，不是对 Ditto online API 的假设；`DittoRealtimeTransport` 的实现体
  留在部署侧，其可行性必须在 GPU 节点上确认。若 Ditto 的 online 管线无法在不改
  upstream 的前提下暴露渐进帧，本 ADR 的抽象仍成立，但
  `DittoRealtimeAvatarProvider` 的远端实现需要一个节点侧 bridge 脚本。
- **`REAL_NEURAL_REALTIME_FRAMES=NO`**。本轮从未有任何真实引擎帧经过本包。
  决定 13 的渐进 poll 缝与有界排空是**架构能力**，不是 Ditto 真的会流式产帧的证据；
  `REAL_DITTO_ONLINE_SMOKE=NOT_RUN` 仍然成立，两者不得互相顶替。
- **排空上限 8 次是未经测量的安全值**。它保证会话层不会挂死，不保证真实节点在 8 次
  询问内一定排空完。真实 deadline 需要 FAMILY-REALTIME-002 的真实 transport 才能定。
- **无 turn 级打断（barge-in）**。V0 的 `cancel()` 结束整个会话。真实打断需要
  orchestrator 才有意义，留给 FAMILY-REALTIME-002。
- **无并发**：`DittoRealtimeAvatarProvider.max_concurrent_sessions=1`。
- Q-MOUTH-001 未解，与本 ADR 无关但仍是 realtime 体验的已知质量缺口。

## Enforcement

| 决定 | 执行机制 | 状态 |
|---|---|---|
| Offline != Realtime（双向不 import 对方管线） | `tests/architecture/test_realtime_boundaries.py::test_offline_media_factory_does_not_import_the_realtime_runtime` / `::test_realtime_runtime_does_not_reuse_the_offline_gate1_pipeline` | 已实现 |
| Transport 与 provider 契约分离 | 同文件 `::test_provider_contract_cannot_reach_the_transport` / `::test_no_provider_module_carries_a_wire_protocol_literal` | 已实现 |
| GPU 依赖不入 AiFamily | 同文件 `::test_realtime_package_declares_no_gpu_dependency` | 已实现 |
| smoke harness 不得自动执行 | 同文件 `::test_smoke_harness_cannot_execute_anything`（禁 import subprocess / socket / asyncio / paramiko / http / urllib） | 已实现 |
| 状态机转移确定性 | `tests/intelligence/media_factory/test_realtime_session_state.py`（13 组非法转移逐条断言） | 已实现 |
| 音频形状 / 乱序 / 重复 / 越窗 | 同上 + `test_realtime_providers.py` | 已实现 |
| first_frame 每轮仅一次（含三条帧路径） | `RealtimeEventEmitter.emit` 抛 `DUPLICATE_FIRST_FRAME`；`test_realtime_contracts.py` / `test_realtime_providers.py` / `test_ditto_realtime_provider.py::test_first_frame_is_announced_once_across_all_three_frame_paths` | 已实现 |
| 渐进帧缝：推送后才产出的帧无需新音频即可送达 | `test_ditto_realtime_provider.py::test_a_frame_produced_after_the_push_still_reaches_the_consumer` / `::test_repeated_reads_do_not_replay_a_remote_frame` | 已实现 |
| 远端先收到收尾信号，本地才发 `turn.completed` | 同文件 `::test_the_node_is_finalised_and_drained_before_turn_completed_is_emitted` / `::test_final_buffered_audio_reaches_the_node_before_the_turn_is_closed` | 已实现 |
| 排空有界，未确认排空不得伪装成功 | 同文件 `::test_a_node_that_never_confirms_the_drain_is_reported_not_awaited` / `::test_a_node_that_fails_at_end_turn_produces_no_completion` / `::test_a_node_that_fails_mid_drain_produces_no_completion` | 已实现 |
| 终态会话交还 provider 容量（按身份释放） | 同文件 `::test_closing_a_session_frees_the_slot_for_the_next_one` / `::test_cancelling_a_session_frees_the_slot_for_the_next_one` / `::test_a_stale_session_cannot_evict_its_replacement`；`test_realtime_providers.py::test_a_terminal_session_stops_counting_against_the_provider` | 已实现 |
| fixture 不得声称真实推理 | `AvatarFrame.__post_init__` + `RealtimeProviderCapabilities.__post_init__`（`realtime_gate_eligible` 需 `real_neural_inference`） | 已实现 |
| 指标不得编造 | `RealtimeMetrics.__post_init__` 拒非法值；默认全 `NOT_RUN` | 已实现 |
| GPU 节点不得存业务真值 | `assert_not_canonical_on_gpu_node`；`test_ditto_realtime_provider.py` 对 7 项逐条参数化断言 | 已实现（**函数级**） |
| 部署形态真的不在 GPU 节点存业务状态 | **当前仅为意图**：本仓库无部署清单、无节点侧代码，无法机械校验一台真实节点上放了什么。补齐路径：节点侧 bridge 落地时随附部署清单，并把清单纳入架构测试扫描 | 未实现 |
| Ditto online API 假设 | **当前仅为意图**：本机无 pinned 源码，无法核验。补齐路径见研究文档的 "Node-side verification checklist" | 未实现 |

## References

- `governance/ADR/ADR-0018-media-avatar-provider-and-gate1-benchmark.md`（§2 provider 化、§3 offline≠realtime、§8 R9）
- `governance/ADR/ADR-0006-minor-data-compliance-constraints.md`（删除义务、不得转委托）
- `governance/ADR/ADR-0017-capability-environment-promotion-gate.md`
- `governance/REPOSITORY_CONSTITUTION.md` R2 / R4 / R7 / R9 / R10 / R14
- `docs/13_research/technology/FAMILY_REALTIME_001_DITTO_ONLINE_AUDIT.md`（`RESEARCH_ONLY`，含本机无法核验 Ditto online 的记录）
- `docs/11_delivery/media_factory/DITTO_REALTIME_ONLINE_SMOKE_RUNBOOK.md`
- `docs/12_governance/COMPLIANCE_HARD_CONSTRAINTS.md`
