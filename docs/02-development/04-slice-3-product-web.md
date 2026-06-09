# 02·04 - Slice 3:产物 Web(自持)

> 目标:给生成产物加一个**可选的、自持的 Web 接口**——FastAPI + **SSE 流式 chat** + **运行期 `/config` 配置面板**(决策④:行为性配置全可改)。spec 开关 `interfaces.web` 控制是否生成,**关掉则产物零 Web 痕迹、不含 fastapi/uvicorn 依赖**。属 `01-project-plan.md` 的 **L2**,**默认产物仍是 Slice 1 的薄核心**(`coding-assistant` preset 保持 `web: false`)。
>
> 前置:Slice 2 门禁全绿(已 ✅)。
>
> **状态:✅ 已完成(退出门禁 §3 全绿;§4 两项人审 2026-06-03 经真实 LLM 验收已签字通过)。** `uv run pytest` 41 fast green(+3:条件渲染开/关 + web_index 无残留 jinja)+ `uv run pytest -m golden` 4 green(新增 web 端到端:生成 web 产物 → `uv lock` → `uv sync` 装 fastapi/uvicorn/httpx → `run --mock` → 产物 `pytest` 含 `test_web.py` 的 SSE + `/config` 全绿)。`ReadLints` clean。本片首次给生成器引入"**按 spec 条件渲染文件**"的能力(`web.py`/`web_index.html`/`test_web.py`/web 依赖随 `interfaces.web` 开关进出),为 Slice 4(MCP)、Slice 5(wizard)复用。`HarnessSpec.interfaces.web` 字段 Slice 0 已预留 → **未改 schema,未触发 `CLAUDE.md §6.1`**。
>
> **实现说明(与计划的细化)**:① **Web 依赖落位**取方案 A——`web=true` 时 `fastapi`/`uvicorn` 直接进 `dependencies`(`uv sync`/Docker/`smoke_check` 零改动即装上),`web=false` 时整段不渲染;测试依赖 `httpx`(`fastapi.testclient` 需要)同样条件进 `[dependency-groups] dev`。② **`/config` 持久化**:本片初版做"面板改 → 进程内 `app.state.config` 生效、**不回写 `config.yaml`**"(理由见 §4)。**实现说明(2026-06-09 改判,人签字):改为回写 `config.yaml`**——用户反馈"每次重启 serve 都要重配"太反常识(尤其一键 wizard 产物 model 留空、key 落 `.env` 而 model 不落盘,重启后 chat 又被 gate)。当年"避免 dump 丢注释"的顾虑用 **`ruamel.yaml` 注释保留 round-trip** 解决:`save_config` 读现有文件 → deep-merge 可编辑字段 → 写回,块级/字段注释与"被注释的可选项菜单"保留(列表 llms/tools 被整体替换时其元素行内注释会丢,可接受);`ruamel.yaml` 仅随 `interfaces.web` 进产物依赖(默认薄核心不含)。详见 §4 软确认结论。③ **SSE = token 级流式 + 进度事件,且可选**(人 2026-06 追加要求,UX 关键):给 `LLMClient` 增 `stream(messages, tools, on_delta)`(Chat Completions `stream=True`,累积 content/tool_calls/usage 并逐 token 回调;仍是 Chat Completions,**未切 Responses / 未换 SDK**,不触发 `CLAUDE.md §6.4`);`loop.run()` 增可选 `on_delta`,有则走 `stream` 否则 `complete`(`loop.py` 仅 +4 行,实测 180 行仍在 150–300 薄区间)。流式开关在调用方:web `/chat?stream=`(默认开)+ 页面复选框、CLI `run --stream/--no-stream`(默认关,保留原行为)、库级传 `on_delta`。mock 端 `stream()` 复用 `complete()` 逐词发 token,离线可测。

## 1. 交付物

生成器侧(`harnessforge/`):

