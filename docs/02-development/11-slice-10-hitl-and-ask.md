# 02·11 - Slice 10:HITL 交互确认 + ask_question 工具（共享一套交互往返）

> 目标:补齐事实标准 harness 的**人在环交互层**。两件能力共用同一套"循环在边界**暂停 → 推结构化 UI → 等用户回应 → 解除继续**"的往返底座,上层是两个可独立开关的能力:
> - **ask_question 工具**(本片**先做**):模型主动调用的内置工具,弹"选择题/文本输入"卡片向用户澄清,答案作为 `tool_result` 喂回。对齐 Cursor 的 AskQuestion。
> - **HITL 工具确认**(本片**后做**):框架在工具执行边界拦截,弹 allow / reject / always-allow,让危险工具敢"预置不放行"。对齐 Claude Code / Cursor 的工具放行。
>
> **缘起 & 排期**:Slice 10 原登记仅 HITL 确认(见 `00-overview §2` Slice 10 行 / `../03-feature-landscape-and-proposals.md §3 T1-B`)。2026-06-09 人新增 ask_question 诉求并定向:**两者共用一套交互管道,先做 ask_question(更简单、纯模型主动)、HITL 抒后,但底座要让 HITL 直接复用**;两份开发计划一次出齐。
>
> **薄/红线**:零新增运行期依赖(`contextvars`/`threading`/`queue` 均 stdlib;Web 复用现成 FastAPI/SSE)。HITL 是**护栏(威胁模型 A)非安全边界**——锁能力仍靠"生成期不编译进去"(`01 §4`),文档须讲清这条。**不**借 HITL 把 `shell` 默认开(改 `01 §6` 全局口径需人签)。属 **§5.2 大改动**(动范式核心 `run_tool` + `llm`/`cli`/`web` + 前端 + 新增 `interaction.py`,跨 ≥3 文件),实现时跑全量回归。

---

## 0. 边界与口径

- **两条能力、一套机制**:ask_question(模型主动问)与 HITL 确认(框架拦截问)语义不同——前者结果是喂回模型的 `tool_result`,后者结果是放行/拒绝某次工具执行——但在 CLI/Web 上都需要同一套"暂停-弹窗-回传"往返。**共享底座 = `harness/interaction.py`(`Asker` 协议 + `ask()` + contextvar 注入)+ CLI/Web 两个 `Asker` 实现 + 前端结构化卡片组件 + Web `POST /chat/{run_id}/respond` 回传管道**。先做 ask_question 时把底座一次建全,HITL 只加"工具边界调用 + 触发配置 + allow 等级",不重写管道。
- **触发依据 = 放行清单,不是单次危险度**(2026-06-09 调研定向,见 §5 取证):主流(Claude Code `default` / Cursor `Allowlist`)都是 **fail-closed**——"工具/命令在不在放行清单里"决定问不问,不在调用时现场判断这次危不危险;**只读是唯一的默认豁免**。故 HITL 触发用**不绑 risk 的放行清单模型**:`tools.confirm` 取 `none`(默认)/ `high` / `all` / 显式工具名列表;放行后从"要问集"移除。`risk=high` 只是 `high` 档的便捷选择器,不是硬编码的唯一触发源。
- **HITL 默认零痕迹、不破坏黄金路径**:`tools.confirm` 默认 `none`(谁都不问 = 当前行为),所以 mock 非交互 golden 不受影响。开启确认后,**非交互 / Web 公开面默认拒绝**(已登记)。
- **ask_question 默认内置开启**(人 2026-06-09 选 default_on):按内置安全工具对待(同 `calculator`),`risk=safe`、默认进 allowlist;非交互场景须优雅降级(见 §2),不得让"模型一问就把单发 `run` 挂死"。
- **HITL 是护栏非安全边界**:确认能拦住"可信但手滑",拦不住改源码的代码所有者(own-your-code 没有地板);强隔离仍交 Docker(威胁模型 B)。与 Slice 9 的关系:Slice 9 是"事后停/续/改",Slice 10 是"事前问/逐次放行",都挂在循环边界但各自独立(不再像旧 Checkpoints 那样配对共建)。

---

## 1. 共享底座:交互往返(ask_question 先做时一次建全,HITL 复用)

### 1.1 新增产物 `harness/interaction.py`（旁路扩展点,不在核心循环里）

一个统一的"问用户"通道,与 `tools`/`hooks` 同级的薄模块:

