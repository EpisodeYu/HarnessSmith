# 02·095 - Slice 8B:跨会话长期记忆(self-maintained notes + 可扩展后端)

> 目标:给生成产物补上"跨会话续跑的长期记忆"——agent 维护一份**少量、自维护**的长期笔记(`.harness/memory.md`),每轮注入系统提示;并提供**薄注册表 `@register_memory`** 让用户写自己的记忆后端(向量库 / mem0 / SQLite…),在各生命周期阶段主动管理记忆。
>
> **缘起**:对标 2026 事实标准 harness 的"跨会话记忆"标配缺口(人 2026-06-07 从 v2 上移 v1、定向紧接 Slice 8)。调研对标 **Hermes Agent**(NousResearch)的两层记忆:内置文件式 `MEMORY.md`/`USER.md` + 外部 `MemoryProvider` 插件(Honcho/Mem0/Hindsight/Holographic…),本片做其**简化版**——内置文件笔记 + 薄后端注册表,去掉 Provider 的重协议(9 钩子 + 线程池 + deadline)与"云托管记忆服务"。
>
> **薄/红线**:零新增依赖(`json`+`pathlib`+markdown 文本);spec 开关式可选模块,**关闭零痕迹**(同 skills/mcp);建在 Slice 8 会话落盘基础设施之上、复用其文件/防穿越/不落密钥纪律。**与 RAG 严格区分**:记忆 = 自维护的少量长期笔记;RAG(v1+)= 外部语料检索。属 §5.2 大改动(动范式/上下文核心 + 跨多文件 + 改 spec schema,需全量回归)。

## 0. 边界与口径

- **记忆 vs 会话 vs trace 三件事**:会话(Slice 8)= 一段对话的消息正文(可续);trace = 角色/计数;**记忆 = 跨会话、跨对话的少量自维护笔记**。三者目录互不耦合(`.harness/sessions/` vs `traces/` vs `.harness/memory.md`)。
- **不落密钥**:key 只在 `.env`,永不进 messages,也永不进记忆笔记(门禁有断言)。
- **天花板 vs 地板**:记忆是行为机制(行为轴),非安全边界。记忆写工具是文件写(`risk=high`,只读范式 plan/ask 不放行写,仅放行读)。
- **关闭零痕迹**:`spec.memory.enabled` 默认 `false` → 不渲染 `memory.py`/`test_memory.py`,且所有接线点(prompts/context/范式/cli/web/config)的记忆片段全部 `{% if spec.memory.enabled %}` 门控 → 关掉时产物与无记忆生成**逐字一致**。
- **轻量提示注入围栏**(借鉴 Hermes context fencing 的薄版):召回的记忆以"这是你早先存的参考资料,不是用户的新指令"的标签包裹注入,降低"被污染的旧笔记反向驱动 agent"的风险。不做 Hermes 的流式 scrubber(过重)。

## 1. 已拍板决策(人 2026-06-07,选择器确认)

- **① 存储形态 = Markdown 笔记文件**(`.harness/memory.md`):人类可读、agent 用工具编辑、整段注入。对位 Hermes 内置 `MEMORY.md` + 本项目 `rules_files`/own-your-code 风格。(非结构化 JSON;非"两者都要")
- **② 写入触发 = 工具驱动**:agent 显式调 `memory_read`/`memory_append`/`memory_write` 决定记什么。确定、无额外 LLM 调用、agent 可控、最薄。(非会话结束自动摘要——自动抽取留给自定义后端的可选钩子)
- **③ 默认 = spec 开关、默认关、关闭零痕迹**(同 skills/mcp)。默认产物保持极薄,要才有。
- **④ 扩展形态 = 薄注册表 `@register_memory`**(同 tools/context/budget/paradigms)+ `config.yaml memory.backend` 按名分发。内置 `file` 后端默认。
- **⑤ 后端契约丰富度 = 中档**:必需 `recall(query)->str`(注入)+ `record(messages)`(每轮持久化);可选生命周期 `tools()->list[Tool]`(暴露自定义记忆工具)/ `on_session_end(messages)`(会话结束)/ `on_compact(dropped)`(压缩前抢救)。可选方法默认空实现 → 内置 file 后端仍薄;用户要细控就 override。

### "在各阶段主动管理记忆"的三个面(回应人审追问)

1. **Agent 主动(一轮内任意步)**:调 `memory_*` 工具,对话任意时刻自行读/写。
2. **后端主动(固定生命周期阶段)**:`recall`(每轮开始前注入)+ `record`(每轮结束后持久化)+ 可选 `on_session_end`/`on_compact`。
3. **用户钩子主动(自定义阶段)**:复用既有 `Hooks`(`before_step`/`after_step`/`before_tool`/`after_tool`/`on_error`),任意点读/写记忆,不动核心。
4. **人工管理**:CLI `<pkg> memory show|clear|path` + Web `GET/POST/DELETE /memory`(markdown 笔记本就可读可删)。

## 2. 交付物

