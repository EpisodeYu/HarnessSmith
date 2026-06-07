# 03 · 对标 2026 事实标准 harness：特性差距与建议

> 本文不是开发计划，也不改任何全局决策——它是一份**对标分析 + 选型建议**，供人决定 v1+ 排期时参考（排期结论已落地，见下方"排期更新"与 `02-development/00-overview.md §2`）。
>
> **状态更新（人 2026-06-07 已采纳）**：本文 §3 的 T1-A 会话持久化、T1-C Checkpoints、T1-B HITL 交互确认已升格为 **v1 必做切片 Slice 8 / 9 / 10**；§5 的跨会话全局记忆已上移 **v1**；§6 D-1 的 `forge add` 已写出详设 [`04-forge-add-incremental-regeneration.md`](./04-forge-add-incremental-regeneration.md)。路线图见 [`02-development/00-overview.md §2`](./02-development/00-overview.md)。其余项仍为待评估建议。
>
> **排期更新（人 2026-06-07 定向，本文建议已被采纳并细化排期）**：在三件套之外又排定了几项——① **跨会话记忆**紧接 Slice 8 记为 **Slice 8B**；② **Slice 9 Checkpoints + Slice 10 HITL = 一组"工具护栏对"相邻一起做**（共用 `before_tool` + Web 审批管道）；③ **§4 T2-G MCP 健康自检/状态面板升格为 Slice 11**（三件套+记忆后的首要方向）；④ **§3 T1-D 原生 Anthropic 双规范 + 推理流式升格为 Slice 12**，§6.4 具体方案已写出待签，见 [`05-llm-dual-spec-anthropic.md`](./05-llm-dual-spec-anthropic.md)；⑤ **§6 D-1 forge add / D-2 eval / D-3 presets 列入 Slice 13+ v1+ backlog**（forge add 仍为头号差异化，先做 Phase 1）。本文 §7 优先级表为当时建议，实际排期以 `02-development/00-overview.md §2` 为准。
> 立项定位 / 红线以 `01-project-plan.md` 为准；切片门禁与 backlog 以 `02-development/00-overview.md` 为准。本文凡触及 `01 §6` 红线的，都显式标注"守红线"。
>
> **基准时间**：2026-06。MVP 已走到 Slice 7（向导 + 范式 + MCP + Skills + 产物 Web/`/config` + 全局 rule + 可组合上下文压缩）。
> **判断口径**：一个特性"值不值得做"在本项目里有四条独立的尺子——① 是不是 2026 的事实标配；② 和"无框架 + own-your-code + 薄"契不契合；③ 触不触红线；④ 薄不薄（能否压进 spec 开关式可选模块、默认零痕迹）。四条都过才进 Tier 1。

---

## 1. 先认清 HarnessForge 已经站在哪

读 `00-research-and-feasibility.md §1.1` 列的"标准 harness 八件套"，对照现状，**这个项目已经覆盖了大半**，而且覆盖方式恰好是事实标准正在收敛的形态（薄循环 + MCP + Skills + 渐进披露 + 可扩展注册表）。这点要先讲清楚，否则容易把"已经做对的事"当成"还要补的洞"。

已经做到、且与事实标准同形的：

