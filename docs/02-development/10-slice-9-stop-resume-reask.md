# 02·10 - Slice 9:停止 / 继续 / 重问(会话时间旅行)

> 目标:在 Slice 8 会话落盘之上补齐事实标准 harness 的**交互控制三件**——**停止**(回合跑到一半喊停、连 LLM 思考/输出一并终止)、**继续**(停止 / Ctrl+C / 断网中断后,下次发送时 LLM 仍知道之前在做什么、可接着干)、**重问**(Web 点任意历史提问就地编辑、确认丢弃后续后从该点重生)。三者共用一根"协作式取消令牌"+ session 截断,统称会话级时间旅行。
>
> **缘起**:Slice 9 槽位原为 T1-C 文件级 Checkpoints(git 快照),已于 2026-06-08 评估撤销(见 `../03-feature-landscape-and-proposals.md §3 T1-C`)。同日人重新定向:把对标 Claude Code / Cursor 的**停止/继续/重问**(会话级,建在 sessions 之上,与"文件级回滚"是两个层面)填入 Slice 9。
>
> **状态:✅ 已实现(2026-06-09);§4 决策点已于 2026-06-08 经人签字(①接受步/chunk 边界、②加断连兜底、③Tier B 崩溃安全、④CLI 不做重问、⑤重问破坏式截断)。门禁全绿:生成器快测 122 + golden 全量 10(含 web/多范式/mcp/skills/memory/wizard/uvx)+ Docker build/run mock;产物自带新测试覆盖停止/取消/checkpoint/崩溃修复/重问;ReadLints clean。**
>
> **薄/红线**:零新增依赖(`threading` / `signal` 均 stdlib);纯运行期机制,**不改 spec schema、不改 LLM API 面**(取消只是给 `stream`/`complete` 加一个协作检查,不动 Chat Completions 选型;不触 `CLAUDE.md §6.1/§6.4`)。属 **§5.2 大改动**(动范式核心循环 + 跨 `agent/plan/ask` + `llm.py` + `web.py`/前端 + `cli.py`),实现时跑全量回归。

## 0. 边界与口径

- **会话本身就是可续状态**:`harness/session.py` 已把整段 `messages` 正文落盘(Slice 8)。"继续"不是新存储,而是"**中断时把进行中的 `messages` 存到一个合法边界**",之后沿用现成 `--continue`/`--resume`/Web 续聊即可——LLM 看到原问题 + 已完成的工具步骤,天然知道"之前在做什么"。
- **停止是护栏不是安全边界**:停止能终止本进程的 LLM 调用与循环,**不保证**外部副作用(已写出去的文件、已发出的网络请求)被回滚——那是 Docker(威胁模型 B)/ 用户自管 git 的事。文档要讲清这条边界。
- **取消只在"合法边界"生效**(优雅中断时保证 `messages` 对 API 合法):① **模型输出中途**(流式逐 chunk)——此时尚未把 assistant 消息 append 进 `messages`,丢弃半截输出、`messages` 停在上一条干净边界;② **下一步开头**(一批工具执行完之后)。**不在一批工具执行中途打断**(避免出现"assistant 有 tool_calls 但缺部分 tool 结果"的非法序列;长工具的中断不在本片范围)。**取消粒度对标 Cursor**:Cursor 的 Stop 也是切断模型生成(mid-token)、且**不杀正在跑的工具/终端进程**(论坛多次确认 Stop "only halts model generation, not the tool process",硬挂工具需手动 kill)——我们"工具批次跑完才停"反而比 Cursor 更可预测、不留悬挂进程;无任何主流 GUI agent 做"任意中途 bit-exact 打断"。
- **崩溃恢复靠 write-ahead(决策③ = Tier B,人 2026-06-08)**:优雅中断停在合法边界、不留悬挂 tool_use;但**硬崩溃**(kill -9 / 断电 / OOM)进程瞬死、任何"中断时存档"代码都来不及跑,只能靠**每步完成即落盘**扛——故采用 **per-step 原子写**(写临时文件 + `os.replace`,仍单文件、不迁 JSONL)+ 会话 `status`(回合干净结束才置 `complete`,载入时非 `complete` = 被中断)。resume 时若历史含**悬挂 `tool_use`**(只有硬崩溃在工具批次中途死掉才会产生),注入合成 error `tool_result` 修复以保证 API 合法。**对标**:Claude Code 用 JSONL 双写(每条消息即时 append + 回合 flush)、resume 时对"有 `tool_use` 缺 `tool_result`"注入合成 tool_result;LangGraph 用 per-superstep checkpoint + `next`/pending 标记(其"仅退出时持久化"模式文档明说无法从崩溃恢复)。即:**结构性标记(悬挂 tool_use)是主信号,`status` 状态位是显式补充**;模型那侧靠上下文自明,不需专门提示。
- **重问是破坏式截断,不是 fork**:按需求"提示会丢失后续对话、确认后从修改点重生",即**覆盖**该 session(丢掉后续),不另存分支。fork(保留两条分支)是后续可选项,不在本片。
- **CLI 只做停止/继续,不做重问**:见 §1 决策④(对标 Claude Code CLI 结论)。