- `generator.py` — 新增**条件渲染机制**:按 spec 谓词跳过部分模板文件(`interfaces.web == false` 时不写 `web.py`、web 测试、web 静态页)。机制要可被后续 slice(MCP/wizard)复用,见 §2.1。
- `pyproject.toml.j2` — 用 `{% if spec.interfaces.web %}` 条件块加 Web 依赖(`fastapi` + `uvicorn`);**关掉则整段不渲染**(满足"关 Web 不含 fastapi/uvicorn"门禁)。依赖落位见 §2.2 决策。
- `smoke_check` / `Dockerfile.j2` / `README.md.j2` — 当 `web=true` 时,生成后冒烟 / 容器 / 文档要能装上并跑通 Web 依赖(`uv sync` 把 web 依赖纳入,见 §2.2)。
- 一份 **web-enabled 测试 fixture spec**(`interfaces.web: true`)供黄金 / 集成测试用;`coding-assistant` preset **保持 `web: false`**(golden 仍薄)。

生成产物侧——流式核心(**始终生成**,非 web 门控;为 token 级流式铺地基):

- `harness/llm.py` — `LLMClient` Protocol + `OpenAIClient` 增 `stream(messages, tools, on_delta)`:Chat Completions `stream=True`,逐块累积 content / tool_calls / usage,文本段回调 `on_delta`,返回与 `complete()` 同形的 `LLMResponse`。
- `harness/loop.py` — `run()` 增可选 `on_delta`;有则走 `client.stream(...)`、否则 `client.complete(...)`(其余逻辑不变,+4 行)。
- `harness/mock.py` — `MockLLM.stream()` 复用 `complete()` 后逐词回调 `on_delta`,离线可测流式。
- `interfaces/cli.py` — `run` 增 `--stream/--no-stream`(默认 `false`,保持 Slice 1 行为)。

生成产物侧——Web 接口(`harnessforge/templates/`,`interfaces.web` 门控):

- `src/<pkg>/interfaces/web.py` — FastAPI 应用,**薄**(实测 ≈ 139 行):
  - `GET /` — 单页前端(无构建,Tailwind CDN;`01-project-plan §6` 自主细节),含 chat 视图(带 stream 复选框)+ config 面板视图。
  - `GET /chat?message=&stream=`(SSE)— `Hooks` 子类 + 后台线程驱动 `loop.run()`,以 `text/event-stream` 推 `token`(默认开)/ `tool_call` / `tool_result` / `final` 事件(见 §2.3)。
  - `GET /config` / `POST /config` — 读 / 改**运行期行为性配置**(prompts / budget 数值 / tools.enabled / context 参数 / profile 采样旋钮 / 定价);**绝不读写密钥真值**(只可见 env 引用名,见 §5 安全)。结构性配置(接口/模块有无)不可改。
- `src/<pkg>/interfaces/web_index.html` — 单页前端(`{{ project_slug }}` 标题为唯一 jinja 变量)。
- `src/<pkg>/interfaces/cli.py` — 条件新增 `serve` 子命令(`uvicorn` 起 `create_app(...)`,默认 `127.0.0.1`,带 `--mock`)。
- `tests/test_web.py`(web 门控)— `/`、`/chat` SSE(token 流 / 非流两路)、`/config` 改配置生效 / 拒非法 / 不泄密的产物自带测试(`fastapi.testclient`)。
- `README.md` / `AGENTS.md` — 增 Web + 流式用法、`/config` 面板说明、"Web 依赖仅 `web: true` 时存在"。

## 2. 任务拆解

### 2.1 条件渲染机制(生成器核心,本片的新能力)
- 现状:`generator.generate()` **无条件**渲染 `templates/` 下每个文件。本片引入**spec 谓词门控**:某些模板文件仅在对应 spec 开关为真时才写出。
- 倾向实现(见 §4 软确认):在 `generator.py` 维护一张显式 `CONDITIONAL_TEMPLATES`(相对路径 → `predicate(spec) -> bool`),渲染循环里命中谓词且为假则 `continue` 跳过。显式、可读、Slice 4/5 直接复用。
- 注意空目录:`interfaces/` 在 `web=false` 时仍有 `cli.py`/`__init__.py`,不会空;若将来出现整目录被跳过,确保不写空目录。