- **原生 function-calling 循环**（TAO/ReAct）——和 Codex/Claude Code 的核心循环是同一个原语：把工具结果喂回、累积上下文、直到模型不再调工具。`paradigms/agent.py` 154 行讲完，符合"模型越强 harness 越薄"的趋势。
- **MCP（stdio + 远程 HTTP/SSE）**——事实标准的工具层，已是 on/off 开关 + 运行期配置。
- **Agent Skills 开放标准**（`SKILL.md` 渐进披露）——这是 Anthropic 2025-12 开源、25+ 工具可移植的标准，HarnessForge 已对齐（Slice 6）。
- **全局 rule 文件注入**（`AGENTS.md`/`CLAUDE.md`/`.cursor/rules` 模式）——Slice 6B。
- **Plan / Ask 只读范式**——对齐 Cursor 三件套。
- **上下文压缩**（`truncate`/`summarize` + 可组合触发条件 + 可扩展注册表）——对位各家的 `/compact`，而且**可扩展这一层是领先的**：竞品的 compaction 大多是黑盒，这里是 `@register_strategy`/`@register_condition` 的 own-code。
- **可观测 + 预算**（JSONL trace + token/cost + 4 维 per-run 预算）——对位 `/cost` 与各家 telemetry。
- **多 profile + 角色路由**、**code-level 生命周期 hooks**、**写-only `.env` 助手**、**注册表自省**（`info` / `GET /registries`）。

**结论**：黄金路径上 HarnessForge 没有"功能洞"，它的洞在**人机协作的交互层（确认/会话/回滚）**和**新进入标配的安全/可信层**——这正是下面要分析的。

---

## 2. 能力对标表（2026 事实标准 × HarnessForge 现状）

把当前被 Claude Code / Codex CLI / Cursor / Cline / Gemini(Antigravity) CLI / Goose / OpenHands 共同确立的能力逐条对账。"标配"= 多数主流 harness 都默认带；"新兴"= 头部已有、正在扩散。

| # | 能力 | 谁有 / 成熟度 | HarnessForge 现状 | 差距判断 |
|---|------|---------------|-------------------|----------|
| 1 | 原生 function-calling 循环 | 全员 / 标配 | ✅ `paradigms/agent.py` | 无 |
| 2 | MCP（stdio + HTTP） | 全员 / 标配 | ✅ Slice 4 | 无 |
| 3 | Agent Skills（SKILL.md 渐进披露） | Claude/扩散中 / 新兴标准 | ✅ Slice 6 | 无 |
| 4 | 全局 rule / memory 文件 | 全员 / 标配 | ✅ Slice 6B（每轮注入） | 基本无（缺分层/嵌套 import、缺自动记忆，见 #15） |
| 5 | Plan mode | Cursor/Claude/Codex / 标配 | ✅ plan 范式（只读） | 缺 Plan→Build 切换（已登记 v1+） |
| 6 | 上下文压缩 `/compact` | 全员 / 标配 | ✅ 可组合 + 可扩展 | 无（且更可拥有） |
| 7 | 成本/预算可观测 | 全员 / 标配 | ✅ trace + 4 维预算 | 无 |
| 8 | 多 LLM profile / 角色路由 | 多数 / 常见 | ✅ Slice 2 | 无 |
| 9 | 生命周期 hooks | Claude（config shell hook）/ 标配 | ⚠️ 仅 code-level（`Hooks` 子类） | 缺 config 级 shell hook（已登记 v1+，见 §5） |
| 10 | **工具调用 HITL 交互确认**（allow/reject/always-allow） | 全员 / **标配** | ❌ 无内置（可 `before_tool` `raise` 自实现） | **明显缺口**（已登记 v1+）→ Tier 1 |
| 11 | **沙箱执行**（默认断网 + 限 cwd） | Codex/Cline/Claude / **标配** | ⚠️ 靠外置 Docker，产物进程内无 | 缺进程级护栏（守红线：不造沙箱，可生成 sandbox-aware wrapper）→ Tier 2 |
| 12 | **Checkpoints**（危险操作前自动快照 + 一键回滚） | Cline/Cursor/Codex / **标配** | ❌ 无 | **明显缺口**，强契合 → Tier 1 |
| 13 | **Subagent / 隔离子上下文** | Claude/扩散中 / 快速标配 | ❌ 无（supervisor multi-agent 已登记 v1+） | 缺口，正是已规划的"agent 即 tool" → Tier 2 |
| 14 | **会话持久化 / resume / `--continue`** | 全员 / **标配** | ❌ CLI 是单轮（"一问一答"） | **明显缺口（backlog 未登记）** → Tier 1 |
| 15 | 任务清单跟踪（TodoWrite 式） | Claude/MS Agent Framework / 常见 | ❌ 无 | 中等缺口（backlog 未登记）→ Tier 2 |
| 16 | 自定义 slash command | Claude/Codex / 常见 | ⚠️ 仅 `/skill-name` | 低优先 → Tier 3 |
| 17 | 原生 Anthropic Messages + thinking/effort | Claude/Codex 走各自原生 / 趋势 | ⚠️ 靠 OpenAI 兼容端点 / LiteLLM | 已登记 v1+（双规范可选模块）→ Tier 1/2 |
| 18 | 推理/思考流式 UX | 全员 / 趋势 | ❌ 无 | 已登记 v1+ → 随 #17 一起 |
| 19 | MCP 健康自检 / 状态面板 | Cursor/Claude / 常见 | ❌ 无 | 已登记 v1+ → Tier 2 |
| 20 | 后台/异步任务、云托管 multi-agent | Claude/Codex/MS / 企业向趋势 | ❌ 无 | **不建议**（云托管=红线） |
| 21 | Eval / 测试 harness | 部分 / 新兴 | ❌ 无（原 v2 提过） | **差异化机会** → §6 |
| 22 | 插件 / marketplace | Claude/Antigravity / 新兴 | ⚠️ 靠 MCP marketplace 文档 | 低优先 → Tier 3 |

