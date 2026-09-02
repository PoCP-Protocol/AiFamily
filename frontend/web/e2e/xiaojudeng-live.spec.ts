import { spawn, type ChildProcess } from "node:child_process";
import { writeFile } from "node:fs/promises";
import { createInterface } from "node:readline";
import { tmpdir } from "node:os";
import { createServer } from "node:net";
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
let questionApiUrl: string;
let browserQuestionApiUrl: string;
let replayApiUrl: string;
const browserReplayApiUrl = "http://127.0.0.1:4173/sandbox-replay";
let commerceApiUrl: string;
const browserCommerceApiUrl = "http://127.0.0.1:4173/sandbox-commerce";
let replayProcess: ChildProcess;
let commerceProcess: ChildProcess;
let commercePort: number;
const replayDatabasePath = resolve(tmpdir(), `xiaojudeng-replay-${Date.now()}.sqlite3`);
const commerceDatabasePath = resolve(tmpdir(), `xiaojudeng-commerce-${Date.now()}.sqlite3`);
const mediaOutputPath = resolve(tmpdir(), `xiaojudeng-playwright-${Date.now()}.mp4`);
const processes: ChildProcess[] = [];
let sandboxDto: SandboxDto;
let browserMediaDto: SandboxDto;

test.describe.configure({ mode: "serial" });