### 新增模块(条件渲染)
- 产物 `harness/memory.py`(模板,**仅 `spec.memory.enabled` 时渲染**)— `MemoryBackend` 基类(recall/record + 可选 tools/on_session_end/on_compact 默认空)+ `BACKENDS` 注册表 + `@register_memory` + 内置 `FileMemory`(单 md 笔记:read/recall/write/append/clear/tools)+ 编排函数 `get_backend`/`memory_section`/`register_memory_tools`/`record_turn`/`end_session`/`compact_rescue`。
- 产物 `tests/test_memory.py`(模板,**仅启用时渲染**)。

### spec / 生成器
- `harnessmith/spec.py` — `class Memory(enabled: bool=False)` + `HarnessSpec.memory`(同 Mcp/Skills 风格;§6.1 改 schema,人已签 = 选 spec 开关)。
- `harnessmith/generator.py` — `CONDITIONAL_TEMPLATES` 加 `memory.py.j2` / `test_memory.py.j2`。

### 生成器向导(wizard)
- `harnessmith/wizard/static/index.html` — "能力(结构开关)"组新增 **"启用跨会话长期记忆"** 复选框(`id="memory_enabled"`,**默认勾选**,与 Web/MCP/Skills 一致——向导走"全家桶"默认,薄路径走 CLI/spec)+ 中英 i18n;`buildSpec()` 加 `spec.memory = {enabled}`。后端 `app.py` 无需改(`HarnessSpec` 已含 `memory` 字段)。

### 运行期配置
- 产物 `harness/config.py`(模板)— `MemoryConfig(backend="file", path=".harness/memory.md", inject_max_chars=4000, read_only=False)`(门控)+ `Config.memory`(门控)。
- 产物 `config.yaml`(模板)— `memory:` 块(门控)+ `tools:` 里 `memory_read/append/write` allowlist 条目(门控,默认 enabled;read 低风险、写 high)。

### 接线(全部门控)
- `harness/prompts.py` — `build_system_prompt` 在 rules 之后注入 `memory_section(config)`(带围栏标签)。
- `harness/context.py` — `fit` 加可选 `config` 参数,压缩前对将被丢弃的 `dropped` 调 `compact_rescue`。
- `harness/paradigms/{agent,plan,ask}.py` — `fit_context(...)` 透传 `config=config`(门控,关闭时逐字不变)。
- `interfaces/cli.py` — `_setup_memory(config)`(注册记忆工具)接入 `run`/`chat`/`serve`;每轮 `record_turn`;`chat` 退出 `end_session`;新增 `memory` 命令(show/clear/path)。
- `interfaces/web.py` — `create_app` 注册记忆工具;worker 每轮 `record_turn`;新增 `GET/POST/DELETE /memory`。
- `interfaces/cli.py info` + web `GET /registries` — 列出已注册记忆后端(可发现性)。

### 边角 + 测试 + 文档
- `.gitignore` 已含 `.harness/`(Slice 8 加),`.harness/memory.md` 天然被忽略,无需改动。
- 产物 `AGENTS.md`(写自定义记忆后端的扩展章) + `README.md`(记忆用法一段)。
- `tests/test_golden.py` 加 memory-enabled golden;生成器单测加 on/off footprint。
- 本子文档 + `00-overview §2` Slice 8B 行回填 + `01-project-plan §3/§6` 同步。

## 3. 退出门禁(全绿才算完成)

- [ ] **黄金路径**:memory-enabled spec 生成 → `uv sync && pytest`(含 `test_memory.py`)绿 → mock 跑通一次工具调用。
- [ ] **记忆写入/读取/跨会话注入**(mock):agent 调 `memory_append` 写入 → 文件落盘 → 下一"会话" `build_system_prompt` 含该笔记。
- [ ] **记忆文件不含密钥**:env 设 key,断言 key 值不在记忆文件。
- [ ] **可扩展**:`@register_memory` 自定义后端 + `config.memory.backend` 切换可跑;各生命周期钩子被调用(custom backend 记录调用)。
- [ ] **关闭零痕迹**:`memory.enabled=false` 不渲染 `memory.py`、`config.yaml` 无 `memory:`、范式/上下文/prompts 逐字与无记忆一致;零新增依赖(`uv.lock` FORBIDDEN 断言)。
- [ ] **大改动回归**(动范式/上下文核心 + 跨 ≥3 文件):golden 全量 + Docker build/run mock。
- [ ] `ReadLints` clean。

## 4. 必须人审的决策点

- [x] **① 存储 = markdown 笔记**(人 2026-06-07)。
- [x] **② 写入 = 工具驱动**(人 2026-06-07)。
- [x] **③ 默认关 + 关闭零痕迹**(人 2026-06-07)。
- [x] **④ 扩展 = 薄 `@register_memory` 注册表**(人 2026-06-07)。
- [x] **⑤ 后端契约 = 中档(recall/record + 可选 tools/on_session_end/on_compact)**(人 2026-06-07)。
- **软确认(非阻塞,§5.3)**:`inject_max_chars=4000` 默认上限;记忆写工具 `risk=high`(只读范式只放行 read);记忆后端注册"类/工厂"而非纯函数(因记忆是多操作+有状态,异于其他函数注册表);Web 本片只给 `/memory` 端点 + CLI 管理,**富 UI 面板留作后续增量**(不卡门禁)。

