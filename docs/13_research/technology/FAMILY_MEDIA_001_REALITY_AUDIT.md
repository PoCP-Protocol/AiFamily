---
id: RES-TECH-FAMILY-MEDIA-001
title: FAMILY-MEDIA-001 Reality Audit — Famili Digital Human & Media Factory
type: research
status: draft
version: 1.0
owner: media-factory-auditor
created: 2026-09-03
updated: 2026-09-03
canonical: false
supersedes: null
superseded_by: null
---

```text
STATUS: RESEARCH_ONLY
NOT_CANONICAL: TRUE
DOC_KIND = EVIDENCE / REALITY AUDIT
本文件是证据与审计结论，不是决定、不是实现规格、不是当前系统真相。
晋升须走 ADR（docs/12_governance/DOCUMENT_GOVERNANCE.md §8.2）。
CODING_STARTED=NO — 本任务禁止正式编码。
TARGET STATE ≠ CURRENT STATE — 凡引用前瞻架构处均作此声明。
```

# FAMILY_MEDIA_001_REALITY_AUDIT

## 1. EXECUTIVE_CONCLUSION

**AiFamily 今天没有可用的法咪莉数字人，也没有 Media Factory。**  
旧 Family 完成了大量「外围 Runtime」（Avatar/Speech Gateway、Realtime Session、Viseme/Gaze/Gesture 规则层、大量测试），但用户可见层停在 **VBF-0 静态主图 Canvas 贴图**；真正的 `image + audio → neural avatar → talking-person video` 主路径 **未打通**。本机仍是 **GT 730 / 2GB**，`MODERN_GPU_NODE=MISSING`。  
AUTOavantar 是有价值的 **offline MediaJob 工作流参考**（checkpoint / GPU load-unload / FFmpeg compose），**不可整仓迁入**；HeyGem/IndexTTS 只能是 Provider。

硬状态：

```text
REAL_NEURAL_AVATAR_INFERENCE = ABSENT   # 产品集成路径；见 §8
FAMILI_V2_ASSETS_FOUND       = YES
AUTOAVANTAR_CODE_LEVEL_REVIEW= COMPLETED
CODING_STARTED               = NO
```

---

## 2. CURRENT_AIFAMILY_STATE

### 2.1 对 16 个强制问题的事实答案

| # | 问题 | 答案 |
|---|---|---|
| 1 | Python-only 后端边界 | **是**（R1 / ADR-0001）。正式后端唯一为 Python/FastAPI/SQLAlchemy/PostgreSQL。TS 只可作 reference。 |
| 2 | `backend/intelligence` 正式职责 | **唯一 AI Runtime（R10）**：Model Gateway / Context / Agent / Tool / Memory / Safety / Human Gate / Eval 等收敛于此。 |
| 3 | `model_gateway` 成熟度 | **EXPERIMENT**：真实代码 + 测试存在；**零业务调用方**；**零外部供应商通过第16条准入**。 |
| 4 | `principal_core` | **NOT_STARTED**：`backend/intelligence/principal` **磁盘不存在**；registry disposition=MIGRATE，排期 Batch 5。 |
| 5 | Context Engine | **ABSENT** |
| 6 | Agent Runtime | **PLANNED**（设计有，代码无） |
| 7 | Tool Runtime | **PLANNED** |
| 8 | Memory | **ABSENT** |
| 9 | Evaluation | **ABSENT** |
| 10 | Media Factory | **ABSENT**（无目录、无 registry 条目、无代码） |
| 11 | Avatar Runtime | **ABSENT** |
| 12 | Voice Runtime | **ABSENT** |
| 13 | 新 AI capability registry 要求 | `CAPABILITY_REGISTRY.yaml` **已存在**；`AI_USE_CASE_REGISTRY.yaml` **MISSING**。涉 AI 行为仍须按 `AI_NATIVE_PRINCIPLES` 自检；入仓须 DOMAIN_REGISTRY + MIGRATION_MANIFEST（R2/R3）。 |
| 14 | 新架构决策 ADR 要求 | **强制**：无 ADR 不做架构决策；禁止在实现 PR 顺手改宪章。 |
| 15 | AI 可否直接改 Family canonical truth | **否（R9）**：仅 Perspective/Recommendation；Fact 须 Named Action + Human Gate。 |
| 16 | Audit/Consent/Authorization/Idempotency | 平台内核 **已实现并有测试**（Wave 1）；MediaJob 落库写状态时应复用，不得另起一套。 |

### 2.2 文档对照

