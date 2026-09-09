import { expect, test } from "@playwright/test";

test.describe("家庭成长 AGI 黄金路径", () => {
  test("从家庭表达走到可回看的成长方向", async ({ page }) => {
    test.setTimeout(90_000);
    await page.goto("/");

    await expect(page.getByRole("heading", { name: /今天，先处理/ })).toBeVisible();
    await page.getByRole("textbox", { name: "首页记录家庭问题" }).fill(
      "每天写作业前都会争吵，我想先理解发生了什么。",
    );
    await page.getByRole("button", { name: /开始整理/ }).click();

    await expect(page.getByRole("heading", { name: "你想先处理哪一件家庭问题？" })).toBeVisible();
    // The assessment is intentionally schema-driven: answer the current
    // question using its first available choice, then advance until submit.
    for (let index = 0; index < 30; index += 1) {
      const choices = page.locator(".family-growth-choice button");
      if (await choices.count()) await choices.first().click();
      const answer = page.locator(".family-growth-item textarea");
      if (await answer.count()) await answer.fill("我们希望先减少写作业前的争吵。");
      const next = page.getByRole("button", { name: /下一题/ });
      if (await next.count() && await next.isVisible()) {
        await next.click();
        continue;
      }
      break;
    }
    await page.getByRole("button", { name: /看见家庭理解/ }).click();

    await expect(page.getByText("这只是一个可以修改的视角")).toBeVisible();
    await page.getByRole("button", { name: /继续决定下一步/ }).click();
    await expect(page.getByText("这是一段可以一起修改的理解")).toBeVisible();

    await page.getByRole("button", { name: /继续决定下一步/ }).click();
    await expect(page.getByText("方向仍然是草案")).toBeVisible();
  });
});
