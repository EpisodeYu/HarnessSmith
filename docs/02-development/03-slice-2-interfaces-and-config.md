# 02·03 - Slice 2:接口与配置

> 目标:在黄金路径之上加"第二种调用接口 + 多模型路由 + 上下文管理",让产物更像真正可用的 harness。均为 `01-project-plan.md` 的 **L2**,通过 **spec 开关**生成,不进默认薄产物的强制项。
>
> 前置:Slice 1 门禁全绿。

## 1. 交付物

- 产物 `interfaces/web.py` — FastAPI + **SSE 极简聊天页**(`/chat`),不含 `/config` 面板(那是 L3)。
- `llm.py` 升级 — 命名 **profile 注册表** + `roles` 路由表 + `client_for(role)`(`generation` / `compaction` / `embedding`)。loop 改为按角色取 client。
- 产物 `harness/context.py` — `max_context_tokens` + **`truncate`**(默认)+ 可选 `summarize`(用 `compaction` profile)。保留头尾 token。
- `presets/rag-research` 骨架(RAG 实现可桩,留 Slice 4)。
- 上述能力的 spec 字段开关 + 渲染分支(关掉时产物不含 fastapi 依赖)。

## 2. 任务拆解

### 2.1 Web chat(SSE)
- FastAPI app,`/chat` 走 SSE 流式;mock 后端可断言流式分片。
- `fastapi`/`uvicorn` 进 `optional-dependencies`,仅 `interfaces.web` 开启时安装。

### 2.2 多 profile 角色路由
- profile:`id / provider / base_url / model / temperature / max_tokens / reasoning_effort / api_key_env`(只存 env 引用名)。
- `client_for(role)` 解析角色 → profile → client;loop / context 处处按角色取,不硬编码模型。

### 2.3 context 管理
- 默认 `truncate`(滑窗 + 保留头尾);`summarize` 为可选,用 `compaction` 角色压缩。
- offload 不在本片(L3)。

## 3. 退出门禁(对应 `01 §8` Non-blocker,做到即验)

- [ ] Web `/chat` SSE 能流式返回(mock 后端)的测试。
- [ ] `client_for(generation/compaction/embedding)` 解析到正确 profile;切换角色绑定后生效(mock client 断言)。
- [ ] context 策略单测:`truncate`(及启用时的 `summarize`)各有覆盖。
- [ ] 第 2 个 preset(rag-research 骨架)能生成并通过其 `pytest`。
- [ ] 关掉 Web 开关时,生成的 `pyproject.toml` **不含** fastapi/uvicorn(薄验证)。
- [ ] `ReadLints` clean。

## 4. 必须人审的决策点

- Web / UX 一眼是否可用(流式手感、最简聊天页够不够)。

## 5. 本 slice 注意

- **薄**:Web / 多 profile / context 都通过 spec 开关生成;**默认 spec 仍是 Slice 1 的薄产物**(`CLAUDE.md §2`)。
- 默认依赖不因本片变重:重依赖一律进 extra,渲染按开关裁剪(`CLAUDE.md §6.2`)。
- 角色集合可扩展,但改 `HarnessSpec` 的 `roles` 结构属人审(`CLAUDE.md §6.1`)。