| 文档 | 状态 |
|---|---|
| `AI_ARCHITECTURE.md` | **存在**（规格；含“现状核实”） |
| `AI_PLATFORM_FORWARD_ARCHITECTURE.md` | **存在**；自标 `canonical: false` / TARGET STATE；**TARGET ≠ CURRENT** |
| `CAPABILITY_REGISTRY.yaml` | **存在**（CLAUDE.md 旧注“尚未建立”已过时） |
| `AI_USE_CASE_REGISTRY.yaml` | **MISSING** |

### 2.3 一句话

治理与平台内核有；AI 业务能力与数字人 **几乎全空**；Media Factory **尚未开工**。

---

## 3. CURRENT_FAMILI_RDH_STATE

旧仓库路径：`D:\Family\50_开发_dev\`（分支 `feature/famili-rdh-smoke-v1-20260821`，含**既有未提交 WIP**——本审计只读，未改动）。

| 层 | 状态 | 证据 |
|---|---|---|
| IP / YAML 策略 | 冻结文档存在 | `multimodal/visual/*.yaml`，2026-08-17 frozen |
| Smoke 输入资产 | 冻结完成 | `RDH_SMOKE_ASSET_FREEZE_REPORT_V1.md`；合同 `RDH_SMOKE_INPUT_CONTRACT_V1.json` |
| Avatar Lab UI / WS / 状态机 | 大量代码+测试 | `apps/avatar-lab/src/*` |
| 用户可见渲染 | **静态主图** | `FamiliLayered2DRenderer` VBF-0：`dynamic_*=false`，嘴/眼/姿全 no-op |
| 几何 placeholder 渲染 | 存在（矢量脸） | `Avatar2DRenderer`：圆头+椭圆眼+嘴型画线 |
| Neural engine 集成 | **产品路径无** | Ditto/MuseTalk/LivePortrait 未进 gateway；合同写 `DITTO: NOT_STARTED` |
| 实验 MP4 文件 | 磁盘有孤立产物 | `outputs/smoke/DITTO_FAMILI_VISUAL_V1_SMOKE_AUDIO_V0.mp4` (~2.0MB)；**无人类验收记录**；本机仍 GT730 |
| GPU | TIER_0 | `nvidia-smi`: GeForce GT 730, 2048 MiB；`MODERN_GPU_NODE=MISSING` |

**用户打开后“活不起来”的直接原因**：看到的是静止法咪莉图（或矢量假脸）+ 可能的音频；嘴/表情/眼神在 VBF-0 **故意不画**；neural 视频从未成为产品主路径。

---

## 4. OLD_FAMILY_ASSETS_FOUND

| Asset | 分类 | 说明 |
|---|---|---|
| `FAMILI_RDH_SMOKE_REFERENCE_V1.png` | **B Frozen Benchmark** + **E Historical** | Smoke 视觉输入；sha256 冻结；V2 出现后降为历史主参考 |
| `FAMILI_VISUAL_DIRECTION_V1.png` + `.metadata.json` | **A 人工认可 IP**（方向） / **E Historical** | metadata: `APPROVED_VISUAL_DIRECTION`；非最终 3D 模型 |
| `FAMILI_RDH_SMOKE_AUDIO_V0.wav` + metadata | **B Frozen Benchmark** | 8.811s；文案「你好，法咪莉…」；Gate1 应固定此音频 |
| `RDH_SMOKE_INPUT_CONTRACT_V1.json` | **B Frozen Benchmark** | 引擎必须同字节；禁重编码 |
| `FAMILI_VOICE_BASELINE_V0_CLEAN_FINAL.wav` | **A 人工认可**（基线）但 identity **NOT_FINAL** | Smoke 音频为其字节拷贝 |
| `visual-identity.yaml` 等 6 份 visual YAML | **A IP Asset**（策略词汇） | expression/gesture/gaze/scene/wardrobe |
| `voice-identity.yaml` / `prosody-policy.yaml` | **D 非最终 Production** | 极简；voice identity NOT_FINAL |
| voice-audition 系列 wav | **C 技术测试 / D 非生产** | 试音，非锁定 |
| `DITTO_*.mp4` 孤立输出 | **C 技术测试**；验收 **未知** | 非 Gate1 通过证据 |
| V2：`FAMILI_V2_*_R01.png`（本机 `D:\Famili-V2-Reference\`） | **A 人工认可 IP**（新主参考） | 见 §16 |

**禁止删除旧资产。**

---

## 5. OLD_RUNTIME_COMPONENTS_FOUND

| 组件 | 位置 | 真实做了什么 |
|---|---|---|
| avatar-gateway | `packages/avatar-gateway` | Provider registry + `FamilyLocal2D` **事件/FSM**，**不做像素** |
| speech-gateway | `packages/speech-gateway` | Azure STT/TTS 适配、viseme→MouthShape **规则映射**、fake/fallback |
| realtime-session | `packages/realtime-session` | `sessionMachine` 小状态机 |
| fpai-multimodal-contracts | `packages/fpai-multimodal-contracts` | CharacterIdentity / MotionIdentity / PerformanceIntent 类型 |
| fpai-multimodal-runtime | `packages/fpai-multimodal-runtime` | IdentityResolver、PerformanceFrameValidator |
| fpai-performance-planner | `packages/fpai-performance-planner` | Intent→expression/gesture/gaze **规则表** |
| avatar-lab | `products/famili-principal/apps/avatar-lab` | WS server、clock、viseme scheduler、Canvas 渲染、大量单测 |
| FamiliLayered2DRenderer | avatar-lab | **drawImage 静态主图**；动态层全 no-op |
| Avatar2DRenderer | avatar-lab | **矢量几何 placeholder** |
| principal-ai | `packages/principal-ai` | LLM 侧参考（非 embodiment） |
| rdh-benchmark | `experiments/rdh-benchmark` | 冻结资产 + smoke 协议；neural 未完成 |

---

## 6. WHAT_IS_REAL

- AiFamily：平台内核（identity/authz/consent/audit/idempotency）、model_gateway 代码与测试、文档治理。
- 旧 Family：完整 multimodal **契约与规则表演出栈**；Canvas 能画出**静止**法咪莉主图或矢量脸；TTS/viseme **映射表**；smoke 音视频**输入资产**冻结。
- 本机 GPU：GT 730 2GB（可探测）。
- AUTOavantar：完整 offline 数字人视频管线源码（HeyGem+IndexTTS+FFmpeg），已 clone 至 `D:\_reference\AUTOavantar`（**AiFamily worktree 外**）。
- V2 三张主参考图：本机存在且已目视。

---

## 7. WHAT_IS_PLACEHOLDER_OR_SIMULATED

- `FamiliLayered2DRenderer`：接受 PerformanceFrame 但 **不可视化**（自述 VBF-0 / pending VBF-1）。
- `Avatar2DRenderer`：非 IP 人物，几何假脸。
- `FamilyLocal2DAvatarGateway`：自述不做真实像素。
- `visemeMapper`：Azure viseme_id→8 MouthShape **查表**（注释写明未活体校验）。
- `gazeRuntime` / PerformancePlanner：语义→偏移 / intent→表情 **规则**。
- AiFamily `design_copilot`：全 `NotImplementedError`。
- 合同态 `DITTO: NOT_STARTED` 与孤立 mp4 并存 → **不得**把文件存在当成 Gate PASS。

---

## 8. REAL_NEURAL_AVATAR_INFERENCE_STATUS

```text
REAL_NEURAL_AVATAR_INFERENCE = ABSENT
```

判据：

1. 产品渲染器明确 **无** neural 路径（VBF-0 `drawImage` only）。
2. avatar-gateway **禁止** Live2D/商业 SDK/GPU（`familyLocal2d.ts` 注释）。
3. Smoke 合同候选引擎 Ditto/MuseTalk/LivePortrait；状态矩阵写 **NOT_STARTED** + 阻塞于 MODERN_GPU。
4. 完整路径 `image+audio → neural model → generated talking frames` **未进入** AiFamily，也未接入 Family 产品主链。

附注：存在孤立 `DITTO_*.mp4`，但无验收表填写、本机 GPU 仍不足以支撑 modern neural、合同仍写 NOT_STARTED → **不构成 PRESENT**。

---

## 9. ROOT_CAUSE_OF_PREVIOUS_FAILURE

按重要性：

| Pri | 根因 | 证据 |
|---|---|---|
| **P0** | **Neural Avatar Engine 缺失 / 未接入产品** | VBF-0 no-op；gateway 无 GPU；合同 DITTO NOT_STARTED |
| **P1** | **Visible avatar last / architecture-first** | 大量 WS/FSM/viseme/gaze/planner/tests 先于“真会动的人” |
| **P1** | **视觉层是 2D workaround** | Layered2D=静态图；Avatar2D=矢量假脸 |
| **P2** | **MODERN_GPU_NODE 缺失** | 文档 + `nvidia-smi` GT730 2GB；SMOKE 明文禁止用 GT730 跑 Ditto |
| **P2** | **Realtime 栈开发过早** | realtime-session / realtimeServer 在无 neural 帧流时已大量建设 |
| **P3** | **Ditto/MuseTalk/LivePortrait 停在评估协议** | 合同候选列表 + human-review 模板空白 |
| **P3** | **Voice identity 未最终却并行试音** | NOT_FINAL + refinement PAUSED until first real video |
| **P4** | **测试通过 ≠ 可见能力** | 单测验证调度/映射/draw call，不验证“像活的法咪莉” |

---

## 10. REUSE_AS_IS

无整包 `REUSE_AS_IS`（语言栈为 TS；AiFamily 后端强制 Python）。

---

## 11. MIGRATE_AS_ASSET

| 项 | WHY |
|---|---|
| RDH smoke 音视频 + input contract | 冻结字节；Gate1 对照组 |
| visual/voice YAML + Visual Bible / IP 文档 | IP 词汇与品牌约束 |
| V1 参考图 | 历史锁定；勿删 |
| V2 三张 master/reference | 新身份主输入 |
| human-review 表格模板 | 验收流程资产 |

---

## 12. REIMPLEMENT_IN_PYTHON

| 概念 | WHY |
|---|---|
| Provider registry 模式（avatar/speech） | 对齐 model_gateway 准入思想；R7/R10 |
| MouthShape / PerformanceFrame 语义层（精简） | 跨引擎中立契约 |
| Offline MediaJob + Provenance | 平台复用 audit/idempotency |
| FFmpeg Composer（概念级重写） | 见 AUTOavantar postprocess |

---

## 13. REUSE_CONCEPT_ONLY

- sessionMachine / speechPlaybackClock / viseme 迟到丢弃策略
- PerformancePlanner 的 intent→表演映射表思路
- IdentityResolver / “identity lock” 思想
- Offline↔Realtime **永久分离**（旧仓已暗示 realtime 与 smoke offline 分轨）

---

## 14. R&D_REFERENCE_ONLY

- 全套 avatar-lab 客户端实现与单测
- Azure SDK 具体 transport
- principal-ai TS
- rdh-benchmark 过程文档 / 试音 wav
- AUTOavantar 整仓（许可证不清 + 架构不兼容）

---

## 15. DO_NOT_MIGRATE

| 项 | WHY |
|---|---|
| FamiliLayered2DRenderer / Avatar2DRenderer 作为“数字人完成” | 假实现；违反 NO VISIBLE FAMILI gate |
| Nest/TS 第二后端 realtime 整栈 | R1 |
| AUTOavantar SQLite 作为平台核心 | 与 PostgreSQL canonical 冲突 |
| AUTOavantar 单线程 FIFO 作为平台调度 | 不可扩展；不适合作家庭平台主链 |
| HeyGem / IndexTTS hard-binding | 只能 Provider |
| Live2D / 商业 Avatar SDK 绑定（旧仓已禁） | 保持 |
| 把 Offline MediaJob 塞进 Realtime 对话主链 | 任务 §16 |

---

## 16. FAMILI_V1_V2_VISUAL_ASSET_DECISION

### 目视比较（V1 smoke vs V2 identity）

| 维度 | V1 SMOKE REFERENCE | V2 IDENTITY MASTER |
|---|---|---|
| identity stability | 可识别法咪莉 | 更稳：办公室品牌上下文一致 |
| talking-head suitability | 半身、正面、可用 | **更优**：清晰口区、肩以上 |
| face/hair/eye/lip clarity | 高 | **更高**（光影与发型更干净） |
| body crop | 胸像 | 胸像偏腰上 |
| background interference | 浅灰科技线 | 办公室景深；品牌墙——可接受但引擎需测背景稳定性 |
| visual maturity / IP | 方向锁定 | **产品级 WHO SHE IS** |

```text
OLD_VISUAL_V1_DISPOSITION=
  KEEP_AS_HISTORICAL_FROZEN_BENCHMARK;
  NO_LONGER_PRIMARY_IDENTITY_MASTER;
  DO_NOT_DELETE

V2_IDENTITY_MASTER_ROLE=
  WHO_SHE_IS — Gate1 Avatar Engine Benchmark 主输入肖像

V2_OFFICE_MASTER_ROLE=
  HOW_SHE_APPEARS_IN_HER_WORLD — 上半身/服装/办公室/坐姿；非首轮 lip-sync 主输入

V2_INTERACTION_REFERENCE_ROLE=
  HOW_SHE_RELATES — 倾听/手势/与孩子相对位置；Gate2 活力度参考，非 Gate1 引擎输入

FIRST_AVATAR_BENCHMARK_INPUT_RECOMMENDATION=
  FAMILI_V2_IDENTITY_MASTER_R01.png
  + FAMILI_RDH_SMOKE_AUDIO_V0.wav
  （固定音频，不换 TTS）
```

产品身份冻结（任务 §11）：法咪莉校长 = Identity+Persona+Relationship+Memory+Context+Reasoning+Agent+Tools+Knowledge+Voice+**Embodiment**；Avatar 只是 Embodiment。Media Factory **不负责** Memory/Reasoning/Family Understanding。

---

## 17. AUTOAVANTAR_CODE_ABSORPTION_MATRIX

Clone：`D:\_reference\AUTOavantar`（depth=1）。**无根目录 OSS LICENSE 文件**；仅有产品激活/配额 `license_service` → **LICENSE_REVIEW_REQUIRED**。GitHub Public ≠ 可商用整仓粘贴。

| SOURCE_FILE | CLASS_OR_FUNCTION | PURPOSE | GOOD_IDEAS | REUSABLE_LOGIC | ARCHITECTURAL_PROBLEMS | LICENSE_RISK | AIFAMILY_TARGET_MODULE | ACTION |
|---|---|---|---|---|---|---|---|---|
| `business/workflow.py` | `DigitalHumanWorkflow` | script→TTS→avatar→post | 分阶段进度；checkpoint 恢复；low_memory 卸模型 | 阶段机概念 | 与 HeyGem/IndexTTS 硬耦合；单体巨大 | 整仓不清 | `intelligence/media_factory/workflow.py` | REIMPLEMENT_HEAVY |
| `core/models/checkpoint.py` | `CheckpointData` / `TagGroupCheckpoint` | 断点续传 | 按标签组粒度 resume | 字段设计思路 | 路径散落字符串 | 同上 | `media_factory` job checkpoint | REIMPLEMENT_LIGHT |
| `core/models/task.py` | `Task` / `TaskConfig` / status enum | 任务模型 | 显式阶段枚举 | 枚举拆分思路 | HeyGem 阶段名进核心模型 | 同上 | `media_factory/models.py` | REIMPLEMENT_LIGHT |
| `core/scheduler/task_scheduler.py` | `SimpleTaskScheduler` | 单线程 FIFO | 超时/取消 | 几乎无 | **单线程 FIFO 不能做平台核心** | 同上 | （未来 worker） | DO_NOT_MIGRATE |
| `core/engines/gpu_manager.py` | `GPUResourceManager` | 同机 TTS↔Avatar 互斥 | acquire/release；unload 切换 | 租约思想 | 全局单例；仅两引擎 | 同上 | `ComputeLeasePort` / LocalSequential | REIMPLEMENT_LIGHT |
| `core/engines/heygem_engine.py` | `HeyGemEngine` | load/unload/generate | 引擎生命周期 | 接口形态 | **Hard binding HeyGem** | HeyGem Community License **MAU 阈值** | `providers/avatar.py` 之一 | LICENSE_REVIEW_REQUIRED |
| `core/engines/tts_engine.py` | TTS wrapper | IndexTTS | load/unload | 接口形态 | Hard binding IndexTTS | IndexTTS 许可需核 | `providers/voice.py` | LICENSE_REVIEW_REQUIRED |
| `business/postprocess/post_processor.py` | PostProcessor | 字幕/BGM/封面/合并 | FFmpeg 滤镜管线 | 命令编排思路 | 与 runtime 路径耦合 | 同上 | `composer/ffmpeg.py` | REIMPLEMENT_HEAVY |
| `backend/api/services/smart_cut_service.py` + TransNetV2 | smart clipping | 镜头切分 | 可选后期能力 | 算法思路 | MediaPipe/权重许可 | 模型许可 | 后期可选 | REUSE_CONCEPT / LICENSE_REVIEW |
| `backend/api/services/database.py` | SQLite persistence | 本地任务库 | — | — | **SQLite 非平台真相库** | — | — | DO_NOT_MIGRATE |
| `engines/heygem/**` | DINet 等 | 实际推理 | 证明 offline neural 可行 | **不要复制进 AiFamily 核心** | 第三方引擎树 | **高** | 外部 provider 进程 | DO_NOT_MIGRATE |
| `voicel/indextts/**` | IndexTTS | TTS | — | — | 巨量第三方 | **高** | 外部 provider | DO_NOT_MIGRATE |

### 关键问答

- **Workflow 值得吸收**：阶段划分（script/audio/avatar/post）、进度、失败点恢复——**重写**为 MediaJob。
- **Checkpoint**：按 segment/tag 粒度 + 产物路径登记——**轻量重写**。
- **Engine Adapter**：`load/unload/generate` + health——变成 `AvatarProvider`/`VoiceProvider`。
- **Low Memory**：阶段结束卸模型；`LocalSequentialComputeLease` 先做。
- **FFmpeg PostProcessor**：字幕/BGM/concat——概念重写，不粘贴。
- **Smart Clipping**：Gate1 **不需要**；后期可选。
- **Scheduler 不能照搬**：单线程 FIFO 服务不了多租户/多 GPU/与 Temporal 愿景冲突。
- **SQLite 不能成核心**：R1 真相库是 PostgreSQL；SQLite 最多本地 dev cache。
- **HeyGem/IndexTTS 只能是 Provider**：避免核心域绑定；许可有阈值/不明；可替换。

---

## 18. MEDIA_FACTORY_TARGET_ARCHITECTURE

**评估，未创建。**

建议落点：`backend/intelligence/media_factory/`

```text
contracts.py / models.py / workflow.py / job_service.py
provider_registry.py / provenance.py
providers/avatar.py / voice.py
composer/base.py / ffmpeg.py
```

**为何属于 `backend/intelligence`（R10）**：Media Factory 是生成式媒体 AI 能力（Avatar/Voice 模型推理编排），不是业务域 CRUD；必须与 model_gateway 一样收敛在唯一 AI Runtime，禁止 `family_avatar_service` 旁路。  
**边界**：产出 Artifact + Provenance；**不写** Family canonical Fact；不承载 Principal Memory/Reasoning。  
Job 状态写入若触达权威业务状态 → 走 platform audit/idempotency；AI 内容本身保持 DRAFT/PROPOSED 语义直至人工验收。

Offline Media Factory ≠ Famili Realtime Runtime（永久分离）。

---

## 19. OFFLINE_REAL_AVATAR_VERTICAL_SLICE

```text
FAMILI_V2_IDENTITY_MASTER_R01.png
+ FAMILI_RDH_SMOKE_AUDIO_V0.wav
    → AvatarEngine.render()
    → frames/video
    → optional Composer
    → FAMILI_REAL_AVATAR_V1.mp4
```

### Contracts（设计，未实现）

**Input contract**

- `identity_image_sha256` / `audio_sha256` 固定
- `engine_id` / `engine_version` / `seed`（若有）
- 禁止擅自重采样音频（继承 RDH 合同精神）

**Engine interface（最小）**

- `prepare(identity) → handle`
- `render(audio, handle) → VideoArtifact`
- `estimate()` / `health()` / `unload()`

**Output contract**

- `FAMILI_REAL_AVATAR_V1.mp4` + provenance JSON（engine、weights hash、input hashes、duration、resolution）

**Acceptance（人眼 Gate1）**

- Identity：像法咪莉（对 V2 master）
- Lip sync：口型跟音频基本对齐
- Motion：自然微头动 + 眨眼
- Stability：无崩脸、无闪烁、连续可看
- **禁止**：静图+音频、几何脸、CSS、API-only

---

## 20. PROVIDER_INTERFACE_PROPOSAL

最小集合（避免过度设计）：

```text
AvatarProvider:
  provider_id, capabilities, health, prepare, render, estimate, load, unload, provenance

VoiceProvider:   # Gate1 可 NOOP / passthrough 冻结 wav
ComposerProvider:
  mux / subtitle / concat

ComputeLeasePort:
  acquire(engine_class) / release
  实现1: LocalSequentialComputeLease
  未来: DistributedGpuComputeLease
```

兼容未来：`HeyGemAvatarProvider` / `MuseTalkAvatarProvider` / `DittoAvatarProvider` / `FamiliLayered2DProvider`(仅 debug) / `FutureRealtimeAvatarProvider`。

---

## 21. TOP_3_AVATAR_ENGINE_ROUTES

不预押 HeyGem。TOP 3（**质量分数一律 NEEDS_BENCHMARK**）：

| Rank | Route | 入选理由 | 主要风险 |
|---|---|---|---|
| 1 | **Ditto**（antgroup/ditto-talkinghead） | 旧 smoke 合同首选；Apache-2.0 代码许可清晰；宣称 realtime 潜力；已有 Family 评估协议 | 权重/依赖仍须核；需 modern GPU；Windows 部署 NEEDS_BENCHMARK |
| 2 | **MuseTalk** | MIT + 模型可商用声明；唇形专项强；Python 集成常见 | 头动/上半身弱于全身方案可能；依赖组件许可需逐项核 |
| 3 | **HeyGem（via AUTOavantar 经验）** | AUTOavantar 证明 offline 管线可跑；load/unload 成熟参考 | **Community License MAU 阈值**；与核心 hard-bind 风险；IDENTITY 对 stylized IP NEEDS_BENCHMARK |

LivePortrait-based：可作为后备研究，本轮不进 TOP3（上半身/身份保持需另证）。

维度表（未跑分前）：

| 维度 | Ditto | MuseTalk | HeyGem |
|---|---|---|---|
| Identity / Lip / Motion / Stability / Eyes / VRAM / Speed / Win/Linux / Python / License / Offline / Realtime | **NEEDS_BENCHMARK** | **NEEDS_BENCHMARK** | License=**REVIEW_REQUIRED**；其余 **NEEDS_BENCHMARK** |

---

## 22. AVATAR_BENCHMARK_SCORECARD

权重（采纳任务默认；理由：不像法咪莉 = FAIL）：

| 维度 | 权重 |
|---|---|
| Identity Preservation | **30%** |
| Lip Sync | 20% |
| Motion Naturalness | 15% |
| Temporal / Face Stability | 15% |
| Expression Quality | 10% |
| Eye / Gaze | 5% |
| Performance | 5% |

规则：**嘴型很好但不像法咪莉 = FAIL**（身份权重大于唇形）。

---

## 23. VOICE_STRATEGY_FOR_GATE1

```text
FIXED_AUDIO = FAMILI_RDH_SMOKE_AUDIO_V0.wav
DO_NOT_RETUNE_TTS_IN_PARALLEL
VOICE_IDENTITY = NOT_FINAL（继承旧结论）
```

第一轮只换 Avatar Engine，不换 Voice——否则无法归因。

---

## 24. GPU_AND_COMPUTE_REQUIREMENTS

| 问题 | 结论 |
|---|---|
| GT730 跑 modern neural？ | **否**（2GB；旧文档 TIER_0 diagnostic only） |
| 本机核实 | `nvidia-smi` → GeForce GT 730, 2048 MiB；`MODERN_GPU_NODE=MISSING` |
| 第一轮 benchmark 最低建议 | 文档曾写 **RTX 3060 12GB** 级；本审计 **采纳为最低建议**，最终以引擎实测为准 |
| 推荐开发 GPU | **12–24GB** 消费级（3060/4070Ti/4080 等）以便并行试 2–3 引擎 |
| 8/12/16/24GB 意义 | 8GB=紧（需 low_memory 串行）；12GB=可严肃 smoke；16–24GB=舒适多引擎对比 |
| CPU fallback | 可能存在但 **不可作为 Gate1 质量路径** |
| LocalSequentialComputeLease | **是**，第一阶段足够 |
| DistributedGpuComputeLease | 多机/队列产品化后再做 |

本任务未装 CUDA/Torch、未下载权重、未跑大型推理。

---

## 25. LICENSE_AND_COMMERCIAL_RISK

| 层 | 状态 |
|---|---|
| AiFamily platform code | 仓库自有治理 |
| AUTOavantar 整仓 | **无明确根 LICENSE** → LICENSE_REVIEW_REQUIRED；禁止整仓复制 |
| HeyGem engine/weights | Silicon Intelligence Community License；**MAU 阈值** → LICENSE_REVIEW_REQUIRED |
| IndexTTS | 需独立核对 → LICENSE_REVIEW_REQUIRED |
| Ditto code | Apache-2.0（公开声明）；**权重条款仍需核对** |
| MuseTalk code/models | MIT + 可商用声明；第三方依赖逐项核 |
| Famili 视觉资产 | 家庭自有 IP（旧 visual-identity ownership 声明）；V2 本机参考须确认权利链 |
| Voice identity | 基线来自 Zhipu glm-4-voice 试音；生产声线权利 **未最终** |
| Generated content | 需产品条款 + 未成年人场景合规（COMPLIANCE） |

**GitHub Public ≠ Commercially Reusable。**

---

## 26. FIRST_IMPLEMENTATION_PR_PROPOSAL

**下一任务（未开始）建议方向**——仅提案：

1. ADR：Offline Media Factory 归属 `backend/intelligence` + Offline/Realtime 分离。
2. Manifest/Registry：登记 `media_factory` capability（NOT_STARTED→…）。
3. 最小 Python 骨架：contracts + AvatarProvider protocol + job model（**无引擎推理**）。
4. 资产迁入策略：V2 identity + smoke audio 作为 benchmark fixtures（只读资产）。
5. GPU 节点采购/租用决策（人类）。

**禁止**在未通过 Gate1 前宣称数字人完成。

---

## 27. FILES_PROPOSED_TO_ADD

```text
docs/13_research/technology/FAMILY_MEDIA_001_REALITY_AUDIT.md  (本文件)
未来（非本任务）:
  governance/ADR/ADR-NNNN-media-factory-offline-runtime.md
  backend/intelligence/media_factory/**  (实现阶段)
  governance 登记行
```

---

## 28. FILES_PROPOSED_TO_CHANGE

```text
本任务：无强制变更。
未来：CURRENT_AI_MAP.md / DOMAIN_REGISTRY / MIGRATION_MANIFEST / CAPABILITY_REGISTRY
     （Media Factory 落地时同 PR 更新）
```

---

## 29. ACCEPTANCE_GATES

| Gate | 含义 | 本任务 |
|---|---|---|
| **GATE 1 — SHE EXISTS** | `FAMILI_REAL_AVATAR_V1.mp4` 人眼可见真人物+唇形+微动 | **仅规划** |
| GATE 2 — SHE FEELS ALIVE | 表情/注视/手势/关系感 | 后续 |
| GATE 3 — SHE TALKS REALTIME | 流式 ASR/TTS/Avatar/WebRTC | 后续 |
| GATE 4 — SHE KNOWS YOU | Principal/Memory/Context… | 后续 |

**NO VISIBLE FAMILI, NO DIGITAL-HUMAN PROGRESS.**

---

## 30. STOP_CONDITIONS

```text
CODING_STARTED=NO
D:\Family_MODIFIED=NO          # 本会话未写入 Family；既有 WIP 未触碰
AIFAMILY_CODE_MODIFIED=NO      # 仅新增本 RESEARCH 文档
REAL_NEURAL_AVATAR_INFERENCE=ABSENT
FAMILI_V2_ASSETS_FOUND=YES
AUTOAVANTAR_CODE_LEVEL_REVIEW=COMPLETED
NEXT_TASK_STARTED=NO
STOPPED=YES
```

---

## Appendix A — Why tests passed but she was not alive

外围全部可测：事件发出、viseme 按时调度、gaze 插值、Canvas clear/draw、资产加载成功。  
VBF-0 明确：`dynamic_mouth/gaze/blink/gesture = false`，`setMouthShape` 等为 no-op。  
因此 **API PASS ∧ WebSocket PASS ∧ State Machine PASS ∧ Renderer Initialized ∧ Unit Tests PASS** 可以同时为真，而用户只看到**一张不会说话的法咪莉静图**。

## Appendix B — Answers A/B/C

**A. AiFamily 现在真正有什么？**  
治理+平台内核+model_gateway 实验基建+迁入的部分业务域空壳/半成品+Mobile UI。**无** Media Factory、**无** Avatar/Voice Runtime、**无** Principal。

**B. 旧 Family 法咪莉数字人做到哪？**  
IP/策略/实时外围 Runtime/静态或几何渲染/smoke 资产冻结。**未**交付可验收的 neural talking-person。

**C. AUTOavantar 值得吸收什么？**  
Offline workflow、checkpoint、GPU 互斥生命周期、FFmpeg compose、Provider 化引擎边界——**概念/轻中度重写**；禁止整仓、SQLite 核心、FIFO 核心、HeyGem/IndexTTS 硬绑定。

---

## Appendix C — POST-AUDIT CANDIDATE CORRECTION (FAMILY-MEDIA-002A)

```text
STATUS: RESEARCH_ONLY / ADDENDUM
DATE: 2026-09-03
DOES_NOT_REWRITE: §21 TOP_3_AVATAR_ENGINE_ROUTES historical audit text above
```

Gate1 公平输入类已冻结为：

`STATIC REFERENCE IMAGE + FIXED AUDIO → REAL TALKING AVATAR VIDEO`

经官方 upstream README 复核后，ACTIVE Gate1 shortlist 校正为：

| Role | Candidate | Upstream |
|---|---|---|
| CANDIDATE_A | Ditto | https://github.com/antgroup/ditto-talkinghead |
| CANDIDATE_B | EchoMimicV3-Flash | https://github.com/antgroup/echomimic_v3 |
| CANDIDATE_C | SadTalker (BASELINE) | https://github.com/OpenTalker/SadTalker |

Deferred（保留，不删除）：

| Candidate | Class | Why deferred from ACTIVE Gate1 |
|---|---|---|
| MuseTalk | DEFERRED_SOURCE_VIDEO_LIPSYNC_CANDIDATE | Official: video dubbing / face-region lipsync; complete avatar path pairs with MuseV video |
| HeyGem / Duix | DEFERRED_VIDEO_CLONE_AVATAR_CANDIDATE | Official: clone from real-person video data |

`WINNER=UNKNOWN` · `quality_scores=null` · `benchmark_status=NOT_RUN` · no inference in 002A.

权威登记：`governance/media_factory/candidates/` + `SHORTLIST.yaml`；ADR-0018 Decision §4 已同步。
