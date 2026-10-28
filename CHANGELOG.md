# Changelog

All notable changes to Easel are documented in this file.

## [Unreleased]

### Added

- Added `easel up`, which starts the OpenClaw gateway (reusing a healthy one) and then the Web workspace, so a single command — `uv run --no-sync easel up` — brings up both. `Ctrl+C` stops only the gateway this run started; `--keep-gateway` leaves it running and `--no-gateway` skips it. When the configured engine needs no gateway (direct API, Codex, OpenCode), it goes straight to the Web UI.
- `easel up` / `easel web` now take their default port from `EASEL_PORT` (environment or `.env`), so a non-default port no longer has to be passed on every invocation. This matters on WSL, where Windows reserves TCP 7409–7979: `localhost:7860` can never be mirrored by `wslrelay`, and the failure is silent (connection refused, nothing logged).

### Improved

- `setup.sh` now prefers **uv** for Python dependencies and **pnpm** for the Web frontend. Either tool is installed into the user directory when missing (`astral.sh/uv` installer, `npm install -g pnpm`) and the installer falls back to pip / npm if that fails, so the previous path still works unchanged.
- uv removes the `python3-venv` prerequisite: `python3 -m venv` aborts on minimal images without `ensurepip` (Ubuntu without `python3-venv`), and non-interactive installs previously warned and fell back to system Python. Both now create `.venv` with `uv venv --seed`.
- Added `web/frontend/pnpm-lock.yaml`, generated from the existing `package-lock.json` with `pnpm import`, so the pnpm path installs with `--frozen-lockfile`. `package-lock.json` is kept for the npm fallback.
- Added `EASEL_PYTHON_TOOL` (`auto|uv|pip`) and `EASEL_NODE_TOOL` (`auto|pnpm|npm`) to pin either package manager.
- Tool detection now ignores WSL-interop binaries under `/mnt/`. A Windows `node` / `npm` / `pnpm` on `PATH` can no longer be mistaken for a Linux toolchain, which used to install dependencies against Windows paths.

### Fixed

- Browser login/publishing no longer fails silently on minimal Linux images. `setup.sh` now installs Playwright's Chromium **system** dependencies (`playwright install-deps chromium`; skipped without root, with the manual command reported instead), and both the installer and `easel doctor` verify a real headless launch instead of only checking that the browser binary exists. Previously `playwright install chromium` reported success while the process exited with code 127 (`libnspr4.so: cannot open shared object file`), so every login attempt ended with “browser couldn't open” — a reason visible only in `outputs/_login/`.
- `Playwright Chromium` in `easel doctor` now distinguishes “not downloaded” from “downloaded but cannot launch”, and the failure hint points at `install-deps` rather than suggesting a re-download that cannot help.
- Installer summary and post-install hints now lead with `easel up` instead of `easel web`.
- The uv path in `setup.sh` is now fail-soft end to end. Missing `uv` is installed into `~/.local/bin` through the official installer (curl, with a wget fallback — minimal images often ship only one); directories without `pyproject.toml` never enable uv, so it can no longer fail with “does not appear to be a Python project”; and if `uv pip install -e` fails, the installer retries once with pip instead of aborting under `set -e`. The `uv venv` step gained the same final fallback to `python3 -m venv`.
- `setup.ps1` gained the same uv support as `setup.sh`, so native Windows installs resolve dependencies faster. `uv` is installed into the user directory through `winget` (official installer as fallback) when missing; `.venv` is created with `uv venv --seed`; dependencies install with `uv pip install -e … --python <venv>` and fall back to pip on failure. `EASEL_PYTHON_TOOL=auto|uv|pip` overrides the choice, and a directory without `pyproject.toml` never enables uv.

### Notes

- Global OpenClaw still installs through npm by design: pnpm's global bin depends on `PNPM_HOME`, and pnpm 10+ blocks dependency postinstall scripts, which OpenClaw's bundled plugins rely on.
- Venv activation is no longer documented as a required step: the generated `easel` console script carries an absolute shebang into `.venv/bin/python`, so `.venv/bin/easel <cmd>` runs without `source .venv/bin/activate`. The documented uv entry point is `uv run --no-sync easel web`; plain `uv run` resolves dependencies and writes a 1 MB+ `uv.lock`, so `uv.lock` is intentionally untracked (`.gitignore`) to keep the env unpinned unless a lockfile is deliberately adopted.
- Added `.gitattributes` pinning `*.sh` and lockfiles to LF. A Windows checkout with `core.autocrlf=true` otherwise hands `bash setup.sh` a CRLF script, which fails with `$'\r': command not found`.

## [0.3.0] - 2026-10-12

### Added

- Added selectable execution engines in Web settings: OpenClaw, Codex, OpenCode, a locally configured ACP agent, and chat-only mode. Engine selection is independent of model providers; Codex and OpenCode expose native model catalogs without copying their credentials.
- Added optional OpenClaw installation: interactive setup defaults to OpenClaw but allows skipping it; use `bash setup.sh --skip-openclaw` or `.\setup.ps1 -SkipOpenClaw` to install the Web workspace first and select an already installed harness later.
- Added a responsive creative-artifact gallery with previous/next controls, keyboard navigation, and support for multiple outputs.
- Added documentation and Agent-prompt path validation, plus harness-settings regression coverage across Linux, macOS, Windows, and Python 3.10/3.12.

