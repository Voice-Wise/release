#!/usr/bin/env bash
# 从构建目录直接上传前端 sourcemap 和原生调试符号，CLI 使用独立缓存。
set -euo pipefail

readonly SENTRY_ORG="dododoai"
readonly SENTRY_JS_PROJECT="livetype-js"
readonly SENTRY_RUST_PROJECT="livetype-rust"

if [[ -z "${SENTRY_AUTH_TOKEN:-}" ]]; then
  echo "SENTRY_AUTH_TOKEN 未设置" >&2
  exit 1
fi

if [[ -z "${SENTRY_RELEASE:-}" ]]; then
  echo "SENTRY_RELEASE 未设置" >&2
  exit 1
fi

if [[ -z "${SENTRY_DIST:-}" ]]; then
  echo "SENTRY_DIST 未设置" >&2
  exit 1
fi

SENTRY_SOURCEMAP_DIR="${SENTRY_SOURCEMAP_DIR:-sentry-input/dist}"
SENTRY_DEBUG_ROOT="${SENTRY_DEBUG_ROOT:-sentry-input/debug}"

SENTRY_TOOL_DIR="${VOICEWISE_RUNNER_ROOT:-${RUNNER_TEMP:-/tmp}}/tools/sentry-3.8.0"
export PATH="${SENTRY_TOOL_DIR}:${PATH}"
if ! command -v sentry-cli >/dev/null 2>&1; then
  case "$(uname -s)" in
    Darwin)
      sentry_asset="sentry-cli-Darwin-universal"
      sentry_sha="2c26914636c47ab9bf9e710484ad7b44d371cbec8bd29cafb36b3cf877bf4285"
      ;;
    Linux)
      sentry_asset="sentry-cli-Linux-x86_64"
      sentry_sha="13f8cb34ae01a6a272d7d7c22e277a105286615b4020de900ea95a8de47cdbb6"
      ;;
    MINGW*|MSYS*|CYGWIN*)
      sentry_asset="sentry-cli-Windows-x86_64.exe"
      sentry_sha="2257cf6805a616f5c3ee291a549ebbba021190048b646adc006beb4e8cdef7fd"
      ;;
    *) echo "不支持的 Sentry CLI 平台" >&2; exit 1 ;;
  esac
  mkdir -p "$SENTRY_TOOL_DIR"
  sentry_download="$SENTRY_TOOL_DIR/sentry-cli.download"
  curl --fail --silent --show-error --location --retry 3 \
    "https://github.com/getsentry/sentry-cli/releases/download/3.8.0/${sentry_asset}" \
    --output "$sentry_download"
  python3 - "$sentry_download" "$sentry_sha" <<'PY'
import hashlib
import sys
from pathlib import Path
if hashlib.sha256(Path(sys.argv[1]).read_bytes()).hexdigest() != sys.argv[2]:
    raise SystemExit("Sentry CLI 下载校验失败")
PY
  chmod +x "$sentry_download"
  mv "$sentry_download" "$SENTRY_TOOL_DIR/sentry-cli"
fi

if ! sentry-cli releases --org "${SENTRY_ORG}" info "${SENTRY_RELEASE}" >/dev/null 2>&1; then
  sentry-cli releases --org "${SENTRY_ORG}" new "${SENTRY_RELEASE}" \
    -p "${SENTRY_JS_PROJECT}" \
    -p "${SENTRY_RUST_PROJECT}" || \
    sentry-cli releases --org "${SENTRY_ORG}" info "${SENTRY_RELEASE}" >/dev/null
fi

if find "${SENTRY_SOURCEMAP_DIR}" -type f -name '*.map' -print -quit 2>/dev/null | grep -q .; then
  # Sentry 的虚拟 URL 前缀需要保留字面的 ~，不能展开为用户目录。
  # shellcheck disable=SC2088
  sentry-cli sourcemaps upload \
    --org "${SENTRY_ORG}" \
    --project "${SENTRY_JS_PROJECT}" \
    --release "${SENTRY_RELEASE}" \
    --dist "${SENTRY_DIST}" \
    --url-prefix "~/" \
    "${SENTRY_SOURCEMAP_DIR}"
elif [[ "${SENTRY_REQUIRE_SOURCEMAPS:-false}" == "true" ]]; then
  echo "构建缺少必须上传的前端 sourcemap" >&2
  exit 1
else
  echo "未找到前端 sourcemap，跳过上传。目录: ${SENTRY_SOURCEMAP_DIR}"
fi

if find "${SENTRY_DEBUG_ROOT}" \( -type d -name '*.dSYM' -o -type f -name '*.pdb' \) -print -quit 2>/dev/null | grep -q .; then
  sentry-cli debug-files upload \
    --org "${SENTRY_ORG}" \
    --project "${SENTRY_RUST_PROJECT}" \
    --include-sources \
    "${SENTRY_DEBUG_ROOT}"
else
  echo "未找到 dSYM/PDB，跳过 Rust 符号上传。目录: ${SENTRY_DEBUG_ROOT}"
fi

sentry-cli releases --org "${SENTRY_ORG}" finalize "${SENTRY_RELEASE}"
