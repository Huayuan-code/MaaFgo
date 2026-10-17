# MaaFGO 的 MaaFwApp 补丁

子模块继续指向公开可获取的固定上游提交；项目差异以本目录按文件名排序的补丁保存，不依赖仅存在于开发电脑上的子模块提交。

常规 `python tools/build_android.py` 构建会自动运行 `tools/apply_android_patches.py`。手动运行外壳 Gradle 前，先在主工程根目录执行：

```powershell
python tools/apply_android_patches.py
```

应用器先执行 `git apply --check`，已应用的补丁通过反向检查确认后跳过，因此重复构建不会叠加修改。遇到上游升级或本地修改冲突时明确失败并保留现有文件；应检查差异并重新生成补丁，勿自动重置子模块。补丁修改后的子模块工作区显示为脏状态是预期行为，主工程只提交补丁文件和应用器。

`0001-preserve-user-config-on-reinstall.patch` 修复手动“重新解压资源”清空本地数据的问题。它保留完整的 `pi/config/`，包括 `Inventory`、`Battle`、`BondCompletion`，其余 PI 资源和临时记录仍重新生成。`config` 不被遍历或搬运；清理其他条目时不跟随符号链接。旧版本的 `pi.roots` 即使误列了 `config`，升级和失败重试也会保留它。APK 内禁止带 `config` 根条目，避免今后误改配方覆盖用户库存；当前 `profile.yaml` 本就不打包该目录。

该补丁保留原安装器的提交标记和归档校验：只有完整解包成功才写版本标记，失败仍可重试。卸载应用、系统“清除数据”仍由 Android 删除全部应用数据，保留规则仅适用于资源更新/重解。

`0002-bind-screen-saver-to-default-display.patch` 在 AppRoot 现有主屏 Compose 树中显示屏保，不新建 Window 或 ViewRoot，避免 ROM 的悬浮窗重定向和重复开窗不绘制问题。手动与自动入口共用弱引用宿主和显示状态；仅可见主屏 Activity 可显示，隐藏/解绑/换宿主时恢复原亮度与 KEEP_SCREEN_ON 位。屏保期间主界面视觉内容及 Dialog 暂停组合，可保存状态和文件选择回调保持；虚拟屏 native 截图与任务继续运行。

`0003-skip-unconfigured-startup-update.patch` 在当前所选更新源缺配置时跳过启动自检，避免调试包每次启动弹错；不切换更新源，不更改用户设置。手动检查仍显示缺少配置的具体原因。

`0004-refresh-controller-for-capture-size.patch` 将 native controller 的缓存键扩展为实际 `displayId`、`width`、`height` 和 `forceStop`。每轮准备时只读取一次采集目标，比例检查、缓存比较与 `screen_resolution` 配置共用该快照。前台取主屏采集器的真实尺寸，后台取虚拟屏的真实配置，忽略可能过期的 payload 尺寸。同一显示器更换分辨率后重新创建 controller 和 tasker，先把存活 Agent 的 sink 登记到新对象，再销毁旧指针；连接失败时保留原对象，释放 controller 时清空缓存键。

该补丁同时在实际 `prepare` 入口检查前台画面是否为 16:9。主屏为 `2160×720` 等不支持比例时，在加载资源、Agent 或创建 native controller 前明确失败，并提示切换后台模式或调整主屏分辨率；不自动修改系统显示设置。后台仍按其虚拟屏尺寸运行，不受主屏宽高影响。这是任务准备阶段的保护，不代表已支持任务执行中的任意旋转或分辨率切换。

验证补丁应用器与外壳 Kotlin 回归：

```powershell
python -m unittest discover -s tests -p test_android_patches.py -v
Android/MaaFwApp/gradlew.bat -p Android/MaaFwApp :app:testDebugUnitTest --tests "com.aliothmoon.maafw.project.PiInstaller*" --tests "com.aliothmoon.maafw.remote.MaaRunnerControllerTargetTest"
```

Kotlin 测试使用内存/ZIP 两种包，实际写入和重解文件，检查库存/队伍/羁绊数据的字节内容、资源刷新、失败重试、错误根清单和符号链接边界。Windows 主机若未启用创建符号链接权限，仅两项链接测试按 JUnit 假设跳过；其余保留测试仍实际执行。

`MaaRunnerControllerTargetTest` 直接调用真实 Runner 的准备与释放方法，显示服务和 native 接口使用替身。8 项用例覆盖同屏换尺寸、对象复用与断连重建、快照只读一次、替换连接失败、销毁顺序、宽主屏下后台仍使用虚拟屏配置、前台非 16:9 提前失败，以及采集未启动时不使用兜底尺寸；不以这些用例替代模拟器或真机运行。
