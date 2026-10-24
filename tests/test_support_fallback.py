"""助战刷新兜底与战斗会话的离线回归测试，不连接设备。"""
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from formation_test_support import ROOT, battle_action as battle
from support_action import SupportAction
from battle.core.models import FormationSlot, REQUIRED_FRAME_COUNT
from battle.runtime.formation_session import sessions


class Context:
    def __init__(self, enabled=True):
        self.root = 3456
        self.token = sessions.begin(self.root, repeat=True)
        self.tasker = NS(stopping=False, controller=object())
        self.attach = {
            "fallback_after_refresh": enabled,
            "class_name": "剑士", "class_all": "def", "servant": "test",
            "礼装状态": "满破", "普通助战-礼装-满破": "",
            "np_level": 1, "level": 1,
            **{f"skill_active_{i}": 0 for i in range(1, 4)},
            **{f"skill_passive_{i}": 0 for i in range(1, 6)},
        }
        self.refreshes = 0
        self.entries = []
        self.fail_entry = None

    def get_task_job(self):
        return NS(job_id=self.root)

    def get_node_data(self, name):
        if name == "编队身份-会话":
            return {"attach": {"session_id": self.token}}
        if name == "资源包配置":
            return {"attach": {"resource_package": "base"}}
        return {"attach": self.attach}

    def run_task(self, entry, pipeline_override=None):
        self.entries.append(entry)
        if entry == "助战刷新":
            self.refreshes += 1
        return NS(status=NS(succeeded=entry != self.fail_entry))


class SupportFallbackTests(unittest.TestCase):
    def setUp(self):
        sessions.stop_owner("")
        self.addCleanup(sessions.stop_owner, "")
        for target, value in (
            ("support_action.time.sleep", None),
            ("support_action.mfaalog.info", None),
            ("support_action.mfaalog.error", None),
            ("support_action.MAX_SWIPE_BEFORE_REFRESH", 2),
        ):
            p = patch(target, value) if isinstance(value, int) else patch(target)
            p.start()
            self.addCleanup(p.stop)

    def search(self, context, match=None):
        action = SupportAction()
        detector = NS(detect=lambda img: [(0, 0, 100, 100, .99)])
        mocks = {
            "_get_servant_map": {"test": {"images": ["test.png"]}},
            "_get_detector": detector, "_init_scale": None, "_tap": None,
            "_swipe": None, "_shot_base": object(), "_ref_shift": (0, 0),
            "_match_ce": True, "_check_active_view": True, "_is_connecting": False,
        }
        for name, result in mocks.items():
            setattr(action, name, Mock(return_value=result))
        action._match_servant = Mock(side_effect=match or (lambda *args: False))
        result = action.run(context, NS(node_name="助战action", custom_action_param="{}"))
        return result, action

    def test_ten_refreshes_then_fallback_and_clear_stale_formation(self):
        ctx = Context()
        slots = tuple(FormationSlot(i, "unknown", is_support=False) for i in range(1, 7))
        revision = sessions.begin_capture(ctx.root, ctx.token)
        for _ in range(REQUIRED_FRAME_COUNT):
            sessions.append_frame(ctx.root, ctx.token, revision, slots)
        sessions.publish(ctx.root, ctx.token, revision, slots, "test")
        result, action = self.search(ctx)
        self.assertTrue(result.success)
        self.assertEqual(ctx.refreshes, 10)
        self.assertEqual(ctx.entries[-1], "助战兜底-选择首个助战")
        # 初始列表和10次刷新后的列表都检查顶部及两次滑动。
        self.assertEqual(action._match_servant.call_count, 33)
        self.assertTrue(sessions.support_fallback(ctx.root, ctx.token))
        self.assertIsNone(sessions.read(ctx.root, ctx.token)[0])

    def test_target_on_tenth_refreshed_top_row_wins_and_clears_fallback(self):
        ctx = Context()
        sessions.set_support_fallback(ctx.root, ctx.token, True)
        result, _ = self.search(ctx, lambda *args: ctx.refreshes == 10)
        self.assertTrue(result.success)
        self.assertEqual(ctx.refreshes, 10)
        self.assertNotIn("助战兜底-选择首个助战", ctx.entries)
        self.assertFalse(sessions.support_fallback(ctx.root, ctx.token))

    def test_default_disabled_continues_past_ten_until_stopped(self):
        ctx = Context(enabled=False)
        def match(*args):
            if ctx.refreshes > 10:
                ctx.tasker.stopping = True
            return False
        result, _ = self.search(ctx, match)
        self.assertFalse(result.success)
        self.assertEqual(ctx.refreshes, 11)
        self.assertNotIn("助战兜底-选择首个助战", ctx.entries)
        self.assertFalse(sessions.support_fallback(ctx.root, ctx.token))

    def test_refresh_or_first_support_failure_does_not_enable_fallback(self):
        for entry in ("助战刷新", "助战兜底-选择首个助战"):
            with self.subTest(entry=entry):
                ctx = Context()
                ctx.fail_entry = entry
                result, _ = self.search(ctx)
                self.assertFalse(result.success)
                self.assertFalse(sessions.support_fallback(ctx.root, ctx.token))

    def test_stop_before_fallback_does_not_click(self):
        ctx = Context()
        ctx.tasker.stopping = True
        action = SupportAction()
        action._tap = Mock()
        self.assertFalse(action._select_fallback(ctx, object(), ctx.root, ctx.token).success)
        action._tap.assert_not_called()

    def test_runtime_ignores_explicit_plan_share_source_and_policies(self):
        ctx = Context()
        sessions.set_support_fallback(ctx.root, ctx.token, True)
        param = {"chaldea_import_source": "must-not-fetch", "chaldea_share": {"actions": []},
                 "plan": {"turns": [{"np_order": [3]}]},
                 "skill_policy": {"auto_servant_skills": False}}
        with patch.object(battle, "fetch_share_data", side_effect=AssertionError("must not fetch")), \
             patch.object(battle, "_parse_plan", wraps=battle._parse_plan) as parse, \
             patch.object(battle, "AutoBattleRuntime") as runtime:
            runtime.return_value.run.return_value = NS(ok=True, reason="victory", turns=1)
            self.assertTrue(battle.AutoBattleAction().run(ctx, NS(custom_action_param=json.dumps(param))).success)
            parse.assert_called_once_with({})
            self.assertIsNone(runtime.call_args.kwargs["initial_formation"])
            self.assertEqual(runtime.call_args.kwargs["roster_servant_ids"], (None,) * 6)

    def test_repeat_retains_fallback_until_new_support_and_task_end_clears_it(self):
        ctx = Context()
        sessions.set_support_fallback(ctx.root, ctx.token, True)
        sessions.battle_started(ctx.root, ctx.token, 2)
        self.assertTrue(sessions.support_fallback(ctx.root, ctx.token))
        sessions.finish(ctx.root, ctx.token)
        fresh = sessions.begin(ctx.root)
        self.assertFalse(sessions.support_fallback(ctx.root, fresh))

    def test_switch_is_default_off_and_available_in_custom_support(self):
        options = json.loads((ROOT / "assets/options/原生自动战斗助战方式.json").read_text("utf-8"))["option"]
        switch = options["多次查找失败随机选择助战"]
        self.assertEqual(switch["default_case"], "No")
        custom = options["原生自动战斗助战方式"]["cases"][0]
        self.assertIn("多次查找失败随机选择助战", custom["option"])


if __name__ == "__main__":
    unittest.main()
