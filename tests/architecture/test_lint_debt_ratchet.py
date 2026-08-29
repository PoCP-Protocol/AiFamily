"""Lint 债务棘轮 —— 让 ruff 错误数只能降、不能涨。

## 这个文件防的是什么

R14 的伤疤是"写成文档的策略等于没有策略"。本仓库还踩到了它的一个变体：
**写成 CI 步骤但没人看的检查，等于没有检查。**

事实经过（`docs/11_delivery/PROJECT_MANAGEMENT_CHARTER.md` §0 第 1、2 条）：
T-01 把 ruff 错误清到 0；此后并发会话新增代码把它累积回 **401** 个；远端 CI
因此从第一次推送起连续三次全红（run 33244397013 / 33244790062 / 33244977302），
**无人发现**。`ruff check` 一直在 CI 里跑着，它只是全程红着而没有人看。

全红的 CI 与没有 CI 等价，且更糟 —— 它让"红"变成常态，于是真实回归也淹在红里。

## 为什么是棘轮，而不是只有"必须为零"

`ruff check .` 为零是终局，也是当前状态，CI 的 `Lint (ruff)` 步骤已经在守它。
但那个门是**全绿/全红**二值的：一旦有人（比如一次大规模迁入）把它弄红，后续
所有人看到的都是"本来就红"，于是它会像上次那样红着放几十次 run 没人管。

棘轮提供的是**方向性保证**：即使某次它非零，也不允许比记录的基线更差。这让
"债务在增长"这件事在**第一次增长时**就失败，而不是等到有人想起来看 CI。

同时它把债务数字**写进仓库**（下方 `BASELINE`），于是：
  * 债务从"跑一次命令才知道"变成 git 里可见、可 diff、可追责的事实
  * 降低债务必须同步下调基线（棘轮只能往下拧），零债务时基线为 0
  * 谁让它涨了，会在自己的 PR 里看到失败，而不是留给下一个人

## 与 CI `Lint (ruff)` 步骤的关系

不是重复。那一步要求**当前为零**；本测试要求**永不倒退**。前者在债务为零时是
更强的约束；后者在债务非零的过渡期里是唯一还能咬人的约束。两者都保留是有意的。
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

# 允许的 ruff 错误总数上限。**只能下调，不能上调。**
#
# 上调它等于把质量债合法化 —— 那正是本文件要防的事。如果你的改动让这个数字
# 涨了，修你的代码，不要改这个常量。若确有不可避免的例外，需要一份 ADR 说明
# 为何该规则在该处不适用，并用针对性的 per-file-ignores 表达，而不是抬高总数。
#
# 2026-08-29: QA 角色把 401 -> 0（详见 ADR-0009 的 sweep 记录）。
BASELINE = 0


def _ruff_error_count(repo_root: Path) -> int:
    """跑 ruff 并数错误条数。用 JSON 输出以免解析人类可读格式。"""
    ruff = shutil.which("ruff")
    cmd = [ruff, "check", ".", "--output-format=json"] if ruff else None
    if cmd is None:
        # 没有独立 ruff 可执行文件时退回 `python -m ruff`（uv 环境里总可用）。
        cmd = ["python", "-m", "ruff", "check", ".", "--output-format=json"]

    proc = subprocess.run(
        cmd,
        cwd=repo_root,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    # ruff 有错误时退出码为 1，无错误为 0；两者都会输出合法 JSON。
    # 退出码 2 才是"ruff 自己坏了"。
    if proc.returncode not in (0, 1):
        pytest.skip(f"ruff 不可用或调用失败(exit={proc.returncode}): {proc.stderr[:400]}")

    try:
        return len(json.loads(proc.stdout or "[]"))
    except json.JSONDecodeError:  # pragma: no cover - ruff 输出异常时
        pytest.skip(f"无法解析 ruff JSON 输出: {proc.stdout[:200]}")
        raise  # 让类型检查器知道此处不返回


def test_ruff_error_count_never_regresses(repo_root: Path) -> None:
    """ruff 错误数不得超过基线。

    失败信息刻意给出**怎么修**而不只是数字 —— 一个只说"你破坏了基线"的测试
    会诱导下一个人直接抬高基线。
    """
    actual = _ruff_error_count(repo_root)

    assert actual <= BASELINE, (
        f"ruff 错误数从基线 {BASELINE} 涨到 {actual}（+{actual - BASELINE}）。\n"
        f"\n"
        f"跑 `uv run ruff check .` 看具体错误，`uv run ruff check . --fix` 修可自动修的，\n"
        f"剩下的对**你改过的文件**跑 `uv run ruff format <文件>`（ADR-0009）。\n"
        f"\n"
        f"不要为了让本测试通过而抬高 BASELINE：那会把质量债合法化，而这个文件\n"
        f"存在的唯一原因就是上一次债务从 0 悄悄涨回 401 且连续三次 CI 全红无人发现。\n"
        f"禁止用 `# noqa: E501` 或放宽 pyproject 的 line-length 来规避（ADR-0009）。"
    )


def test_baseline_is_tightened_when_debt_drops(repo_root: Path) -> None:
    """基线必须贴着实际值 —— 松基线是"看起来在守、实际不咬人"。

    如果实际错误数已经低于基线，说明有人清理了债务但没有把棘轮拧紧。此时基线
    留着的余量就是允许债务无声反弹的空间，而这正是本文件要消灭的失效模式。
    """
    actual = _ruff_error_count(repo_root)

    assert actual >= BASELINE, (
        f"实际 ruff 错误数 {actual} 已低于基线 {BASELINE} —— 请把本文件的 BASELINE "
        f"下调为 {actual}，把棘轮拧紧。\n"
        f"留着余量等于允许债务在不触发失败的情况下反弹到 {BASELINE}。"
    )
