"""用固定版本 MaaFwApp 的真实解析器和任务编译器检查安卓资源。"""
from pathlib import Path
import argparse
import os
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SHELL = ROOT / "Android/MaaFwApp"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-type", choices=("debug", "release"), default="debug")
    args = parser.parse_args()
    source = ROOT / "tests/android/MaaFgoCompatibilityTest.kt"
    target = SHELL / "app/src/test/java/com/aliothmoon/maafw/project/MaaFgoCompatibilityTest.kt"
    if target.exists():
        raise RuntimeError(f"不覆盖子模块中已有的测试文件: {target}")
    if not (ROOT / "Android/assets/interface.json").is_file():
        raise RuntimeError("先运行 tools/prepare_android.py")
    env = dict(os.environ, MAAFGO_COMPAT_ASSETS=str(ROOT / "Android/assets"))
    gradle = SHELL / ("gradlew.bat" if os.name == "nt" else "gradlew")
    shutil.copy2(source, target)
    try:
        task = f":app:test{args.build_type.title()}UnitTest"
        return subprocess.run([str(gradle), "-p", str(SHELL), "--no-daemon", task,
                               "--tests", "com.aliothmoon.maafw.project.MaaFgoCompatibilityTest"], env=env).returncode
    finally:
        target.unlink()


if __name__ == "__main__":
    raise SystemExit(main())
