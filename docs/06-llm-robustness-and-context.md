# 06 · LLM 支持线差距:上下文工程正确性 + 调用鲁棒性(Slice 13+ backlog 待办)

> 本文是 2026-06-10 一次"对标成熟 harness、聚焦 LLM 支持"探索的落地待办——逐项登记**此前 backlog 尚未出现**的 LLM 相关差距,供人排期(指针已登记 `02-development/00-overview.md §2` Slice 13+)。
> 性质同 [`03-feature-landscape-and-proposals.md`](./03-feature-landscape-and-proposals.md)(对标分析 + 建议,不是开发计划);与已立项待签的 [`05-llm-dual-spec-anthropic.md`](./05-llm-dual-spec-anthropic.md)(Slice 12)互补不重叠。
> 共同特征:**全部是运行期 `config.yaml` 旋钮 / 模板内部实现,不改 spec schema、零新增依赖、不触红线**——除排期外原则上无需人审签字(贴近 LLM API 面边缘的两条在 §6 单独标注)。

## 0. 一句话总览

交互层标配(会话 / HITL / MCP 管理)已补完,Anthropic 双规范已立项待签;剩下与成熟 harness(Claude Code / Codex CLI)差距最大、且 backlog 此前未登记的是两类:**上下文策略的工程正确性**(机制形态领先,但有四条会真实触发的故障路径)与 **LLM 调用鲁棒性**(当前是"裸调用")。

## 1. P0 · 上下文策略正确性(会真实发生的故障,建议先修)

### A1 工具结果截断上限(单轮顶爆窗口的第一道闸)

- **问题**:`context.py` 的 `_split_keep_last_turns` 以 user 轮切分,`keep_last_turns ≥ 1` ⇒ **进行中的当前轮永远整体保留**。agent 范式一轮可跑几十个 step、每步喂回工具结果——`fetch` 抓大页面 / Desktop Commander 读大文件,几个大观察值即可顶爆窗口,此时 `truncate`/`summarize` 都无事可做(dropped 为空)。`run_tool`(`paradigms/__init__.py`)现在原样返回任意大小的结果。
- **对标**:Claude Code 对单个 tool result 设上限(约 25k token),超出截断并提示模型(可分页 / 换更窄的查询)。
- **薄做法**:`config.yaml` 加 `tools.max_result_chars`(默认约 100k 字符 ≈ 25k token)+ `run_tool` 末尾一处截断(尾部标注 `[truncated N chars]` 让模型自纠)。运行期旋钮,不改 spec。
- **与已登记项的关系**:v1+ 的 **context offload**(大输出落盘给引用)是同一问题的高级出口;截断是兜底闸(极薄,先做),offload 维持 v1+。

### A2 压缩触发回喂真实 usage(修中文 2–4 倍低估)

- **问题**:`estimate_tokens` 按 4 字符/token 估——对**中文是 2–4 倍低估**(中文 ≈ 1–1.5 字符/token)→ 压缩触发太晚 → 直接撞 context overflow。生成中文 agent 恰是本项目典型场景。
- **关键事实**:不需要引 tokenizer。上一次 LLM 响应的 `usage.prompt_tokens` 就是供应商报告的精确值,loop/trace 已经在手,只是没有回喂给触发条件。成熟 harness 的 auto-compact 都按真实 usage 驱动(占用 vs 窗口百分比)。
- **薄做法**:`max_tokens` 条件改为"上次真实 prompt_tokens + 本步新增消息的字符估算";字符估算仅兜底首次调用。实现上把"上次 usage"传入 `should_compact`(或经 `ContextConfig` 注入),保持条件注册表签名向后兼容(自定义条件不破坏)。

## 2. P1 · 窗口防线补全 + 调用鲁棒性

### B1 `context_window` 字段 + 百分比触发

profile 无"窗口"概念,触发阈值是手填裸数字(默认 `max_tokens: 192000`);换小窗口本地模型(8k/32k vLLM 很常见)用户不会想到同步改 context 阈值 → 必然溢出。加 `LLMProfileConfig.context_window`(可选)+ 内置 `window_pct` 触发条件(如 0.8 = 占用到窗口 80% 即压)。运行期旋钮。

### B2 context overflow 自救

API 报 `context_length_exceeded`(400)时 `paradigms/agent.py` 直接 raise、整轮挂掉。改为:捕获 → 强制压缩一次 → 重试本步(仅一次,防循环)。约 10 行;A2/B1 之后应极少触发,作最后防线。

