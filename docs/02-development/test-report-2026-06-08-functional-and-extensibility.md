# 测试报告 · 功能 + 可扩展性(2026-06-08)

> 用本机 LiteLLM 真实 key 对 HarnessForge **已完成功能(Slice 0–8B)** 做的一次全面功能测试,
> 外加一次**开发者视角的可扩展性审计**(按 `AGENTS.md` 实际动手扩展各能力,看是否真的"方便自定义")。
>
> **本报告只记录发现,未改任何代码 / 模板**(人指示"暂不修改代码")。每条 finding 带复现证据 + 建议;
> `kind`∈{bug, unreasonable(可用但反直觉), improvement, doc}、`layer`∈{generator, product(产物模板), docs, spec}。
>
> 修复时建议优先看 §3 优先级清单与 §4 两条横切主题(一处改动可同时治多条)。

## 修复进展(2026-06-08,fix-test-report-findings)

本轮按 **P1–P5 代码 + P6 文档**修复(暂缓 P7/P8)。决策:未知名用**混合**策略(role/paradigm/strategy 解析失败 fail-fast;budget/context 条件、memory backend 未注册仅告警 + fail-open);新增 config 扩展加载点(`extensions:` + `hooks:`)解决 EXT-1/EXT-2。

| finding | 状态 | 落点 |
|---------|------|------|
| **PARA-1** | ✅ 已修 | `paradigms/__init__.py run_tool(allowed=...)` 执行期拒绝集合外调用;agent/plan/ask 传 `set(active)`;新增 `test_*_refuses_unoffered_high_tool_at_execution` |
| **PARA-2** | ✅ 已修 | plan/ask docstring + slice-5 L77 改为"未 offer **且**执行期拒绝(model-A 护栏)" |
| **PARA-3** | ✅ 已修 | 新增 scripted-mock 发未 offer high 工具的执行期断言 |
| **RT-2** | ✅ 已修 | `context.make_summarizer` 包装 compaction client → `trace.add_usage` + `compaction` 事件(计入预算);新增 `test_summarize_usage_is_traced_and_budgeted` |
| **BUD-1** | ✅ 已修 | `budget.check()` 未知名计入 `len(conditions)` 且 fail-open(AND 不再提前停);新增 `test_unknown_budget_condition_does_not_tighten_and` |
| **BUD-2** | ✅ 已修 | `extensions.check_config` 在 run/serve 启动期黄字告警;新增 `test_cli_run_warns_on_unknown_budget_condition` |
| **LOOP-1** | ✅ 已修 | `cli._validate_role` 与 `--mode` 对称报错(exit 2 列已知 role);新增 `test_cli_run_unknown_role_is_a_clean_error` |
| **LOOP-2** | ✅ 已修 | `check_config` 检出"配 max_cost 但 profile 无单价"告警 |
| **EXT-1 / EXT-2** | ✅ 已修 | 新增 `harness/extensions.py`(`import_extensions`/`load_hooks`/`check_config`)+ `config.extensions`/`config.hooks`;CLI run/chat/serve/info 与 web `create_app`/`_StreamHooks` 接线;AGENTS.md 补章;新增 `test_config_extensions_import_and_hooks_mount` |
| **RT-1 / DOC-PRESETS / SK-2 / MEM-2** | ✅ 已修 | 文档口径对齐(见 §3 表 + README/各 slice 文档) |

> 实现说明:RT-2 采用**计费包装器**(`_AccountingSummarizer`)而非给 strategy 签名加 `trace`/`profile` 形参——同样让摘要 token/cost 进 trace 与预算,但不改 strategy 契约(自定义 strategy 无需 `**kwargs`)。
> 未在本轮范围:P7(WEB-1/2、MCP-1/2、SK-1、SESS-1/2、MEM-1)、P8(LOOP-3/4、BUD-3/4、PARA-4、CLI-1/2)仍待后续。

> **延伸决策(2026-06-08,plan/ask 只读保证的边界)**:讨论确认 PARA-1 只下沉了"未 offer 工具的执行期拦截",**不**覆盖"自写工具默认 `risk="safe"`、忘标 high 的写工具会在 plan/ask 被执行"这一 footgun;其根因是 risk 标签正确性。人决策:**保持默认 `safe` 不变(选 C),仅文档点名**——AGENTS.md「Add a tool」+ README 明确"会改状态的自定义工具必须 `risk="high"`、plan/ask 只读=model-A 护栏非沙箱、硬隔离靠 HITL(Slice 9/10)/容器"。**MCP 注解(`readOnlyHint`)自动预分类:不做**(注解 optional + 不受信,只能省事不能当安全,`safe_tools` 仍是唯一权威白名单)。提示层("不要修改")已在 plan/ask 指令中,属软层、可降概率不可杜绝。

