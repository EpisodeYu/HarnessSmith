# Security Policy

## Reporting a vulnerability

Please report security issues **privately** — do not open a public issue for a vulnerability.

Use GitHub's private vulnerability reporting:

1. Go to the [Security tab](https://github.com/EpisodeYu/HarnessSmith/security) of the repository.
2. Click **Report a vulnerability** and describe the issue, including steps to reproduce and the affected version.

We aim to acknowledge a report within a few days and will keep you updated on the fix and disclosure timeline.

## Supported versions

HarnessSmith is pre-1.0 and ships from `main`. Security fixes target the latest released version on [PyPI](https://pypi.org/project/harnessmith/) and the current `main`.

## Scope and security model

HarnessSmith generates a self-contained agent harness that you run yourself. A few design facts are important when assessing risk:

- **Secrets stay out of git.** Real credentials live only in a gitignored `.env`; the spec and `config.yaml` reference environment-variable names only. Key writers (`set-key`, the web key field) are write-only and never echo values; traces and the debug log record no secrets.
- **High-risk tools are off by default.** Shell and file-writing tools ship disabled and require explicit allowlisting. The runtime allowlist can only narrow the capabilities compiled in at generation time, never extend them.
- **Human-in-the-loop confirmation** gates risky tool calls; non-interactive contexts fail closed. Confirmation is a guardrail for trusted operators, not a hard security boundary — real isolation belongs to Docker or to excluding the capability at generation time.
- **The web interface targets local, trusted use.** The `/config` panel and MCP management page can change runtime behavior and launch local processes; do not expose them to untrusted networks.

If you find a way that secrets leak into git/traces/logs, that a disabled-by-default capability can be enabled at runtime, or that the management surfaces can be abused beyond their documented local-trust model, that is in scope — please report it.