## 1. 已拍板决策(人 2026-06-08;§4 详列)

- **① 取消机制(接受)**:一根协作式取消令牌(`threading.Event` 或 `cancelled() -> bool`)从入口穿到 `loop.run` → 范式循环 → `client.stream`。范式在每步开头(挨着 budget 检查)查一次;`stream` 在逐 chunk 循环里查一次,命中即 `close()` 流并 break。`complete`(非流式)无法中途打断单次阻塞调用,取消在下一步边界生效(Web 默认流式,故影响小)。粒度对标 Cursor(切模型生成 + 不杀工具进程,见 §0)。
- **② 停止入口(显式端点 + 断连兜底)**:**Web** = 显式 `POST /chat/{run_id}/stop`(配 `app.state.runs` 取消令牌表)+ 前端把发送按钮换成停止按钮、点击后调该端点并 `es.close()`;**外加**"浏览器断连即取消"兜底(SSE 生成器侧检测断连 → 置位同一令牌),覆盖关页/网络掉线。**CLI** = SIGINT 处理器(首个 Ctrl+C 置位令牌→优雅停+存档;再按一次→恢复默认处理器硬退出)。
- **③ 继续语义(Tier B:崩溃安全)**:① 优雅中断把进行中 `messages` 存进**同一 session**;② **per-step 原子 write-ahead**(每步完成 `os.replace` 重写单文件)+ 会话 `status`(干净结束才置 `complete`)以扛硬崩溃;③ resume 时对悬挂 `tool_use` 注入合成 error `tool_result` 修复合法性。下次任意发送即带全部上下文续上,LLM 靠上下文自明"之前在做什么"(不强制注入提示;`status`/`stopped` 主要给 UI 与崩溃检测用)。
- **④ 重问(Web 专属)**:破坏式截断重生(确认丢后续)。**CLI 不做**(对标 Claude CLI 重问靠复杂 rewind TUI,按"支持但复杂→不做",见 §4④)。
- **⑤ 重问 = 破坏式截断**(覆盖、丢后续),不做 fork。

## 2. 交付物

### 取消令牌脊柱(核心循环 + LLM client)
- 产物 `harness/paradigms/{agent,plan,ask}.py`(模板,三处同构)— `run()` 加 `cancel: Callable[[], bool] | None = None`;每步开头(挨着 budget 检查)`if cancel and cancel(): stop_reason="interrupted"; break`;把 `cancel` 透传进 `client.stream(..., cancel=cancel)`;`stop_reason="interrupted"` 时不 append 合成答案(沿用现有"仅 final 才 append"逻辑)。
- 产物 `harness/loop.py`(模板)— `run()` 加 `cancel` 参数并透传给范式。
- 产物 `harness/llm.py`(模板)— `LLMClient` Protocol + `OpenAIClient` 的 `stream`/`complete` 加 `cancel` 形参;`stream` 持有 stream 对象、逐 chunk `if cancel and cancel(): stream_obj.close(); break`,返回已组装的半截 `LLMResponse`(由范式在 break 前丢弃)。`complete` 接形参但文档注明无法中途打断(下一步边界生效)。`MockLLM` 同步加 `cancel` 形参(可在流式 mock 里模拟"停在第 N 个 token"以供测试)。

### 停止入口
- 产物 `interfaces/web.py`(模板)— `create_app` 加 `app.state.runs: dict[str, threading.Event]`(+ 一把锁);`_chat_events` 生成 `run_id`、建 `cancel = Event()`、注册并**首发 `event: run {run_id}`**,worker 把 `cancel.is_set` 传进 `run_loop(cancel=...)`;中断时 worker 仍 `session_store.save(部分 messages, status="interrupted")` 并发 `event: stopped`;`finally` 注销 `run_id`。新增 `POST /chat/{run_id}/stop` → 置位对应 `Event`(未知 id 幂等 200)。**断连兜底**(决策②):SSE 生成器侧检测客户端断连(`Request.is_disconnected()` 轮询 / 生成器 `GeneratorExit`)→ 置位同一 `Event`,覆盖关页/掉线。
- 产物 `interfaces/cli.py`(模板)— `run`/`chat` 跑循环时装 SIGINT 处理器置位 `cancel` 令牌(不抛异常);`run_loop(cancel=...)` 返回 `stop_reason="interrupted"` 时正常 `session_store.save`(标 `interrupted`)+ 打印"已停止,下次发送即可继续(或 `--resume <id>`)";二次 Ctrl+C 恢复默认处理器硬退出。

