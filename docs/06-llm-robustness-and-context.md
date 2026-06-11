# 06 · LLM 支持线差距:上下文工程正确性 + 调用鲁棒性

> **状态(2026-06-11,人定向后实现完成 + 真实端点验收通过)**:LLM 配置丰富化 + 本文 **P0 + P1 六项已全部实现并过门禁**(生成器快测 + 全量 golden + Docker + uvx 全绿),并经 **MiMo 真实双端点(OpenAI 兼容 + Anthropic 原生)端到端验收 29/29 通过**(人提供 key,详见文末 §8)。**P2 / P3 仍为 backlog**(`02-development/00-overview.md §2` Slice 14+)。落定的关键决策见下方各节 ✅ 标注与本节末"实现决策落定"。
>
> **增补(2026-06-11,缘起 MiMo 公告)**:新增 **§2.5 reasoning_content 多轮回传**(思考模式 + 工具调用时历史须带回 reasoning,否则 400)——已实现并过生成器快测 + 全量 golden(含 Docker/uvx);真实 MiMo 双端点验收待人给 key 触发。
>
> 本文原是 2026-06-10 一次"对标成熟 harness、聚焦 LLM 支持"探索的落地待办——逐项登记**此前 backlog 尚未出现**的 LLM 相关差距。
> 性质同 [`03-feature-landscape-and-proposals.md`](./03-feature-landscape-and-proposals.md)(对标分析 + 建议);与已实现的 [`05-llm-dual-spec-anthropic.md`](./05-llm-dual-spec-anthropic.md)(Slice 12)互补不重叠。
> 共同特征:**全部是运行期 `config.yaml` 旋钮 / 模板内部实现,不改 spec schema、零新增依赖、不触红线**。

## 实现决策落定(人 2026-06-11 签字,按此执行)

1. **LLM 配置丰富化**:常用采样参数升一等(`top_p` / `frequency_penalty` / `presence_penalty` / `seed` / `stop`,均"仅 set 时发")+ 通用 `extra_body: dict` 透传兜底(覆盖 `top_k` / `enable_thinking` / `thinking_budget` 等非标准参数)。全部进 `LLMProfileConfig`(运行期),web `/config` LLM 卡片 **Advanced(默认折叠)**,留空=用 provider 默认。
2. **上下文窗口 = per-profile `context_window`(默认不填)**:`window_pct` 触发**仅当该 profile 设了 `context_window`** 才生效;未设时不做百分比预压缩,靠 A1(单工具结果截断)+ B2(溢出自救)兜底——**永不误伤大窗口(如 1M)模型**。不做跨端自动探测(对标 Cursor/LiteLLM 靠人工维护的模型注册表,与本项目"provider-agnostic + 生成后不依赖 HarnessForge"定位冲突)。
3. **触发改真实 usage 驱动**:上一步真实 `prompt_tokens` 回喂触发条件(`ContextInfo`),字符估算仅作首调用兜底;**默认 triggers 由 `max_tokens:192000` 改为 `window_pct:0.85`**。
4. **注册表向后兼容**:自定义 `@register_condition` 的旧 `(messages, threshold)` 2 参签名仍可用(`should_compact` 按 arity 决定是否传 `info`),守"可扩展"核心卖点。

## 0. 一句话总览

交互层标配(会话 / HITL / MCP 管理)已补完,Anthropic 双规范已立项待签;剩下与成熟 harness(Claude Code / Codex CLI)差距最大、且 backlog 此前未登记的是两类:**上下文策略的工程正确性**(机制形态领先,但有四条会真实触发的故障路径)与 **LLM 调用鲁棒性**(当前是"裸调用")。

## 1. P0 · 上下文策略正确性(会真实发生的故障,建议先修)— ✅ 已实现

### A1 工具结果截断上限(单轮顶爆窗口的第一道闸)— ✅ 实现:`context.max_tool_result_chars`(默认 100k 字符 ≈ 25k token,0=关),在 `paradigms.run_tool` 尾部截断 + `[truncated N chars]` 标注

- **问题**:`context.py` 的 `_split_keep_last_turns` 以 user 轮切分,`keep_last_turns ≥ 1` ⇒ **进行中的当前轮永远整体保留**。agent 范式一轮可跑几十个 step、每步喂回工具结果——`fetch` 抓大页面 / Desktop Commander 读大文件,几个大观察值即可顶爆窗口,此时 `truncate`/`summarize` 都无事可做(dropped 为空)。`run_tool`(`paradigms/__init__.py`)现在原样返回任意大小的结果。
- **对标**:Claude Code 对单个 tool result 设上限(约 25k token),超出截断并提示模型(可分页 / 换更窄的查询)。
- **薄做法**:`config.yaml` 加 `tools.max_result_chars`(默认约 100k 字符 ≈ 25k token)+ `run_tool` 末尾一处截断(尾部标注 `[truncated N chars]` 让模型自纠)。运行期旋钮,不改 spec。
- **与已登记项的关系**:v1+ 的 **context offload**(大输出落盘给引用)是同一问题的高级出口;截断是兜底闸(极薄,先做),offload 维持 v1+。

