// Electron Release CLI 入口判断工具。兼容 Windows 路径和 file URL 表示差异。
import { fileURLToPath } from 'node:url'

function normalizeEntrypointPath(path) {
  return path.replaceAll('\\', '/').replace(/^\/([A-Za-z]:\/)/, '$1').toLowerCase()
}

export function isCliEntrypoint(importMetaUrl, argvPath) {
  if (!argvPath) return false
  return normalizeEntrypointPath(fileURLToPath(importMetaUrl)) === normalizeEntrypointPath(argvPath)
}
