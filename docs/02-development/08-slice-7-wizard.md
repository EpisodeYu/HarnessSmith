# 02·08 - Slice 7:wizard(生成器单页表单产 spec)+ 产物分页配置页

> 目标(2026-06-06 细化后):
> ① **生成器侧 wizard**——`harnessforge/wizard/`(FastAPI + 无构建单页,Tailwind CDN + 原生 JS,`harnessforge[wizard]` extra)。**只采集「生成什么」的结构选项**(显示名→slug、语言、`paradigms`、`interfaces.web`、`mcp.enabled`+catalog、`skills.enabled`),**首项选语言(中文/English)**;行为性字段(llms/prompts/budget/tools…)由后端**烤可用默认值**进 spec、**不在向导露出**(降低新手门槛,产物开箱即跑);`POST /spec` 校验产合法 spec(可下载)+ 可选一键 `generate()`。
> ② **产物侧分页配置页**——把产物 Web 的 `/config`(Slice 3)从单一 JSON 文本框重组成**按功能分页**(LLM/Context/Budget/Tools/Prompts/Paradigms/Observability)+ **中英切换**;只改运行期行为性配置(守两轴);仅 `interfaces.web=true` 时存在,默认薄产物零改动。**产物不做 wizard、不做首启自动拉起**(人 2026-06-06 定:产物只要分页配置页)。
>
> wizard 是**生成器侧工具**,不进产物、产物不依赖它(`01 §1`)。属 `01-project-plan.md` 的 **L2**。
>
> **本片由 2026-06-05 重切而来**:原 Slice 5 过大,拆为 Slice 5(范式)/ Slice 6(工具基线 + SKILL)/ Slice 7(本片)。wizard 放最后,因它是**对已稳定 spec 的 GUI**——需覆盖 Slice 5 的 `paradigms`、Slice 4/6 的 `mcp.enabled` + catalog、Slice 6 的 `skills.enabled` 等字段。
>
> 前置:Slice 6/6B 门禁全绿(spec 字段集稳定)。
>
> **状态:✅ 已完成(2026-06-06)。** 字段面经人 2026-06-05 定稿(全覆盖 + 按功能分页);四点细化经人 2026-06-06 拍板(见 §4)。退出门禁(§3)实现并自验证全绿后回填。
>
> **红线提醒**:FastAPI/uvicorn 是通用 Web 库、**非 agent 编排框架**(`01 §1`),且仅进**生成器侧** `harnessforge[wizard]` extra,**不污染 `uvx harnessforge new` 核心链路、不进产物**。**密钥红线**:wizard / 产物配置页只采集/回显 env 变量名,绝不收/回显密钥真值(`CLAUDE.md §6.5`)。

## 0. 边界与口径(开工前先对齐)

- **wizard 产 spec(配方);产物配置页改活旋钮**:wizard 是**生成期**采集层(`spec` = 配方);运行期行为性配置由产物自身分页 `/config`(本片重组的 Slice 3 面板)管。两者不混(决策④,`01 §4`)。
- **wizard 只收结构,行为性烤默认**(人 2026-06-06 决策 B):向导 UI 只问"生成什么"(结构),**不展示** llms/prompts/budget/context 等行为性字段;后端对缺省项**烤可用默认值**(默认 LLM profile 指向 `OPENAI_API_KEY`/`OPENAI_BASE_URL`、默认 system prompt、内置工具开、`budget.max_steps=8`)使产物开箱即跑。这些值生成后在**产物配置页 / `.env`** 里改。理由:① 一个生成器对应多个产物,每个产物各配自己的 LLM 等;② 向导选项过多会劝退新手,先低成本拥有 agent;③ 初值/默认值需要带进产物,但不必在向导露出。
- **语言选择贯穿(UI 语言)**:wizard 顶部的单一语言选择**贯穿**到 ① wizard 自身 UI、② 产物 web 默认 UI 语言(经 `spec.language` 种子化,运行期浏览器仍可切并记忆)。**Agent 回答语言不在向导设**:现代模型基本按**用户输入语言**自动回答;想固定默认语言在产物配置页 Prompts 里改 `prompts.system` 即可。
- **显示名 vs 包名**:新增 spec 字段 `display_name`(人类可读,用于产物 UI 标题/header + README 标题,空则回落 `project_slug`);wizard 输入显示名并由它**派生** `project_slug`(snake_case 包名/文件夹,可手改)。
- **spec 仍是全字段**(配方):`HarnessSpec` 字段集不变(含 Slice 5 `paradigms`、Slice 4/6 `mcp.enabled`+catalog、Slice 6 `skills.enabled`、llms/roles/prompts/tools/interfaces/observability/budget/context);差异只在**向导 UI 暴露哪些**——结构暴露、行为性烤默认。手写 spec / `--mcp-server` / 产物配置页仍可改全部行为性字段。
- **LLM 维持 provider-agnostic**:本片 LLM 层不变(Chat Completions + `base_url`)。**原生 OpenAI+Anthropic 双规范可切 = v1+ 可选模块**(人 2026-06-06,见 `00-overview §2 Slice 8+`);接 Claude 当下走 Anthropic 兼容端点 / LiteLLM。
- **依赖隔离**:fastapi/uvicorn 进 `harnessforge[wizard]` extra;核心 `harnessforge` 依赖(typer/jinja2/pydantic/pyyaml)不变 → `uvx harnessforge new` 不拉 fastapi。

