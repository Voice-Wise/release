// Electron updater manifest 生成器。把 Release assets 转换为现有客户端可读取的 latest.json。
import { mkdir, writeFile } from 'node:fs/promises'
import { join } from 'node:path'
import { isCliEntrypoint } from './cli-entrypoint.mjs'

const TARGETS = [
  {
    key: 'darwin-aarch64',
    installerPattern: /LiveType-.+-macos-arm64[.]dmg$/,
    platformAliases: ['macos', 'darwin'],
    archAliases: ['arm64', 'aarch64']
  },
  {
    key: 'darwin-x86_64',
    installerPattern: /LiveType-.+-macos-x64[.]dmg$/,
    platformAliases: ['macos', 'darwin'],
    archAliases: ['x64', 'x86_64']
  },
  {
    key: 'windows-x86_64',
    installerPattern: /LiveType-.+-windows-x64-setup[.]exe$/,
    platformAliases: ['windows'],
    archAliases: ['x64', 'x86_64']
  }
]

function assetUrl(asset, baseUrl) {
  if (asset.browser_download_url) return asset.browser_download_url
  if (asset.url && /^https?:/.test(asset.url)) return asset.url
  return `${baseUrl.replace(/\/$/, '')}/${encodeURIComponent(asset.name)}`
}

function pickOne(candidates, label) {
  if (candidates.length === 1) return candidates[0]
  if (candidates.length === 0) throw new Error(`Missing release asset: ${label}`)
  throw new Error(`Multiple release assets matched ${label}: ${candidates.map((asset) => asset.name).sort().join(', ')}`)
}

export function buildUpdaterManifest({ assets, version, publishedAt, notes = '', baseUrl, platforms = [] }) {
  const platformFilter = new Set(platforms)
  const selectedTargets = platformFilter.size ? TARGETS.filter((target) => platformFilter.has(target.key)) : TARGETS
  const manifestPlatforms = {}
  const installerPlatforms = {}

  for (const target of selectedTargets) {
    const installer = pickOne(
      assets.filter((asset) => target.installerPattern.test(asset.name)),
      `${target.key} installer`
    )
    const url = assetUrl(installer, baseUrl)
    manifestPlatforms[target.key] = { url }
    installerPlatforms[target.key] = { url }
  }

  return {
    version,
    pub_date: publishedAt,
    platforms: manifestPlatforms,
    installers: {
      platform_installers: installerPlatforms
    },
    notes
  }
}

function parseArgs(argv) {
  const args = new Map()
  for (let i = 0; i < argv.length; i += 2) {
    args.set(argv[i], argv[i + 1])
  }
  return args
}

if (isCliEntrypoint(import.meta.url, process.argv[1])) {
  const args = parseArgs(process.argv.slice(2))
  const assetsJson = args.get('--assets-json')
  const version = args.get('--version')
  const publishedAt = args.get('--published-at')
  const baseUrl = args.get('--base-url')
  const outDir = args.get('--out-dir') ?? '.'
  const platforms = (args.get('--platforms') ?? '')
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean)

  if (!assetsJson || !version || !publishedAt || !baseUrl) {
    throw new Error('Usage: generate-updater-manifest.mjs --assets-json <json> --version <version> --published-at <iso> --base-url <url> [--out-dir <dir>] [--platforms <keys>]')
  }

  const manifest = buildUpdaterManifest({
    assets: JSON.parse(assetsJson),
    version,
    publishedAt,
    baseUrl,
    notes: args.get('--notes') ?? '',
    platforms
  })
  await mkdir(outDir, { recursive: true })
  await writeFile(join(outDir, 'latest.json'), `${JSON.stringify(manifest, null, 2)}\n`, 'utf-8')
}
