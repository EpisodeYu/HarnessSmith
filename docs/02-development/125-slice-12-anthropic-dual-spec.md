# 02·12 - Slice 12:原生 OpenAI+Anthropic 双规范 LLM client + 推理流式 UX

> 给 `llm.py` 补第二个走**原生 Anthropic Messages** 的 client，并把 reasoning/thinking 阶段做成显式流式提示。
>
> 口径基准：[`00-overview.md`](./00-overview.md) §6 决策表「LLM API 面」行（默认 Chat Completions provider-agnostic 不动，双规范是内建第二条而非替换）、§10 红线。

## 1. 要解决的问题:兼容端点丢掉了推理模型的一等能力

产物 `llm.py` 的默认 client 走 **Chat Completions + `tools`**，provider-agnostic（靠 `base_url`）。接 Claude 时走 Anthropic 的 OpenAI 兼容端点 / LiteLLM——能跑，但兼容层会丢掉原生 Messages 的一等能力：

| 能力 | 兼容端点现状 | 原生 Messages |
|------|--------------|----------------|
| adaptive thinking + `effort` | 多数兼容层不透传 / 退化 | 一等参数，控制推理深度 |
| prompt caching（`cache_control`） | 丢失（省不了重复前缀的钱） | 一等，长系统提示/工具 schema 显著降本 |
| structured outputs | 不稳定 | 原生支持 |
| `tool_use` / `tool_result` content blocks | 被压成 OpenAI 形状，边角行为不一致 | 原生语义 |
| Opus 系采样约束 | 兼容层可能误发 `temperature` 被拒 | 原生明确禁 `temperature`·`top_p`·`top_k` |

推理模型（thinking/effort）已是主流。本特性把**原生 Anthropic** 作为**内建第二条 client** 补上，不动默认路径。

## 2. 关键使能件:loop 只认 provider-neutral 的 `LLMClient`

产物循环不直接依赖 OpenAI SDK。`llm.py` 已是一层 Protocol/适配：loop 拿到的永远是中性的 `LLMResponse`（`content` / `tool_calls` / `usage`）。**所以「原生 Anthropic」= 新增一个实现同一 `LLMClient` Protocol 的 `AnthropicClient`，把 Anthropic Messages 的请求/响应映射进/出这套中性 dataclass——加文件、不改循环。**

```
def complete(self, messages, tools) -> LLMResponse: ...
def stream(self, messages, tools, *, on_delta=None, on_thinking=None, cancel=None) -> LLMResponse: ...
```

## 3. 两规范的语义映射(实现核心)

`AnthropicClient` 做**双向翻译**，把 loop 的 OpenAI 形状 messages/tools 映射成 Anthropic Messages，再把响应映射回 `LLMResponse`：

| 维度 | Chat Completions（loop 现状） | Anthropic Messages | 映射做法 |
|------|-------------------------------|---------------------|----------|
| system 提示 | `messages[0] = {"role":"system",...}` | 顶层 `system` 参数 | 抽出 system message → 顶层 `system` |
| 普通轮 | `{"role":...,"content":str}` | `{"role":..,"content":[blocks]}` | str → `[{"type":"text","text":...}]` |
| 工具定义 | `tools=[{"type":"function","function":{name,parameters}}]` | `tools=[{name, input_schema}]` | 摊平 `function.*` → 顶层 + `parameters`→`input_schema` |
| 模型发起调用 | `message.tool_calls[].function.{name,arguments(JSON str)}` | assistant 含 `{"type":"tool_use","id","name","input(dict)}` | `tool_use` → `ToolCall(id,name,arguments=json.dumps(input))` |
| 工具结果回喂 | `{"role":"tool","tool_call_id","content"}` | user 轮内 `{"type":"tool_result","tool_use_id","content"}` | tool message → tool_result block |
| usage | `usage.{prompt,completion,total}_tokens` | `usage.{input,output}_tokens`(+cache 字段) | 映射字段名；total = input+output |
| 采样 | `temperature`/`max_tokens`/`reasoning_effort` 仅 set 时发 | `max_tokens` **必填**；`thinking`+`effort`；Opus 系禁 `temperature`·`top_p`·`top_k` | `max_tokens` 兜底默认；按模型族跳过被禁采样参数 |
| prompt caching | 无 | content block 上 `cache_control:{type:"ephemeral"}` | 可选：对长 system / 工具 schema 打 cache 标记 |
| 思考 | 无原生 thinking 流 | thinking blocks / `effort` | 见 §5 推理流式 |