### Improved

- Moved shared Agent prompts and workspace resources to `agents/`, and built-in skills to `skills/builtin/`, replacing the OpenClaw-specific directory names. Updated documentation, prompt paths, installer references, and skill synchronization accordingly.
- Improved harness CLI discovery across user-specific npm, Node, and native installations, including Windows launchers and incomplete environments.
- Preserved conversation ownership, native-session continuation, and existing browser history when switching personas or execution engines.
- Improved settings loading, unified input and dropdown styling, retained configuration panels for unavailable harnesses, and prevented the sidebar Settings button from wrapping.
- Added custom-model reasoning capability configuration and improved provider credential synchronization.

### Fixed

- Improved QR capture, retry freshness, navigation-timeout handling, and terminal login-state polling for Xiaohongshu, Zhihu, and WeChat Channels.
- Improved account verification and nickname/avatar extraction; stale verification responses no longer overwrite newly logged-in accounts.
- Fixed UTF-8 handling and Windows installation PATH preservation, and improved installer idempotency and configuration validation.
- Fixed runtime version drift: package metadata and harness protocol handshakes now report the same Easel version.
- Fixed Python 3.10 compatibility when stopping Agent execution, including repeated-stop protection during process cleanup.

### Upgrade Notes

- Update to this version and rerun the appropriate setup script. For an existing OpenClaw workspace, `bash agents/sync.sh --docs-only` refreshes prompts without replacing private memory or user-provided skills.
- Codex and OpenCode must be installed and authenticated separately before selection. Chat-only mode does not run tools or skills; generic ACP requires a local command configuration.
- Platform maintenance, network restrictions, and anti-abuse checks can still prevent QR login; this release improves detection and error reporting rather than bypassing those restrictions.

## [0.2.1] - 2026-09-24

### Added

- Added a unified **Settings panel** in the workbench (模型配置 · 环境安装 · 更多设置). Model configuration is now editable in the browser across all six channels (chat / transcribe / image / video / music / speech): edit provider, model, Base URL and API key, add custom providers, switch primary/backup, and run a real self-test that reports actual handshake latency. Saving writes to `.env`; keys are returned masked and an empty key field means "leave unchanged".
- Added a runtime **environment installer** (`install_tool.py`) plus an in-panel 环境安装 page: local engines are health-checked for real, installed in the background, and their status is written back as the job progresses.
- Added read-back reconciliation to Bilibili upload: after posting, the member submission API is queried directly and the run only counts as successful if the read-back matches.
- Added `vendor/VENDOR.md` recording the provenance of the bundled `video-pipeline-sdk` (upstream, version, local modifications, how to resync).

### Improved

- Improved conversation latency: the Web chat now talks to the resident gateway over its OpenAI-compatible HTTP endpoint instead of spawning a thin `openclaw agent` client every turn, saving roughly 3s per turn (measured on Linux: 7.6s → 4.5s end-to-end). Transport is pinned per session and never switches mid-conversation, so history is never silently dropped. Set `EASEL_CHAT_TRANSPORT=cli` to return to the old path.
- Improved responsiveness of the outputs library: `/api/outputs` moved to a thread pool so a full product-tree scan no longer blocks the event loop.
- Improved CI coverage: the suite now runs `pytest` instead of `pytest tests/`, so the 38 skill-bundled tests under `skills/**/tests/` actually run in CI.

### Fixed

