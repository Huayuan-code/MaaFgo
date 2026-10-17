"""为 MaaFwApp CPython 3.13 内核交叉编译 OpenCV（需 Android NDK、CMake、Ninja）。"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
VERSION = "4.12.0"
HEADERS_VERSION = "3.13.16-0"


def download(url, path):
    if not path.is_file():
        path.parent.mkdir(parents=True, exist_ok=True)
        part = path.with_suffix(path.suffix + ".part")
        print(f"Download: {url}", flush=True)
        with urllib.request.urlopen(url, timeout=120) as response, part.open("wb") as sink:
            shutil.copyfileobj(response, sink)
        part.replace(path)


def build(abi, ndk, jobs):
    cache = ROOT / "Android/.cache"
    bundle = ROOT / "Android/agent-dist" / abi / "bundle"
    python_lib = bundle / "prefix/lib/libpython3.13.so"
    numpy_headers = bundle / "site-packages/numpy/_core/include"
    if not python_lib.is_file() or not numpy_headers.is_dir():
        raise SystemExit("请先用 MaaFwApp/scripts/build_agent_bundle.py 生成 Python 运行时")
    source = cache / f"opencv-{VERSION}"
    archive = cache / f"opencv-{VERSION}.zip"
    download(f"https://github.com/opencv/opencv/archive/refs/tags/{VERSION}.zip", archive)
    if not source.is_dir():
        with zipfile.ZipFile(archive) as zf:
            zf.extractall(cache)
    # 上游默认关闭 Android Python bindings。显式提供目标头文件和 NumPy 后可构建。
    entry = source / "modules/python/CMakeLists.txt"
    content = entry.read_text(encoding="utf-8")
    entry.write_text(content.replace("if(ANDROID OR APPLE_FRAMEWORK OR WINRT)", "if(APPLE_FRAMEWORK OR WINRT)"), encoding="utf-8")
    # NDK r29 带 --no-undefined-version；上游的子串替换会误留下裸 -version。
    common = source / "modules/python/common.cmake"
    common.write_text(common.read_text(encoding="utf-8").replace(
        'string(REPLACE "-Wl,--no-undefined" ""',
        'string(REPLACE "-Wl,--no-undefined " ""'), encoding="utf-8")

    headers = cache / f"python-headers-{HEADERS_VERSION}" / abi
    header_zip = cache / f"target-{HEADERS_VERSION}-{abi}.zip"
    download(f"https://repo.maven.apache.org/maven2/com/chaquo/python/target/{HEADERS_VERSION}/{header_zip.name}", header_zip)
    if not (headers / "include/python3.13/Python.h").is_file():
        with zipfile.ZipFile(header_zip) as zf:
            for member in zf.infolist():
                if member.filename.startswith("include/python3.13/"):
                    zf.extract(member, headers)

    build_dir = cache / "opencv-build" / abi
    def define(name, value):
        return f"-D{name}={value.as_posix() if isinstance(value, Path) else value}"
    options = {
        "CMAKE_TOOLCHAIN_FILE": ndk / "build/cmake/android.toolchain.cmake",
        "ANDROID_ABI": abi, "ANDROID_PLATFORM": "android-28", "ANDROID_STL": "c++_shared",
        "CMAKE_BUILD_TYPE": "Release", "CMAKE_SHARED_LINKER_FLAGS": "-Wl,-z,max-page-size=16384",
        "CMAKE_MODULE_LINKER_FLAGS": "-Wl,-z,max-page-size=16384",
        "BUILD_LIST": "core,imgproc,imgcodecs,python3", "BUILD_SHARED_LIBS": "OFF",
        "BUILD_opencv_python3": "ON", "BUILD_opencv_python2": "OFF",
        "PYTHON3_FOUND": "ON", "PYTHON3_EXECUTABLE": Path(sys.executable),
        "PYTHON_DEFAULT_EXECUTABLE": Path(sys.executable),
        "PYTHON3_INCLUDE_PATH": headers / "include/python3.13",
        "PYTHON3_NUMPY_INCLUDE_DIRS": numpy_headers,
        "PYTHON3_LIBRARIES": python_lib, "PYTHON3_VERSION_MAJOR": "3", "PYTHON3_VERSION_MINOR": "13",
        "PYTHON3_VERSION_STRING": "3.13.15", "PYTHON3_NUMPY_VERSION": "2.3.2",
        "PYTHON3_CVPY_SUFFIX": ".so", "OPENCV_SKIP_PYTHON_LOADER": "ON",
        "OPENCV_FORCE_PYTHON_LIBS": "ON", "OPENCV_PYTHON3_INSTALL_PATH": bundle / "site-packages",
        "BUILD_TESTS": "OFF", "BUILD_PERF_TESTS": "OFF", "BUILD_EXAMPLES": "OFF",
        "BUILD_opencv_java": "OFF", "BUILD_ANDROID_PROJECTS": "OFF", "BUILD_ANDROID_EXAMPLES": "OFF",
        "WITH_OPENCL": "OFF", "WITH_IPP": "OFF", "WITH_ITT": "OFF", "WITH_FFMPEG": "OFF",
        "WITH_TIFF": "OFF", "WITH_WEBP": "OFF", "WITH_OPENEXR": "OFF", "WITH_AVIF": "OFF",
        "WITH_JASPER": "OFF", "WITH_QUIRC": "OFF", "WITH_V4L": "OFF",
        "BUILD_JPEG": "ON", "BUILD_PNG": "ON", "BUILD_ZLIB": "ON",
    }
    subprocess.run(["cmake", "-S", str(source), "-B", str(build_dir), "-G", "Ninja", *[define(k, v) for k, v in options.items()]], check=True)
    subprocess.run(["cmake", "--build", str(build_dir), "--target", "opencv_python3", "--parallel", str(jobs)], check=True)
    compiled = list((build_dir / "lib").glob("**/cv2.so"))
    if len(compiled) != 1:
        raise SystemExit(f"未生成唯一的 cv2 模块: {compiled}")
    module = bundle / "site-packages/cv2.so"
    shutil.copy2(compiled[0], module)
    strip_name = "llvm-strip.exe" if os.name == "nt" else "llvm-strip"
    strip = next((ndk / "toolchains/llvm/prebuilt").glob(f"*/bin/{strip_name}"))
    subprocess.run([str(strip), "--strip-unneeded", str(module)], check=True)
    licenses = bundle / "licenses/opencv"
    licenses.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source / "LICENSE", licenses / "LICENSE")
    # OpenCV 静态链接的第三方依赖也随包保留许可。
    for path in (source / "3rdparty").rglob("*"):
        if path.is_file() and any(word in path.name.lower() for word in ("license", "copying", "copyright")):
            dest = licenses / path.relative_to(source)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, dest)
    print(f"OpenCV {VERSION}: {bundle / 'site-packages/cv2.so'}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--abi", choices=("arm64-v8a", "x86_64"), default="arm64-v8a")
    parser.add_argument("--ndk", type=Path, default=os.environ.get("ANDROID_NDK_ROOT"))
    parser.add_argument("--jobs", type=int, default=min(8, os.cpu_count() or 2))
    args = parser.parse_args()
    if args.ndk is None or not (args.ndk / "build/cmake/android.toolchain.cmake").is_file():
        parser.error("使用 --ndk 指定 Android NDK，或设置 ANDROID_NDK_ROOT")
    build(args.abi, args.ndk.resolve(), args.jobs)