### 继续(Tier B:崩溃安全)
- 产物 `harness/session.py`(模板)— ① 记录加 `status: "running" | "complete"`(+ 可选 `interrupted` 派生);`save` 接 `status`,**原子写**(写 `.<id>.json.tmp` + `os.replace`,杜绝半写损坏)。② 新增 `checkpoint(session_id, messages, dir)` = per-step write-ahead(每步完成即以 `status="running"` 原子重写);回合干净结束 `save(..., status="complete")`。③ 新增 `repair_orphan_tool_results(messages) -> messages`:扫描 assistant `tool_calls` 缺失的 `tool_call_id`,补一条合成 `{"role":"tool", "tool_call_id":..., "content":"ERROR: interrupted"}`;`load`/`resolve` 载入时若 `status!="complete"` 或检出悬挂 tool_use 即调用它修复。
- 产物 `harness/paradigms/{agent,plan,ask}.py` 或经 hook — 每步完成调用 `session.checkpoint(...)`(write-ahead)。最薄做法:复用现成 `before_step(step, messages)` 挂点写盘,核心循环零侵入;若挂点拿不到 session 句柄则在范式末加一行 checkpoint 调用。
- 续接:复用现成 `--continue`/`--resume`/Web 续聊;LLM 靠上下文自明,**不强制注入"被中断"提示**(决策③:`status`/`stopped` 主要给 UI 与崩溃检测;如后续想要提示,留作运行期 `sessions` 旋钮)。Web `event: stopped` 让前端把"停止"渲染成可继续状态。

### 重问(Web 专属)
- 产物 `harness/session.py`(模板)— 加 `turns(messages) -> list[dict]`(派生 user 消息边界:序号 + 预览)与 `truncate_to_turn(messages, n) -> list[dict]`(截到第 n 个 user 回合之前)。
- 产物 `interfaces/web.py`(模板)— `/chat` 加可选 `edit_turn: int`(要替换/重生的 user 回合序号):载 session → `truncate_to_turn` → 以编辑后的 message 作新一轮 → 跑完**覆盖**保存(丢后续)。
- 产物 `interfaces/web_index.html`(模板)— 回放区每条历史 user 消息加"编辑"控件→就地变 textarea→点发送→**页面内联**确认条("会丢失后续对话",主题化,**不用 `window.confirm`**,沿用 Slice 8 §4b 重命名/删除的内联确认范式)→确认后带 `edit_turn` 发起 `/chat`、清掉该点之后的回放。
- 流式期间:发送按钮↔停止按钮切换(记 `currentRunId` + `es`);停止点击 `POST /chat/{run_id}/stop` + `es.close()`。

### 边角 + 测试 + 文档
- `config.yaml`(模板)— 尽量零新增旋钮;`sessions:` 块下加 `status`/write-ahead 行为注释。
- 产物 `AGENTS.md` / `README.md`(模板)— 停止/继续/重问用法 + "停止是护栏非回滚"边界 + "CLI 无重问" + "崩溃后 resume 自动修复未完成回合"。
- `tests/test_web.py`(模板)— `POST /stop` 置位→`stopped` 事件 + 部分 messages 落盘可续;断连→取消;`edit_turn` 截断重生覆盖 session;`run` 事件带 `run_id`。
- `tests/test_sessions.py`(模板)— `turns`/`truncate_to_turn` 边界;`status` 存取 + 原子写;`repair_orphan_tool_results` 给悬挂 tool_use 补合成 tool_result;`load` 对非 `complete`/悬挂自动修复。
- 产物 `tests/test_harness.py`(模板)— mock 流式在第 N token 触发 `cancel` → 循环 `stop_reason="interrupted"`、`messages` 合法;**模拟硬崩溃**(跑到中途不调 `save`、只留 `checkpoint` 写的文件)→ `load` + 修复后历史对 API 合法、可续。
- 子文档(本文)+ `00-overview §2` Slice 9 行回填 + mermaid/切分说明同步。

## 3. 退出门禁(实现后逐项勾)

