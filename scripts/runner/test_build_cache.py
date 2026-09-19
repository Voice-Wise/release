# 验证本机构建缓存跨源码清理保留，并拒绝覆盖不属于 runner 的目录。
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).with_name("prepare-build-cache.sh")


class BuildCacheTests(unittest.TestCase):
    def test_cache_survives_checkout_clean(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = root / "work space"
            (workspace / "src-tauri").mkdir(parents=True)
            subprocess.run(["git", "init", "--quiet", str(workspace)], check=True)
            environment = dict(os.environ, VOICEWISE_RUNNER_ROOT=str(root / "runner"),
                               GITHUB_WORKSPACE=str(workspace))
            subprocess.run(["bash", str(SCRIPT)], env=environment, check=True)
            target = workspace / "src-tauri/target"
            persistent = target.resolve()
            (target / "compiled-fixture").write_bytes(b"cached-build")
            subprocess.run(["git", "clean", "-ffdx"], cwd=workspace, check=True, capture_output=True)
            self.assertEqual((persistent / "compiled-fixture").read_bytes(), b"cached-build")
            (workspace / "src-tauri").mkdir(exist_ok=True)
            subprocess.run(["bash", str(SCRIPT)], env=environment, check=True)
            self.assertEqual((target / "compiled-fixture").read_bytes(), b"cached-build")
            subprocess.run(["bash", str(SCRIPT)], env=environment, check=True)

    def test_existing_target_is_preserved(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "workspace/src-tauri/target"
            target.mkdir(parents=True)
            (target / "unowned-fixture").write_bytes(b"keep")
            environment = dict(os.environ, VOICEWISE_RUNNER_ROOT=str(root / "runner"),
                               GITHUB_WORKSPACE=str(root / "workspace"))
            result = subprocess.run(["bash", str(SCRIPT)], env=environment, capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual((target / "unowned-fixture").read_bytes(), b"keep")


if __name__ == "__main__":
    unittest.main()