## 0. 测试环境与方法

- **真实 LLM**:本机 LiteLLM(OpenAI 兼容)`http://127.0.0.1:4000/v1`;生成模型 `qwen-plus`(tool-calling + 流式均确认),
  备选 `glm-4.6`/`mimo-v2.5-pro`,embedding `embedding-3`。
- **共享测试床**:从**当前模板**新生成的全功能产物 `generate/ft_full`(cli+web、mcp[fetch/ddg-search/git/desktop-commander]、
  skills、memory、sessions、paradigms agent/plan/ask、rules),`uv sync` + 产物 `pytest` + mock 自检全绿("Verified runnable"),
  已接 LiteLLM 跑通真实一轮。各测试项用**隔离的 `--config` 副本**(state 目录指向 `/tmp`)避免互相污染。
  > 注:仓库里旧的 `generate/my_harness` 是 **Slice 8/8B 之前**生成的陈旧产物(config 无 `sessions`/`memory` 块),
  > 不能代表当前实现——本轮一律用新建的 `ft_full`。
- **生成器基线**:`uv run pytest -m "not golden"` → **119 passed**。
- **方法**:多 agent 并行分区测试(每区真实 LLM 场景 + 文件核查 + 复现证据)。
  > **执行说明**:并行 sweep 跑到后段触发账号 **session limit**(`presets`/`wizard`/`footprint-thin-security`/`triage` 四个 agent 失败),
  > 这 3 个功能区 + 汇总/三角验证由主流程**改为本地 inline 重做**并已补齐(结果见下),不影响覆盖完整性。

## 1. 覆盖总览

| 区域 | 方式 | 结论 | 关键 finding |
|------|------|------|------|
| 核心循环 / trace / `run` | 真实 LLM | 核心正确 | LOOP-1..4 |
| 范式 agent/plan/ask + 注册表 | 真实 LLM + in-proc | **1 个 high bug** | PARA-1..4 |
| 多 profile 角色路由 + context 策略 | 真实 LLM + in-proc | 路由正确,2 问题 | RT-1(doc)/RT-2(bug) |
| MCP stdio(fetch/ddg/git)| 真实 LLM | 全通过 | MCP-1/2(improve) |
| Skills + 全局 rule 注入 | 真实 LLM | 全通过 | SK-1/SK-2 |
| 会话持久化 + chat REPL | 真实 LLM | 全通过 | SESS-1/2 |
| 跨会话记忆(8B)| 真实 LLM + in-proc | 全通过 | MEM-1/2 |
| Web(FastAPI+SSE+/config+sessions+memory)| in-proc TestClient + 真实 LLM | 全通过 | WEB-1/2 |
| 预算条件(per-run)| 真实 LLM + in-proc | 计费/触发正确 | BUD-1..4 |
| 生成器 CLI / doctor / 报错 | inline | 全通过 | CLI-1/2 |
| 薄 / 无框架 / 关闭零痕迹 / 密钥卫生 | inline | **全部达标** | (见 §2.6,无问题) |
| preset(coding-assistant)金路径 | inline 真实 LLM | 全通过 | DOC-PRESETS |
| wizard 单页生成向导 | inline TestClient | 通过 | (结构-only,正常) |
| **可扩展性审计** | inline 真实扩展 | **整体顺手** | EXT-1/EXT-2(见 §3 Part B)|

**一句话结论**:产物在真实 LLM 下端到端可用、生成器报错友好、薄/无框架/密钥卫生全部达标;
可扩展性确实"配置即生成 + `@register_*` 一致注册表",自定义 tool/paradigm 等**不改 `loop.py`** 即可跑通。
最该修的是 **plan/ask 只读保证在执行期可被绕过(PARA-1)** 以及**一类"未注册/拼错的名字在运行期被静默忽略"的护栏弱化(BUD-1/BUD-2/LOOP-1,见 §4)**。

---

## 2. 功能测试发现(Part A)

### 2.1 核心循环 / trace / CLI `run`(真实 qwen-plus)

多步工具调用、工具报错回灌自纠、`max_steps` 停止、`--stream`、死端点/未知模型的干净报错(exit 1 无 traceback)、
`--mode bogus`(exit 2)均正确;7 类 trace 事件结构完好。`cost_usd=0` 纯因默认 profile 未设单价(加价后计费正确)。