### 2.2 Web 依赖落位(关掉必须不含)
- `pyproject.toml.j2`:`{% if spec.interfaces.web %}` 包裹 Web 依赖块。**门禁硬要求**:`web=false` 时 `pyproject.toml` / `uv.lock` / `requirements.txt` 三处均**不含** `fastapi`/`uvicorn`(沿用 Slice 1 的三处洁净断言风格)。
- **决定:进 `dependencies`(方案 A)**。两种都满足"关掉不含";区别在 `web=true` 时的安装路径:
  - A)✅ **已采纳**——直接进 `dependencies`:`uv sync` / Docker / `smoke_check` **零改动**即装上,最薄。偏离 `01-project-plan §5/§7` "进 extra" 的字面措辞,但兑现其真实意图("生成什么才依赖什么")。
  - B) 进 `optional-dependencies.web`:贴合 plan 字面,但 `web=true` 时 `smoke_check`、`Dockerfile`、README 都要带 `--extra web` 同步,改动面更大——未采纳。
  - 实测 `web=false` 时 `pyproject`/`uv.lock`/`requirements.txt` 三处均不含 `fastapi`/`uvicorn`/`httpx`(`httpx` 仅作 web 测试依赖随 dev 组进出)。

### 2.3 SSE 流式 chat(token 级 + 进度事件,可选)
- **进度事件**:web 层 `Hooks` 子类把 `tool_call/tool_result/step/error` 投递到线程安全队列;`loop.run()` 在后台线程跑,SSE 生成器从队列取事件并 `yield`,最后推 `final`(answer + stop_reason + 用量)。
- **token 级流式(人追加要求,已实现)**:`LLMClient.stream(messages, tools, on_delta)` 用 Chat Completions `stream=True` 累积 content/tool_calls/usage 并对每段文本回调 `on_delta`;`loop.run(on_delta=...)` 有回调即走 `stream`、否则 `complete`(核心逻辑不变,仅多一处分支)。web `on_delta` 把文本作 `event: token` 推入队列,前端逐字追加到当前回答行。
- **可选**:web `/chat?stream=`(默认 `true`)+ 页面 stream 复选框;CLI `run --stream/--no-stream`(默认 `false`,保持 Slice 1 行为);库级直接传 `on_delta`。关流式时退化为纯进度事件 + 单次 `final`。
- **流式下的预算/用量**:`stream_options.include_usage` 取末块 usage;provider 若不支持则 usage=0(cost/token 预算不触发,与"profile 无单价"同一注意点,已在注释/AGENTS 写明)。
- mock 后端 `stream()` 复用 `complete()` 逐词发 token:产物自带测试与冒烟全程 mock,**无 key 验证 token 流/非流两条路径**。

### 2.4 运行期 `/config` 面板(决策④:行为性全可改)
- 读:`GET /config` 返回当前 `Config` 的**行为性字段**(脱敏:只给 env 引用名,不给密钥真值)。
- 改:`POST /config` 用 Pydantic 重新校验后**更新进程内 `Config`**,**当场生效**(后续 `/chat` 用新值)。是否回写 `config.yaml` 持久化见 §4。
- **范围**:可改 = prompts / budget(steps/seconds/tokens/cost)/ tools.enabled(allowlist;高风险工具仍受 `tools.py` 风险标记约束)/ context(strategy/max_context_tokens/keep_last_turns)/ profile 采样(temperature/max_tokens)/ 定价。不可改 = 结构性(有无接口/模块、范式拓扑 = 代码,需重新生成)。
- **进阶热重载**(watch 文件、多进程一致性)= v1+(`00-overview §2` Slice 13+ 行),本片只做"面板改 → 进程内生效"。

## 3. 退出门禁(对应 `01 §8` Non-blocker,做到即验)

