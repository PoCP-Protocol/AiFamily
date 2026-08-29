import { readFileSync } from "node:fs";
import path from "node:path";

import { describe, expect, it, vi } from "vitest";

import { createFamilyRefreshRunner, runFamilyRefresh } from "../lib/family/pull-to-refresh";

const REFRESHABLE_LIST_PAGES = [
  "app/(tabs)/index.tsx",
  "app/ui/UI-02.tsx",
  "app/ui/UI-04.tsx",
  "app/ui/UI-06.tsx",
  "app/ui/UI-08.tsx",
  "app/ui/UI-11.tsx",
  "app/ui/UI-12.tsx",
  "app/ui/UI-13.tsx",
  "app/ui/UI-14.tsx",
  "app/ui/UI-15.tsx",
  "app/ui/UI-16.tsx",
  "app/ui/UI-17.tsx",
  "app/ui/UI-18.tsx",
  "app/ui/UI-19.tsx",
  "app/ui/UI-20.tsx",
  "app/ui/UI-22.tsx",
  "app/ui/UI-23.tsx",
  "app/ui/UI-24.tsx",
  "app/ui/UI-25.tsx",
  "app/ui/UI-28.tsx",
  "app/ui/UI-29.tsx",
  "app/ui/UI-30.tsx",
  "app/ui/UI-31.tsx",
  "app/ui/UI-32.tsx",
  "app/ui/UI-33.tsx",
  "app/ui/UI-34.tsx",
] as const;

describe("家庭列表下拉刷新", () => {
  it("同时刷新远端家庭上下文与本机记录", async () => {
    const refreshRemote = vi.fn().mockResolvedValue(undefined);
    const reloadLocal = vi.fn().mockResolvedValue(undefined);

    await expect(runFamilyRefresh({ refreshRemote, reloadLocal })).resolves.toEqual({
      remote: "fulfilled",
      local: "fulfilled",
      completed: true,
    });
    expect(refreshRemote).toHaveBeenCalledTimes(1);
    expect(reloadLocal).toHaveBeenCalledTimes(1);
  });

  it("单侧失败时仍完成另一侧刷新并允许页面恢复", async () => {
    const result = await runFamilyRefresh({
      refreshRemote: vi.fn().mockRejectedValue(new Error("offline")),
      reloadLocal: vi.fn().mockResolvedValue(undefined),
    });

    expect(result).toEqual({ remote: "rejected", local: "fulfilled", completed: true });
  });

  it("合并并发触发并在完成后允许再次刷新", async () => {
    let release!: () => void;
    const pending = new Promise<void>((resolve) => { release = resolve; });
    const refreshRemote = vi.fn(() => pending);
    const reloadLocal = vi.fn().mockResolvedValue(undefined);
    const run = createFamilyRefreshRunner({ refreshRemote, reloadLocal });

    const first = run();
    const second = run();
    expect(second).toBe(first);
    expect(refreshRemote).toHaveBeenCalledTimes(1);
    release();
    await first;
    await run();
    expect(refreshRemote).toHaveBeenCalledTimes(2);
  });

  it("所有已识别的列表、目录和时间线页面均接入统一刷新能力", () => {
    for (const relativePath of REFRESHABLE_LIST_PAGES) {
      const source = readFileSync(path.join(process.cwd(), relativePath), "utf8");
      const directControl = source.includes("refreshControl={<FamilyRefreshControl />}");
      const wrappedList = source.includes("FamilyFlatList as FlatList");
      expect(directControl || wrappedList, relativePath).toBe(true);
    }
  });
});