| id | kind/sev | layer | 标题 | 证据 / 建议 |
|----|----------|-------|------|------|
| **LOOP-1** | unreasonable / **medium** | product | `--role <未知>` 静默回落默认 profile,而 `--mode <未知>` 报错——两个几乎一样的笔误行为相反 | `run "hi" --role bogus` → exit 0 正常跑(用了 default);`--mode bogus` → exit 2。`Config.profile_for` 中 `roles.get(role)` 落空时因 `llms` 非空返回 `llms[0]`,不抛错;但"role 映射存在却指向不存在 profile"又会 `ConfigError`。建议:非默认 role 名未配置时抛错并列出已知 role(与 `--mode` 对称) |
| LOOP-2 | doc / low | product | 默认无单价 → `cost` 恒 `$0`,配了 `max_cost` 也永不触发且无提示 | 加 `input/output_cost_per_million` 后 `cost=$0.0025`。建议 `info`/preflight 检出"配了 max_cost 但 profile 无单价 → 永不触发"时给一行提示 |
| LOOP-3 | improvement / low | product | token/cost 预算是"响应后"检查,单响应一轮无法拦截、必定 overshoot 一个完整响应(off-by-one)| `max_tokens=200` 一轮答完 `total_tokens=314` 未触发(agent.py 已注明)。建议文档强调或每次 `llm_response` 后补一次检查 |
| LOOP-4 | improvement / low | product | 失败的 run 只写 `error` 事件、不写 `run_end`,trace 终止符不统一 | 死端点 trace 末尾是 `{"event":"error",...}` 无 `run_end`。建议:失败也补一条 `run_end(stop_reason="error")`,或在 trace.py 注明"以 run_end 或 error 结尾" |

### 2.2 范式 agent / plan / ask + 注册表

`info` 列注册/选中/默认正确;`--mode bogus` exit 2;省略 `--mode` 走 `config.paradigms.default`(改 default 后跟随);
plan 产只读编号计划、ask 直接作答;agent 提供全部工具、plan/ask 从 **offered schema** 里剔除 high-risk 工具。
自定义范式在 in-process 与**文档路径**下均跑通(见 §3 Part B)。

| id | kind/sev | layer | 标题 | 证据 / 建议 |
|----|----------|-------|------|------|
| **PARA-1** | **bug** / **high** | product | **plan/ask 的"只读"可在执行期被绕过**:模型若 hallucinate 一个未被 offer 的 high-risk 工具,loop 仍会执行并改状态 | plan/ask 只在 `active_names(..., allow_high_risk=False)` 层面**不 offer** high 工具;但执行路径 `paradigms.run_tool → registry.call` **只检查工具是否注册**,不校验 active/risk。真实 plan run 里 qwen-plus 真的发出了未被 offer 的 `memory_write`(仅因猜错参数名失败);in-proc 用正确参数经同一 `run_tool` 路径成功把 `memory.md` 覆写为 "INJECTED BY PLAN MODE"。建议把各范式已算好的 `active` 集合传入 `run_tool`,执行前拒绝集合外调用(返回 ERROR observation,保留自纠),把只读契约下沉到执行期 |
| PARA-2 | doc / medium | docs | 文档把 plan/ask 说成"cannot mutate anything / 未执行",强于运行期实际保证 | `plan.py`/`ask.py` docstring "a plan run cannot mutate anything"、slice 06 第 77 行"高风险工具…未被 offer / **未执行**"。实际只有"未 offer"成立(见 PARA-1)。同文件又有诚实表述"model-A guardrail, not an adversarial sandbox"——前后矛盾。建议:修 PARA-1 后该表述才成立;否则改为"未 offer(model-A 护栏),非硬沙箱",删 slice 06 的"未执行" |
| PARA-3 | improvement / medium | product | `test_plan_mode_is_read_only` 给假信心——只覆盖"offered schema"路径 | 测试用 MockLLM(只会调被 offer 的工具)断言 `danger_write not in calls`,**永远测不到** PARA-1 的执行期漏洞。建议加一条:强制 MockLLM 发出**未被 offer 的 high 工具**调用,断言其不被执行 |
| PARA-4 | improvement / low | product | 非法 `--mode` 会先拉起 MCP 子进程再被拒 | `cli.py run()` 里 `_start_mcp`/`_setup_memory` 在 `run_loop`(校验 mode)之前。`run --mode bogus` 会先启 fetch/ddg/git 再 exit 2。建议:`load_config` 后立刻校验 mode∈enabled,再启 MCP |

### 2.3 多 profile 角色路由 + context 策略

第二 profile(`compactor`/glm-4.6)绑 `roles.compaction` 确实只用于摘要、generation 仍走 qwen-plus(in-proc spy + trace 双证);
四种策略(summarize/truncate/none/未知静默 no-op)行为符合设计;`info` 正确列注册表并对"选中但未注册"标 `!`。