### A2 压缩触发回喂真实 usage(修中文 2–4 倍低估)— ✅ 实现:`ContextInfo.last_prompt_tokens`(上一步真实 usage)经 `fit`→`should_compact` 注入,内置 `max_tokens`/`window_pct` 优先用真实 usage,字符估算仅首调用兜底

- **问题**:`estimate_tokens` 按 4 字符/token 估——对**中文是 2–4 倍低估**(中文 ≈ 1–1.5 字符/token)→ 压缩触发太晚 → 直接撞 context overflow。生成中文 agent 恰是本项目典型场景。
- **关键事实**:不需要引 tokenizer。上一次 LLM 响应的 `usage.prompt_tokens` 就是供应商报告的精确值,loop/trace 已经在手,只是没有回喂给触发条件。成熟 harness 的 auto-compact 都按真实 usage 驱动(占用 vs 窗口百分比)。
- **薄做法**:`max_tokens` 条件改为"上次真实 prompt_tokens + 本步新增消息的字符估算";字符估算仅兜底首次调用。实现上把"上次 usage"传入 `should_compact`(或经 `ContextConfig` 注入),保持条件注册表签名向后兼容(自定义条件不破坏)。

## 2. P1 · 窗口防线补全 + 调用鲁棒性 — ✅ 已实现

### B1 `context_window` 字段 + 百分比触发 — ✅ 实现:`LLMProfileConfig.context_window`(默认 None)+ 内置 `window_pct` 条件(默认 0.85);未设窗口则该条件不触发(靠 A1+B2 兜底,不误伤大窗口模型)

profile 无"窗口"概念,触发阈值是手填裸数字(默认 `max_tokens: 192000`);换小窗口本地模型(8k/32k vLLM 很常见)用户不会想到同步改 context 阈值 → 必然溢出。加 `LLMProfileConfig.context_window`(可选)+ 内置 `window_pct` 触发条件(如 0.8 = 占用到窗口 80% 即压)。运行期旋钮。

### B2 context overflow 自救 — ✅ 实现:共享 `paradigms.generate()` 捕获 `is_context_overflow(exc)` → `fit(force=True)` 强制压一次 → 重试本步一次(再失败上抛,不循环)

API 报 `context_length_exceeded`(400)时 `paradigms/agent.py` 直接 raise、整轮挂掉。改为:捕获 → 强制压缩一次 → 重试本步(仅一次,防循环)。约 10 行;A2/B1 之后应极少触发,作最后防线。

### B3 超时 / 重试 / fallback 旋钮 — ✅ 实现:`LLMProfileConfig.timeout_seconds`/`max_retries` 透传 SDK 构造器;`fallback`(profile 名)在非溢出错误且**尚未吐 delta** 时切该 profile 重试本步一次(流已开始不重试)。未改 `LLMClient` Protocol 签名 → 未触 §6.4

现状仅 SDK 默认(2 次重试、600s 超时),流中断不重试,LLM 异常 = 整轮 raise。对照成熟 harness:429/5xx 指数退避 + 读 `Retry-After`、per-profile 超时、模型/供应商失败转移。薄做法:per-profile `timeout_seconds` / `max_retries`(透传 SDK 即可)+ 可选 `fallback: <profile 名>`(LLM 异常时换 profile 重试本步——profile 体系是现成载体)。流中断重试谨慎排后(half-stream 语义复杂)。

### B4 usage 细分与计费精度 — ✅ 实现:`Usage` 加 `cached_prompt_tokens`/`reasoning_tokens`(OpenAI `prompt_tokens_details.cached_tokens`/`completion_tokens_details.reasoning_tokens`;Anthropic `cache_read_input_tokens`)+ `LLMProfileConfig.cached_input_cost_per_million`;`compute_cost` 缓存命中按缓存价计、**未设缓存价则按全价(不误降)**;trace 累计 cached 并在 `llm_response` 事件暴露

`Usage` 不读 `prompt_tokens_details.cached_tokens` / `completion_tokens_details.reasoning_tokens`,profile 价格也没有 cached-input 档 → 命中供应商自动缓存的长会话**成本被系统性高估**——而长会话 + 重复前缀正是 agent loop 常态。薄做法:`Usage` 加两个可选字段 + profile 加 cached-input 价格档 + trace 计费时按缓存命中扣减。trace/预算是本项目卖点,精度值得补。

