---
id: DELIVERY-MEDIA-DITTO-REALTIME-SMOKE-RUNBOOK
title: Ditto Realtime Online Smoke Runbook
type: delivery
status: draft
version: 0.1
owner: media-factory
created: 2026-09-04
updated: 2026-09-04
canonical: false
---

# Ditto Realtime Online Smoke Runbook (FAMILY-REALTIME-001)

> **This runbook is prepared, not armed.** Nothing in AiFamily executes it. No agent may
> start a GPU node, SSH into one, buy one, download weights, or run inference on the
> strength of this document. A human operator runs it.
>
> Current result: **`REAL_DITTO_ONLINE_SMOKE = NOT_RUN`**.

## 0. What this smoke answers, and what it does not

It answers exactly one question:

> Does Ditto, in online mode, fed realtime-sized audio chunks, produce **progressive
> frames at all** — and if so, when does the first one appear?

It does **not** answer whether the avatar is good. Quality is the human visual gate's
job (ADR-0018 §5), and `Q-MOUTH-001` (teeth / mouth temporal consistency) is already
frozen as a known defect. A smoke that produces frames on schedule with a broken mouth
is still a **PASS for this smoke** and still not production ready.

## 1. Preconditions

| Item | Requirement |
|---|---|
| Node | Linux + Nvidia. Gate1 ran on RTX 4090D; ≥16 GB dedicated VRAM recommended |
| Engine | `antgroup/ditto-talkinghead` @ `c3e47eee2e626500017a0556b470d6d4182f85e8`, cloned **outside** the AiFamily worktree |
| Weights | HuggingFace `digital-avatar/ditto-talkinghead` (`LICENSE_REVIEW_REQUIRED`), outside the worktree |
| Backend | pytorch (reproducibility first; TensorRT is a later question) |
| Verification | `docs/13_research/technology/FAMILY_REALTIME_001_DITTO_ONLINE_AUDIT.md` §4 checklist **completed first** |

**Do §4 of the audit before this runbook.** The online chunk API has never been
inspected on this project's machines; running the smoke without confirming it is how a
harness produces a confident-looking failure.

## 2. Environment

```bash
export DITTO_ENGINE_ROOT=/opt/aifamily-engines/ditto-talkinghead
export DITTO_MODEL_ROOT=$DITTO_ENGINE_ROOT/checkpoints
export DITTO_PYTHON=$DITTO_ENGINE_ROOT/.venv/bin/python   # or conda `ditto`
export DITTO_DEVICE=cuda
# Set on the AiFamily side only when a node-side endpoint is actually serving:
export DITTO_REALTIME_ENDPOINT=<node endpoint>
```

Do **not** add Ditto's CUDA / Torch / TensorRT dependencies to AiFamily's
`pyproject.toml`. The realtime package imports none of them, and
`tests/architecture/test_realtime_boundaries.py::test_realtime_package_declares_no_gpu_dependency`
fails if that changes.

## 3. Frozen inputs

| Asset | SHA256 |
|---|---|
| `FAMILI_V2_IDENTITY_MASTER_R01.png` | `da7fe9d0ebc30b9f2aedd5fc55a08d04749d605e530137300e55719d498535aa` |
| `FAMILI_RDH_SMOKE_AUDIO_V0.wav` | `bf0ecbe6af18235f872e1dc8f29061f4c67bb101a5de56bba3fd9efc0c684912` |

Same assets as Gate1, deliberately: comparing realtime against offline is only
meaningful if the input is byte-identical. **No beautify, upscale, resample, denoise or
re-TTS.** The chunk splitter refuses to resample or downmix rather than silently fixing
a wrong input — that refusal is what keeps the audio hash meaningful.

## 4. Chunking

AiFamily produces the chunk sequence; it does not send it anywhere:

```python
from backend.intelligence.media_factory.realtime import split_wav_to_chunks

chunks = split_wav_to_chunks(
    "FAMILI_RDH_SMOKE_AUDIO_V0.wav",
    session_id="smoke-session-001",
    turn_id="smoke-turn-001",
    chunk_ms=20,      # or 40
)
```

* `chunk_ms=20` — the common browser `AudioWorklet` frame; closest to the real chain.
* `chunk_ms=40` — half the message rate, slightly more latency. Run both if time allows.

