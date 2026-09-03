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
let replayKnowledgeApiUrl: string;
const browserReplayKnowledgeApiUrl = "http://127.0.0.1:4173/sandbox-replay-knowledge";
let commerceApiUrl: string;
const browserCommerceApiUrl = "http://127.0.0.1:4173/sandbox-commerce";
let observabilityApiUrl: string;
const browserObservabilityApiUrl = "http://127.0.0.1:4173/sandbox-observability";
let controlApiUrl: string;
const browserControlApiUrl = "http://127.0.0.1:4173/sandbox-control";
let aiApiUrl: string;
const browserAiApiUrl = "http://127.0.0.1:4173/sandbox-ai";
let incidentApiUrl: string;
const browserIncidentApiUrl = "http://127.0.0.1:4173/sandbox-incident";
let replayProcess: ChildProcess;
let replayPort: number;
let replayKnowledgeProcess: ChildProcess;
let replayKnowledgePort: number;
let commerceProcess: ChildProcess;
let commercePort: number;
const replayDatabasePath = resolve(tmpdir(), `xiaojudeng-replay-${Date.now()}.sqlite3`);
const replayKnowledgeDatabasePath = resolve(tmpdir(), `xiaojudeng-replay-knowledge-${Date.now()}.sqlite3`);
const commerceDatabasePath = resolve(tmpdir(), `xiaojudeng-commerce-${Date.now()}.sqlite3`);
const mediaOutputPath = resolve(tmpdir(), `xiaojudeng-playwright-${Date.now()}.mp4`);
const controlDatabasePath = resolve(tmpdir(), `xiaojudeng-control-${Date.now()}.sqlite3`);
const aiDatabasePath = resolve(tmpdir(), `xiaojudeng-ai-${Date.now()}.sqlite3`);
const incidentDatabasePath = resolve(tmpdir(), `xiaojudeng-incident-${Date.now()}.sqlite3`);
const processes: ChildProcess[] = [];
let sandboxDto: SandboxDto;
let browserMediaDto: SandboxDto;

test.describe.configure({ mode: "serial" });
test.use({
  launchOptions: {
    args: [
      "--disable-features=LocalNetworkAccessChecks",
      "--use-fake-device-for-media-stream",
      "--use-fake-ui-for-media-stream",
    ],
  },
});

