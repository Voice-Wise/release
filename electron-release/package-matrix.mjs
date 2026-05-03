// Electron 发布矩阵。供 Release 仓库根据 skip_windows 生成 macOS/Windows 打包任务。
export function buildElectronPackageMatrix({ skipWindows = true } = {}) {
  const include = [
    {
      name: 'macOS (arm64)',
      os: 'macos-latest',
      platform: 'macos',
      arch: 'arm64',
      builderArgs: '--mac --arm64 --publish never',
      artifactName: 'livetype-electron-macos-arm64',
      artifactPaths: ['dist/LiveType-*-macos-arm64.dmg', 'dist/latest-mac.yml']
    },
    {
      name: 'macOS (x64)',
      os: 'macos-latest',
      platform: 'macos',
      arch: 'x64',
      builderArgs: '--mac --x64 --publish never',
      artifactName: 'livetype-electron-macos-x64',
      artifactPaths: ['dist/LiveType-*-macos-x64.dmg', 'dist/latest-mac.yml']
    }
  ]

  if (!skipWindows) {
    include.push({
      name: 'Windows (x64)',
      os: 'windows-latest',
      platform: 'windows',
      arch: 'x64',
      builderArgs: '--win --x64 --publish never',
      artifactName: 'livetype-electron-windows-x64',
      artifactPaths: ['dist/LiveType-*-windows-x64-setup.exe', 'dist/latest.yml']
    })
  }

  return { include }
}

function parseSkipWindows(value) {
  return ['true', '1', 'yes'].includes(String(value ?? 'true').trim().toLowerCase())
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const skipWindowsIndex = process.argv.indexOf('--skip-windows')
  const skipWindows =
    skipWindowsIndex >= 0 ? parseSkipWindows(process.argv[skipWindowsIndex + 1]) : parseSkipWindows(process.env.SKIP_WINDOWS)
  process.stdout.write(`${JSON.stringify(buildElectronPackageMatrix({ skipWindows }))}\n`)
}
