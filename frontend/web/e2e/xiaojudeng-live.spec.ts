import { spawn, type ChildProcess } from "node:child_process";
import { writeFile } from "node:fs/promises";
import { createInterface } from "node:readline";
import { tmpdir } from "node:os";
import { resolve } from "node:path";
import { expect, test, type Page } from "@playwright/test";

type SandboxDto = {
  source: "synthetic";
  fixture_only: true;
  state: "LIVE";
  media_session_ref: string;
  playback_url: string;
  control_url: string;
  sha256: string;
};

const webRoot = resolve(import.meta.dirname, "..");
const repoRoot = resolve(webRoot, "../..");
const viteEntrypoint = resolve(webRoot, "node_modules/vite/bin/vite.js");
const pythonExecutable = process.platform === "win32"
  ? resolve(repoRoot, ".venv/Scripts/python.exe")
  : resolve(repoRoot, ".venv/bin/python");
const noProviderUrl = "http://127.0.0.1:4181/";
const mediaUrl = "http://127.0.0.1:4182/";
const mediaBrowserOrigin = "http://127.0.0.1:4173/";
const processes: ChildProcess[] = [];
let sandboxDto: SandboxDto;
let browserMediaDto: SandboxDto;

test.describe.configure({ mode: "serial" });

test.beforeAll(async () => {
  sandboxDto = await startMediaSandbox();
  browserMediaDto = {
    ...sandboxDto,
    playback_url: toBrowserProxyUrl(sandboxDto.playback_url),
    control_url: toBrowserProxyUrl(sandboxDto.control_url),
  };
  const mediaProbe = await fetch(new URL("/health", sandboxDto.control_url));
  if (!mediaProbe.ok) throw new Error(`media sandbox probe failed: ${mediaProbe.status}`);
  await Promise.all([
    startVite(4181),
    startVite(4182, JSON.stringify(browserMediaDto)),
  ]);
});

test.afterAll(async () => {
  for (const child of processes.reverse()) {
    child.kill();
  }
});

test("desktop no-provider stays readable and gives a next step", async ({ page }, testInfo) => {
  await page.goto(noProviderUrl);
  await expect(page.getByRole("heading", { name: "和专家一起，把家庭难题聊明白" })).toBeVisible();
  await expect(page.getByRole("img", { name: "合成专家形象" }).first()).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("desktop-discovery.png"), fullPage: true });

  await page.getByRole("button", { name: "查看直播详情" }).click();
  await expect(page.locator("video")).toHaveCount(0);
  await expect(page.getByText("视频暂不可用")).toBeVisible();
  await expect(page.getByText("视频服务暂未连接，请稍后刷新或返回直播首页。")).toBeVisible();
  await expect(page.getByText("APPROVED")).not.toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("desktop-no-provider.png"), fullPage: true });
});

test("390px mobile discovery, empty search, and detail stay usable", async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(noProviderUrl);

  await expect(page.getByRole("heading", { name: "和专家一起，把家庭难题聊明白" })).toBeVisible();
  await expect(page.getByRole("searchbox", { name: "你想解决什么问题？" })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("mobile-discovery.png"), fullPage: true });

  await page.getByRole("searchbox", { name: "你想解决什么问题？" }).fill("不存在的问题");
  await expect(page.getByText("没有匹配的直播")).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("mobile-empty.png"), fullPage: true });

  await page.getByRole("searchbox", { name: "你想解决什么问题？" }).fill("");
  await page.getByRole("button", { name: "查看直播详情" }).click();
  await expect(page.getByRole("heading", { name: "一个可以马上练习的沟通方法" })).toBeVisible();
  await expect(page.getByText("APPROVED")).not.toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("mobile-detail.png"), fullPage: true });
});