映射是**纯函数、可单测**——给定一组 OpenAI 形状 messages/tools，断言映射出的 Anthropic 载荷正确，反向亦然。golden 门禁（mock）不需要真 key。

## 4. 设计:双协议内建(默认 openai,运行期可切)

LLM API 面是结构轴，但双协议做成**内建**而非门控开关：

- `LLMProfile.provider: Literal["openai","anthropic"] = "openai"`（spec.py + 运行期 `LLMProfileConfig` 同步）。spec 的 `provider` 字段仅决定 profile 的初始值。
- 每个产物都渲染 `harness/llm_anthropic.py` + `tests/test_llm_anthropic.py` 并带 `anthropic` 依赖（进 `dependencies`，`uv sync` 开箱即跑）；`config.yaml` 显式写出每个 profile 的 `provider`（默认 `openai`），用户运行期在 `/config` 面板下拉或手改 yaml 即切，无需重新生成。
- spec 快照仍丢弃默认 `provider: openai`（旧 spec 字节稳定）。openai-only 运行**不 import anthropic SDK**（懒加载）。
- client 分发：`llm._client_for_profile(profile)` 按 `provider` 选实现（`make_client` + `ClientRouter` 共用）；未渲染 anthropic 模块时手改 `provider: anthropic` 报带指引的 `RuntimeError` 而非裸 ImportError。
- 角色路由（`generation`/`compaction`/…）语义不变——只是某角色的 profile 可能是 Anthropic。
- `MockLLM` 不变，仍是离线测试/冒烟主力（双规范映射逻辑用纯函数单测覆盖，不需真 key）。
- 产物 `/config` 面板 LLM 卡片露出 `provider` 下拉（name/model/provider 三列）；wizard 不需要任何 anthropic 选项（产物天生双协议，切换是运行期配置）。`test-llm`（CLI + Web）按 `provider` 走 `_client_for_profile` 分发。

## 5. 配套:推理/思考阶段的显式流式 UX

推理模型在 reasoning 阶段会先沉默数秒才吐 content，流式下表现为「无反应等待」。

- **机制**：`stream()` 在收到 thinking/reasoning 增量时，经一个**独立的回调/事件**（`on_thinking`，与 `on_delta` 分离；chunk 可为 `""` = 在思考但内容隐藏）显式提示。Web 推独立 `event: thinking`；CLI 每轮一行灰色 `· thinking …`（stderr，不污染 stdout 答案流）。
- **两规范统一**：Anthropic 原生 thinking blocks → thinking 事件；OpenAI 兼容端点的 `reasoning_content`（若有）→ 同一通道。这层是 provider-neutral 的。`MockLLM` 流式时发一次脉冲使通道离线可测。
- **薄**：不解析/不存思考内容做检索，只做「有动静」的 UX 提示。无 thinking 模型时零效果。
- **`reasoning_effort` 复用为 Anthropic `effort`**（`thinking: adaptive` + `output_config.effort`；`none`=不开思考、`minimal` 映射 `low`）；`max_tokens` 必填，未设兜底。Opus 系按模型族前缀静默跳过被禁的 `temperature`。

### Web reasoning / 工具可视化

产物 Web 聊天页（纯前端 `web_index.html`，零新增依赖、不改 spec/SSE 事件契约/后端）的四态可视化：① 发送即出现带动画省略号的「思考中」占位（非推理模型则首 token 即移除空占位）；② reasoning 流入独立折叠框（小号灰字、思考时展开实时滚动）；③ 最终答案首 token 到达即折叠为一行「已思考 · N 秒」（可点开重读）；④ 工具调用 = 合一折叠块（折叠态：工具名 + 命令/参数预览 + 运行中/完成/出错状态点，展开看完整参数 + 结果）。多步轮里「思考框→工具块→思考框→…→答案」按序交织；历史会话重开经 `renderHistory` 用同款组件还原。

