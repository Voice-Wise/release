#!/bin/bash
# 将本机 runner 的 Rust 构建产物保留在检出目录之外，沿用工作流既有产物路径。
set -euo pipefail
: "${VOICEWISE_RUNNER_ROOT:?缺少本机 runner 根目录}"
: "${GITHUB_WORKSPACE:?缺少工作目录}"
cache_dir="$VOICEWISE_RUNNER_ROOT/cache/cargo-target"
target_dir="$GITHUB_WORKSPACE/src-tauri/target"
mkdir -p "$cache_dir"
if [[ -e "$target_dir" || -L "$target_dir" ]]; then
  if [[ ! -L "$target_dir" || "$(readlink "$target_dir")" != "$cache_dir" ]]; then
    echo "Rust 产物目录不是此 runner 管理的链接，拒绝覆盖。" >&2
    exit 1
  fi
else
  ln -s "$cache_dir" "$target_dir"
fi