- [x] `/chat` SSE(mock 后端)产物自带测试:含工具调用进度事件(`event: tool_call`/`tool_result`)+ 末尾 `event: final` + answer;**默认 token 级流式**发 `event: token`,`?stream=false` 则无 token 仍有 final。(`test_web.py::test_chat_streams_tool_call_and_final_over_sse` / `test_chat_streams_answer_tokens_by_default` / `test_chat_stream_false_emits_no_tokens`)
- [x] **token 级流式核心**:`MockLLM.stream` 逐 token 发文且总和等于 content;`loop.run(on_delta=...)` 把最终回答按 token 流出(不含工具输出)。(产物 `test_harness.py::test_mock_stream_emits_tokens_matching_content` / `test_loop_on_delta_streams_final_answer`)
- [x] `/config` 改运行期配置**当场生效**测试:改 `prompts.system` 后同进程后续 `GET /config` 立即反映;非法值(`budget.max_steps: -1`)被 Pydantic 拒绝返 400。(`test_config_post_updates_runtime_config` / `test_config_post_rejects_invalid_value`)
- [x] `/config` **不泄露密钥**:响应只含 env 引用名(`api_key_env`),无密钥真值;POST 的 `secrets`/结构性 `project_slug` 键被忽略。(`test_config_get_exposes_names_not_secrets` / `test_config_post_ignores_structural_and_secret_keys`)
- [x] **关 Web 时薄验证**:`interfaces.web=false` 产物不含 `web.py`/`web_index.html`/`tests/test_web.py`,`pyproject` 不含 `fastapi`/`uvicorn`/`httpx`,CLI 无 `serve`;golden 另断言 `uv.lock` 不含。(`test_generator.py::test_web_disabled_omits_web_files_and_deps`)
- [x] **开 Web 时可跑**:web-enabled spec 生成 → `uv lock` → `uv sync && pytest` 全绿(含 `test_web.py`)→ 冒烟自检通过。(`test_golden.py::test_golden_web_enabled_generates_locks_and_smoke_passes`;`test_generator.py::test_web_enabled_generates_web_files_and_deps` 快测断结构 + `py_compile`)
- [x] **黄金路径回归(关 Web)**:`coding-assistant` preset(`web: false`)生成 → `uv sync && pytest` → mock 跑通一次工具调用,golden / docker / uvx 4 项全绿,产物依然零 agent 框架、依然薄。
- [x] `web.py` 体量符合"薄"(实测 ≈ 120 行含 docstring;HTML 单页另置 `web_index.html`,不计入核心逻辑)。
- [x] `ReadLints` clean。

## 4. 必须人审的决策点