**两条总结**：
1. 真正"已成标配、HarnessForge 还没有、且 backlog 也没登记"的只有三项：**#10 HITL 交互确认、#12 Checkpoints、#14 会话持久化/resume**。它们都薄、都不触红线、都强契合 own-your-code。这是最值得先做的一批。
2. 其余多数缺口（#9/#13/#17/#18/#19）其实**已经在 v1+ backlog 里**——本文的价值是给它们标出"哪些已经从'锦上添花'升级成'2026 标配'"，从而调整优先级。

---

## 3. Tier 1：高价值 + 强契合 + 不触红线（建议优先）

### T1-A · 会话持久化 + `run --continue` / 多轮 REPL（缺口 #14）

- **是什么**：把一次对话的 `messages` 落到本地（如 `traces/session-*.json` 或 `.harness/sessions/`），CLI 加 `run --continue` / `run --resume <id>`，或一个 `chat` 多轮 REPL；Web 端 session 落盘可续。
- **为什么**：单轮 `run` 是当前最违和的地方——所有事实标准 harness 都默认"接着上一轮聊 / 恢复昨天的会话"。这不是高级特性，是基础交互契约。
- **契合 & 薄**：纯 own-code，零新增依赖（`json` + 文件）；trace 基础设施已在，复用即可。core 增量预计 < 60 行，可做成默认行为而非 spec 开关。
- **红线**：无。**注意**：会话文件里**不得**落任何密钥（沿用 trace 的"只记角色/工具名/计数"纪律）。
- **落地草图**：`Trace` 旁加一个 `Session`（append messages → JSONL/JSON）；`cli.run` 读 `--continue` 时把历史 messages 预置进 paradigm 的初始 `messages`。范式签名已经接收 `messages` 雏形，改动面集中在 paradigms 的起始拼装处。

### T1-B · 工具调用 HITL 交互确认（缺口 #10，backlog 已登记，建议升格）

