# MaaFGO 安卓版

分支：`codex/android-app`。参考 [MaaEnd Android 接入](https://github.com/MaaEnd/MaaEnd/tree/v2/Android)，使用固定提交的 [MaaFwApp](https://github.com/Aliothmoon/MaaFwApp) 子模块。桌面 MXU 继续使用原来的工程和打包流程。

首版面向 Android 10+ 的 arm64-v8a 手机和 x86_64 模拟器，提供 Shizuku / Root 两种授权方式，支持前台模式和 1280×720、240 DPI 的后台虚拟屏。模拟器后台黑屏时使用前台模式，并将模拟器分辨率设为 1280×720。原生自动战斗、Chaldea 编队、助战筛选和日常任务复用现有 Python Agent。移除 BBC 的任务入口、选项、进程监听和 DLL 依赖。

## 构建

需要 JDK 17+、Python 3.12+、Android SDK。标准环境变量为 `JAVA_HOME`、`ANDROID_HOME`（或 `ANDROID_SDK_ROOT`），NDK 默认从 SDK 下寻找，也可设置 `ANDROID_NDK_ROOT`。

```powershell
git submodule update --init Android/MaaFwApp assets/MaaCommonAssets
sdkmanager --install "platforms;android-37.0" "build-tools;37.0.0" "cmake;3.22.1" "ndk;29.0.14206865"
python tools/build_android.py --check-env
python tools/build_android.py
# MuMu 12 等 x86_64 模拟器
python tools/build_android.py --abi x86_64
```

SDK Manager 使用 command-line tools 19.0（13114758）；CI 固定同一版本。依赖版本记录在 `versions.json`：MaaFramework 与 Python 内核中的 maafw 版本必须一致。

产物：`Android/out/MaaFGO-android-<abi>-debug.apk`。默认 debug 包已经由 Android 调试证书签名，可直接安装。不同电脑的调试证书不同，跨机器升级可能需要先卸载，卸载会清除应用数据。

后续只改任务、图片或 Python 代码时：

```powershell
python tools/build_android.py --skip-runtime
# 模拟器包同样需要指定架构
python tools/build_android.py --abi x86_64 --skip-runtime
```

正式签名包使用 `python tools/build_android.py --release`，需设置 `KEYSTORE_PATH`、`KEYSTORE_PASSWORD`、`KEY_ALIAS`、`KEY_PASSWORD`。密钥不要提交到仓库。当前工作流只产出 Actions 调试附件，未接入正式 Release / Mirror酱 发布。

## 目录和依赖

| 位置 | 内容 |
| --- | --- |
| `MaaFwApp/` | 固定提交的安卓外壳，包含 Shizuku / Root、虚拟屏、任务配置 UI |
| `profile.yaml` | 资源、Python 启动参数、图标、应用名和分辨率 |
| `assets/` | 生成的安卓资源，忽略提交 |
| `agent-dist/<abi>/bundle/` | CPython、NumPy、maafw、交叉编译的 cv2 |
| `.cache/`、`sdk/` | 本地下载、编译缓存和可选本地 SDK，忽略提交 |
| `out/` | APK 与资源 SHA-256 清单，忽略提交 |

`prepare_android.py` 从根目录 `assets/` 展开 PI imports、保留源版本号、剔除 BBC 选项与预设步骤，并将 MXU 专有 `scan_select` 转为标准 PI 图片文件选择。桌面资源和既有打包目录不被修改。

Python 使用 [MaaAgentCoreAndroid](https://github.com/Aliothmoon/MaaAgentCoreAndroid) 的预构建内核。OpenCV 使用官方 4.12.0 源码和 Chaquopy CPython 3.13 目标头文件，由 NDK 编译 `core/imgproc/imgcodecs` 与 Python 绑定。构建脚本仅在下载缓存中启用 Android Python 绑定，并修复上游链接参数替换对 NDK r29 的 `--no-undefined-version` 误处理，显式指定目标 Python 和 NumPy 头文件。模块静态链接 OpenCV，只共享 NDK C++ 运行库，并随包保留第三方许可。

ONNX 推理复用 MaaFramework APK 已附带的 `libonnxruntime.so`，通过稳定的 C API v17 调用；不需要 Android onnxruntime Python wheel。桌面仍使用原来的官方 Python wheel。`psutil` 和 `highspy` 不进入手机运行时；当前任务入口不使用每日任务整数规划求解器。

## 验证与实机验收

```powershell
python -m pip install numpy opencv-python-headless onnxruntime
python -m unittest discover -s tests -p "test_android*.py" -v
python tools/run_tests.py --suite all
```

构建脚本检查 APK 内的 MaaFramework、AgentServer、ONNX、C++ 动态库、Python 入口和 cv2 模块。资源生成时计算 SHA-256，记录到 `out/resource-sha256.json`。

实机依次检查：授权连接 → 选择区服与包名 → 登录 → 种树 → 一场原生战斗 → 停止任务 → Chaldea 队伍 / 自定义助战 / 连续战斗。Shizuku 与 Root 需分别验收；首次开发构建不等于已经通过实机验收。失败时从应用导出日志。

MuMu 12 使用 Root、前台模式和 1280×720。前台任务从悬浮球面板开始：在首页点“打开操作面板”，点屏幕边缘的悬浮球，再点“开始任务”。应用内任务页的开始按钮仅用于后台模式。后台虚拟屏在当前 MuMu 的 FGO 测试中出现空画面，不能视为已经通过后台运行验收。

开发期间在同一个 Git 提交上反复构建，APK 的 versionCode 相同。覆盖安装后需在“设置 → 项目资源 → 重新解压资源”手动刷新 PI；仅更新 APK 不会刷新已解压的旧资源。运行配置与应用日志会保留，资源目录内的 Agent 记录会重置。

## 与桌面版的差异

- 没有 BBC、模拟器路径设置和 BBC 配置转换入口；战斗方式仅有原生模式。
- 图片选择列举 APK 中已有礼装模板。添加自定义图片需重新打包。
- 资源和 Agent 随 APK 更新，桌面 Mirror酱 项目 ID 不用于安卓包更新。
- Chaldea 分享链接 / 队伍 ID 可以直接输入。桌面文件路径不等于手机路径；本地文件导入须以手机实际可读路径为准。
- `config/`、`debug/` 由运行时生成，不复制桌面本地账号配置和库存缓存。
