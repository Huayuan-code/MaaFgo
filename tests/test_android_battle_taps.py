"""安卓战斗点击要执行可控时长的 Pipeline，桌面仍使用原点击。"""
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "agent"), str(ROOT / "agent/custom")]
from battle.execution.executor import Executor
from battle.execution import coords


class AndroidBattleTapTests(unittest.TestCase):
    def setUp(self):
        self.ctx = SimpleNamespace(tasker=SimpleNamespace(stopping=False))
        self.ctx.run_task = Mock(return_value=SimpleNamespace(status=SimpleNamespace(succeeded=True)))
        self.controller = Mock()
        self.executor = Executor(self.ctx, self.controller)

    def test_android_buttons_use_pipeline_instead_of_short_controller_clicks(self):
        with patch("battle.execution.executor.is_android", return_value=True):
            self.assertTrue(self.executor.open_command_cards())
            self.assertTrue(self.executor.select_card(3))
            self.assertTrue(self.executor.select_np(2))
        self.assertEqual([c.args[0] for c in self.ctx.run_task.call_args_list],
                         ["战斗_安卓点击攻击", "战斗_安卓选择指令卡3", "战斗_安卓选择宝具2"])
        self.controller.post_click.assert_not_called()

    def test_desktop_preserves_existing_coordinates_and_clicks(self):
        with patch("battle.execution.executor.is_android", return_value=False):
            self.assertTrue(self.executor.open_command_cards())
            self.assertTrue(self.executor.select_card(3))
            self.assertTrue(self.executor.select_np(2))
        self.assertEqual([c.args for c in self.controller.post_click.call_args_list],
                         [coords.ATTACK_BTN, coords.center(coords.CARD_ROI[3]), coords.NP_CLICK[2]])
        self.ctx.run_task.assert_not_called()

    def test_failed_or_missing_task_result_is_not_reported_as_success(self):
        with patch("battle.execution.executor.is_android", return_value=True):
            for detail in [None, SimpleNamespace(status=SimpleNamespace(succeeded=False))]:
                self.ctx.run_task.return_value = detail
                self.assertFalse(self.executor.select_card(1))

    def test_stop_prevents_next_click_and_cancellation_during_click_is_propagated(self):
        with patch("battle.execution.executor.is_android", return_value=True):
            self.ctx.tasker.stopping = True
            self.assertFalse(self.executor.select_card(1))
            self.ctx.run_task.assert_not_called()
            self.ctx.tasker.stopping = False
            def cancel(_entry):
                self.ctx.tasker.stopping = True
                return SimpleNamespace(status=SimpleNamespace(succeeded=True))
            self.ctx.run_task.side_effect = cancel
            self.assertFalse(self.executor.select_np(2))

    def test_pipeline_covers_existing_attack_and_card_coordinates(self):
        nodes = json.loads((ROOT / "assets/resource/base/pipeline/自动战斗_安卓点击.json").read_text(encoding="utf8"))
        points = {"战斗_安卓点击攻击": coords.ATTACK_BTN}
        points.update({f"战斗_安卓选择指令卡{i}": coords.center(box) for i, box in coords.CARD_ROI.items()})
        points.update({f"战斗_安卓选择宝具{i}": p for i, p in coords.NP_CLICK.items()})
        self.assertEqual(set(nodes), set(points))
        for name, point in points.items():
            self.assertEqual(nodes[name]["action"]["type"], "LongPress")
            self.assertEqual(nodes[name]["action"]["param"], {"target": list(point), "duration": 500})
            self.assertEqual(nodes[name]["on_error"], [])


if __name__ == "__main__":
    unittest.main()
