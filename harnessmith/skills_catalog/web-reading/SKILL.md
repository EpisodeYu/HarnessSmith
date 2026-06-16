---
name: web-reading
description: Read complex or JavaScript-rendered web pages cleanly. When a plain URL fetch returns an empty shell, garbled HTML, or "enable JavaScript", re-fetch the page through Jina Reader (https://r.jina.ai/) to get rendered, LLM-ready Markdown. Keyless, no setup. Use whenever a fetched page looks broken or you need the real article/body text.
---

# Web reading: get clean text from complex pages

Plain HTTP fetch tools (e.g. the `fetch` MCP tool) download the *raw* HTML and
strip tags. That fails on modern sites whose content is rendered by JavaScript
(SPAs, infinite-scroll, app-shell pages): the raw HTML is an empty shell, so
you get little or no real text.

**Jina Reader** (`https://r.jina.ai/`) renders the page in a real browser and
returns clean Markdown of the main content. It is **keyless** (anonymous, rate
limited) — no API key or config needed — so it works in any generated harness
that has a URL-fetching tool.

## When to use this

Use Jina Reader whenever a normal fetch of a page returns any of:

- empty or near-empty body, or only nav/menu/footer boilerplate
- "Please enable JavaScript", a loading spinner, or an obvious app shell
- garbled / truncated content that doesn't match what the page clearly contains
- a long, content-heavy article you want as clean Markdown

## How to use it

Prepend `https://r.jina.ai/` to the original URL and fetch THAT with your
existing fetch / HTTP-GET tool:

```
https://r.jina.ai/https://example.com/some/article
```

For example, to read `https://news.site/article/123`, fetch
`https://r.jina.ai/https://news.site/article/123`. The result is rendered
Markdown of the page's main content.

Notes:

- Keep the original URL's scheme (`https://...`) after the prefix.
- It is rate limited when keyless; if you hit a limit or a page is anti-bot
  protected, say so and fall back to the plain fetch result rather than looping.
- If this harness has the `jina-reader` MCP server enabled (with a `JINA_API_KEY`),
  prefer its `read_url` tool instead — same engine, higher quota, more reliable.
