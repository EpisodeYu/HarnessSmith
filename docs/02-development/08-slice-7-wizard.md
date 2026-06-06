# 02·08 - Slice 7:wizard(生成器单页表单产 spec)+ 产物分页配置页

> 目标(2026-06-06 细化后):
> ① **生成器侧 wizard**——`harnessforge/wizard/`(FastAPI + 无构建单页,Tailwind CDN + 原生 JS,`harnessforge[wizard]` extra)采集 `HarnessSpec` 全字段,**首项选语言(中文/English)**、**按功能分页**、**输入显示名自动派生 slug**;`POST /spec` 校验产合法 spec(可下载)+ 可选一键 `generate()`。
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
- **语言选择贯穿始终**(人 2026-06-06 补齐):wizard 顶部的单一语言选择**贯穿**到 ① wizard 自身 UI、② 产物 web 默认 UI 语言(经 `spec.language` 种子化,运行期浏览器仍可切并记忆)、③(**可选**)Agent 默认回答语言。
  - **Agent 回答语言 = 可选软指令**:现代模型基本会按**用户输入语言**自动回答,故不强制;wizard 勾选"让 Agent 默认用所选语言回答"时,后端把一句**软指令**(默认用 X 回答,但用户用别的语言则跟随)追加进 `prompts.system`(成为可在 `config.yaml` 改的普通运行期文本)。默认**不勾**,避免强制覆盖自动跟随、避免每轮多花 token。
- **显示名 vs 包名**:新增 spec 字段 `display_name`(人类可读,用于产物 UI 标题/header + README 标题,空则回落 `project_slug`);wizard 输入显示名并由它**派生** `project_slug`(snake_case 包名/文件夹,可手改)。
- **覆盖稳定后的 spec 全字段**:含 Slice 5 `paradigms`、Slice 4/6 `mcp.enabled` +(开时)catalog 多选预填、Slice 6 `skills.enabled`、以及 llms/roles/prompts/tools/interfaces/observability/budget/context。
- **LLM 维持 provider-agnostic**:本片 LLM 层不变(Chat Completions + `base_url`)。**原生 OpenAI+Anthropic 双规范可切 = v1+ 可选模块**(人 2026-06-06,见 `00-overview §2 Slice 8+`);接 Claude 当下走 Anthropic 兼容端点 / LiteLLM。
- **依赖隔离**:fastapi/uvicorn 进 `harnessforge[wizard]` extra;核心 `harnessforge` 依赖(typer/jinja2/pydantic/pyyaml)不变 → `uvx harnessforge new` 不拉 fastapi。

## 1. 交付物

生成器侧(`harnessforge/`):

- `spec.py` — `HarnessSpec` 新增 `display_name: str | None`(纯标签,不进 `config.yaml`)+ `language: Literal["en","zh"] = "en"`(产物 web 默认 UI 语言种子)。
- `generator.py` — 渲染上下文加 `display_name`(= `spec.display_name or spec.project_slug`)+ `language`;`config.yaml` context 块改为**从 `spec.context` 种子化**(沿用 rules_files 式 seed,未设时输出与旧版字节一致)。
- `wizard/`(新目录,`[wizard]` extra 门控):
  - `wizard/app.py` — FastAPI:`GET /`(单页)、`GET /meta`(范式/内置工具/catalog/presets 元数据)、`POST /spec`(`HarnessSpec` 校验 → spec YAML + `harnessforge new` 命令 / 字段级错误)、`POST /generate`(可选一键 `generate()` render-only,产物落盘后由用户 `uv sync`)。
  - `wizard/static/index.html` — 无构建单页:**首项语言下拉(中/英)** + `{zh,en}` i18n 字典(切换换 wizard UI),该选择同时写入 `spec.language`(贯穿到产物);Prompts 页含"让 Agent 默认用所选语言回答"复选(默认关 → 后端追加软指令);按功能分页(基本/LLM/Prompts/Tools/Context/Budget/Interfaces/Observability/产出);显示名→slug 前端派生;`mcp.enabled` 时 catalog server 多选。
- `cli.py` — `harnessforge wizard`(懒加载 uvicorn + wizard app,默认 `127.0.0.1:8000`;未装 extra 给友好提示)。
- `pyproject.toml` — 新增 `[project.optional-dependencies] wizard = [fastapi, uvicorn]`;`dev` 加 fastapi/uvicorn/httpx 供 `fastapi.testclient` 测试。

