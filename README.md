# VoiceWise Release

该仓库用于存放 VoiceWise 的 **Public 构建产物** 与 **Updater manifests**（供客户端应用内更新使用）。

## Updater Manifests

- Stable（正式版）：`latest-<platform>-stable-<arch>.json`
- Nightly（每次提交自动构建）：`latest-<platform>-nightly-<arch>.json`
- 兼容旧版本客户端：`latest-<platform>-<arch>.stable.json`

示例（macOS Apple Silicon）：
- `latest-darwin-stable-aarch64.json`
- `latest-darwin-nightly-aarch64.json`

## Releases

- 正式发布：tag 为 `vX.Y.Z`
- Nightly 发布：tag 为 `v<nightly-version>`，并标记为 `prerelease`
