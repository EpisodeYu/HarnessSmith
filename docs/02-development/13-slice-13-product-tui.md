# 02·13 - Slice 13:产物 TUI(全屏终端 agent)

> 目标:给生成产物加一个**可选的、自持的全屏终端 TUI 接口**——基于 **Textual**,对标 Claude Code CLI / Cursor CLI / OpenCode:**默认进连续对话**、内置一个**与 Web `/config` 全字段对齐**的配置面板、**未配 LLM 时引导进入 config 配 LLM**。spec 开关 `interfaces.tui` 控制是否生成,**关掉则产物零 TUI 痕迹、不含 textual 依赖**。与 `interfaces.web` 同级;默认产物仍是 Slice 1 的薄核心(`coding-assistant` preset / example 保持 `tui: false`)。
>
> 前置:Slice 12 门禁全绿。
>
> 本片是**前瞻设计**,尚未随产物实现;其余切片均为已落地能力。
>
> **红线提醒**:Textual 是**通用终端 UI 库**(Rich 作者出品的 TUI 框架),**非 agent 编排框架**,不违定位红线;且仅在 `interfaces.tui=true` 时进产物依赖。本片改 `HarnessSpec.interfaces` schema(新增 `tui` 字段)= `CLAUDE.md §6.1`;给可选接口加重依赖 `textual` = `CLAUDE.md §6.2`——两项均需人审。

## 0. 边界与口径

- **第三个可选接口**:`interfaces`(`cli` / `web` / **`tui`**)互不强制;`cli` 恒在(`run` 单轮 + `chat` 纯文本 REPL 作回退),`web`/`tui` 各自 opt-in。默认产物(全关结构)仍是薄 CLI。
- **TUI 内只有连续对话**:TUI 启动即进持久 chat,不做单轮模式;单轮 `run` 仍由 CLI 提供。保留纯文本 `chat`/`run` 作 TUI 不可用(哑终端 / 无 TTY)时的回退。
- **复用产物 harness 层、不走 HTTP/SSE**:TUI 直接回调驱动 `harness.loop.run`(`on_delta`/`on_thinking`/`cancel`/`checkpoint`),复用 `harness.config`(`load_config`/`Config.model_validate`/`save_config`/`set_env_value`)、`harness.session.*`、`harness.llm.ClientRouter`、`harness.interaction`(`using_asker`/`using_confirmer`)、`harness.mcp`、`harness.extensions`/`hooks`。
- **线程模型(对标 OpenCode)**:agent loop 跑在 **Textual 线程 worker**(`@work(thread=True)`),UI 线程只渲染 / 收输入;`on_delta`/`on_thinking` 经 `call_from_thread` 推 UI;HITL / `ask_question` 模态经 `threading.Event` 跨线程阻塞 worker 等用户答复。
- **配置面板 = 与 Web `/config` 全字段对齐**:LLM(profile + 采样 advanced + pricing + 写 key/base_url 到 `.env` + 测连通)/ roles / context / budget / tools(本地 + MCP allowlist)/ MCP server 增删改 / prompts + rule files / paradigms / observability / memory。改完 `Config.model_validate` 校验 + `save_config` **保注释**写回 `config.yaml`。
- **未配 LLM 判据**复用 Web 的 `any(p.model.strip() for p in cfg.llms)` → TUI 显示 banner 引导进 config 配 LLM(不做引导式问答,只提示进配置页)。
- **启动优先级 `tui > web > chat`**:一键脚本与裸命令在 `interfaces.tui=true` 时默认进 TUI,即使同时开了 web 也以 TUI 为先(web 仍可手动 `serve`)。

## 1. 交付物

生成器侧(`harnessmith/`):

- `spec.py` — `Interfaces` 新增 `tui: bool = False`(仿 `web`;`HarnessSpec.interfaces` 不改)。
- `generator.py` — `CONDITIONAL_TEMPLATES` 新增 `interfaces/tui.py.j2`、`tests/test_tui.py.j2`(谓词 `spec.interfaces.tui`)。
- `pyproject.toml.j2` — `{% if interfaces.tui %}` 加 **textual**(实现时用 uv 添加最新版);`ruamel.yaml` 门控由 `{% if interfaces.web %}` 改为 `{% if interfaces.web or interfaces.tui %}`(TUI 配置写回需要)。
- `config.py.j2` — `save_config`/`_deep_merge_into` 门控扩到 `web or tui`。
- `cli.py.j2` — `{% if interfaces.tui %}` 加 `@app.command() def tui(...)`;`_main` 回调改 `invoke_without_command=True`,无子命令且 tui 开启时进 TUI(裸命令默认)。
- `__launch_name__.{sh,bat}.j2` — action 优先级 `{% if interfaces.tui %}tui{% elif interfaces.web %}serve --open{% else %}chat{% endif %}`。
- 向导(Web + CLI)与启动脚本加 `interfaces.tui` 开关;`examples/spec.yaml` / `presets/coding-assistant/spec.yaml` 显式 `tui: false`(守薄默认)。
- `README.md.j2` / `AGENTS.md.j2` — TUI 启动说明 + layout。

