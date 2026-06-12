"""HarnessSmith wizard (Slice 7) — a generator-side single-page form for specs.

Opt-in via the ``harnessmith[wizard]`` extra (FastAPI + uvicorn). It collects a
full :class:`~harnessmith.spec.HarnessSpec` (grouped by function, language-first
UI) and produces a downloadable, validated spec — optionally generating the repo
in one click. It is a generation-time tool only: it never ships into a generated
product and the product never depends on it. Secrets are never collected or
echoed; profiles carry env-var NAMES only.
"""

from __future__ import annotations