| id | kind/sev | layer | 标题 | 证据 / 建议 |
|----|----------|-------|------|------|
| RT-1 | doc / medium | docs | 文档称"summarize 缺 compaction 角色回落 truncate",实际用 generation profile 做摘要(不回落)| `01-project-plan.md` L52 / `00-overview.md` L94 / slice-7 L130 均称回落 truncate;但 `profile_for('compaction')` 未配时回落首个 profile,故 `summarizer` 永不为 None,`context.py` 的 truncate 兜底实际不触发——用户得到的是"用 generation 模型真摘要"(额外成本)。wizard 注解(slice-7 L81/82)反而写对了。建议:改这三处口径与 wizard 一致 |
| **RT-2** | **bug** / **medium** | product | **compaction(摘要)调用的 token/cost 既不写 trace 也不计入预算** | summarize 触发时 `summarizer.complete(...)` 的 Usage 被丢弃:无 `trace.add_usage`、无 trace 事件。后果:① CLI 打印的 totals 与 cost/token 预算**少算**摘要开销(in-proc:generation+compaction 各 1 次,但 totals 只含 generation);② trace 里看不到第二个模型被调过。trace.py 自称"累计以便执行 cost 预算",而摘要开销逃逸。建议:把摘要响应 usage 计入 trace totals 并补一条 `compaction` 事件 |

### 2.4 MCP stdio 基线(fetch / ddg-search / git)

真实 LLM 下全通过:`fetch__fetch` 取回 example.com、`ddg-search__search` 返回 10 条真实结果、`git__git_status` 对 ft_full 仓库生效;
allowlist 收窄正确(关掉 `fetch__fetch` 后模型拿不到;`git_commit` 等写工具/desktop-commander 从不注册);
无启用工具的 desktop-commander 保持休眠(不启进程);`run` 路径 `mcp_manager.close()` 可靠回收子进程。

| id | kind/sev | layer | 标题 | 证据 / 建议 |
|----|----------|-------|------|------|
| MCP-1 | improvement / low | product | MCP server 串行连接,启动延迟随数量线性叠加 | `_main()` 逐个 `await wait_for(self._connect(...))`;3 个 stdio server ~2.7s,每次 `run`/`serve` 都付。建议 `asyncio.gather` 并发连接(各自包 wait_for+try 以保持失败隔离)|
| MCP-2 | improvement / low | product | `serve` 不 close MCP manager → 关停时遗留 stdio 子进程 | `serve()` 丢弃 `_start_mcp` 返回值,uvicorn 退出/被 kill 时后台线程死掉、AsyncExitStack 不跑,uvx/npx 子进程被孤儿化。**实测主机上有其他测试 serve 留下的 8h/1 天龄 mcp-server 孤儿进程**。建议:serve 保留 manager 并在 shutdown/atexit 调 close(),或把子进程放进独立进程组退出时整组 SIGTERM |

### 2.5 Skills + 全局 rule 注入

真实 LLM 全通过:example-skill 的 name+description 注入系统提示;`/example-skill` 展开整段 SKILL.md;`read_skill` 工具可读正文;
绝对路径 RULES.md 每轮注入并被遵守;缺失 rule 文件静默跳过;**根目录 CLAUDE.md 自动识别注入**、而 AGENTS.md 正确地不自动注入;
`disable-model-invocation` 技能从 L1 排除但可经 `/name`/read_skill 触达。

| id | kind/sev | layer | 标题 | 证据 / 建议 |
|----|----------|-------|------|------|
| SK-1 | unreasonable / low | product | `/` 斜杠命令约定与"以 `/` 开头的正常提问(如文件路径)"冲突,误报 "no skill named" | `/etc/hosts is what kind of file?` → stderr `ERROR: no skill named 'etc/hosts'`(提问仍照常作答,但有困惑性报错;且 `/` 原样进 prompt 会诱导模型把输入当命令)。建议 `_expand_skill` 仅当首 token 命中已发现技能名(或不含路径分隔符)时才拦截 |
| SK-2 | doc / low | docs | 产物 README 未提"根 CLAUDE.md 自动注入"(仅 AGENTS.md 提了),"AGENTS.md / CLAUDE.md"并列让人以为行为对等 | `prompts.py` `_CONVENTION_RULE_FILES=('CLAUDE.md',)`;AGENTS.md.j2 L80-83 写清,README.md.j2 没写。建议 README 规则段加一句:根 CLAUDE.md 未列也自动注入、AGENTS.md 不会 |

### 2.6 会话持久化 + chat REPL / 跨会话记忆(8B)

