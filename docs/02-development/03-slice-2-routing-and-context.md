# 02·03 - Slice 2:LLM 路由 + 上下文

> 目标:在黄金路径之上,把"LLM 调用管线"做厚一点点——**多 profile 角色路由** + **上下文管理**,为后续 summarize / RAG / multi-agent 铺地基。两者都在调用管线上,且 summarize 依赖 compaction 角色,放同一片最顺。均为 `01-project-plan.md` 的 **L2**,**默认产物仍是 Slice 1 的薄核心**。
>
> 前置:Slice 1 门禁全绿(已 ✅)。
>
> **状态:✅ 已完成(退出门禁 §3 全绿)。** `uv run pytest` 38 fast green + `uv run pytest -m golden` 3 green;生成产物自带测试 8 → **14**(+6:路由/缓存 + truncate/summarize)。关键设计:路由复用 Slice 0 既有 `llms`/`roles` 字段;context 走**运行期专属**配置(`config.py` + `config.yaml`,不进 `HarnessSpec`),与定价/`max_tokens` 同构 → **未触发 `CLAUDE.md §6.1`**,无人审硬门槛。

## 1. 交付物

- `config.py` 升级 — **profile 注册表** + `client_for(role)`(`generation` / `compaction` / `embedding`),带 client 缓存;复用现有 `llms` + `roles`。
- `llm.py` — `make_client(config, role)` 真正按角色解析 profile;`loop.py` 仍以 `generation` 为默认(角色接口 Slice 1 已预留)。
- 产物 `harness/context.py` — `ContextConfig`(运行期):`strategy`(`truncate` 默认 / `summarize`)+ `max_context_tokens` + `keep_last_turns`;`truncate`=滑窗(保留 system + 最近 N 轮),`summarize`=用 `compaction` 角色把旧history压成摘要。
- `config.yaml` 增 `context:` 段(模板默认值,运行期可改);`HarnessSpec.context` **保持 Slice 0 的 reserved passthrough,不动**。
- 生成产物自带测试:`client_for(role)` 路由(mock)、context `truncate`/`summarize` 单测。

## 2. 任务拆解

### 2.1 多 profile 角色路由(无 spec 变更)
- `config.py.Config.client_for(role)`:角色 → profile → 缓存的 client;`llm.make_client(config, role, mock=)` 复用。
- `loop.py` 默认 `generation`;compaction/embedding 由 context/(将来)RAG 调用。
- profile 的 temperature/max_tokens 等可选参数:**行为性,落运行期 `config.py` 的 profile 模型**(默认值),不进 spec。

### 2.2 context 管理(运行期专属,无 spec 变更)
- `ContextConfig` 落 `config.py`(`extra="forbid"`,全可选带默认,默认 `truncate`)。`config.yaml` 渲染一个带默认值/注释的 `context:` 段。
- `context.py.fit(messages, ctx, client_for=None)`:`truncate` 保留 system + 最近 `keep_last_turns` 轮,按 `max_context_tokens` 估算(轻量启发式,无重依赖);`summarize` 超限时用 `compaction` client 压缩旧history并注入摘要,默认关。
- `loop.py` 在每次调用 LLM 前对 messages 应用 context 策略。
- offload(大输出落盘)不在本片(v1+)。

## 3. 退出门禁(对应 `01 §8` Non-blocker,做到即验)

- [x] `client_for(...)` 解析到正确 profile + client 缓存(`test_profile_for_routes_roles` / `test_client_router_caches_per_role` / `test_loop_runs_via_client_for`)。
- [x] context 单测:`truncate`(`test_context_truncate_*`,超限裁剪、保留 system、干净 turn 边界、最近消息保留)+ `summarize`(`test_context_summarize_injects_summary`,mock compaction 摘要注入、旧 history 压缩)。
- [x] 默认产物(`truncate` 且不设 `max_context_tokens`)= no-op,行为同 Slice 1;无新增运行期依赖。
- [x] 黄金路径回归:preset 生成 → `uv sync && pytest`(14 green)→ mock 跑通一次工具调用(golden/docker/uvx 全绿)。
- [x] `ReadLints` clean。

## 4. 必须人审的决策点

- 无硬门槛(`context` 保持运行期专属,不改 `HarnessSpec` → 不触发 §6.1)。
- 软确认(非阻塞):角色集合就用 `generation/compaction/embedding`(可扩展);默认 context 策略 `truncate` + 默认 `max_context_tokens`/`keep_last_turns` 取值是否合理。

## 5. 本 slice 注意

- **薄**:`truncate` 是轻量启发式,无新依赖;`summarize` 是可选策略(运行期开),不引入新运行期依赖。默认仍是 Slice 1 薄产物(`CLAUDE.md §2`)。
- **配方 vs 活旋钮**(决策④,`01 §4`):profile 参数 / context 参数都是行为性配置,落运行期 `config.yaml`;`spec` 不变,wizard 将来若要预填初值再议(同定价/`max_tokens`)。
- Web chat **不在本片**(挪到 Slice 3 产物 Web);本片纯产物核心 + 运行期配置,无新接口。
- 若实现中发现 `context` 必须进 spec 才合理 → 那才触发 `CLAUDE.md §6.1`,先停问人。
