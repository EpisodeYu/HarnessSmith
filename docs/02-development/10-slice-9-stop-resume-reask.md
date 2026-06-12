# 02·10 - Slice 9:停止 / 继续 / 重问(会话时间旅行)

> 目标:在 Slice 8 会话落盘之上补齐事实标准 harness 的**交互控制三件**——**停止**(回合跑到一半喊停、连 LLM 思考/输出一并终止)、**继续**(停止 / Ctrl+C / 断网中断后,下次发送时 LLM 仍知道之前在做什么、可接着干)、**重问**(Web 点任意历史提问就地编辑、确认丢弃后续后从该点重生)。三者共用一根「协作式取消令牌」+ session 截断,统称会话级时间旅行。
>
> 前置:Slice 8 门禁全绿。
>
> **薄/红线**:零新增依赖(`threading` / `signal` 均 stdlib);纯运行期机制,不改 spec schema、不改 LLM API 面(取消只是给 `stream`/`complete` 加一个协作检查,不动 Chat Completions 选型);属大改动(动范式核心循环 + 跨 `agent/plan/ask` + `llm.py` + `web.py`/前端 + `cli.py`,跑全量回归)。

## 0. 边界与口径

- **会话本身就是可续状态**:`harness/session.py` 已把整段 `messages` 正文落盘(Slice 8)。「继续」不是新存储,而是「中断时把进行中的 `messages` 存到一个合法边界」,之后沿用现成 `--continue`/`--resume`/Web 续聊即可——LLM 看到原问题 + 已完成的工具步骤,天然知道「之前在做什么」。
- **停止是护栏不是安全边界**:停止能终止本进程的 LLM 调用与循环,**不保证**外部副作用(已写出去的文件、已发出的网络请求)被回滚——那是 Docker(威胁模型 B)/ 用户自管 git 的事。
- **取消只在「合法边界」生效**(优雅中断时保证 `messages` 对 API 合法):① 模型输出中途(流式逐 chunk)——丢弃半截输出、`messages` 停在上一条干净边界;② 下一步开头(一批工具执行完之后)。**不在一批工具执行中途打断**(避免出现「assistant 有 tool_calls 但缺部分 tool 结果」的非法序列)。**取消粒度对标 Cursor**:Stop 切断模型生成(mid-token)、不杀正在跑的工具/终端进程;我们「工具批次跑完才停」反而更可预测、不留悬挂进程。
- **崩溃恢复靠 write-ahead(Tier B)**:优雅中断停在合法边界、不留悬挂 tool_use;但**硬崩溃**(kill -9 / 断电 / OOM)进程瞬死,只能靠**每步完成即落盘**扛——故采用 **per-step 原子写**(写临时文件 + `os.replace`,仍单文件)+ 会话 `status`(回合干净结束才置 `complete`,载入时非 `complete` = 被中断)。resume 时若历史含悬挂 `tool_use`,注入合成 error `tool_result` 修复以保证 API 合法。结构性标记(悬挂 tool_use)是主信号,`status` 状态位是显式补充;模型那侧靠上下文自明,不需专门提示。
- **重问是破坏式截断,不是 fork**:覆盖该 session(丢掉后续),不另存分支。fork 是后续可选项。
- **CLI 只做停止/继续,不做重问**:见 §1 决策④。

## 1. 关键决策

- **① 取消机制**:一根协作式取消令牌(`threading.Event` 或 `cancelled() -> bool`)从入口穿到 `loop.run` → 范式循环 → `client.stream`。范式在每步开头(挨着 budget 检查)查一次;`stream` 在逐 chunk 循环里查一次,命中即 `close()` 流并 break。`complete`(非流式)无法中途打断单次阻塞调用,取消在下一步边界生效(Web 默认流式,故影响小)。
- **② 停止入口(显式端点 + 断连兜底)**:Web = 显式 `POST /chat/{run_id}/stop`(配 `app.state.runs` 取消令牌表)+ 前端发送按钮换停止按钮 + 「浏览器断连即取消」兜底(SSE 生成器侧检测断连 → 置位同一令牌)。CLI = SIGINT 处理器(首个 Ctrl+C 置位令牌→优雅停+存档;再按一次→硬退出)。
- **③ 继续语义(Tier B:崩溃安全)**:① 优雅中断把进行中 `messages` 存进同一 session;② per-step 原子 write-ahead + 会话 `status`;③ resume 时对悬挂 `tool_use` 注入合成 error `tool_result` 修复合法性。下次任意发送即带全部上下文续上,LLM 靠上下文自明(不强制注入提示)。
- **④ 重问(Web 专属)**:破坏式截断重生(确认丢后续)。CLI 不做(Claude CLI 重问靠复杂 rewind TUI,按「支持但复杂→不做」)。
- **⑤ 重问 = 破坏式截断**(覆盖、丢后续),不做 fork。

## 2. 交付物

### 取消令牌脊柱
- 产物 `harness/paradigms/{agent,plan,ask}.py`(三处同构)— `run()` 加 `cancel: Callable[[], bool] | None = None`;每步开头 `if cancel and cancel(): stop_reason="interrupted"; break`;透传进 `client.stream(..., cancel=cancel)`;`stop_reason="interrupted"` 时不 append 合成答案。
- 产物 `harness/loop.py` — `run()` 加 `cancel` 并透传。
- 产物 `harness/llm.py` — `LLMClient` Protocol + `OpenAIClient` 的 `stream`/`complete` 加 `cancel` 形参;`stream` 逐 chunk `if cancel and cancel(): stream_obj.close(); break`,返回已组装的半截 `LLMResponse`(由范式 break 前丢弃)。`MockLLM` 同步加 `cancel`。

