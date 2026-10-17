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