- `AskRequest`(dataclass):
  - `kind: Literal["question", "approval"]` — 谁发起、什么语义。
  - `prompt: str` — 问题正文 / 确认说明。
  - `options: list[Option]` — 每项 `{id, label}`;question 由模型给,approval 由 HITL 固定填(allow_once/reject/...)。
  - `allow_text: bool` — 是否允许自由文本输入(question 常开,approval 常关)。
  - `allow_multiple: bool` — 多选(question 用)。
  - `context: dict` — approval 携带 `tool`/`arguments`/`risk` 供 UI 展示。
- `AskResponse`(dataclass):`option_ids: list[str]` + `text: str | None` + 便捷属性 `selected`(单选首个)。
- `Asker`(Protocol):`def ask(self, req: AskRequest) -> AskResponse`。
- 注入脊柱:`_CURRENT: ContextVar[Asker | None]` + `using_asker(asker)`(contextmanager)+ 模块级 `ask(req) -> AskResponse`(读 contextvar)。**工具/边界都经 `ask()` 调用,不必改 tool 签名或 `run()` 形参**——这是"扩展性优先"的关键:ask_question 工具体内 `from ..interaction import ask` 即可,HITL 边界同理。
- 降级(无 asker / 非交互):`NonInteractiveAsker` — question → `AskResponse(text="(no interactive user available; proceed using your best judgment)")` 让模型自行决定、绝不挂死;approval → 选 `reject`(fail-closed,符合"非交互默认拒绝")。

> **为什么用 contextvar 而非新增 `run()` 形参**:Slice 9 已给 `run()` 加了 `cancel`/`checkpoint` 两个穿透回调;再加 asker 会让范式签名继续膨胀,且 ask 要深入到**工具函数体内部**(tool 是纯函数,拿不到 `run()` 的局部),contextvar 是唯一不改 tool 签名又能触达的薄注入。入口 `with using_asker(...)` 包住整个 turn,worker 线程内显式设置(contextvar 不跨 `threading.Thread` 继承)。

### 1.2 CLI 实现 `CliAsker`

- 渲染:`prompt` + 编号选项(`[1] ... [2] ...`),`typer.prompt` 读输入;`allow_text` 时空选项也接受自由文本。
- 与 Slice 9 协作:ask 期间首个 Ctrl-C 视为取消该 ask(返回降级/拒绝),不与 `_interruptible`(`cli.py:32`)的取消令牌打架。
- TTY 探测:`sys.stdin.isatty()` 为假(管道/CI/`--mock` 冒烟)→ 用 `NonInteractiveAsker`,保证单发 `run`、Docker 冒烟、golden 不被阻塞。

### 1.3 Web 实现 `WebAsker` + 回传管道(复用 Slice 9 的 run 注册表)

现状 `_chat_events`(`web.py:144`)的 worker 线程把事件经 `queue` **单向** push 给 SSE。升级为**双向**:

- `WebAsker.ask(req)`:生成 `request_id` → 把 `("ask", {request_id, ...req})` 投进事件队列(前端据此弹卡片)→ **阻塞**在该 run 的"回传队列"上 `get()` → 拿到回传转成 `AskResponse` 返回。
- `create_app` 扩 `app.state.runs`:现为 `run_id -> cancel Event`(`web.py:286`,仅 stop 用),并存一张 `run_id -> {request_id -> reply Queue}`(或在 run 记录上挂 pending 表)。
- 新增 `POST /chat/{run_id}/respond`(body:`{request_id, option_ids, text}`)→ 把回传投进对应队列,解除 worker 阻塞。未知 run/request 幂等 200。
- **stop 联动**:`POST /chat/{run_id}/stop`(`web.py:337`)或断连(`GeneratorExit`,`web.py:252`)置 cancel 时,同时给所有 pending 回传队列投一个"取消"哨兵 → 阻塞中的 ask 立即返回(approval=reject / question=降级),不留挂起线程。
- **超时 / 公开面默认拒绝**:`WebAsker` 可配可选等待上限,超时按 fail-closed(approval=reject)。公开面隔离沿用 Slice 14+ backlog 的"管理面/公开面隔离"前提。

