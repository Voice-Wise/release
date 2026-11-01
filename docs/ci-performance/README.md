# GitHub Actions 提速记录

应用源码固定为 `57bd292ef4655b747dc5765d5f6b52fbb0e8f18f`（v1.1.0）。比较的是不同 workflow 实现；CSV 的 `commit` 列表示 release 仓库的 workflow SHA，不是应用源码 SHA。

## 实测结果

| 范围 | 优化前 | 优化后 | 变化 |
| --- | ---: | ---: | ---: |
| CI：macOS + 前端，跳过 Windows，与原常用配置一致 | 152 秒 | 106 秒 | -30.3% |
| CI：完整 macOS / Windows + 前端 | 最近 50 次 CI 均跳过 Windows，无同范围基线 | 86 秒 | 完整复核通过 |
| Nightly：macOS、实际公证和公开发布 | 203 秒 | 186 秒 | -8.4% |
| Release：macOS + Windows、完整测试和打包验收 | 363 秒 | 321 秒 | -11.6% |
| GitHub 有效缓存 | 5,340,396,264 字节 / 9 项 | 2,071,762,248 字节 / 6 项 | -61.2% |

直接证据：CI [旧配置同源码对照](https://github.com/Voice-Wise/release/actions/runs/41297245788)、[最终同配置复测](https://github.com/Voice-Wise/release/actions/runs/41299644657)、[最终完整双平台 CI](https://github.com/Voice-Wise/release/actions/runs/41299246633)；Nightly [优化前](https://github.com/Voice-Wise/release/actions/runs/41189207123)、[最终复测](https://github.com/Voice-Wise/release/actions/runs/41299249270)；Release [优化前](https://github.com/Voice-Wise/release/actions/runs/41191225403)、[最终复测](https://github.com/Voice-Wise/release/actions/runs/41300234048)。

正式版采用新增的 `verify_only=true`：执行所有测试、签名、公证、双平台打包、资产上传和更新清单校验，随后清理本次私有草稿；没有覆盖已发布的 v1.1.0。公开标签切换及 stable 别名操作未重复执行，因此这行比较含有少量发布操作的差异。Nightly 两次连续完成了实际公开发布（192 秒、186 秒）。

这些是同源码的成功实测样本，不是固定耗时保证。GitHub 机器分配、下载、公证及模型服务存在波动；冷缓存和失败样本完整保留，没有混入提速百分比。分片前完整双平台 CI 为 112 秒，分片后为 86 秒；同配置 macOS CI 的相邻成功样本为 97 秒、106 秒。

## 最近 50 次运行和时间拆解

优化前先用 `gh run list --limit 50` 留存：7 次 CI、36 次 Nightly、6 次 Release、1 次 Runner Check，共 423 个 job。

- [before-jobs.csv](before-jobs.csv)：每个 job 的排队、准备、执行时间。
- [before-runs.json](before-runs.json)：原始 50 次运行索引。
- [control-jobs.csv](control-jobs.csv)、[control-runs.json](control-runs.json)：原 workflow 在同一应用源码上的额外对照。
- [after-jobs.csv](after-jobs.csv)、[after-runs.json](after-runs.json)：迭代复测，含冷缓存、失败、取消策略试验及最终成功样本。
- [cache-final.json](cache-final.json)：最终 6 个有效缓存及大小。

计时口径是阶段合计，并非三个连续区间：

| 字段 | 含义 |
| --- | --- |
| `dependency_wait_s` | workflow 创建到 job 创建，包括 needs、workflow 调度及并发组等待 |
| `queue_s` | job 的 created_at 到 started_at，单独计算 runner 排队 |
| `prepare_s` | job 总时长减实际执行，包含初始化、checkout、安装、缓存传输、编译及收尾 |
| `compile_in_prepare_s` | 从测试步骤开始到 Cargo Finished 日志的时间，已计入准备 |
| `execute_s` | 测试步骤扣除编译后的时长；非测试 job 表示其构建、公证、上传等主要工作 |

前端测试框架初始化仍计入测试步骤。历史日志不可用，或取消/编译失败发生在 Cargo Finished 之前时，执行列只能视为上界。CSV 保留结论及日志可用性；失败、取消、跳过不参与成功耗时比较。Jobs API 默认取得该 run 最新 attempt 的 job。

主要规律：原 Nightly macOS 测试 job 实际执行约 13 秒，绝大部分时间花在准备和编译。分片后同样检查由两台机器分别准备，关键路径取两者较长者。

| Nightly macOS 原生检查 | runner 排队 | 准备（含编译） | 实际执行 | job 时长 |
| --- | ---: | ---: | ---: | ---: |
| 原串行 job | 2 秒 | 149.686 秒 | 13.314 秒 | 163 秒 |
| 新 rust 分片 | 4 秒 | 81.311 秒 | 10.689 秒 | 92 秒 |
| 新 functional 分片 | 3 秒 | 60.306 秒 | 5.694 秒 | 66 秒 |

原正式版自托管 macOS 打包 job 的历史排队中位数约 117 秒，来自单台本机 runner 忙碌，不能归因于测试。其他大多数 hosted job 的排队中位数约 2–7 秒。分片后 Nightly 关键路径转为打包、公证及传输，因此整条流程的提速小于原生检查阶段。

## 最终实现

1. 删除独立的 runner 标签导出 job 和 CI 参数中转 job；直接使用标签，保留仓库变量 `MACOS_BUILD_RUNNER`。
2. 接收端 CI 按源码仓库、源码分支分组并取消旧运行；main/master/缺少源码分支时用独立 run_id。主线排队中的提交也不会被同组新请求替换。
3. Nightly 各运行独立执行；公共 nightly 标签的发布 job 使用 `cancel-in-progress: false` 和 `queue: max` 串行，保留等待任务。
4. 正式版前端、原生和云端测试直接使用触发输入启动；更新日志独立在 Ubuntu 并行生成，最终与草稿发布原子写入。发布仍等待版本检查、更新日志、全部测试、打包及清单校验。
5. 每个平台的 Rust 单测和本地 functional 套件拆为两台机器执行，`fail-fast: false`。每项检查只执行一次；publish 依赖矩阵整体成功。
6. 纯 Rust job 直接调用原有 Node 脚本，去掉仅用于转调 Node 的 Bun 下载。原 Windows Bun 准备常耗时 30–60 秒，部分样本约 100 秒。前端及 workflow / 发布脚本检查均在 Ubuntu。
7. Rust 缓存统一版本和每平台 shared-key，CI/Nightly/Release 共用测试依赖；打包独立按平台/target 共用缓存。只有 rust 分片写测试缓存，functional 和 cloud 只读取；不缓存 Cargo 安装工具。
8. 只为 dev/test 关闭调试符号，保留调试断言、优化级别、全部用例和场景；release profile、签名、公证及 Sentry 符号上传保持原配置。打包缓存不受 test profile 设置影响。
9. setup-bun 使用内置可执行文件缓存及 GitHub 预编译二进制下载。Bun 依赖缓存只给需要前端依赖的打包 job，按平台共享。没有增加不需要的 Node/Go 工具链或 Rust 缓存。
10. 本机 runner 显式验证预装的 Bun 1.3.2、Rust stable、Cargo、目标平台，直接复用，不每次联网更新 Rust。hosted runner 继续 setup-rust。Windows 临时目录使用 RUNNER_TEMP，不假定 D: 存在。
11. Tauri action 只做构建、签名、公证；上传独立复用完成的文件。每个 gh 请求至多 3 次，覆盖上传前的资产 API 查询；临时硬链接保持原资产命名和签名字节，不复制大文件，不重新构建已完成的产物。上传前验证本次私有草稿及版本，Windows 显式使用 UTF-8。
12. 新增 `verify_only` 手动验收模式，默认正式发布行为保持不变。33 个发布/runner/计时工具测试覆盖发布门禁、签名文件、资产命名、请求重试、草稿边界、UTF-8、更新日志及原有清单逻辑。
13. 新增 Ubuntu `Workflow checks`。文档提交只执行轻量变更识别并返回同名成功检查；重检查步骤跳过，避免 workflow 级 paths-ignore 让 required check 永久 Pending。跨仓库源码触发器原本已有文档 paths-ignore。

[GitHub 并发文档](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency) 已支持 queue:max。actionlint 1.7.12 尚未收录该字段，lint 命令只忽略这一条精确的未知字段诊断，其余 workflow、表达式及 shell 检查全部运行；GitHub 实际运行也已验证服务端语法。缓存行为见 [Swatinem/rust-cache](https://github.com/Swatinem/rust-cache)、[setup-bun](https://github.com/oven-sh/setup-bun)。

## 本地连续构建

在独立临时 checkout、同一源码上测试，未改动共享源码开发工作区。

| 构建 | 第一次 | 第二次 | 第三次 |
| --- | ---: | ---: | ---: |
| 原 Rust cargo test --no-run | 77.640 秒 | 3.213 秒 | 0.417 秒 |
| 不生成 dev/test 调试符号 | 67.606 秒 | 3.491 秒 | 0.254 秒 |
| 前端 bun run build | 9.458 秒 | 6.580 秒 | — |

第二次 Rust 构建因 Tauri 首次生成 plist 的 mtime 多运行一次 build script；第三次完全 Fresh，没有持续重编译的不存在文件。关闭调试符号后，完整单测和 6 个本地功能场景通过。本机有既有 Cargo/sccache 状态及不同于 hosted runner 的工具链，以上用于验证连续构建，不作为全新机器冷构建基准。

前端脚本是 tsc && vite build，重复调用仍打包约 6.6 秒。发布的 Sentry release/dist 等构建输入每次不同，需要保留；Nightly/Release 的前端测试 job 不重复构建前端，由各平台打包时构建。仓库没有 Docker/Go 构建，因此没有添加相关缓存或安装步骤。工具均使用预编译版本，没有执行 cargo install / go install。

## 完整性和失败记录

保留原有的 744 个 macOS Rust 单测（4 ignored）、311 个 Windows Rust 单测（1 ignored）、242 个前端测试、两平台各 6 个本地功能场景、两平台云端功能回归（各 7 passed、原有 2 skipped），以及版本一致性、签名、公证、Sentry、资产及更新清单校验。

| 真实复测问题 | 处理 |
| --- | --- |
| 初次 Windows CI 本地套件栈溢出，41296857909 | 同步正式版既有的 16 MB 主线程栈设置到 CI/Nightly，完整场景复测通过 |
| 本机冗余 Rust 更新请求超时，41297751994 | 验证并复用已安装工具链，hosted 安装逻辑保留 |
| Apple 公证连接超时、上传前 GitHub API 超时，41297179239 / 41298036694 | 未跳过公证发布；上传拆分并覆盖完整请求重试，后续两轮实际公证和公开发布成功 |
| Windows 解析中文 Release JSON 使用 CP1252，41298795833 | 显式 UTF-8，增加真实子进程及旧 locale 回归测试，远端 Windows 上传成功 |
| 云端模型输出未命中原有“你好”断言，41298795833 / 41299519648 | 保留失败、原断言及门禁，没有给测试添加自动重试或放宽标准；最终完整复测两平台通过 |
| 首次新缓存预热，41296855226 / 41297796832 | 分别 744 秒 / 590 秒，记录迁移成本，不计入稳态提速样本 |

取消策略实测：同分支旧运行 41297580177 被新运行 41297588409 自动取消；master 的 41297471926 与 41297591554 重叠执行后均成功，旧主线运行没有被取消。主线取消逻辑还使用独立 run_id 避免 pending 替换。

云端模型回归仍有真实输出波动；最终成功验收不表示这些应用/第三方场景已经消除波动。全部失败记录可从 after-runs.json 追溯。

## 范围边界与复现

本次只修改 release 仓库。源码仓库 Voice-Wise/VoiceWise 的 trigger-ci.yml 仍按 SHA 分组，trigger-nightly.yml 仍可能取消旧 master 触发；未同步修改。在同步前，本接收端能保证已收到的主线请求完整执行，无法覆盖源头尚未发出就被取消的请求。本仓库 main 无分支保护或 ruleset，未修改保护配置；Workflow checks 保持稳定名称供 required check 使用。

纯文档提交 68fa633 的 [Workflow checks](https://github.com/Voice-Wise/release/actions/runs/41301285911) 实测成功：仅 checkout、变更识别及摘要执行，actionlint 下载、workflow 校验和发布脚本测试全部 skipped；同名检查返回 success。

```sh
python3 scripts/actions-timing.py --limit 50 --output /tmp/actions-baseline
python3 scripts/actions-timing.py --run RUN_ID --output /tmp/actions-after
```

脚本用 gh 采集 jobs 和日志；输出目录缓存已采集内容。重新采集同一 run 的新 attempt 时应使用新目录。原始日志留在本机临时目录，仓库只保存运行索引和计时数据。