test.beforeAll(async () => {
  const questionPort = await reserveFreePort();
  questionApiUrl = `http://127.0.0.1:${questionPort}`;
  browserQuestionApiUrl = "http://127.0.0.1:4173/sandbox-question";
  await startQuestionSandbox(questionPort);
  sandboxDto = await startMediaSandbox();
  await startControlSandbox(await reserveFreePort());
  await startAiSandbox(await reserveFreePort());
  await startIncidentSandbox(await reserveFreePort());
  commercePort = await reserveFreePort();
  commerceProcess = await startCommerceSandbox(commercePort);
  replayPort = await reserveFreePort();
  replayProcess = await startReplaySandbox(replayPort);
  replayKnowledgePort = await reserveFreePort();
  replayKnowledgeProcess = await startReplayKnowledgeSandbox(replayKnowledgePort, true);
  await startObservabilitySandbox(await reserveFreePort());
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
      questionApiUrl.replace("http://", "ws://"),
      browserReplayApiUrl,
      browserReplayKnowledgeApiUrl,
      browserCommerceApiUrl,
      browserObservabilityApiUrl,
      browserControlApiUrl,
      browserAiApiUrl,
      browserIncidentApiUrl,
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
  test.setTimeout(60_000);
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
  await page.getByRole("button", { name: "开始播放" }).click();
  await expect.poll(async () => page.locator("video").evaluate((video) => video.readyState)).toBeGreaterThanOrEqual(2);
  await expect.poll(async () => page.locator("video").evaluate((video) => video.currentTime)).toBeGreaterThan(0);
  await expect(page.locator("video")).toHaveJSProperty("paused", false);
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
  await expect(page.getByText("实时", { exact: true })).toBeVisible();
  const moderatorPage = await page.context().newPage();
  await installOriginProxy(
    moderatorPage,
    mediaUrl,
    mediaBrowserOrigin,
    new URL(sandboxDto.control_url).origin,
  );
  await moderatorPage.goto(`${mediaUrl}#live-ops`);
  await expect(moderatorPage.getByRole("heading", { name: "直播提问审核" })).toBeVisible();
  await expect(moderatorPage.getByText("怎样先听懂再回应？")).toBeVisible();
  await moderatorPage.getByRole("button", { name: "批准展示" }).click();
  await expect(moderatorPage.getByText("当前没有待审核问题")).toBeVisible();
  await moderatorPage.close();
  await expect(page.getByText("家长提问")).toBeVisible();
  await expect(page.getByText("怎样先听懂再回应？")).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("desktop-approved-question.png"), fullPage: true });

  await expect(page.getByRole("button", { name: "结束本场" })).toBeVisible();
  await page.getByRole("button", { name: "结束本场" }).click();
  await expect(page.getByText("本场直播已经停止。")).toBeVisible();
  await expect(page.locator("video")).toHaveCount(0);
  await expect(page.getByText("仅限成人", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "需要继续支持？先了解专家服务方式" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "把一场直播，留下能反复用的方法" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "把冲突变成一次共同练习" })).toBeVisible();
  await expect(page.getByText("先听懂情绪")).toBeVisible();
  await expect(page.getByText("最后约定一步")).toBeVisible();
  await page.getByRole("button", { name: "收藏这张知识卡" }).click();
  await expect(page.getByRole("button", { name: "已收藏到家庭笔记" })).toBeDisabled();
  const stoppedOldCapability = await page.request.get(sandboxDto.playback_url);
  expect(stoppedOldCapability.status()).toBe(403);
  await page.screenshot({ path: testInfo.outputPath("desktop-stopped.png"), fullPage: true });

  const replayPurchaseResponse = page.waitForResponse(
    (response) => response.url().endsWith("/sandbox/live-commerce/purchases")
      && response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "解锁并播放回看（演示）" }).click();
  const replayPurchase = await (await replayPurchaseResponse).json() as {
    purchase_ref: string;
    track: string;
  };
  expect(replayPurchase.track).toBe("MEDIA_ENTITLEMENT");
  const replayVideo = page.getByLabel("小橘灯合成直播回看");
  await expect(replayVideo).toBeVisible();
  const replayCapability = await replayVideo.getAttribute("src");
  expect(replayCapability).toContain("capability=");
  const replayBeforeDelete = await page.request.get(replayCapability!);
  expect(replayBeforeDelete.status()).toBe(200);
  await page.screenshot({ path: testInfo.outputPath("desktop-replay.png"), fullPage: true });

  await page.getByRole("button", { name: "撤销回看权益" }).click();
  await expect(page.getByText("回看权益已撤销")).toBeVisible();
  await expect(replayVideo).toHaveCount(0);
  const replayAfterEntitlementRevoke = await page.request.get(replayCapability!);
  expect(replayAfterEntitlementRevoke.status()).toBe(403);
  await page.screenshot({ path: testInfo.outputPath("desktop-replay-revoked.png"), fullPage: true });

  commerceProcess.kill();
  replayProcess.kill();
  await Promise.all([waitForProcessExit(commerceProcess), waitForProcessExit(replayProcess)]);
  commerceProcess = await startCommerceSandbox(commercePort);
  replayProcess = await startReplaySandbox(replayPort);
  const replayBalanceAfterRestart = await fetch(
    `${commerceApiUrl}/sandbox/live-commerce/purchases/${encodeURIComponent(replayPurchase.purchase_ref)}/balances`,
    { headers: syntheticActorHeaders() },
  );
  expect(replayBalanceAfterRestart.status).toBe(200);
  expect((await replayBalanceAfterRestart.json()).entitlement).toBe("REVOKED");
  const replayOldUrlAfterRestart = await page.request.get(replayCapability!);
  expect(replayOldUrlAfterRestart.status()).toBe(403);

  const replayDeletion = await fetch(`${replayApiUrl}/sandbox/replays/media.synthetic.1/delete`, {
    method: "POST",
    headers: { ...syntheticActorHeaders(), "Content-Type": "application/json" },
    body: JSON.stringify({
      deletion_ref: "replay-deletion.e2e",
      idempotency_key: "replay-deletion.e2e",
      reason: "adult requested sandbox replay deletion",
    }),
  });
  expect(replayDeletion.status).toBe(200);
  const replayAfterDelete = await page.request.get(replayCapability!);
  expect(replayAfterDelete.status()).toBe(410);
  replayKnowledgeProcess.kill();
  await waitForProcessExit(replayKnowledgeProcess);
  replayKnowledgeProcess = await startReplayKnowledgeSandbox(replayKnowledgePort, false);
  const knowledgeAfterRestart = await fetch(
    `${replayKnowledgeApiUrl}/sandbox/replay-knowledge/replays/media.synthetic.1/knowledge`,
    { headers: syntheticActorHeaders() },
  );
  expect(knowledgeAfterRestart.status).toBe(410);
  await page.reload();
  await page.getByRole("button", { name: "进入直播间" }).click();
  await page.getByText("连接演练工具").click();
  await page.getByRole("button", { name: "结束本场" }).click();
  await expect(page.getByText("回放与衍生章节已删除，刷新或重启后不会恢复。")).toBeVisible();
  await expect(page.getByRole("heading", { name: "把冲突变成一次共同练习" })).toHaveCount(0);
  await page.screenshot({ path: testInfo.outputPath("desktop-replay-deleted.png"), fullPage: true });

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
    replay_entitlement: "REVOKED",
    replay_old_url_after_entitlement_revoke_status: replayAfterEntitlementRevoke.status(),
    replay_old_url_after_restart_status: replayOldUrlAfterRestart.status(),
    replay_old_url_after_delete_status: replayAfterDelete.status(),
    replay_after_restart: "REVOKED_THEN_DELETED",
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

