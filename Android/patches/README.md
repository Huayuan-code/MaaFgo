# MaaFGO 的 MaaFwApp 补丁

子模块继续指向公开可获取的固定上游提交；项目差异以本目录按文件名排序的补丁保存，不依赖仅存在于开发电脑上的子模块提交。

常规 `python tools/build_android.py` 构建会自动运行 `tools/apply_android_patches.py`。手动运行外壳 Gradle 前，先在主工程根目录执行：

```powershell
python tools/apply_android_patches.py
```

应用器先执行 `git apply --check`，已应用的补丁通过反向检查确认后跳过，因此重复构建不会叠加修改。遇到上游升级或本地修改冲突时明确失败并保留现有文件；应检查差异并重新生成补丁，勿自动重置子模块。补丁修改后的子模块工作区显示为脏状态是预期行为，主工程只提交补丁文件和应用器。

`0001-preserve-user-config-on-reinstall.patch` 修复手动“重新解压资源”清空本地数据的问题。它保留完整的 `pi/config/`，包括 `Inventory`、`Battle`、`BondCompletion`，其余 PI 资源和临时记录仍重新生成。`config` 不被遍历或搬运；清理其他条目时不跟随符号链接。旧版本的 `pi.roots` 即使误列了 `config`，升级和失败重试也会保留它。APK 内禁止带 `config` 根条目，避免今后误改配方覆盖用户库存；当前 `profile.yaml` 本就不打包该目录。

该补丁保留原安装器的提交标记和归档校验：只有完整解包成功才写版本标记，失败仍可重试。卸载应用、系统“清除数据”仍由 Android 删除全部应用数据，保留规则仅适用于资源更新/重解。

`0002-bind-screen-saver-to-default-display.patch` 将后台屏保明确绑定主屏。应用 Context 在多屏运行时可能将悬浮窗加到当前游戏虚拟屏，遮住识别画面；修复后 View 和 WindowManager 共用主屏的 WindowContext，Android 10 使用 DisplayContext。主屏或 Context 不可用时明确返回失败，不回退到可能盖住游戏的应用 Context。

验证补丁应用器与真实 Kotlin 安装器：

```powershell
python -m unittest discover -s tests -p test_android_patches.py -v
Android/MaaFwApp/gradlew.bat -p Android/MaaFwApp :app:testDebugUnitTest --tests "com.aliothmoon.maafw.project.PiInstaller*"
```

Kotlin 测试使用内存/ZIP 两种包，实际写入和重解文件，检查库存/队伍/羁绊数据的字节内容、资源刷新、失败重试、错误根清单和符号链接边界。Windows 主机若未启用创建符号链接权限，仅两项链接测试按 JUnit 假设跳过；其余保留测试仍实际执行。