会话:单 `run` 写 `<id>.json`(只存正文、不存 system、**全程无密钥**——store/traces grep 不到 `sk-`);`--continue`/`--resume` 正确;
piped `chat` 多轮串联 + 跨 `run`/`chat` 续聊;mode 入库;`--resume ../evil` 被收敛进 store 目录(防穿越)。
记忆:`memory_append` 写入、新会话注入命中("teal")、`memory show/path/clear` 正常、即便被要求也不会把真实 key 写进 `memory.md`;
关闭 memory 时**零痕迹**(不渲染 memory.py/test、config 无 memory 块)。

| id | kind/sev | layer | 标题 | 证据 / 建议 |
|----|----------|-------|------|------|
| SESS-1 | improvement / low | product | `chat` REPL 退出时不打印续聊提示(只有 `run` 打印 `resume: run --resume <id>`)| `chat` 仅开场 banner 出现一次 id,逐轮 summary 无 id/无续聊提示。建议退出时补一行 `resume: chat --continue / run --resume <id>` |
| SESS-2 | unreasonable / low | product | `--resume <拼错的 id>` 静默新建同名会话,无"未找到"提示 | `run --resume doesnotexist123` → 直接建 `doesnotexist123.json`。`--continue` 静默可接受;但显式 `--resume` 笔误应提示"无该会话,已新建"。建议:resume_id 给定但文件不存在时,stderr 一行提示(保留新建行为) |
| MEM-1 | unreasonable / low | product | `memory <未知动作>` 静默当 `show`(exit 0)| `memory delete`/`memory clera` → 打印记忆且 exit 0,看不出"想清空但没清"。建议:动作不在 {show,clear,path} 时 stderr 报错 + exit 2(与同函数里"未知 backend"报错一致)|
| MEM-2 | doc / low | docs | 产物 README 记忆段漏了 `memory path` 子命令 | README 只列 `show`/`clear`,实际/slice 文档/`--help` 都有 `path`。建议 README 补 `memory path` |

### 2.7 Web 界面(FastAPI + SSE + /config + sessions + memory)

in-proc TestClient + 真实 qwen-plus 全通过:`GET /` 返回 HTML;SSE `/chat` 真实逐 token 流式(事件 `session/title/token/step/tool_call/tool_result/final/error`);
`GET /config` 不含密钥值、`POST /config` 改 `prompts.system` 下一轮即生效、非法 patch 400;sessions 增删改查 + rename 未知 404 + 删除幂等 + 路径穿越收敛;
`/memory` 读写删 + read_only 拒写 400;`/registries` 暴露 paradigms/strategies/conditions/budget/memory;`/env` 写 dummy 不回显值;
首条消息自动起标题(随请求语言,中文 prompt 给中文标题)且不重复起标题;UI 默认英、EN/中文切换持久化 localStorage。

| id | kind/sev | layer | 标题 | 证据 / 建议 |
|----|----------|-------|------|------|
| WEB-1 | unreasonable / low | product | `session` SSE 事件在 run 成功前就发,首条消息失败后 UI 留一个磁盘/侧栏都不存在的"幽灵会话 id" | 失败 first turn:SSE 先 `session{id}` 后 `error`,但只有成功路径才 `save()`;前端 error handler 不重置 `currentSession`。会自愈(下条消息复用该 id 才落盘),但中间态不一致。建议:成功保存后才发 `session`,或前端 error 时若未收到 `final` 则重置 currentSession |
| WEB-2 | unreasonable / low | product | 一次 LLM 失败在聊天里显示**两条**error(`where:llm` + `where:run`)| `_StreamHooks.on_error` 推一条,worker 外层 except 又推一条同源错误,前端各打印一次。建议:二选一去重 |

### 2.8 预算条件(per-run)

真实 LLM + in-proc 全跑通:`max_steps=1` 一轮停(`stop_reason=max_steps`);`max_tokens` 停(off-by-one);
**cost 路径完整验证**(设单价后 `cost_usd>0`、math 正确、`max_cost` 触发);`combine: or` 首条即停 / `and` 全中才停;
tumbling 窗口语义正确;自定义 `@register_budget_condition` 进 `BUDGET_CONDITIONS`/`info` 并能停 run。AGENTS.md 预算段准确。