test.beforeAll(async () => {
  const questionPort = await reserveFreePort();
  questionApiUrl = `http://127.0.0.1:${questionPort}`;
  browserQuestionApiUrl = "http://127.0.0.1:4173/sandbox-question";
  await startQuestionSandbox(questionPort);
  sandboxDto = await startMediaSandbox();
  replayProcess = await startReplaySandbox(await reserveFreePort());
  commercePort = await reserveFreePort();
  commerceProcess = await startCommerceSandbox(commercePort);
  browserMediaDto = {
    ...sandboxDto,
    playback_url: toBrowserProxyUrl(sandboxDto.playback_url),
    control_url: toBrowserProxyUrl(sandboxDto.control_url),
  };
  const mediaProbe = await fetch(new URL("/health", sandboxDto.control_url));
  if (!mediaProbe.ok) throw new Error(`media sandbox probe failed: ${mediaProbe.status}`);
  await Promise.all([
    startVite(4181),
    startVite(
      4182,
      JSON.stringify(browserMediaDto),
      browserQuestionApiUrl,
      browserReplayApiUrl,
      browserCommerceApiUrl,
    ),
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

  await page.getByRole("textbox", { name: "向专家提问" }).fill("怎样先听懂再回应？");
  await page.getByRole("button", { name: "提交" }).click();
  await expect(page.getByText("问题已提交，等待人工审核")).toBeVisible();
  await expect(page.getByText("等待人工审核", { exact: true }).last()).toBeVisible();
  await page.getByRole("link", { name: "专家工作台" }).click();
  await expect(page.getByRole("heading", { name: "直播提问审核" })).toBeVisible();
  await expect(page.getByText("怎样先听懂再回应？")).toBeVisible();
  await page.getByRole("button", { name: "批准展示" }).click();
  await expect(page.getByText("当前没有待审核问题")).toBeVisible();
  await page.getByRole("link", { name: "直播首页" }).click();
  await page.getByRole("button", { name: "进入直播间" }).click();
  await expect(page.getByText("家长提问")).toBeVisible();
  await expect(page.getByText("怎样先听懂再回应？")).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("desktop-approved-question.png"), fullPage: true });

  await page.getByText("连接演练工具").click();
  await page.getByRole("button", { name: "结束本场" }).click();
  await expect(page.getByText("本场直播已经停止。")).toBeVisible();
  await expect(page.locator("video")).toHaveCount(0);
  await expect(page.getByText("仅限成人")).toBeVisible();
  await expect(page.getByRole("heading", { name: "需要继续支持？先了解专家服务方式" })).toBeVisible();
  const stoppedOldCapability = await page.request.get(sandboxDto.playback_url);
  expect(stoppedOldCapability.status()).toBe(403);
  await page.screenshot({ path: testInfo.outputPath("desktop-stopped.png"), fullPage: true });

  const browserReplayProbe = await page.evaluate(async ({ baseUrl, headers }) => {
    try {
      const response = await fetch(`${baseUrl}/sandbox/replays/media.synthetic.1`, { headers });
      return { status: response.status, body: await response.text() };
    } catch (error) {
      return { status: 0, body: String(error) };
    }
  }, { baseUrl: browserReplayApiUrl, headers: syntheticActorHeaders() });
  expect(browserReplayProbe.status, browserReplayProbe.body).toBe(200);
  await page.getByRole("button", { name: "播放回看" }).click();
  const replayVideo = page.getByLabel("小橘灯合成直播回看");
  await expect(replayVideo).toBeVisible();
  const replayCapability = await replayVideo.getAttribute("src");
  expect(replayCapability).toContain("capability=");
  const replayBeforeDelete = await page.request.get(replayCapability!);
  expect(replayBeforeDelete.status()).toBe(200);
  await page.screenshot({ path: testInfo.outputPath("desktop-replay.png"), fullPage: true });

  await page.getByRole("button", { name: "删除回看" }).click();
  await expect(page.getByText("回看已删除")).toBeVisible();
  await expect(replayVideo).toHaveCount(0);
  const replayAfterDelete = await page.request.get(replayCapability!);
  expect(replayAfterDelete.status()).toBe(410);
  await page.screenshot({ path: testInfo.outputPath("desktop-replay-deleted.png"), fullPage: true });

  replayProcess.kill();
  replayProcess = await startReplaySandbox(await reserveFreePort());
  const replayAfterRestart = await fetch(`${replayApiUrl}/sandbox/replays/media.synthetic.1`, {
    headers: syntheticActorHeaders(),
  });
  expect(replayAfterRestart.status).toBe(200);
  expect((await replayAfterRestart.json()).state).toBe("DELETED");

  await page.getByRole("button", { name: "撤回观看权限" }).click();
  await expect(page.getByText("观看权限已经撤回。")).toBeVisible();
  await expect(page.locator("video")).toHaveCount(0);
  const revokedOldCapability = await page.request.get(sandboxDto.playback_url);
  expect(revokedOldCapability.status()).toBe(403);
  await page.getByRole("link", { name: "查看服务方案" }).click();
  await expect(page.getByRole("heading", { level: 2, name: "支持这场内容" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "会员权益" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "付费内容" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "预约30分钟真人咨询" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "了解平台积分" })).toBeVisible();
  const purchaseResponsePromise = page.waitForResponse(
    (response) => response.url().endsWith("/sandbox/live-commerce/purchases")
      && response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "支持这场内容（演示）" }).click();
  const purchaseBody = await (await purchaseResponsePromise).json() as { purchase_ref: string };
  await expect(page.getByText("演示记录已创建，没有真实扣款。")).toBeVisible();
  await page.getByRole("button", { name: "撤销演示记录" }).click();
  await expect(page.getByText(/演示记录已撤销/)).toBeVisible();
  await expect(page.getByRole("button", { name: "暂不可预约" })).toBeDisabled();
  await page.screenshot({ path: testInfo.outputPath("desktop-service-offering.png"), fullPage: true });

  commerceProcess.kill();
  await waitForProcessExit(commerceProcess);
  commerceProcess = await startCommerceSandbox(commercePort);
  const persistentBalance = await fetch(
    `${commerceApiUrl}/sandbox/live-commerce/purchases/${encodeURIComponent(purchaseBody.purchase_ref)}/balances`,
    { headers: syntheticActorHeaders() },
  );
  expect(persistentBalance.status).toBe(200);
  const persistentBalanceBody = await persistentBalance.json() as {
    cash: number;
    settlement: number;
    entitlement: string;
  };
  expect(persistentBalanceBody.cash).toBe(0);
  expect(persistentBalanceBody.settlement).toBe(0);
  expect(persistentBalanceBody.entitlement).toBe("REVOKED");
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
    replay: "PASS",
    replay_old_url_after_delete_status: replayAfterDelete.status(),
    replay_after_restart: "DELETED",
    adult_contract_separation: "PASS_SUPPORT_SERVICE_POINTS",
    adult_support_reversal: "PASS_NO_EXTERNAL_EFFECT",
    commerce_restart_balance: persistentBalanceBody,
  }, null, 2);
  await writeFile(testInfo.outputPath("state-results.json"), stateResults, "utf8");
  await testInfo.attach("state-results.json", {
    body: Buffer.from(stateResults),
    contentType: "application/json",
  });
});

