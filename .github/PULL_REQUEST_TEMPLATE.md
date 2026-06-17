## Summary

<!-- What does this change and why? Focus on the "why". -->

## Layer

<!-- Which layer does this touch? -->

- [ ] Generator (`harnessmith/*.py`)
- [ ] Product template (`harnessmith/templates/**`)
- [ ] HarnessSpec / schema
- [ ] Docs / chore only

## How was this verified?

- [ ] `uv run pytest -q` passes
- [ ] Golden path green: a preset/example spec generates, `uv sync && pytest` passes, and a mock function-calling turn (with one tool call) succeeds
- [ ] Generated `pyproject.toml` contains no `langchain` / `langgraph` / `adk`
- [ ] (Large change: `HarnessSpec`, a core template, or 3+ files) golden snapshots + Docker smoke test run
- [ ] No new lint errors/warnings

## Notes for reviewers

<!-- Anything reviewers should know: trade-offs, follow-ups, screenshots. -->
