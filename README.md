# LiveType Release

This repository builds VoiceWise release artifacts from the private source repository.

Functional test policy:

- Nightly builds run only local functional tests that do not require API keys or real provider resources.
- Release builds run the full gate: local functional tests plus cloud regression tests that require provider credentials.
