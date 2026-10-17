# 安卓首版模拟器验收记录

日期：2026-10-18。开发分支：`codex/android-app`。

## 环境与产物

- MuMu Player 12，Android 12 / API 32，x86_64，Root 授权。
- 前台模式，主屏 1280×720、DPI 240，从悬浮球面板启动任务。
- 日服包名 `com.aniplex.fategrandorder`，游戏版本 2.139.5。
- 首轮收尾 APK：2.0.9-alpha.15 / versionCode 1195，代码提交 `b6abc5c`；后续兼容版本见文末。
- 本地输出 `Android/out/MaaFGO-android-x86_64-debug.apk` 与 `MaaFGO-android-arm64-v8a-debug.apk`；SHA-256 见同目录 `apk-sha256.json`。

## 已验证结果

| 项目 | 结果与证据 |
| --- | --- |
| APK 安装、Root 服务、资源与 Python Agent | 成功；最终 APK 覆盖安装后服务状态“就绪”，资源标记 1195 |
| 安卓 Python / OpenCV / NumPy / ONNX | CPython 3.13.15、OpenCV 4.12、NumPy 2.3.2；两个模型推理与 Agent 完整导入成功 |
| 日服自动启动与登录 | `run_20261018_012514_1.jsonl`：COMPLETED，1 分 45 秒 |
| 日服日常战斗 | `run_20261018_020044_1.jsonl`：COMPLETED，3 分 54 秒，原生战斗成功 1/1 |
| 日服完整战斗链 | 自动回主界面 → 主线记录 1 → 冬木 → X-A（宅邸残迹）→ 首个助战 → 队伍识别 → 进入关卡 → 出牌 / 宝具 → 结算；未使用苹果 |
| 国服自动登录 | `run_20261018_011624_1.jsonl`：COMPLETED，59 秒 |
| 国服种树 | `run_20261018_011849_1.jsonl`：COMPLETED，5 秒；识别到可转换材料为 0，因此未实际转换 AP |
| 自动检查 | Android 专项 12 项通过；既有回归套件 274 项通过、1 项跳过；生成资源与 interface schema 校验通过 |

战斗运行使用 alpha.14，在面板中明确选择“不食用苹果 / 1 次 / 首个助战 / 不使用 Chaldea 队伍”。最终 alpha.15 只补充选项默认值格式转换，覆盖安装和资源刷新已复验；未重复消耗 AP。成功日志及面板截图保存在本机 `Android/out/mumu-jp-battle-passed.jsonl`、`mumu-jp-battle-passed.png`。

## 本轮修复

- DirectHit 节点没有识别矩形，MaaFramework 5.14.3 的等待稳定动作会报错。安卓资源生成时为此类节点补充显式画面区域。
- 日服主线记录标题与国服不同：新增正式模板到 `resource/base/image/OoTTemple/主线记录1-jp.png`，由日服 pipeline 引用；第一部章节选项不再覆盖区服标题模板。
- MXU 的 `default` 兼容字段不被安卓外壳读取：生成时转换成标准 PI `default_case`，避免“首个助战”误选为“自定义助战”。

## 验证边界

- 当前 MuMu 的后台虚拟屏出现空画面，后台模式未通过；前台模式已完成上述流程。
- Shizuku、ARM64 真机、连续多场、Chaldea 编队与复杂关卡未做本轮端到端验收。
- 原生战斗部分指令卡的颜色 / 归属识别置信度不足时使用现有容错出牌；本轮普通 X-A 成功，不能据此认定精确指令卡策略已全部验证。
- 国服日常导航在早期测试中未通过，本轮转为日服后未复验国服战斗。
- Agent 详细输出会触发面板限流提示，完整信息可从日志导出；该提示不是战斗失败。
- 尚未配置安卓正式签名与 Release / Mirror酱更新源。安装包为本地调试版。

同一 versionCode 调试覆盖安装不会自动刷新已解压 PI。请用“设置 → 项目资源 → 重新解压资源”，必要时重启服务；详见 README。发布新版本时须递增 APK versionCode，保留资源 interface.json 的既有版本同步约定。

## MXU 兼容性补充验收

- 安装版本：2.0.9-alpha.18 / versionCode 1198，提交 `44e378f`；x86_64 与 ARM64 APK 均已重新构建，模拟器安装并启动成功。
- Python 打包专项 14 项通过；安卓真实 ProjectLoader / RunPlanBuilder 的 Kotlin 检查 2 项通过，其中覆盖普通/冠位 1 号/冠位 2 号的满破与非满破共 6 条礼装参数路径。
- 新生成的 Pipeline 与 interface schema 校验通过。6 个动态扫描选项均转为标准 select，每个含 47 个文件选项、图标与默认“不限”。
- MuMu 实际打开普通助战的满破礼装列表，选择“迦勒底午茶时光”，确认配置中持久化的是 `迦勒底午茶时光.png`。截图在本机 `Android/out/mumu-compat-ce-list.png`。
- Chaldea 文件按钮按文本输入回退，链接/ID/手机路径的参数替换和编队说明加载通过 Kotlin 检查；本轮未运行游戏编队。
- UI 检查没有启动战斗、没有消耗 AP。检查后恢复之前的任务配置，SHA-256 校验一致。
- 详细转换方式与保留的限制见 [COMPATIBILITY.md](COMPATIBILITY.md)；构建审计结果在 `Android/out/interface-compatibility.json`。