- **是什么**：内置一个可选的 `before_tool` 确认闸——交互式 TTY/Web 弹"allow / reject / always-allow（记住到本次会话或 `config.yaml`）"；**非交互/Web 公开面默认拒绝**。
- **为什么**：2026 已是标配（Codex/Claude/Cline 都有 allow-once/always-allow）。它把"危险工具默认关"从"全有或全无"升级成"用时逐次授权"，让 `shell`/写文件类工具**敢于默认预置但不默认放行**。
- **契合 & 薄**：扩展点已就位——`Hooks.before_tool` 已存在、文档明说"HITL 确认 live here"。只需提供一个**内置可选** `ConfirmHooks` 实现 + `config.yaml` 的 `tools.confirm: [tool names]`。default-off，零痕迹。
- **红线守住**：这是**护栏（威胁模型 A，可信但会手滑）**，不是"对代码所有者强制地板"——文档要继续讲明它不是安全边界（`01 §4`）；要锁死能力仍靠"生成期不编译进去"。**不要**借它把 `shell` 默认开（那会改 `01 §6` 全局口径，需人签字，已在 backlog 注明）。
- **落地草图**：`harness/hooks.py` 加 `class ConfirmHooks(Hooks)`；CLI 走 `typer.confirm`，Web 走一个 SSE 往返的 pending-approval 事件。

### T1-C · Checkpoints：危险工具前自动 git 快照 + 一键回滚（缺口 #12）

- **是什么**：当启用了写文件 / shell 类工具时，在执行**前**自动打一个 checkpoint（git stash/commit 到一个隐藏分支或 `.harness/checkpoints/`），提供 `<pkg> revert` / Web "撤销本次运行"。
- **为什么**：Cline/Cursor/Codex 把"自动快照 + 一键 undo"当成自主多文件编辑的**主要安全网**。HarnessForge 的产物默认就生成在 git 仓库里（生成器 `git init`），天然有底座；这是最便宜就能拿到的"可信但会手滑"护栏。
- **契合 & 薄**：和 own-your-code 完美契合（用户的产物本就是 git 仓库）；纯 own-code，调 `git` CLI 即可，零新增 Python 依赖。可做成 spec 开关 `tools.checkpoints: true`（或自动在检测到写类工具时启用）。
- **红线**：无。是护栏不是沙箱——它**回滚文件**，不**阻止**破坏（破坏防护交 Docker/容器，模型 B）。文档要写清这条边界。
- **落地草图**：复用 `before_tool`（与 T1-B 同一挂点）：高风险工具触发前 `git add -A && git commit -m "checkpoint" --quiet` 到影子 ref；`revert` 命令 `git restore` 到上一个 checkpoint。

### T1-D · 原生 Anthropic 双规范 client + reasoning 流式 UX（缺口 #17/#18，backlog 已登记，建议升格）

- **是什么**：`llm.py` 第二个 client 走 Anthropic Messages（顶层 `system` / content blocks / `tool_use`+`tool_result` / `effort` + adaptive thinking / Opus 4.7/4.8 禁 `temperature`·`top_p`·`top_k` / prompt caching / structured outputs），把 loop 的消息·工具格式映射进出；同时把 reasoning/thinking 阶段做成显式流式提示（避免"无反应等待"，这是 Slice 3 真实 LLM 验收时记下的 UX 坑）。spec 开关式**可选模块**，默认仍 OpenAI 兼容端点。
- **为什么**：推理模型（thinking/effort）已是 2026 主流，而"接 Claude 走 OpenAI 兼容端点 / LiteLLM"会丢掉 thinking、prompt caching、effort 这些一等能力。这从"以后可能要"正在变成"用户现在就要"。
- **契合 & 薄**：`llm.py` 已是 Protocol/适配层，第二个 client 是**加文件不改循环**，符合扩展点设计。default-off → 不启用零痕迹、`pyproject` 不进 `anthropic`。
- **红线**：**改 LLM API 面 = `CLAUDE.md §6.4`，实现前需人再签具体方案**（backlog 已注明）。务必保住"默认 provider-agnostic Chat Completions"不动，双规范是**可选第二条**而非替换。

---

## 4. Tier 2：中等价值 / 中等契合（建议排，但靠后）

### T2-E · Subagent = "agent 即 tool"（固定拓扑 supervisor，缺口 #13）