## 1. 交付物

生成器侧(`harnessforge/`):

- `spec.py` — `HarnessSpec` 新增 `display_name: str | None`(纯标签,不进 `config.yaml`)+ `language: Literal["en","zh"] = "en"`(产物 web 默认 UI 语言种子)。
- `generator.py` — 渲染上下文加 `display_name`(= `spec.display_name or spec.project_slug`)+ `language`;`config.yaml` context 块改为**从 `spec.context` 种子化**(沿用 rules_files 式 seed,未设时输出与旧版字节一致)。
- `wizard/`(新目录,`[wizard]` extra 门控):
  - `wizard/app.py` — FastAPI:`GET /`(单页)、`GET /meta`(范式/catalog/presets 元数据 + `generate_base`)、`POST /spec`(对缺省行为性字段烤 `_BAKED_DEFAULTS` → `HarnessSpec` 校验 → spec YAML + `harnessforge new` 命令〔填入目标目录〕/ 字段级错误)、`POST /generate`(`generate()` 渲染;`launch:true` + Web 时额外**后台拉起产物 `uv run <slug> serve` 并回 URL**,否则保持 render-only)。`_BAKED_DEFAULTS` 只在字段缺省时填(显式/手写 spec 优先)。
  - `wizard/static/index.html` — 无构建**精简单页**:**首项语言下拉(中/英)** + `{zh,en}` i18n 字典(切换换 wizard UI),该选择写入 `spec.language`(贯穿到产物 UI 默认);**只两组结构选项**——基本(显示名→slug、`paradigms` 多选+默认)与 能力(`interfaces.web`、`mcp.enabled`+catalog 多选、`skills.enabled`)+ 生成产物;显示名→slug→目标目录前端逐级派生。
- `cli.py` — `harnessforge wizard`(懒加载 uvicorn + wizard app;**默认自动挑空闲端口**(`_find_free_port`,从 8000 起,`--port` 可固定)并打印可打开地址;未装 extra 给友好提示)。产物 `serve` 同样默认自动挑端口 + 打印地址。
- `pyproject.toml` — 新增 `[project.optional-dependencies] wizard = [fastapi, uvicorn]`;`dev` 加 fastapi/uvicorn/httpx 供 `fastapi.testclient` 测试。

产物侧(`harnessforge/templates/`,`interfaces.web` 门控):

- `src/<pkg>/interfaces/web_index.html.j2` — Config 视图重组为**按功能子 tab**(LLM/Context/Budget/Tools/Prompts/Paradigms/Observability)+ 顶部**语言切换(静态双语标签 `语言/Language`,默认值由 `{{ language }}` 即 `spec.language` 种子化,localStorage 记忆)**;LLM tab 每个 profile 带**写入式 set-key**(写 `.env`、不回显);chat 视图行为不变;标题/header 用 `{{ display_name }}`。**后端 `web.py` `/config` 不变**(仍是同一组 `_EDITABLE_FIELDS`);新增 `POST /env`(write-only 写 `.env`,不回显)。
- `README.md.j2` / `web.py.j2` — 标题用 `{{ display_name }}`(回落 slug)。
- **写入式 `.env` 密钥助手**(人 2026-06-06 决策 D):`config.py set_env_value(name, value)`(只写本地 gitignored `.env`、单行防注入、env 名校验)+ CLI `<pkg> set-key <ENV_NAME>`(隐藏输入)+ Web `POST /env` / LLM tab 输入框。**write-only**:值只进 `.env`,绝不进 `config.yaml`/spec/trace/日志/任何响应。降低"建 .env 粘 key"门槛(尤其 Windows 免配系统环境变量)。keyring 仍 v1+。
- `cli.py`(产物)/ `cli.py`(生成器) — `serve` / `wizard` 默认 `--port 0` 自动挑空闲端口(`_find_free_port`,从 8000 起)并打印可打开地址。

