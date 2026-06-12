# 02·11 - Slice 10:HITL 交互确认 + ask_question 工具(共享一套交互往返)

> 目标:补齐事实标准 harness 的**人在环交互层**。两件能力共用同一套「循环在边界**暂停 → 推结构化 UI → 等用户回应 → 解除继续**」的往返底座:
> - **ask_question 工具**:模型主动调用的内置工具,弹「选择题/文本输入」卡片向用户澄清,答案作为 `tool_result` 喂回(对齐 Cursor AskQuestion)。
> - **HITL 工具确认**:框架在工具执行边界拦截,弹 allow / reject / always-allow,让危险工具敢「预置不放行」(对齐 Claude Code / Cursor 工具放行)。
>
> 前置:Slice 9 门禁全绿。
>
> **薄/红线**:零新增运行期依赖(`contextvars`/`threading`/`queue` 均 stdlib;Web 复用现成 FastAPI/SSE)。HITL 是**护栏(威胁模型 A)非安全边界**——锁能力仍靠「生成期不编译进去」(`00-overview.md` §4),不借 HITL 把 `shell` 默认开。

## 0. 边界与口径

- **两条能力、一套机制**:ask_question(模型主动问)结果是喂回模型的 `tool_result`;HITL 确认(框架拦截问)结果是放行/拒绝某次工具执行。但在 CLI/Web 上都需同一套「暂停-弹窗-回传」往返。**共享底座 = `harness/interaction.py`(`Asker` 协议 + `ask()` + contextvar 注入)+ CLI/Web 两个 asker 实现 + 前端结构化卡片组件 + Web `POST /chat/{run_id}/respond` 回传管道**。先做 ask_question 时把底座一次建全,HITL 只加「工具边界调用 + 触发配置 + allow 等级」。
- **触发依据 = 放行清单,不是单次危险度**:主流(Claude Code `default` / Cursor `Allowlist`)都是 **fail-closed**——「工具/命令在不在放行清单里」决定问不问,不在调用时现场判断这次危不危险;**只读是唯一的默认豁免**。故 HITL 触发用不绑 risk 的放行清单模型:`confirm` 取 `none`(默认)/ `high` / `all` / 显式工具名列表;放行后从「要问集」移除。`risk=high` 只是 `high` 档的便捷选择器。
- **HITL 默认零痕迹、不破坏黄金路径**:`confirm` 默认 `none`(谁都不问 = 当前行为)。开启确认后,**非交互 / Web 公开面默认拒绝**。
- **ask_question 默认内置开启**:按内置安全工具对待(同 `calculator`),`risk=safe`、默认进 allowlist;非交互场景须优雅降级(不得让「模型一问就把单发 `run` 挂死」)。
- **HITL 是护栏非安全边界**:确认能拦住「可信但手滑」,拦不住改源码的代码所有者;强隔离仍交 Docker(威胁模型 B)。

## 1. 共享底座:交互往返

### 1.1 产物 `harness/interaction.py`(旁路扩展点,不在核心循环里)

与 `tools`/`hooks` 同级的薄模块:

- `AskRequest`(dataclass):`kind: Literal["question","approval"]` / `prompt: str` / `options: list[Option]`(每项 `{id, label}`;question 由模型给,approval 由 HITL 固定填)/ `allow_text: bool` / `allow_multiple: bool` / `context: dict`(approval 携带 `tool`/`arguments`/`risk`)。
- `AskResponse`(dataclass):`option_ids: list[str]` + `text: str | None` + 便捷属性 `selected`。
- `Asker`(Protocol):`ask(self, req) -> AskResponse`。
- 注入脊柱:`_CURRENT: ContextVar[Asker | None]` + `using_asker(asker)`(contextmanager)+ 模块级 `ask(req)`(读 contextvar)。工具/边界都经 `ask()` 调用,**不必改 tool 签名或 `run()` 形参**——这是「扩展性优先」的关键。
- 降级(无 asker / 非交互):`NonInteractiveAsker` — question → 返回「无交互用户、请自行判断」让模型决定、绝不挂死;approval → 选 `reject`(fail-closed)。

> **为什么用 contextvar 而非新增 `run()` 形参**:Slice 9 已给 `run()` 加了 `cancel`/`checkpoint`;再加 asker 会让范式签名膨胀,且 ask 要深入到工具函数体内部(tool 是纯函数,拿不到 `run()` 的局部),contextvar 是唯一不改 tool 签名又能触达的薄注入。入口 `with using_asker(...)` 包住整个 turn,worker 线程内显式设置。