产物侧(`harnessforge/templates/`,`interfaces.web` 门控):

- `src/<pkg>/interfaces/web_index.html.j2` — Config 视图重组为**按功能子 tab**(LLM/Context/Budget/Tools/Prompts/Paradigms/Observability)+ 顶部**语言切换(en/zh,默认值由 `{{ language }}` 即 `spec.language` 种子化,localStorage 记忆)**;chat 视图行为不变;标题/header 用 `{{ display_name }}`。**后端 `web.py` `/config` 不变**(仍是同一组 `_EDITABLE_FIELDS`,分页与 i18n 纯前端)。
- `README.md.j2` / `web.py.j2` — 标题用 `{{ display_name }}`(回落 slug)。

测试:`tests/test_wizard.py`(`fastapi.testclient`)+ `test_spec.py`/`test_generator.py` 增 display_name/context/分页断言 + `test_golden.py` 增 wizard 端到端 golden。

## 2. 任务拆解(实现说明)

### 2.1 生成器 wizard:字段面(全覆盖 + 按功能分页 + 语言优先)
- **首控件 = 语言**;前端 i18n 字典覆盖全部可见文案,切换即换(零新增依赖)。
- **分页**:基本(显示名→slug、`paradigms` 多选+默认)/ LLM(profiles:`name`/`model`/`api_key_env`/`base_url_env`)/ Prompts(`system`/`persona`/`rules_files`)/ Tools(内置勾选 + `mcp.enabled`+catalog 多选 + `skills.enabled`)/ Context(`strategy`/`keep_last_turns`/`max_context_tokens`)/ Budget(`max_steps`/`max_seconds`/`max_cost_usd`)/ Interfaces(`web`,`cli` 始终)/ Observability(`trace`/`trace_dir`)/ 产出。
- **采样/单价不进 wizard**:`spec.LLMProfile` 是 `extra="forbid"` 的最小集(只 name/model/api_key_env/base_url_env),采样(temperature/max_tokens)与单价是**运行期旋钮**(`config.yaml`/产物配置页 LLM tab),wizard 明确标注、不放进 spec。**budget 的 `max_tokens` 同理**(spec.Budget 无该字段,运行期才有)。
- **roles 自动派生**:有 profile 时自动写 `roles.generation = 第一个 profile`(其余 role 用户在 config.yaml 改);wizard 不做完整 roles 编辑器(保持薄)。
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

## 3. 退出门禁(对应 `01 §8` Non-blocker;✅ 实现并自验证)

- [x] **wizard 产合法 spec 并能生成可跑产物**:`POST /spec`(含 `paradigms` 多选、`mcp.enabled`+catalog、显示名→slug)→ `HarnessSpec` 校验通过 → 写 spec → `generate()` → `uv lock` → `uv sync`+import+mock 跑一步+`pytest` 全绿(`test_golden.py::test_golden_wizard_spec_generates_and_smoke_passes`,web=true 含 `test_web`)。
- [x] **wizard 不泄密 / 不进产物**:只采集/回显 env 名(`test_wizard.py::test_spec_only_holds_env_names_never_secret_values`);核心 `dependencies` 不含 fastapi/uvicorn(`test_core_dependencies_exclude_wizard_deps`),关 Web 产物不含(沿用 Slice 3 断言)。
- [x] **catalog 预填经 wizard 落 `config.yaml`**:`POST /generate` 选中 server → 产物 `config.yaml mcp.servers` 含该条目(沿用 Slice 6 catalog 落地路径;wizard golden 走 `generate(mcp_servers=...)`)。
- [x] **显示名机制**:`display_name` 渲染进产物 web 标题/header + README 标题,未设回落 slug(`test_generator.py::test_display_name_renders_in_titles_and_readme` / `test_display_name_falls_back_to_slug`)。
- [x] **产物配置分页 + 语言**:`web_index.html` 含语言开关(en/zh)+ 按功能 `cfg-tabs`;`/config` 行为不变(`test_web.py` 全绿;`test_generator.py::test_web_index_has_paged_config_and_language_switch`)。
- [x] **语言贯穿**:wizard 语言选择写入 `spec.language` → 产物 web 默认 UI 语言被种子化(`test_generator.py::test_language_seeds_product_web_default` / `test_language_defaults_to_en_in_product_web`;`test_wizard.py::test_language_threads_into_product_default`);可选 LLM 软指令**仅勾选时**追加进 `prompts.system`(`test_llm_language_directive_added_only_when_opted_in`);`spec.language` 默认 `en`、非法值被拒(`test_spec.py::test_language_*`)。
- [x] **context 种子化**:`spec.context` → `config.yaml` context 块;未设时字节一致(`test_context_block_seeds_from_spec` / `test_context_block_defaults_when_spec_omits_it`)。
- [x] **大改动回归**:动 schema(`display_name`)+ 跨 ≥3 文件 → golden 全量 + Docker 冒烟 + `uvx harnessforge new` 冒烟全绿;无框架断言(pyproject/lock 无 langchain/langgraph/adk)。
- [x] `ReadLints` clean。
- [ ] **wizard / 配置页对外可读(人审,§4②)**:起 `harnessforge wizard` 与产物 `serve` 实际点一遍,确认字段集/措辞/中英文案/默认对非作者用户友好。

