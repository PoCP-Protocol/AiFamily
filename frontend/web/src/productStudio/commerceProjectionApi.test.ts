import { describe, expect, it } from "vitest";
import { HttpCommerceProjectionApiClient } from "./commerceProjectionApi";

const payload = { family_id: "f-1", projection_version: 1, visibility: "FAMILY_PRIVATE", read_only: true, order_intents: [], entitlements: [], text_equivalent: "read only" };
const response = (body: unknown, ok = true, status = 200) => ({ ok, status, json: async () => body }) as Response;

describe("commerce projection API", () => {
  it("reads an encoded family projection with scope headers", async () => {
    let request: RequestInfo | URL | undefined; let init: RequestInit | undefined;
    const client = new HttpCommerceProjectionApiClient({ fetchImpl: async (input, options) => { request = input; init = options; return response(payload); }, authorization: "Bearer x", tenantScope: "tenant-a" });
    await expect(client.get("family/a")).resolves.toMatchObject({ family_id: "f-1", read_only: true });
    expect(String(request)).toContain("family%2Fa"); expect(init?.headers).toMatchObject({ authorization: "Bearer x", "x-tenant-scope": "tenant-a" });
  });
  it("fails closed on a writable or cross-family response", async () => {
    const client = new HttpCommerceProjectionApiClient({ fetchImpl: async () => response({ ...payload, read_only: false }) });
    await expect(client.get("f-1")).rejects.toMatchObject({ code: "INVALID_RESPONSE" });
  });
});
