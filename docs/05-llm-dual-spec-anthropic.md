# 05 · 原生 OpenAI+Anthropic 双规范 LLM client + 推理流式 UX（已实现，2026-06-10）

> 本文原为 `CLAUDE.md §6.4` 待签方案；**人 2026-06-10 签字放行（"开始规划并实现"=批准本文方案及其默认口径），当日按 Phase 1+2 实现完成**（Phase 3 prompt caching 精修仍留待后续，见 §6）。§8 各决策点的落定见文末"实现说明"。
> 由 `03-feature-landscape-and-proposals.md §3 T1-D` 升格而来（2026-06-07 人定向排为 Slice 12）。
> 口径基准：`00-overview.md §3` 决策表"LLM API 面"行（**默认 Chat Completions provider-agnostic 不动，双规范是可选第二条而非替换**）、`01-project-plan.md §6`（红线）。

---

## 1. 要解决的问题：兼容端点丢掉了推理模型的一等能力

当前产物 `llm.py` 只有一个 `OpenAIClient`，走 **Chat Completions + `tools`**，provider-agnostic（靠 `base_url`）。接 Claude 时走 **Anthropic 的 OpenAI 兼容端点 / LiteLLM**——能跑，但**兼容层会丢掉 Anthropic 原生 Messages 的一等能力**：

| 能力 | 兼容端点现状 | 原生 Messages |
|------|--------------|----------------|
| adaptive thinking + `effort` | 多数兼容层不透传 / 退化 | 一等参数，控制推理深度 |
| prompt caching（`cache_control`） | 丢失（省不了重复前缀的钱） | 一等，长系统提示/工具 schema 显著降本 |
| structured outputs | 不稳定 | 原生支持 |
| `tool_use` / `tool_result` content blocks | 被压成 OpenAI 形状，边角行为不一致 | 原生语义 |
| Opus 4.7/4.8 采样约束 | 兼容层可能误发 `temperature` 被拒 | 原生明确禁 `temperature`·`top_p`·`top_k` |

> **判断**：推理模型（thinking/effort）已是 2026 主流。"接 Claude 走兼容端点"从"够用"正在变成"漏掉用户现在就要的能力"。本特性把**原生 Anthropic** 作为**可选第二条 client** 补上，不动默认路径。

## 2. 关键使能件：loop 只认 provider-neutral 的 `LLMClient`

产物循环**不直接依赖 OpenAI SDK**。`llm.py` 已是一层 Protocol/适配：

```47:57:harnessforge/templates/src/__project_slug__/harness/llm.py.j2
    def complete(self, messages: list[dict], tools: list[dict] | None) -> LLMResponse:
        ...

    def stream(
        self,
        messages: list[dict],
        tools: list[dict] | None,
        *,
        on_delta: Callable[[str], None] | None = None,
    ) -> LLMResponse:
        ...
```

loop 拿到的永远是中性的 `LLMResponse`(`content` / `tool_calls` / `usage`)。**所以"原生 Anthropic"= 新增一个实现同一 `LLMClient` Protocol 的 `AnthropicClient`，把 Anthropic Messages 的请求/响应映射进/出这套中性 dataclass——加文件、不改循环。** 这正是 `llm.py` 顶部注释承诺的扩展点（"the same loop runs against any ... client"）。

## 3. 两规范的语义映射（实现核心）

`AnthropicClient` 要做的是**双向翻译**，把 loop 的 OpenAI 形状 messages/tools 映射成 Anthropic Messages，再把响应映射回 `LLMResponse`：

