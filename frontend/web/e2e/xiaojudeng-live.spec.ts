import { expect, test } from "@playwright/test";

const mediaPlaybackConfigured = Boolean(process.env.VITE_MEDIA_PLAYBACK_DTO);

test("desktop: expert discovery opens a concise video-first detail", async ({ page }, testInfo) => {
  await page.goto("/");

  await expect(page.getByRole("heading", { name: "和专家一起，把家庭难题聊明白" })).toBeVisible();
  await expect(page.getByText("小橘灯：家庭沟通中的温柔练习")).toBeVisible();
  await expect(page.getByText("真实场景、清楚方法、当下就能用。")).toBeVisible();
  await expect(page.getByText("内容已审核").first()).toBeVisible();
  await expect(page.getByRole("img", { name: "合成专家形象" }).first()).toBeVisible();
  await expect(page.getByText("family-private")).not.toBeVisible();
  await expect(page.getByText("APPROVED")).not.toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("desktop-discovery.png"), fullPage: true });

  await page.getByRole("button", { name: mediaPlaybackConfigured ? "进入直播间" : "查看直播详情" }).click();
  await expect(page.getByRole("heading", { name: "一个可以马上练习的沟通方法" })).toBeVisible();
  await expect(page.getByText("收藏与回看将在获得明确授权后开放。")).toBeVisible();
  await expect(page.getByText("开发诊断信息")).toBeVisible();
  await expect(page.getByText("APPROVED")).not.toBeVisible();

  if (mediaPlaybackConfigured) {
    await expect(page.locator("video")).toHaveCount(1);
    await expect(page.locator("video")).toHaveAttribute("src", /127\.0\.0\.1/);
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
    await page.screenshot({ path: testInfo.outputPath("desktop-stopped.png"), fullPage: true });

    await page.getByRole("button", { name: "撤回观看权限" }).click();
    await expect(page.getByText("观看权限已经撤回。")).toBeVisible();
    await expect(page.locator("video")).toHaveCount(0);
    await page.screenshot({ path: testInfo.outputPath("desktop-revoked.png"), fullPage: true });
  } else {
    await expect(page.getByText("视频暂不可用")).toBeVisible();
    await expect(page.getByText("视频服务暂未连接，请稍后刷新或返回直播首页。")).toBeVisible();
    await expect(page.locator("video")).toHaveCount(0);
    await page.screenshot({ path: testInfo.outputPath("desktop-no-provider.png"), fullPage: true });
  }
});

test("mobile: discovery, empty search, and detail remain usable", async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");

  await expect(page.getByRole("heading", { name: "和专家一起，把家庭难题聊明白" })).toBeVisible();
  await expect(page.getByRole("searchbox", { name: "你想解决什么问题？" })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("mobile-discovery.png"), fullPage: true });

  await page.getByRole("searchbox", { name: "你想解决什么问题？" }).fill("不存在的问题");
  await expect(page.getByText("没有匹配的直播")).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("mobile-empty.png"), fullPage: true });

  await page.getByRole("searchbox", { name: "你想解决什么问题？" }).fill("");
  await page.getByRole("button", { name: mediaPlaybackConfigured ? "进入直播间" : "查看直播详情" }).click();
  await expect(page.getByRole("heading", { name: "一个可以马上练习的沟通方法" })).toBeVisible();
  await expect(page.getByText("APPROVED")).not.toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("mobile-detail.png"), fullPage: true });
});
