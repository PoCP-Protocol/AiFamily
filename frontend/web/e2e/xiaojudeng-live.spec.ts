import { expect, test } from "@playwright/test";

const mediaPlaybackConfigured = Boolean(process.env.VITE_MEDIA_PLAYBACK_DTO);

test("Xiao Ju Deng homepage card opens the H-LIVE-01 read-only detail", async ({ page }, testInfo) => {
  await page.goto("/");

  await expect(page.getByRole("heading", { name: "为家庭问题找到合适的专家场次" })).toBeVisible();
  await expect(page.getByText("小橘灯：家庭沟通中的温柔练习")).toBeVisible();
  await expect(page.getByText("家长与照护者").first()).toBeVisible();
  await expect(page.getByText("直播中")).toBeVisible();
  await expect(page.getByText("即将开始")).toBeVisible();
  await expect(page.getByText("已结束 / 回看受限")).toBeVisible();
  if (mediaPlaybackConfigured) {
    await expect(page.getByText("LIVE").first()).toBeVisible();
  } else {
    await expect(page.getByText("SCHEDULED")).toBeVisible();
  }
  await expect(page.getByText("ENDED")).toBeVisible();
  await expect(page.getByText("#家庭沟通").first()).toBeVisible();
  if (mediaPlaybackConfigured) {
    await expect(page.getByText("MEDIA_READY").first()).toBeVisible();
  } else {
    await expect(page.getByText("NO_MEDIA").first()).toBeVisible();
  }
  await expect(page.getByPlaceholder("例如：家庭沟通")).toBeVisible();
  await expect(page.getByText("家庭理解工作台（次级入口）")).toBeVisible();
  await expect(page.getByText("家庭成长 · AI 原生体验")).not.toBeVisible();
  await page.getByRole("button", { name: "查看直播详情" }).click();

  await expect(page.getByText("H-LIVE-01 · 只读详情")).toBeVisible();
  await expect(page.getByRole("article")).toContainText("APPROVED");
  await expect(page.getByRole("article")).toContainText("UNEXPIRED");
  await expect(page.getByRole("article")).toContainText("FAMILY");
  await expect(page.getByRole("article")).toContainText("true · DEV_ONLY");
  await expect(page.getByRole("article")).toContainText("收藏");
  await expect(page.getByRole("article")).toContainText("回看");
  await expect(page.getByRole("article")).toContainText("LOCKED · 不可用");
  await expect(page.getByRole("button", { name: /收藏|回看/ })).toHaveCount(0);
  if (mediaPlaybackConfigured) {
    await expect(page.locator("video")).toHaveCount(1);
    await expect(page.locator("video")).toHaveAttribute("src", /127\.0\.0\.1/);
    await expect(page.locator("video")).not.toHaveAttribute("autoplay");
    await expect(page.getByText("SANDBOX_SYNTHETIC · FIXTURE_ONLY")).toBeVisible();
    await page.screenshot({ path: testInfo.outputPath("h03-live.png"), fullPage: true });
    await page.getByRole("button", { name: "模拟断流" }).click();
    await expect(page.getByText("DISCONNECTED")).toBeVisible();
    await expect(page.locator("video")).toHaveCount(0);
    await page.screenshot({ path: testInfo.outputPath("h03-disconnected.png"), fullPage: true });
    await page.getByRole("button", { name: "恢复播放" }).click();
    await expect(page.getByText("LIVE").last()).toBeVisible();
    await expect(page.locator("video")).toHaveCount(1);
    await page.screenshot({ path: testInfo.outputPath("h03-recovered.png"), fullPage: true });
    await page.getByRole("button", { name: "停止直播" }).click();
    await expect(page.getByText("STOPPED")).toBeVisible();
    await expect(page.locator("video")).toHaveCount(0);
    await page.screenshot({ path: testInfo.outputPath("h03-stopped.png"), fullPage: true });
    await page.getByRole("button", { name: "撤回授权" }).click();
    await expect(page.getByText("REVOKED")).toBeVisible();
    await expect(page.locator("video")).toHaveCount(0);
    await page.screenshot({ path: testInfo.outputPath("h03-revoked.png"), fullPage: true });
  } else {
    await expect(page.getByText("视频暂不可用")).toBeVisible();
    await expect(page.getByText("WAITING_AUTHORIZATION")).toBeVisible();
    await expect(page.locator("video")).toHaveCount(0);
    await expect(page.locator("[data-playback-url]")).toHaveCount(0);
  }
  await expect(page.getByRole("article")).not.toContainText("token");
  await expect(page.getByRole("article")).not.toContainText("预约");

  await page.getByRole("button", { name: "返回直播发现" }).click();
  await expect(page.getByRole("button", { name: "查看直播详情" })).toBeVisible();
});