> **实现说明(2026-06-09)**:pending 表选了"独立平行 map"方案——`app.state.runs` 维持 `run_id -> cancel Event`(stop 端点与既有测试逐字不动),另加 `app.state.pending: run_id -> {request_id -> reply Queue}`,共用 `runs_lock`。`_chat_events` 新增 `pending=None` 形参;worker 线程内 `with using_asker(asker)`(contextvar 不跨线程,故在 worker 内设)。`WebAsker.ask` 投 `("ask", …)` 事件后阻塞在 reply Queue 上,`POST /chat/{run_id}/respond` 投回 `{option_ids,text}` 解除;stop / `GeneratorExit` 给所有 pending Queue 投 `None` 哨兵 fail-closed。`CliAsker` 放在 `interfaces/cli.py`(依赖 typer)、`WebAsker` 放在 `interfaces/web.py`;`Asker` 协议 + `NonInteractiveAsker` + contextvar 注入留在 `harness/interaction.py`(仅 stdlib)。超时等待上限本片未接(留 B / 后续)。

### 1.4 前端结构化卡片(`web_index.html`,question/approval 共用一个组件)

- 监听 `event: ask` → 在对话流里渲染一张卡片:`prompt` + 选项按钮(单/多选)+(可选)文本框 + 提交。提交 → `POST /chat/{run_id}/respond`。
- 主题化、内联(不用 `window.confirm/prompt`),沿用 Slice 8 §4b / Slice 9 重问的内联确认范式。
- approval 卡片额外展示工具名 + 参数预览 + 风险标记;question 卡片展示模型给的选项 + "跳过"。

---

## 2. 计划 A:ask_question 工具（先做)

> **状态:✅ 已实现(2026-06-09)**。`ask_question` 内置工具在 `tools.py` 始终注册(`risk=safe`),`config.yaml.j2` 在 `spec.tools` 之后**无条件**渲染 `ask_question: enabled: true`(对齐决策①:内置直接生成、不进 spec、要关就运行期移出 allowlist)。CLI(`run`/`chat`)与 Web(`_chat_events` worker)入口已用 `using_asker(...)` 包住 `run_loop`;非交互(CLI 非 TTY / `--mock` / Web 断连)走 `NonInteractiveAsker` 优雅降级。前端 `web_index.html` 监听 `event: ask` 渲染内联卡片(单/多选 + 文本框 + 提交/跳过),提交 `POST /chat/{run_id}/respond`。
>
> **交互形态(2026-06-09 人确认 + 实机反馈修订)**:① 选项由 **LLM 自己构造**(工具参数 `options: string[]`,调用时填);② **多选**支持(`allow_multiple`,Web checkbox / CLI 逗号分隔,`option_ids` 列表);③ **自定义输入做成 Cursor 式"最后一项 = 其他…",且对 question 恒定可用**:asker **在 UI 层**自动追加一个"Other…"项(Web 单选时收起文本框、选中才展开;CLI 末尾加 `[N+1] Other`,选中后再追问自定义文本)——`AskRequest.options` 仍**逐字**是模型给的选项,"Other"是 CLI/Web 各自合成、映射回既有 `text` 字段,不改协议/工具签名。工具描述已提示模型**不要自己再加 "Other" 选项**。
>
> **实机反馈修订(2026-06-09)**:① **去掉 `allow_free_text` 参数**——之前模型偶尔传 `false` 导致单选题没有自定义框、用户被困在固定选项里;现在 question **始终** `allow_text=True`(模型无法剥夺用户自定义输入的能力,对齐 Cursor);`allow_text` 仅对未来的 approval 卡片(只 allow/reject 按钮)取 false。② **Web 卡片答完即坍缩成一行摘要**(`❓ 问题 → 选中/自定义`),随对话流自然上滚,不再有大块交互控件钉在底部;并**抑制 `ask_question` 的 `→/← tool` 流水行**(卡片已表达该次交互),避免重复。③ **修复流式文本与卡片错位**(实机:一回合连问多题时,模型最终总结显示在所有卡片**上方**)——根因是前端把整轮流式文本复用同一个 `answer` DOM 元素(在 step 0 的前导文本处创建,位于卡片上方,后续 step 的总结又追加进去);改为**每当插入卡片/工具行就 `answer = null`**,让后续 token 另起新行落到卡片**下方**(前导文本仍在卡片上方,符合对话顺序)。此前置 bug 非 ask 专属,任何"多步 + 步间都产文本 + 工具输出穿插"都会触发,本次一并修。

