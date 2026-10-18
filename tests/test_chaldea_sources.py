"""Chaldea 手机粘贴分享链接、关卡检索与离线缓存回归。"""

import base64
import gzip
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, quote, urlencode, urlsplit


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent" / "custom"))

from agent import chaldea
from agent.chaldea import chaldea_client as client


class ChaldeaSourceTests(unittest.TestCase):
    def setUp(self):
        self.share = {
            "quest": {"id": 94146537, "phase": 1},
            "team": {"onFieldSvts": [{"svtId": 704000}], "backupSvts": []},
            "notes": "".join(chr(0x4E00 + i) for i in range(200)),
        }
        compressed = gzip.compress(json.dumps(self.share, ensure_ascii=False).encode(), mtime=0)
        self.v1 = base64.b64encode(compressed).decode()
        self.v2 = "G" + base64.urlsafe_b64encode(compressed).decode()

    def assertSourceDecodes(self, source):
        quest_id, team_id, content = client.parse_import_source(source)
        self.assertIsNone(quest_id)
        self.assertIsNone(team_id)
        self.assertEqual(client.decode_content(content), self.share)

    def test_user_short_link(self):
        self.assertEqual(client.parse_import_source(
            "https://link.chaldea.center/laplace/share?id=72098"), (None, 72098, None))

    def test_numeric_team_and_quest_ids(self):
        self.assertEqual(client.parse_import_source("72098"), (None, 72098, None))
        self.assertEqual(client.parse_import_source("94146537"), (94146537, None, None))

    def test_current_v2_long_link(self):
        self.assertSourceDecodes("https://link.chaldea.center/laplace/share?" + urlencode({
            "data": self.v2, "questId": 94146537, "phase": 1,
        }))

    def test_legacy_v1_literal_plus_and_slash(self):
        self.assertIn("+", self.v1)
        self.assertIn("/", self.v1)
        self.assertSourceDecodes("https://chaldea.center/laplace/share?data=" + self.v1)

    def test_percent_encoded_v1_data(self):
        self.assertSourceDecodes("https://link.chaldea.center/laplace/share?data="
                                 + quote(self.v1, safe=""))

    def test_percent_encoded_v2_alphabet_and_padding(self):
        # URI 可合法转义任何字符，不只 +、/、=。
        escaped = "".join(f"%{ord(ch):02X}" for ch in self.v2)
        self.assertSourceDecodes("https://link.chaldea.center/laplace/share?data=" + escaped)

    def test_raw_compressed_data(self):
        for source in (self.v1, self.v2, quote(self.v1, safe="")):
            with self.subTest(source=source[:30]):
                self.assertSourceDecodes(source)

    def test_query_only_data_and_id(self):
        self.assertSourceDecodes("data=" + self.v1)
        self.assertSourceDecodes("?data=" + quote(self.v2, safe=""))
        self.assertEqual(client.parse_import_source("id=72098"), (None, 72098, None))

    def test_invalid_or_unrelated_url_does_not_become_team_id(self):
        for source in (
            "https://link.chaldea.center/laplace/share?notid=72098",
            "https://link.chaldea.center/laplace/share?redirect=https://example.com/?id=72098",
            "https://link.chaldea.center/laplace/share#id=72098",
            "https://link.chaldea.center/laplace/share/id=72098",
            "https://link.chaldea.center/laplace/share?id=72098garbage",
            "https://link.chaldea.center/laplace/share?id=72098&id=21086",
            "https://link.chaldea.center/laplace/share?id=0",
            "https://unrelated.example/?id=72098",
            "https://chaldea.center.evil.example/?id=72098",
            "https://[invalid/?id=72098",
            "0", "²", "not a source",
        ):
            with self.subTest(source=source):
                self.assertEqual(client.parse_import_source(source), (None, None, None))

    def test_invalid_data_does_not_fall_back_to_id(self):
        for query in ("data=&id=72098", "data=invalid&id=72098",
                      "data=GH4s%20bad&id=72098", "data=GH4s%ZZ&id=72098",
                      "data=GH4sAAA&data=GH4sBBB&id=72098"):
            with self.subTest(query=query):
                self.assertEqual(client.parse_import_source(
                    "https://link.chaldea.center/laplace/share?" + query), (None, None, None))

    def test_complete_data_takes_precedence_over_id(self):
        self.assertSourceDecodes("https://link.chaldea.center/laplace/share?data="
                                 + quote(self.v2, safe="") + "&id=72098")

    def test_inline_data_never_requires_network(self):
        with patch.object(chaldea, "fetch_team_by_id") as fetch_team, \
                patch.object(chaldea, "fetch_teams_by_quest") as fetch_quest:
            data, quest_id, team_id = chaldea.fetch_share_data(
                "https://link.chaldea.center/laplace/share?data=" + quote(self.v1, safe=""))
        self.assertEqual(data, self.share)
        self.assertEqual(quest_id, 94146537)
        self.assertEqual(team_id, "offline")
        fetch_team.assert_not_called()
        fetch_quest.assert_not_called()


