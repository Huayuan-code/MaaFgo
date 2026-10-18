"""选卡在等待截止后才出现时仍应继续；未确认和取消时不能盲点。"""

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "agent"), str(ROOT / "agent/custom")]

from battle.core.enums import Scene
from battle.core.models import BattleAction, BattleState, Confidence
from battle.core.policy import StrategyProfile
from battle.runtime.runtime import AutoBattleRuntime


class CommandConfirmationTests(unittest.TestCase):
    def run_scenario(self, observations, *, cancel_on_recheck=False):
        clock = [0.0]
        context = SimpleNamespace(tasker=SimpleNamespace(stopping=False))
        capture = Mock()
        capture.wait.return_value = capture
        capture.get.return_value = object()
        controller = Mock()
        controller.post_screencap.return_value = capture
        decider = SimpleNamespace(
            plan=None, decide=lambda *_args, **_kwargs: BattleAction(None, ())
        )
        runtime = AutoBattleRuntime(context, controller, decider, StrategyProfile())
        runtime.executor = SimpleNamespace(open_command_cards=Mock(return_value=True))
        runtime._observe = Mock(side_effect=[
            BattleState(Scene.MAIN_BATTLE, Confidence(1.0), (), (), ()),
            BattleState(Scene.VICTORY, Confidence(1.0), (), (), ()),
        ])
        pending = iter(observations)

        def detect(_context, _image):
            scene, elapsed = next(pending)
            clock[0] += elapsed
            if cancel_on_recheck and scene is Scene.COMMAND_SELECTION:
                context.tasker.stopping = True
            return scene

        def sleep(seconds):
            clock[0] += seconds

        with patch("battle.runtime.runtime.perception.detect_scene", side_effect=detect), \
                patch("battle.runtime.runtime.time.monotonic", side_effect=lambda: clock[0]), \
                patch("battle.runtime.runtime.time.sleep", side_effect=sleep):
            result = runtime.run()
        return result, runtime

    def test_command_scene_on_final_recheck_resumes_without_another_attack(self):
        for clicks in (1, 3):
            with self.subTest(clicks=clicks):
                # 手机一轮 OCR 超过五秒；前两次未响应，最后一次复核才出现指令卡。
                observations = [(Scene.MAIN_BATTLE, 6.0)]
                observations += [(Scene.MAIN_BATTLE, 0.0), (Scene.MAIN_BATTLE, 6.0)] * (clicks - 1)
                observations += [(Scene.COMMAND_SELECTION, 0.0)]
                result, runtime = self.run_scenario(observations)
                self.assertTrue(result.ok, result.reason)
                self.assertEqual(runtime.executor.open_command_cards.call_count, clicks)
                self.assertEqual(runtime._observe.call_count, 2)

    def test_confirmed_scene_within_deadline_still_resumes(self):
        result, runtime = self.run_scenario([(Scene.COMMAND_SELECTION, 0.1)])
        self.assertTrue(result.ok, result.reason)
        runtime.executor.open_command_cards.assert_called_once()

    def test_stuck_main_scene_exhausts_bounded_retries(self):
        result, runtime = self.run_scenario(
            [(Scene.MAIN_BATTLE, 6.0), (Scene.MAIN_BATTLE, 0.0)] * 6
        )
        self.assertFalse(result.ok)
        self.assertEqual(result.reason, "open_cards_confirm_failed")
        self.assertEqual(runtime.executor.open_command_cards.call_count, 6)
        runtime._observe.assert_called_once()

    def test_unknown_scene_stops_without_further_attack(self):
        result, runtime = self.run_scenario([
            (Scene.MAIN_BATTLE, 6.0), (Scene.UNKNOWN, 0.0)
        ])
        self.assertFalse(result.ok)
        runtime.executor.open_command_cards.assert_called_once()
        runtime._observe.assert_called_once()

    def test_cancelled_late_confirmation_does_not_resume(self):
        result, runtime = self.run_scenario([
            (Scene.MAIN_BATTLE, 6.0), (Scene.COMMAND_SELECTION, 0.0)
        ], cancel_on_recheck=True)
        self.assertFalse(result.ok)
        runtime.executor.open_command_cards.assert_called_once()
        runtime._observe.assert_called_once()


if __name__ == "__main__":
    unittest.main()
