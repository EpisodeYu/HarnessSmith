# 调研与可行性:Agent Harness（2026）

> 本文是 HarnessSmith 立项的背景调研。先讲清楚 2026 年大火的 "harness" 概念，再盘点竞品、判断立项意义、评估可行性与难度。

## 1. harness 是什么（2026 年的定义）

核心共识只有一条公式:

> **Agent = Model + Harness**

模型负责"想",harness 负责"让它真的、可靠地、反复地做成"。harness = 一个 agent 里**除模型权重之外的一切**:系统提示、工具定义、循环控制、沙箱、hooks、记忆系统、文件系统、可观测性。

这个词在 2026 年才被正式标准化:OpenAI 在 3 月发布《Harness Engineering》、Anthropic 跟进长时任务的 harness 设计、Martin Fowler 站点上 Birgitta Böckeler 写了配套文章,几周内术语统一。连 DeepSeek 都成立了专门的 "Harness" team 来做 DeepSeek Code(对标 Claude Code / OpenAI Codex)。Claude Code 官方文档直接写道:"Claude Code serves as the agentic harness around Claude"。

### 1.1 一个标准 harness 的组成

这也正是 HarnessSmith 需要能生成的模块:

- **编排循环 (Orchestration Loop)**:ReAct / TAO(Thought-Action-Observation)状态机,决定何时继续、何时停、出错怎么办。"call the model until done" 不是 harness,是 bug。
- **上下文工程 (Context Management)**:选择检索什么、压缩超窗历史、过滤噪音、把大工具输出 offload 到磁盘。多数 agent 失败源于"对着错误的上下文推理"。
- **工具执行层 (Tool Execution)**:把模型意图映射到真实函数调用,做 schema 校验与错误契约 —— 这里 **MCP** 是事实标准。
- **沙箱 (Sandbox)**:Docker / microVM 隔离执行。
- **状态与记忆 (State / Memory)**:跨会话续跑,不从零开始。
- **护栏与验证 (Guardrails / Verification)**:校验输出、救援坏 JSON、lint/test gate、自纠错循环。
- **可观测性 (Observability)**:全链路 trace、成本、工具级失败归因。
- **Guides(前馈)/ Sensors(反馈)** 两类控制 + 生命周期 Hooks。

### 1.2 关键趋势

**模型越强,harness 越薄。** Manus 半年重写 5 次,每次都在删复杂度(复杂工具定义 → 通用 shell;"管理 agent" → 简单结构化交接)。这对 HarnessSmith 是利好:目标就是"生成可拥有、可删改的薄 harness 代码",踩在潮流上。

## 2. 竞品盘点(有无立项意义)

把赛道分成三层,HarnessSmith 的构思横跨其中两层:

### A. 无代码 / 低代码托管平台(描述→直接跑,框架隐藏,SaaS 托管)
- Arahi AI、Nagent、MindStudio、SketricGen、Vellum。
- **与诉求冲突**:锁定、托管、隐藏 harness,不给"可自定义、不依赖 agent 框架的代码"。

