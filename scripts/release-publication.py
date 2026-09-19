#!/usr/bin/env python3
"""管理每次构建的私有草稿，验证更新清单后发布，并清理失败构建。"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import quote


def gh(*args, payload=None):
    command = ["gh", *args]
    if payload is not None:
        command += ["--input", "-"]
    result = subprocess.run(
        command, input=json.dumps(payload) if payload is not None else None,
        text=True, capture_output=True, check=True,
    )
    if args[0] == "api" and result.stdout.strip():
        return json.loads(result.stdout)
    return result.stdout.strip() or None


def api(repo, path, method="GET", payload=None):
    return gh("api", f"repos/{repo}/{path}", "--method", method, payload=payload)


def draft_tag(channel):
    return f"build-{channel}-{os.environ['GITHUB_RUN_ID']}-{os.environ['GITHUB_RUN_ATTEMPT']}"


def create(repo, channel):
    version = os.environ["RELEASE_VERSION"]
    release = api(repo, "releases", "POST", {
        "tag_name": draft_tag(channel), "target_commitish": os.environ["GITHUB_SHA"],
        "name": f"VoiceWise {'Nightly ' if channel == 'nightly' else 'v'}{version}",
        "body": os.environ.get("RELEASE_BODY", ""),
        "draft": True, "prerelease": channel == "nightly", "make_latest": "false",
    })
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
        output.write(f"id={release['id']}\n")


def validate_draft(release, channel):
    if not release["draft"] or release["tag_name"] != draft_tag(channel):
        raise RuntimeError("拒绝操作不属于本次构建的草稿")


def find_release(repo, tag):
    # 按标签获取公开版本；只有 404 表示不存在，网络/权限失败必须中止。
    try:
        return api(repo, f"releases/tags/{quote(tag, safe='')}")
    except subprocess.CalledProcessError as error:
        if "HTTP 404" in (error.stderr or ""):
            return None
        raise


def generate_manifest(repo, release_id, tag, version, channel, directory):
    owner, name = repo.split("/", 1)
    command = [
        sys.executable, str(Path(__file__).with_name("generate-updater-manifests.py")),
        "--owner", owner, "--repo", name, "--tag", tag,
        "--release-id", str(release_id), "--version", version,
        "--channel", channel, "--out-dir", str(directory),
    ]
    source_sha = os.environ.get("SOURCE_COMMIT_SHA", "")
    if source_sha:
        command += ["--source-commit-sha", source_sha]
    subprocess.run(command, check=True)
    path = directory / "latest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    required = {"darwin-aarch64"}
    if os.environ.get("SKIP_WINDOWS") != "true":
        required.add("windows-x86_64")
    if not required <= manifest["platforms"].keys() or not required <= manifest["installers"]["platform_installers"].keys():
        raise RuntimeError("更新清单缺少本次要求构建的平台")
    if manifest["version"] != version:
        raise RuntimeError("更新清单版本与构建版本不一致")
    if channel == "nightly" and manifest.get("source_commit_sha") != source_sha:
        raise RuntimeError("更新清单源码 SHA 与构建不一致")
    return path


def publish(repo, channel, release_id):
    release = api(repo, f"releases/{release_id}")
    validate_draft(release, channel)
    version = os.environ["RELEASE_VERSION"]
    tag = "nightly" if channel == "nightly" else f"v{version}"
    old = find_release(repo, tag)
    if old and channel == "stable":
        raise RuntimeError(f"正式版本 {tag} 已发布，拒绝覆盖")
    with tempfile.TemporaryDirectory() as directory:
        manifest = generate_manifest(repo, release_id, tag, version, channel, Path(directory))
        gh("release", "upload", release["tag_name"], str(manifest), "--repo", repo, "--clobber")
        # 测试门禁由工作流保证；资产、签名和清单全部就绪后才替换公开版本。
        if old:
            gh("release", "delete", tag, "--repo", repo, "--yes", "--cleanup-tag")
        api(repo, f"releases/{release_id}", "PATCH", {
            "tag_name": tag, "draft": False,
            "make_latest": "false" if channel == "nightly" else "true",
        })
        if channel == "stable":
            if find_release(repo, "stable"):
                gh("release", "delete", "stable", "--repo", repo, "--yes", "--cleanup-tag")
            gh("release", "create", "stable", "--repo", repo, "--target", tag,
               "--title", f"VoiceWise Latest Stable (v{version})",
               "--notes", f"Latest stable release: v{version}", str(manifest))


def cleanup(repo, channel, release_id):
    release = api(repo, f"releases/{release_id}")
    if not release["draft"]:
        return
    validate_draft(release, channel)
    api(repo, f"releases/{release_id}", "DELETE")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["create", "publish", "cleanup"])
    parser.add_argument("--channel", required=True, choices=["nightly", "stable"])
    args = parser.parse_args()
    repo = os.environ["GITHUB_REPOSITORY"]
    if args.action == "create":
        create(repo, args.channel)
    else:
        globals()[args.action](repo, args.channel, int(os.environ["RELEASE_ID"]))


if __name__ == "__main__":
    main()
