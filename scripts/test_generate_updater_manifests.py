import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT_PATH = Path(__file__).with_name("generate-updater-manifests.py")
SPEC = importlib.util.spec_from_file_location("generate_updater_manifests", SCRIPT_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("Unable to load manifest generator")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class SourceCommitShaTests(unittest.TestCase):
    def test_accepts_full_sha_and_normalizes_case(self) -> None:
        sha = "A" * 40
        self.assertEqual(MODULE._normalize_source_commit_sha(sha), "a" * 40)

    def test_rejects_short_sha(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "40-character"):
            MODULE._normalize_source_commit_sha("1236d50a")

    def test_rejects_non_hex_sha(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "40-character"):
            MODULE._normalize_source_commit_sha("z" * 40)

    def test_nightly_manifest_contains_source_commit_sha(self) -> None:
        version = "0.1.29-nightly.1"
        updater_name = f"LiveType_{version}_darwin_aarch64.app.tar.gz"
        installer_name = f"LiveType_{version}_darwin_aarch64.dmg"
        release = {
            "published_at": "2026-08-11T00:52:15Z",
            "html_url": "https://example.com/nightly",
            "assets": [
                {
                    "name": updater_name,
                    "browser_download_url": f"https://example.com/{updater_name}",
                },
                {
                    "name": f"{updater_name}.sig",
                    "url": "https://api.example.com/signature",
                },
                {
                    "name": installer_name,
                    "browser_download_url": f"https://example.com/{installer_name}",
                },
            ],
        }
        source_commit_sha = "a" * 40

        with tempfile.TemporaryDirectory() as output_dir:
            argv = [
                str(SCRIPT_PATH),
                "--owner",
                "Voice-Wise",
                "--repo",
                "release",
                "--tag",
                "nightly",
                "--version",
                version,
                "--source-commit-sha",
                source_commit_sha,
                "--out-dir",
                output_dir,
                "--channel",
                "nightly",
            ]
            with (
                patch.object(sys, "argv", argv),
                patch.object(MODULE, "_http_get_json", return_value=release),
                patch.object(
                    MODULE,
                    "_download_github_release_asset",
                    return_value=b"signature",
                ),
            ):
                self.assertEqual(MODULE.main(), 0)

            manifest = json.loads(
                (Path(output_dir) / "latest.json").read_text(encoding="utf-8")
            )

        self.assertEqual(manifest["source_commit_sha"], source_commit_sha)
        self.assertEqual(manifest["version"], version)


if __name__ == "__main__":
    unittest.main()
