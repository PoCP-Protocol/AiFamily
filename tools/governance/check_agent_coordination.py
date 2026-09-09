"""Read-only ADR-0158 coordination consistency check.

This tool reports coordination defects. It never edits, merges, deletes, resets,
pushes, or claims another agent's worktree.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml

REGISTER = Path("governance/AGENT_COORDINATION.yaml")


@dataclass(frozen=True)
class Worktree:
    path: str
    head: str
    branch: str | None
    dirty: bool


def _run(*args: str, cwd: Path) -> str:
    result = subprocess.run(args, cwd=cwd, capture_output=True, text=True, check=True)
    return result.stdout


def _worktrees(repo_root: Path) -> list[Worktree]:
    raw = _run("git", "worktree", "list", "--porcelain", cwd=repo_root)
    blocks = [block for block in raw.split("\n\n") if block.strip()]
    result: list[Worktree] = []
    for block in blocks:
        fields = dict(
            line.split(" ", 1) for line in block.splitlines() if " " in line
        )
        path = fields.get("worktree")
        head = fields.get("HEAD")
        if not path or not head:
            continue
        status = subprocess.run(
            ("git", "status", "--porcelain"),
            cwd=path,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        branch = fields.get("branch")
        if branch and branch.startswith("refs/heads/"):
            branch = branch.removeprefix("refs/heads/")
        result.append(Worktree(path, head, branch, bool(status.strip())))
    return result


def _load(repo_root: Path) -> dict:
    with (repo_root / REGISTER).open(encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def _path_overlap(left: list[str], right: list[str]) -> bool:
    for lhs in left:
        for rhs in right:
            if lhs == rhs or lhs.startswith(rhs.rstrip("/") + "/") or rhs.startswith(
                lhs.rstrip("/") + "/"
            ):
                return True
    return False


def check(repo_root: Path) -> list[str]:
    data = _load(repo_root)
    findings: list[str] = []
    entries = data.get("observed_threads", [])
    ids = [entry.get("task_id") for entry in entries]
    if len(ids) != len(set(ids)):
        findings.append("duplicate task_id in observed_threads")

    active = [
        entry
        for entry in entries
        if entry.get("status") in {"IN_PROGRESS", "READY_FOR_REVIEW"}
    ]
    for entry in active:
        missing = [
            key
            for key in ("task_id", "owner", "cwd", "capability", "last_observed")
            if not entry.get(key)
        ]
        if missing:
            findings.append(f"{entry.get('task_id', '<unknown>')}: missing {','.join(missing)}")
        if entry.get("owner") in {None, "", "unassigned", "unknown"}:
            findings.append(f"{entry.get('task_id', '<unknown>')}: active task has no named owner")

        for key in ("base_ref", "allowed_paths", "current_truth", "claim", "evidence", "next_gate"):
            value = entry.get(key)
            if value in (None, "", "UNKNOWN") or value == []:
                findings.append(f"{entry.get('task_id', '<unknown>')}: missing {key}")

    for entry in entries:
        cwd = entry.get("cwd")
        if not cwd:
            continue
        path = Path(cwd)
        if not path.exists():
            findings.append(f"{entry.get('task_id', '<unknown>')}: cwd does not exist: {cwd}")
            continue
        try:
            _run("git", "rev-parse", "--show-toplevel", cwd=path)
        except (subprocess.CalledProcessError, FileNotFoundError):
            findings.append(f"{entry.get('task_id', '<unknown>')}: cwd is not a Git worktree: {cwd}")

    for index, left in enumerate(entries):
        left_paths = left.get("allowed_paths", [])
        for right in entries[index + 1 :]:
            if _path_overlap(left_paths, right.get("allowed_paths", [])):
                findings.append(
                    f"path overlap: {left.get('task_id')} <> {right.get('task_id')}"
                )

    registered_cwds = {
        str(Path(entry.get("cwd", "")).resolve())
        for entry in entries
        if entry.get("cwd")
    }
    for worktree in _worktrees(repo_root):
        if str(Path(worktree.path).resolve()) not in registered_cwds and worktree.dirty:
            findings.append(f"UNOWNED dirty worktree: {worktree.path} ({worktree.head})")

    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    findings = check(args.repo_root.resolve())
    if findings:
        print("ADR-0158 coordination: BLOCKED", file=sys.stderr)
        for finding in findings:
            print(f"- {finding}", file=sys.stderr)
        return 1
    print("ADR-0158 coordination: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