生成产物侧(`interfaces.tui` 门控):

- `src/<pkg>/interfaces/tui.py` — Textual App:
  - `ChatScreen`(默认):流式消息区 + 输入框 + 状态栏(model / paradigm / steps / tokens / cost)+ 工具调用内联渲染 + 未配 LLM banner;slash 命令(`/config /sessions /new /model /mode /mcp /help /quit`)或命令面板;Stop(Esc)接 `cancel`;session resume + checkpoint。
  - `ConfigScreen`(全字段对齐 Web /config):LLM/roles/context/budget/tools/MCP/prompts+rules/paradigms/observability/memory;`Config.model_validate` + `save_config` 写回;`set_env_value` 写 `.env`(write-only)。
  - 模态:HITL 确认(`ToolConfirmer`)、`ask_question`(`TextualAsker`)、session/model/mode picker。
- `tests/test_tui.py` — 用 Textual `App.run_test()` pilot + MockLLM(无 key/网络):启动进 ChatScreen、未配 LLM banner、开 config 面板、mock 跑通一轮流式、(选)HITL/ask 模态往返。
- `README.md` / `AGENTS.md` — TUI 用法 + "textual 仅 `tui: true` 时存在"。

## 2. 任务拆解

### 2.1 门控与依赖(生成器)
`CONDITIONAL_TEMPLATES` 加两条;`pyproject.toml.j2` 加 `textual`(tui)+ `ruamel.yaml` 门控扩到 `web or tui`;`config.py.j2` 的 `save_config` 同步扩门控。门禁硬要求:`tui=false` 时 `pyproject`/`uv.lock`/`requirements.txt` 三处均不含 `textual`,无 `interfaces/tui.py`/`tests/test_tui.py`,CLI 无 `def tui`。

### 2.2 TUI 骨架 + ChatScreen(线程模型)

```mermaid
flowchart LR
  subgraph uiThread [Textual UI thread]
    App[TuiApp]
    Chat[ChatScreen]
    Config[ConfigScreen]
    Modals[Confirm/Ask/Picker 模态]
  end
  subgraph worker [thread worker]
    Loop["loop.run(...)"]
  end
  Chat -->|"send @work(thread)"| Loop
  Loop -->|"on_delta/on_thinking via call_from_thread"| Chat
  Loop -->|"using_asker/using_confirmer"| Modals
  Modals -->|"threading.Event 回传答案"| Loop
  Config -->|"load_config/model_validate/save_config/set_env_value"| Cfg[(config.yaml/.env)]
```

worker 跑 sync `loop.run`,流式经 `call_from_thread` 推进消息区;Stop 设 `cancel` 令牌(复用 Slice 9 协作式取消);session resume / checkpoint 直接用 `harness.session`;paradigm 切换走 `config.paradigms`。未配 LLM:`any(p.model.strip() for p in cfg.llms)` 为假时显 banner + 禁输入。

### 2.3 跨线程模态(HITL + ask_question)
`TextualConfirmer` / `TextualAsker` 实现 `harness.interaction` 的协议:被 worker 线程调用时 `call_from_thread` 推模态,`threading.Event`/队列阻塞 worker 等 UI 回传答案(对齐 Slice 10 的 asker/confirmer 底座)。session/model/mode picker 同款模态。

### 2.4 ConfigScreen 全字段对齐
各 section 对应 Web `/config` 同名分区(字段范围见 Slice 3 + Slice 7 分页 + Slice 11 MCP 管理 + Slice 8B memory tab);改完统一 `Config.model_validate` → `save_config(updates, path)` 保注释写回;key/base_url 经 `set_env_value` 写 `.env`(不回显);MCP server 增删改复用 Slice 11 的 `save_config` + 热重连路径。