Each chunk is PCM16 / mono / 16 kHz and carries `sequence`, `presentation_time_ms`,
`turn_id` and `is_final`.

**Feed chunks at wall-clock pace.** Pushing the whole file at once measures batch
throughput and tells you nothing about realtime behaviour — it is the single easiest way
to produce a number that looks like success.

## 5. Machine-readable plan

```python
from backend.intelligence.media_factory.realtime import build_ditto_online_smoke_plan

plan = build_ditto_online_smoke_plan(
    identity_locator="node://frozen/FAMILI_V2_IDENTITY_MASTER_R01.png",
    audio_locator="node://frozen/FAMILI_RDH_SMOKE_AUDIO_V0.wav",
    chunk_ms=20,
)
```

The plan carries the frozen hashes, the env-var contract, the GPU node boundary, the
record fields, the node-side step list, and the forbidden-actions list. Building it runs
nothing: the module imports no `subprocess`, `socket`, `asyncio`, `paramiko`, `http` or
`urllib`, and an architecture test asserts that.

## 6. Node-side execution (human operator)

1. Confirm the node attests `engine=ditto-talkinghead`, `online_mode=true`,
   `device=cuda`, and the commit pin. **An unattested node must not report frames as
   real** — AiFamily marks frames `real_neural_inference=False` unless the node says
   otherwise, and that is by design (ADR-0019 §7).
2. Prepare the identity once. Record `identity_prepare_ms`.
3. Open a session. Start the turn clock **at the first pushed chunk**, not at session
   open — session open cost is not first-frame latency.
4. Push chunks at wall-clock pace until `is_final`.
5. Record the arrival time of the **first** frame, then every subsequent frame interval.
6. End the turn, drain remaining frames, record `total_runtime_ms`.
7. Record every error verbatim. An error list of `[]` on a run that visibly stuttered is
   a reporting bug, not a clean run.

## 7. What to record

Fill `DittoOnlineSmokeReport`:

```text
audio_chunk_count
chunk_ms
first_frame               (bool — did any frame arrive at all)
frame_count
effective_fps
first_frame_latency_ms
total_runtime_ms
real_neural_inference     (from node attestation, never assumed)
errors
```

Rules that are not negotiable:

* Anything not measured stays **`NOT_RUN`**. Anything attempted but unavailable is
  **`UNKNOWN`**. Neither may become `0`.
* Do not average away a stall. Report the interval series or its max, not just the mean.
* Fixture numbers and node numbers must never appear in the same table without their
  `source` field. `FIXTURE_SYNTHETIC` timings are real timings of a fake generator.

## 8. Interpreting the result

| Observation | Reading |
|---|---|
| No frame ever arrives | Online mode does not expose progressive frames as wired. Go back to audit §4 item 7 (does upstream need a node-side bridge?) |
| First frame arrives, then stalls | Chunk pacing or queue starvation. Record `queue_depth`; do not tune the model |
| Frames arrive at a stable interval | The realtime path is **plumbed**. Still not a product: quality gate and `Q-MOUTH-001` are untouched |
| Frames arrive but node did not attest | `real_neural_inference=False`. The run proves transport, not inference |

A successful smoke promotes exactly one flag: `REAL_DITTO_ONLINE_SMOKE=EXECUTED`. It
does **not** promote `WINNER`, `PRODUCTION_READY`, or any Gate verdict.

## 9. Boundary reminders

The node is a **GPU Media Compute Node** and nothing else
(`backend/intelligence/media_factory/realtime/gpu_node_boundary.py`):

* **May hold:** engine, weights, temporary session state, temporary audio chunks,
  temporary frame buffers, runtime metrics, ephemeral caches.
* **May never hold as canonical:** user memory, family profile, course state, assessment
  state, authorization state, business truth, Principal long-term memory.
* Retention: `EPHEMERAL_PER_SESSION`. The node never writes Family canonical truth (R9).

Copy back only: the filled report, logs, and the metrics manifest. **Do not commit
binaries.** Free the GPU and exit the engine environment when done.

## 10. Forbidden

* No automatic cloud GPU start or purchase; no payment binding by an agent.
* No agent-initiated SSH.
* No model weight download from this repository.
* No fabricated latency or fps numbers.
* No family, minor or business state on the node.
* No mouth/teeth tuning in this task — `Q-MOUTH-001` stays frozen.