| 维度 | Chat Completions（loop 现状） | Anthropic Messages | 映射做法 |
|------|-------------------------------|---------------------|----------|
| system 提示 | `messages[0] = {"role":"system",...}` | 顶层 `system` 参数（不在 messages 内） | 抽出 system message → 顶层 `system` |
| 普通轮 | `{"role":"user"/"assistant","content":str}` | `{"role":..., "content":[blocks]}` | str → `[{"type":"text","text":...}]` |
| 工具定义 | `tools=[{"type":"function","function":{name,parameters}}]` | `tools=[{name, input_schema}]` | 摊平 `function.*` → 顶层 + `parameters`→`input_schema` |
| 模型发起调用 | `message.tool_calls[].function.{name,arguments(JSON str)}` | assistant 内容含 `{"type":"tool_use","id","name","input(dict)}` | `tool_use` → `ToolCall(id,name,arguments=json.dumps(input))` |
| 工具结果回喂 | `{"role":"tool","tool_call_id","content"}` | user 轮内 `{"type":"tool_result","tool_use_id","content"}` | tool message → tool_result block |
| usage | `usage.{prompt,completion,total}_tokens` | `usage.{input,output}_tokens`(+cache 字段) | 映射字段名；total = input+output |
| 采样 | `temperature`/`max_tokens`/`reasoning_effort` 仅 set 时发 | `max_tokens` **必填**;`thinking`+`effort`;Opus 4.7/4.8 **禁** `temperature`·`top_p`·`top_k` | `max_tokens` 兜底默认;按模型族跳过被禁采样参数 |
| prompt caching | 无 | content block 上 `cache_control:{type:"ephemeral"}` | 可选:对长 system / 工具 schema 打 cache 标记 |
| 思考 | 无原生 thinking 流 | thinking blocks / `effort` | 见 §5 推理流式 |

> 映射是**纯函数、可单测**——给定一组 OpenAI 形状 messages/tools，断言映射出的 Anthropic 载荷正确，反向亦然。golden 门禁(mock)不需要真 key。

## 4. 设计：spec 开关式可选模块（默认零痕迹）

### 4.1 spec / config 面

LLM API 面是结构轴。**新增一个 spec 字段标记 profile 走哪套规范**（这是 `CLAUDE.md §6.1` 改 spec schema，本方案待签的一部分）：

```yaml
# harness.spec.yaml（LLMProfile 新增 provider，默认 openai → 关闭时字节零痕迹）
llms:
  - name: default
    model: gpt-4o-mini
    api_key_env: OPENAI_API_KEY        # 现状不变
  - name: claude                        # 仅当用户选 anthropic 才出现
    provider: anthropic                 # 新增字段，默认 "openai"
    model: claude-opus-4-8
    api_key_env: ANTHROPIC_API_KEY
```

- `LLMProfile.provider: Literal["openai","anthropic"] = "openai"`（spec.py + 运行期 `LLMProfileConfig` 同步加）。**默认 `openai` → 生成的 `pyproject` 不含 `anthropic`、`config.yaml` 不出 `provider` 字段、字节与现状一致**。
- 依赖门控：仅当**任一 profile** `provider: anthropic` 时，渲染期把 `anthropic` 加进 `[project.optional-dependencies]`（沿用 Slice 3/4 "按 spec 条件渲染/加依赖"机制）。关闭 → 零新增依赖（薄验证：`pyproject`/`uv.lock`/`req` 不含 `anthropic`）。

### 4.2 client 分发（不改 loop、不改路由语义）

`make_client` / `ClientRouter` 按 `profile.provider` 选实现，其余不动：

```python
def _client_for_profile(profile):
    if profile.provider == "anthropic":
        from .llm_anthropic import AnthropicClient   # 单独文件，opt-in import
        return AnthropicClient(profile)
    return OpenAIClient(profile)
```

- `AnthropicClient` 放**单独文件** `harness/llm_anthropic.py`（`provider=openai` 时该文件可不渲染 → 真零痕迹），实现 `complete` / `stream`。
- 角色路由（`generation`/`compaction`/`embedding`）语义不变——只是某角色的 profile 可能是 Anthropic。
- `MockLLM` 不变，仍是离线测试/冒烟主力（双规范的映射逻辑用纯函数单测覆盖，不需真 key）。

