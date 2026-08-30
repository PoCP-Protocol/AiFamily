import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

const source = readFileSync(resolve(process.cwd(), "components/family/family-experience-hub.tsx"), "utf8");

describe("family experience hub blueprint alignment", () => {
  it("expresses the family-first value chain instead of implementation UI ids", () => {
    expect(source).toContain("WE ARE FAMILY");
    expect(source).toContain("看见需要");
    expect(source).toContain("一起理解");
    expect(source).toContain("做一件小事");
    expect(source).toContain("需要时有人");
    expect(source).not.toContain("UI-01");
    expect(source).not.toContain("UI-02");
  });

  it("keeps the primary actions attached to real semantic journeys", () => {
    expect(source).toContain('go("/assessment" as Href)');
    expect(source).toContain('go("/actions/today" as Href)');
    expect(source).toContain('go("/catalog" as Href)');
    expect(source).toContain('go("/growth/story" as Href)');
  });

  it("labels disconnected browser sessions as a local demo", () => {
    expect(source).toContain("本机演示 · 未同步");
    expect(source).toContain("家庭上下文已连接");
  });
});
