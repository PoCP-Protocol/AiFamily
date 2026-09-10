import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  reporter: "list",
  use: {
    baseURL: "http://127.0.0.1:4191",
    trace: "on-first-retry",
  },
  // The family-growth route performs a real auth + assessment HTTP call;
  // starting only Vite would turn a backend outage into a misleading UI test.
  webServer: [
    {
      command: "uv run uvicorn backend.apps.family_api.main:app --host 127.0.0.1 --port 8093",
      url: "http://127.0.0.1:8093/health",
      reuseExistingServer: false,
      env: { AIFAMILY_ENV: "development" },
      cwd: "D:/AiFamily",
    },
    {
      command: "pnpm exec vite --config vite.e2e.config.ts --host 127.0.0.1 --port 4191 --strictPort",
      url: "http://127.0.0.1:4191",
      reuseExistingServer: false,
      env: { AIFAMILY_ENV: "development" },
    },
  ],
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