### 1.2 CLI 实现 `CliAsker`(放 `interfaces/cli.py`)
渲染 `prompt` + 编号选项,`typer.prompt` 读输入;`allow_text` 时接受自由文本。与 Slice 9 协作:ask 期间首个 Ctrl-C 视为取消该 ask(返回降级/拒绝)。TTY 探测:`sys.stdin.isatty()` 为假(管道/CI/`--mock`)→ 用 `NonInteractiveAsker`。

### 1.3 Web 实现 `WebAsker` + 回传管道(放 `interfaces/web.py`,复用 Slice 9 run 注册表)
- `WebAsker.ask(req)`:生成 `request_id` → 把 `("ask", {request_id, ...req})` 投事件队列(前端弹卡片)→ 阻塞在该 run 的「回传队列」上 → 拿到回传转成 `AskResponse` 返回。
- `app.state.pending: run_id -> {request_id -> reply Queue}`(与 `app.state.runs` 平行,共用 `runs_lock`)。
- `POST /chat/{run_id}/respond`(body:`{request_id, option_ids, text}`)→ 把回传投进对应队列。未知 run/request 幂等 200。
- stop 联动:`POST /chat/{run_id}/stop` 或断连(`GeneratorExit`)置 cancel 时,给所有 pending 回传队列投 `None` 哨兵 → 阻塞中的 ask 立即返回(approval=reject / question=降级)。

### 1.4 前端结构化卡片(`web_index.html`,question/approval 共用一个组件)
监听 `event: ask` → 在对话流里渲染卡片(`prompt` + 选项按钮 + 可选文本框 + 提交)→ `POST /chat/{run_id}/respond`。主题化、内联(不用 `window.confirm/prompt`)。答完坍缩成一行摘要(`❓ 问题 → 选中/自定义` / `🔒 …→ 决定`)随对话流上滚。approval 卡片额外展示工具名 + 参数预览 + 风险 pill。

## 2. 计划 A:ask_question 工具

- **新增内置工具 `ask_question`**(`harness/tools.py`,`risk=safe`,始终注册 + 默认进 `config.yaml` allowlist):
  - 参数:`question: str`、`options: string[]`(可空 = 纯文本问)、`allow_multiple: bool=false`。**自由文本恒开**(Cursor 式「Other…」逃生口,由 asker 在 UI 层自动追加,`AskRequest.options` 仍逐字是模型给的选项;模型无法剥夺用户自定义输入的能力)。
  - 工具体:构造 `AskRequest(kind="question", ...)` → `ask()` → 把 `AskResponse` 格式化成确定字符串回模型(`User selected: <label>` / `User answered: <text>` / `User skipped.`)。
- **入口接线**:`cli.run`/`cli.chat`、`web._chat_events` 各自 `with using_asker(CliAsker()/WebAsker(...))` 包住 `run_loop(...)`;Web 在 worker 线程内设置 asker。
- **降级**:非交互(CLI 非 TTY、`--mock`)→ `NonInteractiveAsker` 让模型自行决定。
- **启用形态**:当内置工具直接生成 + 默认进 allowlist,`interaction.py` 底座始终生成(同范式注册表先例);要关 = 运行期移出 allowlist,不动 spec。

## 3. 计划 B:HITL 工具确认(复用 §1 底座)

- **触发配置(运行期,不进 spec)**:`config.yaml` **顶层** `confirm`(`tools:` 已是列表无法挂子键)= `none`(默认)/ `high` / `all` / 显式工具名列表。`Config.confirm` 字段 + 校验(空→`none`,非关键字裸串报错防误关)。默认 `none` → 零痕迹、不破坏 golden。
- **确认边界 + allow 4 档(对齐 Codex CLI)**:确认走 `harness/interaction.py` 的 `ToolConfirmer` + `using_confirmer` contextvar 注入 + 模块级 `confirm_tool()`,在 `run_tool`(`paradigms/__init__.py`)执行边界拦截(`run_tool` **未新增形参**,与 asker 同套 contextvar 注入,三个范式文件逐字不动)。若工具命中「要问集」(放行清单 − 会话已放行集):
  - `allow_once` → 执行本次,下次再问。
  - `reject` → 不执行,返回 `ERROR: user rejected tool <name>`(模型可自纠;不崩循环)。
  - `allow_session` → 加进进程内「本会话放行集」,本对话内该工具不再问(内存,重启重置)= 「会话内该工具所有调用全放行」。
  - `allow_always` → 永久:经 stdlib `config.persist_confirm`(只重写 `confirm:` 一行/块、保留全部注释;CLI-only 也能写,不依赖 web 专属 ruamel)写回 `config.yaml`。在分类策略(`high`/`all`)下会把策略「冻结」为剩余工具名的显式列表。
