import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
const source = readFileSync(resolve(__dirname, "../app/ui/UI-20.tsx"), "utf8");
describe("UI-20 original teacher-detail baseline", () => {
  it("restores title, expert detail, expertise, available slots and one-to-one entry", () => {
    for (const copy of ["名师详情", "老师介绍", "擅长领域", "可了解的时间", "在线咨询", "预约 1 对 1"]) expect(source).toContain(copy);
  });
  it("reuses supply and slot projections and keeps the UI-21 route", () => {
    expect(source).toContain("getServiceOfferings");
    expect(source).toContain("getServiceSlots");
    expect(source).toContain("UI-21?offeringRef=");
  });
});