- **新增内置工具 `ask_question`**(`harness/tools.py`,`risk=safe`,默认随产物生成 + 默认进 `config.yaml` allowlist):
  - 参数 schema:`question: str`、`options: string[]`(可空 = 纯文本问)、`allow_multiple: bool=false`。自由文本恒开(Cursor 式 "Other" 逃生口),不再有 `allow_free_text` 开关。
  - 工具体:构造 `AskRequest(kind="question", ...)` → `ask()` → 把 `AskResponse` 格式化成确定字符串回模型(如 `User selected: <label>` / `User answered: <text>` / `User skipped.`)。
- **入口接线**:`cli.run`/`cli.chat`、`web._chat_events` 各自 `with using_asker(CliAsker()/WebAsker(...))` 包住 `run_loop(...)`;Web 在 worker 线程内设置 asker。
- **降级**:非交互(CLI 非 TTY、`--mock`)→ `NonInteractiveAsker` 让模型自行决定;不改变现有单发 `run` 语义。
- **薄取舍 / 待签**:是否给 spec 开关(见 §5 决策点①)。推荐**不动 spec**——当内置工具直接生成,`interaction.py` 底座始终生成(同"范式注册表始终在"先例),想关就运行期从 allowlist 移除。

---

## 3. 计划 B:HITL 工具确认（后做,复用 §1 底座)

> **状态:✅ 已实现(2026-06-09)**。`config.yaml` 顶层新增 `confirm` 旋钮(`none` 默认 / `high` / `all` / 工具名列表),`Config.confirm` 字段 + 校验(空→`none`,非关键字裸串报错防误关)。确认走 **`harness/interaction.py` 的 `ToolConfirmer` + `using_confirmer` contextvar 注入 + 模块级 `confirm_tool()`**,在 `run_tool`(`paradigms/__init__.py`)执行边界拦截:`confirm_tool(name, args, registry.risk_of(name))` 返回拒绝串则不执行(返回 `ERROR: user rejected tool <name>`,模型自纠、循环不崩),否则照常 `registry.call`。四档 `allow_once`/`reject`/`allow_session`/`allow_always` 对齐 Codex。CLI(`run`/`chat` 各 `with using_confirmer(_build_confirmer(...))`,`chat` 复用同一 confirmer 让 session 放行跨轮)与 Web(`_chat_events` 每请求按 `config.confirm` 重建 confirmer,会话级放行集存 `app.state.confirm_sessions[session_id]`,worker 内 `using_confirmer`)均接线;非交互(无 asker)/ Web stop·断连(`None` 哨兵)经既有 asker 降级 → approval 选 `reject`(fail-closed)。前端 `web_index.html` 的 `event: ask` 卡片 approval 分支:工具名 + 参数预览 + 风险 pill(high 红 / safe 绿)+ 四按钮(默认高亮 `allow_session`、`reject` 描红),答完坍缩成 `🔒 …→ 决定` 摘要。
>
> **实现说明(与初版计划的偏差)**:① **触发配置是顶层 `confirm`** 而非 `tools.confirm`(`tools:` 已是列表,无法挂子键;§0 已留"或顶层 `confirm` 段"口子)。② **`run_tool` 未新增 `confirm_set` 形参**——改用与 asker 同一套 contextvar 注入(`using_confirmer`/`confirm_tool`),三个范式文件**逐字不动**(更薄、与 ask_question 的 contextvar 范式一致;§1.1 已确立该理由)。③ **`allow_always` 写回用 stdlib 的 `config.persist_confirm`**(只重写 `confirm:` 一行/块、保留全部注释)而非 web 专属的 ruamel `save_config`——因 `save_config`/ruamel 仅在 `interfaces.web` 时生成,CLI-only 产物没有;`persist_confirm` 始终生成、零新增依赖,两个入口共用。④ **`allow_always` 在分类策略(`high`/`all`)下会把策略"冻结"为剩余工具名的显式列表**(把该工具移出 confirm 集 = 写剩余集),是一次刻意的持久选择,已在 config 注释/AGENTS.md 标注。