## 5. 配套：推理/思考阶段的显式流式 UX

**缘起**（2026-06-03 Slice 3 真实 LLM 验收记下的 UX 坑，已登记）：推理模型在 reasoning 阶段会先沉默数秒才吐 content，流式下表现为"无反应等待"。

- **机制**：`stream()` 在收到 thinking/reasoning 增量时，经一个**新的回调/事件**显式提示，而非塞进 `on_delta`（那是最终答案文本）。Web 推 `event: thinking`（或前端"思考中…"指示器），CLI 打一行轻量提示。
- **两规范统一**：Anthropic 原生 thinking blocks → thinking 事件；OpenAI 兼容端点的 `reasoning_content`(若有) → 同一事件。**这层是 provider-neutral 的**：`LLMResponse`/回调约定加一个"思考流"通道，两个 client 都往里灌。
- **薄**：不解析/不存思考内容做检索，只做"有动静"的 UX 提示。default 行为不变（无 thinking 模型时零效果）。

## 6. 分阶段落地（薄优先、风险递增）

- **Phase 1 — 非流式映射**：`AnthropicClient.complete()`（§3 全套映射）+ spec `provider` 字段 + 依赖门控 + 关闭零痕迹断言。映射纯函数单测 + mock 黄金路径。**最先做、价值已兑现大半**（thinking/effort/caching 可用）。
- **Phase 2 — 流式 + 思考事件**：`AnthropicClient.stream()` + §5 思考流通道（两 client 统一）+ Web `event: thinking` + CLI 提示。
- **Phase 3（可选）— prompt caching / structured outputs 精修**：对长 system/工具 schema 打 `cache_control`；结构化输出按需。

## 7. 红线复核（对照 `01 §6` / `CLAUDE.md §6.4`）

- **不替换默认面**：默认 `provider=openai`、Chat Completions、provider-agnostic **完全不动**；双规范是**可选第二条**。✅（§4.1）
- **不换底座 SDK 选型方向**：仍 openai 官方 SDK 走默认；`anthropic` SDK 仅在 opt-in 时作可选依赖加入，不取代 openai SDK。✅
- **改 spec schema（`§6.1`）+ 改 LLM API 面（`§6.4`）**：`provider` 字段 + 第二套规范客户端**都触发人审**——本文即待签方案，**签字前不动代码**。⏳
- **薄 / 默认零痕迹**：关闭时 `pyproject`/`config.yaml`/字节与现状一致、不引 `anthropic`。✅
- **不让密钥进 git/trace**：Anthropic profile 同样只存 `api_key_env` 名，真值入 `.env`；trace 沿用脱敏纪律。✅
- **不引 agent 框架**：纯加一个 client 实现 + 映射函数，不引 LangChain/LiteLLM 进默认核心（当下兼容端点路径仍可用 LiteLLM，但那是用户运行期选择，不进产物依赖）。✅

## 8. 设计决策落定（人 2026-06-10 签字放行；按本文默认口径执行）