test("adult membership remains independent and restart-readable", async ({ page }, testInfo) => {
  await installOriginProxy(page, mediaUrl, mediaBrowserOrigin, new URL(sandboxDto.control_url).origin);
  await page.goto(mediaUrl);
  await page.evaluate(() => localStorage.removeItem("xiaojudeng.sandbox.membership.purchase_ref"));
  await page.goto(`${mediaUrl}#live-service`);
  await expect(page.getByRole("heading", { name: "会员权益" })).toBeVisible();

  const membershipButton = page.getByRole("button", { name: "开通小橘灯会员（演示）" });
  await expect(membershipButton).toBeEnabled();
  const [purchaseResponse] = await Promise.all([
    page.waitForResponse(
      (response) => response.url().includes("/sandbox/live-commerce/purchases")
      && response.request().method() === "POST",
    ),
    membershipButton.click(),
  ]);
  const purchaseBody = await purchaseResponse.json() as {
    purchase_ref: string;
    track: string;
  };
  expect(purchaseBody.track).toBe("MEMBERSHIP");
  expect(purchaseBody.purchase_ref).toMatch(/^membership\.ui\./);
  await expect(page.getByText("会员权益：已开通（演示）")).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("desktop-membership-active.png"), fullPage: true });

  commerceProcess.kill();
  await waitForProcessExit(commerceProcess);
  commerceProcess = await startCommerceSandbox(commercePort);
  await page.reload();
  await expect(page.getByText("会员权益：已开通（演示）")).toBeVisible();
  const activeAfterRestart = await fetch(
    `${commerceApiUrl}/sandbox/live-commerce/purchases/${encodeURIComponent(purchaseBody.purchase_ref)}/balances`,
    { headers: syntheticActorHeaders() },
  );
  expect(activeAfterRestart.status).toBe(200);
  expect((await activeAfterRestart.json()).entitlement).toBe("ACTIVE");

  await page.getByRole("button", { name: "撤销会员演示记录" }).click();
  await expect(page.getByText("会员权益：已撤销（演示）")).toBeVisible();
  commerceProcess.kill();
  await waitForProcessExit(commerceProcess);
  commerceProcess = await startCommerceSandbox(commercePort);
  await page.reload();
  await expect(page.getByText("会员权益：已撤销（演示）")).toBeVisible();
  const revokedAfterRestart = await fetch(
    `${commerceApiUrl}/sandbox/live-commerce/purchases/${encodeURIComponent(purchaseBody.purchase_ref)}/balances`,
    { headers: syntheticActorHeaders() },
  );
  expect(revokedAfterRestart.status).toBe(200);
  const revokedBody = await revokedAfterRestart.json() as {
    cash: number;
    settlement: number;
    entitlement: string;
  };
  expect(revokedBody.cash).toBe(0);
  expect(revokedBody.settlement).toBe(0);
  expect(revokedBody.entitlement).toBe("REVOKED");
  await page.screenshot({ path: testInfo.outputPath("desktop-membership-revoked.png"), fullPage: true });
});

async function startMediaSandbox(): Promise<SandboxDto> {
  const child = spawn(
    pythonExecutable,
    [
      "-m",
      "poc.media_adapter_sandbox.replay_harness",
      "--serve",
      "--output",
      mediaOutputPath,
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
    const isQuestionRequest = incoming.pathname.startsWith("/sandbox-question/");
    const isReplayRequest = incoming.pathname.startsWith("/sandbox-replay/");
    const isCommerceRequest = incoming.pathname.startsWith("/sandbox-commerce/");
    const path = isMediaRequest
      ? incoming.pathname.replace("/sandbox-media", "")
      : isQuestionRequest
        ? incoming.pathname.replace("/sandbox-question", "")
        : isReplayRequest
          ? incoming.pathname.replace("/sandbox-replay", "")
        : isCommerceRequest
          ? incoming.pathname.replace("/sandbox-commerce", "")
        : incoming.pathname;
    const source = new URL(
      `${path}${incoming.search}`,
      isMediaRequest
        ? mediaProviderOrigin
        : isQuestionRequest
          ? questionApiUrl
          : isReplayRequest
            ? replayApiUrl
            : isCommerceRequest
              ? commerceApiUrl
            : sourceBaseUrl,
    );
    const response = await route.fetch({ url: source.toString() });
    await route.fulfill({ response });
  });
}

