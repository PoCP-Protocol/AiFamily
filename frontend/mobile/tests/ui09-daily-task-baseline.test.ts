import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
const source = readFileSync(resolve(__dirname, "../app/ui/UI-09.tsx"), "utf8");
describe("UI-09 original daily-task baseline contract", () => {
  it("keeps the blue reminder and separates the real task from optional references", () => {
    for (const copy of ["AI家庭管家提醒", "1", "真实任务记录", "可选参考", "今日行动记录", "完成今日任务"]) expect(source).toContain(copy);
    expect(source).toContain("TaskCard");
  });
  it("keeps the original completion action routed through the existing named check-in state", () => {
    expect(source).toContain("startAction()");
    expect(source).toContain("completeAction(reflection)");
    expect(source).toContain("家长反思");
  });
  it("persists start, pause, resume, cancel, and completion states for restart-safe readback", () => {
    expect(source).toContain("getFamilyToday");
    expect(source).toContain("changeTodayTaskState");
    for (const state of ["NOT_STARTED", "IN_PROGRESS", "PAUSED", "CHECKED_IN", "CANCELLED"]) expect(source).toContain(state);
    for (const action of ["START", "PAUSE", "RESUME", "CANCEL"]) expect(source).toContain(action);
    expect(source).toContain("task_version");
  });
  it("does not turn task completion or reflection into diagnosis, a family rank, or a result", () => {
    expect(source).toContain("不会被当作孩子的事实或教育结果");
    expect(source).toContain("不代表已经产生教育效果");
    expect(source).not.toMatch(/儿童诊断|家庭排名|家庭总分/);
  });
  it("does not present synthetic progress or streak metrics as family facts", () => {
    expect(source).not.toContain("本周完成度");
    expect(source).not.toContain("连续打卡");
    expect(source).not.toContain("isComplete ? 78");
    expect(source).not.toContain("? 12 : 1");
    expect(source).not.toMatch(/const\s+progress\s*=/);
  });
});