事实标准的 subagent（独立上下文窗 + 自己的工具/模型 + 只回摘要，不污染主会话）**恰好就是** backlog 里已规划的"supervisor multi-agent / agent 即 tool"。建议**就按这个事实标准的形态落地**：一个把"子 agent = 再跑一次 `run()`"包成普通工具的固定拓扑，opt-in，生成为 own-code。

- **务必**框成"一个具体、固定拓扑、生成为自有代码的模式"，**不是**通用编排框架——这是 `01 §6` 的红线分界（"≥2 个 agent"允许、"通用编排框架/动态图/DSL/运行期范式抽象层"禁止）。
- **薄做法**：`@register_paradigm` 或一个 `spawn_subagent(task, allowed_tools, model)` 工具，子 agent 用受限 registry + 独立 trace，返回摘要字符串。复用现有范式注册表与 tools 注册表，不引新抽象层。

### T2-F · 任务清单跟踪（TodoWrite 式，缺口 #15）

- 让 agent 能维护一个本轮/本会话的待办清单（一个内置可选工具 `update_todos` + 注入回系统提示）。长任务里它显著降低"跑偏/漏步"。Claude Code 的 TodoWrite、MS Agent Framework 的 TodoProvider 都验证了价值。
- **薄**：一个工具 + 一段 context 注入，零依赖，spec 开关或直接作为 `coding-assistant` preset 的预置工具。不触红线。

### T2-G · MCP 健康自检 / 状态面板（缺口 #19，backlog 已登记）

- `<pkg> mcp status` / 扩 `doctor` + `/config` 健康视图：probe 每个配置 server 连通性 + 工具计数 + 不可达标红 + 缺 Node 提示。**复用现有 `McpManager.errors`/`discovered`**，几乎是免费的。对齐 Cursor 的 MCP 面板。低风险、中价值。
- **部分已落地（2026-06-07，人定向 Scope 1）**：`GET /mcp/discover`（复用 `McpManager.discovered`，连通失败按 server 报 `error`）+ Web Tools 标签自动扫描，把已配置 server 的工具直接列出、勾选即入 allowlist（免手写 `<server>__<tool>` YAML），详见 `02-development/04-slice-3-product-web.md §4`。**剩余仍为 v1+**：`<pkg> mcp status`/`doctor` 健康视图、面板内增删/编辑 server（= `/config` 可改 `mcp`，触安全面）、热重连。

### T2-H · sandbox-aware shell 工具 wrapper（缺口 #11，谨慎）

- **不造沙箱**（红线），但可生成一个"默认断网 + 限定 cwd 子树"的 shell 工具**版本**：用 stdlib subprocess + 工作目录约束 + 可选 `unshare`/无网络环境变量，作为 Docker 之外的进程级护栏兜底。
- **必须框清**：这是 own-code 的"收窄的工具实现"，不是平台级强制沙箱；真隔离仍交 Docker/容器（模型 B）。否则会滑向"生产级权限/沙箱"红线。**建议先只出文档 + Docker 强化，代码 wrapper 排后**。

---

## 5. Tier 3：观望 / 谨慎（多数偏离定位或边际收益低）

- **config 级 shell hooks**（Claude Code/Cursor 风格：`config.yaml` 声明事件→shell 命令）——已登记 v1+，但**code-level `Hooks` 已覆盖同等扩展能力**，且引入"配置可间接 exec 任意命令"的新安全面，与 T1-B 的确认闸重叠。**结论：缓做**，除非有"非程序员用户也要配 hook"的明确诉求。
- **自定义 slash command**——薄但边际价值有限（产物是单 agent CLI，不是 IDE）。低优先。
- **跨会话长期记忆 / auto-memory**——是趋势，但容易把"薄 harness"做胖（需要存储、检索、淘汰策略），且与 RAG（v1+）部分重叠。**留 v2**，不要在没有真实多会话诉求前提早做。
- **插件 / marketplace**——偏生态托管，且与"不做在线 registry"口径相邻。靠"MCP marketplace 文档 + Composio 式 remote MCP"即可，不自建。