- [x] **Web / UX 一眼是否可用(2026-06-03 人已签字通过)**:单页 chat + config 面板的可用性与观感(`00-overview §2` 人审项)。供审:`uv run <pkg> serve [--mock]` 起服务,浏览器看 chat 进度事件流 + 切到 Config 标签改一项(如 `prompts.system`)保存后再 chat 验证生效。前端为 Tailwind CDN 单页 + 原生 `EventSource`,无构建。**验收方式**:用本机 liteLLM 真实 LLM(`mimo-v2.5-pro`)经 SSH 端口转发在浏览器验证——token 流式 / 工具进度事件 / `/config` 改 `prompts.system` 当场生效均通过。
- [x] **`/config` 可改字段范围(2026-06-03 人已签字通过)**:边界已实现为——可改 `_EDITABLE_FIELDS = llms/roles/prompts/tools/context/observability/budget`;不可改结构性(`version`/`project_slug`)与 `secrets`(POST 中这些键被忽略,GET 不返回)。真实端点验证:GET 仅回 env 名不回密钥真值,越权键(`project_slug`/`secrets`)被忽略,非法值(`budget.max_steps:-1`)返 400。**范围符合预期,确认通过**。
- **v1+ 待办(2026-06-03 真实 LLM 验收发现)**:推理模型(如 `mimo-v2.5-pro`)在 reasoning 阶段会先沉默数秒才吐 content,流式下表现为"无反应等待",UX 差。**v1 新增模型"思考/reasoning"支持时,需显式提示**(如 `event: thinking` / 前端"思考中…"指示器,或把 `reasoning_content` 作为思考流推送),避免空白等待。**2026-06-07 升格为 Slice 12**(随原生 Anthropic 双规范一起做,§6.4 方案待签,见 `05-llm-dual-spec-anthropic.md` §5);见 `00-overview §2` Slice 12。
- **v1+ 待办(2026-06-05 部署拓扑讨论发现):`/config` 须与公开面隔离**。现状:`/chat` 与 `/config`(读 + 改运行期行为性配置)挂在**同一 FastAPI app、同端口、无鉴权**(`web.py` `create_app`)。在"**管理员托管 + 接口发布**"拓扑(`01 §4` 拓扑②,实际更常见)下,把 web 接口发布给终端用户 = 用户也能 POST `/config` 改掉管理员配好的 prompt / 预算 / tool allowlist——**配置即接口的安全面被击穿**。此拓扑下运行期配置本应安全(用户在网络接口另一侧、够不着 `config.yaml`),但前提是**管理面与公开面隔离**。**v1+ 落地候选**:① `/config` 加鉴权(token / 管理员凭证);② `/config` 仅绑 `127.0.0.1`、`/chat` 对外;③ **生成期开关**让发布实例不渲染 / 只读 `/config`(即 `01 §4` "`/config` 存在性 = 结构轴开关",会动 `HarnessSpec` → 触发 `CLAUDE.md §6.1`)。会动代码、③ 还动 spec,实现前请人签字。已登记到 `00-overview §2` Slice 13+ backlog(**且为 Slice 11 面板改 `mcp` 的前提**)。
- **软确认结论(Agent 已自主决定,`CLAUDE.md §5.3`;非阻塞,可一句话改判)**:
  - **SSE 粒度** = **token 级流式 + 进度事件,且可选**(人 2026-06 追加要求,已落地;见 §2.3 与头部实现说明③)。原"进度事件级、token 留 v1+"的方案已被取代。
  - **Web 依赖落位** = 方案 A(`web=true` 直接进 `dependencies`,不动冒烟/容器链路);"关掉不含"已三处(pyproject/lock/req)兑现 plan 的真实意图。
  - **`/config` 持久化** = ~~仅进程内生效,不回写 `config.yaml`~~ → **回写 `config.yaml`(进程内即时生效 + 落盘,保留注释)**。**2026-06-09 改判(人签字)**:初版定"不回写"(顾虑 PyYAML `safe_dump` 丢注释、保护用户手写配置;重启从盘重载),但实际造成"每次重启 serve 都要重新配置"的反常识体验——同一面板里 `.env`(key)/ rule 文件 / memory 笔记都落盘,唯独 `/config`(model / prompts / budget / tools / context)只进内存,且按钮叫"保存"、提示"已保存",认知冲突;wizard 一键产物 model 留空更是重启即丢、chat 复被 gate。改判方案:`POST /config` 校验通过后经 `config.py::save_config` 用 **`ruamel.yaml` 注释保留 round-trip** 回写——deep-merge 可编辑字段,块级/字段注释 + "被注释的可选项菜单"保留,列表(llms/tools)整体替换时元素行内注释会丢(已接受)。`create_app(config_path=...)` 记录回写路径,`serve` 透传 `--config`;传内存 config 且无 `config_path` 时不落盘(测试/库用不产生杂散文件)。`ruamel.yaml` 仅随 `interfaces.web` 进 `dependencies`(同 fastapi/uvicorn 模式,默认薄核心 `web:false` 三处 pyproject/lock/req 均不含,已加断言)。**文件 watch 热重载(监听外部对 config.yaml 的改动)仍属 v1+**,与本次"面板写回"是两件事。产物测试 `test_web.py::test_config_post_persists_to_yaml_preserving_comments`(落盘 + 注释保留 + 重载可见)/ `test_config_post_without_path_does_not_write_file`(无路径不落盘);生成器 `test_generator.py` web 开/关含/不含 `ruamel` 断言;web golden + docker(web 产物)端到端覆盖。
  - **条件渲染机制** = `generator.CONDITIONAL_TEMPLATES`(相对模板路径 → `predicate(spec)`),Slice 4/5 直接复用。
  - **配置面板"未保存"守卫(2026-06-07 UX 细化,Agent 自主)**:面板编辑仅在 DOM、点 Save 才 `POST /config` 生效,用户常忘按 Save 致刚配的 LLM profile 丢失。落地为**未保存提醒**而非自动保存(自动保存会与服务端 Pydantic 校验/重渲染/即时生效心智三处打架,且违反"薄"):脏标记(任一编辑亮"未保存"+高亮 Save)、切走 Chat / 刷新前 `confirm`、切回 Config 时 `!dirty` 才 `loadConfig()`(修根因——原先每次切回都无脑重载覆盖未保存编辑)。纯前端 `web_index.html`,产物 HTML 自带断言(`test_web.py::test_index_has_unsaved_config_guard`)。
  - **Tools 标签分组(2026-06-07 UX 细化,Agent 自主)**:原 `cfg.tools`(config.yaml 的 allowlist)在面板平铺成一长串,MCP 工具(命名 `<server>__<tool>`)与内置混在一起很乱。改为前端按名分组渲染:**"你的工具"(非 `__` 且非内置,置顶)→ 内置工具 → 每个 MCP server 一个默认折叠的 `<details>`(标题显示 server 名 + 启用/总数)**。内置集合 `BUILTIN_TOOLS`(`get_current_time`/`calculator`/skills 开时 `read_skill`)由 jinja 注入。**用户自定义 Python tool 现状**:`@registry.tool` 注册 + 在 config.yaml `tools:` allowlist 才会被模型用到并显示在页面(面板对**自定义 Python tool** 不做 registry 自动发现;**MCP 工具已可自动发现,见下条**)——已入 allowlist 的自定义 tool 即归入置顶"你的工具"组。**勾选框的作用**:`enabled` 是运行期实时开关(进程内即时生效、免重启、免改 YAML),`config.yaml` 列出 = 声明进 allowlist 宇宙,勾选 = 在宇宙内开/关——二者不冗余(尤其 MCP 一个 server 十几个工具时按需开)。Tools 区底部加 `tools_extend_hint` 小字(对齐其余 tab 的 extend-hint 风格):说明"注册 + 加 config.yaml 才显示、勾选框实时开关",避免用户 `@registry.tool` 后发现不显示而困惑。产物 HTML 自带断言(`test_web.py::test_index_groups_tools_by_source`);AGENTS.md "Add a tool" 同步说明分组位置。
  - **rule 文件改为面板内编辑正文(2026-06-07,人定向 R2)**:原 Prompts 标签的 rule 管理是个"每行一个路径"的 textarea(只管 `rules_files` 路径清单,不能编辑正文),既不像主流(放约定文件自动读)也不方便。对标 2026 事实标准(`AGENTS.md` 开放标准为单一约定文件,但 Cursor `.cursor/rules/*` / Claude 嵌套 / Copilot 路径专属 = **多文件也是标配**),保留**多文件**、但把每个 rule 文件做成**可在面板内编辑正文**:每文件一行 `[路径输入 + markdown 正文框 + 删除]` + "添加规则文件"。后端新增 `GET /rules`(读 `prompts.rules_files` 各文件正文)、`POST /rules`(写单文件)+ `_safe_repo_path`(**仅允许仓库内相对路径,绝对路径/`..` 穿越一律 400**——面板不得读写宿主任意文件;这是"Web 写仓库文件"的新面,与 v1+「`/config` 与公开面隔离」相关,已局限在 markdown 文件 + 路径白名单)。保存语义:**折进主 Save**(先 `POST /rules` 写各文件正文、再 `POST /config` 存 `rules_files` 列表),不另设每文件按钮——避免重蹈"per-field 保存易忘"(见上"未保存守卫")。**自动识别的约定文件也在列表里显示**(2026-06-07 追加):`GET /rules` 在显式 `rules_files` 之外,把存在于根目录的约定文件(`CLAUDE.md`,见 `075-slice-6b §5`)以 `auto:true` 一并返回;面板渲染为**只读路径 + "自动"标记**的行,正文可编辑(Save 经 `POST /rules` 写回),但**不计入** `collectConfig` 的 `rules_files`(仍按约定注入,不污染显式列表)。产物测试 `test_web.py::test_rules_endpoint_writes_and_reads_within_repo` / `test_rules_endpoint_rejects_paths_outside_repo`(路径越界拒绝)/ `test_rules_endpoint_surfaces_auto_recognized_claude_md` / `test_index_has_editable_rule_files`;web golden 端到端覆盖。AGENTS.md "Project rules" 段同步。
  - **移除 `prompts.persona`(2026-06-07,人签字;触 `CLAUDE.md §6.1` 改 spec schema)**:`persona` 在 `build_system_prompt` 里只是紧跟 `system` 后再拼一段文本(`parts.append(prompts.persona)`),与写进 `system` 机制等价、无任何特殊语义,在 Prompts 配置页显得冗余/业余。整条移除:`spec.py Prompts` / 产物 `PromptsConfig` / `config.yaml`(渲染)/ `prompts.py`(拼接)/ Web Prompts 标签输入框 + i18n + collect/render,只留 `system + rules_files`。预设/示例均未用 persona;唯一兼容性破点:已有 spec.yaml/config.yaml 里写了 `persona:` 的会因 `extra="forbid"` 校验报错(pre-1.0、own-code 产物互不影响,接受)。门禁:`test_spec.py` 去掉 persona 断言后快测全绿 + 黄金路径绿。
  - **MCP 工具自动发现(2026-06-07,人定向 Scope 1)**:解决"加了 MCP server 还要手写 `<server>__<tool>` allowlist、且连上前根本不知道工具名"的痛点(对标 Claude Code)。后端加 `GET /mcp/discover`:对 `config.mcp.servers` 全部 server 连一次 + `list_tools`(复用 `McpManager.discovered`,失败按 server 隔离进 `error`、空 servers 直接短路),返回每工具的 `{name, short, description, listed, enabled}`。前端 Tools 标签**打开即自动扫描**(每页缓存一次,带"扫描 MCP"重扫按钮、异步不卡 UI):MCP 分组显示 server 的**全部**发现工具,勾上即写入 allowlist 并启用;保存改为 **DOM 驱动**(每个勾选框带 `data-name`/`data-listed`,`collectConfig` 据此回写——已列出的工具勾/不勾都回写,发现但未列出的仅勾选才写,避免 config 被一个 server 几十个工具塞爆)。条件渲染:仅 `spec.mcp.enabled` 产物有该端点与扫描 UI。产物测试:`test_web.py::test_mcp_discover_lists_real_server_tools`(对真实 stdio dummy server 验证 echo/add 发现 + allowlist 状态)、`test_mcp_discover_returns_empty_without_servers`、`test_index_has_mcp_discovery_ui`;web golden(coding-assistant 默认 `mcp.enabled`)端到端覆盖。**剩余归「MCP 健康管理」,2026-06-07 升格为 Slice 11**(见 §4 与 `00-overview §2` Slice 11):面板内增删/编辑 MCP server(需 `/config` 可改 `mcp` = Scope 2,触安全面,前提=发布拓扑隔离 Slice 13+)、server 连通性/健康状态面板(#19 / T2-G)、热重连。

## 5. 本 slice 注意

- **薄**:默认产物(`web: false`)必须与 Slice 1/2 完全一致,零新增依赖、零 Web 文件;`web.py` 自身保持薄(`CLAUDE.md §2`)。
- **核心改动克制**:进度事件复用既有 `Hooks`(不改 loop);token 级流式仅给 `loop.run()` 加一处可选 `on_delta` 分支(+4 行,实测 180 行仍在 150–300 薄区间),累积逻辑落在 `llm.py` 适配层。token 流式是人明确追加的 UX 需求,故接受这点核心改动;若再要扩展导致 loop 明显变厚,先停问人(`CLAUDE.md §6.8`)。
- **密钥红线**(`CLAUDE.md §6.5`):`/config` 面板、SSE 事件、trace、日志任一路径出现明文 key 即失败。面板只可见 env 引用名;"密钥只写不回显面板" = L3,本片不做密钥编辑。
- **不绑框架**:FastAPI/uvicorn 是通用 Web 库,**不是 agent 编排框架**,不违反定位红线(`01-project-plan §1` 措辞);但仅在 `web=true` 时进产物。
- **配方 vs 活旋钮**(决策④,`01 §4`):`/config` 改的是运行期行为性配置(`config.yaml` 域);接口有无 / 模块 / 范式拓扑是结构性的,只能重新生成。Web 面板属**产物自持**,HarnessForge 不做中心化配置/托管。
- **MCP 工具**(stdio + 远程 HTTP/SSE)挪到 Slice 4(2026-06-03 定向);**完整 HITL Web** 已排 Slice 10、**`/config` 热重载进阶、联网 MCP registry** 仍为 v1+,均不在本片(`00-overview §2` Slice 4 / Slice 10 / Slice 13+)。