test("desktop media cold-start covers live, disconnect, recover, stop, and revoke", async ({ page }, testInfo) => {
  await installOriginProxy(page, mediaUrl, mediaBrowserOrigin, new URL(sandboxDto.control_url).origin);
  await page.goto(mediaBrowserOrigin);
  expect(await page.evaluate(() => window.location.origin)).toBe("http://127.0.0.1:4173");
  const browserHealth = await page.evaluate(async (controlUrl) => {
    try {
      const response = await fetch(new URL("/health", controlUrl));
      return response.status;
    } catch {
      return 0;
    }
  }, browserMediaDto.control_url);
  expect(browserHealth).toBe(200);

  await expect(page.getByText("小橘灯：家庭沟通中的温柔练习")).toBeVisible();
  await expect(page.getByText("内容已审核").first()).toBeVisible();
  await expect(page.getByText("family-private")).not.toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("desktop-media-discovery.png"), fullPage: true });

  await page.getByRole("button", { name: "进入直播间" }).click();
  await expect(page.locator("video")).toHaveCount(1);
  await expect(page.locator("video")).toHaveAttribute("src", /127\.0\.0\.1/);
  await expect(page.locator("video")).toHaveAttribute("poster", /^data:image\/svg\+xml,/);
  await expect(page.locator("video")).toHaveAttribute("preload", "none");
  await expect(page.locator("video")).not.toHaveAttribute("autoplay");
  await expect(page.getByText("可以播放")).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("desktop-live.png"), fullPage: true });

  await page.getByText("连接演练工具").click();
  await page.getByRole("button", { name: "中断连接" }).click();
  await expect(page.getByText("直播连接中断。")).toBeVisible();
  await expect(page.locator("video")).toHaveCount(0);
  await page.screenshot({ path: testInfo.outputPath("desktop-disconnected.png"), fullPage: true });

  await page.getByRole("button", { name: "重新连接" }).click();
  await expect(page.getByText("可以播放")).toBeVisible();
  await expect(page.locator("video")).toHaveCount(1);
  await page.screenshot({ path: testInfo.outputPath("desktop-recovered.png"), fullPage: true });

  await page.getByRole("button", { name: "结束本场" }).click();
  await expect(page.getByText("本场直播已经停止。")).toBeVisible();
  await expect(page.locator("video")).toHaveCount(0);
  await expect(page.getByText("仅限成人")).toBeVisible();
  await expect(page.getByRole("heading", { name: "需要继续支持？先了解专家服务方式" })).toBeVisible();
  const stoppedOldCapability = await page.request.get(sandboxDto.playback_url);
  expect(stoppedOldCapability.status()).toBe(403);
  await page.screenshot({ path: testInfo.outputPath("desktop-stopped.png"), fullPage: true });

  await page.getByRole("button", { name: "撤回观看权限" }).click();
  await expect(page.getByText("观看权限已经撤回。")).toBeVisible();
  await expect(page.locator("video")).toHaveCount(0);
  const revokedOldCapability = await page.request.get(sandboxDto.playback_url);
  expect(revokedOldCapability.status()).toBe(403);
  await page.getByRole("button", { name: "了解服务方式" }).click();
  await expect(page.getByText("当前仅展示服务说明，不会自动下单、扣费或联系专家。")).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("desktop-revoked.png"), fullPage: true });
  const stateResults = JSON.stringify({
    live: "PASS",
    disconnected: "PASS",
    recovered: "PASS",
    stopped: "PASS",
    stopped_old_url_status: stoppedOldCapability.status(),
    revoked: "PASS",
    revoked_old_url_status: revokedOldCapability.status(),
    adult_only_service_next_step: "PASS",
  }, null, 2);
  await writeFile(testInfo.outputPath("state-results.json"), stateResults, "utf8");
  await testInfo.attach("state-results.json", {
    body: Buffer.from(stateResults),
    contentType: "application/json",
  });
});

async function startMediaSandbox(): Promise<SandboxDto> {
  const child = spawn(
    pythonExecutable,
    [
      "-m",
      "poc.media_adapter_sandbox.replay_harness",
      "--serve",
      "--output",
      resolve(tmpdir(), "xiaojudeng-playwright.mp4"),
      "--duration",
      "3",
      "--ttl",
      "60",
    ],
    { cwd: repoRoot, stdio: ["ignore", "pipe", "pipe"] },
  );
  processes.push(child);
  child.stderr?.resume();
  const line = await readFirstJsonLine(child);
  return JSON.parse(line) as SandboxDto;
}

function toBrowserProxyUrl(actualUrl: string): string {
  const actual = new URL(actualUrl);
  return new URL(`/sandbox-media${actual.pathname}${actual.search}`, mediaBrowserOrigin).toString();
}

async function installOriginProxy(
  page: Page,
  sourceBaseUrl: string,
  browserBaseUrl: string,
  mediaProviderOrigin: string,
): Promise<void> {
  await page.route(`${browserBaseUrl}**`, async (route) => {
    const incoming = new URL(route.request().url());
    const isMediaRequest = incoming.pathname.startsWith("/sandbox-media/");
    const path = isMediaRequest
      ? incoming.pathname.replace("/sandbox-media", "")
      : incoming.pathname;
    const source = new URL(
      `${path}${incoming.search}`,
      isMediaRequest ? mediaProviderOrigin : sourceBaseUrl,
    );
    const response = await route.fetch({ url: source.toString() });
    await route.fulfill({ response });
  });
}

async function startVite(port: number, mediaDto?: string): Promise<void> {
  const env = { ...process.env };
  delete env.VITE_MEDIA_PLAYBACK_DTO;
  if (mediaDto) env.VITE_MEDIA_PLAYBACK_DTO = mediaDto;
  const child = spawn(
    process.execPath,
    [viteEntrypoint, "--host", "127.0.0.1", "--port", String(port), "--strictPort"],
    { cwd: webRoot, env, stdio: ["ignore", "pipe", "pipe"] },
  );
  processes.push(child);
  await waitForUrl(`http://127.0.0.1:${port}/`);
}

async function readFirstJsonLine(child: ChildProcess): Promise<string> {
  if (!child.stdout) throw new Error("media sandbox stdout unavailable");
  const lines = createInterface({ input: child.stdout });
  return await new Promise<string>((resolveLine, reject) => {
    let settled = false;
    const timeout = setTimeout(() => reject(new Error("media sandbox startup timed out")), 15_000);
    child.once("exit", (code) => {
      if (settled) return;
      clearTimeout(timeout);
      reject(new Error(`media sandbox exited before startup: ${code ?? "unknown"}`));
    });
    lines.once("line", (line) => {
      settled = true;
      clearTimeout(timeout);
      resolveLine(line);
    });
  });
}

async function waitForUrl(url: string): Promise<void> {
  const deadline = Date.now() + 15_000;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(url);
      if (response.ok) return;
    } catch {
      // The process is still starting.
    }
    await new Promise((resolveDelay) => setTimeout(resolveDelay, 100));
  }
  throw new Error(`Vite did not start: ${url}`);
}