测试:`tests/test_wizard.py`(`fastapi.testclient`)+ `test_spec.py`/`test_generator.py` 增 display_name/context/分页断言 + `test_golden.py` 增 wizard 端到端 golden。

## 2. 任务拆解(实现说明)

### 2.1 生成器 wizard:结构-only 表单 + 烤默认(决策 B)
- **首控件 = 语言**;前端 i18n 字典覆盖全部可见文案,切换即换(零新增依赖)。
- **UI 只暴露结构**:基本(显示名→slug、`paradigms` 多选+默认、语言)+ 能力(`interfaces.web`、`mcp.enabled`+catalog 多选、`skills.enabled`)+ 产出。**不展示** llms/prompts/tools/context/budget/observability/roles。
- **后端烤默认值**(`app.py _BAKED_DEFAULTS`,仅缺省时填):默认 LLM profile(`name=default`/`model=gpt-4o-mini`/`api_key_env=OPENAI_API_KEY`/`base_url_env=OPENAI_BASE_URL`)+ `roles.generation=default` + `prompts.system="You are a helpful assistant."` + 内置工具(get_current_time/calculator)开 + `budget.max_steps=8`;context/observability 走 `config.yaml` 模板默认。这样产物开箱即跑,用户在**产物配置页 / `.env`** 里改这些。显式传入(或手写 spec)优先于默认。
- **显示名→slug**:前端 `lower / 非字母数字→_ / 去首尾_ / 数字开头补_`;用户改过 slug 后不再自动覆盖;后端按 `spec._SLUG_RE` 兜底校验。

### 2.2 后端校验 + 产出
- `POST /spec`:`HarnessSpec.model_validate` → 合法 `yaml.safe_dump(exclude_none)`(只 env 名)+ `new_command`(含选中的 `--mcp-server`);失败返 400 + `errors:[{loc,msg}]`。
- `POST /generate`:校验 + 解析 catalog 选择(仅 `mcp.enabled` 时)+ `generate()` **render-only**(快/离线,不卡 UI);返回落盘路径 + `next`(`uv sync` 接力)。**软确认落地**:卡 UI 风险用 render-only + 始终提供 spec 下载 / `harnessforge new --spec` 接力规避。
- **catalog 预填**:选中 server → `generate(mcp_servers=...)` 落产物 `config.yaml mcp.servers` + tool allowlist(env 仅名、高风险默认关),不进 spec/快照。

### 2.3 产物分页配置页
- 重写 `web_index.html.j2` Config 视图:`GET /config` 读 → 渲染各功能 tab 表单(profiles/roles/context/budget/tools/prompts/paradigms/observability)→ Save 收集回 `POST /config`(整体 patch,后端 Pydantic 再校验,非法返 400)。**只改行为性**;结构性不可改(需重新生成)。
- 语言切换(en/zh)纯前端 + `localStorage` 记忆;产物默认 `en`(通用),可切中文。

### 2.4 依赖隔离
- fastapi/uvicorn 进 `harnessforge[wizard]` extra;`harnessforge wizard` 懒加载;核心 CLI、`uvx harnessforge new`、产物均不含。测试断言核心 `dependencies` 不含 fastapi/uvicorn。

### 2.5 web 可操作性优化(实现说明,2026-06-06,人定向)

降低 wizard 上手成本 + 把"生成→看到产物"打通成一键。**只动生成器侧 wizard,不改 spec/模板/产物生成口径**。

