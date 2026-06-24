# 02·16 - Slice 14:multi-agent 子代理(subagents / agent-as-tool)

> 目标:给生成产物补上「multi-agent」能力——**orchestrator-worker / agent-as-tool** 模式(2026 生产部署 #1,占比约 70%;成熟 harness 如 Claude Code `Task`、Anthropic Sub-agents、OpenAI agent-as-tool 都用它)。主 agent(就是默认 `agent` 范式)在**合适时机自行判断**,通过一个 `dispatch` 工具把独立子任务**并行**委派给作用域受限的 worker 子代理,每个 worker 在**独立上下文**里跑、回结构化结果,主 agent 负责综合。
>
> **形态结论(经人审确认)**:成熟 harness **不把 multi-agent 做成用户可选的「模式 / 范式」**,而是暴露成一个工具,由主 agent 自主触发。所以本切片**不新增范式、不改核心循环**——委派只是一个工具。
>
> **薄 / 红线**:零新增运行期依赖(stdlib `concurrent.futures` 线程池 + 自有薄内层循环);spec 开关式可选模块,**关闭零痕迹**(同 mcp/skills/memory);**固定拓扑、深度 1**(worker 永不持有 `dispatch`,不能再起 subagent);**严禁**任何 agent 编排框架 / 工作流 DSL / 动态图引擎。

## 0. 边界与口径

- **supervisor = 现有 `agent` 范式**:没有新范式,`spec.paradigms` 不变;supervisor 自主调用 `dispatch` 工具来委派。CLI/Web 无新模式开关。
- **上下文隔离 = 核心红利**:每个 worker 用**全新 history**(`[system=worker prompt, user=task]`),不带主对话上下文、不带全局 rules/memory/skills;只拿到自己的作用域工具与自己的任务文本。
- **作用域工具**:worker 的 `tools` 是它**自己的 allowlist**(已注册工具的子集),经 `registry.active_names(set(worker.tools), allow_high_risk=worker.allow_high_risk)` 过滤;**`dispatch` 始终被剔除**(深度 1,带兜底:`run_tool` 的 `allowed` 也不含 dispatch)。
- **并行 fan-out**:一次 `dispatch(tasks=[...])` 列多个 `{agent, task}` → `ThreadPoolExecutor(max_workers=max_parallel)` 并发;结果按**输入顺序**(非完成顺序)合并返回。单任务跳过线程池。
- **非交互 worker**:worker 线程不继承 HITL confirmer/asker 的 ContextVar(`confirm_tool` 无 confirmer = 放行;`ask` 无 asker = 「无人可问」降级),即 worker 不弹 HITL、不挂起。supervisor 自身的工具仍走 HITL。
- **预算 / runaway**:worker 花费经共享 `UsageLedger`(自带锁,线程安全)汇入 `.harness/usage.json`,受各 profile `cost_limit` 约束;worker 自身步数受 `max_steps` 上限;主回合受 supervisor `max_steps`/`cost_limit`。
- **trace 隔离**:worker 用 `Trace(enabled=False)`(不写父 JSONL,避免并发抢写),但挂共享 ledger 让花费照常累计。
- **关闭零痕迹**:`spec.subagents.enabled` 默认 `false` → 不渲染 `subagents.py`/`test_subagents.py`,config/prompts/cli/web 的所有片段全部门控 → 关掉时产物与无 subagents 生成逐字一致;无新增依赖。

## 1. 关键决策

- **① 形态 = opt-in spec 模块 + agent-as-tool**(非范式)。`dispatch` 是唯一新增工具,`risk=safe`。
- **② 并行优先**:首版即并行 fan-out(stdlib 线程池),不改薄核心循环(并行只在 `dispatch` 工具内部)。
- **③ 固定拓扑、深度 1**:worker 不能再起 subagent(规避无限委派 / runaway,符合生产建议「数量小、拓扑浅」)。
- **④ roster = 运行期活旋钮**:worker 名单 / 提示词 / 工具 / profile 在 `config.yaml subagents:` 里配置;spec 只决定模块有无(`subagents.enabled`)。空 roster = 移除 `dispatch` 工具。
- **⑤ 复用基建,不复制核心**:内层 worker 循环复用范式共享 plumbing(`generate`/`run_tool`/`assistant_message`),不 import 任何范式文件;client 按 worker `role` 经 `client_for_profile_name` 新建(mock 模式新建 `MockLLM`,避免并行共享可变状态)。

## 2. 交付物

### 新增模块(条件渲染)
- 产物 `harness/subagents.py`(仅 `spec.subagents.enabled` 时渲染)— `register_subagent_tools(config, registry, *, mock, ledger)` 注册 `dispatch` 工具 + 内层 `_run_subagent`(隔离上下文 / 作用域工具 / 深度 1)+ `subagents_section(config)`(系统提示注入)+ `dispatch` 批量并行工具。
- 产物 `tests/test_subagents.py`(仅启用时渲染)。

### spec / 生成器 / 向导
- `spec.py` — `class Subagents(enabled: bool=False)` + `HarnessSpec.subagents`(同 Mcp/Skills/Memory 风格;改 schema = spec 开关,已走 §6 人审)。
- `generator.py` — `CONDITIONAL_TEMPLATES` 加 `subagents.py.j2` / `test_subagents.py.j2`。
- 向导(CLI `cli_wizard.py` + Web `wizard/static/index.html`)— 能力组新增「启用多 agent 子代理」开关(**默认不勾**,属进阶能力);`build_spec` 写 `subagents.enabled`;Web JS 写 `spec.subagents`。

### 运行期配置
- 产物 `harness/config.py` — `SubagentDef(name, description, prompt, role="generation", tools=[], allow_high_risk=False, max_steps=12)` + `SubagentsConfig(max_parallel=4, agents=[])`(门控)+ `Config.subagents`。
- 产物 `config.yaml` — `subagents:` 块(门控,种 `researcher`/`writer` 两个示例 worker)+ `tools:` 里 `dispatch` allowlist 条目。

### 接线(全部门控)
- `harness/prompts.py` — `build_system_prompt` 在 memory 之后注入 `subagents_section(config)`(列出 roster + 「独立子任务一次性并行委派、你负责综合」)。
- `interfaces/cli.py` — `_setup_subagents(config, mock)` 接入 `run`/`chat`/`serve`;`info` 注册 `dispatch` 以便上报。
- `interfaces/web.py` — `create_app` 注册;`POST /config` + `PUT`(config-import)后**重绑** `dispatch`(闭包在注册期捕获 config,Budget 页改了 worker 模型/价后需重绑)。

## 3. 退出门禁

- [x] 黄金路径:subagents-enabled spec 生成 → `uv sync && pytest`(含 `test_subagents.py`)绿 → mock 跑通一次 function-calling(`test_golden_subagents_enabled_generates_and_smoke_passes`)。
- [x] 上下文隔离 + 作用域工具 + 深度 1:worker 系统提示 = 自己的 prompt(无 supervisor 上下文)、只被 offer 自己的工具、永不被 offer `dispatch`(产物 `test_subagents.py` 断言)。
- [x] 并行 fan-out:`dispatch` 多任务返回全部结果;worker 能执行自己的工具;未知 agent 报错不崩。
- [x] 成本汇入共享 ledger(mock);端到端:supervisor 调 `dispatch` → worker 离线跑 → 综合 final。
- [x] 无框架断言:生成的 `pyproject.toml` / `uv.lock` 不含 langchain/langgraph/adk。
- [x] 关闭零痕迹:`subagents.enabled=false` 不渲染 `subagents.py`、`config.yaml` 无 `subagents:`/`dispatch`、prompts/cli/web 逐字与无 subagents 一致;零新增依赖。
- [x] 大改动回归(动 `HarnessSpec` + 新模块 + 跨 ≥3 文件):全量 golden(示例 + preset + web/mcp/skills/memory/多范式/anthropic/wizard)+ Docker build/run mock + `uvx harnessmith new` 冒烟。
- [x] `ReadLints`:clean。

## 4. 留待 backlog(本切片明确不做)

- **并行内 HITL**:worker 当前非交互(并行 + 逐次确认体验复杂);需要时再设计经 ContextVar 传递 confirmer。
- **Web Subagents `/config` 页**:roster 当前经 `config.yaml` 编辑 + 重启 /(PUT)config-import 生效;可视化编辑 roster 留 backlog(MVP 不进 `_EDITABLE_FIELDS`)。
- **多级 / 嵌套拓扑、handoff、debate**:固定深度 1 之外的拓扑均不在范围(避免滑向通用编排框架红线)。
