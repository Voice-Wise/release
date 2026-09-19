# 验证临时签名材料的生命周期、失败恢复和用户钥匙串搜索列表保护。
import base64
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("apple_signing", Path(__file__).with_name("apple-signing.py"))
signing = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(signing)


class SigningTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name) / "signing"
        self.github_env = Path(self.temporary.name) / "github-env"
        self.search = ["/Users/example/Library/Keychains/login.keychain-db"]
        self.original = self.search.copy()
        self.calls = []
        self.fail_import = False
        self.environment = patch.dict(os.environ, {
            "APPLE_CERTIFICATE": base64.b64encode(b"certificate-fixture").decode(),
            "APPLE_CERTIFICATE_PASSWORD": "fixture-password",
            "GITHUB_ENV": str(self.github_env),
        })
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.mock = patch.object(signing, "security", side_effect=self.security)
        self.mock.start()
        self.addCleanup(self.mock.stop)

    def security(self, *args):
        self.calls.append(args)
        if args[0] == "list-keychains":
            if "-s" in args:
                self.search = list(args[args.index("-s") + 1:])
                return ""
            return "\n".join(json.dumps(path) for path in self.search)
        if args[0] == "create-keychain":
            Path(args[-1]).touch()
            self.search.append(args[-1])
        if args[0] == "delete-keychain":
            Path(args[-1]).unlink()
        if args[0] == "import":
            self.assertEqual(Path(args[1]).read_bytes(), b"certificate-fixture")
            self.assertEqual(Path(args[1]).stat().st_mode & 0o777, 0o600)
            if self.fail_import:
                raise RuntimeError("模拟证书导入失败")
        return ""

    def test_prepare_and_cleanup_preserve_user_state(self):
        signing.prepare(self.directory)
        keychain = self.directory / "build.keychain-db"
        self.assertEqual(self.search, self.original + [str(keychain)])
        self.assertTrue(keychain.exists())
        self.assertFalse((self.directory / "certificate.p12").exists())
        self.assertEqual(self.directory.stat().st_mode & 0o777, 0o700)
        self.assertEqual(self.github_env.read_text().strip().split("=", 1),
                         ["VOICEWISE_SIGNING_KEYCHAIN", str(keychain)])
        signing.cleanup(self.directory)
        self.assertEqual(self.search, self.original)
        self.assertFalse(keychain.exists())
        self.assertFalse((self.directory / "state.json").exists())
        self.assertFalse(any(call[0] == "default-keychain" for call in self.calls))
        signing.cleanup(self.directory)

    def test_import_failure_cleans_partial_material(self):
        self.fail_import = True
        with self.assertRaisesRegex(RuntimeError, "模拟证书导入失败"):
            signing.prepare(self.directory)
        self.assertEqual(self.search, self.original)
        self.assertEqual(list(self.directory.iterdir()), [])

    def test_cleanup_preserves_keychain_added_during_job(self):
        signing.prepare(self.directory)
        self.search.append("/Users/example/Library/Keychains/another.keychain-db")
        expected = self.original + [self.search[-1]]
        signing.cleanup(self.directory)
        self.assertEqual(self.search, expected)

    def test_next_prepare_recovers_interrupted_job(self):
        signing.prepare(self.directory)
        (self.directory / "certificate.p12").write_bytes(b"interrupted-fixture")
        signing.prepare(self.directory)
        self.assertEqual(len(self.search), 2)
        self.assertFalse((self.directory / "certificate.p12").exists())
        signing.cleanup(self.directory)
        self.assertEqual(self.search, self.original)

    def test_invalid_certificate_does_not_mutate_keychains(self):
        with patch.dict(os.environ, {"APPLE_CERTIFICATE": "!invalid!"}):
            with self.assertRaises(ValueError):
                signing.prepare(self.directory)
        self.assertEqual(self.calls, [])

    def test_unowned_file_is_not_overwritten(self):
        self.directory.mkdir()
        path = self.directory / "build.keychain-db"
        path.write_bytes(b"unowned-fixture")
        with self.assertRaisesRegex(RuntimeError, "拒绝覆盖"):
            signing.prepare(self.directory)
        self.assertEqual(path.read_bytes(), b"unowned-fixture")
        self.assertEqual(self.calls, [])


if __name__ == "__main__":
    unittest.main()
