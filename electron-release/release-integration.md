<!-- Electron Release 集成说明。记录私有触发、公有 CI/Release 迁移合同和缺失 Secret 风险。 -->

# Electron Release 集成

触发链路保持源项目模式：私有应用仓通过 `repository_dispatch` 发送 `ci`、`nightly`、`release`，公有 `Voice-Wise/release` 仓 checkout 私有源码后执行 Electron 验证和打包。

## 稳定契约

- `ci` payload 保留 `sha`、`ref`、`skip_windows`、`sender_repo`。
- `nightly` payload 保留 `ref`、`branch`、`skip_windows`。
- `release` payload 保留 `ref`、`version`、`skip_windows`。
- Release 仓安装命令为 `bun install --frozen-lockfile`。
- Electron CI 验证命令为 `npm run typecheck`、`npm run test`、`npm run test:functional:local`。
- Electron 打包命令为 `npm run build && electron-builder <platform args>`。
- stable manifest 发布到 `https://github.com/Voice-Wise/release/releases/download/stable/latest.json`。
- nightly manifest 发布到 `https://github.com/Voice-Wise/release/releases/download/nightly/latest.json`。
- artifact 命名与 `electron-builder.yml` 保持一致：`LiveType-<version>-macos-<arch>.dmg`、`LiveType-<version>-windows-<arch>-setup.exe`。

## Release 仓库迁移 TODO

- 将 Tauri workflow 中的 `tauri-apps/tauri-action` 替换为 `npm run build` 加 `electron-builder --mac/--win --publish never`。
- macOS 签名与公证继续使用 Release 仓现有 `APPLE_CERTIFICATE`、`APPLE_CERTIFICATE_PASSWORD`、`APPLE_SIGNING_IDENTITY`、`APPLE_ID`、`APPLE_PASSWORD`、`APPLE_TEAM_ID`。
- Windows 签名所需证书当前 Release YAML 未提供；迁移 Windows 正式包前需要补充 Windows code signing secret，或在 workflow 中明确保留 unsigned 降级。
- Sentry sourcemap/debug symbol 上传可继续沿用 Release 仓现有 `SENTRY_AUTH_TOKEN`、`SENTRY_ORG`、`SENTRY_PROJECT`，但 Electron dSYM/PDB 搜索路径需改到 `dist/`。

## 发布候选验证矩阵

- 本地必过：`npm run typecheck && npm run test && npm run test:functional:local && npm run build`。
- Release 合同必过：`npm run test -- electron-release`。
- native smoke：`npm run test:native-smoke` 记录为 RC 风险项；需要在真实 macOS/Windows 机器上确认权限、热键、粘贴、前台应用和系统音频相关能力。
- Windows 正式发布：默认沿用 `skip_windows=true`；如果开启 Windows 包，需要先处理 Windows 签名 secret 或明确 unsigned 降级。