| id | kind/sev | layer | 标题 | 证据 / 建议 |
|----|----------|-------|------|------|
| **BUD-1** | **bug** / **medium** | product | `combine: and` 静默丢弃"未注册/拼错"的条件名 → AND 比预期**更早**触发(向不安全方向偏)| `check()` 里 `evaluated` 只对已注册条件 +1,`and` 门是 `len(fired) < evaluated`。`{max_steps, max_typoo}` 的 AND 退化成只看 `max_steps`,提前停。docstring 只说"未知名被跳过",没说这会改变 AND 语义。建议:load 时校验条件名(同其它 config 错误那样报错),或把未知名计入 `evaluated` 且视为未满足(fail-open)|
| **BUD-2** | unreasonable / **medium** | product | 拼错的预算条件在**运行期**静默变 no-op(无警告),护栏悄悄消失 | `info` 会标 `! max_stpes — selected but NOT registered`,但 `run` 不会:只配了拼错条件时整轮**无预算**且无提示。建议:`run`/`serve` 复用 `info` 的诊断,运行期对未知条件名给警告或严格模式下报错 |
| BUD-3 | improvement / low | product | `combine: or` 多条同时命中时,`stop_reason` 只取首条但 message 列出全部,二者不一致 | `stop_reason='max_steps'` 而 message `'max_steps >= 1.0 / max_tokens >= 1.0'`。建议二选一 |
| BUD-4 | improvement / low | product | 阈值在停止消息里恒以浮点显示(`max_steps >= 1.0`)| `threshold` 类型 float。建议显示时去掉整数的 `.0`,或 `BudgetConditionSpec` 接受 `int|float` |

### 2.9 生成器 CLI / doctor / 报错(inline)

`doctor`(uv 0.11.7 + network ok)、参数互斥(both/neither → exit 2)、未知 preset / bogus `--mcp-server`(exit 2 列可选)、
各类非法 spec(坏 slug / extra 字段 / 空 paradigms / role 指向未知 profile / 文件缺失 / 非映射 → 均 exit 2 + 清晰信息)、
`--no-verify --no-git` 仍产 `uv.lock`+`requirements.txt`、重跑非空目录拒覆盖(exit 1)、`--mcp-server` 遇 `mcp.enabled=false` 黄字忽略、
帮助文本准确——**全部通过**。

| id | kind/sev | layer | 标题 | 证据 / 建议 |
|----|----------|-------|------|------|
| CLI-1 | unreasonable / low | generator | "Invalid spec:" 前缀对"未知 preset / bogus mcp-server"不准确(spec 可能完全合法甚至无 spec)| `except (... PresetNotFoundError, CatalogError)` 共用 `Invalid spec:` 前缀。建议拆分或改中性 `Error:` 前缀 |
| CLI-2 | improvement / low | generator | 原始 pydantic `ValidationError` 文本(errors.pydantic.dev URL + 整个 input dump)直接抛给用户 | role 校验失败会打印 `input_value={...}` + 文档 URL。建议格式化成 `field: message`,详情藏到 verbose |

### 2.10 薄 / 无框架 / 关闭零痕迹 / 密钥卫生(inline,全部达标)

- **无框架**:minimal 与 full 的 `pyproject.toml`/`uv.lock`/`requirements.txt` **均不含** langchain/langgraph/adk。
- **关闭即零依赖**:minimal(关 web/mcp/skills/memory)依赖仅 `openai/pydantic/pydantic-settings/pyyaml/typer` 5 个;
  `fastapi`/`uvicorn`/`mcp` 只出现在 full。
- **关闭即零文件**:minimal 不渲染 `web.py`/`mcp.py`/`skills.py`/`memory.py`/`paradigms/{plan,ask}.py`(只 `agent.py`)。
  (`context.py`/`session.py` 仍在 minimal——属当前核心设计:context 默认 summarize、sessions 默认开。)
- **薄**:核心循环 `loop.py`(69)+ `paradigms/agent.py`(159)= **228 行**,落在文档"150–300"区间内;
  minimal 总 src 2122 行、full 3838 行。
- **密钥卫生**:bed `.env` 未被 git 跟踪、在 `.gitignore`、真实 key 不在任何被跟踪文件;`config.yaml` 只存 env **名**。

> 此区**无 finding**(全部达标),仅记录数据备查。

### 2.11 preset 金路径(coding-assistant)+ wizard(inline)

- **coding-assistant**:`harnessforge new --preset` 走完 `uv sync`+产物 pytest+mock(exit 0);接 LiteLLM 真实一轮 `256/4=64`(调 calculator);
  config 预填 MCP 基线正确(fetch/git_status 开、git_commit/desktop-commander 关);RULES.md 生成并注入;pyproject 无框架——**通过**。
- **wizard**:`GET /` 返回 17KB 表单,路由 `/spec`、`/generate`、`/meta`;只采集结构项(paradigms/web/mcp),行为字段烤默认——**符合设计**。

| id | kind/sev | layer | 标题 | 证据 / 建议 |
|----|----------|-------|------|------|
| DOC-PRESETS | doc / low | docs | 多处文档声称存在 `rag-research`(骨架)/ 极薄 `example` preset,实际**只有 `coding-assistant`** | `ls harnessforge/presets/` 仅 `coding-assistant`;但 `01-project-plan.md` L49/L133、`00-overview.md` L119、`03-feature-landscape.md` L157 都把 rag-research/example 当已有 preset 写。建议:统一为"现有 preset = coding-assistant",其余标注为 backlog(`03 §6 D-3` 已列为待补)|

