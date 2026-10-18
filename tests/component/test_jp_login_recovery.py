"""用真实 MaaFramework 执行日服提示页、标题页重试和中途弹窗；不连接设备。

保留生产点击区域、next/JumpBack、max_hit、on_error 和全局错误恢复。
只替换 OCR/模板识别并缩短等待，由控制器模拟首次点击丢失和页面变化。
"""
import copy
import json
import os
from pathlib import Path
import tempfile
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
TITLE = "自动登录2"
PROMPT = "自动登录"
HOME = "直到达到主界面"
CLOSE = "如果要关闭"
NOTICE = "关闭主界面弹窗"
NOTICE_ALT = "关闭主界面弹窗2"
CONFIRMED = "确认抵达主界面流程"


class LoginMemoryController(CustomController):
    def __init__(self, *, succeed_after, popup=False, initial="title", prompt_succeed_after=1):
        self.scene = initial
        self.succeed_after = succeed_after
        self.popup = popup
        self.prompt_succeed_after = prompt_succeed_after
        self.prompt_clicks = []
        self.title_clicks = []
        self.popup_clicks = []
        self.unexpected_inputs = []
        super().__init__()

    def connect(self): return True
    def request_uuid(self): return "jp-title-recovery-memory-only"
    def get_features(self): return 0
    def screencap(self): return np.zeros((720, 1280, 3), dtype=np.uint8)

    def click(self, x, y):
        if self.scene == "prompt":
            self.prompt_clicks.append((x, y))
            if (610 <= x < 670 and 665 <= y < 685
                    and self.prompt_succeed_after is not None
                    and len(self.prompt_clicks) >= self.prompt_succeed_after):
                self.scene = "title"
        elif self.scene == "title":
            self.title_clicks.append((x, y))
            # 当前标题截图中的 Touch Screen 区域；旧生产矩形落在其上方。
            if (590 <= x <= 690 and 595 <= y <= 640
                    and self.succeed_after is not None
                    and len(self.title_clicks) >= self.succeed_after):
                self.scene = ("popup" if self.popup is True else self.popup) if self.popup else "home"
        elif self.scene in ("popup", "notice", "notice_alt"):
            self.popup_clicks.append((x, y))
            if 1200 <= x <= 1250 and 0 <= y <= 50:
                self.scene = "home"
        else:
            self.unexpected_inputs.append(("click", x, y))
        return True

    def reject_input(self, *args):
        self.unexpected_inputs.append(args)
        return False

    start_app = stop_app = swipe = touch_down = touch_move = touch_up = reject_input
    click_key = input_text = key_down = key_up = reject_input


class JpLoginRecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        Library.open(Path(os.environ.get("MAAFW_BINARY_PATH", Path(maa.__file__).parent / "bin")))
        Tasker.set_log_dir("")
        Tasker.set_stdout_level(LoggingLevelEnum.Off)
        cls.source = json.loads((ROOT / "assets/resource/jp/pipeline/run_FGO.json").read_text("utf-8"))
        cls.defaults = json.loads((ROOT / "assets/resource/base/default_pipeline.json").read_text("utf-8"))

    def run_login(self, *, succeed_after, popup=False, initial="title", legacy=False,
                  entry=TITLE, prompt_succeed_after=1):
        nodes = {name: copy.deepcopy(self.source[name]) for name in (PROMPT, TITLE, HOME, CLOSE, NOTICE, NOTICE_ALT)}
        controller = LoginMemoryController(succeed_after=succeed_after, popup=popup, initial=initial,
                                           prompt_succeed_after=prompt_succeed_after)
        seen = []

        class Screen(CustomRecognition):
            def analyze(self, context, argv):
                if argv.node_name == PROMPT and controller.scene == "prompt":
                    return (405, 651, 481, 39)  # 本次后台失败现场的实际 OCR 框。
                if argv.node_name == TITLE and controller.scene == "title":
                    return (20, 610, 190, 50)  # 标题页稳定的引继按钮 OCR 锚点。
                if argv.node_name == HOME and controller.scene == "home":
                    return (0, 0, 1, 1)
                if argv.node_name == CLOSE and controller.scene == "popup":
                    return (1200, 0, 50, 50)
                if argv.node_name == NOTICE and controller.scene == "notice":
                    return (1200, 0, 50, 50)
                if argv.node_name == NOTICE_ALT and controller.scene == "notice_alt":
                    return (1200, 0, 50, 50)
                return None

        class Record(CustomAction):
            def run(self, context, argv):
                seen.append(argv.node_name)
                return True

        for node in nodes.values():
            node.pop("focus", None)
            node.update(pre_delay=0, post_delay=0, timeout=40, rate_limit=1)
            node["recognition"] = {"type": "Custom", "param": {"custom_recognition": "screen"}}
        if legacy:
            nodes[TITLE].pop("on_error", None)
        nodes[CONFIRMED] = {"action": {"type": "Custom", "param": {"custom_action": "record"}}}
        # 保留真实 Default.on_error，以检测失败是否错误地转成全局恢复成功。
        nodes["Global_Null"] = {"action": {"type": "Custom", "param": {"custom_action": "record"}}}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "pipeline").mkdir()
            (root / "pipeline/日服登录.json").write_text(json.dumps(nodes, ensure_ascii=False), "utf-8")
            (root / "default_pipeline.json").write_text(json.dumps(self.defaults), "utf-8")
            resource = Resource()
            resource.use_cpu()
            self.assertTrue(resource.post_bundle(root).wait().succeeded)
            resource.register_custom_recognition("screen", Screen())
            resource.register_custom_action("record", Record())
            self.assertTrue(controller.post_connection().wait().succeeded)
            tasker = Tasker()
            self.assertTrue(tasker.bind(resource, controller))
            job = tasker.post_task(entry)
            try:
                deadline = time.monotonic() + 4
                while not job.status.done and time.monotonic() < deadline:
                    time.sleep(.01)
                self.assertTrue(job.status.done, "标题页重试未在上限内结束")
                succeeded = job.status.succeeded
            finally:
                tasker.post_stop().wait()
        self.assertEqual(controller.unexpected_inputs, [])
        return succeeded, controller, seen

    def test_one_lost_click_is_retried_and_reaches_home(self):
        succeeded, controller, seen = self.run_login(succeed_after=2)
        self.assertTrue(succeeded)
        self.assertEqual(len(controller.title_clicks), 2)
        self.assertEqual(seen, [CONFIRMED])
        self.assertEqual(controller.scene, "home")

    def test_popup_jumpback_returns_to_home_check_without_another_title_click(self):
        succeeded, controller, seen = self.run_login(succeed_after=1, popup=True)
        self.assertTrue(succeeded)
        self.assertEqual(len(controller.title_clicks), 1)
        self.assertEqual(len(controller.popup_clicks), 1)
        self.assertEqual(seen, [CONFIRMED])

    def test_three_lost_clicks_end_as_failed_without_global_back_recovery(self):
        succeeded, controller, seen = self.run_login(succeed_after=None)
        self.assertFalse(succeeded)
        self.assertEqual(len(controller.title_clicks), 3)
        self.assertEqual(controller.scene, "title")
        self.assertEqual(seen, [])

    def test_unknown_screen_never_receives_blind_title_click(self):
        succeeded, controller, seen = self.run_login(succeed_after=1, initial="unknown")
        self.assertFalse(succeeded)
        self.assertEqual(controller.title_clicks, [])
        self.assertEqual(seen, [])

    def test_inherited_default_demonstrates_the_false_success_guard_prevents(self):
        succeeded, controller, seen = self.run_login(succeed_after=None, legacy=True)
        self.assertTrue(succeeded)
        self.assertEqual(len(controller.title_clicks), 3)
        self.assertEqual(seen, ["Global_Null"])

    def test_servant_prompt_lost_click_retries_then_reaches_title_and_home(self):
        succeeded, controller, seen = self.run_login(
            succeed_after=1, initial="prompt", entry=PROMPT, prompt_succeed_after=2)
        self.assertTrue(succeeded)
        self.assertEqual(len(controller.prompt_clicks), 2)
        self.assertEqual(len(controller.title_clicks), 1)
        self.assertEqual(seen, [CONFIRMED])

    def test_servant_prompt_exhaustion_stops_without_global_back_recovery(self):
        succeeded, controller, seen = self.run_login(
            succeed_after=1, initial="prompt", entry=PROMPT, prompt_succeed_after=None)
        self.assertFalse(succeeded)
        self.assertEqual(len(controller.prompt_clicks), 3)
        self.assertEqual(controller.title_clicks, [])
        self.assertEqual(controller.scene, "prompt")
        self.assertEqual(seen, [])

    def test_unknown_screen_during_servant_prompt_never_receives_click(self):
        succeeded, controller, seen = self.run_login(
            succeed_after=1, initial="unknown", entry=PROMPT)
        self.assertFalse(succeeded)
        self.assertEqual(controller.prompt_clicks, [])
        self.assertEqual(controller.title_clicks, [])
        self.assertEqual(seen, [])

    def test_intermediate_notices_close_before_home_without_extra_title_click(self):
        for scene in ("notice", "notice_alt"):
            for entry in (PROMPT, TITLE):
                with self.subTest(scene=scene, entry=entry):
                    succeeded, controller, seen = self.run_login(
                        succeed_after=1, initial="prompt" if entry == PROMPT else "title",
                        popup=scene, entry=entry)
                    self.assertTrue(succeeded)
                    self.assertEqual(len(controller.popup_clicks), 1)
                    self.assertEqual(len(controller.prompt_clicks), 1 if entry == PROMPT else 0)
                    self.assertEqual(len(controller.title_clicks), 1)
                    self.assertEqual(seen, [CONFIRMED])


if __name__ == "__main__":
    unittest.main()
