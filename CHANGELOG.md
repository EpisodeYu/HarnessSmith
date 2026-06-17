# Changelog

All notable changes to HarnessSmith are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Web chat: a 3-tier tool-permission dropdown in the chat bar.
- Skills: a wizard-selectable bundled-skills catalog (`web-reading`).
- MCP catalog: keyed Bocha (in-GFW) search and Jina Reader for web access.

### Changed

- Dropped the bundled `example-skill` in favor of the curated skills catalog.

### Fixed

- CLI: close the MCP manager on every `run` exit path.
- MCP: reconnect a server whose session dies mid-run; decouple auth status from the connection indicator and gate unauthenticated remotes.
- Web: explain missing-key connection failures on the Tools page; keep an edited MCP server in place; keep the chat stream alive after a recovered tool error; keep the MCP auth box fillable; stop tool-call scrolling from trapping the reader at the bottom.
- LLM: guard non Chat-Completions responses and retry instead of crashing (#11).
- Generator: hard-bound the uvx prewarm so a stdio server cannot hang it (#10).
- Catalog: `fetch` ignores `robots.txt` so user-directed reads work.

## [0.1.0] - 2026-06-16

Initial public release.

### Added

- Config-to-code generator that renders a standalone, framework-free Python agent harness from a `HarnessSpec` (web wizard, terminal wizard, preset, or hand-written YAML).
- Native function-calling agent loop with paradigm dispatch (`agent` / `plan` / `ask`), lifecycle hooks, and graceful stop conditions.
- Dual LLM protocol, switchable at runtime: OpenAI-compatible Chat Completions (provider-agnostic via `base_url`) and native Anthropic Messages, with reasoning/thinking streaming.
- LLM profile registry with role routing, per-profile sampling, timeout/retry/fallback.
- Tool registry with risk levels (high-risk tools off by default), composable hooks, and a thin tool-policy layer.
- Local session persistence with resume/continue, a `chat` REPL, and crash-safe checkpointing.
- Context management: combinable triggers and strategies, tool-result clipping, overflow recovery, and a `max_steps` valve.
- Persistent per-LLM cost ledger with per-profile prices and hard cost limits.
- Optional modules (opt-in, leave no trace when off): FastAPI web interface with SSE chat and a paged bilingual `/config` panel, MCP client (stdio/HTTP/SSE) with a curated catalog, Agent Skills (`SKILL.md`), and cross-session memory.
- Runnability: `uv.lock` + `.python-version`, Dockerfile + devcontainer, `requirements.txt` fallback, a mock-LLM test suite, and post-generation smoke verification.

[Unreleased]: https://github.com/EpisodeYu/HarnessSmith/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/EpisodeYu/HarnessSmith/releases/tag/v0.1.0