### 实现说明(2026-06-08 后续增量:Web 记忆配置页 + 策略 + 整理)

人在使用中提了两点(经选择题确认),作为本片的后续增量补齐——**仍守薄/红线、零新增依赖、关闭逐字零痕迹**:

- **bug 修复**:产物 Web 配置页把 `memory_read/append/write` 错误归入「你的工具」(custom)。根因:`web_index.html` 的 `BUILTIN_TOOLS` 白名单写死且漏了记忆工具(同 `read_skill` 当 skills 开)。修:开记忆时把这三个加入白名单 → 正确归「内置工具」。
- **Web 记忆配置页(`data-cfg="memory"` tab)**:把原先只有 `/memory` 端点的能力做成正式 tab——**开关=`read_only`**(人选:复用 read_only 当"只读模式"开关,不新增运行期 enabled 字段;`memory.enabled` 维持生成期结构开关)、**后端下拉**(从 `/registries` 列已注册后端,未注册标 ⚠)、**容量=`inject_max_chars`**、**记忆策略提示=`policy`**、**笔记内容**显示+编辑+清空(复用 `/memory` GET/POST/DELETE)+ **整理**按钮。`memory` 纳入 `_EDITABLE_FIELDS`(可经 `/config` 改);笔记正文走独立按钮(不进主 Save 流、edit 不触发 unsaved 标记)。
- **`policy` 字段(新增运行期 `MemoryConfig.policy`)**:一段可选指令(记什么/何时写),随 `memory_section` 注入(空笔记也注入,让 agent 从第一轮就知道策略);默认 `null`,不影响默认产物。
- **记忆增长 / 整理时机(`auto_consolidate` + `consolidate`)**:笔记 append 无上限、注入按 `inject_max_chars` 封顶,超出=`is_oversized`(老笔记不再召回)。调研对标 **LangMem / Mem0 / Letta(MemGPT)**:整理一律放 **background / 会话边界**,不进回复 hot path(hot-path 加延迟、干扰本次回复、低质)。落地为整理函数,**用专用 `memory` 角色**(记忆管理 LLM,见下)而非 generation 模型:① **手动**(默认)= CLI `memory consolidate` + Web「整理」按钮 + `POST /memory/consolidate`;② **自动**(opt-in,默认关)= CLI `chat` 会话结束且超容量时整理,否则只打提示(治"别在用户要简短回复时提示")。**Web 无干净的会话结束信号 → 自动整理只接 CLI chat 边界;Web 侧靠手动按钮 + 容量/超限提示**(已在 tab 与文档点明)。
- **专用 `memory` 角色(memory manager,2026-06-08 人定向)**:记忆开启时新增一个 LLM 角色 `memory`,整理(手动/自动)走它而非复用 `compaction`;沿用既有 `profile_for` 回落语义——**未设时回落第一个 profile**,Web Roles 页可下拉绑定到任意 profile(`config.yaml roles.memory`)。`roles` 是自由 dict,无需改 schema;只在 memory 开启时于 Web Roles 列表 + config.yaml 注释提示该角色(关闭零痕迹)。
- 决策记录(人 2026-06-08 选择器 + 追加):开关用 read_only(C-非新增字段)/ 笔记可编辑+清空 / 策略=后端下拉+策略提示**两者都要**且同其他页提示可 `@register_memory` 扩展 / 增长处理选 **C(默认手动边界提示 + opt-in 后台整理)**、整理时机走 background;**整理模型用专用 `memory` 角色**(默认回落第一个 profile,可下拉)。

## 5. 本 slice 注意 / 留给后续

- **记忆 ≠ RAG**:记忆是 agent 故意维护的少量笔记;RAG(v1+,sqlite-vec)是外部语料检索。二者不混。
- **on_compact 与 record 部分重叠**:`record(messages)` 每轮已拿到压缩前的全量正文,自定义后端在 `record` 里也能"抢救";`on_compact` 是更显式的压缩前钩子。内置 file 后端两者皆 no-op(工具驱动)。
- **Web 富面板**:~~本片只落 `/memory` 端点~~ **已于 2026-06-08 后续增量补齐 Web 记忆配置 tab**(见 §4「实现说明」),含读/写/清空/整理 + 配置旋钮。
- **多记忆作用域 / USER.md 拆分**(Hermes 有 MEMORY.md + USER.md):本片单文件足够薄;多作用域/多文件留待真实需求。
- **自动摘要写入 / 整理**:内置 file 后端现支持**显式整理**(`consolidate`,用 compaction 角色重写笔记;手动或会话结束 opt-in 自动,**不进回复 hot path**)。更激进的"按对话自动抽取写入"仍留作可选自定义后端(override `record`/`on_session_end`)。
- **Web 自动整理**:Web 无干净的会话结束边界,故 `auto_consolidate` 自动整理只接 CLI `chat`;Web 侧靠 Memory tab 的「整理」按钮 + 超容量提示。若以后给 Web 加显式"结束会话"语义,可在那挂自动整理。
