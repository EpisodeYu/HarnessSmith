# 02·03 - Slice 2:LLM 路由 + 上下文

> 目标:在黄金路径之上,把"LLM 调用管线"做厚一点点——**多 profile 角色路由** + **上下文管理**,为后续 summarize / RAG / multi-agent 铺地基。两者都在调用管线上,且 summarize 依赖 compaction 角色,放同一片最顺。均为 `01-project-plan.md` 的 **L2**,通过 spec 开关/字段生成,**默认产物仍是 Slice 1 的薄核心**。
>
> 前置:Slice 1 门禁全绿(已 ✅)。
>
> **状态:📝 规划中(骨架)。** 开工前需先敲定 §4 的 §6.1 决策(context 字段语义)。

## 1. 交付物

- `llm.py` 升级 — 命名 **profile 注册表** + `roles` 路由表 + `client_for(role)`(`generation` / `compaction` / `embedding`);`loop.py` 改为按角色取 client(`generation` 为默认,接口已在 Slice 1 预留)。
- 产物 `harness/context.py` — `max_context_tokens` + **`truncate`**(默认,滑窗 + 保留 system/最近若干轮)+ **可选 `summarize`**(用 `compaction` 角色把旧历史压成摘要)。
- spec/config:`context` 字段落地语义(见 §4 决策);`roles` 复用 Slice 0 已有字段(无 schema 变更)。
- 生成产物自带测试:`client_for(role)` 路由(mock)、context `truncate`/`summarize` 单测。

## 2. 任务拆解

### 2.1 多 profile 角色路由(无 spec schema 变更)
- 复用现有 `llms`(profile 列表)+ `roles`(dict)。`config.py` 增 `client_for(role)`:角色 → profile → client;`llm.py.make_client(config, role)` 已是雏形,扩成真正按角色路由 + 缓存 client。
- `loop.py` 仍以 `role="generation"` 为默认;compaction/embedding 由 context/RAG 调用。
- LLM profile 可选参数(temperature / max_tokens 等)是否进 profile:**行为性配置,落运行期 config**;若要进 spec 属 §6.1(到时再议)。

### 2.2 context 管理
- 默认 `truncate`:按 `max_context_tokens` 估算,保留 system + 最近 N 轮;token 估算用轻量启发式(不引重依赖)。
- 可选 `summarize`:超限时用 `compaction` 角色 client 把旧历史压成一段摘要后再续。**默认关**,开了才走 compaction。
- offload(大输出落盘)不在本片(v1+)。

## 3. 退出门禁(对应 `01 §8` Non-blocker,做到即验)

- [ ] `client_for(generation/compaction/embedding)` 解析到正确 profile;切换角色绑定后生效(mock client 断言)。
- [ ] context 策略单测:`truncate` 必覆盖;启用时 `summarize` 覆盖(用 mock compaction client 断言摘要被注入、历史被压)。
- [ ] 默认产物(不开 summarize)仍薄:不新增重运行期依赖。
- [ ] 黄金路径回归:preset 生成 → `uv sync && pytest` 全绿 → mock 跑通一次工具调用(沿用 Slice 1 门禁)。
- [ ] `ReadLints` clean。

## 4. 必须人审的决策点

- [ ] **`context` 字段语义(`CLAUDE.md §6.1`,开工前必须签)**:Slice 0 把 `context: dict | None` 留作 passthrough。本片要给它结构(如 `strategy: truncate|summarize`、`max_context_tokens`、`keep_last_turns`)。**给保留字段定语义 = schema 变更**,需先确认字段形状。倾向:`context: {strategy, max_context_tokens, keep_last_turns}`,全可选带默认,默认 `truncate`。
- [ ] 角色集合是否就用 `generation/compaction/embedding`(可扩展)。

## 5. 本 slice 注意

- **薄**:context/summarize 通过开关生成;默认仍是 Slice 1 薄产物(`CLAUDE.md §2`)。
- **配方 vs 活旋钮**:profile 选择/温度、context 参数都是**行为性**配置,尽量落运行期 `config.yaml`(决策④,`01 §4`)。
- 改 `HarnessSpec` 字段/语义(`context`、`roles` 结构)属 `CLAUDE.md §6.1`,开工前确认(见 §4)。
- Web chat **不在本片**(挪到 Slice 3 产物 Web);本片纯产物核心 + 运行期配置,无新接口。
