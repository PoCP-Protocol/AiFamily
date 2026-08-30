import { expect, test } from "@playwright/test";

test("desktop Web can generate, review, feedback and replay a draft", async ({ page }) => {
  await page.goto("/");
  await page.getByText("家庭理解工作台（次级入口）").click();
  await page.getByLabel("你的表达").fill("孩子最近不愿意写作业，我们总在争吵。");
  await page.getByRole("checkbox").check();
  await page.getByRole("button", { name: "生成理解草案" }).click();

  await expect(page.getByText("DRAFT", { exact: true })).toBeVisible();
  await expect(page.getByText("测试夹具")).toBeVisible();
  await page.getByRole("button", { name: "有帮助" }).click();
  await expect(page.getByText("已记录“有帮助”的反馈。")).toBeVisible();
  await page.getByRole("button", { name: "打开体验回放" }).click();
  await expect(page.getByRole("heading", { name: "这次体验发生了什么" })).toBeVisible();
  await page.getByRole("button", { name: "请求人工顾问" }).click();
  await expect(page.getByText("等待人工确认", { exact: true })).toBeVisible();
});
