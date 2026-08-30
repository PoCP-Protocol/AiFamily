import { expect, test } from "@playwright/test";

test("adult can go from a family moment to a small step", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "今天，想先让哪件小事轻一点？" })).toBeVisible();
  await page.getByRole("button", { name: /我想说一件家庭小事/ }).click();
  await page.getByLabel("写给自己的话").fill("孩子最近不愿意写作业，我们总在争吵。");
  await page.getByRole("checkbox").check();
  await page.getByRole("button", { name: "看看我们听到了什么" }).click();

  await expect(page.getByRole("heading", { name: "我们先把这件事放在这里" })).toBeVisible();
  await expect(page.getByText("你刚才说的是")).toBeVisible();
  await expect(page.getByText("我们目前听到的")).toBeVisible();
  await expect(page.getByText("今晚可以试的一小步")).toBeVisible();
  await expect(page.getByText("DRAFT", { exact: true })).toHaveCount(0);

  await page.getByRole("button", { name: "今晚先试这一步" }).click();
  await expect(page.getByRole("heading", { name: "不用一次解决全部。" })).toBeVisible();
  await page.getByRole("checkbox", { name: "我今晚想先试这一步" }).check();
  await expect(page.getByText("已记下。明天可以从这里继续，不需要重新解释一遍。")).toBeVisible();
  await page.getByRole("button", { name: "回到首页" }).click();
  await expect(page.getByRole("heading", { name: "今天，想先让哪件小事轻一点？" })).toBeVisible();
});

test("assessment entry can be exited before submitting", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: /我想做一次小测评/ }).click();
  await page.getByRole("button", { name: "沟通总是绕回争吵" }).click();
  await page.getByRole("button", { name: "先回首页", exact: true }).click();
  await expect(page.getByRole("heading", { name: "今天，想先让哪件小事轻一点？" })).toBeVisible();
});