---

## 6. 只有"own-your-code 生成器"才能打的差异化（强烈建议至少投 1 个）

前面的 §3–§5 多数是"补齐别人也有的标配"。但 HarnessForge 有两个**竞品结构上做不到**的杠杆——因为竞品要么是托管平台、要么是你 import 的框架，**都不交付一份你拥有的代码**。这才是真正的护城河投资。

### D-1 · `forge add` / 增量再生成 + 模板升级（headline 差异化）

- **痛点**：own-your-code 的最大代价是"我生成后改了代码，现在想加 Web / MCP / 换范式，难道要重新生成、丢掉我的编辑？" 这是 `create-next-app` 生态用 **codemod / `add` 子命令**解决的问题，目前 HarnessForge 只在 backlog 里零散提过 `forge add/regenerate`。
- **建议**：把它升格为 v1+ 的**头号产品投资**——`harnessforge add web|mcp|skills|paradigm <name>` 做**结构轴的增量生成**（只新增"缺席"的能力代码，对已存在文件做 3-way merge / 仅插入扩展点），`harnessforge upgrade` 做模板版本升级（靠 `harness.spec.yaml` 里的 `version` 做 codemod）。
- **为什么是护城河**：它把"own-your-code 的代价"直接抵消掉，且**结构上锁死了竞品**——托管平台没有你的代码可 add，框架的"add" 只是装包不是改你的循环。这是把 `01 §4` 的"结构轴/能力天花板"做成可增量演进的产品化兑现。
- **难度诚实**：3-way merge 进用户已编辑的代码是这份建议里最难的（要处理冲突、要可预测）。可先从"纯新增、不碰已有文件"的安全子集起步（加一个新范式/新 MCP 块），把会改已有文件的留后。
- **详设**：完整设计（三种操作 add/upgrade/regenerate 的区分、`harness.spec.yaml` 快照作支点、扩展点锚点插入、分 Phase 落地、红线复核、待签决策）见 [`04-forge-add-incremental-regeneration.md`](./04-forge-add-incremental-regeneration.md)。

### D-2 · 内置极薄 eval / golden-task harness（spec 开关）

- 八件套里的"护栏与验证（Guardrails/Verification）"目前只覆盖到预算停止。把"**给你的 agent 生成一份可拥有的最小评测脚手架**"（一个 `evals/` 目录 + 一组 golden task + 一个跑分脚本，复用 mock + trace）做成 spec 开关，是**竞品普遍没有"可拥有 eval 代码"**的空位，且天然契合本项目"生成你拥有的薄代码"的卖点。薄、不触红线、原 v2 已提过——建议提前。

### D-3 · 更多 preset + spec 分享

- 目前只有 `coding-assistant`（实用）+ `rag-research`（骨架）+ 极薄 example。补 `deep-research` / `customer-support` / `data-analyst` 等 preset，是把"5 分钟到价值"做实的最低成本投资；spec 可分享（贴一段 YAML 即复刻）也强化 own-your-code。中等价值、低风险。

---

## 7. 建议优先级与一句话理由

| 优先级 | 项 | 一句话理由 |
|--------|----|-----------|
| **P0** | T1-A 会话持久化/resume | 单轮 `run` 是当前最违和的基础缺口，最薄、零依赖 |
| **P0** | T1-C Checkpoints | 产物本就是 git 仓库，几乎免费拿到事实标准的"自主编辑安全网" |
| **P1** | T1-B HITL 交互确认 | 标配且扩展点已就位，让危险工具敢"预置不放行" |
| **P1** | D-1 `forge add`/upgrade（安全子集先行） | **唯一的结构性护城河**，直接抵消 own-your-code 的代价 |
| **P2** | T1-D Anthropic 双规范 + reasoning 流式 | 推理模型已主流；但改 LLM 面需人签 `§6.4` |
| **P2** | D-2 eval harness（spec 开关） | 补齐"验证"支柱，且是可拥有 eval 的差异化空位 |
| **P3** | T2-E subagent、T2-F todo、T2-G mcp status | 中价值、薄、多数已在 backlog；按需排 |
| **观望** | T2-H sandbox wrapper、T3 全部 | 易触红线或边际收益低，先文档/缓做 |
| **不做** | #20 云托管/后台 multi-agent、通用编排框架、在线 registry、真沙箱、生产级权限 | `01 §6` 红线 |