- **持久度由档本身表达**:`allow_session`(内存)+ `allow_always`(写 config)覆盖「记会话 vs 记持久」两级,不另设 `remember` 旋钮(UI 默认高亮 `allow_session`)。**不加 `allow_all_readonly`**(只读默认豁免)、**不放「会话级全放行」逐次档**(用运行期把 `confirm` 临时切 `none` 等价覆盖)。
- **不改 `before_tool` 语义**:`hooks.before_tool` 保持观察型;确认走 `interaction.confirm_tool()`。
- **非交互 / Web 公开面默认拒绝**:`NonInteractiveAsker` approval=reject;断连/超时=reject。

## 4. 退出门禁

- 黄金路径:preset/web 生成 → `uv sync && pytest` 绿 → mock 跑通一次工具调用(`--mock` 走 `NonInteractiveAsker`,ask_question 不会被误触)。
- 共享底座:`interaction.ask()` 经 contextvar 解析;无 asker / 非交互 → 降级(question 不挂死、approval 选 reject)。
- ask_question(A):CLI 与 Web 各跑通一次「模型调 ask_question → 弹 `event: ask` → 回传 → 答案进 `tool_result`」;非 TTY/`--mock` 降级。
- HITL(B)四档:`allow_once`/`reject`/`allow_session`/`allow_always` 各正确;`reject` 返回 ERROR 且循环不崩;**非交互默认拒绝断言**;`allow_session` 本会话该工具不再问;`allow_always` 写回 `config.yaml`(注释保留);Web approval 往返绿。
- 触发口径:`confirm` = `none`(零问)/ `high`(只高危)/ `all`(含只读)/ 工具名列表各命中正确;只读默认豁免。
- Web stop 联动:stop / 断连置 cancel 时,pending ask 立即解除(`None` 哨兵 → question 降级 / approval 拒绝);`/respond` 幂等。
- 关闭仍薄:ask_question 从 allowlist 移除后不 offer;`confirm: none`(默认)零问/零阻断、golden mock 路径不触发确认;无新增运行期依赖。
- 大改动回归(动范式核心 `run_tool` + `llm`/`cli`/`web` + 前端 + 新增 `interaction.py`):golden 全量 + Docker build/run mock。
- `ReadLints` clean。

## 5. 关键决策

- **① ask_question 启用形态 = 不动 spec**(内置工具直接生成 + 默认进 allowlist,底座始终生成;要关 = 运行期移出 allowlist)。
- **② allow 等级 = 干净 4 档** `allow_once / reject / allow_session / allow_always`(对齐 Codex);不加 `allow_all_readonly`(只读默认豁免);不放「会话级全放行」逐次档(用 `confirm=none` 等价)。
- **③ always-allow 记到哪 = 两者都给、默认 session**:`allow_session`(内存)+ `allow_always`(写回 `config.yaml`),不另设 `remember` 旋钮。
- **④ 是否据 HITL 把 `shell`/写工具默认开 = 不动**:HITL 确认只是额外闸,与「危险工具默认不启用 / 锁能力靠生成期不编译」正交;`config.yaml` 默认 `confirm: none` 且高危工具仍默认 `enabled: false`。改全局口径仍走 `CLAUDE.md §6`。
- **软确认**:`request_id`/`run_id` 风格沿用 `uuid4().hex[:12]`;contextvar 注入而非新增 `run()` 形参;前端卡片复用 Slice 8/9 内联确认范式。

## 6. 注意 / 留给后续

- **底座先建全**:做 A 时 `interaction.py` + `Asker` + CLI/Web 实现 + 前端卡片 + `POST /respond` 一次到位,B 只加「工具边界调用 + `confirm` 配置 + allow 等级」。
- **不抄的(违薄或重叠)**:Claude 式 pattern/参数级匹配(工具是函数粒度用不上)、`auto` LLM classifier 放行(要再跑模型,重)、`bypass/yolo`(= `confirm: none` 天然覆盖)。
- **公开面隔离**:Web 开 HITL/ask 后,管理面与公开面隔离是 v1+ 的前提(同 `/config`)。
- **多 ask 并发**:本片按「一个 run 同一时刻至多一个 pending ask」实现;若将来 subagent 并发,再扩 pending 表。
