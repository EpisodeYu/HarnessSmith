# 15 · LLM 支持线:上下文工程正确性 + 调用鲁棒性

> 对标成熟 harness（Claude Code / Codex CLI）的 LLM 支持线，逐项登记上下文策略与调用鲁棒性的工程细节。
> 性质与 v1+ 设计文档一致；与 [`125-slice-12-anthropic-dual-spec.md`](./125-slice-12-anthropic-dual-spec.md) 互补不重叠。
> 共同特征：**全部是运行期 `config.yaml` 旋钮 / 模板内部实现，不改 spec schema、零新增依赖、不触红线**。
>
> **落地状态**：§1（P0）+ §2（P1）+ §2.5（reasoning 多轮回传）+ §2.6（issue #5 长会话护栏，含原 §4 D1 滚动摘要合并）+ LLM 配置丰富化已是**默认能力**；§3（P2）/ §4（D2/D3）仍为 v1+ backlog（见 [`00-overview.md`](./00-overview.md) §8）。

## 0. 一句话总览

机制（注册表 / 路由 / 计账）已领先，缺的是让它们在真实长会话里不出事的工程细节：**上下文策略的工程正确性**（机制形态领先，但有几条会真实触发的故障路径）与 **LLM 调用鲁棒性**（避免「裸调用」）。

## LLM 配置丰富化(默认能力)

- 常用采样参数升一等（`top_p` / `frequency_penalty` / `presence_penalty` / `seed` / `stop`，均「仅 set 时发」）+ 通用 `extra_body: dict` 透传兜底（覆盖 `top_k` / `enable_thinking` / `thinking_budget` 等非标准参数）。全部进 `LLMProfileConfig`（运行期），Web `/config` LLM 卡片 **Advanced（默认折叠）**，留空 = 用 provider 默认。

## 1. P0 · 上下文策略正确性（默认能力）

### A1 工具结果截断上限（单轮顶爆窗口的第一道闸）
- **问题**：以 user 轮切分压缩时，进行中的当前轮永远整体保留。agent 范式一轮可跑几十个 step、每步喂回工具结果——`fetch` 抓大页面 / Desktop Commander 读大文件，几个大观察值即可顶爆窗口。A1 的单结果截断是入历史前的第一道闸；当前轮的「整轮保留」no-op 已由 §2.6 L1 的 round 级折叠（`_split_for_compaction`）根治。
- **对标**：Claude Code 对单个 tool result 设上限（约 25k token），超出截断并提示模型。
- **实现**：`context.max_tool_result_chars`（默认 100k 字符 ≈ 25k token，0=关），在 `paradigms.run_tool` 尾部截断 + `[truncated N chars]` 标注让模型自纠。运行期旋钮。context offload（大输出落盘给引用）是同一问题的高级出口，维持 v1+。

### A2 压缩触发回喂真实 usage（修中文 2–4 倍低估）
- **问题**：`estimate_tokens` 按 4 字符/token 估——对中文是 2–4 倍低估（中文 ≈ 1–1.5 字符/token）→ 压缩触发太晚 → 撞 context overflow。
- **关键事实**：不需引 tokenizer。上一次 LLM 响应的 `usage.prompt_tokens` 就是供应商报告的精确值，loop/trace 已在手。
- **实现**：`ContextInfo.last_prompt_tokens`（上一步真实 usage）经 `fit`→`should_compact` 注入，内置 `max_tokens`/`window_pct` 优先用真实 usage，字符估算仅首调用兜底；保持条件注册表签名向后兼容。

## 2. P1 · 窗口防线补全 + 调用鲁棒性（默认能力）

### B1 `context_window` 字段 + 百分比触发
profile 加 `LLMProfileConfig.context_window`（可选，默认 None）+ 内置 `window_pct` 触发条件（默认 0.85）；未设窗口则该条件不触发（靠 A1 + B2 兜底，**不误伤大窗口模型如 1M**）。不做跨端自动探测（与「provider-agnostic + 生成后不依赖 HarnessSmith」定位冲突）。运行期旋钮。

