# MaaFGO 安卓版

分支：`codex/android-app`。参考 [MaaEnd Android 接入](https://github.com/MaaEnd/MaaEnd/tree/v2/Android)，使用固定提交的 [MaaFwApp](https://github.com/Aliothmoon/MaaFwApp) 子模块。桌面 MXU 继续使用原来的工程和打包流程。

首版面向 Android 10+ 的 arm64-v8a 手机和 x86_64 模拟器，提供 Shizuku / Root 两种授权方式，支持前台模式和 1280×720、240 DPI 的后台虚拟屏。后台依赖设备的虚拟屏能力，受限时可改用前台并调整为 16:9。原生自动战斗、Chaldea 编队、助战筛选和日常任务复用现有 Python Agent，实际验收范围见 [TESTING.md](TESTING.md)。移除 BBC 的任务入口、选项、进程监听和 DLL 依赖。

## 从 MXU 移植时的必要适配

采用“共享任务与 Agent，打包时生成安卓资源副本”的方式维护两个平台。MXU 的界面扩展需要转换成 MaaFwApp 支持的标准 PI；运行环境、设备控制和本地路径则按 Android 处理。

| 层面 | 本次适配及维护要点 |
| --- | --- |
| 界面与选项 | 展开 `interface.json` 的 imports；将 `scan_select` 转成标准图片文件列表，保留完整文件名、默认项和 attach 参数；`default` 转 `default_case`；Chaldea 文件按钮退回文本输入，任务说明并入 description。细节见 [COMPATIBILITY.md](COMPATIBILITY.md) |
| Windows 依赖 | 安卓仅保留原生自动战斗，移除 BBC 入口、路径选项、DLL 和进程监听；安卓 Agent 不导入 BBC/psutil。公共 Chaldea 解析依赖仍保留 |
| Python 与原生库 | APK 自带 CPython、NumPy、maafw 和 NDK 编译的 cv2；MaaFramework 与 Python 内核的 maafw 版本必须匹配。启动时配置 Python 路径及原生库路径，不能直接复用 Windows wheel |
| YOLO 与 OCR | 保留 `support_det.onnx`、`quest_detect.onnx` 及 OCR 模型；安卓通过 APK 的 `libonnxruntime.so` C API v17 推理，桌面继续使用官方 Python wheel。当前安卓桥用于单输入 float32 图像模型、CPU 推理 |
| 控制与后台 | 使用 Shizuku/Root 服务采集和注入触摸；后台把游戏启动到独立虚拟屏。修复日服声明页焦点、标题点击位置与有限重试，并为 DirectHit 的稳定等待补齐明确区域。共享 Pipeline 还需检查零尺寸点击区域、转场确认及失败传播；白纸化地球 19 个副本已补齐相关保护 |
| 分辨率与生命周期 | 后台固定 1280×720 / DPI 240，前台要求 16:9；任务间尺寸改变后重建 controller/tasker。屏保放在主 Activity 的 Compose 树中，恢复亮度与唤醒标记，避免遮挡虚拟屏；运行中改尺寸/旋转仍需先停止 |
| 数据与文件输入 | Agent 工作目录对齐手机 PI 根目录；库存、Chaldea 缓存和羁绊进度放在 `pi/config/`。升级及手动重解保留整个 config；文件输入使用手机可读路径，`content://` 不会自动转换。库存失败须明确报错，已有有效数据不能被不完整结果覆盖 |
| Chaldea 数据链 | 复用编队与缓存业务，修复分享链接/Base64 解析、phase 默认过滤和缓存关卡匹配。支持手机直接获取链接；当前原生策略不能保证复现分享中的指定 Arts 面卡顺序 |
| 构建与更新 | 固定公开上游子模块，定制保存为可重放的 [0001–0004 补丁](patches/README.md)；分别构建 ARM64/x86_64，递增 APK versionCode。安卓更新源和签名独立配置，源 interface 版本保留，桌面打包版同步仍遵守原版本保护约定 |

后续新增 MXU 专属字段时，应同步补充 `tools/prepare_android.py` 的转换、打包回归和真实 Kotlin PI/执行计划检查。修改安卓生成目录会在下次生成时被覆盖，应修改源文件或转换器。新增外壳定制应更新补丁，而非只留下本机子模块修改。

当前已完成 APK 构建、MuMu 授权连接、登录、原生单场战斗、后台/屏保、库存落盘与读取、Chaldea 下载缓存，以及超宽逻辑主屏测试。ARM64 真机、完整自定义助战/自动编队/羁绊补齐、连续战斗和异常恢复仍需独立验收；正式签名与发布更新源尚未配置。具体日志、版本及边界以 [TESTING.md](TESTING.md) 为准。

## 构建

需要完整 JDK 17+（含 `javac`、`jlink`，本机实测 JDK 21）、Python 3.12+、Android SDK。标准环境变量为 `JAVA_HOME`、`ANDROID_HOME`（或 `ANDROID_SDK_ROOT`），NDK 默认从 SDK 下寻找，也可设置 `ANDROID_NDK_ROOT`。

外壳 APK 安装下限为 API 28 / Android 9，后台模式要求 API 29 / Android 10 以上；当前支持目标为 Android 10+，实测设备为 MuMu Android 12 / API 32。安装下限不代表对应系统已验收。

```powershell
git submodule update --init Android/MaaFwApp assets/MaaCommonAssets
sdkmanager --install "platforms;android-37.0" "build-tools;37.0.0" "cmake;3.22.1" "ndk;29.0.14206865"
python tools/build_android.py --check-env
python tools/build_android.py
# MuMu 12 等 x86_64 模拟器
python tools/build_android.py --abi x86_64
```

SDK Manager 使用 command-line tools 19.0（13114758）；CI 固定同一版本。依赖版本记录在 `versions.json`：MaaFramework 与 Python 内核中的 maafw 版本必须一致。

常规构建自动应用 `patches/` 中的外壳补丁，重复运行会跳过已应用的补丁。直接运行子模块 Gradle 前须先执行 `python tools/apply_android_patches.py`；补丁冲突会明确报错，具体行为和测试见 [patches/README.md](patches/README.md)。子模块保留公开的上游提交，定制改动由可重放补丁记录。

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

MXU 扩展字段的逐项兼容方式、文件按钮退回文本输入的限制，以及安卓真实解析器检查，见 [COMPATIBILITY.md](COMPATIBILITY.md)。

Python 使用 [MaaAgentCoreAndroid](https://github.com/Aliothmoon/MaaAgentCoreAndroid) 的预构建内核。OpenCV 使用官方 4.12.0 源码和 Chaquopy CPython 3.13 目标头文件，由 NDK 编译 `core/imgproc/imgcodecs` 与 Python 绑定。构建脚本仅在下载缓存中启用 Android Python 绑定，并修复上游链接参数替换对 NDK r29 的 `--no-undefined-version` 误处理，显式指定目标 Python 和 NumPy 头文件。模块静态链接 OpenCV，只共享 NDK C++ 运行库，并随包保留第三方许可。

ONNX 推理复用 MaaFramework APK 已附带的 `libonnxruntime.so`，通过稳定的 C API v17 调用；不需要 Android onnxruntime Python wheel。桌面仍使用原来的官方 Python wheel。`psutil` 和 `highspy` 不进入手机运行时；当前任务入口不使用每日任务整数规划求解器。

## 验证与实机验收

本次 MuMu 安装、日服登录和一场原生战斗的具体结果与验证边界见 [TESTING.md](TESTING.md)。

```powershell
python -m pip install numpy opencv-python-headless onnxruntime
python -m unittest discover -s tests -p "test_android*.py" -v
python tools/run_tests.py --suite all
```

构建脚本检查 APK 内的 MaaFramework、AgentServer、ONNX、C++ 动态库、Python 入口和 cv2 模块。资源生成时计算 SHA-256，记录到 `out/resource-sha256.json`。

实机依次检查：授权连接 → 选择区服与包名 → 登录 → 种树 → 一场原生战斗 → 停止任务 → Chaldea 队伍 / 自定义助战 / 连续战斗。Shizuku 与 Root 需分别验收；首次开发构建不等于已经通过实机验收。失败时从应用导出日志。

MuMu 12 的前台任务从悬浮球面板开始：在首页点“打开操作面板”，点屏幕边缘的悬浮球，再点“开始任务”。应用内任务页的开始按钮用于后台模式。日服启动声明页已加入识别后恢复窗口焦点，解决本机 Android 12 虚拟屏冷启动停住的问题；Shizuku、库存落盘、屏保与后台战斗分别验收，具体边界见 [TESTING.md](TESTING.md)。

超宽屏优先选择后台模式：游戏在固定 `1280×720 / DPI 240` 虚拟屏运行，主屏无需改成 16:9。MuMu 将逻辑主屏设为 `2160×720` 后已验证 Shizuku 后台登录、截图和日服 X-A 一场完整战斗。前台按主屏实际画面操作，目前要求 16:9；首页“修改分辨率”会改变系统显示尺寸，用完可“重置分辨率”。任务之间调整尺寸后控制器会按新的触摸范围重建；任务运行中应先停止，再调整和重开。模拟器的逻辑尺寸测试不替代 ARM64 手机、异形屏和厂商后台限制验收。

本机现已通过 Root 后台单场原生战斗、Shizuku 后台冷启动与仓库统计、屏保重复显隐/自动收尾，以及退回模拟器桌面后继续运行。屏保为应用内黑底与最低亮度，需要 MaaFGO 界面可见；任务仍在虚拟屏服务中执行。ARM64 真机与完整 Chaldea 编队实战仍需另测。

ARM64 包在本机 x86_64 MuMu 上的转译验收未通过：可以安装并打开界面，但 Root/Shizuku 特权服务由 x86_64 的系统 `app_process` 启动，无法加载 ARM64 的 `libbridge.so`；独立 MaaFramework/ONNX 探针也出现崩溃。MuMu 使用已验收的 x86_64 包，ARM64 完整流程须在真正的 ARM64 设备继续验证，详细分层结果见 [TESTING.md](TESTING.md)。

“构建个人从者礼装库”会将两库保存到应用外部文件目录的 `pi/config/Inventory/`。Chaldea 分享链接可直接粘贴到“Chaldea 队伍导入”，手机下载并缓存到 `pi/config/Battle/`，无需桌面预先下载 JSON。

开发期间在同一个 Git 提交上反复构建，APK 的 versionCode 相同。覆盖安装后需在“设置 → 项目资源 → 重新解压资源”手动刷新 PI；仅更新 APK 不会刷新已解压的旧资源。运行配置、应用日志及 `pi/config/` 内的库存、队伍缓存和羁绊进度会保留，PI 内其他临时记录会重置。

## 与桌面版的差异

- 没有 BBC、模拟器路径设置和 BBC 配置转换入口；战斗方式仅有原生模式。
- 图片选择列举 APK 中已有礼装模板。添加自定义图片需重新打包。
- 资源和 Agent 随 APK 更新，桌面 Mirror酱 项目 ID 不用于安卓包更新。
- Chaldea 分享链接 / 队伍 ID 可以直接输入。桌面文件路径不等于手机路径；本地文件导入须以手机实际可读路径为准。
- `config/`、`debug/` 由运行时生成，不复制桌面本地账号配置和库存缓存。