test("adult points support preserves expert settlement across restart and reversal", async ({ page }, testInfo) => {
  await installOriginProxy(page, mediaUrl, mediaBrowserOrigin, new URL(sandboxDto.control_url).origin);
  await page.goto(mediaUrl);
  await page.evaluate(() => localStorage.removeItem("xiaojudeng.sandbox.points.purchase_ref"));
  await page.goto(`${mediaUrl}#live-service`);

  const pointsButton = page.getByRole("button", { name: "使用 100 积分支持专家（演示）" });
  const [purchaseResponse] = await Promise.all([
    page.waitForResponse(
      (response) => response.url().endsWith("/sandbox/live-commerce/purchases")
        && response.request().method() === "POST",
    ),
    pointsButton.click(),
  ]);
  const purchaseBody = await purchaseResponse.json() as { purchase_ref: string; track: string };
  expect(purchaseBody.track).toBe("POINTS");
  expect(purchaseBody.purchase_ref).toMatch(/^points-support\.ui\./);
  await expect(page.getByText("积分支持：已记录（演示）")).toBeVisible();
  await expect(page.getByText(/专家 80 积分/)).toBeVisible();
  await expect(page.getByText(/平台 20 积分/)).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("desktop-points-active.png"), fullPage: true });

  commerceProcess.kill();
  await waitForProcessExit(commerceProcess);
  commerceProcess = await startCommerceSandbox(commercePort);
  await page.reload();
  await expect(page.getByText("积分支持：已记录（演示）")).toBeVisible();
  const settlementAfterRestart = await fetch(
    `${commerceApiUrl}/sandbox/live-commerce/purchases/${encodeURIComponent(purchaseBody.purchase_ref)}/settlements`,
    { headers: syntheticActorHeaders() },
  );
  expect(settlementAfterRestart.status).toBe(200);
  const activeSettlement = await settlementAfterRestart.json() as {
    beneficiaries: Array<{ beneficiary_ref: string; net_amount: number }>;
    total: number;
  };
  expect(activeSettlement.total).toBe(100);
  expect(activeSettlement.beneficiaries).toEqual([
    { beneficiary_ref: "expert.synthetic.1", net_amount: 80 },
    { beneficiary_ref: "platform:aifamily", net_amount: 20 },
  ]);

  await page.getByRole("button", { name: "撤销积分支持" }).click();
  await expect(page.getByText("积分支持已撤销：现金 ¥0.00，专家与平台待结算均为 0。")).toBeVisible();
  commerceProcess.kill();
  await waitForProcessExit(commerceProcess);
  commerceProcess = await startCommerceSandbox(commercePort);
  const [balanceAfterRestart, settlementAfterReversal] = await Promise.all([
    fetch(
      `${commerceApiUrl}/sandbox/live-commerce/purchases/${encodeURIComponent(purchaseBody.purchase_ref)}/balances`,
      { headers: syntheticActorHeaders() },
    ),
    fetch(
      `${commerceApiUrl}/sandbox/live-commerce/purchases/${encodeURIComponent(purchaseBody.purchase_ref)}/settlements`,
      { headers: syntheticActorHeaders() },
    ),
  ]);
  expect(balanceAfterRestart.status).toBe(200);
  expect(settlementAfterReversal.status).toBe(200);
  expect(await balanceAfterRestart.json()).toMatchObject({
    cash: 0,
    settlement: 0,
    entitlement: "REVOKED",
  });
  expect(await settlementAfterReversal.json()).toMatchObject({
    entitlement: "REVOKED",
    total: 0,
  });
  await page.reload();
  await expect(page.getByText("积分支持已撤销：现金 ¥0.00，专家与平台待结算均为 0。")).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("desktop-points-revoked.png"), fullPage: true });
});