### B2 context overflow 自救
API 报 `context_length_exceeded`（400）时，共享 `paradigms.generate()` 捕获 `is_context_overflow(exc)` → `fit(force=True)` 强制压一次 → 重试本步一次（再失败上抛，不循环）。约 10 行；A2/B1 之后应极少触发，作最后防线。

### B3 超时 / 重试 / fallback 旋钮
`LLMProfileConfig.timeout_seconds`/`max_retries` 透传 SDK 构造器；`fallback`（profile 名）在非溢出错误且**尚未吐 delta** 时切该 profile 重试本步一次（流已开始不重试）。未改 `LLMClient` Protocol 签名 → 未触 `§6.4`。流中断重试谨慎排后（half-stream 语义复杂）。

### B4 usage 细分与计费精度
`Usage` 加 `cached_prompt_tokens`/`reasoning_tokens`（OpenAI `prompt_tokens_details.cached_tokens`/`completion_tokens_details.reasoning_tokens`；Anthropic `cache_read_input_tokens`）+ `LLMProfileConfig.cached_input_cost_per_million`；`compute_cost` 缓存命中按缓存价计、**未设缓存价则按全价（不误降）**；trace 累计 cached 并在 `llm_response` 事件暴露。长会话 + 重复前缀正是 agent loop 常态，精度值得补。

## 2.5 P0 · reasoning_content 多轮回传（思考模式 + 工具调用，默认能力）

- **问题（会真实 400 的故障）**：产物把推理仅当作一次性「思考中」UX 提示——流式 `reasoning_content` 只喂 `on_thinking` 后丢弃、非流式不读，于是**带工具调用的 assistant 历史消息回传时缺 `reasoning_content`**。多家思考模型要求：思考模式下历史含工具调用时，后续回传的带 tool_calls 的 assistant **必须**完整带 `reasoning_content`，否则 **400**。Anthropic 原生同源：带 `tool_use` 的 assistant 必须以带 `signature` 的 thinking block 开头。单轮多步与跨轮 resume 都会踩中。
- **设计原则**：**只回显端点自己产出的 reasoning + 只挂在带 `tool_calls` 的 assistant 上**——对不吐 reasoning 的模型零痕迹（`LLMResponse.reasoning` 恒空，什么都不挂）；最终无工具的答复消息不挂（避开「无工具却带 reasoning」的兼容问题）。
- **实现**：`LLMResponse` 加 `reasoning`/`reasoning_signature`；两 client 的 `complete`/`stream` 捕获（OpenAI `reasoning_content`→`reasoning`；Anthropic thinking 文本 + `signature_delta`）；`assistant_message()` 在带工具调用时写中性键 `reasoning_content`（+ `reasoning_signature`）；`OpenAIClient` 发请求层按 `reasoning_history_field`（默认 `reasoning_content`，`""`=关，vLLM 可设 `reasoning`）重命名/开关并 strip 掉 Anthropic 专属 `reasoning_signature`；`to_anthropic_messages` 在带工具调用 assistant 前补带 signature 的 thinking block（无 signature 则跳过，避免裸 thinking block 反而 400）。压缩/持久化天然安全（整条 dict 保留/原样存），加回归测试 + 不变量注释钉死；`estimate_tokens` 计入 `reasoning_content`。
- **已知限制**：字段名分歧靠 `reasoning_history_field` 旋钮兜底；Anthropic `redacted_thinking`（罕见、加密打码）暂不保留。

## 2.6 P1 · 长会话护栏补全（issue #5 实测，默认能力）

真实长程多轮 + 强制多次压缩实测（`coding-assistant` 产物 + reasoning 模型）暴露四条故障/缺位，均薄修、运行期、零依赖、不改 spec schema：

