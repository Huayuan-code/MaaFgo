"""向固定 MaaFwApp 子模块应用可重放补丁；已应用时不重复修改。"""
from __future__ import annotations

import argparse
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SHELL = ROOT / "Android/MaaFwApp"
PATCHES = ROOT / "Android/patches"


def git_apply(shell: Path, patch: Path, *options: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(shell), "apply", *options, str(patch.resolve())],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )


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
    for patch in patch_files:
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