test("expert settlement requires a human finance decision and survives restart", async ({ page }, testInfo) => {
  await installOriginProxy(page, mediaUrl, mediaBrowserOrigin, new URL(sandboxDto.control_url).origin);
  await page.goto(`${mediaUrl}#live-service`);
  await page.evaluate(() => localStorage.removeItem("xiaojudeng.sandbox.content_support.purchase_ref"));
  await page.reload();
  await page.getByRole("button", { name: "支持这场内容（演示）" }).click();
  await expect(page.getByText("演示记录已创建，没有真实扣款。")).toBeVisible();

  await page.getByRole("link", { name: "专家工作台" }).click();
  await expect(page.getByRole("heading", { name: "专家结算审核" })).toBeVisible();
  await page.getByRole("button", { name: "申请最近一笔专家结算（演示）" }).click();
  await expect(page.getByText("等待人工审批")).toBeVisible();
  await expect(page.getByText("专家待结算 ¥4.00")).toBeVisible();
  await expect(page.getByText("付款状态：未执行")).toBeVisible();

  await page.getByRole("button", { name: "批准结算" }).click();
  await expect(page.getByText("已批准，等待外部付款系统（未执行）")).toBeVisible();
  await expect(page.getByText("审核理由：人工核对合成结算与原始支持记录一致")).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("desktop-settlement-approved.png"), fullPage: true });

  commerceProcess.kill();
  await waitForProcessExit(commerceProcess);
  commerceProcess = await startCommerceSandbox(commercePort);
  await page.reload();
  await expect(page.getByText("已批准，等待外部付款系统（未执行）")).toBeVisible();
  await expect(page.getByText("付款状态：未执行")).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("desktop-settlement-restart.png"), fullPage: true });
});

test("runtime observability degrades visibly and recovers after provider restart", async ({ page }, testInfo) => {
  await installOriginProxy(page, mediaUrl, mediaBrowserOrigin, new URL(sandboxDto.control_url).origin);
  await page.goto(`${mediaUrl}#live-ops`);
  await expect(page.getByRole("heading", { name: "直播运行状态" })).toBeVisible();
  await expect(page.getByText("READY", { exact: true })).toBeVisible();
  await expect(page.getByText("视频媒体")).toBeVisible();
  await expect(page.getByText("成人互动与审核")).toBeVisible();
  await expect(page.getByText("录制回放")).toBeVisible();
  await expect(page.getByText("交易与权益")).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("desktop-runtime-ready.png"), fullPage: true });

  commerceProcess.kill();
  await waitForProcessExit(commerceProcess);
  await page.getByRole("button", { name: "重新检查运行状态" }).click();
  await expect(page.getByText("DEGRADED", { exact: true })).toBeVisible();
  const commerceCard = page.getByText("交易与权益").locator("..");
  await expect(commerceCard.getByText(/provider unreachable or timed out/)).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("desktop-runtime-degraded.png"), fullPage: true });

  commerceProcess = await startCommerceSandbox(commercePort);
  await page.getByRole("button", { name: "重新检查运行状态" }).click();
  await expect(page.getByText("READY", { exact: true })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("desktop-runtime-recovered.png"), fullPage: true });
});

