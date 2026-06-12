# 02·03 - Slice 2:LLM 路由 + 上下文

> 目标:在黄金路径之上把「LLM 调用管线」做厚一点点——**多 profile 角色路由** + **上下文管理**,为后续 summarize / RAG / multi-agent 铺地基。两者都在调用管线上,且 summarize 依赖 compaction 角色,放同一片最顺。**默认产物仍是 Slice 1 的薄核心**。
>
> 前置:Slice 1 门禁全绿。
>
> 路由复用 Slice 0 既有 `llms`/`roles` 字段;context 走**运行期专属**配置(`config.py` + `config.yaml`,不进 `HarnessSpec`),与定价同构 → 未触发 `CLAUDE.md §6.1`。

## 1. 交付物

- `config.py` 升级 — **profile 注册表** + `client_for(role)`(`generation` / `compaction` / `embedding`),带 client 缓存;复用现有 `llms` + `roles`。
- `llm.py` — `make_client(config, role)` 真正按角色解析 profile;`loop.py` 仍以 `generation` 为默认。
- 产物 `harness/context.py` — `ContextConfig`(运行期):`strategy`(`truncate` / `summarize`)+ 阈值 + `keep_last_turns`;`truncate`=滑窗(保留 system + 最近 N 轮),`summarize`=用 `compaction` 角色把旧 history 压成摘要。
- `config.yaml` 增 `context:` 段(模板默认值,运行期可改);`HarnessSpec.context` 保持 Slice 0 的 reserved passthrough。
- 生成产物自带测试:`client_for(role)` 路由(mock)、context `truncate`/`summarize` 单测。

> 注:context 后续(Slice 7)增强为「触发条件 + 策略」两层薄注册表 + usage 驱动触发,默认策略改为 `summarize`,详见 [`08-slice-7-wizard.md`](./08-slice-7-wizard.md) 与 [`00-overview.md`](./00-overview.md) §6 决策表「context 默认」行。

## 2. 任务拆解

### 2.1 多 profile 角色路由(无 spec 变更)
- `config.py.Config.client_for(role)`:角色 → profile → 缓存的 client;`llm.make_client(config, role, mock=)` 复用。
- `loop.py` 默认 `generation`;compaction/embedding 由 context/(将来)RAG 调用。
- profile 的 temperature/max_tokens 等可选参数:行为性,落运行期 `config.py` 的 profile 模型(默认值),不进 spec。

### 2.2 context 管理(运行期专属,无 spec 变更)
- `ContextConfig` 落 `config.py`(`extra="forbid"`,全可选带默认)。`config.yaml` 渲染带默认值/注释的 `context:` 段。
- `context.py.fit(...)`:`truncate` 保留 system + 最近 N 轮(轻量启发式,无重依赖);`summarize` 超限时用 `compaction` client 压缩旧 history 并注入摘要。
- `loop.py` 在每次调用 LLM 前对 messages 应用 context 策略。
- offload(大输出落盘)不在本片(v1+)。

## 3. 退出门禁

- `client_for(...)` 解析到正确 profile + client 缓存。
- context 单测:`truncate`(超限裁剪、保留 system、干净 turn 边界、最近消息保留)+ `summarize`(mock compaction 摘要注入、旧 history 压缩)。
- 默认产物 = no-op,行为同 Slice 1;无新增运行期依赖。
- 黄金路径回归:preset 生成 → `uv sync && pytest` → mock 跑通一次工具调用(golden/docker/uvx 全绿)。
- `ReadLints` clean。

## 4. 关键决策

- 无硬门槛(`context` 保持运行期专属,不改 `HarnessSpec` → 不触发 §6.1)。
- 角色集合 `generation/compaction/embedding`(可扩展);默认 context 策略与阈值取合理默认。

## 5. 本 slice 注意

- **薄**:`truncate` 是轻量启发式,无新依赖;`summarize` 是可选策略,不引入新运行期依赖。默认仍是 Slice 1 薄产物(`CLAUDE.md §2`)。
- **配方 vs 活旋钮**(`00-overview.md` §3):profile 参数 / context 参数都是行为性配置,落运行期 `config.yaml`;`spec` 不变。
- Web chat 不在本片(挪到 Slice 3 产物 Web);本片纯产物核心 + 运行期配置,无新接口。