---

## 3. 可扩展性审计(Part B,开发者视角)

**方法**:把自己当新接手的开发者,**严格照 `AGENTS.md` 动手**扩展每个能力(用 bed 真实跑,改完即还原),评判"是否真的方便"。

### 3.1 逐项结论(✓=照文档跑通)

| 扩展点 | 路径 | 结果 | 备注 |
|--------|------|------|------|
| **自定义 tool** | 在 `tools.py` 加 `@registry.tool(...)` + config 启用 | ✓ 真实跑通 | 加 `word_count` → 模型实际调用、答 "6 words"、trace 见 `name: word_count`;**不动 loop.py**;AGENTS.md 准确 |
| **自定义 paradigm** | 建 `paradigms/mymode.py` + `__init__.py` 加 `from . import mymode` + config enable | ✓ 跑通 | `run --mode mymode` → `echo: hello world`;`info` 列出 `mymode (selected)`;AGENTS.md 准确 |
| **自定义 budget 条件** | `@register_budget_condition` | ✓(sweep 已证)| 进 `BUDGET_CONDITIONS`/`info`,能停 run |
| **自定义 memory 后端** | `@register_memory` 子类 | ✓(sweep 已证)| 进 `info` memory backends;契约 `recall/record` + 可选生命周期钩子 |
| **自定义 context 策略/条件** | `@register_strategy`/`@register_condition` | ✓ 注册+发现 | 未导入时 `info` 明确标 `! head_tail — selected but NOT registered (import its module?)` |
| **加 MCP server** | 纯 `config.yaml` 贴 server 块 | ✓ | schema 接受任意 server 块、`info` 正常加载;与已验证的启动/allowlist 同一路径 |
| **换模型 / provider** | 改 `config.yaml` profile base_url | ✓(路由区已证)| provider-agnostic |
| **加 LLM profile + role** | 纯 config | ✓(路由区已证)| `roles.compaction` 真实生效 |
| **加 Skill** | 放 `skills/<name>/SKILL.md` | ✓(skills 区已证)| 渐进披露 |
| **全局 rule** | config `prompts.rules_files` / 根 CLAUDE.md | ✓(skills 区已证)| 运行期热改 |
| **Hook(before_tool 等)** | 子类 `Hooks` | ⚠ 见 EXT-1 | 代码里能用,但 **CLI/Web/config 无法挂载** |

**整体评价(正面)**:`@register_*` 注册表在 tool/paradigm/context/budget/memory 上**形状一致**(写函数→装饰器→config 按名选),
全部经 `info` + `GET /registries`(+ Web 各 tab)**可发现**、运行期 config 可选;自定义 tool/paradigm **确认无需改 `loop.py`**。
这就是项目主卖点("own your code + 薄注册表"),**确实落地且顺手**。

### 3.2 可扩展性 finding

| id | kind/sev | layer | 标题 | 证据 / 建议 |
|----|----------|-------|------|------|
| **EXT-1** | improvement / **medium** | product+docs | **Hook 是唯一无法在运行期挂载的扩展点**:只能改代码 | `cli.py` 的 `run`/`chat` 调 `run_loop(...)` **不传 hooks**(用默认 `Hooks()`);`web.py` 同理。AGENTS.md 写"pass an instance into run(..., hooks=AuditHooks())",但没说 CLI/Web 根本没暴露入口——要用自定义 hook 必须改 `cli.py`/`web.py` 或自写驱动。鉴于 Hook 正是 logging/guardrail/redaction/HITL 的官方落点(且 Slice 9/10 计划在 `before_tool` 上建 checkpoints+HITL),这个缺口值得补:在 config 里声明一个"hooks 模块/类路径"由 CLI/Web 加载,或至少在 AGENTS.md 注明"CLI 默认不挂 hook,需改 cli.py 第 ~158 行" |
| EXT-2 | improvement / low | docs+product | 独立扩展模块"导入以触发注册"缺统一落点(paradigm 除外)| 改内置注册表文件(`tools.py`/`budget.py`/`context.py`/`memory.py`)天然被导入、无坑;但若放**独立模块**,只有 paradigm 有明确落点(`paradigms/__init__.py` 加 import),context/budget/memory 的"imported at startup"没说在哪导。已被 `info`/`/registries` 的 `! ... (import its module?)` 兜底(能发现错误),但仍需手找地方导。建议:提供一个约定的"用户扩展加载点"(如 config `extensions: [module...]` 在启动时 import),或 AGENTS.md 对每类注册表点明具体导入位置 |