- **触发配置(运行期,不进 spec)**:`config.yaml` 顶层新增 `confirm`(实现落在顶层而非 `tools.confirm`,见上方实现说明)= `none`(默认)/ `high` / `all` / 显式工具名列表。默认 `none` → 零痕迹、不破坏 golden。
- **确认边界 + allow 等级(干净 4 档,对齐 Codex CLI)**:在 `run_tool`(`paradigms/__init__.py:94`)执行工具前,若工具命中"要问集"(放行清单 − 会话已放行集),`ask(AskRequest(kind="approval", context={tool,args,risk}, options=[allow_once, reject, allow_session, allow_always]))` —— 这 4 档对齐 Codex 的 Accept once / Reject / **Accept for session** / **Accept and add to policy**(2026-06-09 调研,见 §5 取证):
  - `allow_once` → 执行本次,下次该工具再问。
  - `reject` → 不执行,返回 `ERROR: user rejected tool <name>`(模型可自纠;不崩循环,沿用 `run_tool` 既有 ERROR 语义)。
  - `allow_session` → 加进进程内"本会话放行集",本对话内该工具不再问(内存,重启重置)。**这就是"会话内该命令的所有调用全放行"**(人 2026-06-09 问及;= Codex "Accept for session" 的 identical-operation 等价,我们按工具名粒度),**已含、无需另设档**。
  - `allow_always` → 永久:写回 `config.yaml`(把该工具移出 `confirm` 集 / 加豁免,经 `save_config` 保注释;= Codex "add to policy")。
- **持久度由档本身表达,不另设 `remember` 旋钮**:`allow_session`(内存)与 `allow_always`(写 config)已覆盖"记会话 vs 记持久"两级(人 2026-06-09 选"两者都给、默认 session";UI 默认高亮 `allow_session` 档)。
- **不加 `allow_all_readonly`、不放"会话级全部放行"逐次档**(人 2026-06-09 签):只读靠默认豁免(`confirm` 不纳入 safe,或用 `high` 档);"会话级全放行"(Cline `--auto-approve`/Codex `never` 类)是 mode/flag 语义,用运行期把 `confirm` 临时切 `none` 等价覆盖,不进弹窗以免误点降护栏。
- **不改 `before_tool` 语义**:`hooks.before_tool`(`hooks.py:22`)保持观察型;确认走 `interaction.confirm_tool()`(经 contextvar 读 `ToolConfirmer`,**未新增 `run_tool` 形参**,见实现说明②),live at the tool-execution boundary。
- **非交互 / Web 公开面默认拒绝**:`NonInteractiveAsker` approval=reject;断连/超时=reject。
- **红线**:确认是护栏非保证;**不**据此把 `shell`/写工具默认开(改 `01 §6` 需人签,见 §5 决策点④,沿用既有登记)。

---

## 4. 退出门禁（实现后逐项勾;A 先交付可单独绿,B 再补)

> **实现进度(2026-06-09)**:**共享底座 + 计划 A(ask_question)+ 计划 B(HITL 工具确认)均已实现并全绿**(生成器快测 132 + golden 10 + Docker 2;产物自带 interaction/ask_question/HITL 四档/触发口径/persist_confirm/Web approval 往返测试;ReadLints clean)。下方门禁全部勾选。

- [x] **黄金路径**:preset/web 生成 → `uv sync && pytest` 绿 → mock 跑通一次工具调用(mock `script=None` 调首个工具 `get_current_time`,ask_question 不会被误触;`--mock` 走 `NonInteractiveAsker`)。
- [x] **共享底座**:`interaction.ask()` 经 contextvar 解析(`using_asker`);无 asker / 非交互 → 降级(question 返回"无用户、自行判断"不挂死、approval 选 reject)单测绿(`test_ask_resolves_via_contextvar_and_restores` / `test_noninteractive_degrades_question_and_rejects_approval`)。
- [x] **ask_question(A)**:CLI(`CliAsker`,monkeypatch `typer.prompt` 注入假 stdin:数字→选项 id、文本→自由回答、空→跳过)与 Web(`WebAsker` + `POST /chat/{run_id}/respond`)各跑通一次"模型调 ask_question → 弹 `event: ask` → 回传 → 答案进 `tool_result`"(`test_ask_question_tool_feeds_answer_back_as_tool_result` / `test_ask_question_round_trips_over_web`);非 TTY/`--mock` 降级绿(`test_ask_question_tool_degrades_without_a_user`)。
- [x] **HITL(B)四档**:`allow_once`/`reject`/`allow_session`/`allow_always`(mock asker)绿(`test_confirm_allow_once_runs_but_asks_every_time` / `test_confirm_reject_returns_error_and_loop_survives` / `test_confirm_allow_session_then_stops_asking` / `test_confirm_allow_always_runs_and_persists_remaining_policy`);`reject` 返回 `ERROR: user rejected tool <name>` 且循环不崩;**非交互默认拒绝断言**(`test_confirm_non_interactive_rejects_fail_closed`);`allow_session` 本会话该工具不再问;`allow_always` 写回 `config.yaml`(`persist_confirm` 注释保留,`test_persist_confirm_rewrites_only_the_confirm_line`);Web approval 往返绿(`test_hitl_tool_confirmation_round_trips_over_web`)。
- [x] **触发口径**:`confirm` = `none`(零问,`test_confirm_none_is_zero_overhead`)/ `high`(只高危)/ `all`(含只读)/ 工具名列表 各命中正确(`test_confirm_names_resolves_each_policy`);只读默认豁免;字段校验绿(`test_confirm_config_accepts_keywords_and_lists`)。
- [x] **Web stop 联动**:stop / 断连(`GeneratorExit`)置 cancel 时,pending ask 立即解除(投 `None` 哨兵 → question 降级 / approval 拒绝),无挂起线程(`test_stop_unblocks_a_pending_ask_fail_closed`;`/respond` 幂等 `test_respond_endpoint_routes_answer_and_is_idempotent`)。
- [x] **关闭仍薄**:ask_question 从 allowlist 移除(或 `enabled: false`)后不 offer;`confirm: none`(默认)零问/零阻断、golden mock 路径不触发确认(`test_confirm_none_is_zero_overhead` + golden 全绿);**无新增运行期依赖**(底座只用 stdlib `contextvars`,`persist_confirm` 只用 stdlib `re`/`pathlib`、CLI-only 也能写回;golden `uv.lock` FORBIDDEN 断言不含 langchain/langgraph/adk 全绿)。
- [x] **大改动回归**:golden 全量(10 项:preset/web/mcp/multi-paradigm/thin/mcp-baseline/skills/memory/wizard/uvx)+ Docker build/run mock 全绿。
- [x] `ReadLints` clean。

