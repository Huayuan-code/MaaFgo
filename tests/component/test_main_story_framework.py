"""真实 MaaFramework 资源、Context 克隆及动作调用；仅使用内存控制器。"""
from pathlib import Path
import sys
import time
import unittest
from unittest.mock import patch

import maa
import numpy as np
from maa.controller import CustomController
from maa.custom_action import CustomAction
from maa.define import LoggingLevelEnum
from maa.library import Library
from maa.resource import Resource
from maa.tasker import Tasker

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "agent"), str(ROOT / "agent/custom")]
from main_story_action import MainStoryAction, StoryRunner, StoryStopped, map_swipes, next_names
from main_story_recognition import MainStoryNext


class ScreenController(CustomController):
    def __init__(self, image):
        self.image, self.clicks, self.swipes = image, [], []
        super().__init__()

    def connect(self): return True
    def request_uuid(self): return "story-memory-only"
    def get_features(self): return 0
    def screencap(self): return self.image.copy()
    def click(self, x, y):
        self.clicks.append((x, y))
        return True
    def swipe(self, x1, y1, x2, y2, duration):
        self.swipes.append((x1, y1, x2, y2))
        return True
    def reject(self, *args): return False
    start_app = stop_app = touch_down = touch_move = touch_up = reject
    click_key = input_text = key_down = key_up = reject


class FrameworkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        Library.open(Path(maa.__file__).parent / "bin")
        Tasker.set_log_dir("")
        Tasker.set_stdout_level(LoggingLevelEnum.Off)

    def resource(self, server):
        resource = Resource()
        resource.use_cpu()
        for folder in ("base", server):
            self.assertTrue(resource.post_bundle(ROOT / "assets/resource" / folder).wait().succeeded)
        return resource

    def test_both_bundles_and_normalized_route(self):
        for server in ("cn", "jp"):
            with self.subTest(server=server):
                resource = self.resource(server)
                self.assertEqual(resource.get_node_data("主线-配置")["attach"]["server"], server)
                route = list(map_swipes(resource))
                self.assertEqual(route[:5], ["巡-初始化左滑"] * 5)
                self.assertEqual(route[-1], "巡-左4c")
                self.assertEqual(next_names(resource.get_node_data("全局-战前吃体力")), ["全局-体力不足"])

    def test_main_story_abort_fails_without_global_recovery_or_inputs(self):
        reason = "已进入编队，但关卡要求指定首发队员；请按编制限制弹窗手动调整"
        for server in ("cn", "jp"):
            for outcome in (StoryStopped(reason), RuntimeError("截图失败"), None):
                with self.subTest(server=server, outcome=outcome):
                    resource = self.resource(server)
                    self.assertEqual(resource.get_node_data("自动推主线调度")["on_error"], [])
                    controller = ScreenController(np.zeros((720, 1280, 3), np.uint8))
                    self.assertTrue(controller.post_connection().wait().succeeded)
                    visited, messages = [], []

                    class FakeRunner:
                        completed, battles = 3, 0

                        def run(self):
                            if outcome is not None:
                                raise outcome
                            return "达到推进上限：已推进 3 关，完成战斗 0 场"

                    class Record(CustomAction):
                        def run(self, ctx, argv):
                            visited.append(argv.node_name)
                            if argv.node_name == "主线-结果提示":
                                messages.append(ctx.get_node_data(argv.node_name)["focus"]["Node.Action.Starting"])
                            return True

                    resource.register_custom_action("auto_main_story", MainStoryAction())
                    resource.register_custom_action("record_story_exit", Record())
                    # 保留全局恢复的入口和链路，但用无输入记录器代替设备操作。
                    # 若入口再次遗漏 on_error: []，会访问这些节点并误变成成功。
                    overrides = {}
                    chain = ("Global_Null", "其他异常", "回主界面")
                    for index, name in enumerate(chain):
                        overrides[name] = {
                            "recognition": {"type": "DirectHit"},
                            "action": {"type": "Custom", "param": {"custom_action": "record_story_exit"}},
                            "next": [chain[index + 1]] if index + 1 < len(chain) else [],
                            "on_error": [], "pre_delay": 0, "post_delay": 0, "post_wait_freezes": 0,
                        }
                    overrides["主线-结果提示"] = {
                        "action": {"type": "Custom", "param": {"custom_action": "record_story_exit"}},
                        "pre_delay": 0, "post_delay": 0,
                    }
                    tasker = Tasker()
                    self.assertTrue(tasker.bind(resource, controller))
                    try:
                        with patch("main_story_action.StoryRunner", return_value=FakeRunner()):
                            job = tasker.post_task("自动推主线调度", overrides)
                            deadline = time.monotonic() + 10
                            while not job.status.done and time.monotonic() < deadline:
                                time.sleep(0.01)
                            self.assertTrue(job.status.done, "主线中断后没有及时结束任务")
                            self.assertEqual(job.status.succeeded, outcome is None)
                        self.assertEqual(visited, ["主线-结果提示"])
                        self.assertEqual(len(messages), 1)
                        if outcome is not None:
                            self.assertIn(f"主线中断：{outcome}", messages[0])
                            self.assertIn("已推进 3 关，完成战斗 0 场", messages[0])
                        self.assertEqual(controller.clicks, [])
                        self.assertEqual(controller.swipes, [])
                    finally:
                        tasker.post_stop().wait()

    def test_cloned_context_does_not_leak_and_swipe_is_one_step(self):
        resource = self.resource("cn")
        controller = ScreenController(np.zeros((720,1280,3),np.uint8))
        self.assertTrue(controller.post_connection().wait().succeeded)
        checks, errors = [], []
        class Probe(CustomAction):
            def run(self, ctx, argv):
                try:
                    ctx.override_pipeline({"进本流程": {"next": ["助战action", "进本-队伍确认"]}})
                    local = ctx.clone()
                    checks.append(next_names(local.get_node_data("进本流程")) ==
                                  ["助战action", "进本-队伍确认"])
                    local.override_pipeline({"主线-配置": {"attach": {"quest_limit": 1}}})
                    checks.append(ctx.get_node_data("主线-配置")["attach"]["quest_limit"] == 10)
                    runner = StoryRunner(local)
                    runner.action("巡-初始化左滑", override={"巡-初始化左滑": {"repeat": 1}})
                    # 规范化 next 下仍正确阻止默认 AP 分支，避免进入 StopTask。
                    runner.reco = lambda name, image: name == "全局-战前吃体力"
                    try:
                        runner.interrupt(None, entering=True)
                    except StoryStopped as exc:
                        checks.append("AP 不足" in str(exc))
                    return True
                except Exception as exc:
                    errors.append(repr(exc))
                    return False
        resource.register_custom_action("story_probe", Probe())
        tasker = Tasker()
        self.assertTrue(tasker.bind(resource, controller))
        status = tasker.post_task("story_probe", {"story_probe": {
            "action": {"type":"Custom","param":{"custom_action":"story_probe"}}
        }}).wait()
        self.assertTrue(status.succeeded, errors)
        self.assertEqual(checks, [True, True, True])
        self.assertEqual(len(controller.swipes), 1)
        self.assertEqual(controller.clicks, [])

    def test_custom_support_runs_with_recognition_detail(self):
        resource = self.resource("cn")
        controller = ScreenController(np.zeros((720, 1280, 3), np.uint8))
        self.assertTrue(controller.post_connection().wait().succeeded)
        seen, errors = [], []

        class Inner(CustomAction):
            def run(self, ctx, argv):
                seen.append((argv.node_name, argv.reco_detail.reco_id))
                return True

        class Outer(CustomAction):
            def run(self, ctx, argv):
                try:
                    runner = StoryRunner(ctx.clone())
                    for name in ("助战action", "Chaldea助战action"):
                        runner.task(name, {name: {
                            "recognition": {"type": "DirectHit"},
                            "action": {"type": "Custom", "param": {
                                "custom_action": "story_support_probe"
                            }},
                            "next": [],
                            "on_error": [],
                        }})
                    return True
                except Exception as exc:
                    errors.append(repr(exc))
                    return False

        resource.register_custom_action("story_support_probe", Inner())
        resource.register_custom_action("story_outer_probe", Outer())
        tasker = Tasker()
        self.assertTrue(tasker.bind(resource, controller))
        status = tasker.post_task("story_outer_probe", {"story_outer_probe": {
            "action": {"type": "Custom", "param": {
                "custom_action": "story_outer_probe"
            }}
        }}).wait()
        self.assertTrue(status.succeeded, errors)
        self.assertEqual([name for name, _ in seen],
                         ["助战action", "Chaldea助战action"])
        self.assertTrue(all(reco_id > 0 for _, reco_id in seen))
        self.assertEqual(controller.clicks, [])

    def test_custom_next_returns_click_point_through_framework(self):
        sys.path.insert(0, str(ROOT / "tests"))
        from test_main_story import NextImageTests
        fixture = NextImageTests()
        resource = self.resource("cn")
        image, _, _, box = fixture.scene("cn", panel=True)
        controller = ScreenController(image)
        self.assertTrue(controller.post_connection().wait().succeeded)
        resource.register_custom_recognition("main_story_next", MainStoryNext())
        tasker = Tasker()
        self.assertTrue(tasker.bind(resource,controller))
        self.assertTrue(tasker.post_task("主线-列表NEXT").wait().succeeded)
        self.assertEqual(controller.clicks, [(round(box[0]+box[2]/2), round(box[1]+box[3]/2+100*2/3))])


if __name__ == "__main__":
    unittest.main()
