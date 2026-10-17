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
            self.assertEqual(option["cases"][1]["pipeline_override"]["助战action"]["attach"]["native_setting"], "礼装.png")
            self.assertNotIn("scan_dir", option)

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
