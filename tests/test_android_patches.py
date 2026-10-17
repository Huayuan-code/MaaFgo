"""Android 外壳补丁应用器：重放、幂等和冲突不覆盖验证。"""
import importlib.util
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("android_patches", ROOT / "tools/apply_android_patches.py")
patcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(patcher)


@unittest.skipUnless(shutil.which("git"), "git required")
class AndroidPatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.shell = self.root / "shell"
        (self.shell / "app/src/main").mkdir(parents=True)
        subprocess.run(["git", "init", "--quiet", str(self.shell)], check=True)
        self.patches = self.root / "patches"
        self.patches.mkdir()
        self.file = self.shell / "app/src/main/config.txt"
        self.file.write_text("original\n", encoding="utf-8")
        self.patch = self.patches / "0001-example.patch"
        self.patch.write_text(
            "diff --git a/app/src/main/config.txt b/app/src/main/config.txt\n"
            "--- a/app/src/main/config.txt\n+++ b/app/src/main/config.txt\n"
            "@@ -1 +1 @@\n-original\n+preserved\n", encoding="utf-8",
        )

    def test_replays_and_is_idempotent_without_touching_unrelated_files(self):
        other = self.shell / "app/src/main/other.txt"
        other.write_text("developer change", encoding="utf-8")
        self.assertEqual(patcher.apply_patches(self.shell, self.patches), [(self.patch.name, "applied")])
        self.assertEqual(self.file.read_text(), "preserved\n")
        snapshot = self.file.stat().st_mtime_ns
        self.assertEqual(patcher.apply_patches(self.shell, self.patches), [(self.patch.name, "already applied")])
        self.assertEqual(snapshot, self.file.stat().st_mtime_ns)
        self.assertEqual(other.read_text(), "developer change")

    def test_conflict_fails_without_overwriting_local_change(self):
        self.file.write_text("local change\n", encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "0001-example.patch"):
            patcher.apply_patches(self.shell, self.patches)
        self.assertEqual(self.file.read_text(), "local change\n")

    def test_partial_patch_does_not_get_mistaken_for_already_applied(self):
        self.patch.write_text(self.patch.read_text() +
            "diff --git a/app/src/main/second.txt b/app/src/main/second.txt\n"
            "--- a/app/src/main/second.txt\n+++ b/app/src/main/second.txt\n"
            "@@ -1 +1 @@\n-before\n+after\n", encoding="utf-8")
        self.file.write_text("preserved\n", encoding="utf-8")
        second = self.shell / "app/src/main/second.txt"
        second.write_text("before\n", encoding="utf-8")
        with self.assertRaises(RuntimeError):
            patcher.apply_patches(self.shell, self.patches)
        self.assertEqual(second.read_text(), "before\n")

    def test_missing_or_empty_patch_directory_fails(self):
        self.patch.unlink()
        with self.assertRaises(RuntimeError):
            patcher.apply_patches(self.shell, self.patches)
        self.patches.rmdir()
        with self.assertRaises(RuntimeError):
            patcher.apply_patches(self.shell, self.patches)


if __name__ == "__main__":
    unittest.main()
