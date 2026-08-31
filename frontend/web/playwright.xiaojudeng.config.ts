import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  testMatch: "xiaojudeng-live.spec.ts",
  fullyParallel: false,
  workers: 1,
  reporter: "list",
  outputDir: "test-results/xiaojudeng-isolated",
  use: {
    trace: "on-first-retry",
  },
  projects: [{ name: "xiaojudeng-chromium", use: { ...devices["Desktop Chrome"] } }],
});
