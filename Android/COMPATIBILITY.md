# MXU 扩展在安卓版中的兼容方式

实现位于 `tools/prepare_android.py`，只转换安卓资源副本。桌面选项及既有打包目录保持原样，`interface.json` 的版本字段按源值保留。

核对依据是本机修改版 MXU 的 `src/types/interface.ts`、`src/utils/pipelineOverride.ts`、`src-tauri/src/commands/app_config.rs`，以及固定提交的 MaaFwApp `PiParser.kt`、`RunPlanBuilder.kt`、两个 OptionEditor。文件列表属于 PI/界面端功能，MaaFramework 接收最终的 Pipeline 参数。

| 桌面功能 | 安卓兼容方式 |
| --- | --- |
| `scan_select`、`scan_dir`、`scan_filter` | 打包时枚举文件，生成标准 `select` / `cases`；普通助战、冠位 1 号、冠位 2 号各包含满破和非满破，共 6 组，每组 47 项（含“不限”） |
| 扫描结果的图片与文件名 | 标准 case `icon` 显示图片图标；显示名省略扩展名，传给 Agent 的 case 名和 attach 值仍是完整文件名 |
| `0_空.png` | 显示为“不限”，传参仍为 `0_空.png`，沿用识别脚本原来的跳过校验逻辑 |
| 目录扫描选项的默认值 | 保留有效的已声明默认文件；空默认值优先“不限”；默认文件不存在时构建报错，避免悄悄换成其他礼装 |
| MXU `default` | 转为标准 `default_case`；输入框自身的 `default` 保持原样 |
| 扫描选项的 attach 赋值 | 保留 MXU 按选项名写入 attach 的语义；嵌套结构和其他参数保持不变 |
| Chaldea `input_type: file` 按钮 | 当前外壳没有此按钮，改为标准字符串输入；支持分享链接、队伍/关卡 ID、手机可读 JSON 路径或已有缓存文件名，原 Pipeline 替换逻辑保持不变 |
| 任务 `doc` 独立说明按钮 | 将 Chaldea 自动编队说明并入标准任务 `description`，在选项下方显示 |
| 从者/礼装图标、层级选项、整数/布尔输入、开关 | 使用外壳已经支持的标准 PI 字段；本轮未改写其业务逻辑 |

文件列表反映 APK 内置资源。添加模板需要更新 APK；桌面端的“放入文件夹后点刷新”和大图预览没有直接搬到手机。标准列表仍可切换已有模板，不依赖修改版 MXU。Chaldea 输入框不会把桌面文件路径或 Android `content://` URI 自动转换成手机可读文件。

## 校验

每次生成输出 `Android/out/interface-compatibility.json`，记录实际转换的列表、文件输入和文档。后续出现当前外壳不支持的新选项类型时直接报错，避免功能在界面中消失。

```powershell
python tools/prepare_android.py
python -m unittest discover -s tests -p test_android_packaging.py -v
python tools/check_android_interface.py
```

最后一项将仓库内的 Kotlin 检查暂存到固定版本 MaaFwApp 的单测目录，调用其真实 PI 解析器与执行计划编译器，核对六组礼装的默认值、图标、最终文件名参数，以及 Chaldea 字符串替换和说明显示。检查结束删除暂存文件，不修改外壳源码。

## 合入主干时的 MXU 核验（2026-10-18）

本次将 `codex/android-app` 的 `c85ce8f` 合入 `origin/main` 的 `3c76588`。主干独有的 3 个 merge commit 没有额外文件差异，自动合并无冲突。核验使用独立工作目录及全新 MXU 装配目录，未同步或覆盖任何现有打包版，原工作目录的未提交改动不参与合并。

| 检查 | 结果 |
| --- | --- |
| 桌面入口和依赖 | MXU 打包脚本、workflow、requirements 及 BBC 实现保留，安卓转换只写独立副本；桌面仍注册 19 个 Action 和 2 个 sink，含 BBC 启停、战斗、Chaldea/BBC 双向导入与停止监听 |
| 桌面界面和选项 | 实际调用 MXU 资源、Agent、杂项与 BBC 文件装配方法，25 个任务和 1,151 个展开后的选项保留；8 个 `scan_select`、2 个文件输入、BBC/native 双模式及默认 BBC 均保留 |
| 版本和隔离 | 全新装配使用源版本 `v1.2.28`，Mirror酱配置及 Windows 内嵌 Python 路径保持；9,298 个源文件前后 SHA-256 相同，没有混入 APK、安卓运行时或个人 config。此项未执行桌面框架依赖安装和 MXU GUI 启动；OCR 配置另行验证 |
| 桌面 ONNX 推理 | Windows 使用官方 `onnxruntime.InferenceSession` 和 CPUExecutionProvider；两套真实 YOLO 模型与合并前实现对同一张测试图的完整输出逐元素相同，不走安卓 C API 桥 |
| 章节模板 | 真实 MaaFramework 验证国服、日服各 8 个第一部章节：国服有效模板与 ROI 保持原样，日服使用新增标题模板；27 个章节选项均保留 |
| 回归 | 合并前主干全套 248 项，合并后全套 328 项，无失败；Windows 均有 1 项 tkinter GUI 用例因环境缺 tkinter 跳过。组件测试实际使用 MaaFramework v5.10.4，覆盖 19 副本导航、登录重试、库存失败传播及编队采集失败 |
| 主干 CI | 安卓双 ABI 构建补充 `main` push 触发，安卓专项测试路径也加入 push 过滤；桌面发布仍由原有标签/手动流程控制 |

共享业务确有三类修复一并进入 MXU：日服标题与中途弹窗、白纸化地球 19 副本有界导航与助战正向确认、库存失败正确上报。库存成功链的动作参数未改写；第一部章节仅移除重复的国服模板覆盖，使区服覆盖可以生效。

Chaldea 的来源解析和缓存校验同时改善桌面端。按关卡 ID 搜索队伍不再默认限制 `phase=3`，因此也能找到冠位等 `phase=1` 队伍；这是有意的共享行为变化，显式队伍链接/ID 和显式 phase 参数仍可用。实际游戏筛选、连续战斗等验收边界沿用 [TESTING.md](TESTING.md)，上述装配和探针不替代桌面完整实战。

本机原始日志、源/产物清单与哈希、桌面注册及模型探针保存在 `Android/.cache/main-merge-20261018-162247/`。