class ChaldeaQuestQueryTests(unittest.TestCase):
    def query(self, *args, **kwargs):
        response = MagicMock()
        response.read.return_value = json.dumps({"data": [{
            "id": 72098, "quest_id": 94146537, "phase": 1, "data": "Gtest",
        }]}).encode()
        with patch.object(client.urllib.request, "urlopen", return_value=response) as request:
            teams = client.fetch_teams_by_quest(*args, **kwargs)
        self.assertEqual(teams[0]["id"], 72098)
        return parse_qs(urlsplit(request.call_args.args[0].full_url).query)

    def test_default_query_includes_coronation_phase_one_teams(self):
        query = self.query(94146537)
        self.assertEqual(query["questId"], ["94146537"])
        self.assertNotIn("phase", query)

    def test_explicit_phase_is_preserved(self):
        for phase in (1, 3):
            with self.subTest(phase=phase):
                query = self.query(94146537, phase=phase, limit=10)
                self.assertEqual(query["phase"], [str(phase)])
                self.assertEqual(query["limit"], ["10"])


class ChaldeaCacheTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        patcher = patch.object(chaldea, "CACHE_DIR", str(self.root))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.share = {"quest": {"id": 94146537, "phase": 1},
                      "team": {"onFieldSvts": [], "backupSvts": []}}

    def write(self, name, data=None):
        path = self.root / name
        path.write_text(json.dumps(self.share if data is None else data), encoding="utf-8")
        return str(path)

    def test_new_cache_name_is_found_by_quest_and_team(self):
        path = self.write("摩狂狂_72098_94146537.json")
        self.assertEqual(chaldea._find_cache_file(94146537, None), path)
        self.assertEqual(chaldea._find_cache_file(None, 72098), path)

    def test_legacy_quest_cache_is_still_readable(self):
        path = self.write("chaldea_quest_94146537_72098.json")
        self.assertEqual(chaldea._find_cache_file(94146537, None), path)

    def test_legacy_team_cache_is_still_readable(self):
        path = self.write("chaldea_team_72098.json")
        self.assertEqual(chaldea._find_cache_file(None, 72098), path)

    def test_legacy_quest_team_name_is_still_readable(self):
        path = self.write("94146537_72098_摩根.json")
        self.assertEqual(chaldea._find_cache_file(94146537, 72098), path)

    def test_misnamed_cache_is_rejected_even_when_filename_matches(self):
        self.write("错误_72098_94146537.json", {"quest": {"id": 93000002}, "team": {}})
        self.assertIsNone(chaldea._find_cache_file(94146537, None))

    def test_bad_cache_does_not_mask_another_valid_cache(self):
        (self.root / "损坏_72098_94146537.json").write_text("{broken", encoding="utf-8")
        self.write("错误_72099_94146537.json", {"quest": {"id": 93000002}, "team": {}})
        path = self.write("正确_72100_94146537.json")
        self.assertEqual(chaldea._find_cache_file(94146537, None), path)

    def test_quest_content_accepts_legacy_string_id(self):
        self.share["quest"]["id"] = "94146537"
        path = self.write("chaldea_quest_94146537_72098.json")
        self.assertEqual(chaldea._find_cache_file(94146537, None), path)

    def test_quest_cache_rejects_missing_or_non_object_quest(self):
        for value in ({"team": {}}, {"quest": None}, {"quest": []}, [94146537]):
            with self.subTest(value=value):
                self.write("chaldea_quest_94146537_72098.json", value)
                self.assertIsNone(chaldea._find_cache_file(94146537, None))

    def test_quest_id_prefix_collision_does_not_match(self):
        self.write("chaldea_quest_941465370_72098.json")
        self.assertIsNone(chaldea._find_cache_file(94146537, None))

    def test_quest_import_uses_new_cache_without_network(self):
        self.write("摩狂狂_72098_94146537.json")
        with patch.object(chaldea, "fetch_teams_by_quest") as request:
            data, quest_id, team_id = chaldea.fetch_share_data("94146537")
        self.assertEqual(data, self.share)
        self.assertEqual((quest_id, team_id), (94146537, "cached"))
        request.assert_not_called()

    def test_quest_download_has_no_phase_filter_and_then_works_offline(self):
        content = "G" + base64.urlsafe_b64encode(gzip.compress(json.dumps(self.share).encode())).decode()
        result = {"id": 72098, "content": content, "votes": {"up": 10}}
        with patch.object(chaldea, "fetch_teams_by_quest", return_value=[result]) as request:
            first = chaldea.fetch_share_data("94146537")
        request.assert_called_once_with(94146537, phase=None, limit=10)
        self.assertEqual(first[0], self.share)
        with patch.object(chaldea, "fetch_teams_by_quest", side_effect=OSError("offline")) as request:
            second = chaldea.fetch_share_data("94146537")
        self.assertEqual(second[0], self.share)
        request.assert_not_called()


if __name__ == "__main__":
    unittest.main()
