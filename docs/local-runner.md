# 本机 macOS ARM 构建

`voicewise-m4` 是 Release 仓库专用的 macOS ARM64 runner。仓库变量 `MACOS_BUILD_RUNNER=voicewise-m4` 将 ARM64 的 Rust 构建和打包分配给本机；删除此变量可恢复 GitHub 托管构建。测试、Windows 和发布整理任务继续使用云端 runner。macOS 仅发布 Apple Silicon（ARM64）版本，不再编译或测试 Intel 版本。

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

本机后台服务设置 `TAURI_BUNDLER_DMG_IGNORE_CI=false`，让 DMG 制作跳过需要 Finder 自动化权限的排版步骤，避免后台 AppleScript 超时。此降级仅影响本机产出的 macOS DMG 安装窗口布局，不改变应用内容、签名或公证；云端构建保持原行为。

此 runner 只用于受信任的 Release 构建，不应给公开仓库的外部 PR 添加使用它的工作流。

## 发布流水线

主分支由 Nightly 统一运行前端单测、Rust 单测和无 API Key 的功能测试，不再额外触发一轮相同的普通 CI；功能分支保留普通 CI。纯文档修改不自动构建，仍可手动触发。

测试与完整打包同时开始，打包直接复用本机缓存，不再先运行一遍完整 Rust release 编译。安装包只上传到本次运行独有的未公开 Release 草稿；Sentry sourcemap 和原生调试符号从构建机直接上传，不经过 Actions Artifact 中转。

所有已启用平台的测试、打包、Sentry 上传成功后，才校验并上传更新清单，再发布草稿。正式版额外等待云端回归测试。失败或取消时清理本次草稿，旧 Nightly 在新包验证完成前保持可用。发布切换任务一旦开始会完成切换，避免取消导致版本停留在中间状态。

Windows 仍为 x86_64，默认跳过；手动启用 Windows 后，其测试与打包也必须通过。签名、公证和自动清理机制保持不变。