### 2.5 入口 / 启动脚本 / 裸命令
`cli.py.j2` 加 `tui` 子命令 + `invoke_without_command=True` 裸命令默认(仅 tui 产物);`__launch_name__.{sh,bat}.j2` 优先级 `tui > web > chat`;README/AGENTS 同步。

## 3. 退出门禁

- **开 TUI 可跑(黄金路径)**:`interfaces.tui=true` 生成 → `uv lock` → `uv sync && pytest`(含 `test_tui.py` 用 `App.run_test()` pilot + mock 跑通一轮流式)→ 冒烟自检;`uv.lock` 含 `textual` + `ruamel`。
- **关 TUI 零痕迹**:`interfaces.tui=false` 产物不含 `interfaces/tui.py`/`tests/test_tui.py`,`pyproject`/`uv.lock`/`requirements.txt` 不含 `textual`,CLI 无 `def tui`,启动脚本默认 `chat`(或 web 时 `serve --open`)。
- **未配 LLM 引导**:`hasLLM` 为假时 ChatScreen 显 banner + 禁输入并指向 `/config`;配好 model(+key)后对话可流式。
- **配置面板全字段**:各 section 改值 → `Config.model_validate` 校验(非法拒)→ `save_config` 保注释回写;`set_env_value` 写 `.env`(write-only);面板/事件/trace/日志均不出现明文 key。
- **HITL / ask_question 模态**:TUI 中弹出 → 回传 → 答案进 loop / `tool_result`(headless pilot)。
- **启动优先级**:`tui` 产物一键脚本 + 裸命令默认进 TUI(`tui > web > chat`)。
- **大改动回归**(改 schema + 跨 ≥3 文件):golden 全量 + Docker 冒烟 + `uvx harnessmith new` 冒烟;无框架断言。
- `ReadLints` clean;**对外可读(人审)**:真起 `<pkg> tui` 走查对话流式 / 工具内联 / config 全字段改并写回 / 未配 LLM 引导 / HITL/ask 模态 / 中英文案。

## 4. 关键决策

- **① 技术栈 = Textual 全屏 TUI**(目标「真的像 Claude CLI / Cursor CLI / OpenCode」)。
- **② 新增 `HarnessSpec.interfaces.tui`(改 schema,`CLAUDE.md §6.1`)**:opt-in、默认关、关掉零痕迹,与 `web` 同模式。
- **③ 产物加重依赖 `textual`(`CLAUDE.md §6.2`)**:仅 `tui: true` 时进产物依赖;`ruamel` 门控随之扩到 `web or tui`。
- **④ 配置面板 = 与 Web `/config` 全字段对齐**(代价:`tui.py` 体量大 + 双面字段一致性维护承诺)。
- **⑤ 入口 = opt-in + 终端优先**:启用后一键脚本/裸命令默认进 TUI,保留 `chat`/`run` 回退,web+tui 同开时脚本以 tui 为先。
- **⑥ TUI 内只连续对话**(无单轮模式;单轮仍由 CLI `run` 提供)。
- **⑦ 未配 LLM = 提示进 config**(不做引导式问答,只 banner 引导进配置页)。
- **⑧ 对外可读(实现后真实验收)**。

## 5. 本 slice 注意

- **薄**:默认产物(`tui: false`)必须与开此片前完全一致、零新增依赖、零 TUI 文件;`tui.py` 作为 opt-in 接口允许较大体量(类比 `web.py`),但不引 agent 编排框架。
- **双面维护**:TUI 配置面板与 Web `/config` 全字段对齐 = 一项双 UI 一致性维护承诺;后续 spec/config 字段演进时两面同步。
- **跨线程是主风险**:worker 跑 sync loop、`call_from_thread` 推流、HITL/ask 用 `Event` 阻塞 worker 等答复——本片首要工程风险,先打通对话主链路再铺配置面板。
- **密钥红线**(`CLAUDE.md §6.5`):配置面板、模态、trace、日志任一路径出现明文 key 即失败;面板只可见 env 引用名,key/base_url 经 `set_env_value` 只写 `.env`、不回显。
- **不绑框架**:Textual 是通用 TUI 库,非 agent 编排框架,仅在 `tui=true` 时进产物。
- **测试 headless 可跑**:Textual `App.run_test()` pilot 无需真 TTY,`smoke_check` 的 `pytest` 在生成仓库内可跑(CI 友好)。