test("adult report waits for a human moderator stop decision", async ({ page }, testInfo) => {
  await installOriginProxy(page, mediaUrl, mediaBrowserOrigin, new URL(sandboxDto.control_url).origin);
  await page.goto(`${mediaUrl}#live-home`);
  await page.getByRole("button", { name: "进入直播间" }).click();
  await page.getByRole("button", { name: "举报本场直播" }).click();
  await expect(page.getByRole("button", { name: "已提交人工安全审核" })).toBeVisible();
  await page.getByRole("link", { name: "专家工作台" }).click();
  await expect(page.getByRole("heading", { name: "直播安全事件" })).toBeVisible();
  await expect(page.getByText("成人请求人工核对本场直播内容")).toBeVisible();
  await page.getByRole("button", { name: "人工停播" }).click();
  await expect(page.getByText("当前没有待处理举报")).toBeVisible();
  await page.getByRole("link", { name: "直播首页" }).click();
  await expect(page.getByText("暂无直播")).toBeVisible();
  await expect(page.getByRole("button", { name: "进入直播间" })).toHaveCount(0);
  await page.screenshot({ path: testInfo.outputPath("desktop-human-incident-stop.png"), fullPage: true });
});

test("content safety withdrawal removes the live session from family discovery", async ({ page }, testInfo) => {
  await installOriginProxy(page, mediaUrl, mediaBrowserOrigin, new URL(sandboxDto.control_url).origin);
  await requireOk(fetch(
    `${controlApiUrl}/sandbox/live-control/sessions/${sandboxDto.media_session_ref}/review`,
    {
      method: "POST",
      headers: { ...syntheticHeaders("CONTENT_REVIEWER"), "Content-Type": "application/json" },
      body: JSON.stringify({
        decision_key: "e2e-withdraw-live-session",
        action: "WITHDRAW",
        reason: "人工撤回合成直播演练",
        review_ref: "review.synthetic.withdrawn",
      }),
    },
  ));
  await page.goto(`${mediaUrl}#live-home`);
  await expect(page.getByText("暂无直播")).toBeVisible();
  await expect(page.getByText("当前没有可展示的专家直播。")).toBeVisible();
  await expect(page.getByRole("button", { name: "进入直播间" })).toHaveCount(0);
  await page.screenshot({ path: testInfo.outputPath("desktop-control-withdrawn.png"), fullPage: true });
});