## 2.5 P0 · reasoning_content 多轮回传(思考模式 + 工具调用)— ✅ 已实现(2026-06-11,缘起 MiMo 公告)

- **问题(会真实 400 的故障)**:产物把推理仅当作一次性「思考中」UX 提示——`OpenAIClient` 流式 `reasoning_content` 只喂 `on_thinking` 后丢弃、非流式不读,`LLMResponse` 无 reasoning 字段,`assistant_message()` 重建历史只含 `content`+`tool_calls`。于是**带工具调用的 assistant 历史消息回传时缺 `reasoning_content`**。MiMo 公告(及 DeepSeek 思考 / Qwen / Kimi 同源)要求:思考模式下历史含工具调用时,后续回传的带 tool_calls 的 assistant **必须**完整带 `reasoning_content`,否则 **400**。Anthropic 原生同源:带 `tool_use` 的 assistant 必须以带 `signature` 的 thinking block 开头。单轮多步(Request 1‑2 含上一步工具调用 assistant)与跨轮 resume 都会踩中。
- **设计原则**:**只回显端点自己产出的 reasoning + 只挂在带 `tool_calls` 的 assistant 上**——对 OpenAI 官方 / 非推理模型零痕迹(它们不吐 reasoning,`LLMResponse.reasoning` 恒空,什么都不挂),顺带修了 DeepSeek/Qwen/Kimi 同款 bug;最终无工具的答复消息不挂(避开"无工具却带 reasoning → 老 DeepSeek 400 / Qwen 忽略")。
- **实现**:`LLMResponse` 加 `reasoning`/`reasoning_signature`;两 client 的 `complete`/`stream` 捕获(OpenAI `reasoning_content`→`reasoning` 兜底;Anthropic thinking 文本 + `signature_delta`);`assistant_message()` 在带工具调用时写中性键 `reasoning_content`(+ `reasoning_signature`);`OpenAIClient` 发请求层按 `reasoning_history_field`(默认 `reasoning_content`,`""`=关,vLLM 可设 `reasoning`)重命名/开关并 **strip 掉 Anthropic 专属 `reasoning_signature`**;`to_anthropic_messages` 在带工具调用 assistant 前补带 signature 的 thinking block(无 signature 则跳过,避免裸 thinking block 反而 400)。压缩/持久化天然安全(整条 dict 保留/原样存),仅加回归测试 + 不变量注释钉死;`estimate_tokens` 计入 `reasoning_content`。
- **风险与残留**:① 字段名分歧靠 `reasoning_history_field` 旋钮兜底(web `/config` 按名保留,不新增可见 UI);② Anthropic `redacted_thinking`(罕见、加密打码)暂不保留——代码注释标注的已知限制;③ 压缩需保持"整条 dict 不 strip",已加注释 + 测试守护。
- **门禁**:生成器快测 182 + 全量 golden 13(含 Docker build+run、uvx)全绿;新增产物单测覆盖 OpenAI 捕获/wire 翻译(字段名/off/strip signature)、Anthropic signature 往返、loop 往返、压缩与 session 保留 reasoning;`ReadLints` 无新增。**真实 MiMo 双端点端到端验收需人提供 key(§0.1),待人触发**。
- **红线复核**:不改 spec schema(`reasoning_history_field` 是运行期 `LLMProfileConfig` 字段)、零新依赖、不引框架、不改 LLM API 面(仍 Chat Completions / Anthropic Messages,未改 `LLMClient` Protocol 方法签名 → 不触 §6.4)、reasoning 非密钥(随会话文本走既有持久化纪律,debug 日志不记内容)→ 不触 `CLAUDE.md §6`。

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

- 全部条目:不引 agent 编排框架、不触云托管/沙箱/权限红线 ✅;零新增依赖 ✅;运行期旋钮不改 spec schema(`§6.1` 不触发)✅;密钥路径不涉(`extra_body` 仅存非密钥值,文档点明)✅。
- **B3 fallback / extra_body**(已实现):不改 Chat Completions 选型、默认不启用、不动默认行为,**未改 `LLMClient` Protocol 签名** → 确认不触 `§6.4` ✅。**P2 structured outputs**(未做)落地时若要动 Protocol 仍按 `§6.4` 停下请人签。
- P0+P1 排期 = 人 2026-06-11 定向并实现(见本文顶部状态);**P2/P3 仍排 Slice 14+**(`02-development/00-overview.md §2`)。

## 7. 排期形态 — ✅ P0+P1 已作为一个小切片实现(2026-06-11)