- Fixed Windows installation on PowerShell 5.1, where `setup.ps1` failed outright during the configuration-writing stage (issue #41).
- Fixed workspace resolution: `sync.sh`, `setup.ps1`, `doctor` and the video pipeline each hard-coded a different workspace path, so on the other OpenClaw layout they wrote to a directory the agent never reads — while still reporting success. All four now ask OpenClaw itself for its runtime `workspaceDir` (issue #19).
- Fixed a placeholder API key in `.env.example` silently disabling the whole OpenAI-compatible branch of `setup.sh`, which produced a config with no provider while `doctor` still reported all green. `doctor` now verifies that the primary model's provider actually has credentials.
- Fixed the HTML preview in the content library: the built-in「复制到公众号」button now works inside the preview drawer, and the preview always renders the latest version instead of a heuristically cached one.
- Fixed images breaking after pasting into WeChat: local images referenced by a preview are inlined as base64 data-URIs, so the bytes travel with the clipboard instead of requiring WeChat to fetch a local Easel URL.
- Fixed `install_tool.py` crashing under non-UTF-8 locales on Windows, which left the install endpoint with an empty id allowlist and made the 环境安装 page reject every tool.
- Fixed domestic-platform publishing to fall back to a direct connection (Chromium-level `--no-proxy-server`), so it works with a VPN enabled.
- Fixed `scripts/gateway.ps1` missing its UTF-8 BOM — the only Chinese-containing `.ps1` without one, which PowerShell 5.1 decoded using the system ANSI code page.

### Security

- Hardened the settings and install endpoints: the install id allowlist is derived from the engine's own recipe table, and settings writes are validated server-side.
- Closed a command-injection hole in `.env` writes. The previous guard only rejected newlines, but `setup.sh` sources `.env`, so a non-newline value such as `KEY=$(id)` still reached bash's command substitution. Values are now restricted to the character set these fields actually need.
- Added a Content-Security-Policy to the 公众号 preview page. The preview iframe needs `allow-scripts` for its copy button, and an opaque origin is not enough protection because the Web API is CORS-open and unauthenticated — reproduced in a real browser, a script embedded in generated content could call a local endpoint and read the response. `connect-src 'none'` now blocks that exfiltration path while leaving the copy button and image rendering intact.

[0.2.1]: https://github.com/ZJU-REAL/Easel/releases/tag/v0.2.1

## [0.2.0] - 2026-09-18

### Added

- Added the `video-production` Skill: an end-to-end video pipeline (probe → transcribe → scenes → design table → scaffold → verify → preview → render → deliver) with two human confirmation gates and quality gates (five-piece manifest, loudness, transitions). The upstream `video-pipeline-sdk` (MIT) is now vendored into the repo so the pipeline is self-contained, reproducible, and editable. Skill count is now 114.
- Added three-tier transcription with automatic fallback: SRT/VTT subtitles first, then SiliconFlow ASR API, then local whisper as a last resort — so a run no longer requires downloading the 3GB model when a transcript or API key is available.
- Added a **「笔」capability menu** to the workbench input area: click to browse everything Easel can do ("能做的都在这"); selecting an item prefills the prompt.
- Added a ffmpeg-based slideshow renderer for image-storyboard voiceover dramas (Ken Burns, differentiated transitions, libass dynamic captions, light whoosh SFX, loudnorm).

### Improved

- Improved the Skill library display: Chinese display names shown large with the original name beneath, kept in sync across search and the drawer.
- Improved in-conversation cards to support multi-select (`ask_user` multiSelect rendering and multi-value submission).
- Improved file uploads: files exceeding the upload limit are automatically converted to local materials via a copy channel (without changing the 50MB config).
- Improved reasoning visibility: `--thinking` now defaults to medium so chain-of-thought shows when the gateway supports it.

### Fixed

- Fixed chain-of-thought (CoT) display in the Web conversation: token/thinking now streams token-by-token, and the anti-stall heartbeat no longer overrides real status.
- Fixed the Gemini adapter to support `streamGenerateContent` streaming.
- Fixed UTF-8 persistence on Windows (state read/write) and migrated the shutdown hook to a lifespan handler.

[0.2.0]: https://github.com/ZJU-REAL/Easel/releases/tag/v0.2.0

## [0.1.1] - 2026-09-15

### Added

- Added WeChat Official Account (公众号) support: article publishing, Data Center metrics, and account management via a background QR-scan session.
- Added an optional vendored typesetting Skill (`gzh-design`, AGPL-3.0), bringing the Skill count to 113.

### Improved

- Improved the workbench **创作数据** panel: Bilibili and Douyin now populate "近 7 日 · 环比" (7-day metrics with week-over-week change) and "最近作品" (recent works).
  - Bilibili reads the creator overview API for play/like/comment/favorite/share/follower deltas, and lists recent uploads (title/link/cover/stats).
  - Douyin parses the real "近 7 日" labels with a section anchor to avoid mis-reading the "最新作品" card, handles the "较前7日±X" delta format, hardens polling stability, and scrapes recent works from the content-manage page.

### Fixed

- Fixed OpenClaw version detection in `easel doctor` on Windows (the `.cmd` shim cannot be invoked bare).
- Fixed cross-platform gateway/launcher robustness and Xiaohongshu login navigation races.

[0.1.1]: https://github.com/ZJU-REAL/Easel/releases/tag/v0.1.1

## [0.1.0] - 2026-08-31

Easel's first public release, jointly developed by REAL Lab and OpenDCAI Lab.

### Highlights

- Added an end-to-end social media operations workflow covering discovery, planning, creation, publishing, and attribution.
- Added profile-driven account context and persistent operating memory across sessions and platforms.
- Added 112 executable Skills for research, writing, visual production, audio, video, publishing, and analytics.
- Added the Web workspace and CLI for running workflows, inspecting outputs, and managing projects locally.
- Added multimodal production workflows for knowledge cards, stories, lifestyle content, audio, and video.
- Added publishing workflows for Xiaohongshu, Douyin, Kuaishou, Zhihu, Bilibili, and WeChat Channels.
- Added output manifests, publishing checks, content calendars, and performance attribution workflows.
- Added Chinese and English documentation, examples, product showcases, and institutional branding.

[0.1.0]: https://github.com/ZJU-REAL/Easel/releases/tag/v0.1.0