### B3 超时 / 重试 / fallback 旋钮

现状仅 SDK 默认(2 次重试、600s 超时),流中断不重试,LLM 异常 = 整轮 raise。对照成熟 harness:429/5xx 指数退避 + 读 `Retry-After`、per-profile 超时、模型/供应商失败转移。薄做法:per-profile `timeout_seconds` / `max_retries`(透传 SDK 即可)+ 可选 `fallback: <profile 名>`(LLM 异常时换 profile 重试本步——profile 体系是现成载体)。流中断重试谨慎排后(half-stream 语义复杂)。

### B4 usage 细分与计费精度

`Usage` 不读 `prompt_tokens_details.cached_tokens` / `completion_tokens_details.reasoning_tokens`,profile 价格也没有 cached-input 档 → 命中供应商自动缓存的长会话**成本被系统性高估**——而长会话 + 重复前缀正是 agent loop 常态。薄做法:`Usage` 加两个可选字段 + profile 加 cached-input 价格档 + trace 计费时按缓存命中扣减。trace/预算是本项目卖点,精度值得补。

## 3. P2 · structured outputs 提前到默认路径

`response_format: json_schema` 在 Chat Completions 上已是标配能力,**不必等 Slice 12**(届时 Anthropic client 只需做映射)。作为 profile / 调用旋钮落 `OpenAIClient`。实现前需细化一点:与工具调用循环的交互(通常只在收尾步要 JSON 输出),旋钮作用面(全程 vs 收尾)要先定。

## 4. P3 · 压缩品质(不紧急)

- **D1 滚动摘要合并**:`summarize` 产生的摘要是 system note,而 `_split_keep_last_turns` 把 system 消息无条件保留 → 多次压缩后**摘要只增不并**。改为新一轮摘要把旧摘要一起折叠进去(滚动摘要)。
- **D2 microcompaction(工具结果老化)**:整体 summarize 前,先把久远 step 的工具输出替换为占位符(保留 tool_call 结构)——Claude Code 2026 的做法;可作内置策略或 `summarize` 的前置阶段。
- **D3 缓存友好压缩约束**:每次压缩重写消息前缀,必然击穿供应商 prompt cache;memory 注入每轮变化同理。不需要新机制——做 D1/D2 时把"前缀尽量稳定、变化靠尾部追加"记为设计约束即可(与 Slice 12 Phase 3 `cache_control` 互补;本条 provider 无关)。

## 5. 明确不缺 / 不建议补(避免误判成洞)

- **已对齐或领先**:可扩展压缩注册表(竞品多为黑盒)、compaction 开销计入 trace/预算(`_AccountingSummarizer`,多数竞品不做)、memory 的 `compact_rescue` 钩子、compaction 角色路由、采样参数"仅 set 时发"的 reasoning 模型兼容。
- **多模态输入(图片)**:成熟 harness 有,但与"薄 + 文本 agent 生成器"定位关系不大 → 观望不补。
- **`parallel_tool_calls` / `tool_choice` 强制旋钮**:边际价值低 → 观望。

## 6. 红线与人审复核(对照 `01 §6` / `CLAUDE.md §6`)

- 全部条目:不引 agent 编排框架、不触云托管/沙箱/权限红线 ✅;零新增依赖 ✅;运行期旋钮不改 spec schema(`§6.1` 不触发)✅;密钥路径不涉 ✅。
- **B3 fallback / P2 structured outputs** 贴近"LLM API 面"边缘:不改 Chat Completions 选型、默认不启用、不动默认行为,判断为不触 `§6.4`;**若实现时发现要动 `LLMClient` Protocol 签名,按 `§6.4` 停下请人签**。
- 排期本身 = 人决定(Slice 13+ 进入前需人排期,见 `02-development/00-overview.md §2`)。

## 7. 建议排期形态

P0 + P1 六项合计约一个小切片的体量("LLM 健壮性切片"),自然位置在 Slice 12 之前或并行——不依赖双规范,反而让双规范落地时少踩坑(usage 细分、窗口防线对 Anthropic client 同样适用)。P2/P3 可零散插队。

---

> 一句话:机制(注册表/路由/计账)已领先,缺的是让它们**在真实长会话里不出事**的工程细节——单轮截断、真实 usage、窗口感知、溢出自救、超时重试、缓存计价。全部薄、全部运行期、零依赖。
