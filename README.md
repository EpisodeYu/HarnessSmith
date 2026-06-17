<div align="center">

<img src="docs/assets/social-preview.png" alt="HarnessSmith" width="720">

# HarnessSmith

**Forge your own agent harness.**

A config-to-code generator that produces a standalone, framework-free agent harness you fully own — no LangChain, no LangGraph, no ADK, and no dependency on HarnessSmith after generation.

[![PyPI version](https://img.shields.io/pypi/v/harnessmith.svg)](https://pypi.org/project/harnessmith/)
[![PyPI downloads](https://img.shields.io/pypi/dm/harnessmith.svg)](https://pypi.org/project/harnessmith/)
![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)
[![GitHub stars](https://img.shields.io/github/stars/EpisodeYu/HarnessSmith?style=flat&logo=github)](https://github.com/EpisodeYu/HarnessSmith/stargazers)

**English** | [中文](#harnessmith-1)

</div>

---

<!-- Demo: record the web chat (token streaming + tool-call panel) or a CLI run and drop a GIF here. -->
<!-- <p align="center"><img src="docs/assets/demo.gif" alt="HarnessSmith demo" width="820"></p> -->

## Quick start

Pick how to launch the setup wizard — either way you build a standalone, framework-free harness **from scratch** (you choose the capabilities: paradigms, web UI, MCP, skills, memory) that is smoke-verified before handover.

**Clone the repo and run the one-click launcher** — cross-platform (Windows, macOS, Linux), nothing to memorize; double-clicking the file works too. It installs [uv](https://docs.astral.sh/uv/) on first use, then asks whether you want the web wizard (recommended) or the terminal wizard:

```bash
git clone https://github.com/EpisodeYu/HarnessSmith.git && cd HarnessSmith
./HarnessSmith.sh     # macOS / Linux  — or double-click it
HarnessSmith.bat      # Windows        — or double-click it
```

**Or run it on demand with [uv](https://docs.astral.sh/uv/)** — no clone, nothing installed permanently:

```bash
uvx --from "harnessmith[wizard]" harnessmith wizard --open   # web wizard (recommended)
uvx harnessmith new                                          # or the interactive CLI wizard
```

Then start the project you just created and chat — set your model and key right in the web interface (recommended), or use the terminal:

```bash
cd my-agent                    # the name you chose
uv run my-agent serve --open   # recommended: configure your model and chat, all in the browser
uv run my-agent chat           # optional: chat in the terminal
```

See [Getting started](#getting-started) for every option, including non-interactive generation from a hand-written spec.

## Why HarnessSmith?

Most "agent starters" hand you an app wired to a framework you cannot remove. HarnessSmith generates a repository that is **yours** — readable, editable, and free of any agent-orchestration framework.

| | HarnessSmith | LangGraph scaffolds | ADK / static templates |
|---|---|---|---|
| Agent-framework lock-in | **None** — a plain Python loop you own | LangGraph runtime | ADK / mixed frameworks |
| Edit or delete any line | **Yes** — self-contained repo | Limited — app sits on the framework | Limited |
| Config-to-code (only selected capabilities are generated) | **Yes** | No — fixed template | No |
| Core loop size | **~150–300 lines** | Abstracted by the framework | Abstracted by the framework |
| Runtime dependency on the generator | **None** | Framework runtime | Framework runtime |
| Tests + lockfile + Dockerfile, smoke-verified on generation | **Yes** | Varies | Varies |
| Dual LLM protocol, switchable at runtime (OpenAI + Anthropic) | **Yes** | Varies | Varies |

## Overview

HarnessSmith is a generator for the agent harness, in the spirit of `create-next-app`. A specification (`HarnessSpec`) is captured through a web wizard, an interactive terminal wizard, a preset, or a hand-written YAML file; HarnessSmith then renders a **complete, independent Python repository** — readable, editable, testable, and runnable on its own. The generated project is not a consumer of HarnessSmith: once generated, it has zero relationship with the generator.

### Design positioning

- **No agent-framework lock-in.** The generated code has zero dependency on any agent-orchestration framework. The loop is plain Python that you own. Ordinary general-purpose libraries (OpenAI SDK, Pydantic, Typer, FastAPI) are used as libraries, not as frameworks that own your control flow.
- **Own your code.** The output is a self-contained repository with its own tests, lockfile, Dockerfile, and documentation. Every line can be read, changed, or deleted.
- **Config-to-code.** Capabilities are selected at generation time; the generator renders only what was selected. A feature that is switched off leaves no trace — no module, no dependency, no dead code.
- **Thin by default.** The default product is a minimal, fully runnable harness whose core loop stays in the low hundreds of lines. Heavier capabilities (MCP, web interface, skills, memory) are opt-in spec toggles.

## Highlights

<details>
<summary><b>Full capability list</b> — click to expand</summary>

<br>

- **Native function calling** — the loop drives the model through the API's `tool_calls` (TAO/ReAct semantics), not through text parsing.
- **Dual LLM protocol, runtime-switchable** — every product ships both an OpenAI Chat Completions client (provider-agnostic via `base_url`: vLLM, Together, Groq, LiteLLM, any compatible endpoint) and a native Anthropic Messages client. Each LLM profile selects its `provider` in runtime configuration; no regeneration required.
- **Reasoning streams as a first-class signal** — thinking/reasoning deltas are surfaced live (a status line in the CLI; a collapsible reasoning panel in the web UI), and `reasoning_content` is preserved across tool-calling turns for models that require it.
- **Multi-paradigm runtime** — `agent` (default tool-calling loop), `plan` and `ask` (both read-only), selectable per turn (`--mode` / web dropdown). Paradigms live in a thin registry; users add their own with `@register_paradigm` without touching the built-ins.
- **Sessions and resumption** — every conversation persists locally; resume with `--continue` / `--resume <id>`, in the multi-turn `chat` REPL, or from the web session sidebar (automatic titling, rename, delete). In the web UI, conversations run in parallel — each session streams independently and switching the sidebar never interrupts a background run. Interrupted runs are crash-safe: state is checkpointed at message boundaries and repaired on resume.
- **Stop / continue / re-ask** — a run can be cancelled mid-turn (cooperative cancellation that also terminates streaming), continued later with full context, or — in the web UI — re-asked by editing any earlier prompt and regenerating from that point.
- **Human-in-the-loop** — a built-in `ask_question` tool lets the model ask the user structured clarifying questions, and tool-call confirmation (`allow once / reject / allow for session / allow always`) gates risky tools. Non-interactive contexts fail closed.
- **Persistent per-LLM cost accounting** — a usage ledger accumulates token counts per LLM profile across runs; cost is derived from per-profile prices, and a per-profile `cost_limit` blocks the model before the next call once reached. Managed from the web Budget page or the `usage` CLI.
- **Context management** — combinable triggers (`window_pct`, `max_tokens`, `max_turns`; driven by real token usage) select when to compact; strategies (`truncate`, `summarize`, `none`) define how; both are user-extensible registries. Oversized tool results are clipped before entering history, overflow recovery compacts on demand, a `max_steps` valve bounds runaway tool loops, and compaction folds within a single long turn (sub-turn `keep_last_steps`) so even one agentic turn stays inside the window.
- **Composable hooks and a thin tool-policy layer** — mount one or more `Hooks` subclasses through `config.hooks` (subclass-and-mount, no `@register_hook`); five lifecycle points (`before_step` / `after_step` / `before_tool` / `after_tool` / `on_error`). `before_tool` may refuse a call and `after_tool` may redact a result — a code-level policy gate with no middleware machinery — and multiple hooks compose in order. The web UI has a dedicated **Hooks** tab with a privacy-safe execution log; `info` (CLI) and `GET /registries` (web) surface every extension point — tools, paradigms, context strategies/conditions, memory backends, imported extensions, and mounted hooks.
- **Per-session working directory** — an optional working-directory hint (CLI `--cwd`, the `chat` REPL's `/cwd`, or the web chat toolbar with a directory browser) is injected into the system prompt as guidance, not a sandbox. The current date/time is injected each turn too.
- **Tool ecosystem without built-in bloat** — a decorator-based tool registry with per-tool risk levels, plus an opt-in MCP client (stdio, HTTP, and SSE transports) with a curated catalog (keyless multi-engine web search, fetch, git, time, Desktop Commander, GitHub). The default web-search server is keyless and multi-engine (Bing/Baidu/DuckDuckGo/Brave/Sogou/…) with automatic failover, so it keeps working when any single engine is slow or unreachable on a given network. Node-based MCP servers are `npm install`ed once into a stable per-server dir and launched directly with `node` (never the ephemeral `npx` cache, which is unreliable on Windows). MCP servers are managed at runtime: health status, add/edit/remove, and hot reconnection from the web panel; `mcp status` from the CLI.
- **Agent Skills** — opt-in support for the open `SKILL.md` standard with progressive disclosure; skills are plain files, no framework involved.
- **Cross-session memory** — an opt-in, self-maintained long-term note injected each turn, written through tools, consolidated by a dedicated LLM role at session boundaries, and replaceable via a thin `@register_memory` backend registry.
- **Always-applied project rules** — markdown rule files (`AGENTS.md` / `CLAUDE.md` / `.cursor/rules` conventions) injected into every system prompt.
- **Full observability** — a JSONL trace per run with token/cost accounting, and an opt-in, local-only debug log that records lifecycle events (names, counts, durations) and never message content, tool arguments, or secrets.
- **Verified runnable before handover** — the generator locks dependencies and smoke-tests every new repository (`uv sync`, import check, a mock function-calling turn, `pytest`) before declaring it ready.

</details>

## What gets generated

### Core (always present)

| Capability | Description |
|---|---|
| Agent loop | Native function-calling loop with paradigm dispatch, lifecycle hooks, and graceful stop conditions (including a `max_steps` valve) |
| LLM layer | Profile registry with role routing (`generation`, `compaction`, plus optional `title` / `memory` roles), per-profile sampling parameters, timeout/retry/fallback, and dual-protocol clients (OpenAI-compatible + native Anthropic) |
| Tool registry | Decorator-registered tools with risk levels; high-risk tools disabled by default, allowlist-only |
| Hooks & policy | Composable `Hooks` subclasses mounted via `config.hooks`; observer + tool-policy lifecycle points (`before_tool` refuse / `after_tool` redact); extension discoverability via `info` / `GET /registries` |
| Sessions | Local JSON persistence, `--continue` / `--resume`, `chat` REPL, crash-safe checkpointing, per-session working-directory hint |
| Interaction | `ask_question` structured clarification + HITL tool confirmation, shared CLI/web infrastructure |
| Context | Trigger/strategy compaction registries, tool-result clipping, overflow recovery, `max_steps` bound, sub-turn folding |
| Budget | Persistent per-LLM cost ledger with per-profile prices and hard cost limits |
| Prompts | System prompt assembly with always-applied rule-file injection, current date/time, and the working-directory hint |
| Observability | JSONL trace + token/cost counts; opt-in local-only debug log |
| CLI | `run`, `chat`, `info`, `test-llm`, `set-key`, `usage` (plus `serve`, `mcp`, `memory` when the matching modules are enabled) |
| Runnability | `uv.lock` + `.python-version`, Dockerfile + `.dockerignore` + devcontainer, `requirements.txt` pip fallback, mock-LLM test suite, one-click launcher script |

### Optional modules (spec toggles; disabled = absent from code and dependencies)

| Module | Description |
|---|---|
| Web interface | FastAPI + SSE chat with token-level streaming, collapsible reasoning and tool-call panels, a session sidebar with parallel per-session conversations, a chat toolbar (paradigm, generation model, working-directory picker), and a paged bilingual (en/zh) `/config` panel — LLM, Context, Tools, MCP, Hooks, Paradigms, Prompts, Budget, Memory, Observability, and System tabs (MCP and Memory appear only when those modules are enabled). Edits apply live and are written back to `config.yaml` with comments preserved |
| MCP tools | Model Context Protocol client over stdio / HTTP / SSE, allowlist and risk flags, curated catalog prefill, runtime server management with health probes and hot reconnect |
| Agent Skills | `SKILL.md` discovery, metadata injection, and on-demand loading |
| Long-term memory | Self-maintained markdown note with tool-driven writes, policy shaping, consolidation, and a pluggable backend registry |

## Architecture

```mermaid
flowchart LR
  user[User] --> entry["CLI / terminal wizard / web wizard"]
  entry --> spec["HarnessSpec (Pydantic, YAML)"]
  spec --> gen["Generator (Jinja2)"]
  templates["Template library (no agent framework)"] --> gen
  catalog["MCP catalog"] -.-> gen
  gen --> repo["Generated repository (independently owned)"]
  subgraph repoInner [Generated repository]
    loop["loop.py + paradigms/ (agent / plan / ask)"]
    llm["llm.py + llm_anthropic.py (dual protocol)"]
    tools["tools.py (+ mcp.py stdio/http/sse)"]
    sessions["session.py + interaction.py"]
    ctx["context.py + usage.py + trace.py"]
    hooks["hooks.py + extensions.py (policy + discovery)"]
    cli["interfaces/cli.py"]
    web["interfaces/web.py (SSE chat + /config)"]
    extras["skills.py / memory.py (opt-in)"]
    docker["Dockerfile + devcontainer"]
  end
  repo --> repoInner
```

The generator and its output are strictly separated layers. The spec decides **structure** (which capabilities are compiled in); the generated product's `config.yaml` is the **runtime authority** for behavior (models, prompts, tool allowlists, context parameters, prices and limits) — all adjustable without regeneration.

## Technology stack

**Generator**

- Python ≥ 3.11, managed end-to-end with [uv](https://docs.astral.sh/uv/)
- [Typer](https://typer.tiangolo.com/) (CLI), [questionary](https://github.com/tmbo/questionary) (interactive terminal wizard)
- [Jinja2](https://jinja.palletsprojects.com/) (template rendering)
- [Pydantic v2](https://docs.pydantic.dev/) + PyYAML (`HarnessSpec` validation and serialization)
- FastAPI + uvicorn (web wizard, optional `[wizard]` extra — never shipped into products)

**Generated product**

- Runtime: `openai` (Chat Completions, provider-agnostic via `base_url`), `anthropic` (native Messages), `pydantic` + `pydantic-settings`, `pyyaml`, `typer`
- Web interface (when enabled): `fastapi`, `uvicorn`, `ruamel.yaml` (comment-preserving config write-back); the UI is a single static page (Tailwind CSS via CDN, no build step)
- MCP (when enabled): the official `mcp` SDK
- Tests: `pytest` with an offline mock LLM (dev dependency group; not a runtime dependency)
- Environment contract: uv (`uv.lock` + `.python-version`) with Docker and `requirements.txt` fallbacks

The generated `pyproject.toml` contains no agent-orchestration framework, and the test suite asserts it.

## Getting started

### Prerequisites

- [uv](https://docs.astral.sh/uv/getting-started/installation/) (uv provisions the correct Python automatically; no system Python required)
- Docker (optional, for containerized runs)

### Installation

HarnessSmith is published on [PyPI](https://pypi.org/project/harnessmith/). With [uv](https://docs.astral.sh/uv/) you can run it without installing anything:

```bash
uvx --from "harnessmith[wizard]" harnessmith wizard --open      # launch the web wizard (recommended)
uvx harnessmith new                                             # or the interactive CLI wizard
```

Prefer a persistent install? Any of these work:

```bash
uv tool install harnessmith        # install the CLI with uv
pip install harnessmith            # or with pip
# from source (for development):
git clone https://github.com/EpisodeYu/HarnessSmith.git && cd HarnessSmith && uv sync
```

### Generating a harness

**The easiest start** is the one-click launcher in the repository root — double-click or run `HarnessSmith.sh` (macOS / Linux) or `HarnessSmith.bat` (Windows). It offers a choice between the **web wizard** (recommended) and the terminal wizard, and installs uv on first use.

Prefer the command line? Each surface is a single command:

```bash
uv run harnessmith wizard                                   # web wizard (recommended; uv sync --extra wizard)
uv run harnessmith new                                      # interactive terminal wizard
uv run harnessmith new my-agent --preset coding-assistant   # non-interactive, from a bundled preset
uv run harnessmith new my-agent --spec ./harness.spec.yaml  # non-interactive, from a hand-written spec
uv run harnessmith doctor                                   # preflight check of the local toolchain
```

- The **web wizard** (`wizard`) and the **terminal wizard** (`new` with no `--spec` / `--preset`) collect the same structural choices — display name, paradigms, web interface, MCP, skills, memory — and apply identical defaults; the web wizard suits desktops, the terminal wizard suits headless servers.
- After rendering, the generator locks dependencies and runs a smoke verification (`uv sync`, import check, one mock function-calling turn, `pytest`). Pass `--no-verify` to skip it, for example when offline.
- Secrets are never collected by any wizard and never enter the spec, the generated `config.yaml`, or git.
- The `--preset` shortcut is for scripted or CI generation, not the recommended start: the bundled `coding-assistant` preset enables MCP with **every tool allowlisted — shell and file writes included — and no confirmation gate** (`confirm: none`). Prefer a wizard, or review `config.yaml` (tighten the tool allowlist, set `confirm: high`) before pointing it at a real model.

### Running the generated harness

**The simplest path** is the generated repo's own one-click launcher, named after the display name with spaces collapsed to `-` (e.g. `My-Coding-Assistant.sh` / `.bat`, so it needs no shell quoting). It auto-syncs dependencies and, for web-enabled products, starts the web chat and opens your browser; otherwise it opens a terminal chat.

Equivalently, from the command line:

```bash
cd my-agent
uv sync                                  # uv provisions Python + an isolated venv
uv run my-agent set-key OPENAI_API_KEY   # write the API key into .env (never echoed, never in git)
uv run my-agent serve --open             # web chat + /config panel (web-enabled products; recommended)
uv run my-agent test-llm                 # probe each configured model
uv run my-agent chat                     # multi-turn conversation in the terminal
uv run my-agent run "Summarize ./notes"  # single turn; add --mode plan|ask, --stream, --cwd

# fully containerized alternative (generated by default):
docker build -t my-agent . && docker run --rm -it my-agent
```

Model and endpoint are configured in `config.yaml` (or on the web `/config` LLM tab): set `model`, point `base_url_env` / `api_key_env` at the appropriate environment variables, and choose `provider: openai` or `provider: anthropic` per profile. An offline trial without any key is available via `--mock` on `run`, `chat`, and `serve`.

### Product CLI reference

| Command | Purpose |
|---|---|
| `run [PROMPT]` | Execute one turn. Options: `--mode agent\|plan\|ask`, `--stream`, `--continue`, `--resume <id>`, `--role`, `--cwd`, `--mock` |
| `chat` | Multi-turn REPL with persistent sessions; `/cwd` sets the working-directory hint; `Ctrl-D` or `/exit` to quit |
| `serve` | Start the web interface (`--host`, `--port`, `--open`); web-enabled products |
| `info` | Introspect every extension point — registered tools, paradigms, context strategies/conditions, memory backends, imported extensions, and mounted hooks |
| `test-llm` | Connectivity and capability probe for each configured LLM profile |
| `set-key <ENV_NAME>` | Write a secret into `.env` without echoing it or touching git |
| `usage` | Inspect or clear the persistent per-LLM cost ledger |
| `memory show\|clear\|path\|consolidate` | Manage the long-term memory note; memory-enabled products |
| `mcp status` / `mcp warm` | Probe MCP server health / pre-warm launchers; MCP-enabled products |

### Configuration model

| Layer | File | Role |
|---|---|---|
| Generation-time spec | `harness.spec.yaml` | The recipe: which capabilities are compiled into the product, plus initial values. A snapshot is kept in the generated repository |
| Runtime configuration | `config.yaml` | The authority for behavior: LLM profiles and roles, prompts and rule files, tool allowlist, context strategy, hooks, MCP servers, prices and cost limits, observability. Editable by hand or via the web `/config` panel (live application + comment-preserving write-back) |
| Secrets | `.env` (gitignored) | The only location for real credentials. `config.yaml` and the spec reference environment-variable *names* only |

Structural changes (adding or removing an interface or module) require regeneration; behavioral changes never do.

## Security model

- **Secrets never enter git.** Real values live exclusively in the gitignored `.env`; all other files reference environment-variable names. `set-key` and the web panel's key writer are write-only and never echo values. Traces and the debug log record no secrets.
- **High-risk tools are off by default.** Shell and file-writing tools ship disabled and require explicit allowlisting; the runtime allowlist can only narrow the set compiled in at generation time, never extend it.
- **Human-in-the-loop confirmation** (`tools.confirm: none|high|all|<tool names>`) intercepts risky tool calls with `allow once / reject / allow for session / allow always`; non-interactive contexts reject by default. Confirmation is a guardrail for trusted operators, not a security boundary — hard isolation belongs to Docker or to excluding the capability at generation time.
- **The web interface targets local, trusted use.** The `/config` panel and the MCP management page can modify runtime behavior and launch local processes; do not expose them to untrusted networks.

## License

[MIT](./LICENSE) © 2026 EpisodeYu

---

<div align="center">

<img src="docs/assets/social-preview.png" alt="HarnessSmith" width="720">

# HarnessSmith

**锻造你自己的 agent harness。**

一个"配置即生成"的代码生成器,产出一套你完全拥有的独立 agent harness 代码仓库——不绑定任何 agent 编排框架(无 LangChain、LangGraph、ADK),生成后不再依赖 HarnessSmith。

[![PyPI version](https://img.shields.io/pypi/v/harnessmith.svg)](https://pypi.org/project/harnessmith/)
[![PyPI downloads](https://img.shields.io/pypi/dm/harnessmith.svg)](https://pypi.org/project/harnessmith/)
![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)
[![GitHub stars](https://img.shields.io/github/stars/EpisodeYu/HarnessSmith?style=flat&logo=github)](https://github.com/EpisodeYu/HarnessSmith/stargazers)

[English](#harnessmith) | **中文**

</div>

---

## 快速上手

选择启动配置向导的方式——两种都从头生成一套独立、无框架锁定的 harness(能力由你勾选:范式、Web 界面、MCP、技能、记忆),并在交付前完成冒烟自检。

**克隆仓库并运行一键启动器**——跨平台(Windows、macOS、Linux),无需记命令,双击文件也能跑。它会在首次使用时安装 [uv](https://docs.astral.sh/uv/),随后询问你要 Web 向导(推荐)还是终端向导:

```bash
git clone https://github.com/EpisodeYu/HarnessSmith.git && cd HarnessSmith
./HarnessSmith.sh     # macOS / Linux  —— 或直接双击
HarnessSmith.bat      # Windows        —— 或直接双击
```

**或用 [uv](https://docs.astral.sh/uv/) 按需运行**——无需克隆,不留常驻安装:

```bash
uvx --from "harnessmith[wizard]" harnessmith wizard --open   # Web 向导(推荐)
uvx harnessmith new                                          # 或终端交互向导
```

随后启动刚生成的项目开始对话——在 Web 界面里直接配置模型与 key 并对话(推荐),或使用终端:

```bash
cd my-agent                    # 你填写的项目名
uv run my-agent serve --open   # 推荐:在浏览器里配置模型与 key 并对话
uv run my-agent chat           # 可选:在终端对话
```

见[使用指南](#使用指南)了解全部方式,包括用手写 spec 非交互生成。

## 为什么选 HarnessSmith?

多数"agent 脚手架"给你的是一个绑死在某框架上、无法移除的应用。HarnessSmith 生成的是一个**属于你**的仓库——可读、可改、且不含任何 agent 编排框架。

| | HarnessSmith | LangGraph 脚手架 | ADK / 静态模板 |
|---|---|---|---|
| agent 框架锁定 | **无**——属于你的纯 Python 循环 | LangGraph 运行时 | ADK / 多框架 |
| 每一行都可改可删 | **可以**——自包含仓库 | 受限——应用建在框架之上 | 受限 |
| 配置即生成(只生成选中的能力) | **是** | 否——固定模板 | 否 |
| 核心循环体量 | **约 150–300 行** | 被框架抽象 | 被框架抽象 |
| 生成后对生成器的运行期依赖 | **无** | 框架运行时 | 框架运行时 |
| 自带测试 + 锁文件 + Dockerfile + 冒烟自检 | **是** | 视情况 | 视情况 |
| 双 LLM 协议、运行期可切(OpenAI + Anthropic) | **是** | 视情况 | 视情况 |

## 概述

HarnessSmith 是 agent harness 的生成器,定位类似 `create-next-app`。通过 Web 向导、终端交互向导、preset 或手写 YAML 采集一份规格(`HarnessSpec`),HarnessSmith 据此渲染出一个**完整、独立的 Python 代码仓库**——可读、可改、可测试、可独立运行。生成的项目与 HarnessSmith 没有任何运行期关系:生成即脱离。

### 设计定位

- **无 agent 框架锁定。** 生成代码对任何 agent 编排框架零依赖,循环是属于你的普通 Python 代码。通用库(OpenAI SDK、Pydantic、Typer、FastAPI)只作为库使用,不接管控制流。
- **代码归你所有。** 产出是带有自有测试、锁文件、Dockerfile 与文档的自包含仓库,每一行都可以阅读、修改或删除。
- **配置即生成。** 能力在生成期选择,生成器只渲染被选中的部分;关闭的功能不留任何痕迹——没有模块、没有依赖、没有死代码。
- **默认极薄。** 默认产物是最小但完整可跑的 harness,核心循环维持在数百行以内;较重的能力(MCP、Web 界面、技能、记忆)均为 spec 开关式可选项。

## 亮点

<details>
<summary><b>完整能力清单</b> —— 点击展开</summary>

<br>

- **原生 function calling** —— 循环通过 API 的 `tool_calls`(TAO/ReAct 语义)驱动模型,而非文本解析。
- **双 LLM 协议,运行期可切** —— 每个产物同时内置 OpenAI Chat Completions 客户端(经 `base_url` 对接 vLLM、Together、Groq、LiteLLM 等任意兼容端点)与原生 Anthropic Messages 客户端;每个 LLM profile 在运行期配置中选择 `provider`,无需重新生成。
- **推理过程一等公民** —— thinking/reasoning 增量实时呈现(CLI 状态行、Web 可折叠推理面板),并在工具调用多轮间保留 `reasoning_content`,兼容有此要求的模型。
- **多范式运行时** —— `agent`(默认工具调用循环)、`plan` 与 `ask`(均只读),每轮可切(`--mode` / Web 下拉)。范式存放于薄注册表,用户以 `@register_paradigm` 自行扩展,不触碰内置实现。
- **会话持久化与续聊** —— 每次对话本地落盘;以 `--continue` / `--resume <id>`、多轮 `chat` REPL 或 Web 会话侧栏(自动起标题、重命名、删除)续聊。Web 界面支持多会话并行——每个会话独立流式输出,切换侧栏不会打断后台运行。中断的运行具备崩溃安全:状态在消息边界写入检查点,恢复时自动修复。
- **停止 / 继续 / 重问** —— 回合中途可取消(协作式取消,流式输出一并终止),之后携带完整上下文继续;Web 界面支持就地编辑任一历史提问并从该点重新生成。
- **人在环交互** —— 内置 `ask_question` 工具让模型向用户提出结构化澄清问题;工具调用确认(`允许一次 / 拒绝 / 本会话允许 / 永久允许`)拦截高风险工具,非交互场景默认拒绝。
- **按 LLM 持久成本核算** —— 用量账本按 LLM profile 跨运行累计 token;成本由各 profile 单价派生,达到 `cost_limit` 即在下次调用前阻止该模型。经 Web Budget 页或 `usage` CLI 管理。
- **上下文管理** —— 可组合触发条件(`window_pct`、`max_tokens`、`max_turns`,以真实 token 用量驱动)决定何时压缩;策略(`truncate`、`summarize`、`none`)决定如何压缩;两者均为用户可扩展的注册表。超大工具结果在入历史前截断,溢出时按需强制压缩;`max_steps` 阀值约束失控的工具循环,压缩还能在单个长回合内折叠(子回合 `keep_last_steps`),使一个 agentic 回合也能留在窗口内。
- **可组合 hooks 与薄 tool-policy 层** —— 通过 `config.hooks` 挂载一个或多个 `Hooks` 子类(子类化并挂载,无 `@register_hook`);五个生命周期点(`before_step` / `after_step` / `before_tool` / `after_tool` / `on_error`)。`before_tool` 可拒绝一次调用、`after_tool` 可改写/脱敏结果——一层代码级 policy 门禁,不引入 middleware 机制——多个 hook 按顺序组合。Web 界面有专门的 **Hooks** tab 并带隐私安全的执行日志;`info`(CLI)与 `GET /registries`(Web)呈现所有扩展点——工具、范式、上下文策略/触发条件、记忆后端、已导入的 extensions 与已挂载的 hooks。
- **按会话工作目录** —— 可选的工作目录提示(CLI `--cwd`、`chat` REPL 的 `/cwd`,或 Web 聊天工具栏的目录浏览器)注入系统提示,作为指引而非沙箱。当前日期/时间也会每轮注入。
- **不臃肿的工具生态** —— 装饰器注册的工具注册表带按工具风险分级,另有可选 MCP 客户端(stdio、HTTP、SSE 三种传输)与精选 catalog(免密钥多引擎网页搜索、fetch、git、时间、Desktop Commander、GitHub)。默认网页搜索 server 免密钥且多引擎(Bing/百度/DuckDuckGo/Brave/搜狗/…)带自动 failover,因此在某些引擎慢或不可达的网络下也能正常工作。Node 系 MCP server 会被 `npm install` 进固定的按 server 独立目录、再用 `node` 直接启动(不走临时 `npx` 缓存——它在 Windows 上不可靠)。MCP server 运行期管理:健康状态、增删改、热重连(Web 面板),CLI 侧 `mcp status`。
- **Agent Skills** —— 可选支持开放的 `SKILL.md` 标准与渐进披露;技能是纯文件,不引入框架。
- **跨会话记忆** —— 可选的自维护长期笔记,每轮注入系统提示,经工具写入,在会话边界由专用 LLM 角色整理,并可通过薄 `@register_memory` 注册表替换后端。
- **全局规则常驻注入** —— markdown 规则文件(`AGENTS.md` / `CLAUDE.md` / `.cursor/rules` 惯例)注入每轮系统提示。
- **完整可观测性** —— 每次运行产出 JSONL trace 与 token/成本计数;可选的仅本地 debug 日志记录生命周期事件(名称、计数、耗时),绝不记录消息内容、工具参数或密钥。
- **交付前验证可运行** —— 生成器锁定依赖并对每个新仓库执行冒烟验证(`uv sync`、import 检查、一次 mock function-calling、`pytest`),全绿才视为就绪。

</details>

## 生成内容

### 核心(始终生成)

| 能力 | 说明 |
|---|---|
| Agent 循环 | 原生 function-calling 循环,含范式分发、生命周期 hook 与优雅停止(含 `max_steps` 阀值) |
| LLM 层 | profile 注册表 + 角色路由(`generation`、`compaction`,以及可选 `title` / `memory` 角色),按 profile 的采样参数、超时/重试/fallback,双协议客户端(OpenAI 兼容 + 原生 Anthropic) |
| 工具注册表 | 装饰器注册 + 风险分级;高风险工具默认关闭,仅 allowlist 显式开启 |
| Hooks 与 policy | 经 `config.hooks` 挂载的可组合 `Hooks` 子类;observer + tool-policy 生命周期点(`before_tool` 拒绝 / `after_tool` 脱敏);经 `info` / `GET /registries` 提供扩展可发现性 |
| 会话 | 本地 JSON 持久化、`--continue` / `--resume`、`chat` REPL、崩溃安全检查点、按会话工作目录提示 |
| 交互层 | `ask_question` 结构化澄清 + HITL 工具确认,CLI/Web 共用同一套底座 |
| 上下文 | 触发条件/策略双注册表、工具结果截断、溢出自救、`max_steps` 约束、子回合折叠 |
| 预算 | 按 LLM 持久成本账本,按 profile 设单价与硬性成本上限 |
| 提示词 | 系统提示拼装 + 规则文件常驻注入、当前日期/时间、工作目录提示 |
| 可观测性 | JSONL trace + token/成本计数;可选仅本地 debug 日志 |
| CLI | `run`、`chat`、`info`、`test-llm`、`set-key`、`usage`(启用对应模块时另有 `serve`、`mcp`、`memory`) |
| 可运行性 | `uv.lock` + `.python-version`、Dockerfile + `.dockerignore` + devcontainer、`requirements.txt` pip 兜底、mock LLM 测试套件、一键启动脚本 |

### 可选模块(spec 开关;关闭 = 代码与依赖中均不存在)

| 模块 | 说明 |
|---|---|
| Web 界面 | FastAPI + SSE 聊天,token 级流式、可折叠推理与工具调用面板、支持多会话并行的会话侧栏、聊天工具栏(范式、生成模型、工作目录选择),以及分页双语(中/英)`/config` 面板——LLM、Context、Tools、MCP、Hooks、Paradigms、Prompts、Budget、Memory、Observability、System 各 tab(MCP 与 Memory 仅在对应模块启用时出现)。修改即时生效并回写 `config.yaml`(保留注释) |
| MCP 工具 | Model Context Protocol 客户端(stdio / HTTP / SSE),allowlist 与风险标记,精选 catalog 预填,运行期 server 管理(健康探测 + 热重连) |
| Agent Skills | `SKILL.md` 发现、元数据注入与按需加载 |
| 长期记忆 | 自维护 markdown 笔记,工具驱动写入、策略塑形、整理压缩,后端可插拔 |

## 架构

生成器与产物是严格分离的两层。spec 决定**结构**(哪些能力被编译进产物);产物的 `config.yaml` 是行为的**运行期权威**(模型、提示词、工具 allowlist、上下文参数、单价与限额)——全部可在不重新生成的前提下调整。架构图见英文部分 [Architecture](#architecture)。

## 技术栈

**生成器**

- Python ≥ 3.11,全链路使用 [uv](https://docs.astral.sh/uv/) 管理
- [Typer](https://typer.tiangolo.com/)(CLI)、[questionary](https://github.com/tmbo/questionary)(终端交互向导)
- [Jinja2](https://jinja.palletsprojects.com/)(模板渲染)
- [Pydantic v2](https://docs.pydantic.dev/) + PyYAML(`HarnessSpec` 校验与序列化)
- FastAPI + uvicorn(Web 向导,可选 `[wizard]` extra——绝不进入产物)

**生成产物**

- 运行期:`openai`(Chat Completions,经 `base_url` 对接任意兼容端点)、`anthropic`(原生 Messages)、`pydantic` + `pydantic-settings`、`pyyaml`、`typer`
- Web 界面(启用时):`fastapi`、`uvicorn`、`ruamel.yaml`(保留注释的配置回写);前端为单一静态页面(Tailwind CSS CDN,无构建步骤)
- MCP(启用时):官方 `mcp` SDK
- 测试:`pytest` + 离线 mock LLM(dev 依赖组,非运行期依赖)
- 环境契约:uv(`uv.lock` + `.python-version`),Docker 与 `requirements.txt` 兜底

生成的 `pyproject.toml` 不含任何 agent 编排框架,且测试套件对此作出断言。

## 使用指南

### 前置条件

- [uv](https://docs.astral.sh/uv/getting-started/installation/)(uv 会自动下载匹配的 Python,无需预装系统 Python)
- Docker(可选,用于容器化运行)

### 安装

HarnessSmith 已发布到 [PyPI](https://pypi.org/project/harnessmith/)。配合 [uv](https://docs.astral.sh/uv/) 可免安装直接运行:

```bash
uvx --from "harnessmith[wizard]" harnessmith wizard --open      # 启动 Web 向导(推荐)
uvx harnessmith new                                             # 或终端交互向导
```

想要常驻安装,以下任选其一:

```bash
uv tool install harnessmith        # 用 uv 安装 CLI
pip install harnessmith            # 或用 pip
# 从源码(开发用):
git clone https://github.com/EpisodeYu/HarnessSmith.git && cd HarnessSmith && uv sync
```

### 生成 harness

**最简单的方式**是仓库根目录的一键启动器——双击或运行 `HarnessSmith.sh`(macOS / Linux)或 `HarnessSmith.bat`(Windows)。它会让你在 **Web 向导(推荐)** 与终端向导之间选择,并在首次使用时代为安装 uv。

偏好命令行?每条都是单命令:

```bash
uv run harnessmith wizard                                   # Web 向导(推荐;uv sync --extra wizard)
uv run harnessmith new                                      # 终端交互向导
uv run harnessmith new my-agent --preset coding-assistant   # 非交互,使用内置 preset
uv run harnessmith new my-agent --spec ./harness.spec.yaml  # 非交互,使用手写 spec
uv run harnessmith doctor                                   # 本机工具链预检
```

- **Web 向导**(`wizard`)与 **终端向导**(`new` 不带 `--spec` / `--preset`)采集同一组结构选项——显示名、范式、Web 界面、MCP、技能、记忆——并应用一致的默认值;Web 向导适合桌面环境,终端向导适合无图形界面的服务器。
- 渲染完成后,生成器锁定依赖并执行冒烟验证(`uv sync`、import 检查、一次 mock function-calling、`pytest`);离线等场景可用 `--no-verify` 跳过。
- 任何向导都不采集密钥;密钥不会进入 spec、生成的 `config.yaml` 或 git。
- `--preset` 是面向脚本 / CI 生成的捷径,并非推荐起点:内置的 `coding-assistant` preset 会开启 MCP 并**把每个工具都加入 allowlist(含 shell 与写文件),且不设确认门禁**(`confirm: none`)。请优先用向导,或在接入真实模型前先检查 `config.yaml`(收窄 allowlist、把 `confirm` 设为 `high`)。

### 运行生成的 harness

**最简单的方式**是生成仓库自带的一键启动器,以其显示名命名、空白折叠为 `-`(如 `My-Coding-Assistant.sh` / `.bat`,终端无需引号)。它会自动 `uv sync`,并在启用 Web 的产物里启动 Web 聊天并打开浏览器;否则打开终端聊天。

等价的命令行方式:

```bash
cd my-agent
uv sync                                  # uv 自动准备 Python 与隔离 venv
uv run my-agent set-key OPENAI_API_KEY   # 把 API key 写入 .env(不回显、不进 git)
uv run my-agent serve --open             # Web 聊天 + /config 面板(启用 Web 的产物;推荐)
uv run my-agent test-llm                 # 探测各配置模型
uv run my-agent chat                     # 终端多轮对话
uv run my-agent run "总结 ./notes"        # 单轮;可加 --mode plan|ask、--stream、--cwd

# 完全容器化的替代方案(默认生成):
docker build -t my-agent . && docker run --rm -it my-agent
```

模型与端点在 `config.yaml`(或 Web `/config` 的 LLM tab)配置:设置 `model`,将 `base_url_env` / `api_key_env` 指向对应环境变量,并为每个 profile 选择 `provider: openai` 或 `provider: anthropic`。`run`、`chat`、`serve` 均支持 `--mock`,可在没有任何 key 的情况下离线试用。

### 产物 CLI 参考

| 命令 | 用途 |
|---|---|
| `run [PROMPT]` | 执行一轮。选项:`--mode agent\|plan\|ask`、`--stream`、`--continue`、`--resume <id>`、`--role`、`--cwd`、`--mock` |
| `chat` | 多轮 REPL,会话自动持久化;`/cwd` 设置工作目录提示;`Ctrl-D` 或 `/exit` 退出 |
| `serve` | 启动 Web 界面(`--host`、`--port`、`--open`);启用 Web 的产物 |
| `info` | 内省所有扩展点——已注册的工具、范式、上下文策略/触发条件、记忆后端、已导入的 extensions 与已挂载的 hooks |
| `test-llm` | 对每个 LLM profile 做连通性与能力探测 |
| `set-key <ENV_NAME>` | 将密钥写入 `.env`,不回显、不触碰 git |
| `usage` | 查看或清空按 LLM 的持久成本账本 |
| `memory show\|clear\|path\|consolidate` | 管理长期记忆笔记;启用记忆的产物 |
| `mcp status` / `mcp warm` | 探测 MCP server 健康 / 预热启动器;启用 MCP 的产物 |

### 配置模型

| 层 | 文件 | 角色 |
|---|---|---|
| 生成期 spec | `harness.spec.yaml` | 配方:哪些能力被编译进产物,以及初始值;快照保留在生成的仓库中 |
| 运行期配置 | `config.yaml` | 行为的权威来源:LLM profile 与角色、提示词与规则文件、工具 allowlist、上下文策略、hooks、MCP server、单价与成本上限、可观测性。可手改,也可经 Web `/config` 面板修改(即时生效 + 保留注释回写) |
| 密钥 | `.env`(gitignored) | 真实凭证的唯一存放处;`config.yaml` 与 spec 仅引用环境变量*名称* |

结构性变更(增删接口或模块)需要重新生成;行为性变更永远不需要。

## 安全模型

- **密钥不入 git。** 真实值仅存于 gitignored 的 `.env`;其余文件只引用环境变量名。`set-key` 与 Web 面板的密钥写入均为只写、不回显;trace 与 debug 日志不记录密钥。
- **高风险工具默认关闭。** shell 与写文件类工具默认禁用,需显式 allowlist 开启;运行期 allowlist 只能在生成期编译进的集合内收窄,永远不能扩张。
- **人在环确认**(`tools.confirm: none|high|all|<工具名>`)以"允许一次 / 拒绝 / 本会话允许 / 永久允许"拦截高风险工具调用;非交互场景默认拒绝。确认机制是面向可信操作者的护栏,不是安全边界——硬隔离依靠 Docker,或在生成期就不编译该能力。
- **Web 界面面向本地可信使用。** `/config` 面板与 MCP 管理页可修改运行期行为并启动本地进程,请勿暴露给不可信网络。

## 许可

[MIT](./LICENSE) © 2026 EpisodeYu
