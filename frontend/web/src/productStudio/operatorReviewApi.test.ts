import { describe, expect, it, vi } from "vitest";
import {
  HttpOperatorReviewApiClient,
  OperatorReviewApiError,
  type ProductDefinitionReviewTask,
} from "./operatorReviewApi";

const task = (changes: Partial<ProductDefinitionReviewTask> = {}): ProductDefinitionReviewTask => ({
  task_id: "human-task:one",
  status: "OPEN",
  proposal_id: "proposal:one",
  draft_id: "decision-draft:one",
  action_name: "ADOPT_PRODUCT_CONCEPT_AS_DEFINITION",
  action_arguments: {
    concept_id: "concept:one",
    zone_assessment_id: "assessment:one",
    source_decision_draft_ref: "decision-draft:one",
    product_kind: "MICRO_CAMP",
    duration_days: 21,
    primary_contradiction: "理解与行动之间存在断点",
    demand_ref: "demand:one",
    market_insight_refs: ["insight:one"],
    component_ids: ["component:action:v1"],
    skill_ids: ["skill:reflection:v1"],
    success_metric_ids: ["metric:completion:v1"],
    guardrail_ids: ["guardrail:no-ranking:v1"],
    stop_conditions: ["guardian_requests_stop"],
    pause_policy: "guardian_can_pause",
    human_gate_policy: "operator_review_required",
  },
  risk_level: "MEDIUM",
  provenance_ref: "model-draft:one",
  created_at: "2026-09-01T09:00:00Z",
  expires_at: "2026-09-02T09:00:00Z",
  etag: '"etag-one"',
  decision_id: null,
  decision_outcome: null,
  decision_reason: null,
  decided_at: null,
  request_id: null,
  ...changes,
});

const response = (body: unknown, status = 200) => new Response(JSON.stringify(body), {
  status,
  headers: { "content-type": "application/json" },
});