### reasoning 持久化

- **工具调用轮**：reasoning 落中性键 `reasoning_content`（API 必须回喂、由各 client 映射上线）。
- **最终答案轮**：经 `paradigms.final_assistant_message(answer, reasoning)` 落**纯显示键 `reasoning_display`**，使无工具的「思考 + 回答」轮重开也能展开思考。该键绝不上线——`OpenAIClient._wire_messages` 把它与 `reasoning_content`/`reasoning_signature` 一并从 wire 剥离，Anthropic 映射只读已知键天然忽略。agent/plan/ask 三范式统一调 helper。
- 详细的 reasoning 多轮回传（思考模式 + 工具调用时历史须带回 reasoning，否则 400）见 [`15-llm-robustness-and-context.md`](./15-llm-robustness-and-context.md) §2.5。

## 6. 分阶段落地

- **Phase 1 — 非流式映射**：`AnthropicClient.complete()`（§3 全套映射）+ `provider` 字段 + 双协议内建渲染。映射纯函数单测 + mock 黄金路径。
- **Phase 2 — 流式 + 思考事件**：`AnthropicClient.stream()`（含 `input_json_delta` 工具参数累积、thinking/text 双通道、cancel 关流）+ §5 思考流通道（两 client 统一）+ Web `event: thinking` + CLI 提示。
- **Phase 3（可选）— prompt caching / structured outputs 精修**：对长 system/工具 schema 打 `cache_control`；结构化输出按需。

## 7. 红线复核（对照 §10 / `CLAUDE.md §6.4`）

- **不替换默认面**：默认 `provider=openai`、Chat Completions、provider-agnostic 完全不动；双规范是内建第二条。
- **不换底座 SDK 选型方向**：仍 openai 官方 SDK 走默认；`anthropic` SDK 作产物默认依赖加入，不取代 openai SDK。
- **薄**：openai-only 运行不 import anthropic SDK（懒加载）。
- **不让密钥进 git/trace**：Anthropic profile 同样只存 `api_key_env` 名，真值入 `.env`；trace 沿用脱敏纪律。
- **不引 agent 框架**：纯加一个 client 实现 + 映射函数（兼容端点路径仍可用 LiteLLM，但那是用户运行期选择，不进产物依赖）。

## 8. 关键设计决策(最终)

1. **spec 字段**：`provider: Literal["openai","anthropic"]`，默认 `openai`（`spec.LLMProfile` + 产物 `LLMProfileConfig` 同步）。
2. **双协议内建**：每个产物恒渲染 `llm_anthropic.py` + 其测试、恒带 `anthropic` 依赖（进 `dependencies`）；`config.yaml` 显式写 `provider:`（默认 `openai`）供用户改；spec 快照丢弃默认值。openai-only 运行懒加载、不 import anthropic SDK。产物 `/config` LLM 卡片恒有 provider 下拉。
3. **思考流通道**：独立 `LLMClient.stream(on_thinking=...)` 回调（与 `on_delta` 分离）；Web 推独立 `event: thinking`；CLI 每轮一行灰色 `· thinking …`（stderr）。OpenAI 兼容端点 `reasoning_content` 透传进同一通道。
4. **Opus 系采样约束**：按模型族前缀静默跳过 `temperature`（产物本就不发 `top_p`/`top_k`）。
5. **Web 可视化**：四态（动画占位 / reasoning 折叠框 / 答案折叠为「已思考 N 秒」 / 工具调用合一折叠块）+ reasoning 持久化（工具轮 `reasoning_content` / 最终轮显示专用 `reasoning_display`，wire 剥离不回喂）。Web-only（CLI 维持一行 `· thinking …`），不加显示开关。

> 一句话：双规范不是替换，是给推理模型补上「原生才有」的 thinking/effort——靠 loop 已有的 provider-neutral `LLMClient` 扩展点，加一个映射客户端；双协议内建于每个产物，`provider` 默认 `openai`、运行期面板/配置随时切。
