"""Release 发布边界：签名身份、调试标志、ABI 和版本不得混淆。"""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("check_android_release", ROOT / "tools/check_android_release.py")
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


class ReleaseVerificationTests(unittest.TestCase):
    def setUp(self):
        self.digest = release.certificate_digest(release.CERTIFICATE)
        self.signers = f"Verifies\nSigner #1 certificate SHA-256 digest: {self.digest}\n"
        self.badging = ("package: name='com.aliothmoon.maafw.maafgo' versionCode='1200' "
                        "versionName='2.0.11-beta.2' platformBuildVersionName='16'\n"
                        "native-code: 'arm64-v8a'\n")

    def validate(self, signers=None, badging=None, tag="v2.0.11-beta.2"):
        return release.validate_metadata(self.signers if signers is None else signers,
                                         self.badging if badging is None else badging,
                                         self.digest, "arm64-v8a", tag)

    def test_signed_release_accepts_beta_and_stable_versions(self):
        self.assertFalse(self.validate()["debuggable"])
        stable = self.badging.replace("2.0.11-beta.2", "2.0.11")
        self.assertEqual(self.validate(badging=stable, tag="v2.0.11")["version_name"], "2.0.11")

    def test_certificate_digest_accepts_uppercase_colon_form(self):
        formatted = ":".join(self.digest[i:i + 2] for i in range(0, len(self.digest), 2)).upper()
        self.assertEqual(self.validate(signers=self.signers.replace(self.digest, formatted))["certificate_sha256"],
                         self.digest)

    def test_unrelated_signer_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "正式证书"):
            self.validate(signers=self.signers.replace(self.digest, "0" * 64))

    def test_missing_and_additional_signers_are_rejected(self):
        for signers in ("Verifies\n", self.signers + f"Signer #2 certificate SHA-256 digest: {self.digest}\n"):
            with self.subTest(signers=signers), self.assertRaisesRegex(ValueError, "正式证书"):
                self.validate(signers=signers)

    def test_debuggable_apk_is_rejected_even_with_the_right_certificate(self):
        with self.assertRaisesRegex(ValueError, "debuggable"):
            self.validate(badging=self.badging + "application-debuggable\n")

    def test_wrong_and_multiple_abis_are_rejected(self):
        for native in ("'x86_64'", "'arm64-v8a' 'x86_64'", ""):
            with self.subTest(native=native), self.assertRaisesRegex(ValueError, "原生架构"):
                self.validate(badging=self.badging.replace("'arm64-v8a'", native))

    def test_tag_version_mismatch_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "不一致"):
            self.validate(tag="v2.0.11")

    def test_missing_manifest_metadata_is_rejected(self):
        for badging in ("", "native-code: 'arm64-v8a'\n", self.badging.replace("versionCode='1200'", "versionCode='0'")):
            with self.subTest(badging=badging), self.assertRaises(ValueError):
                self.validate(badging=badging)


if __name__ == "__main__":
    unittest.main()
