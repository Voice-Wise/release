// Release asset 收集器。用 Node 跨平台匹配 Electron 打包产物并复制到上传目录。
import { cp, mkdir, readdir } from 'node:fs/promises'
import { basename, join, relative, sep } from 'node:path'

function normalizePath(path) {
  return path.split(sep).join('/')
}

function escapeRegExp(value) {
  return value.replace(/[|\\{}()[\]^$+?.]/g, '\\$&')
}

function globToRegExp(pattern) {
  const source = normalizePath(pattern)
    .split('*')
    .map((part) => escapeRegExp(part))
    .join('[^/]*')
  return new RegExp(`^${source}$`)
}

async function listFiles(root, dir = root) {
  const entries = await readdir(dir, { withFileTypes: true })
  const files = []
  for (const entry of entries) {
    const path = join(dir, entry.name)
    if (entry.isDirectory()) files.push(...(await listFiles(root, path)))
    else if (entry.isFile()) files.push(path)
  }
  return files
}

export async function collectReleaseAssets({ patterns, outDir, cwd = process.cwd() }) {
  await mkdir(outDir, { recursive: true })
  const files = await listFiles(cwd)
  const copied = []

  for (const pattern of patterns) {
    const matcher = globToRegExp(pattern)
    const matches = files.filter((file) => matcher.test(normalizePath(relative(cwd, file))))
    if (matches.length === 0) {
      throw new Error(`Missing artifact pattern: ${pattern}`)
    }
    for (const match of matches) {
      const target = join(outDir, basename(match))
      await cp(match, target)
      copied.push(target)
    }
  }

  return copied
}

function parseArgs(argv) {
  const args = new Map()
  for (let index = 0; index < argv.length; index += 2) {
    args.set(argv[index], argv[index + 1])
  }
  return args
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const args = parseArgs(process.argv.slice(2))
  const patternsJson = args.get('--patterns-json')
  const outDir = args.get('--out-dir')

  if (!patternsJson || !outDir) {
    throw new Error('Usage: collect-release-assets.mjs --patterns-json <json> --out-dir <dir>')
  }

  const copied = await collectReleaseAssets({
    patterns: JSON.parse(patternsJson),
    outDir
  })
  for (const path of copied) console.log(path)
}