P0 + P1 六项 + LLM 配置丰富化合为一个小切片("LLM 配置丰富化 + 上下文管理策略补充")**已实现**:usage 细分 / 窗口防线 / 采样旋钮对 OpenAI 与 Anthropic 两 client 同样适用,双规范不受影响。**P2/P3 仍可零散插队**(见下)。

## 8. 真实端点验收(2026-06-11,人提供 key,29/29 通过)

用人配置的本地 `.env`(MiMo,`mimo-v2.5`,**OpenAI 兼容 + Anthropic 原生两端点**)生成 `coding-assistant` 产物并对本文全部条目做真实端到端验证,**29 项检查全绿**(允许 token 消耗)。逐项:

- **采样旋钮(LLM 配置丰富化)**:`top_p`/`frequency_penalty`/`presence_penalty`/`seed`/`stop` 一并发给 MiMo OpenAI 端点 **全部被接受(无 400)**,`stop` 序列真实生效(停止串不出现在输出)。`seed` 参数被接受;**复现性是供应商 best-effort**(MiMo 为推理模型,不保证同 seed 同输出)——门槛取"接受 + 两次调用都成功",决定性作观察。
- **`extra_body` 透传**:`{enable_thinking: false}` 与 `{top_k: 20}` 均被端点接受(无 400),证明 SDK 原样透传非标准参数。**MiMo 忽略 `enable_thinking`(reasoning 仍跑)= 供应商是否实现该参数的范畴**,透传机制本身已由"被接受"证明。
- **B4 cached/reasoning usage**:MiMo OpenAI 端点真实返回 `prompt_tokens_details.cached_tokens`(实测 192)与 `completion_tokens_details.reasoning_tokens`(实测 63–183),正确映射进 `Usage.cached_prompt_tokens`/`reasoning_tokens`;Anthropic 端 `cache_read_input_tokens` 同样映射。`compute_cost` 对缓存命中按 `cached_input_cost_per_million` 计、**未设缓存价时按全价(不误降)**,均断言精确。
- **A2 真实 usage 驱动触发**:同一短消息真实 `prompt_tokens=248` ≫ 字符估算 `4`(实证中文/紧凑 prompt 的数倍低估);真实 usage 命中 `max_tokens:100` 触发而字符估算不命中。
- **B1 `context_window` + `window_pct`**:接近满窗(ratio 0.90)触发、大窗口(×1000)静默不误压、未设 `context_window` 不触发;`summarize` 经**真实 compaction LLM** 把 16 条历史实压到 5 条并带摘要 note。
- **B2 溢出自救**:**真实发现——MiMo 与 DeepSeek 生产端点对超长输入(~1.25M 字符)自动截断/滑窗并正常作答,而非返回 `context_length_exceeded`**,故无法靠输入体积在这些端点触发 B2(印证其"罕见最后防线"定位)。改用**真实 `openai.BadRequestError` + 真实供应商措辞**验证 `is_context_overflow`(识别三种 overflow 措辞、忽略瞬时 503 以便走 fallback 而非压缩),并以**真实 MiMo 端点作 retry 目标**验证 `generate()` 的"检测溢出 → 强制压一次 → 重试本步"控制流(`calls=2`、消息 3→1、重试成功)。
- **B3 超时/重试/fallback**:坏模型名报错**未被误判为 overflow**(走 fallback 而非压缩);`generate()` 真实切换到 `backup` profile 重试成功;`timeout_seconds`/`max_retries` 透传 SDK 后真实调用正常。
- **A1 单工具结果截断**:大结果被截到 `max_tool_result_chars` 并带 `[truncated N chars]` 标注,`0` 关闭则原样通过。
- **真实 function-calling(两规范)**:OpenAI 与 Anthropic 端各跑通一次完整 agent turn(`calculator`,得正确答案 12),trace 记录真实 usage(含 cached),Anthropic `tool_use`↔`tool_result` 往返 + 思考流 `on_thinking` 真实增量(实测 51 次)均正常。

> 验收方式:生成产物 → `uv sync` → 真实脚本逐项断言(不改生成器/模板代码,纯真实验证)。三项最初的"失败"经核查均为**端点特性而非功能缺陷**(MiMo 不保证 seed 决定性、忽略 enable_thinking;两端点自动截断超长输入),已据此把对应断言定位为观察项 / 改用真实 SDK 异常验证。

---

> 一句话:机制(注册表/路由/计账)已领先,缺的是让它们**在真实长会话里不出事**的工程细节——单轮截断、真实 usage、窗口感知、溢出自救、超时重试、缓存计价。全部薄、全部运行期、零依赖。