1. **立项 Slice 12**：✅ 批准（"开始规划并实现"即签字）。
2. **spec 字段**：✅ `provider: Literal["openai","anthropic"]`，默认 `openai`（`spec.LLMProfile` + 产物 `LLMProfileConfig` 同步）。
3. **依赖与文件门控**：✅ 任一 profile=anthropic 才渲染 `llm_anthropic.py` + `tests/test_llm_anthropic.py`、才把 `anthropic>=0.92` 加进产物 `dependencies`；默认 spec 的 `pyproject`/`config.yaml`/spec 快照零 anthropic 痕迹（快照序列化时丢弃默认 `provider: openai`，保持旧 spec 字节稳定）。实现说明：依赖进 `dependencies`（沿用 web/mcp 的条件渲染机制）而非字面 `optional-dependencies`——`uv sync` 直接可用，开箱即跑。
4. **思考流通道**：✅ 独立通道——`LLMClient.stream(on_thinking=...)` 新回调（与 `on_delta` 分离，chunk 可为 `""`=「在思考但内容隐藏」）；Web 推独立 `event: thinking`（前端一条灰色 "thinking …" 行，首个 token/工具/结束事件时移除）；CLI 每轮一行灰色 `· thinking …`（stderr，不污染 stdout 答案流）。OpenAI 兼容端点的 `reasoning_content` 透传进同一通道；MockLLM 流式时发一次 `"(mock thinking)"` 脉冲使通道离线可测。
5. **分阶段**：✅ Phase 1+2 一次做完（`LLMClient` Protocol 本就要求 `complete`+`stream`，只做 Phase 1 产物 Web 流式即缺口）；Phase 3（`cache_control` 精修 / structured outputs）仍留待后续。
6. **Opus 4.7/4.8 采样约束**：✅ 按模型族前缀（`claude-opus-4-7` / `claude-opus-4-8` / `claude-fable`）**静默跳过** `temperature`（产物本就不发 `top_p`/`top_k`）。另：`reasoning_effort` 复用为 Anthropic `effort`（`thinking: adaptive` + `output_config.effort`；`none`=不开思考、`minimal` 映射 `low`）；`max_tokens` 必填，未设兜底 16000。

### 实现说明（2026-06-10）

- 映射纯函数（`to_anthropic_messages` / `to_anthropic_tools` / `from_anthropic_content` / `from_anthropic_usage`）+ 流式拼装（含 `input_json_delta` 累积、thinking/text 双通道、cancel 关流）由产物自带 `tests/test_llm_anthropic.py` 覆盖，不需真 key。
- 分发：`llm._client_for_profile(profile)` 按 `provider` 选实现（`make_client` + `ClientRouter` 共用）；未渲染 anthropic 模块的产物若手改 `provider: anthropic`，报带指引的 `RuntimeError` 而非裸 ImportError。
- 门禁记录：生成器快测 171 全绿 + golden 13 全绿（含新增 anthropic golden、Docker 2、uvx 冒烟）。wizard 不露出 provider（行为性/llm 配置本就烤默认，沿用 Slice 7 口径）。

### 真实端点验收（2026-06-11，人提供 key，已通过）

用人配置的 `.env`（仅本地，已加 `.gitignore`）对两家 Anthropic 兼容端点做真实冒烟，全部通过：

- **MiMo `mimo-v2.5`**（token-plan Anthropic 端点）：非流式 complete + 真实 `tool_use` 往返（calculator，trace 确认 `tool_call`/`tool_result` 事件与 usage 映射）；流式 `input_json_delta` 累积出合法工具参数；CLI `· thinking …` 与 Web SSE `event: thinking` 均收到真实思考增量；`reasoning_effort: low`（`thinking: adaptive` + `output_config.effort`）端点接受。
- **DashScope `qwen3.6-flash`**（apps/anthropic 端点）：流式 + thinking + 工具调用交叉验证通过，确认映射非单端点兼容。
- DeepSeek 官方 anthropic 端点 401（`.env` 里 `DEEPSEEK_API_KEY` 是 token-plan 的 key，DeepSeek 官方不认）——验证了 401 错误能干净上抛，非本切片问题。
- 已知模型怪癖（非映射缺陷）：mimo-v2.5 对 Web 会话自动标题的 prompt 不遵从，直接回答了消息里嵌的算术（`{"result": "1452"}`）；title 调用本身不带工具、链路正确，换遵循指令的模型即正常。

---

> 一句话：双规范不是替换，是给推理模型补上"原生才有"的 thinking/effort——靠 loop 已有的 provider-neutral `LLMClient` 扩展点，加一个映射客户端 + 一个 spec 开关，关掉零痕迹。**已实现并过全部门禁（2026-06-10）。**