describe("HttpOperatorReviewApiClient", () => {
  it("uses Bearer for list/detail and validates the requested task", async () => {
    const fetchImpl = vi.fn()
      .mockResolvedValueOnce(response({ items: [task()] }))
      .mockResolvedValueOnce(response(task()));
    const client = new HttpOperatorReviewApiClient({ fetchImpl, accessToken: "token-one" });

    expect(await client.listOpenTasks()).toHaveLength(1);
    expect((await client.getTask("human-task:one")).proposal_id).toBe("proposal:one");
    expect(fetchImpl.mock.calls[0][1].headers.Authorization).toBe("Bearer token-one");
    expect(fetchImpl.mock.calls[1][0]).toContain("human-task%3Aone");
  });

  it("posts only outcome and reason while binding ETag and idempotency", async () => {
    const openTask = task();
    const fetchImpl = vi.fn().mockResolvedValue(response({
      actor_id: "operator:server",
      execution_status: "PENDING",
      task: task({
        status: "DECIDED",
        decision_id: "decision:server",
        decision_outcome: "ACCEPT",
        decision_reason: "证据充分",
        decided_at: "2026-09-01T10:00:00Z",
        request_id: "named-action-request:server",
      }),
    }));
    const client = new HttpOperatorReviewApiClient({ fetchImpl, accessToken: "token-one" });

    const result = await client.decide(openTask, "ACCEPT", "证据充分", "key-one");

    const init = fetchImpl.mock.calls[0][1] as RequestInit;
    expect(JSON.parse(String(init.body))).toEqual({ outcome: "ACCEPT", reason: "证据充分" });
    expect(init.headers).toMatchObject({
      Authorization: "Bearer token-one",
      "Idempotency-Key": "key-one",
      "If-Match": '"etag-one"',
    });
    expect(result.actor_id).toBe("operator:server");
    expect(result.task.request_id).toBe("named-action-request:server");
  });

  it("fails closed when server lineage does not match the reviewed proposal", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(response({
      actor_id: "operator:server",
      execution_status: "PENDING",
      task: task({
        status: "DECIDED",
        proposal_id: "proposal:forged",
        decision_id: "decision:server",
        decision_outcome: "ACCEPT",
        decision_reason: "证据充分",
        decided_at: "2026-09-01T10:00:00Z",
        request_id: "named-action-request:server",
      }),
    }));
    const client = new HttpOperatorReviewApiClient({ fetchImpl });

    await expect(client.decide(task(), "ACCEPT", "证据充分", "key-one"))
      .rejects.toMatchObject({ code: "INVALID_RESPONSE" } satisfies Partial<OperatorReviewApiError>);
  });

  it("rejects non-open queue items and detail lineage drift", async () => {
    const decidedTask = task({
      status: "DECIDED",
      decision_id: "decision:server",
      decision_outcome: "REJECT",
      decision_reason: "证据不足",
      decided_at: "2026-09-01T10:00:00Z",
    });
    const queueClient = new HttpOperatorReviewApiClient({
      fetchImpl: vi.fn().mockResolvedValue(response({ items: [decidedTask] })),
    });
    await expect(queueClient.listOpenTasks())
      .rejects.toMatchObject({ code: "INVALID_RESPONSE" } satisfies Partial<OperatorReviewApiError>);

    const expected = task();
    const detailClient = new HttpOperatorReviewApiClient({
      fetchImpl: vi.fn().mockResolvedValue(response(task({ draft_id: "decision-draft:changed" }))),
    });
    await expect(detailClient.getTask(expected.task_id, expected))
      .rejects.toMatchObject({ code: "INVALID_RESPONSE" } satisfies Partial<OperatorReviewApiError>);
  });

  it("rejects malformed state snapshots and extra action arguments", async () => {
    const missingDecision = task({ status: "DECIDED" });
    const malformedState = new HttpOperatorReviewApiClient({
      fetchImpl: vi.fn().mockResolvedValue(response({ items: [missingDecision] })),
    });
    await expect(malformedState.listOpenTasks())
      .rejects.toMatchObject({ code: "INVALID_RESPONSE" } satisfies Partial<OperatorReviewApiError>);

    const extraArguments = {
      ...task(),
      action_arguments: { ...task().action_arguments, tenant_scope: "forged" },
    };
    const malformedArguments = new HttpOperatorReviewApiClient({
      fetchImpl: vi.fn().mockResolvedValue(response({ items: [extraArguments] })),
    });
    await expect(malformedArguments.listOpenTasks())
      .rejects.toMatchObject({ code: "INVALID_RESPONSE" } satisfies Partial<OperatorReviewApiError>);
  });

  it("rejects duplicate references and an invalid decision timestamp", async () => {
    const duplicateReferences = {
      ...task(),
      action_arguments: {
        ...task().action_arguments,
        market_insight_refs: ["insight:one", "insight:one"],
      },
    };
    const duplicateClient = new HttpOperatorReviewApiClient({
      fetchImpl: vi.fn().mockResolvedValue(response({ items: [duplicateReferences] })),
    });
    await expect(duplicateClient.listOpenTasks())
      .rejects.toMatchObject({ code: "INVALID_RESPONSE" } satisfies Partial<OperatorReviewApiError>);

    const invalidTimestamp = task({
      status: "DECIDED",
      decision_id: "decision:server",
      decision_outcome: "REJECT",
      decision_reason: "证据不足",
      decided_at: "not-a-time",
    });
    const timestampClient = new HttpOperatorReviewApiClient({
      fetchImpl: vi.fn().mockResolvedValue(response(invalidTimestamp)),
    });
    await expect(timestampClient.getTask(invalidTimestamp.task_id))
      .rejects.toMatchObject({ code: "INVALID_RESPONSE" } satisfies Partial<OperatorReviewApiError>);
  });

  it("rejects changed decision arguments and reason", async () => {
    const reviewed = task();
    const changed = {
      ...reviewed,
      status: "DECIDED" as const,
      action_arguments: { ...reviewed.action_arguments, duration_days: 90 },
      decision_id: "decision:server",
      decision_outcome: "ACCEPT" as const,
      decision_reason: "服务端替换的理由",
      decided_at: "2026-09-01T10:00:00Z",
      request_id: "named-action-request:server",
    };
    const client = new HttpOperatorReviewApiClient({
      fetchImpl: vi.fn().mockResolvedValue(response({
        actor_id: "operator:server",
        execution_status: "PENDING",
        task: changed,
      })),
    });
    await expect(client.decide(reviewed, "ACCEPT", "人工理由", "key-one"))
      .rejects.toMatchObject({ code: "INVALID_RESPONSE" } satisfies Partial<OperatorReviewApiError>);
  });
});
