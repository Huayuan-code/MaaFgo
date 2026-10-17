"""Android PI 转换回归：BBC 隔离、选项依赖、动态图片选择及源文件保护。"""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("prepare_android", ROOT / "tools/prepare_android.py")
android = importlib.util.module_from_spec(spec)
spec.loader.exec_module(android)


class AndroidInterfaceTests(unittest.TestCase):
    def test_mxu_defaults_become_pi_default_case(self):
        source = self.fixture()
        source["option"]["native_setting"] = {
            "type": "select", "default": "first_support",
            "cases": [{"name": "custom_support"}, {"name": "first_support"}],
        }
        converted = android.adapt_interface(source, ROOT / "assets")["option"]["native_setting"]
        self.assertEqual(converted["default_case"], "first_support")
        self.assertNotIn("default", converted)
        self.assertEqual(source["option"]["native_setting"]["default"], "first_support")

    def test_direct_hit_wait_has_an_explicit_area(self):
        nodes = {
            "navigation": {"post_wait_freezes": 1000},
            "explicit": {"pre_wait_freezes": {"time": 500, "target": [10, 20, 30, 40]}},
            "matched": {"recognition": {"type": "TemplateMatch"}, "post_wait_freezes": 800},
            "disabled": {"post_wait_freezes": 0},
        }
        android.adapt_wait_freezes(nodes)
        self.assertEqual(nodes["navigation"]["post_wait_freezes"], {"time": 1000, "target": [0, 0, 1280, 720]})
        self.assertEqual(nodes["explicit"]["pre_wait_freezes"]["target"], [10, 20, 30, 40])
        self.assertEqual(nodes["matched"]["post_wait_freezes"], 800)
        self.assertEqual(nodes["disabled"]["post_wait_freezes"], 0)

    def fixture(self):
        return {
            "version": "v9.8.7", "mirrorchyan_rid": "MaaFgo", "mirrorchyan_multiplatform": True,
            "controller": [{"name": "安卓设备", "type": "Adb"}],
            "task": [{"name": "登录"}, {"name": "启动bbc"}, {"name": "关闭bbc"},
                     {"name": "BBC 配置转 Chaldea 本地队伍"},
                     {"name": "战斗", "option": ["battle_mode", "主线-战斗方式"]}],
            "preset": [{"name": "default", "task": [{"name": "登录"}, {"name": "启动bbc"}, {"name": "战斗"}]}],
            "option": {
                "battle_mode": {"default": "bbc", "cases": [
                    {"name": "bbc", "option": ["windows_path"]}, {"name": "native", "option": ["native_setting"]}]},
                "主线-战斗方式": {"default": "native", "cases": [{"name": "native"}, {"name": "bbc"}]},
                "native_setting": {"type": "input", "inputs": []},
                "windows_path": {"type": "input", "inputs": []},
            },
        }

    def test_native_only_and_does_not_mutate_desktop(self):
        source = self.fixture()
        before = copy.deepcopy(source)
        result = android.adapt_interface(source, ROOT / "assets")
        self.assertEqual(source, before)
        self.assertEqual(result["version"], "v9.8.7")
        self.assertEqual([t["name"] for t in result["task"]], ["登录", "战斗"])
        self.assertEqual([t["name"] for t in result["preset"][0]["task"]], ["登录", "战斗"])
        self.assertNotIn("windows_path", result["option"])
        self.assertNotIn("mirrorchyan_rid", result)
        self.assertEqual(result["option"]["battle_mode"]["default_case"], "native")
        self.assertEqual([c["name"] for c in result["option"]["battle_mode"]["cases"]], ["native"])

    def test_missing_option_fails_build(self):
        source = self.fixture()
        del source["option"]["native_setting"]
        with self.assertRaisesRegex(ValueError, "native_setting"):
            android.adapt_interface(source, ROOT / "assets")

    def test_scan_select_becomes_standard_pi_with_real_filenames(self):
        with tempfile.TemporaryDirectory() as tmp:
            assets = Path(tmp)
            folder = assets / "resource/base/image/lizhuang/满破"
            folder.mkdir(parents=True)
            for name in ("礼装.png", "0_空.png"):
                (folder / name).write_bytes(b"fixture")
            source = self.fixture()
            source["option"]["native_setting"] = {
                "type": "scan_select", "scan_dir": "resource/base/image/lizhuang/满破", "scan_filter": "*.png",
                "pipeline_override": {"助战action": {"attach": {"native_setting": "{native_setting}"}}},
            }
            option = android.adapt_interface(source, assets)["option"]["native_setting"]
            self.assertEqual(option["type"], "select")
            self.assertEqual(option["default_case"], "0_空.png")
            self.assertEqual(option["cases"][0]["label"], "不限")
            self.assertEqual(option["cases"][1]["icon"], "resource/base/image/lizhuang/满破/礼装.png")
            self.assertEqual(option["cases"][1]["pipeline_override"]["助战action"]["attach"]["native_setting"], "礼装.png")
            self.assertNotIn("scan_dir", option)

    def test_scan_default_and_mxu_attach_assignment_are_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            assets = Path(tmp)
            (assets / "images").mkdir()
            (assets / "images/0_空.png").write_bytes(b"fixture")
            (assets / "images/目标.png").write_bytes(b"fixture")
            (assets / "images/目录.png").mkdir()
            source = self.fixture()
            source["option"]["native_setting"] = {
                "type": "scan_select", "scan_dir": "images", "scan_filter": "*.png", "default": "目标.png",
                "pipeline_override": {"node": {"attach": {"native_setting": "", "other": 7}}},
            }
            converted = android.adapt_interface(source, assets)["option"]["native_setting"]
            self.assertEqual(converted["default_case"], "目标.png")
            self.assertEqual(len(converted["cases"]), 2)
            self.assertEqual(converted["cases"][1]["pipeline_override"]["node"]["attach"],
                             {"native_setting": "目标.png", "other": 7})
            source["option"]["native_setting"]["default"] = "已删除.png"
            with self.assertRaisesRegex(ValueError, "默认文件不存在"):
                android.adapt_interface(source, assets)

    def test_file_button_falls_back_to_standard_text_input(self):
        source = self.fixture()
        source["option"]["native_setting"] = {
            "type": "input", "inputs": [{"name": "source", "input_type": "file", "default": "12345"}],
            "pipeline_override": {"node": {"attach": {"source": "{source}"}}},
        }
        converted = android.adapt_interface(source, ROOT / "assets")["option"]["native_setting"]
        self.assertNotIn("input_type", converted["inputs"][0])
        self.assertEqual(converted["inputs"][0]["pipeline_type"], "string")
        self.assertEqual(converted["inputs"][0]["default"], "12345")
        self.assertIn("手机", converted["inputs"][0]["description"])
        self.assertEqual(converted["pipeline_override"], source["option"]["native_setting"]["pipeline_override"])

    def test_mxu_task_doc_becomes_standard_task_description(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "assets").mkdir()
            (root / "docs").mkdir()
            (root / "docs/guide.md").write_text("# 使用说明\n正文", encoding="utf-8")
            source = self.fixture()
            source["task"][0].update(description="任务简介", doc="docs/guide.md")
            converted = android.adapt_interface(source, root / "assets")
            self.assertEqual(converted["task"][0]["description"], "任务简介\n\n# 使用说明\n正文")
            self.assertNotIn("doc", converted["task"][0])

    def test_project_extensions_are_all_converted(self):
        source = android.load_interface(ROOT / "assets")
        converted = android.adapt_interface(source, ROOT / "assets")
        report = android.compatibility_report(source, converted)
        self.assertEqual(len(report["file_lists"]), 6)
        self.assertEqual(len(report["file_inputs_as_text"]), 1)
        self.assertEqual(len(report["task_docs_in_description"]), 1)
        for name, option in converted["option"].items():
            self.assertIn(option.get("type", "select"), android.ANDROID_OPTION_TYPES)
            if source["option"][name].get("type") != "scan_select":
                continue
            for case in option["cases"]:
                self.assertTrue((ROOT / "assets" / case["icon"]).is_file())
                self.assertEqual(case["pipeline_override"]["助战action"]["attach"][name], case["name"])

    def test_unsupported_option_type_fails_instead_of_disappearing(self):
        source = self.fixture()
        source["option"]["native_setting"] = {"type": "desktop_extension"}
        with self.assertRaisesRegex(ValueError, "安卓外壳不支持"):
            android.adapt_interface(source, ROOT / "assets")

    def test_cyclic_import_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            assets = Path(tmp)
            (assets / "interface.json").write_text(json.dumps({"import": ["interface.json"]}), encoding="utf8")
            with self.assertRaisesRegex(ValueError, "循环"):
                android.load_interface(assets)

    def test_import_cannot_escape_assets(self):
        with tempfile.TemporaryDirectory() as tmp:
            assets = Path(tmp)
            (assets / "interface.json").write_text(json.dumps({"import": ["../private.json"]}), encoding="utf8")
            with self.assertRaisesRegex(ValueError, "越出"):
                android.load_interface(assets)

    def test_rejects_output_outside_generated_directory(self):
        with self.assertRaisesRegex(ValueError, "输出目录"):
            # 不需要读取当前仓库中尚未提交的本地 import。
            from unittest.mock import patch
            with patch.object(android, "load_interface", return_value=self.fixture()):
                android.prepare(ROOT, ROOT / "assets")

    def test_only_windows_actions_are_excluded_from_agent(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source"
            for name in ("custom/bbc_start.py", "custom/bbc_connection_manager.py",
                         "custom/auto_battle_action.py", "chaldea/bbc_formatter.py", "chaldea/bbc_importer.py"):
                path = source / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("# fixture", encoding="utf8")
            target = Path(tmp) / "target"
            android.copy_agent(source, target)
            self.assertFalse((target / "custom/bbc_start.py").exists())
            self.assertFalse((target / "custom/bbc_connection_manager.py").exists())
            self.assertTrue((target / "custom/auto_battle_action.py").exists())
            self.assertTrue((target / "chaldea/bbc_formatter.py").exists())
            self.assertTrue((target / "chaldea/bbc_importer.py").exists())


if __name__ == "__main__":
    unittest.main()
