"""MuMu SDK返回同一句柄时，重复连接/延迟析构不能使新连接失效。"""
import os
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock, mock_open

from test_bbc_startup import ROOT, load_classes


class MumuConnectionTests(unittest.TestCase):
    def setUp(self):
        self.active = {}
        self.disconnected = []
        self.created = []
        owner = self

        class Api:
            def nemu_connect(self, path, index):
                owner.active[index + 1] = True
                return index + 1

            def nemu_disconnect(self, handle):
                owner.disconnected.append(handle)
                owner.active.pop(handle, None)

        class Mumu:
            @staticmethod
            def check_mumuInstallPath(path):
                return os.path.normpath(path)

            def __init__(self, path, index=0, app_index=0, pkg=None, use_manager=True):
                self.mumuPath = os.path.normpath(path)
                self.emulatorIndex, self.appIndex, self.pkg = index, app_index, pkg
                self.nemu = Api()
                self.handle = self.nemu.nemu_connect(path, index)
                self.displayid = 0
                self.serialno = ''
                owner.created.append(self)

            def snapshot(self):
                if not owner.active.get(self.handle):
                    raise RuntimeError('displayid=-1')
                return NS(shape=(1080, 1920, 3))

            def get_ready(self):
                self.snapshot()

            def set_serialno(self, serialno):
                self.serialno = serialno

            def disconnect(self):
                # 与BBC的__del__同样无条件断开。
                self.nemu.nemu_disconnect(self.handle)

        self.Mumu = Mumu
        self.page = NS(idx=0, device=NS(running=False, snapshotDevice=None, operateDevice=None),
                       snapshotDevice=None, operateDevice=None)
        self.ns = load_classes(ROOT / 'bbcdll/bbc_tcp_server.py', {'ConnectionAPI', '_RetiredMumuApi'}, {
            'Mumudevice': Mumu, 'ensure_imports': lambda: None, 'get_bb_page': lambda: self.page,
            '_log': Mock(), 'open': mock_open(),
            '_bb_window_global': NS(pagebar=NS(tags=[NS(createText=Mock())]), updateConnectLst=Mock()),
        })
        self.api = self.ns['ConnectionAPI']

    def connect(self, pkg='com.aniplex.fategrandorder', index=0):
        return self.api.connect_mumu('C:/MuMu', index, pkg, 0)

    def install_existing(self, pkg='com.aniplex.fategrandorder'):
        old = self.Mumu('C:\\MuMu', 0, 0, pkg)
        self.page.snapshotDevice = self.page.operateDevice = old
        self.page.device.snapshotDevice = self.page.device.operateDevice = old
        return old

    def test_auto_connected_device_is_reused_with_normalized_path(self):
        old = self.install_existing()
        result = self.connect()
        self.assertTrue(result['success'])
        self.assertEqual(result['connection_action'], 'reused')
        self.assertIs(self.page.device.snapshotDevice, old)
        self.assertEqual(len(self.created), 1)
        self.assertEqual(self.disconnected, [])

    def test_repeated_connections_keep_capturing(self):
        for _ in range(5):
            result = self.connect()
            self.assertTrue(result['capture_verified'])
            self.assertEqual(result['resolution'], [1920, 1080])
            self.page.device.snapshotDevice.snapshot()
        self.assertEqual(len(self.created), 1)

    def test_stale_handle_is_repaired_without_replacing_object(self):
        old = self.install_existing()
        self.active.clear()
        result = self.connect()
        self.assertTrue(result['success'])
        self.assertEqual(result['connection_action'], 'reconnected')
        self.assertIs(self.page.device.snapshotDevice, old)
        self.assertEqual(len(self.created), 1)
        old.snapshot()

    def test_package_switch_closes_old_before_allocating_same_handle(self):
        old = self.install_existing('com.bilibili.fatego')
        result = self.connect()
        self.assertTrue(result['success'])
        current = self.page.device.snapshotDevice
        self.assertIsNot(current, old)
        self.assertEqual(current.handle, 1)
        self.assertEqual(self.disconnected, [1])
        # 模拟缓存/回调中的旧对象在新连接完成后才被析构。
        old.disconnect()
        old.disconnect()
        current.snapshot()
        self.assertEqual(self.disconnected, [1])

    def test_switch_to_another_emulator_has_no_late_disconnect(self):
        old = self.install_existing()
        result = self.connect(index=1)
        self.assertTrue(result['success'])
        self.assertEqual(self.page.device.snapshotDevice.handle, 2)
        old.disconnect()
        self.page.device.snapshotDevice.snapshot()

    def test_running_battle_refuses_reconnection(self):
        old = self.install_existing()
        self.page.device.running = True
        result = self.connect()
        self.assertFalse(result['success'])
        self.assertEqual(self.disconnected, [])
        old.snapshot()

    def test_failed_capture_is_not_reported_as_connected(self):
        self.Mumu.snapshot = Mock(return_value=None)
        self.assertFalse(self.connect()['success'])


if __name__ == '__main__':
    unittest.main()