test("creator and human operators can run a complete session lifecycle in the UI", async ({ page }, testInfo) => {
  await installOriginProxy(page, mediaUrl, mediaBrowserOrigin, new URL(sandboxDto.control_url).origin);
  await page.goto(`${mediaUrl}#live-ops`);
  await expect(page.getByRole("heading", { name: "直播场次控制台" })).toBeVisible();
  await page.getByRole("button", { name: "创建新的演示场次" }).click();
  await expect(page.getByText("场次草稿已创建，等待人工内容审核。")).toBeVisible();
  const sessionCard = page.getByRole("article", {
    name: "直播场次 小橘灯：把冲突变成一次共同练习",
  });
  await sessionCard.getByRole("button", { name: "人工审核通过" }).click();
  await expect(page.getByText("人工审核完成，可以由运营开播。")).toBeVisible();
  await expect(sessionCard.getByRole("button", { name: "开始直播" })).toBeDisabled();
  await page.getByRole("button", { name: "检查摄像头和麦克风" }).click();
  await expect(page.getByText("摄像头和麦克风已就绪，可以开播。")).toBeVisible();
  await expect(page.getByText("WebRTC 低延迟通道已建立。")).toBeVisible();
  const viewerVideo = page.getByLabel("本地 WebRTC 观众画面");
  await expect(viewerVideo).toBeVisible();
  await expect.poll(async () => viewerVideo.evaluate((video: HTMLVideoElement) => ({
    audioTracks: (video.srcObject as MediaStream | null)?.getAudioTracks().length ?? 0,
    hasVideoFrame: video.videoWidth > 0,
    videoTracks: (video.srcObject as MediaStream | null)?.getVideoTracks().length ?? 0,
  }))).toEqual({ audioTracks: 1, hasVideoFrame: true, videoTracks: 1 });
  await expect(sessionCard.getByRole("button", { name: "开始直播" })).toBeEnabled();
  await sessionCard.getByRole("button", { name: "开始直播" }).click();
  await expect(page.getByText("直播已开始，符合范围的家庭可以发现。")).toBeVisible();
  await sessionCard.getByRole("button", { name: "人工停止直播" }).click();
  await expect(page.getByText("直播已人工停止，家庭入口已撤回。")).toBeVisible();
  await expect(page.getByText("WebRTC 通道已停止。")).toBeVisible();
  await expect(page.getByLabel("本地 WebRTC 观众画面")).toHaveCount(0);
  await expect(sessionCard.getByText("APPROVED · WITHDRAWN")).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("desktop-creator-lifecycle.png"), fullPage: true });
});

