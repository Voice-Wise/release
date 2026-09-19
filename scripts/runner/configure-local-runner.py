#!/usr/bin/env python3
# 将已下载的 macOS runner 注册到 Release 仓库，安装独立工具目录和签名清理钩子。
import argparse
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys


def command(arguments, *, cwd=None, env=None):
    subprocess.run(arguments, cwd=cwd, env=env, check=True)


def configure(root):
    root = root.resolve()
    if not (root / "config.sh").is_file():
        raise RuntimeError("请先下载并校验 GitHub 官方 macOS ARM64 runner，解压到目标目录")
    if (root / ".runner").exists():
        raise RuntimeError("目标目录已有已注册 runner，请先检查现有配置")
    support = root / "support"
    support.mkdir(exist_ok=True)
    for name in ["apple-signing.py", "prepare-build-cache.sh"]:
        shutil.copy2(Path(__file__).with_name(name), support / name)
    python = shutil.which("python3")
    hook = support / "cleanup-signing.sh"
    hook.write_text(
        "#!/bin/bash\n# 清理上一任务或异常退出遗留的 CI 签名材料。\n"
        "set -euo pipefail\n"
        f"exec {shlex.quote(python)} {shlex.quote(str(support / 'apple-signing.py'))} cleanup\n"
    )
    hook.chmod(0o700)
    variables = {
        "VOICEWISE_RUNNER_ROOT": str(root),
        "VOICEWISE_SIGNING_STATE_DIR": str(root / "state/signing"),
        "ACTIONS_RUNNER_HOOK_JOB_STARTED": str(hook),
        "ACTIONS_RUNNER_HOOK_JOB_COMPLETED": str(hook),
        "CARGO_HOME": str(root / "tools/cargo"),
        "RUSTUP_HOME": str(root / "tools/rustup"),
        "CARGO_BUILD_JOBS": "4",
        "BUN_INSTALL_CACHE_DIR": str(root / "cache/bun"),
        "TAURI_BUNDLER_DMG_IGNORE_CI": "false",
    }
    for name in ["CARGO_HOME", "RUSTUP_HOME", "BUN_INSTALL_CACHE_DIR", "VOICEWISE_SIGNING_STATE_DIR"]:
        Path(variables[name]).mkdir(parents=True, exist_ok=True, mode=0o700)
    environment = os.environ.copy()
    environment.update(variables)
    environment["PATH"] = ":".join([
        str(root / "tools/bun"), str(root / "tools/cargo/bin"),
        str(Path(shutil.which("rustup")).parent),
        str(Path(shutil.which("node")).parent),
        "/opt/homebrew/bin", "/usr/bin", "/bin", "/usr/sbin", "/sbin",
    ])
    command(["rustup", "toolchain", "install", "stable", "--profile", "minimal", "--no-self-update"], env=environment)
    command(["rustup", "default", "stable"], env=environment)
    if not (root / "tools/bun/bun").is_file():
        raise RuntimeError("请先在 tools/bun 中安装与工作流一致的 Bun 1.3.2")
    registration = json.loads(subprocess.check_output([
        "gh", "api", "--method", "POST", "repos/Voice-Wise/release/actions/runners/registration-token",
    ], text=True))
    token = registration["token"]
    result = subprocess.run([
        str(root / "config.sh"), "--unattended", "--url", "https://github.com/Voice-Wise/release",
        "--token", token, "--name", "voicewise-m4", "--labels", "voicewise-m4", "--work", "_work",
    ], cwd=root, env=environment, text=True, capture_output=True)
    print((result.stdout + result.stderr).replace(token, "***"))
    if result.returncode:
        raise RuntimeError("runner 注册失败")
    # 这里只保存运行环境和路径，发布密钥始终由 GitHub 在任务执行时提供。
    with (root / ".env").open("a") as stream:
        for name, value in variables.items():
            stream.write(f"{name}={value}\n")
    (root / ".env").chmod(0o600)
    (root / ".path").write_text(environment["PATH"])
    command([str(root / "svc.sh"), "install"], cwd=root, env=environment)
    command([str(root / "svc.sh"), "start"], cwd=root, env=environment)
    command([str(root / "svc.sh"), "status"], cwd=root, env=environment)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("runner_directory", type=Path)
    arguments = parser.parse_args()
    try:
        configure(arguments.runner_directory)
    except Exception as error:
        print(f"本机 runner 配置失败：{error}", file=sys.stderr)
        sys.exit(1)
