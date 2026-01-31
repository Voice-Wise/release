import argparse
import json
import os
import re
import sys
import urllib.request
from pathlib import Path


def _http_get_json(url: str, token: str) -> dict:
    req = urllib.request.Request(url)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _download_github_release_asset(asset_api_url: str, token: str) -> bytes:
    req = urllib.request.Request(asset_api_url)
    req.add_header("Accept", "application/octet-stream")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req) as resp:
        return resp.read()


def _pick_one(items: list[dict], name: str) -> dict:
    if len(items) == 1:
        return items[0]
    if not items:
        raise RuntimeError(f"Missing release asset: {name}")
    names = ", ".join(sorted(a.get("name", "<unknown>") for a in items))
    raise RuntimeError(f"Multiple release assets matched {name}: {names}")


def _find_updater_asset(
    assets: list[dict],
    version: str,
    platform_aliases: list[str],
    arch: str,
    extension: str,
) -> dict:
    platform_re = "|".join(re.escape(p) for p in platform_aliases)
    pattern = re.compile(
        rf"^.+_{re.escape(version)}_({platform_re})_{re.escape(arch)}.*{re.escape(extension)}$"
    )
    candidates = [a for a in assets if pattern.match(a.get("name", ""))]
    return _pick_one(
        candidates,
        f"version={version} platform={platform_aliases} arch={arch} ext={extension}",
    )


