"""构建 MaaFGO APK；支持 ARM64 手机和 x86_64 模拟器。"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SHELL = ROOT / "Android/MaaFwApp"
VERSIONS = json.loads((ROOT / "Android/versions.json").read_text(encoding="utf-8"))


def run(args, **kwargs):
    subprocess.run([str(arg) for arg in args], cwd=ROOT, check=True, **kwargs)


def environment():
    problems = []
    java_home = os.environ.get("JAVA_HOME")
    java = Path(java_home) / "bin" / ("java.exe" if os.name == "nt" else "java") if java_home else shutil.which("java")
    if not java or not Path(java).is_file():
        problems.append("缺少 JDK 17+；设置 JAVA_HOME")
    elif not all((Path(java).parent / (tool + (".exe" if os.name == "nt" else ""))).is_file() for tool in ("javac", "jlink")):
        problems.append("JAVA_HOME 指向精简 Java 运行时；需要包含 javac 和 jlink 的完整 JDK 17+")
    sdk = Path(os.environ.get("ANDROID_HOME") or os.environ.get("ANDROID_SDK_ROOT") or ROOT / "Android/sdk").resolve()
    if not (sdk / "platforms/android-37").is_dir() and not (sdk / "platforms/android-37.0").is_dir():
        problems.append(f"缺少 Android SDK platforms;android-37.0: {sdk}")
    ndk = Path(os.environ.get("ANDROID_NDK_ROOT") or sdk / "ndk" / VERSIONS["ndk"]).resolve()
    if not (ndk / "build/cmake/android.toolchain.cmake").is_file():
        problems.append(f"缺少 Android NDK {VERSIONS['ndk']}: {ndk}")
    # 优先 SDK 自带 CMake/Ninja，否则使用 PATH。
    cmake_dirs = sorted((sdk / "cmake").glob("*/bin"), reverse=True)
    if cmake_dirs:
        os.environ["PATH"] = str(cmake_dirs[0]) + os.pathsep + os.environ.get("PATH", "")
    for name in ("cmake", "ninja"):
        if not shutil.which(name):
            problems.append(f"缺少 {name}；安装 SDK cmake;3.22.1 或添加到 PATH")
    if not (SHELL / "gradlew").is_file():
        problems.append("MaaFwApp 子模块为空：git submodule update --init Android/MaaFwApp")
    return sdk, ndk, problems


def validate_apk(apk: Path, abi="arm64-v8a"):
    with zipfile.ZipFile(apk) as zf:
        names = set(zf.namelist())
        required = [f"lib/{abi}/" + name for name in (
            "libMaaFramework.so", "libMaaAgentServer.so", "libonnxruntime.so", "libc++_shared.so")]
        required += ["assets/agent/bundle.zip", "assets/agent/agent-runtime.json"]
        missing = [name for name in required if name not in names]
        if missing:
            raise RuntimeError(f"APK 缺少必要文件: {missing}")
        import io
        with zipfile.ZipFile(io.BytesIO(zf.read("assets/agent/bundle.zip"))) as bundle:
            for name in (f"{abi}/bin/python3", f"{abi}/site-packages/cv2.so"):
                if name not in bundle.namelist():
                    raise RuntimeError(f"APK Python bundle 缺少 {name}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-env", action="store_true")
    parser.add_argument("--abi", choices=("arm64-v8a", "x86_64"), default="arm64-v8a")
    parser.add_argument("--skip-runtime", action="store_true", help="已有完整运行时，仅更新资源和 APK")
    parser.add_argument("--release", action="store_true", help="使用 KEYSTORE_PATH 等变量签名 release 包")
    args = parser.parse_args()
    os.environ["MAAFGO_ANDROID_ABI"] = args.abi
    sdk, ndk, problems = environment()
    for problem in problems:
        print(problem)
    if problems:
        return 1
    if args.check_env:
        print(f"构建环境就绪：SDK={sdk}，NDK={ndk}")
        return 0
    if args.release and not all(os.environ.get(name) for name in ("KEYSTORE_PATH", "KEYSTORE_PASSWORD", "KEY_ALIAS", "KEY_PASSWORD")):
        parser.error("release 需要 KEYSTORE_PATH、KEYSTORE_PASSWORD、KEY_ALIAS、KEY_PASSWORD；日常测试使用默认 debug")
    if not args.skip_runtime:
        run([sys.executable, SHELL / "scripts/build_agent_bundle.py", "--out", ROOT / "Android/agent-dist",
             "--abi", args.abi, "--core-tag", VERSIONS["python_core"]])
        run([sys.executable, ROOT / "tools/build_android_opencv.py", "--abi", args.abi, "--ndk", ndk])
    if not (ROOT / f"Android/agent-dist/{args.abi}/bundle/site-packages/cv2.so").is_file():
        raise RuntimeError("Python 运行时缺少 cv2.so，请去掉 --skip-runtime 重新构建")
    run([sys.executable, SHELL / "scripts/setup_maa_framework.py", "--abi", args.abi, "--tag", VERSIONS["maafw"]])
    run([sys.executable, ROOT / "tools/prepare_android.py"])
    # 保留开发者已有的机器配置，只补充本次构建所需键。
    props = SHELL / "local.properties"
    lines = props.read_text(encoding="utf-8-sig").splitlines() if props.exists() else []
    settings = {"sdk.dir": sdk.as_posix(), "pi.profile": "../profile.yaml",
                "build.debugAbi": args.abi, "build.releaseAbi": args.abi, "build.ndkVersion": VERSIONS["ndk"]}
    lines = [line for line in lines if line.split("=", 1)[0].strip() not in settings]
    props.write_text("\n".join(lines + [f"{key}={value}" for key, value in settings.items()]) + "\n", encoding="utf-8")
    mode = "release" if args.release else "debug"
    # AGP 增量更新 APK 时会保留旧的未引用 ZIP 数据；资源包很大，反复构建会膨胀。
    # 删除本次构建目录中的生成 APK，让签名任务重新生成紧凑的安装包。
    apk_dir = SHELL / f"app/build/outputs/apk/{mode}"
    for old_apk in apk_dir.glob("*.apk"):
        old_apk.unlink()
    gradle = SHELL / ("gradlew.bat" if os.name == "nt" else "gradlew")
    if os.name != "nt":
        gradle.chmod(gradle.stat().st_mode | 0o111)
    run([gradle, "-p", SHELL, "--no-daemon", f":app:assemble{mode.title()}"])
    apks = list(apk_dir.glob("*.apk"))
    if len(apks) != 1:
        raise RuntimeError(f"预期一个 APK，实际 {apks}")
    validate_apk(apks[0], args.abi)
    out = ROOT / "Android/out" / f"MaaFGO-android-{args.abi}-{mode}.apk"
    out.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(apks[0], out)
    print(f"APK 已生成并校验：{out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
