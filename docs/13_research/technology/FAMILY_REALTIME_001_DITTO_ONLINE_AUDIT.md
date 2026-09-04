---
id: RES-TECH-FAMILY-REALTIME-001
title: FAMILY-REALTIME-001 Ditto Online Pipeline Audit — Attempted, Not Completed
type: research
status: draft
version: 1.0
owner: media-factory
created: 2026-09-04
updated: 2026-09-04
canonical: false
supersedes: null
superseded_by: null
---

```text
STATUS: RESEARCH_ONLY
NOT_CANONICAL: TRUE
DOC_KIND = EVIDENCE / LIMITATION RECORD
本文件是证据与限制记录，不是决定、不是实现规格、不是当前系统真相。
晋升须走 ADR（docs/12_governance/DOCUMENT_GOVERNANCE.md §8.2）。
DITTO_ONLINE_SOURCE_INSPECTED = NO
UNVERIFIED 段落中的每一条都必须在 GPU 节点上核验后才能采信。
```

# FAMILY_REALTIME_001_DITTO_ONLINE_AUDIT

## 1. EXECUTIVE_CONCLUSION

**本任务要求审计 pinned Ditto 的 online 管线，该审计未能完成。**
原因是事实性的、可复核的：**pinned 源码不在本机**。

因此 FAMILY-REALTIME-001 的实现范围调整为：**只冻结 AiFamily 侧的 provider 中立抽象，
不对 Ditto 的 online API 做任何被当作真相的假设。** 这个调整是有意的，不是妥协——
一个建立在未核验 API 假设之上的适配器，会把假设伪装成契约。

```text
DITTO_ONLINE_SOURCE_ON_DISK        = NO
DITTO_ONLINE_API_VERIFIED          = NO
ONLINE_MODE_ENABLEMENT_VERIFIED    = NO
RUN_CHUNK_SEMANTICS_VERIFIED       = NO
CHUNKSIZE_SEMANTICS_VERIFIED       = NO
PROGRESSIVE_FRAME_HOOK_VERIFIED    = NO
UPSTREAM_MODIFICATION_REQUIRED     = UNKNOWN
REAL_DITTO_ONLINE_SMOKE            = NOT_RUN
```

## 2. 已核验的事实（VERIFIED — 本机实测）

### 2.1 pinned 源码不在本机

搜索结果，2026-09-04：

```text
D:\ 顶层 + 二级目录中名称匹配 *ditto* 的目录：0 命中
D:\_reference 二级目录：AUTOavantar / .codegraph / backend / business / config /
              core / engines / frontend / models / tools / voicel  —— 无 ditto
D:\Famili-V2-Reference：空
工作区内 grep "stream_pipeline|online_mode|run_chunk|chunksize|StreamSDK"：0 文件命中
```

Gate1 的真实推理是在**远端 RTX 4090D**（AutoDL）上完成的，引擎与权重按 ADR-0018 §
engine isolation 留在该节点上，从未进入本机或本仓库。这是**符合设计的**结果，不是丢失。

### 2.2 AiFamily 已核验的 Ditto 事实（来自本仓库既有实现，非本轮推断）

| 事实 | 锚点 |
|---|---|
| upstream URL / commit pin | `backend/intelligence/media_factory/contracts.py:29-30` |
| 代码许可 Apache-2.0；权重 `LICENSE_REVIEW_REQUIRED` | `contracts.py:31`、`ditto_remote_package.py:65-67` |
| 首次 smoke backend 为 pytorch（可复现性优先于 FPS） | `contracts.py:32` |
| offline 调用形态：`inference.py --data_root --cfg_pkl --audio_path --source_path --output_path` | `providers/ditto.py:286-299` |
| 权重布局含 `ditto_pytorch/` 与 `ditto_cfg/v0.4_hubert_cfg_pytorch.pkl` | `providers/ditto.py:259-269` |
| 官方测试环境 A100 / Centos 7.2 / py3.10 / torch 2.5.1+cu121 / TensorRT 8.6.1 | `ditto_remote_package.py:37-43` |
| offline provider 自报 `realtime=False` | `providers/ditto.py:87-92` |

以上全部是 **offline 批处理**形态的事实。**没有一条**能说明 online 管线的行为。

### 2.3 Gate1 人审结论（已核验，来自 FAMILY-MEDIA-003）

```text
DITTO_GATE1        = CONDITIONAL_PASS
REAL_NEURAL_AVATAR = YES
PRODUCTION_READY   = NO
WINNER             = NOT_DECIDED
Q-MOUTH-001        = FROZEN（牙齿/口部时序一致性；smo_k_d=3 与 5 无实质差异）
```

## 3. 本轮要求回答但**未能核验**的问题（UNVERIFIED）

任务 §3 列出九个必须"determine and document"的问题。诚实的答案是：**九个全部
UNVERIFIED**。下表把每个问题连同它对 AiFamily 侧设计的影响一起记下，供节点侧核验时逐条销项。

