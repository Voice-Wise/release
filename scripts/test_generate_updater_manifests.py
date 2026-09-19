"""验证源码 SHA、草稿下载链接及受支持平台的更新清单。"""

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
        self.check_manifest(draft=False)

    def test_draft_manifest_uses_final_public_urls(self) -> None:
        self.check_manifest(draft=True)

    def check_manifest(self, draft):
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
        # 旧 Intel 资产即使存在也不能进入新清单；Windows x64 仍保留。
        for platform, arch, extension in [("darwin", "x86_64", ".app.tar.gz"), ("windows", "x64", ".exe")]:
            name = f"LiveType_{version}_{platform}_{arch}{extension}"
            release["assets"] += [
                {"name": name, "browser_download_url": f"https://example.com/{name}"},
                {"name": name + ".sig", "url": "https://api.example.com/signature"},
            ]
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
            if draft:
                argv += ["--release-id", "42"]
            with (
                patch.object(sys, "argv", argv),
                patch.object(MODULE, "_http_get_json", return_value=release) as get_release,
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
        self.assertEqual(set(manifest["platforms"]), {"darwin-aarch64", "windows-x86_64"})
        self.assertEqual(set(manifest["installers"]["platform_installers"]), {"darwin-aarch64", "windows-x86_64"})
        if draft:
            self.assertEqual(get_release.call_args.args[0], "https://api.github.com/repos/Voice-Wise/release/releases/42")
            self.assertEqual(manifest["platforms"]["darwin-aarch64"]["url"],
                             f"https://github.com/Voice-Wise/release/releases/download/nightly/{updater_name}")
            self.assertEqual(manifest["installers"]["platform_installers"]["darwin-aarch64"]["url"],
                             f"https://github.com/Voice-Wise/release/releases/download/nightly/{installer_name}")


if __name__ == "__main__":
    unittest.main()