- [x] **黄金路径**:preset/web 生成 → `uv sync && pytest`(含停止/重问用例)绿 → mock 跑通一次工具调用。
- [x] **停止终止全链路**:mock 流式中途 `cancel` → 范式 `stop_reason="interrupted"`、`stream_obj.close()` 被调用(`test_openai_client_stream_closes_on_cancel`)、半截输出被丢弃;`messages` 对 API 合法(无 assistant-tool_calls 缺结果)。
- [x] **停止后可继续**:中断后 session 存了合法部分 messages(status `interrupted`);`--continue`/Web 续聊第二轮上下文含原问题 + 已完成工具步骤(LLM "知道之前在做什么")。
- [x] **崩溃恢复(Tier B)**:per-step `checkpoint` 原子写(`_atomic_write` 写 `.tmp`+`os.replace`);模拟硬崩溃(只留 checkpoint、不调 `save`)后 `load` 检出 `status!="complete"`、`repair_orphan_tool_results` 补齐悬挂 tool_use → resume 历史对 API 合法、可续(`test_crash_recovery_via_checkpoint_is_resumable` + `test_load_repairs_uncleanly_finished_session`)。
- [x] **Web 停止按钮 + 断连**:`run` 事件带 `run_id`;`POST /chat/{run_id}/stop` 置位→`stopped`→流结束(`test_stop_interrupts_run_and_saves_resumable_partial`);断连(`GeneratorExit`)亦触发取消;按钮流式期切停止、结束复原(`setStreaming`)。
- [x] **CLI Ctrl+C**:首个 SIGINT 优雅停(`_interruptible` 置位 cancel 令牌)+ 存档 + 提示;二次恢复默认处理器硬退出;非主线程降级为不可中断(可预测)。
- [x] **重问截断重生(Web)**:`edit_turn` 截到该 user 回合前(`truncate_to_turn`)→ 编辑后问题重生 → 覆盖 session(后续丢弃)(`test_reask_edit_turn_truncates_and_regenerates`);前端内联确认(`beginReask`/`confirmReask`)、不出现 `window.confirm`/`window.prompt`。
- [x] **关闭/未触发仍薄**:`sessions.enabled=false` 时停止仍能终止(只是不存档可续,cancel 不依赖 sessions);无重问入口(`edit_turn` 仅在 sessions 开启时生效);不新增运行期依赖(`threading`/`signal` stdlib;golden `uv.lock` FORBIDDEN 断言不含 langchain/langgraph/adk)。
- [x] **大改动回归**(动范式核心 + `llm.py` + 跨 ≥3 文件):golden 全量 10 + Docker build/run mock 全绿。
- [x] `ReadLints` clean。

## 4. 人审决策点(已于 2026-06-08 签字)

- [x] **① 取消粒度 = 步/chunk 边界(接受)**:协作式取消令牌穿 loop→client、流式逐 chunk 检查 + `close()`、工具批次跑完不中途打断、`complete` 不可中途取消(下一步边界生效)。**取证:对标 Cursor**——Stop 只切模型生成、不杀工具进程(无 GUI agent 做 bit-exact 中途打断),我们更可预测。
- [x] **② Web 停止入口 = 显式 `POST /chat/{run_id}/stop` + run 注册表,并加"断连即取消"兜底**(覆盖关页/掉线)。
- [x] **③ 继续 = Tier B(崩溃安全)**:per-step 原子 write-ahead + `status` 标记 + resume 修复悬挂 `tool_use`;**不强制注入"被中断"提示**(模型靠上下文自明,标记给 UI/崩溃检测)。**取证:Claude Code** JSONL 双写 + 修复缺失 tool_result;**LangGraph** per-superstep checkpoint + `next`/pending 标记(仅退出持久化模式无法扛崩溃)。
- [x] **④ CLI 重问 = 不做**:Claude Code CLI **支持**重问,但实现为 `Esc Esc` / `/rewind` 的**交互式 rewind 菜单**(方向键选历史 prompt + 多种 restore 模式 + checkpoint 联动)——属"支持但需复杂 TUI 实现"。按规则(支持但复杂→不做),**CLI 不做重问**,仅 Web 做。
- [x] **⑤ 重问 = 破坏式截断重生(覆盖、丢后续)**,不做 fork 分支。
- **软确认(非阻塞,`CLAUDE.md §5.3`)**:`run_id` = `uuid4().hex[:12]`(同 session/trace 风格);`turns` 以 user 消息下标派生(零额外存储);停止后丢弃半截模型输出(已流式显示的 token 视为临时、续接时重生);write-ahead 仍用单文件原子写(不迁 JSONL,保持薄)。

## 5. 注意 / 留给后续

- **停止 ≠ 回滚副作用**:停止只断 LLM/循环,已发生的工具副作用要靠 Docker / 用户 git。这与已撤销的 T1-C(文件级回滚)是两个层面——本片不碰文件。
- **工具批次中途不可打断**:长跑工具(如 shell)的中途中断不在本片;取消在该工具批次完成后、下一步开头生效。
- **fork(保留分支)** 是重问的自然延伸(新 session id + 截断复制 + 父链),本片不做;若后续要做,`turns`/`truncate_to_turn` 已可复用。
- **与 Slice 10 HITL 的关系**:两者都挂在循环边界,但 Slice 9 是"事后停/续/改",Slice 10 是"事前逐次放行";不再像旧 Checkpoints 那样需要配对共建,各自独立。