---

## 5. 人审决策点（实现前请人签）

- [x] **① ask_question 启用形态(人 2026-06-09 签:不动 spec)**:当内置工具直接生成 + 默认进 allowlist,`interaction.py` 底座始终生成(同范式注册表先例);要关 = 运行期移出 allowlist。不加 spec 开关(不触 `CLAUDE.md §6.1` 改 spec schema)。
- [x] **② allow 等级集合(人 2026-06-09 签:干净 4 档)**:`allow_once / reject / allow_session / allow_always`,对齐 Codex Accept once / Reject / Accept for session / add to policy。**不加 `allow_all_readonly`**(只读默认豁免);**不放"会话级全放行"逐次档**(用运行期 `confirm=none` 等价)。`allow_session` 即"会话内该工具全放行"(人问及,已含)。
- [x] **③ always-allow 记到哪(人 2026-06-09 签:两者都给、默认 session)**:由 `allow_session`(内存)+ `allow_always`(写回 `config.yaml`,经 `save_config` 保注释)两档表达,不另设 `remember` 旋钮;UI 默认高亮 `allow_session`。
- [x] **④ 是否据 HITL 把 `shell`/写工具默认开(实现保持默认不动,未触 `01 §6`)**:HITL 确认只是**额外闸**,与"危险工具默认不启用 / 锁能力靠生成期不编译"正交——实现**未**因有了确认就把 `shell`/写工具默认开,`config.yaml` 默认 `confirm: none` 且高危工具仍默认 `enabled: false`,需要时人各自显式开。改全局口径仍走 `CLAUDE.md §6`,本片不触。
- **软确认(`§5.3` 可自主)**:`request_id`/`run_id` 风格沿用 `uuid4().hex[:12]`;contextvar 注入而非新增 `run()` 形参;前端卡片复用 Slice 8/9 内联确认范式。

---

## 6. 注意 / 留给后续

- **底座先建全**:做 A 时 `interaction.py` + `Asker` + CLI/Web 实现 + 前端卡片 + `POST /respond` 一次到位,B 只加"工具边界调用 + `confirm` 配置 + allow 等级",避免管道写两遍。
- **不抄的(违薄或重叠)**:Claude 式 pattern/参数级匹配(`Bash(npm *)`,我们工具是函数粒度用不上)、`auto` LLM classifier 放行(要再跑模型,重)、`bypass/yolo`(= `confirm: none` 天然覆盖)、`plan` 只读 mode(已用 plan/ask 范式 + allowlist 覆盖)。
- **公开面隔离**:Web 开 HITL/ask 后,管理面与公开面隔离是 Slice 14+ backlog 的前提(同 `/config`)。
- **多 ask 并发**:本片按"一个 run 同一时刻至多一个 pending ask"实现(循环是串行的);若将来 subagent 并发,再扩 pending 表。
