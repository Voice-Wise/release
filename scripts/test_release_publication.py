"""验证草稿发布顺序、失败保护、平台门禁及清理边界。"""

import importlib.util
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("publication", Path(__file__).with_name("release-publication.py"))
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, {
            "GITHUB_RUN_ID": "123", "GITHUB_RUN_ATTEMPT": "2",
            "GITHUB_SHA": "b" * 40, "RELEASE_VERSION": "0.1.29-nightly.1",
            "SOURCE_COMMIT_SHA": "a" * 40, "SKIP_WINDOWS": "true",
        })
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.draft = {"id": 42, "draft": True, "tag_name": "build-nightly-123-2"}

    def test_publish_uploads_manifest_before_replacing_old_release(self):
        events = []
        def call_api(repo, path, method="GET", payload=None):
            events.append((method, path, payload))
            return self.draft
        def call_gh(*args):
            events.append(args)
        with patch.object(MODULE, "api", side_effect=call_api), \
             patch.object(MODULE, "gh", side_effect=call_gh), \
             patch.object(MODULE, "find_release", return_value={"id": 7}), \
             patch.object(MODULE, "generate_manifest", return_value=Path("latest.json")):
            MODULE.publish("owner/repo", "nightly", 42)
        self.assertEqual([event[:2] for event in events], [
            ("GET", "releases/42"), ("release", "upload"),
            ("release", "delete"), ("PATCH", "releases/42"),
        ])
        self.assertEqual(events[-1][2], {"tag_name": "nightly", "draft": False, "make_latest": "false"})

    def test_invalid_manifest_preserves_public_release(self):
        with patch.object(MODULE, "api", return_value=self.draft) as api, \
             patch.object(MODULE, "find_release", return_value={"id": 7}), \
             patch.object(MODULE, "generate_manifest", side_effect=RuntimeError("缺少签名")), \
             patch.object(MODULE, "gh") as gh:
            with self.assertRaises(RuntimeError):
                MODULE.publish("owner/repo", "nightly", 42)
        gh.assert_not_called()
        api.assert_called_once_with("owner/repo", "releases/42")

    def test_upload_failure_preserves_public_release(self):
        with patch.object(MODULE, "api", return_value=self.draft) as api, \
             patch.object(MODULE, "find_release", return_value={"id": 7}), \
             patch.object(MODULE, "generate_manifest", return_value=Path("latest.json")), \
             patch.object(MODULE, "gh", side_effect=RuntimeError("上传失败")) as gh:
            with self.assertRaises(RuntimeError):
                MODULE.publish("owner/repo", "nightly", 42)
        self.assertEqual(gh.call_count, 1)
        self.assertEqual(gh.call_args.args[:2], ("release", "upload"))
        self.assertEqual(api.call_count, 1)

    def test_cleanup_keeps_published_release(self):
        with patch.object(MODULE, "api", return_value={"draft": False}) as api:
            MODULE.cleanup("owner/repo", "nightly", 42)
        api.assert_called_once_with("owner/repo", "releases/42")

    def test_cleanup_deletes_only_current_draft(self):
        with patch.object(MODULE, "api", return_value=self.draft) as api:
            MODULE.cleanup("owner/repo", "nightly", 42)
        self.assertEqual(api.call_args.args, ("owner/repo", "releases/42", "DELETE"))
        with patch.object(MODULE, "api", return_value={**self.draft, "tag_name": "build-nightly-123-1"}) as api:
            with self.assertRaises(RuntimeError):
                MODULE.cleanup("owner/repo", "nightly", 42)
        self.assertEqual(api.call_count, 1)

    def test_published_stable_version_cannot_be_overwritten(self):
        draft = {**self.draft, "tag_name": "build-stable-123-2"}
        with patch.object(MODULE, "api", return_value=draft), \
             patch.object(MODULE, "find_release", return_value={"id": 7}), \
             patch.object(MODULE, "generate_manifest") as generate:
            with self.assertRaises(RuntimeError):
                MODULE.publish("owner/repo", "stable", 42)
        generate.assert_not_called()

    def test_lookup_does_not_ignore_permission_or_network_errors(self):
        for status in (403, 500, 404):
            with self.subTest(status=status), patch.object(MODULE, "api", side_effect=
                    subprocess.CalledProcessError(1, "gh", stderr=f"HTTP {status}")):
                if status == 404:
                    self.assertIsNone(MODULE.find_release("owner/repo", "nightly"))
                else:
                    with self.assertRaises(subprocess.CalledProcessError):
                        MODULE.find_release("owner/repo", "nightly")

    def test_manifest_requires_enabled_platforms_and_exact_source(self):
        manifest = {
            "version": os.environ["RELEASE_VERSION"], "source_commit_sha": "a" * 40,
            "platforms": {"darwin-aarch64": {}},
            "installers": {"platform_installers": {"darwin-aarch64": {}}},
        }
        with tempfile.TemporaryDirectory() as directory, patch.object(MODULE.subprocess, "run"):
            path = Path(directory) / "latest.json"
            path.write_text(json.dumps(manifest))
            args = ("owner/repo", 42, "nightly", manifest["version"], "nightly", Path(directory))
            self.assertEqual(MODULE.generate_manifest(*args), path)
            with patch.dict(os.environ, SKIP_WINDOWS="false"):
                with self.assertRaisesRegex(RuntimeError, "平台"):
                    MODULE.generate_manifest(*args)
            manifest["source_commit_sha"] = "c" * 40
            path.write_text(json.dumps(manifest))
            with self.assertRaisesRegex(RuntimeError, "SHA"):
                MODULE.generate_manifest(*args)


if __name__ == "__main__":
    unittest.main()
