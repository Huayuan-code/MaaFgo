"""真实 MaaFramework 验证库存失败状态；仅替换图像和动作，不连接设备。"""
import copy
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest

import maa
import numpy as np
from maa.controller import CustomController
from maa.custom_action import CustomAction
from maa.custom_recognition import CustomRecognition
from maa.define import LoggingLevelEnum
from maa.library import Library
from maa.resource import Resource
from maa.tasker import Tasker

ROOT = Path(__file__).resolve().parents[2]
ENTRY = "构建个人从者礼装库"
BUILD = "个人库存-执行构建"
FAILED = "个人库存-失败提示"
NAVIGATION = {"个人库存-打开菜单", "个人库存-打开编队菜单", "个人库存-点击灵基一览"}


class InventoryMemoryController(CustomController):
    def __init__(self):
        super().__init__()
        self.inputs = 0

    def connect(self):
        return True

    def request_uuid(self):
        return "inventory-failure-routing"

    def get_features(self):
        return 0

    def screencap(self):
        return np.zeros((720, 1280, 3), dtype=np.uint8)

    def reject_input(self, *args):
        self.inputs += 1
        return False

    start_app = stop_app = click = swipe = touch_down = touch_move = touch_up = reject_input
    click_key = input_text = key_down = key_up = reject_input


class InventoryFailureRoutingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        Library.open(Path(os.environ.get("MAAFW_BINARY_PATH", Path(maa.__file__).parent / "bin")))
        Tasker.set_log_dir("")
        Tasker.set_stdout_level(LoggingLevelEnum.Off)
        cls.nodes = json.loads((ROOT / "assets/resource/base/pipeline/构建个人从者礼装库.json").read_text("utf-8"))
        cls.defaults = json.loads((ROOT / "assets/resource/base/default_pipeline.json").read_text("utf-8"))

    def run_inventory(self, *, hits=NAVIGATION, build_success=True, entry=ENTRY,
                      legacy=False, cancel=False):
        nodes = copy.deepcopy(self.nodes)
        seen = []
        recognition_started = threading.Event()

        class Screen(CustomRecognition):
            def analyze(self, context, argv):
                recognition_started.set()
                return (0, 0, 1, 1) if argv.node_name in hits else None

        class Record(CustomAction):
            def run(self, context, argv):
                seen.append(argv.node_name)
                return build_success if argv.node_name == BUILD else True

        # 保留生产 next/on_error、enabled 和 JumpBack；将视觉与设备动作换成可控结果。
        for node in nodes.values():
            if legacy:
                node.pop("on_error", None)
            node.pop("focus", None)
            for key in ("pre_wait_freezes", "post_wait_freezes", "repeat_wait_freezes"):
                node.pop(key, None)
            node.update(pre_delay=0, post_delay=0, timeout=30_000 if cancel else 30, rate_limit=1)
            recognition = node.get("recognition", {})
            kind = recognition.get("type", "DirectHit") if isinstance(recognition, dict) else recognition
            if kind != "DirectHit":
                node["recognition"] = {"type": "Custom", "param": {"custom_recognition": "screen"}}
                node.pop("inverse", None)
            node["action"] = {"type": "Custom", "param": {"custom_action": "record"}}

        # 模拟原来的全局错误恢复成功：库存任务须禁止该默认路径，其他任务仍应保留。
        nodes["Global_Null"] = {"action": {"type": "Custom", "param": {"custom_action": "record"}}}
        nodes["其他任务"] = {"next": ["其他任务-识别不到"], "timeout": 30, "rate_limit": 1}
        nodes["其他任务-识别不到"] = {
            "recognition": {"type": "Custom", "param": {"custom_recognition": "screen"}},
            "timeout": 30, "rate_limit": 1,
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "pipeline").mkdir()
            (root / "pipeline/库存.json").write_text(json.dumps(nodes, ensure_ascii=False), "utf-8")
            (root / "default_pipeline.json").write_text(json.dumps(self.defaults), "utf-8")
            resource = Resource()
            resource.use_cpu()
            self.assertTrue(resource.post_bundle(root).wait().succeeded)
            resource.register_custom_recognition("screen", Screen())
            resource.register_custom_action("record", Record())
            controller = InventoryMemoryController()
            self.assertTrue(controller.post_connection().wait().succeeded)
            tasker = Tasker()
            self.assertTrue(tasker.bind(resource, controller))
            job = tasker.post_task(entry)
            try:
                if cancel:
                    self.assertTrue(recognition_started.wait(2), "未进入可取消的等待识别阶段")
                    tasker.post_stop().wait()
                    self.assertFalse(tasker.running)
                deadline = time.monotonic() + 4
                while not job.status.done and time.monotonic() < deadline:
                    time.sleep(0.01)
                self.assertTrue(job.status.done, "库存任务出现无界错误恢复")
                succeeded = job.status.succeeded
            finally:
                tasker.post_stop().wait()
            self.assertEqual(controller.inputs, 0)
        return succeeded, seen

    def test_navigation_timeout_is_failed_after_visible_failure_notice(self):
        for missing in NAVIGATION:
            with self.subTest(missing=missing):
                succeeded, seen = self.run_inventory(hits=NAVIGATION - {missing})
                self.assertFalse(succeeded)
                self.assertIn(FAILED, seen)
                self.assertNotIn(BUILD, seen)
                self.assertNotIn("Global_Null", seen)

    def test_legacy_default_recovery_demonstrates_false_success(self):
        succeeded, seen = self.run_inventory(hits={"个人库存-打开菜单"}, legacy=True)
        self.assertTrue(succeeded)
        self.assertIn("Global_Null", seen)
        self.assertNotIn(BUILD, seen)

    def test_scanner_custom_action_failure_is_not_recovered_as_success(self):
        succeeded, seen = self.run_inventory(build_success=False)
        self.assertFalse(succeeded)
        self.assertIn(BUILD, seen)
        self.assertIn(FAILED, seen)
        self.assertNotIn("Global_Null", seen)

    def test_successful_scan_still_completes(self):
        succeeded, seen = self.run_inventory()
        self.assertTrue(succeeded)
        self.assertIn(BUILD, seen)
        self.assertNotIn(FAILED, seen)

    def test_internal_scan_pipeline_returns_failure_to_custom_action(self):
        succeeded, seen = self.run_inventory(hits=set(), entry="个人库存-从者筛选重置")
        self.assertFalse(succeeded)
        self.assertNotIn("Global_Null", seen)

    def test_cancel_during_navigation_stops_without_recovery_or_scan(self):
        # PostStop 的底层 Job 在不同版本/时序下可为 succeeded，UI 取消必须识别外壳的 stopRequested。
        # 此处验证库存闭合错误分支不会妨碍停止，也不会在停止后继续扫描或恢复点击。
        _native_success, seen = self.run_inventory(hits=set(), cancel=True)
        self.assertNotIn(BUILD, seen)
        self.assertNotIn(FAILED, seen)
        self.assertNotIn("Global_Null", seen)

    def test_other_tasks_retain_their_default_error_recovery(self):
        succeeded, seen = self.run_inventory(hits=set(), entry="其他任务")
        self.assertTrue(succeeded)
        self.assertIn("Global_Null", seen)


if __name__ == "__main__":
    unittest.main()
