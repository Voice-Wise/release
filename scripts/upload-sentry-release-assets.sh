#!/usr/bin/env bash
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

if ! command -v sentry-cli >/dev/null 2>&1; then
  curl -sL https://sentry.io/get-cli/ | bash
fi

if ! sentry-cli --org "${SENTRY_ORG}" releases info "${SENTRY_RELEASE}" >/dev/null 2>&1; then
  sentry-cli --org "${SENTRY_ORG}" releases new "${SENTRY_RELEASE}" \
    -p "${SENTRY_JS_PROJECT}" \
    -p "${SENTRY_RUST_PROJECT}"
fi

if find "${SENTRY_SOURCEMAP_DIR}" -type f -name '*.map' -print -quit 2>/dev/null | grep -q .; then
  sentry-cli --org "${SENTRY_ORG}" --project "${SENTRY_JS_PROJECT}" releases files "${SENTRY_RELEASE}" upload-sourcemaps "${SENTRY_SOURCEMAP_DIR}" \
    --dist "${SENTRY_DIST}" \
    --url-prefix "~/" \
    --rewrite
else
  echo "未找到前端 sourcemap，跳过上传。目录: ${SENTRY_SOURCEMAP_DIR}"
fi

if find "${SENTRY_DEBUG_ROOT}" \( -type d -name '*.dSYM' -o -type f -name '*.pdb' \) -print -quit 2>/dev/null | grep -q .; then
  sentry-cli --org "${SENTRY_ORG}" --project "${SENTRY_RUST_PROJECT}" debug-files upload "${SENTRY_DEBUG_ROOT}" --include-sources
else
  echo "未找到 dSYM/PDB，跳过 Rust 符号上传。目录: ${SENTRY_DEBUG_ROOT}"
fi

sentry-cli --org "${SENTRY_ORG}" releases finalize "${SENTRY_RELEASE}"
