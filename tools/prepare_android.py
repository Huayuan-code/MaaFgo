"""生成 MaaFwApp 资源副本，保留桌面资源和版本字段不变。"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "Android" / "assets"
REMOVED_TASKS = {"启动bbc", "关闭bbc", "BBC 配置转 Chaldea 本地队伍"}
NATIVE_NEXT = [
    "[JumpBack]执行回主界面", "[JumpBack]执行队伍选择", "[JumpBack]执行章节导航",
    "[JumpBack]原生自动战斗_多次入口", "战斗完成信息",
]


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def adapt_wait_freezes(value):
    """DirectHit 没有识别矩形；新版框架需显式指定等待区域。"""
    if isinstance(value, dict):
        recognition = value.get("recognition", "DirectHit")
        kind = recognition.get("type", "DirectHit") if isinstance(recognition, dict) else recognition
        if kind == "DirectHit":
            for key in ("pre_wait_freezes", "post_wait_freezes", "repeat_wait_freezes"):
                wait = value.get(key)
                if isinstance(wait, (int, float)) and wait > 0:
                    value[key] = {"time": wait, "target": [0, 0, 1280, 720]}
                elif isinstance(wait, dict) and wait.get("target", True) is True:
                    wait["target"] = [0, 0, 1280, 720]
        for child in value.values():
            adapt_wait_freezes(child)
    elif isinstance(value, list):
        for child in value:
            adapt_wait_freezes(child)


def copy_agent(source: Path, target: Path):
    def ignore(folder, names):
        patterns = ["__pycache__", "*.pyc"]
        if Path(folder) == source / "custom":
            patterns += ["bbc*.py", "chaldea_import_action.py"]
        return shutil.ignore_patterns(*patterns)(folder, names)
    # chaldea/bbc_formatter.py 是公共包的纯 Python 依赖，不能按文件名前缀全局剔除。
    shutil.copytree(source, target, ignore=ignore)


def load_interface(assets: Path) -> dict:
    """展开 PI imports：列表按声明顺序追加，映射后声明覆盖前声明。"""
    result = {}
    active = set()

    def merge(path):
        path = path.resolve()
        if not path.is_relative_to(assets.resolve()):
            raise ValueError(f"import 越出资源目录: {path}")
        if path in active:
            raise ValueError(f"循环 import: {path}")
        active.add(path)
        data = read_json(path)
        for key, value in data.items():
            if key == "import":
                continue
            if key in ("task", "preset", "group"):
                result.setdefault(key, []).extend(value)
            elif key == "option":
                result.setdefault(key, {}).update(value)
            else:
                result[key] = value
        for imported in data.get("import", []):
            merge(assets / imported)
        active.remove(path)

    merge(assets / "interface.json")
    return result


def option_refs(value):
    if isinstance(value, dict):
        refs = value.get("option", [])
        if isinstance(refs, list):
            yield from (ref for ref in refs if isinstance(ref, str))
        for key, child in value.items():
            # pipeline 的 attach / option 字段不属于 PI 选项依赖。
            if key not in ("pipeline_override", "option"):
                yield from option_refs(child)
    elif isinstance(value, list):
        for child in value:
            yield from option_refs(child)


def adapt_interface(data: dict, assets: Path) -> dict:
    data = copy.deepcopy(data)
    data["description"] = "FGO 安卓自动化助手；使用 Shizuku 或 Root，后台画面固定为 1280×720。"
    # 安卓 APK 随资源更新。桌面 Mirror酱 RID 未配置 APK，不能用于手机更新。
    data.pop("mirrorchyan_rid", None)
    data.pop("mirrorchyan_multiplatform", None)
    data["agent"] = {"child_exec": "python3", "child_args": ["-u", "agent/main.py"]}
    data["task"] = [t for t in data["task"] if t["name"] not in REMOVED_TASKS]
    for task in data["task"]:
        if task["name"] == "直接bbc战斗":
            # 保留内部任务名以兼容既有 pipeline / preset，仅用户文案不再提 BBC。
            task["description"] = "从助战、编队或战斗界面开始原生自动战斗。"
        elif "description" in task:
            for text in ("BBC 战斗或原生自动战斗", "BBC战斗或原生自动战斗", "BBC 或原生自动战斗"):
                task["description"] = task["description"].replace(text, "原生自动战斗")
    for preset in data.get("preset", []):
        preset["task"] = [t for t in preset["task"] if t["name"] not in REMOVED_TASKS]

    options = data["option"]
    for name in ("battle_mode", "主线-战斗方式"):
        option = options[name]
        option["cases"] = [case for case in option["cases"] if case["name"] == "native"]
        option["default"] = "native"
        option["description"] = "安卓版使用原生自动战斗，可导入 Chaldea 队伍。"

    # 只保留可从任务、资源和全局选项到达的选项，去掉 BBC / 模拟器路径配置。
    pending = list(option_refs({key: value for key, value in data.items() if key != "option"}))
    pending.extend(data.get("global_option", []))
    used = set()
    while pending:
        name = pending.pop()
        if name in used:
            continue
        if name not in options:
            raise ValueError(f"缺少选项定义: {name}")
        used.add(name)
        pending.extend(option_refs(options[name]))
    data["option"] = {name: opt for name, opt in options.items() if name in used}

    # MXU 分支独有 scan_select：把已打包图片枚举为标准 PI select。
    for name, option in data["option"].items():
        if option.get("type") != "scan_select":
            continue
        folder = (assets / option.pop("scan_dir")).resolve()
        if not folder.is_relative_to(assets.resolve()):
            raise ValueError(f"scan_dir 越出资源目录: {folder}")
        pattern = option.pop("scan_filter", "*.png")
        files = sorted(folder.glob(pattern), key=lambda p: (not p.name.startswith("0_"), p.name))
        if not files:
            raise ValueError(f"选项 {name} 没有可打包的图片: {folder}")
        override = option.pop("pipeline_override", {})
        cases = []
        for path in files:
            def replace(value):
                if isinstance(value, str):
                    return value.replace("{" + name + "}", path.name)
                if isinstance(value, dict):
                    return {key: replace(child) for key, child in value.items()}
                if isinstance(value, list):
                    return [replace(child) for child in value]
                return value
            cases.append({"name": path.name, "label": path.stem, "pipeline_override": replace(override)})
        option.update(type="select", cases=cases, default=files[0].name)
    return data


def prepare(root: Path = ROOT, output: Path = OUTPUT) -> dict:
    assets = root / "assets"
    interface = adapt_interface(load_interface(assets), assets)
    adapt_wait_freezes(interface)
    output = output.resolve()
    # 此目录只放生成文件；不接受任意用户目录，避免清理误删其他工程文件。
    if output != (root / "Android" / "assets").resolve():
        raise ValueError("输出目录必须是工程内的 Android/assets")
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)
    for folder in ("resource", "i18n"):
        shutil.copytree(assets / folder, output / folder, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".git"))
    copy_agent(root / "agent", output / "agent")
    for name, source in (("Announcement.md", root / "Android/Announcement.md"), ("LICENSE", root / "LICENSE")):
        shutil.copy2(source, output / name)
    write_json(output / "interface.json", interface)

    # 即便某入口未带 battle_mode 选项，也不能落回桌面默认的 BBC 调度。
    daily = output / "resource/base/pipeline/日常战斗.json"
    pipeline = read_json(daily)
    pipeline["通用战斗调度"]["next"] = NATIVE_NEXT
    pipeline["执行bbc战斗"] = {"enabled": False}
    pipeline["执行战斗结束"] = {"enabled": False}
    write_json(daily, pipeline)
    for server in ("cn", "jp"):
        close = output / "resource" / server / "pipeline/关闭游戏.json"
        pipeline = read_json(close)
        pipeline.pop("关闭bbc", None)
        pipeline["关闭游戏"].pop("next", None)
        write_json(close, pipeline)
    for name in ("bbc战斗.json", "BBC配置转Chaldea本地队伍.json", "启动bbc.json", "更新bbc配置文件.json"):
        (output / "resource/base/pipeline" / name).unlink(missing_ok=True)

    for path in (output / "resource").glob("*/pipeline/**/*.json"):
        pipeline = read_json(path)
        original = copy.deepcopy(pipeline)
        adapt_wait_freezes(pipeline)
        if pipeline != original:
            write_json(path, pipeline)

    # OCR 模型既支持仓库现有文件，也支持干净 checkout 的 MaaCommonAssets。
    ocr = output / "resource/model/ocr"
    if not all((ocr / file).is_file() for file in ("rec.onnx", "det.onnx", "keys.txt")):
        common = assets / "MaaCommonAssets/OCR/ppocr_v6/medium"
        if not common.is_dir():
            raise ValueError("OCR 模型缺失，请运行 git submodule update --init assets/MaaCommonAssets")
        shutil.copytree(common, ocr, dirs_exist_ok=True)
    # 对生成包记录哈希；不触碰既有桌面打包目录。
    hashes = {path.relative_to(output).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
              for path in sorted(output.rglob("*")) if path.is_file()}
    write_json(output.parent / "out/resource-sha256.json", hashes)
    return interface


if __name__ == "__main__":
    argparse.ArgumentParser(description=__doc__).parse_args()
    result = prepare()
    print(f"Android 资源已生成: {OUTPUT}，{len(result['task'])} 个任务，{len(result['option'])} 个选项")