## 4. 必须人审的决策点

- [x] **① wizard 字段 = 全覆盖 + 按功能分页——人 2026-06-05 定稿**。
- [x] **②（2026-06-06 细化,人拍板)**:
  - **语言优先 + 双语 + 贯穿**:wizard 与产物配置页首项/首控件为语言(中/英),后续用所选语言;wizard 的单一语言选择**贯穿**到 wizard UI + 产物 web 默认 UI 语言(`spec.language` 种子,运行期可切)+(可选)Agent 默认回答语言。**LLM 默认语言做成可选软指令**(默认关;现代模型一般按输入语言自动回答,强制会覆盖自动跟随且每轮多花 token)。
  - **显示名 → 派生 slug**:新增 `spec.display_name`(改 schema,触发 `CLAUDE.md §6.1`,**人 2026-06-06 签字**);wizard 输入显示名派生 `project_slug`。
  - **产物不做 wizard,只做分页配置页**:产物侧不做首启自动拉起 / 独立 wizard,只把 `/config` 按功能分页 + 中英切换;只改运行期行为性配置(守两轴)。
  - **LLM 规范**:本片维持 provider-agnostic;**原生 OpenAI+Anthropic 双规范登记 v1+**(人 2026-06-06:"要做双规范,但不做在 slice7,后续单独做,先记在 v1")。
- [ ] **③ 字段是否齐 / 对外可读(实现后真实验收)**:起 wizard + 产物 serve 点一遍,确认覆盖与中英措辞。
- **软确认(非阻塞,`CLAUDE.md §5.3`)**:`POST /generate` 取 render-only(卡 UI 规避,始终提供 spec 下载 / `new --spec` 接力);无构建单页(Tailwind CDN);wizard 依赖进 `[wizard]` extra;采样/单价/budget.max_tokens 留运行期(不进 spec);roles 自动派生 generation。

## 5. 本 slice 注意

- **不进产物 / 不绑框架**:wizard 仅生成器侧、FastAPI 非 agent 编排框架(`01 §1`);产物不依赖 wizard(守"生成后不再依赖 HarnessForge")。
- **密钥红线**(`CLAUDE.md §6.5`):wizard 表单 / 回显 / 产出 spec、产物配置页 / `/config` 只存 env 变量名。
- **配方 vs 活旋钮**(决策④,`01 §4`):wizard 产 `spec`(配方);产物分页 `/config` 改运行期行为性配置;结构性(接口/模块/范式拓扑=代码)只能重新生成。
- **薄**:默认产物(`web:false`)零改动、零新增依赖;产物 Web 的分页/i18n 是单页前端内的事,`web.py` 后端不变、仍薄。
- **覆盖随 spec 演进**:若 spec 再增字段,wizard 同步补。
- **v1+ 衔接**:原生 Anthropic 双规范(prompt caching / adaptive thinking + effort / Opus 4.7/4.8 禁采样 / structured outputs)登记 `00-overview §2 Slice 8+`;`/config` 与公开面隔离(Slice 3 已登记)仍是发布前提。