async function startVite(
  port: number,
  mediaDto?: string,
  interactionBaseUrl?: string,
  replayBaseUrl?: string,
  commerceBaseUrl?: string,
): Promise<void> {
  const env = { ...process.env };
  delete env.VITE_MEDIA_PLAYBACK_DTO;
  if (mediaDto) env.VITE_MEDIA_PLAYBACK_DTO = mediaDto;
  if (interactionBaseUrl) env.VITE_LIVE_INTERACTION_BASE_URL = interactionBaseUrl;
  if (replayBaseUrl) env.VITE_LIVE_REPLAY_BASE_URL = replayBaseUrl;
  if (commerceBaseUrl) env.VITE_LIVE_COMMERCE_BASE_URL = commerceBaseUrl;
  const child = spawn(
    process.execPath,
    [viteEntrypoint, "--host", "127.0.0.1", "--port", String(port), "--strictPort"],
    { cwd: webRoot, env, stdio: ["ignore", "pipe", "pipe"] },
  );
  processes.push(child);
  await waitForUrl(`http://127.0.0.1:${port}/`);
}

async function startCommerceSandbox(port: number): Promise<ChildProcess> {
  commerceApiUrl = `http://127.0.0.1:${port}`;
  const child = spawn(
    pythonExecutable,
    [
      "-m",
      "poc.standalone_live_commerce_sandbox.commerce_api",
      "--serve",
      "--database",
      commerceDatabasePath,
      "--port",
      String(port),
    ],
    { cwd: repoRoot, stdio: ["ignore", "pipe", "pipe"] },
  );
  processes.push(child);
  child.stdout?.resume();
  child.stderr?.resume();
  await waitForUrl(`${commerceApiUrl}/health`);
  return child;
}

async function startReplaySandbox(port: number): Promise<ChildProcess> {
  replayApiUrl = `http://127.0.0.1:${port}`;
  const child = spawn(
    pythonExecutable,
    [
      "-m",
      "poc.standalone_live_replay_sandbox.replay_api",
      "--serve",
      "--database",
      replayDatabasePath,
      "--media",
      mediaOutputPath,
      "--port",
      String(port),
    ],
    { cwd: repoRoot, stdio: ["ignore", "pipe", "pipe"] },
  );
  processes.push(child);
  child.stdout?.resume();
  child.stderr?.resume();
  await waitForUrl(`${replayApiUrl}/health`);
  return child;
}

function syntheticActorHeaders(): Record<string, string> {
  return {
    "X-Sandbox-Source": "SANDBOX_SYNTHETIC",
    "X-Fixture-Only": "true",
    "X-Tenant-Id": "tenant.synthetic.alpha",
    "X-Family-Id": "family.synthetic.alpha",
    "X-Actor-Id": "actor.synthetic.adult",
    "X-Actor-Role": "ADULT_VIEWER",
  };
}

async function startQuestionSandbox(port: number): Promise<void> {
  const child = spawn(
    pythonExecutable,
    [
      "-m",
      "poc.standalone_live_moderation_sandbox.question_api",
      "--serve",
      "--database",
      resolve(tmpdir(), `xiaojudeng-questions-${Date.now()}.sqlite3`),
      "--port",
      String(port),
    ],
    { cwd: repoRoot, stdio: ["ignore", "pipe", "pipe"] },
  );
  processes.push(child);
  child.stdout?.resume();
  child.stderr?.resume();
  await waitForUrl(`${questionApiUrl}/health`);
}

async function reserveFreePort(): Promise<number> {
  const server = createServer();
  return await new Promise<number>((resolvePort, reject) => {
    server.once("error", reject);
    server.listen(0, "127.0.0.1", () => {
      const address = server.address();
      if (!address || typeof address === "string") {
        server.close();
        reject(new Error("unable to reserve question sandbox port"));
        return;
      }
      server.close(() => resolvePort(address.port));
    });
  });
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

async function waitForProcessExit(child: ChildProcess): Promise<void> {
  if (child.exitCode !== null || child.signalCode !== null) return;
  await new Promise<void>((resolveExit, reject) => {
    const timeout = setTimeout(() => reject(new Error("sandbox shutdown timed out")), 10_000);
    child.once("exit", () => {
      clearTimeout(timeout);
      resolveExit();
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
