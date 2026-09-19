# 本机 macOS ARM 构建

`voicewise-m4` 是 Release 仓库专用的 macOS ARM64 runner。仓库变量 `MACOS_BUILD_RUNNER=voicewise-m4` 将 ARM64 的 Rust 构建和打包分配给本机；删除此变量可恢复 GitHub 托管构建。测试、Intel macOS、Windows 和发布整理任务继续使用云端 runner。

GitHub Secrets 仍然是发布密钥的唯一配置入口。本机不需要手动保存 Apple 证书、公证密码或 Tauri 更新签名密钥。工作流把证书导入 CI 专属临时钥匙串，不修改用户默认钥匙串；签名步骤只向 Tauri 传签名身份，避免重复创建钥匙串。

临时证书在导入后立即删除，临时钥匙串在工作流的 `always()` 清理步骤中删除。runner 的任务开始和结束钩子会再次清理同一状态目录，覆盖工作流中断以及下次启动时的恢复。异常断电时不会承诺立即清理，下次任务开始前必须成功完成清理。

默认安装目录为 `~/.local/share/github-actions/voicewise-release`。该目录独立保存 runner、Bun 1.3.2、Rust 工具链、依赖缓存和编译产物，不使用日常开发目录。每个任务仍由 `actions/checkout` 清理源码，Rust 的 `target` 是指向独立缓存目录的链接。本机跳过远程 Cargo 缓存 action，避免其清理长期使用的工具和构建产物。

## 安装与验证

从 GitHub 官方发布下载并校验 macOS ARM64 runner，解压到安装目录；将校验过的 Bun 1.3.2 放到 `tools/bun/bun`。在已登录 `gh` 且拥有仓库管理员权限的终端中执行：

```bash
python3 scripts/runner/configure-local-runner.py ~/.local/share/github-actions/voicewise-release
```

安装脚本自动申请一次性注册令牌并配置用户级后台服务；不会把 `gh` 登录凭据或发布 Secrets 写入 runner 环境文件。注册完成后，手动运行 `Local Runner Check`：它会验证真实签名、Apple 公证凭据和任务结束后的钥匙串状态，不发布应用。

macOS 服务随用户登录启动，机器需联网且保持唤醒。runner 离线时已经指定它的任务会排队，不会自动转移到云端；要恢复云端构建，删除 `MACOS_BUILD_RUNNER` 后重新运行工作流。

此 runner 只用于受信任的 Release 构建，不应给公开仓库的外部 PR 添加使用它的工作流。