> **给人的决策点（2026-06-07 已拍板，结论见下）**：① 三件套**已立为独立切片 Slice 8/9/10**，其中 **9+10 配对相邻一起做**、**跨会话记忆紧接为 Slice 8B**（人 2026-06-07）。② `forge add`/upgrade **确认为头号差异化、列入 Slice 13+ 先做 Phase 1 安全子集**（人 2026-06-07；详设 `04-forge-add`）。③ **Anthropic 双规范排为 Slice 12**，§6.4 具体方案**已写出待签** [`05-llm-dual-spec-anthropic.md`](./05-llm-dual-spec-anthropic.md)（人 2026-06-07）。④ 三件套+记忆后的首要方向**确认为 Slice 11 MCP 健康/管理**（人 2026-06-07）。

---

## 8. 红线复核（本文所有建议逐条对照 `01 §6`）

- 不引入任何 **agent 编排框架**（LangChain/LangGraph/ADK）——本文无一项需要。✅
- 不做**通用多 agent 编排框架 / 工作流 DSL / 动态图引擎 / 运行期范式抽象层**——T2-E 严格限定为"固定拓扑、own-code、agent 即 tool"，不越界。✅
- 不做**云托管 / 中心化配置托管**——#20 显式列为不做。✅
- 不做**生产级权限系统 / 内置真沙箱 / 在线 MCP registry**——T1-B/T1-C/T2-H 全部框为"护栏（威胁模型 A）"，强制隔离仍交 Docker（模型 B）；不自建 registry。✅
- 不让**密钥进 git / spec / trace / 日志**——T1-A 会话落盘特别标注沿用 trace 的脱敏纪律。✅
- **改 spec schema / LLM API 面**——T1-D 触 `§6.4`，已标"需人再签"；其余建议尽量走运行期 `config.yaml` 不动 spec 语义。✅

---

## 参考资料（2026-06 检索）

- Jonathan Fulton — *Inside the Agent Harness: How Codex and Claude Code Actually Work* (2026-04): <https://medium.com/jonathans-musings/inside-the-agent-harness-how-codex-and-claude-code-actually-work-63593e26c176>
- *Claude Code: Skills, Subagents, Hooks, Plugins, and Harnesses for Production Multi-Agent Workflows*: <https://boringbot.substack.com/p/claude-code-skills-subagents-hooks>
- Claude Code Docs — *Automate actions with hooks*: <https://code.claude.com/docs/en/hooks-guide>
- Firecrawl — *Claude Code vs Codex: Which AI Coding Agent Should You Use in 2026?*: <https://www.firecrawl.dev/blog/claude-code-vs-codex>
- Microsoft — *Agent Framework at BUILD 2026: Agent Harness, Hosted Agents, CodeAct, and more*: <https://devblogs.microsoft.com/agent-framework/microsoft-agent-framework-at-build-2026-announce/>
- Modal — *Best Code Execution Sandboxes for Coding Agents in 2026*: <https://modal.com/resources/best-code-execution-sandboxes-coding-agents>
- Tembo — *The 2026 Guide to Coding CLI Tools: 15 AI Agents Compared*: <https://www.tembo.io/blog/coding-cli-tools-comparison>
- AddyOsmani.com — *Agent Harness Engineering*: <https://addyosmani.com/blog/agent-harness-engineering/>
</content>
</invoke>