> 关联:EXT-2 的"`info` 能发现、`run` 静默忽略"与 §2.8 BUD-2、§2.3 未知 context 条件、§2.1 LOOP-1 同根(见 §4)。

---

## 4. 两条横切主题(一处改可治多条)

1. **"未注册 / 拼错 / 未配置的名字在运行期被静默忽略",削弱护栏。**
   涉及:`LOOP-1`(未知 --role 静默回落)、`BUD-1`(AND 丢未知条件 → 提前停)、`BUD-2`(拼错预算条件 → 整轮无预算)、未知 context 条件被跳过、`EXT-2`(未导入的扩展)。
   `info`/`/registries` 已有诊断,但 `run`/`serve`/`profile_for` 不复用。
   **统一修法**:在 `load_config` 时校验所有"按名引用"(roles 目标、budget/context 条件名、paradigm 名、memory backend)是否已注册/可解析,
   不通过则 fail-fast(或非严格模式下运行期打一行警告)。
2. **安全/护栏在"offer 期 / 配置期"成立,但"执行期"不成立(防御纵深缺一层)。**
   涉及:`PARA-1`(plan/ask 只读靠不 offer,执行期不拦)、`BUD-1`(AND 语义被未知名改写)。
   **统一修法**:把"当前允许集合"下沉到执行边界——`run_tool`/`registry.call` 校验工具在本范式 active 集合内;预算把未知条件视为"未满足"。

## 5. 优先级清单(我的三角验证后)

| # | id | 为什么排这 |
|---|----|------|
| P1 | **PARA-1** | 唯一 high bug:plan/ask "只读"这一对外承诺可被执行期绕过(真实模型已触发);连带 PARA-2/3 |
| P2 | **RT-2** | 摘要开销对 trace 与 cost/token 预算**不可见**——计费/可观测正确性 |
| P3 | **BUD-1 + BUD-2** | 护栏被静默弱化/移除(§4 主题①+②),安全方向错误 |
| P4 | **LOOP-1** | 高频笔误(--role)静默走错 profile,与 --mode 不对称 |
| P5 | **EXT-1** | Hook 无法运行期挂载——直接影响即将到来的 Slice 9/10(checkpoints/HITL 都在 before_tool 上) |
| P6 | RT-1 / DOC-PRESETS / SK-2 / MEM-2 / LOOP-2 / PARA-2 | 文档与实现对齐(一批 doc 修正)|
| P7 | WEB-1 / WEB-2 / MCP-2 / SK-1 / SESS-2 / MEM-1 | UX 打磨 + 资源泄漏(MCP-2 孤儿进程)|
| P8 | LOOP-3/4 / BUD-3/4 / PARA-4 / CLI-1/2 / EXT-2 / SESS-1 | 低优雅化 |

## 6. 未覆盖 / 受限(诚实记录)

- **远程 MCP(Streamable HTTP)传输**未测(bed 只有 stdio server);`mcp.py` 的 `url`/`auth_env` 路径未走。
- **真实 LLM 触发的上下文压缩(192k token)**未端到端跑(成本),summarize 走的是 in-proc `fit_context`/低 `max_turns` 触发(同一代码路径)。
- **Docker `docker build`/`docker run`** 本轮未实跑(磁盘紧 + golden 已覆盖),只核查了 Dockerfile/.dockerignore/.devcontainer 在场。
- **Web 真浏览器端**(EventSource/localStorage/侧栏内联改名删)只读 `web_index.html` + TestClient 推断,未驱动真实浏览器。
- **并发写**(同一 session/memory 多进程)未测(thin 设计、单租户,文档已注明)。
- PARA-1 的真实触发是**概率性**(模型 hallucinate 未 offer 的 high 工具);执行期漏洞已 in-proc 确定性复现,但真实命中频率未统计。
- 受 **session limit** 影响,sweep 的并行三角验证 agent 未跑;本报告的去重/优先级为主流程人工综合(已对 P1–P3 复核)。

---

### 附:复现要点

- 测试床:`/home/s1yu/HarnessForge/generate/ft_full`(`.venv/bin/ft_full`,config 已设 `qwen-plus`、`.env` 已接 LiteLLM)。
- 隔离跑:`cp config.yaml /tmp/x.yaml` 改 state 目录 → `.venv/bin/ft_full <cmd> --config /tmp/x.yaml`。
- 扩展点 in-proc 探针:`.venv/bin/python` 直接 `import ft_full.harness.*` 注册并跑 loop(镜像 `cli.py` 接线)。
- 原始 sweep 结构化结果:`/tmp/claude-1000/-home-s1yu-HarnessForge/7fa5242e-.../tasks/wmxi1sya7.output`(10 个区报告 JSON)。