| # | 问题 | 状态 | 对 AiFamily 侧抽象的影响 |
|---|---|---|---|
| 1 | `online_mode` 如何启用（配置键、读取位置、改变了什么） | UNVERIFIED | 无。属 provider 内部配置，按 ADR-0019 §2 不进通用契约 |
| 2 | `run_chunk` / chunk 输入的真实 API 与调用序列 | UNVERIFIED | 无。`DittoRealtimeTransport.push_audio` 是节点侧实现要满足的形状，不是对 upstream API 的复刻 |
| 3 | 期望采样率与音频格式 | **部分可推断** | AiFamily 侧强制 PCM16/mono/16000Hz。若节点期望其它形状，转换责任在**节点侧**，不得在 AiFamily 侧静默重采样（会破坏冻结音频哈希） |
| 4 | `chunksize` 语义（如 `(3,5,2)` 元组到样本/帧的映射） | UNVERIFIED | 无。属 provider 配置 |
| 5 | 帧生成路径（音频块 → 帧的组件序列） | UNVERIFIED | 无 |
| 6 | worker 线程 / 队列 / 缓冲的名称与数量 | UNVERIFIED | 无。AiFamily 侧只暴露 `queue_depth` 指标，其值由节点上报 |
| 7 | 首帧在何处可得 | UNVERIFIED | AiFamily 侧以 `avatar.first_frame` 事件定义首帧时刻，与引擎内部实现解耦 |
| 8 | 渐进帧能否经 callback/queue 暴露而**不改** upstream | UNVERIFIED — **最关键的未知** | 若答案为「不能」，则需要节点侧 bridge 脚本；ADR-0019 §Consequences 已把这一风险显式接受 |
| 9 | 是否需要改动 upstream | UNKNOWN | 同上 |

### 3.1 为什么问题 8 最关键

如果 Ditto 的 writer 只能落地成视频文件、没有任何逐帧 hook，那么"realtime"就需要在
节点侧写一个 bridge（在引擎进程内订阅帧、经 endpoint 推出去）。这不影响 ADR-0019
冻结的抽象——`RealtimeAvatarProvider` 不关心对面怎么拿到帧——但它决定了
FAMILY-REALTIME-002 的工作量与是否触及"不得 vendor Ditto"的边界
（**bridge 脚本住在 GPU 节点上，不入本仓库**，因此不构成 vendoring）。

### 3.2 关于既有知识的处置

作者对 upstream 仓库结构（`stream_pipeline_online.py` / `stream_pipeline_offline.py` /
`core/atomic_components/*`）存在训练期先验印象。**本文件不记录这些印象。**
理由：任务明确要求"Do not claim real inference from fixtures"，同一纪律适用于文档——
把回忆写成带行号的表格，读者无法区分它与实测，而这正是 FAMILY-MEDIA-001 审计
要防的病。未核验的内容一律记为 UNVERIFIED，不补细节。

## 4. Node-side verification checklist（下次接触 GPU 节点时逐条销项）

在节点上（引擎已 clone 至 `$DITTO_ENGINE_ROOT`，commit = `c3e47ee…`）执行并记录：

1. `git -C "$DITTO_ENGINE_ROOT" rev-parse HEAD` —— 确认 pin 未漂移
2. 列出 repo 根与 `core/atomic_components/` 的实际文件清单（确认模块名假设）
3. 定位 online 与 offline 两条管线的入口类/函数，记录**真实签名**（含行号）
4. 记录 `online_mode` 的配置键、默认值、以及它切换了哪些组件
5. 记录 chunk 输入方法的签名、期望 dtype / 归一化区间 / 采样率
6. 记录 `chunksize` 元组每一位的含义及其到样本数与帧数的换算
7. 判定：**不改 upstream** 能否取到渐进帧？（可以 → 记录 hook；不可以 → 写出所需
   最小改动，并确认该改动只落在节点侧）
8. 记录首帧可得的位置与最早时刻
9. 记录 worker/队列结构与可观测的 `queue_depth` 来源
10. 用 `docs/11_delivery/media_factory/DITTO_REALTIME_ONLINE_SMOKE_RUNBOOK.md`
    执行一次 20ms 分块 smoke，回填 `DittoOnlineSmokeReport`

销项后本文件升版；**若结论要影响架构，须走 ADR**，不得直接改 ADR-0019 的 Decision 段。

## 5. 本文件不主张什么

- 不主张 Ditto 适合或不适合 realtime。`WINNER=NOT_DECIDED` 未变。
- 不主张 AiFamily 侧的抽象已被真实引擎验证。`REAL_NEURAL_REALTIME_FRAMES=NO`。
- 不主张 `NOT_RUN` 的指标有任何数值。

## References

- `governance/ADR/ADR-0019-realtime-avatar-provider-and-gpu-node-boundary.md`
- `governance/ADR/ADR-0018-media-avatar-provider-and-gate1-benchmark.md`
- `docs/13_research/technology/FAMILY_MEDIA_001_REALITY_AUDIT.md`（`RESEARCH_ONLY`）
- `docs/11_delivery/media_factory/DITTO_GATE1_GPU_RUNBOOK.md`
- `docs/11_delivery/media_factory/DITTO_REALTIME_ONLINE_SMOKE_RUNBOOK.md`