### B. 代码脚手架生成器(最接近 HarnessSmith)
- [`create-agent-app` / AgentForge](https://github.com/Saichandra2520/agentforge):一条命令生成 ReAct/RAG/Multi-Agent —— 但**构建在 LangGraph 之上**(正是要避开的)。
- [`create-google-adk-agent`](https://github.com/unrealandychan/create-adk-agent):交互式向导选 agent 类型/工具/MCP —— 但绑死 Google ADK。
- [`full-stack-ai-agent-template`](https://github.com/vstorm-co/full-stack-ai-agent-template):FastAPI + Next.js,内置 5 个 agent 框架、4 个向量库、RAG、流式、会话持久化 —— 功能很全,但**静态模板 + 依赖 agent 框架**,没有 Web 配置向导。
- 各类 cookiecutter(agent-api-cookiecutter、agent-framework-cookiecutter 等):都绑定某个框架。

### C. 轻量框架 / from-scratch 教学仓库
- 运行时框架:[OpenAI Agents SDK](https://github.com/openai/openai-agents-python)、PydanticAI、Agno、Atomic Agents —— 是框架而非生成器。
- 大量 "ReAct from scratch / NanoHarness" 教学仓库 —— 是示例而非工具。

### 结论:立项有意义,但窗口窄

HarnessSmith 设想的精确组合 —— **"不绑定 agent 编排框架(LangChain/LangGraph/ADK)、生成你完全拥有可删改代码的 harness 生成器 + Web 可视化配置向导 + MCP 工具目录 + RAG/上下文/护栏可选 + 同时产出 Web/CLI 接口"** —— 目前**没有完全对位的项目**。MVP 不一次做全,先收敛到「生成 → 跑通 → 易改」的黄金路径,其余按分层(L1/L2/L3)推进(详见 [01-project-plan.md](./01-project-plan.md))。

差异化窗口比较窄,必须把以下三点打透,否则会被 `create-agent-app` 与 `full-stack-ai-agent-template` 覆盖:
1. **无 agent 框架锁定(不是「无依赖」)**:生成代码零 LangChain/LangGraph/ADK 等 **agent 编排框架**依赖;底座只用通用库(openai SDK / pydantic / typer 等),不构成锁定。
2. **own-your-code(eject 即所得)**:产出独立、可读、可删改的仓库。
3. **配置即生成**:Web 向导 / CLI 采集 spec → 一键渲染。

## 3. MCP 生态(可复用的工具层)

- 官方 [MCP Registry](https://registry.modelcontextprotocol.io/);Smithery(7000+ servers,CLI 一键装)、mcp.so(19000+)、Glama、[awesome-mcp-servers](https://github.com/punkpeye/awesome-mcp-servers)。
- MCP 在 2026 年初已达 ~9700+ 公共 server、月 ~9700 万 SDK 下载。官方 Python SDK 成熟,接入 stdio / HTTP-SSE 传输都简单。
- HarnessSmith MVP 接入 **stdio 本地 + 远程 HTTP/SSE 传输**(2026-06-03 定向,取代初版"仅 stdio");生成期只决定有无,server/tool 全运行期 `config.yaml` 配。**联网 registry 仍推迟 v1+**;静态 catalog 降级为 wizard 预填便捷数据源(非安全闸)。安全上需注意:工具元数据会被 agent 当指令,优先用 vendor 维护的 server、收紧权限、高风险工具默认关。

## 4. 可行性与难度

整体**可行**,核心不难,难在"做全 + 做好"。粗略拆解(单人 / 小团队;"层"列对应 [01-project-plan.md](./01-project-plan.md) 的 L1/L2/L3 分层 MVP):

| 模块 | 难度 | 层 | 说明 |
| --- | --- | --- | --- |
| 核心循环(原生 function-calling) | 易 | L1 | 150–300 行;走 Chat Completions + tools(provider-agnostic),不用 Responses |
| 代码生成引擎(Jinja2 + spec) | 中 | L1 | |
| 可运行性 / 打包(uv 契约 + Docker + 冒烟自检) | 易–中 | L1 | uv 锁定 + 自动管 Python;默认产出 Dockerfile/devcontainer;生成后自检 |
| 轻量可观测(JSONL trace + 成本) | 中 | L1 | |
| 轻量护栏(预算停止) | 中 | L1 | HITL Web 确认推迟到 L3 |
| MCP 工具接入(MCP Python SDK) | 易–中 | L2 | **stdio + 远程 HTTP/SSE**(2026-06-03 定向);联网 registry 推迟 v1+ |
| 多 LLM profile + 角色路由 | 中 | L2 | generation/compaction/embedding 分别绑定 |
| 上下文预算管理(truncate/summarize) | 中 | L2 | offload 落盘推迟到 L3 |
| Web 配置向导 | 中 | L2 | 无构建单页即可 |
| 基础 RAG(chunk/embed/检索) | 中 | L3 | sqlite-vec 本地零服务;备 numpy 余弦兜底 |
| 沙箱 / 隔离执行(Docker/microVM) | 中–难 | v2 | 最易拖时间;区别于 L1 的打包用 Docker |

**风险点**:scope 过大(想一次全做)、差异化不够锐(沦为又一个脚手架)、沙箱与安全是深坑、生成产物在异构环境跑不起来。对策:MVP 收敛到**黄金路径**并按**垂直切片**推进(详见 [01-project-plan.md](./01-project-plan.md) §3/§9);可运行性靠 uv 契约 + 默认 Docker + 生成后冒烟自检(§7);沙箱 / 多范式 / 联网 MCP registry / RAG 等坚决推迟。

## 5. 参考资料

- Martin Fowler / Birgitta Böckeler — Harness engineering for coding agent users: <https://martinfowler.com/articles/harness-engineering.html>
- Hugging Face — Harness, Scaffold, and the AI Agent Terms Worth Getting Right: <https://huggingface.co/blog/agent-glossary>
- Towards AI — Harness Engineering: The Layer That Matters More Than the Model
- The Anatomy of an Agent Harness — agent-cookbook.com
- OpenAI Agents SDK: <https://github.com/openai/openai-agents-python>
- 官方 MCP Registry: <https://registry.modelcontextprotocol.io/>
- awesome-mcp-servers: <https://github.com/punkpeye/awesome-mcp-servers>
