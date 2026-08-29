import { describe, expect, it } from "vitest";

import { suggestPrivateNoteTags, validatePrivateNoteTagInput } from "../server/private-note-tags";

describe("private note tag gateway", () => {
  it("returns only controlled editable tags from a structured model response", async () => {
    const result = await suggestPrivateNoteTags(
      { title: "今晚先听完", body: "孩子有点难过，我先停下来听他说完。", topic: "亲子沟通", privacyAcknowledged: true },
      {
        listModels: async () => ({ object: "list", data: [{ id: "gpt-5-mini", object: "model", created: 1, owned_by: "openai" }] }),
        invoke: async () => ({ id: "test", created: 1, model: "gpt-5-mini", choices: [{ index: 0, message: { role: "assistant", content: JSON.stringify({ tags: ["亲子沟通", "情绪陪伴", "孩子很棒"] }) }, finish_reason: "stop" }] }),
      } as never,
    );

    expect(result).toMatchObject({ tags: ["亲子沟通", "情绪陪伴"], source: "MODEL_GATEWAY", persistence: "NONE", externalEffect: false, factBoundary: "TAGS_ARE_EDITABLE_PERSPECTIVE_NOT_FACT" });
  });

  it("blocks identifying family information before a model request", () => {
    expect(() => validatePrivateNoteTagInput({ title: "小学四年级的日常", body: "今天一起阅读", topic: "家庭阅读", privacyAcknowledged: true })).toThrow("private_note_contains_identifying_information");
  });

  it("falls back to a rule-based editable classification when the model is unavailable", async () => {
    const result = await suggestPrivateNoteTags(
      { title: "睡前共读", body: "今晚一起读了一个小故事。", topic: "家庭阅读", privacyAcknowledged: true },
      { listModels: async () => { throw new Error("offline"); }, invoke: async () => { throw new Error("unreachable"); } } as never,
    );

    expect(result).toMatchObject({ source: "RULE_BASED_FALLBACK", modelGatewayStatus: "FALLBACK_RULE_BASED", persistence: "NONE", externalEffect: false });
    expect(result.tags).toContain("家庭阅读");
  });
});
