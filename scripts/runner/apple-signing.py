#!/usr/bin/env python3
# 管理 CI 临时签名钥匙串和证书文件，保留用户默认钥匙串及其他搜索项。
import argparse
import base64
import json
import os
from pathlib import Path
import secrets
import shlex
import subprocess
import sys


def security(*args):
    result = subprocess.run(
        ["/usr/bin/security", *args], capture_output=True, text=True, timeout=60
    )
    if result.returncode:
        # 参数可能包含密码，错误输出也不回显证书内容。
        raise RuntimeError(f"钥匙串操作 {args[0]} 失败，退出码 {result.returncode}")
    return result.stdout


def search_list():
    return shlex.split(security("list-keychains", "-d", "user"))


def state_directory():
    configured = os.environ.get("VOICEWISE_SIGNING_STATE_DIR")
    if configured:
        return Path(configured)
    return Path(os.environ["RUNNER_TEMP"]) / "voicewise-signing"


def cleanup(directory):
    state_path = directory / "state.json"
    if not state_path.exists():
        return
    state = json.loads(state_path.read_text())
    keychain = directory / "build.keychain-db"
    certificate = directory / "certificate.p12"
    if state["keychain"] != str(keychain):
        raise RuntimeError("签名状态目录不匹配，拒绝删除其他钥匙串")
    certificate.unlink(missing_ok=True)
    # 仅移除本任务的搜索项，保留用户在任务运行期间添加的其他钥匙串。
    current = search_list()
    remaining = [path for path in current if path != str(keychain)]
    if remaining != current:
        security("list-keychains", "-d", "user", "-s", *remaining)
    if keychain.exists():
        security("delete-keychain", str(keychain))
    state_path.unlink()
    print("CI 临时签名材料已清理，用户默认钥匙串保持不变。")


def prepare(directory):
    cleanup(directory)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    directory.chmod(0o700)
    keychain = directory / "build.keychain-db"
    certificate = directory / "certificate.p12"
    if keychain.exists() or certificate.exists():
        raise RuntimeError("签名目录存在未登记的文件，拒绝覆盖")
    encoded = "".join(os.environ["APPLE_CERTIFICATE"].split())
    decoded = base64.b64decode(encoded, validate=True)
    if not decoded:
        raise RuntimeError("Apple 签名证书为空")
    password = os.environ["APPLE_CERTIFICATE_PASSWORD"]
    baseline = search_list()
    state_path = directory / "state.json"
    with open(state_path, "x", opener=lambda path, flags: os.open(path, flags, 0o600)) as stream:
        json.dump({"keychain": str(keychain)}, stream)
    try:
        with open(certificate, "xb", opener=lambda path, flags: os.open(path, flags, 0o600)) as stream:
            stream.write(decoded)
        keychain_password = secrets.token_urlsafe(32)
        security("create-keychain", "-p", keychain_password, str(keychain))
        security("set-keychain-settings", "-lut", "21600", str(keychain))
        security("unlock-keychain", "-p", keychain_password, str(keychain))
        security(
            "import", str(certificate), "-k", str(keychain), "-P", password,
            "-T", "/usr/bin/codesign", "-T", "/usr/bin/pkgbuild",
            "-T", "/usr/bin/productbuild",
        )
        security(
            "set-key-partition-list", "-S", "apple-tool:,apple:,codesign:",
            "-s", "-k", keychain_password, str(keychain),
        )
        # 不改变默认钥匙串，只把 CI 钥匙串追加到已有搜索列表。
        paths = list(dict.fromkeys([*baseline, *search_list(), str(keychain)]))
        security("list-keychains", "-d", "user", "-s", *paths)
        with open(os.environ["GITHUB_ENV"], "a") as stream:
            stream.write(f"VOICEWISE_SIGNING_KEYCHAIN={keychain}\n")
        print("GitHub Secrets 中的证书已导入 CI 临时钥匙串。")
    except BaseException:
        cleanup(directory)
        raise
    finally:
        certificate.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["prepare", "cleanup"])
    arguments = parser.parse_args()
    try:
        {"prepare": prepare, "cleanup": cleanup}[arguments.action](state_directory())
    except Exception as error:
        print(f"签名环境处理失败：{error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
