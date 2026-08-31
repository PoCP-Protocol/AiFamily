# Family Growth S1→S2 Synthetic Run Evidence

## Scope

这是 `codex/family-assessment-s01@d507b45` 的 synthetic/dev 运行证据，不是生产验收。场景绑定“晚饭后因作业安排反复起冲突”的家庭困扰；儿童只作为受益对象，不作为授权人或公开互动主体。

## Runnable entry

```powershell
$env:EXPO_PUBLIC_FAMILY_JOURNEY_SYNTHETIC='true'
pnpm exec expo start --web --port 11002
```

页面入口：`http://localhost:11002/ui/UI-02` → `UI-03` → `UI-04` → `UI-05`。

## User path

1. 成人在 UI-02 输入家庭困扰并确认用途说明。
2. 完成最小题集，提交后进入 UI-03。
3. UI-03 展示“我们听到的家庭关注”、可能方向、知识依据和未知项。
4. 成人可返回修改、退出或恢复；确认/拒绝是显式 Human Gate。
5. CONFIRM 的 S1 contract 返回 `INTENT_CREATED`、`intent_id` 和 `HUMAN_CONFIRMED_INTENT_NOT_OUTCOME`；DISMISS 返回 `NO_ACTION` 且没有 intent。
6. 仅确认后显示进入 UI-04 的入口；UI-04 使用既有 synthetic Journey plan fixture，UI-05 提供实践/复盘入口：`CONTINUE`、`ADJUST`、`PAUSE`、`HUMAN_REVIEW_REQUIRED`。

## Commands and raw outcomes

```text
frontend/mobile: pnpm exec vitest run
38 test files passed, 1 skipped
183 tests passed, 1 skipped

frontend/mobile: pnpm build
Done in 112ms

repo: uv run pytest tests/apps/family_api/test_assessment_routes.py tests/domains/assessment/test_assessment_flow.py -q
25 passed in 1.04s

frontend/mobile: pnpm exec tsc --noEmit
PASS

repo: git diff --check
PASS
```

## Browser observation (2026-08-31)

在本地 11002 页面实际完成：打开 `/ui/UI-02` → 恢复一条家庭困扰草稿 → 点击“像我们家，继续深入” → 逐题选择“经常”并完成 7/7 → 点击“看见我的整理”。结果页实际显示：

- “一到写作业就容易争吵，我想先找到更温和的开始。”
- “依据 / 可能的方向 / 还未知 / 这份理解背后的知识”四个可读区域。
- 结果页明确提示：未登录并完成授权时不会放入家庭空间、不会自动创建计划或行动。
- 结果页提供“像我们家 / 不太像 / 补充 / 返回修改 / 重新开始测评 / 退出”。

本次 screenshot 已在任务对话中展示；当前浏览器运行没有持久化图像文件。由于本地 synthetic session 未连接真实家庭授权，确认按钮不会伪造 `intent_id`，因此 UI-03→S2 的确认 receipt、计划回读、实践和复盘仍按上节 `NOT_STARTED/BLOCKED` 处理。

## Negative/recovery coverage

- 成人拒绝理解：`NO_ACTION`，不创建 intent/plan/action。
- UI-03 读取失败：显示重新读取；确认失败：显示稍后重试。
- 退出 UI-02：本地草稿可恢复；重新开始显式清空当前测评流程。
- 跨家庭、撤回/过期 Consent、真实 PG 重启回读、真实 Audit/Outbox 事务和 Journey HTTP/PG 尚未运行，不能写成 PASS。

## Evidence classification

- `PASS`: synthetic UI contract、局部 assessment route/flow、前端 build/typecheck。
- `SKIP`: 现有 auth logout test（测试文件标记 skip）。
- `NOT_STARTED/BLOCKED`: connected Identity/session、read-time Consent、真实 tenant/family scope、PG persistence/restart readback、跨家庭真实负测、S2 Journey HTTP/PG 与持久截图/录屏。

## Rollback

回滚本次 evidence artifact 和实现提交时，只需在本分支反向移除 `d507b45`/`d7b65b8` 对应文件；不涉及 main、Platform 底座或共享 Journey WIP。
