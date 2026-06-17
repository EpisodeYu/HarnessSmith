# Contributing to HarnessSmith

Thanks for your interest in improving HarnessSmith. This guide covers everything you need to make a good first contribution.

HarnessSmith is a **code generator**: it reads a `HarnessSpec` and renders a standalone, framework-free Python agent harness. Before changing anything, read the one rule that shapes the whole project below.

## The one mental model: generator vs generated product

There are two layers, and every change touches exactly one of them:

| Layer | Where | What it is |
|---|---|---|
| **Generator** | `harnessmith/*.py` (`spec`, `generator`, `cli`, `scaffold`, `wizard`, ...) | The spec schema, render engine, CLI, wizards, catalog, presets. The package published to PyPI. |
| **Product templates** | `harnessmith/templates/**/*.j2` | Rendered output is the code a *user* receives. Editing a template changes every future generated project. |

A consequence: **tests must cover the generated product, not only the generator.** The golden path is: generate -> `uv sync` -> `pytest` -> a mock-LLM function-calling turn.

## Project red lines (please respect these)

These are core to the product's identity. PRs that cross them will be asked to change:

- **No agent-orchestration framework in generated output.** Never add LangChain, LangGraph, ADK, or similar to a product template or its dependencies. The generated `pyproject.toml` is asserted to be free of them.
- **Thin by default.** The default product's core loop stays in the low hundreds of lines. Heavier capabilities (MCP, web UI, skills, memory) are opt-in spec toggles — when off, they leave no module, dependency, or dead code.
- **Secrets never enter git.** Real values live only in a gitignored `.env`; `config.yaml` and the spec reference environment-variable *names* only. Never write secrets into traces, logs, or any tracked file.

## Development setup

Prerequisites: [uv](https://docs.astral.sh/uv/) (it provisions the right Python for you). Docker is optional, for the container smoke test.

```bash
git clone https://github.com/EpisodeYu/HarnessSmith.git
cd HarnessSmith
uv sync                  # install generator dependencies
uv sync --extra wizard   # optional: web wizard (FastAPI/uvicorn)
```

Generate a product to try your changes end to end:

```bash
uv run harnessmith new my-agent --preset coding-assistant   # non-interactive, from a preset
uv run harnessmith new my-agent --spec ./harness.spec.yaml  # from a hand-written spec
uv run harnessmith new my-agent --no-verify                 # skip the post-generation smoke check (offline)
uv run harnessmith wizard                                    # web wizard
uv run harnessmith doctor                                    # preflight check of the local toolchain
```

## Running tests

```bash
uv run pytest -q          # fast suite (generator units + product rendering); golden tests excluded by default
uv run pytest -m golden   # golden snapshots: real generation + uv sync + the product's own pytest (slow)
uv run pytest -m docker   # container smoke test (needs a running Docker daemon)
```

Day-to-day development uses a **mock LLM** — no API key required.

## What "done" looks like

Before opening a PR, make sure:

- New or changed generator/template code has an automated test (unit or integration).
- The golden path is green: a preset/example spec generates, `uv sync && pytest` passes, and a mock function-calling turn (including one tool call) succeeds.
- The generated `pyproject.toml` contains no `langchain` / `langgraph` / `adk`.
- The post-generation smoke check passes; your editor reports no new lint errors/warnings.
- If you changed `HarnessSpec`, a core template, or touched 3+ files, also run the golden snapshots and the Docker smoke test.

## Commit and PR conventions

- Use [Conventional Commits](https://www.conventionalcommits.org/): `feat:`, `fix:`, `refactor:`, `docs:`, `chore:`, `test:`, `perf:`, `build:`, `ci:`.
- One commit per logical change; don't bundle unrelated edits.
- Open a PR against `main` with a short description of the *why*, the layer you touched (generator vs template), and how you verified it.

## Questions and proposals

Open an [issue](https://github.com/EpisodeYu/HarnessSmith/issues) for bugs and feature ideas. For larger changes (especially anything touching `HarnessSpec`, the LLM API surface, or the thin/no-framework boundaries), open an issue to discuss the design before investing in a PR.