- **默认勾选(开箱即用的"全家桶"默认)**:`paradigms` 全选(`agent` 仍是首项=运行期默认范式);能力 `interfaces.web` / `mcp.enabled` / `skills.enabled` 默认开;catalog 预选默认 `fetch` / `ddg-search` / `git`。这些只是**表单默认值**,用户可取消。
- **catalog 在 wizard 的呈现 = 策展子集**(`app.py _WIZARD_CATALOG_ORDER` / `_WIZARD_CATALOG_DEFAULT`,经 `/meta` 的 `default_checked` 下发):显示 `fetch` / `ddg-search` / `git` / `desktop-commander`(默认勾的三项在前、DC 在最后),**隐藏 `github`(需 token + 无可启用工具)与 `time`(冷门)**。**catalog 本体不变**——`github`/`time` 仍在 `mcp_servers.yaml`,CLI `--mcp-server github/time` 照常可用;策展只作用于 wizard 表单(人 2026-06-06 选 wizard-only)。`git` vs `github`:`git`=本地仓库、免 key、读类默认开,做默认;`github`=remote MCP 平台 API、需 `GITHUB_MCP_TOKEN`,从表单隐藏。
- **「生成产物」分两法**(原"产出"+"一键生成产物(可选)"合并):
  - **一键生成**:目标目录默认 `<HarnessForge 根>/generate/<包名>`(`/meta.generate_base` + 前端按 slug 派生,可手改;`generate/` 已入 `.gitignore`),git init 复选。点击 → `POST /generate {launch:true}` 渲染产物;**当勾了 Web** 则在后台 worker 线程跑 **`uv sync` → `uv run <slug> serve --port <自动空闲端口>`**(**真实模式**,人 2026-06-06 选),回一个 `job_id`。前端轮询 `GET /generate/status/{job_id}` 渲染**分步进度条**(`render → sync → serve`,各步 pending/running/done/error),**全部 done 后才点亮「跳转到 <显示名>」按钮**(在此之前按钮置灰不可点);打开产物 web 后在配置页 / `.env` 填 LLM key 即可对话。任一步 error → 进度条标红 + 显示原因(`.setup.log`/`.serve.log` 可查)。未勾 Web 时保持 render-only、不拉起。
  - **CLI 生成**:校验并产出 spec → spec.yaml 下载 + 完整 `harnessforge new <默认目标目录> --spec spec.yaml [--mcp-server ...]` 命令(目标目录已填入)。
- **进程语义**:拉起的产物 `serve` 以**独立 session 后台**运行(`start_new_session=True`,输出落 `<target>/.serve.log`),wizard 退出后产物仍在跑(便于已打开的标签继续用);`_LAUNCHED` 持有句柄防 GC,`_JOBS` 持进度记录供轮询。**仅生成器侧便利**,产物本身不依赖 wizard。
- **测试**:`test_wizard.py` 增 catalog 策展/默认勾选/`generate_base`/命令填目标目录/`launch` 行为(`_spawn_launch` 经 monkeypatch 打桩,不实跑 uv;另测 job 步序/`/generate/status` 404);另实跑过一次真实进度条拉起冒烟(steps `render→sync→serve` 全 done、产物 web 200、标题含显示名)。golden `test_golden_wizard_spec_generates_and_smoke_passes` 走 `/spec`(render-only)不受影响。

**(2026-06-06 续:web 可操作性二轮)** wizard 单页**精简文案**(删 intro_note / display_name_hint / slug_hint / target_hint / oneclick_hint 五处说明文字及其 i18n 键,降噪);一键生成改为**分步进度条 + 成功前禁用跳转**(见上)。

**端口转发体验(2026-06-06,人定向:不做反代、只加提醒)**:针对"Linux 跑 + 从 Windows 经 SSH 访问要转发两次(wizard + 产物各一次)"的体验问题,调研业界(Jupyter=单端口子路径多路复用 / Streamlit·Gradio=默认让用户 SSH 转发 / Gradio share=公网代理隧道有外部依赖+安全面 / VS Code·Cursor Remote=监听即自动逐端口转发)。**结论(人拍板)**:① **Windows 全程本地无障碍**——wizard+产物同机 `127.0.0.1` 访问、零转发(`start_new_session` 在 Windows 静默忽略,产物作为 wizard 子进程,本地用反而更干净);② 会用 Linux 远程的用户**会自己配端口转发**,故**不做单端口反代**(避免动产物结构 + SSE 反代复杂度),仅在各处**加便利提醒**:`harnessforge wizard`(`cli.py`)与产物 `serve`(`cli.py.j2`)在 **Linux** 下打印 `ssh -L <port>:127.0.0.1:<port> <user>@<host>`;wizard web 在 **Linux**(`/meta.linux` 门控)且产物就绪时,在跳转按钮旁提示先转发产物端口。**单端口反代(Jupyter 模式)**留作 v1+ 备选(若将来要"只转一次"),其前提是产物前端改相对路径 + FastAPI `root_path` + wizard SSE 流式反代——已记录可行性与对产物独立性无损(反代纯生成器侧、产物仍可独立 `serve` 直连)。