### 停止入口
- 产物 `interfaces/web.py` — `create_app` 加 `app.state.runs: dict[str, threading.Event]`(+ 锁);`_chat_events` 生成 `run_id`、建 `cancel`、首发 `event: run {run_id}`,worker 把 `cancel.is_set` 传进 `run_loop`;中断时 worker 仍 `save(部分 messages, status="interrupted")` 并发 `event: stopped`;`finally` 注销 `run_id`。`POST /chat/{run_id}/stop` 置位对应 `Event`(未知 id 幂等 200)。断连兜底(`Request.is_disconnected()` / `GeneratorExit`)置位同一 `Event`。
- 产物 `interfaces/cli.py` — `run`/`chat` 装 SIGINT 处理器置位 `cancel`(不抛异常);返回 `interrupted` 时正常 `save`(标 `interrupted`)+ 打印「已停止,下次发送即可继续」;二次 Ctrl+C 硬退出。

### 继续(Tier B:崩溃安全)
- 产物 `harness/session.py` — ① 记录加 `status: "running" | "complete"`;`save` 接 `status`,**原子写**(写 `.tmp` + `os.replace`)。② 新增 `checkpoint(session_id, messages, dir)` = per-step write-ahead(每步完成以 `status="running"` 原子重写)。③ 新增 `repair_orphan_tool_results(messages)`:扫描 assistant `tool_calls` 缺失的 `tool_call_id`,补合成 `{"role":"tool","tool_call_id":...,"content":"ERROR: interrupted"}`;`load`/`resolve` 载入时若 `status!="complete"` 或检出悬挂 tool_use 即修复。
- 产物 `harness/paradigms/*` 或经 hook — 每步完成调用 `session.checkpoint(...)`。续接复用现成 `--continue`/`--resume`/Web 续聊。

### 重问(Web 专属)
- 产物 `harness/session.py` — `turns(messages)`(派生 user 消息边界:序号 + 预览)+ `truncate_to_turn(messages, n)`(截到第 n 个 user 回合之前)。
- 产物 `interfaces/web.py` — `/chat` 加可选 `edit_turn: int`:载 session → `truncate_to_turn` → 以编辑后的 message 作新一轮 → 跑完覆盖保存。
- 产物 `interfaces/web_index.html` — 回放区每条历史 user 消息加「编辑」控件→就地变 textarea→点发送→页面内联确认条(「会丢失后续对话」,不用 `window.confirm`)→确认后带 `edit_turn` 发起 `/chat`。流式期间发送按钮↔停止按钮切换。

### 边角 + 文档
- `config.yaml` 尽量零新增旋钮;`sessions:` 块下加 `status`/write-ahead 注释。
- 产物 `AGENTS.md` / `README.md`(停止/继续/重问用法 + 「停止是护栏非回滚」边界 + 「CLI 无重问」+「崩溃后 resume 自动修复未完成回合」)。
- `tests/test_web.py`、`tests/test_sessions.py`、`tests/test_harness.py`。

## 3. 退出门禁

- 黄金路径:preset/web 生成 → `uv sync && pytest`(含停止/重问用例)绿 → mock 跑通一次工具调用。
- 停止终止全链路:mock 流式中途 `cancel` → 范式 `stop_reason="interrupted"`、`stream_obj.close()` 被调用、半截输出被丢弃;`messages` 对 API 合法。
- 停止后可继续:中断后 session 存了合法部分 messages(status `interrupted`);`--continue`/Web 续聊第二轮上下文含原问题 + 已完成工具步骤。
- 崩溃恢复(Tier B):per-step `checkpoint` 原子写;模拟硬崩溃(只留 checkpoint)后 `load` 检出非 `complete` + `repair_orphan_tool_results` 补齐悬挂 tool_use → resume 历史对 API 合法、可续。
- Web 停止按钮 + 断连:`run` 事件带 `run_id`;`POST /chat/{run_id}/stop` 置位→`stopped`→流结束;断连亦触发取消。
- CLI Ctrl+C:首个 SIGINT 优雅停 + 存档 + 提示;二次硬退出;非主线程降级为不可中断。
- 重问截断重生(Web):`edit_turn` 截到该 user 回合前 → 编辑后问题重生 → 覆盖 session;前端内联确认(不出现 `window.confirm`/`window.prompt`)。
- 关闭/未触发仍薄:`sessions.enabled=false` 时停止仍能终止(只是不存档可续);无重问入口;不新增运行期依赖。
- 大改动回归(动范式核心 + `llm.py` + 跨 ≥3 文件):golden 全量 + Docker build/run mock。
- `ReadLints` clean。

## 4. 本 slice 注意 / 留给后续

- **停止 ≠ 回滚副作用**:停止只断 LLM/循环,已发生的工具副作用要靠 Docker / 用户 git。
- **工具批次中途不可打断**:长跑工具(如 shell)的中途中断不在本片;取消在该工具批次完成后、下一步开头生效。
- **fork(保留分支)** 是重问的自然延伸(新 session id + 截断复制 + 父链),本片不做;`turns`/`truncate_to_turn` 已可复用。
- **与 Slice 10 HITL 的关系**:两者都挂在循环边界,但 Slice 9 是「事后停/续/改」,Slice 10 是「事前逐次放行」;各自独立。
