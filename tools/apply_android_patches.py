"""向固定 MaaFwApp 子模块应用可重放补丁；已应用时不重复修改。"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SHELL = ROOT / "Android/MaaFwApp"
PATCHES = ROOT / "Android/patches"


def git_apply(shell: Path, patch: Path, *options: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(shell), "apply", *options, str(patch.resolve())],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )


def applied_prefix(shell: Path, patches: list[Path]) -> int:
    """Later patches may edit files or hunks introduced by earlier ones; verify the chain together."""
    if len(patches) < 2:
        return 0
    paths = set()
    for patch in patches:
        stat = subprocess.run(
            ["git", "-C", str(shell), "apply", "--numstat", "-z", str(patch.resolve())],
            capture_output=True,
        )
        if stat.returncode:
            return 0  # Preserve the ordinary per-patch failure diagnostic.
        records = iter(stat.stdout.split(b"\0"))
        for record in records:
            if not record:
                continue
            path = record.split(b"\t", 2)[2]
            # Rename records have an empty path followed by the old and new names.
            paths.update([os.fsdecode(path)] if path else [os.fsdecode(next(records)), os.fsdecode(next(records))])
    with tempfile.TemporaryDirectory(prefix="maafgo-patch-index-") as temporary:
        env = dict(os.environ, GIT_INDEX_FILE=str(Path(temporary) / "index"))

        def scratch(*args, data=None):
            return subprocess.run(
                ["git", "-C", str(shell), *args], env=env, capture_output=True, input=data,
            )

        if scratch("read-tree", "--empty").returncode:
            return 0
        present = [path for path in sorted(paths) if (shell / path).exists() or (shell / path).is_symlink()]
        if present and scratch("add", "-f", "--", *present).returncode:
            return 0
        tree = scratch("write-tree")
        if tree.returncode:
            return 0
        # Only the temporary index is reversed. User files, their mtimes, and the real index stay intact.
        for count in range(len(patches), 1, -1):
            if scratch("read-tree", tree.stdout.strip().decode("ascii")).returncode:
                return 0
            for patch in reversed(patches[:count]):
                if scratch("apply", "--cached", "--reverse", str(patch.resolve())).returncode:
                    # Windows text-mode writers may produce CRLF patches while git add
                    # normalizes the index to LF. Retry only that transport conversion;
                    # do not ignore arbitrary whitespace in a developer's local edits.
                    raw = patch.read_bytes()
                    if b"\r\n" not in raw or scratch(
                        "apply", "--cached", "--reverse", "-", data=raw.replace(b"\r\n", b"\n"),
                    ).returncode:
                        break
            else:
                return count
    return 0


def apply_patches(shell: Path = SHELL, patches: Path = PATCHES) -> list[tuple[str, str]]:
    """保留不冲突的本地改动；补丁既不能应用也不能反向验证时明确失败。"""
    if not (shell / "app/src/main").is_dir():
        raise RuntimeError(f"MaaFwApp 子模块未初始化: {shell}")
    if not patches.is_dir():
        raise RuntimeError(f"找不到安卓外壳补丁目录: {patches}")
    result = []
    patch_files = sorted(patches.glob("*.patch"))
    if not patch_files:
        raise RuntimeError(f"安卓外壳补丁目录为空: {patches}")
    prefix = applied_prefix(shell, patch_files)
    for index, patch in enumerate(patch_files):
        if index < prefix:
            result.append((patch.name, "already applied"))
            continue
        check = git_apply(shell, patch, "--check")
        if check.returncode == 0:
            applied = git_apply(shell, patch)
            if applied.returncode:
                raise RuntimeError(f"应用补丁失败 {patch.name}:\n{applied.stderr.strip()}")
            result.append((patch.name, "applied"))
        elif git_apply(shell, patch, "--reverse", "--check").returncode == 0:
            result.append((patch.name, "already applied"))
        else:
            raise RuntimeError(
                f"补丁 {patch.name} 与当前 MaaFwApp 不兼容；请检查子模块版本或本地改动。\n"
                f"{check.stderr.strip()}"
            )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shell", type=Path, default=SHELL)
    parser.add_argument("--patches", type=Path, default=PATCHES)
    args = parser.parse_args()
    for name, status in apply_patches(args.shell, args.patches):
        print(f"MaaFwApp: {name}: {status}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