## 3. 退出门禁(对应 `01 §8` Non-blocker;✅ 实现并自验证)

- [x] **wizard(结构-only 表单)产合法 spec 并能生成可跑产物**:结构-only `POST /spec`(显示名→slug、`paradigms` 多选、`mcp.enabled`+catalog)→ 后端烤行为性默认 → `HarnessSpec` 校验通过 → 写 spec → `generate()` → `uv lock` → `uv sync`+import+mock 跑一步+`pytest` 全绿(`test_golden.py::test_golden_wizard_spec_generates_and_smoke_passes`,web=true 含 `test_web`)。
- [x] **结构-only 表单 + 烤默认**:向导 UI 只暴露结构控件、不暴露行为性(`test_wizard.py::test_wizard_ui_is_structural_only`);结构-only 表单经后端烤出默认 LLM/prompt/budget/tools 使产物完整(`test_baked_defaults_fill_behavioral_fields`);显式行为性字段优先于默认(`test_explicit_behavioral_fields_win_over_defaults`)。
- [x] **wizard 不泄密 / 不进产物**:只采集/回显 env 名(`test_wizard.py::test_spec_only_holds_env_names_never_secret_values`);核心 `dependencies` 不含 fastapi/uvicorn(`test_core_dependencies_exclude_wizard_deps`),关 Web 产物不含(沿用 Slice 3 断言)。
- [x] **catalog 预填经 wizard 落 `config.yaml`**:`POST /generate` 选中 server → 产物 `config.yaml mcp.servers` 含该条目(沿用 Slice 6 catalog 落地路径;wizard golden 走 `generate(mcp_servers=...)`)。
- [x] **显示名机制**:`display_name` 渲染进产物 web 标题/header + README 标题,未设回落 slug(`test_generator.py::test_display_name_renders_in_titles_and_readme` / `test_display_name_falls_back_to_slug`)。
- [x] **产物配置分页 + 语言**:`web_index.html` 含语言开关(en/zh)+ 按功能 `cfg-tabs`;`/config` 行为不变(`test_web.py` 全绿;`test_generator.py::test_web_index_has_paged_config_and_language_switch`)。
- [x] **语言贯穿(UI)**:wizard 语言选择写入 `spec.language` → 产物 web 默认 UI 语言被种子化(`test_generator.py::test_language_seeds_product_web_default` / `test_language_defaults_to_en_in_product_web`;`test_wizard.py::test_language_threads_into_product_default`);`spec.language` 默认 `en`、非法值被拒(`test_spec.py::test_language_*`)。Agent 回答语言不在向导设(产物 Prompts 里改)。
- [x] **context 种子化**:`spec.context` → `config.yaml` context 块;未设时字节一致(`test_context_block_seeds_from_spec` / `test_context_block_defaults_when_spec_omits_it`)。
- [x] **大改动回归**:动 schema(`display_name`)+ 跨 ≥3 文件 → golden 全量 + Docker 冒烟 + `uvx harnessforge new` 冒烟全绿;无框架断言(pyproject/lock 无 langchain/langgraph/adk)。
- [x] `ReadLints` clean。
- [ ] **wizard / 配置页对外可读(人审,§4②)**:起 `harnessforge wizard` 与产物 `serve` 实际点一遍,确认字段集/措辞/中英文案/默认对非作者用户友好。

## 4. 必须人审的决策点

