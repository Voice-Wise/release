# LiveType Release

This repository builds VoiceWise release artifacts from the private source repository.

Nightly builds resolve the exact VoiceWise source commit after checkout, inject it into the application at compile time, and publish the same full SHA as `source_commit_sha` in `latest.json`. The SHA remains outside user-facing version and artifact names.

Functional test policy:

- Nightly builds run only local functional tests that do not require API keys or real provider resources.
- Release builds run the full gate: local functional tests plus cloud regression tests that require provider credentials.

本机 macOS ARM 构建、GitHub Secrets 使用及云端切换方式见 [本机 runner 说明](docs/local-runner.md)。
