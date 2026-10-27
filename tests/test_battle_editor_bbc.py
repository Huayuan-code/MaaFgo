"""BBC uploads convert offline into previews without saving or device startup."""
import copy
import http.client
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

from agent.battle_editor.bbc_import import import_bbc_document
from agent.battle_editor.server import create_server
from agent.battle_editor.storage import EditorError
from agent.battle_editor.validation import validate_battle


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/bbc/爱尔奎特_光狐_光狐.json"


class BbcUploadTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="bbc-upload 中文 ")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        static = self.root / "assets/web/battle-editor"
        static.mkdir(parents=True)
        (static / "index.html").write_text("offline editor", encoding="utf-8")
        for relative in ("agent/chaldea/bbc_servant_ids.json", "agent/utils/Chaldea/equip_names_CN.json"):
            target = self.root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / relative, target)
        self.config = json.loads(FIXTURE.read_text("utf-8"))
        self.server = create_server(self.root, 0)
        self.server._catalog = {"servants": [], "equips": [], "mysticCodes": []}
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.close_server)

    def close_server(self):
        self.server.shutdown()
        self.thread.join(5)
        self.server.server_close()

    def request(self, payload, *, token=True, origin=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=10)
        headers = {"Content-Type": "application/json"}
        if token:
            headers["X-Editor-Token"] = self.server.token
        if origin:
            headers["Origin"] = origin
        connection.request("POST", "/api/import-bbc", json.dumps(payload, ensure_ascii=False).encode("utf-8"), headers)
        response = connection.getresponse()
        status, body = response.status, json.loads(response.read())
        connection.close()
        return status, body

    def test_real_config_converts_without_bbc_installation_or_writing(self):
        original = copy.deepcopy(self.config)
        before = {str(path.relative_to(self.root)): path.read_bytes() for path in self.root.rglob("*") if path.is_file()}
        status, result = self.request({"config": self.config, "name": FIXTURE.name})
        self.assertEqual(status, 200, result)
        self.assertEqual(result["sourceName"], FIXTURE.name)
        self.assertTrue(result["validation"]["valid"], result["validation"])
        self.assertEqual(result["data"]["_source"], "bbc")
        self.assertEqual(result["data"]["team"]["onFieldSvts"][2]["supportType"], "friend")
        self.assertEqual(sum(action["type"] == "attack" for action in result["data"]["actions"]), 3)
        self.assertEqual(result["data"]["_bbcSource"]["file"], FIXTURE.name)
        self.assertEqual(len(result["data"]["_bbcSource"]["sha256"]), 64)
        self.assertEqual(result["warnings"], result["data"]["_conversionWarnings"])
        self.assertEqual(self.config, original)
        self.assertEqual(before, {str(path.relative_to(self.root)): path.read_bytes() for path in self.root.rglob("*") if path.is_file()})

    def test_invalid_documents_and_names_are_actionable_and_preserve_files(self):
        for value in (None, [], "BBC", True, {}):
            with self.subTest(config=value):
                status, result = self.request({"config": value, "name": "BBC.json"})
                self.assertEqual(status, 422, result)
                self.assertTrue(result["error"]["message"])
        for filename in ("../secret.json", "C:/private.json", "x\\y.json"):
            with self.subTest(filename=filename):
                status, result = self.request({"config": self.config, "name": filename})
                self.assertEqual(status, 400, result)
        self.assertEqual(list(self.server.storage.battle_dir.iterdir()), [])

    def test_unsupported_extended_instruction_is_rejected_before_import(self):
        self.config["round1_turn0_skill"] = [["BBDubai", 3, 0]]
        status, result = self.request({"config": self.config, "name": "extended.json"})
        self.assertEqual(status, 422, result)
        self.assertEqual(result["error"]["code"], "bbc_conversion_failed")
        self.assertEqual(list(self.server.storage.battle_dir.iterdir()), [])

    def test_upload_requires_same_origin_and_session_token(self):
        payload = {"config": self.config, "name": "BBC.json"}
        self.assertEqual(self.request(payload, token=False)[0], 403)
        self.assertEqual(self.request(payload, origin="https://untrusted.invalid")[0], 403)

    def test_conversion_failure_returns_422_without_internal_traceback(self):
        with patch("agent.battle_editor.bbc_import._converter", side_effect=ValueError("无法转换这条动作")):
            with self.assertRaises(EditorError) as raised:
                import_bbc_document(self.root, self.config)
        self.assertEqual((raised.exception.status, raised.exception.code), (422, "bbc_conversion_failed"))

    def test_conversion_warnings_remain_visible_in_saved_plan_checks(self):
        result = import_bbc_document(self.root, self.config, FIXTURE.name)
        result["data"]["_conversionWarnings"] = ["BBC 按波次推进，请核对固定回合", "候选选卡需手动核对"]
        path = self.server.storage.save_battle("bbc_saved", result["data"], create=True)
        restored = self.server.storage.read_battle(path["name"])["data"]
        report = validate_battle(restored)
        warnings = [issue for issue in report["issues"] if issue["code"] == "bbc_conversion_warning"]
        self.assertTrue(report["valid"], report)
        self.assertEqual([issue["message"] for issue in warnings], result["data"]["_conversionWarnings"])
        self.assertTrue(all(issue["severity"] == "warning" for issue in warnings))
        self.assertFalse(any(issue["code"] == "preserved_field" and issue["path"].startswith("_") for issue in report["issues"]))

    def test_grand_bond_effect_is_a_real_filter_without_fabricating_a_bond_ce(self):
        for state in (True, False):
            data = {"team": {"onFieldSvts": [{"supportType": "friend", "grandSvt": True,
                                             "classBoardData": {"grandBondEquipSkillChange": state}}, None, None],
                             "backupSvts": [None, None, None]}, "actions": []}
            report = validate_battle(data)
            self.assertTrue(report["valid"], report)
            self.assertNotIn("unrestricted_support", [issue["code"] for issue in report["issues"]])
            self.assertNotIn("equip2", data["team"]["onFieldSvts"][0])

    def test_new_process_imports_no_online_chaldea_or_device_modules(self):
        script = r'''
import builtins, json, pathlib, socket, sys
sys.path.insert(0, sys.argv[1])
original = builtins.__import__
def guarded(name, *args, **kwargs):
    if name.split('.')[0] in {'chaldea', 'maa', 'requests', 'mfaalog', 'custom'}:
        raise AssertionError('offline editor imported ' + name)
    return original(name, *args, **kwargs)
builtins.__import__ = guarded
socket.socket = lambda *a, **kw: (_ for _ in ()).throw(AssertionError('network IO'))
from agent.battle_editor.bbc_import import import_bbc_document
result = import_bbc_document(pathlib.Path(sys.argv[2]), json.load(sys.stdin), '离线 BBC.json')
assert result['data']['team']['onFieldSvts'][2]['supportType'] == 'friend'
print('offline conversion ok')
'''
        result = subprocess.run([sys.executable, "-c", script, str(ROOT), str(self.root)],
                                input=json.dumps(self.config), capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("offline conversion ok", result.stdout)


if __name__ == "__main__":
    unittest.main()