- [x] **① wizard 字段 = 全覆盖 + 按功能分页——人 2026-06-05 定稿**。
- [x] **②（2026-06-06 细化,人拍板)**:
  - **wizard 瘦身为结构-only + 行为性烤默认**(决策 B):向导 UI 只问"生成什么"(结构),llms/prompts/budget/context 由后端烤默认值、不在向导露出,生成后在产物配置页改。人给的理由:① 一个生成器对应多个产物、各配自己的 LLM;② 向导选项过多劝退新手,先低成本拥有 agent;③ 初值默认值要带进产物但不必在向导展示。
  - **语言优先 + 双语 + 贯穿(UI)**:wizard 与产物配置页首项/首控件为语言(中/英);wizard 的单一语言选择**贯穿**到 wizard UI + 产物 web 默认 UI 语言(`spec.language` 种子,运行期可切)。Agent 回答语言**不在向导设**(模型按输入语言自动回答;要固定在产物 Prompts 改)。
  - **显示名 → 派生 slug**:新增 `spec.display_name`(改 schema,触发 `CLAUDE.md §6.1`,**人 2026-06-06 签字**);wizard 输入显示名派生 `project_slug`。
  - **产物不做 wizard,只做分页配置页**:产物侧不做首启自动拉起 / 独立 wizard,只把 `/config` 按功能分页 + 中英切换;只改运行期行为性配置(守两轴)。LLM/prompts/budget/context 等行为性配置的**正式入口就是产物配置页**。
  - **LLM 规范**:本片维持 provider-agnostic;**原生 OpenAI+Anthropic 双规范登记 v1+**(人 2026-06-06:"要做双规范,但不做在 slice7,后续单独做,先记在 v1")。
  - **写入式 `.env` 密钥助手 = 做 B+C(决策 D,人 2026-06-06)**:产物侧 Web LLM tab + CLI `set-key` 把 key 真值**只写本地 gitignored `.env`、write-only 不回显**(合规,见 §5 密钥红线);生成器 wizard 不收 key;keyring 留 v1+。理由:`.env` 已比 Windows 系统环境变量简单,助手只是免去"手建 .env 粘 key"。
  - **端口自动侦测 + 双语语言标签**(人 2026-06-06):`wizard`/产物 `serve` 默认自动挑空闲端口并打印地址(避开端口占用);语言切换标签恒显示 `语言/Language` 让任何语言用户都能找到切换。
- [ ] **③ 字段是否齐 / 对外可读(实现后真实验收)**:起 wizard + 产物 serve 点一遍,确认覆盖与中英措辞。
- **软确认(非阻塞,`CLAUDE.md §5.3`)**:`POST /generate` 取 render-only(卡 UI 规避,始终提供 spec 下载 / `new --spec` 接力);无构建单页(Tailwind CDN);wizard 依赖进 `[wizard]` extra;后端 `_BAKED_DEFAULTS` 取默认 LLM(`gpt-4o-mini` + `OPENAI_API_KEY`/`OPENAI_BASE_URL`)、默认 system prompt、内置工具开、`budget.max_steps=8`(仅缺省时填,显式优先);采样/单价/context 等其余行为性走产物 `config.yaml` 模板默认 + 产物配置页。

## 5. 本 slice 注意

- **不进产物 / 不绑框架**:wizard 仅生成器侧、FastAPI 非 agent 编排框架(`01 §1`);产物不依赖 wizard(守"生成后不再依赖 HarnessForge")。
- **密钥红线**(`CLAUDE.md §6.5`):wizard 表单 / 回显 / 产出 spec、产物配置页 / `/config` 只存 env 变量名。**写入式 `.env` 助手**(set-key / `POST /env`)把真值**只写本地 gitignored `.env`**、不回显、不进 git/spec/trace/日志——`.env` 本就是放真值的地方,合规;真·密钥库(keyring/OS 凭证)仍 v1+。**生成器 wizard 始终不收 key**(spec 不能含密钥)。
- **配方 vs 活旋钮**(决策④,`01 §4`):wizard 产 `spec`(配方);产物分页 `/config` 改运行期行为性配置;结构性(接口/模块/范式拓扑=代码)只能重新生成。
- **薄**:默认产物(`web:false`)零改动、零新增依赖;产物 Web 的分页/i18n 是单页前端内的事,`web.py` 后端不变、仍薄。
- **覆盖随 spec 演进**:若 spec 再增字段,wizard 同步补。
- **v1+ 衔接**:原生 Anthropic 双规范(prompt caching / adaptive thinking + effort / Opus 4.7/4.8 禁采样 / structured outputs)登记 `00-overview §2 Slice 8+`;`/config` 与公开面隔离(Slice 3 已登记)仍是发布前提。