test("synthetic transcript becomes an AI draft only after human review", async ({ page }, testInfo) => {
  await installOriginProxy(page, mediaUrl, mediaBrowserOrigin, new URL(sandboxDto.control_url).origin);
  await page.goto(`${mediaUrl}#live-ops`);
  await expect(page.getByRole("heading", { name: "直播内容助手" })).toBeVisible();
  await page.getByRole("button", { name: "生成 AI 草案" }).click();
  await expect(page.getByLabel("AI 直播草案")).toBeVisible();
  await expect(page.getByText("DRAFT", { exact: true })).toBeVisible();
  await expect(page.getByText("问题场景", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "人工编辑后保留" }).click();
  await expect(page.getByText("EDITED_DRAFT", { exact: true })).toBeVisible();
  await expect(page.getByText("人工复核已记录，结果仍不是家庭事实。")).toBeVisible();
  await expect(page.getByText(/不写家庭事实/)).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("desktop-ai-human-gate.png"), fullPage: true });
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
    const isReplayKnowledgeRequest = incoming.pathname.startsWith("/sandbox-replay-knowledge/");
    const isCommerceRequest = incoming.pathname.startsWith("/sandbox-commerce/");
    const isObservabilityRequest = incoming.pathname.startsWith("/sandbox-observability/");
    const isControlRequest = incoming.pathname.startsWith("/sandbox-control/");
    const isAiRequest = incoming.pathname.startsWith("/sandbox-ai/");
    const isIncidentRequest = incoming.pathname.startsWith("/sandbox-incident/");
    const path = isMediaRequest
      ? incoming.pathname.replace("/sandbox-media", "")
      : isQuestionRequest
        ? incoming.pathname.replace("/sandbox-question", "")
      : isReplayRequest
        ? incoming.pathname.replace("/sandbox-replay", "")
      : isReplayKnowledgeRequest
        ? incoming.pathname.replace("/sandbox-replay-knowledge", "")
        : isCommerceRequest
          ? incoming.pathname.replace("/sandbox-commerce", "")
        : isObservabilityRequest
          ? incoming.pathname.replace("/sandbox-observability", "")
        : isControlRequest
          ? incoming.pathname.replace("/sandbox-control", "")
        : isAiRequest
          ? incoming.pathname.replace("/sandbox-ai", "")
        : isIncidentRequest
          ? incoming.pathname.replace("/sandbox-incident", "")
        : incoming.pathname;
    const source = new URL(
      `${path}${incoming.search}`,
      isMediaRequest
        ? mediaProviderOrigin
        : isQuestionRequest
          ? questionApiUrl
        : isReplayRequest
          ? replayApiUrl
        : isReplayKnowledgeRequest
          ? replayKnowledgeApiUrl
            : isCommerceRequest
              ? commerceApiUrl
            : isObservabilityRequest
              ? observabilityApiUrl
            : isControlRequest
              ? controlApiUrl
            : isAiRequest
              ? aiApiUrl
            : isIncidentRequest
              ? incidentApiUrl
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
  interactionWsUrl?: string,
  replayBaseUrl?: string,
  replayKnowledgeBaseUrl?: string,
  commerceBaseUrl?: string,
  observabilityBaseUrl?: string,
  controlBaseUrl?: string,
  aiBaseUrl?: string,
  incidentBaseUrl?: string,
): Promise<void> {
  const env = { ...process.env };
  delete env.VITE_MEDIA_PLAYBACK_DTO;
  if (mediaDto) env.VITE_MEDIA_PLAYBACK_DTO = mediaDto;
  if (interactionBaseUrl) env.VITE_LIVE_INTERACTION_BASE_URL = interactionBaseUrl;
  if (interactionWsUrl) env.VITE_LIVE_INTERACTION_WS_URL = interactionWsUrl;
  if (replayBaseUrl) env.VITE_LIVE_REPLAY_BASE_URL = replayBaseUrl;
  if (replayKnowledgeBaseUrl) env.VITE_LIVE_REPLAY_KNOWLEDGE_BASE_URL = replayKnowledgeBaseUrl;
  if (commerceBaseUrl) env.VITE_LIVE_COMMERCE_BASE_URL = commerceBaseUrl;
  if (observabilityBaseUrl) env.VITE_LIVE_OBSERVABILITY_BASE_URL = observabilityBaseUrl;
  if (controlBaseUrl) env.VITE_LIVE_CONTROL_BASE_URL = controlBaseUrl;
  if (aiBaseUrl) env.VITE_LIVE_AI_BASE_URL = aiBaseUrl;
  if (incidentBaseUrl) env.VITE_LIVE_INCIDENT_BASE_URL = incidentBaseUrl;
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
      "--commerce-base-url",
      commerceApiUrl,
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

async function startReplayKnowledgeSandbox(port: number, seed: boolean): Promise<ChildProcess> {
  replayKnowledgeApiUrl = `http://127.0.0.1:${port}`;
  const args = [
    "-m",
    "poc.standalone_live_replay_sandbox.knowledge_api",
    "--serve",
    "--database",
    replayKnowledgeDatabasePath,
    "--replay-database",
    replayDatabasePath,
    "--replay-ref",
    "media.synthetic.1",
    "--port",
    String(port),
  ];
  if (seed) args.push("--seed-approved-fixture");
  const child = spawn(pythonExecutable, args, {
    cwd: repoRoot,
    stdio: ["ignore", "pipe", "pipe"],
  });
  processes.push(child);
  child.stdout?.resume();
  child.stderr?.resume();
  await waitForUrl(`${replayKnowledgeApiUrl}/health`);
  return child;
}

async function startObservabilitySandbox(port: number): Promise<ChildProcess> {
  observabilityApiUrl = `http://127.0.0.1:${port}`;
  const child = spawn(
    pythonExecutable,
    [
      "-m",
      "poc.standalone_live_observability_sandbox.health_api",
      "--media-url",
      new URL(sandboxDto.control_url).origin,
      "--interaction-url",
      questionApiUrl,
      "--replay-url",
      replayApiUrl,
      "--commerce-url",
      commerceApiUrl,
      "--port",
      String(port),
    ],
    { cwd: repoRoot, stdio: ["ignore", "pipe", "pipe"] },
  );
  processes.push(child);
  child.stdout?.resume();
  child.stderr?.resume();
  await waitForUrl(`${observabilityApiUrl}/health`);
  return child;
}

async function startControlSandbox(port: number): Promise<void> {
  controlApiUrl = `http://127.0.0.1:${port}`;
  const child = spawn(
    pythonExecutable,
    [
      "-m",
      "poc.standalone_live_control_sandbox.session_api",
      "--serve",
      "--database",
      controlDatabasePath,
      "--port",
      String(port),
    ],
    { cwd: repoRoot, stdio: ["ignore", "pipe", "pipe"] },
  );
  processes.push(child);
  child.stdout?.resume();
  child.stderr?.resume();
  await waitForUrl(`${controlApiUrl}/health`);
  const now = Date.now();
  await requireOk(fetch(`${controlApiUrl}/sandbox/live-control/sessions`, {
    method: "POST",
    headers: { ...syntheticHeaders("CREATOR"), "Content-Type": "application/json" },
    body: JSON.stringify({
      session_ref: sandboxDto.media_session_ref,
      idempotency_key: "e2e-create-live-session",
      title: "小橘灯：家庭沟通中的温柔练习",
      speaker: "小橘灯老师",
      expert_summary: "围绕家庭沟通中的具体场景，练习可核对、可暂停的表达方式。",
      applicable_scope: "家长与照护者",
      problem_tags: ["家庭沟通", "照护者"],
      starts_at: new Date(now - 60_000).toISOString(),
      ends_at: new Date(now + 3_600_000).toISOString(),
      audience_scope: "FAMILY",
    }),
  }));
  await requireOk(fetch(
    `${controlApiUrl}/sandbox/live-control/sessions/${sandboxDto.media_session_ref}/review`,
    {
      method: "POST",
      headers: { ...syntheticHeaders("CONTENT_REVIEWER"), "Content-Type": "application/json" },
      body: JSON.stringify({
        decision_key: "e2e-approve-live-session",
        action: "APPROVE",
        reason: "人工确认合成直播内容适合成年家庭成员",
        review_ref: "review.synthetic.e2e",
      }),
    },
  ));
  await requireOk(fetch(
    `${controlApiUrl}/sandbox/live-control/sessions/${sandboxDto.media_session_ref}/lifecycle`,
    {
      method: "POST",
      headers: { ...syntheticHeaders("LIVE_OPERATOR"), "Content-Type": "application/json" },
      body: JSON.stringify({
        action_key: "e2e-start-live-session",
        action: "GO_LIVE",
        reason: "人工确认合成媒体已准备",
      }),
    },
  ));
}

async function startAiSandbox(port: number): Promise<void> {
  aiApiUrl = `http://127.0.0.1:${port}`;
  const child = spawn(
    pythonExecutable,
    [
      "-m",
      "poc.standalone_live_ai_sandbox.ai_api",
      "--serve",
      "--database",
      aiDatabasePath,
      "--port",
      String(port),
    ],
    { cwd: repoRoot, stdio: ["ignore", "pipe", "pipe"] },
  );
  processes.push(child);
  child.stdout?.resume();
  child.stderr?.resume();
  await waitForUrl(`${aiApiUrl}/health`);
}

async function startIncidentSandbox(port: number): Promise<void> {
  incidentApiUrl = `http://127.0.0.1:${port}`;
  const child = spawn(
    pythonExecutable,
    [
      "-m",
      "poc.standalone_live_moderation_sandbox.incident_api",
      "--serve",
      "--database",
      incidentDatabasePath,
      "--port",
      String(port),
      "--control-base-url",
      controlApiUrl,
      "--media-base-url",
      new URL(sandboxDto.control_url).origin,
    ],
    { cwd: repoRoot, stdio: ["ignore", "pipe", "pipe"] },
  );
  processes.push(child);
  child.stdout?.resume();
  child.stderr?.resume();
  await waitForUrl(`${incidentApiUrl}/health`);
}

function syntheticHeaders(role: string): Record<string, string> {
  return {
    "X-Sandbox-Source": "SANDBOX_SYNTHETIC",
    "X-Fixture-Only": "true",
    "X-Tenant-Id": "tenant.synthetic.alpha",
    "X-Family-Id": "family.synthetic.alpha",
    "X-Actor-Id": `actor.synthetic.${role.toLowerCase()}`,
    "X-Actor-Role": role,
  };
}

async function requireOk(request: Promise<Response>): Promise<void> {
  const response = await request;
  if (!response.ok) throw new Error(`sandbox setup failed: ${response.status} ${await response.text()}`);
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