def _find_signature_asset(
    assets: list[dict],
    version: str,
    platform_aliases: list[str],
    arch: str,
    updater_asset_name: str,
) -> dict:
    exact_name = f"{updater_asset_name}.sig"
    exact = [a for a in assets if a.get("name") == exact_name]
    if exact:
        return _pick_one(exact, f"signature for {updater_asset_name}")

    platform_re = "|".join(re.escape(p) for p in platform_aliases)
    pattern = re.compile(
        rf"^.+_{re.escape(version)}_({platform_re})_{re.escape(arch)}.*\.sig$"
    )
    candidates = [a for a in assets if pattern.match(a.get("name", ""))]

    if len(candidates) <= 1:
        return _pick_one(
            candidates,
            f"signature for version={version} platform={platform_aliases} arch={arch}",
        )

    ranked = sorted(
        candidates,
        key=lambda a: (
            0 if updater_asset_name in a.get("name", "") else 1,
            a.get("name", ""),
        ),
    )
    best = ranked[0]
    tied = [
        a
        for a in ranked
        if (updater_asset_name in a.get("name", ""))
        == (updater_asset_name in best.get("name", ""))
    ]
    return _pick_one(tied, f"signature for {updater_asset_name}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--owner", required=True)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument(
        "--channel",
        default="stable",
        choices=["stable", "nightly"],
        help="Update channel (stable or nightly)",
    )
    parser.add_argument(
        "--format",
        default="combined",
        choices=["combined"],
        help=(
            "Manifest format. "
            "'combined' writes a single latest.json with all platforms "
            "using standard Tauri keys (e.g. darwin-aarch64)."
        ),
    )
    parser.add_argument("--notes", default="")
    parser.add_argument(
        "--platforms",
        default="",
        help=(
            "Comma-separated list of os_target-arch pairs to include "
            "(e.g. 'darwin-aarch64,windows-x86_64'). If omitted, all platforms are included."
        ),
    )
    parser.add_argument(
        "--version",
        default="",
        help="Explicit version string (without 'v' prefix). If not provided, derived from --tag.",
    )
    parser.add_argument(
        "--token-env",
        default="GITHUB_TOKEN",
        help="Name of env var containing a GitHub token for API + asset downloads",
    )
    args = parser.parse_args()

    if args.channel == "stable":
        if not re.fullmatch(r"v\d+\.\d+\.\d+", args.tag):
            raise RuntimeError(f"Expected stable tag vX.Y.Z, got: {args.tag}")
    elif args.tag != "nightly":
        if not re.fullmatch(r"v\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?", args.tag):
            raise RuntimeError(f"Expected nightly tag vX.Y.Z(-pre)?(+meta)? or 'nightly', got: {args.tag}")

    token = os.environ.get(args.token_env, "")

    release = _http_get_json(
        f"https://api.github.com/repos/{args.owner}/{args.repo}/releases/tags/{args.tag}",
        token=token,
    )

    published_at = release.get("published_at") or release.get("created_at")
    if not published_at:
        raise RuntimeError("Release missing published_at/created_at")

    assets = release.get("assets") or []
    if not isinstance(assets, list):
        raise RuntimeError("Release assets payload invalid")

    if args.version:
        version = args.version.removeprefix("v")
    else:
        version = args.tag.removeprefix("v")
    notes = (args.notes or "").strip()
    if not notes:
        release_html_url = release.get("html_url") or ""
        channel_label = "Stable" if args.channel == "stable" else "Nightly"
        notes = f"VoiceWise v{version}（{channel_label}）\n\n更新说明请查看：{release_html_url}".strip()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    targets = [
        {
            "os_target": "darwin",
            "arch_canonical": "aarch64",
            "platform_aliases": ["macos", "darwin"],
            "arch_aliases": ["aarch64", "arm64"],
            "extensions": [".app.tar.gz", ".tar.gz"],
        },
        {
            "os_target": "darwin",
            "arch_canonical": "x86_64",
            "platform_aliases": ["macos", "darwin"],
            "arch_aliases": ["x86_64", "x64"],
            "extensions": [".app.tar.gz", ".tar.gz"],
        },
        {
            "os_target": "windows",
            "arch_canonical": "x86_64",
            "platform_aliases": ["windows"],
            "arch_aliases": ["x86_64", "x64"],
            "extensions": [".exe"],
        },
    ]

    if args.platforms:
        platform_filter = set(p.strip() for p in args.platforms.split(",") if p.strip())
        targets = [
            t for t in targets
            if f"{t['os_target']}-{t['arch_canonical']}" in platform_filter
        ]
        if not targets:
            raise RuntimeError(
                f"No targets matched --platforms filter: {args.platforms}"
            )

    # Build combined manifest with all platforms in one file
    all_platforms: dict[str, dict] = {}

    for target in targets:
        os_target = target["os_target"]
        arch_canonical = target["arch_canonical"]
        last_error: Exception | None = None
        updater_asset = None
        matched_arch_alias = None
        for arch in target["arch_aliases"]:
            for ext in target["extensions"]:
                try:
                    updater_asset = _find_updater_asset(
                        assets=assets,
                        version=version,
                        platform_aliases=target["platform_aliases"],
                        arch=arch,
                        extension=ext,
                    )
                    matched_arch_alias = arch
                    break
                except Exception as exc:  # noqa: BLE001
                    last_error = exc
            if updater_asset is not None:
                break

        if updater_asset is None:
            # Skip missing platforms (e.g. Windows temporarily disabled)
            print(
                f"[generate-updater-manifests] skipping {os_target}-{arch_canonical}: "
                f"{last_error or 'no matching asset'}",
                file=sys.stderr,
            )
            continue

        sig_asset = _find_signature_asset(
            assets=assets,
            version=version,
            platform_aliases=target["platform_aliases"],
            arch=matched_arch_alias or target["arch_aliases"][0],
            updater_asset_name=updater_asset["name"],
        )

        sig_bytes = _download_github_release_asset(sig_asset["url"], token=token)
        sig_content = sig_bytes.decode("utf-8").strip()

        # Standard Tauri platform key: {os_target}-{arch}
        platform_key = f"{os_target}-{arch_canonical}"
        all_platforms[platform_key] = {
            "signature": sig_content,
            "url": updater_asset["browser_download_url"],
        }

    if not all_platforms:
        raise RuntimeError("No platform assets found — cannot generate manifest")

    manifest = {
        "version": version,
        "pub_date": published_at,
        "platforms": all_platforms,
        "notes": notes,
    }

    out_path = out_dir / "latest.json"
    out_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"[generate-updater-manifests] wrote {out_path} with platforms: {', '.join(sorted(all_platforms))}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"[generate-updater-manifests] {exc}", file=sys.stderr)
        raise SystemExit(1)