- **L1 压缩解耦 user 轮粒度**：旧切分以 user 轮为界，单个长 agentic 轮（一条 user、几十个 tool step）内 `dropped` 恒空 → `truncate`/`summarize`/`force` 全是保证性 no-op，小窗口模型撞无法自救的 overflow 悬崖。改为 `_split_for_compaction`：在 user 轮地板（`keep_last_turns`）之外再加 **tool-round 地板**（`keep_last_steps`，默认 8；一轮 = 一条带 `tool_calls` 的 assistant + 其 tool 结果），两者取更激进的切点 → 单轮内也能按轮折叠，`force` 路径不再是保证性 no-op。整轮丢弃保配对合法、存活 tool-call assistant 的 `reasoning_content` 不破。force 与常规触发压缩都走此折叠。
- **L2 滚动摘要合并（原 §4 D1）**：`summarize` 把**既有摘要笔记 + 本次 `dropped`** 一起喂 summarizer，产出单条合并笔记（`_SUMMARY_NOTE_PREFIX` 识别旧笔记），摘要栈恒 O(1)，不再每轮前插一条只增不并。
- **L3 阈值低于 keep 地板的空转**：`max_tokens`/`window_pct` 阈值低于 `keep_last_turns` 的 token 地板时 `should_compact` 永真却永远 no-op、空转 churn。L1 的 round 地板把有效地板降低使阈值可达；`fit` 再加**饱和短路**：非 `force` 路径若一次压缩未严格缩小估算 token，原样返回且不记日志（机制修，不靠告警用户）。
- **L4 agent 循环步数硬上限**：三范式 `run()` 原是 `while True`，唯一非模型停止是默认关掉的 `cost_limit`（默认单价=0 → 默认零防护）。加运行期 `Config.max_steps`（默认 50，0=不限），每步开头到顶即以 `stop_reason="max_steps"` 干净停（续聊可继续），与取消/预算同处步边界。三范式（agent/plan/ask）同构各加同一守卫。

## 3. P2 · structured outputs 提前到默认路径（backlog）

`response_format: json_schema` 在 Chat Completions 上已是标配能力。作为 profile / 调用旋钮落 `OpenAIClient`。实现前需细化：与工具调用循环的交互（通常只在收尾步要 JSON 输出），旋钮作用面（全程 vs 收尾）要先定。若要动 `LLMClient` Protocol 仍按 `§6.4` 停下请人签。

## 4. P3 · 压缩品质（backlog,不紧急）

- **D1 滚动摘要合并** — ✅ **已实现，见 §2.6 L2**（旧摘要 + 本次 `dropped` 合并为单条笔记，摘要栈 O(1)）。
- **D2 microcompaction（工具结果老化）**：整体 summarize 前，先把久远 step 的工具输出替换为占位符（保留 tool_call 结构）。可作内置策略或 `summarize` 的前置阶段。（§2.6 L1 的 round 级折叠已能在单轮内丢弃久远轮；D2 是更细的「保结构换占位符」变体，仍 backlog。）
- **D3 缓存友好压缩约束**：每次压缩重写消息前缀必然击穿供应商 prompt cache；memory 注入每轮变化同理。做 D1/D2 时把「前缀尽量稳定、变化靠尾部追加」记为设计约束即可（与 Slice 12 Phase 3 `cache_control` 互补，本条 provider 无关）。

## 5. 明确不缺 / 不建议补（避免误判成洞）

- **已对齐或领先**：可扩展压缩注册表（竞品多为黑盒）、compaction 开销计入 trace/预算（`_AccountingSummarizer`）、memory 的 `compact_rescue` 钩子、compaction 角色路由、采样参数「仅 set 时发」的 reasoning 模型兼容。
- **多模态输入（图片）**：成熟 harness 有，但与「薄 + 文本 agent 生成器」定位关系不大 → 观望不补。
- **`parallel_tool_calls` / `tool_choice` 强制旋钮**：边际价值低 → 观望。

## 6. 红线复核（对照 §10 / `CLAUDE.md §6`）

- 全部条目：不引 agent 编排框架、不触云托管/沙箱/权限红线；零新增依赖；运行期旋钮不改 spec schema；密钥路径不涉（`extra_body` 仅存非密钥值）。
- B3 fallback / extra_body：不改 Chat Completions 选型、默认不启用、不动默认行为，未改 `LLMClient` Protocol 签名 → 不触 `§6.4`。P2 structured outputs 落地时若要动 Protocol 仍按 `§6.4` 停下请人签。

> 一句话：机制（注册表/路由/计账）已领先，缺的是让它们在真实长会话里不出事的工程细节——单轮截断、真实 usage、窗口感知、溢出自救、超时重试、缓存计价、reasoning 多轮回传。全部薄、全部运行期、零依赖。
