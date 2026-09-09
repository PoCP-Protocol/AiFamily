"""R15 分支窗口期治理检查（governance/REPOSITORY_CONSTITUTION.md R15）。

对每一条远端 `codex/*` / `feat/*` / `chief/*` 探索性分支：
1. 若其最后一次真实功能 commit 距今超过 R15_WINDOW_DAYS 天，且
2. 该分支未在 main.py / dev_wiring.py 中被 include_router /
   install_*_wiring 引用（即未接组合根），且
3. 该分支没有对应的开放 PR，

则判定为违反 R15，输出到 stderr 并以非零退出码结束（供 CI 周期任务观测，当前不阻断 push/merge —— 见
REPOSITORY_CONSTITUTION.md §2 执行状态表 "部分" 标注：先观测出真实分布，再决定是否升级为强制阻断）。

不做任何自动 push/delete/tag 操作 —— 分支删除是不可逆动作，必须由人工在看到本工具输出后决定，
参见 `.claude/commands/branch-triage.md` 的既有纪律：
"删除远程分支前，必须让用户逐字确认具体分支名"。
本工具只诚实地报告状态，不代为决策。
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime

R15_WINDOW_DAYS = 7
EXPLORATORY_PREFIXES = ("codex/", "feat/", "chief/")
COMPOSITION_ROOT_FILES = (
    "backend/apps/family_api/main.py",
    "backend/apps/family_api/dev_wiring.py",
)


@dataclass(frozen=True)
class StaleBranchFinding:
    branch: str
    last_commit_at: datetime
    days_stale: int
    has_open_pr: bool


def _run(*args: str) -> str:
    result = subprocess.run(args, capture_output=True, text=True, check=True)
    return result.stdout.strip()


def _list_exploratory_branches() -> list[str]:
    raw = _run("git", "branch", "-r", "--format=%(refname:short)")
    branches = [line for line in raw.splitlines() if line and "HEAD" not in line]
    return [
        b[len("origin/") :]
        for b in branches
        if b.startswith("origin/") and b[len("origin/") :].startswith(EXPLORATORY_PREFIXES)
    ]


def _last_commit_at(branch: str) -> datetime:
    ts = _run("git", "log", "-1", "--format=%ct", f"origin/{branch}")
    return datetime.fromtimestamp(int(ts), tz=UTC)


def _touches_composition_root(branch: str) -> bool:
    """True if this branch's own diff vs its merge-base with main modifies a
    composition-root file — a rough proxy for "wired in", cheap enough to run
    per-branch without cloning. A real merge/PR review still verifies the
    include_router/install_*_wiring call exists, not just that the file moved.
    """
    merge_base = _run("git", "merge-base", "origin/main", f"origin/{branch}")
    diff = _run("git", "diff", "--name-only", merge_base, f"origin/{branch}")
    changed = set(diff.splitlines())
    return any(f in changed for f in COMPOSITION_ROOT_FILES)


def _has_open_pr(branch: str) -> bool:
    try:
        out = _run("gh", "pr", "list", "--head", branch, "--state", "open", "--json", "number")
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False
    return out not in ("", "[]")


def find_stale_branches() -> list[StaleBranchFinding]:
    findings: list[StaleBranchFinding] = []
    now = datetime.now(UTC)
    for branch in _list_exploratory_branches():
        last_commit_at = _last_commit_at(branch)
        days_stale = (now - last_commit_at).days
        if days_stale < R15_WINDOW_DAYS:
            continue
        if _touches_composition_root(branch):
            continue
        has_open_pr = _has_open_pr(branch)
        if has_open_pr:
            continue
        findings.append(
            StaleBranchFinding(
                branch=branch,
                last_commit_at=last_commit_at,
                days_stale=days_stale,
                has_open_pr=has_open_pr,
            )
        )
    return findings


def main() -> int:
    findings = find_stale_branches()
    if not findings:
        print("R15: no stale unwired branches found.")
        return 0

    print(
        f"R15 违规：以下 {len(findings)} 条分支超过 {R15_WINDOW_DAYS} 天未接组合根、"
        "且无开放 PR，应归档 (git tag archive/<name> + 删除远端分支) 或立即开 PR：",
        file=sys.stderr,
    )
    for f in findings:
        print(
            f"  - {f.branch}  (最后commit {f.last_commit_at.date()}，"
            f"停滞 {f.days_stale} 天)",
            file=sys.stderr,
        )
    print(
        "本工具不会自动删除任何分支——归档/删除前必须人工逐条确认分支名"
        "（见 .claude/commands/branch-triage.md）。",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
