# 02·08 - Slice 7:wizard(向导产 spec)+ 产物分页配置页

> 目标:
> ① **生成器侧 wizard**——Web 向导(`harnessmith/wizard/`,FastAPI + 无构建单页,`harnessmith[wizard]` extra)+ 终端交互向导(`harnessmith/cli_wizard.py`,questionary)。**只采集「生成什么」的结构选项**(显示名→slug、语言、`paradigms`、`interfaces.web`、`mcp.enabled`+catalog、`skills.enabled`、`memory.enabled`),**首项选语言(中文/English)**;行为性字段(llms/prompts/budget/tools…)由后端**烤可用默认值**进 spec、**不在向导露出**(降低新手门槛,产物开箱即跑)。
> ② **产物侧分页配置页**——把产物 Web 的 `/config`(Slice 3)从单一 JSON 文本框重组成**按功能分页**(LLM/Context/Tools/Paradigms/Prompts/Budget/Observability)+ **中英切换**;只改运行期行为性配置;仅 `interfaces.web=true` 时存在。产物不做 wizard、不做首启自动拉起。
>
> wizard 是**生成器侧工具**,不进产物、产物不依赖它。
>
> 前置:Slice 6/6B 门禁全绿(spec 字段集稳定)。

## 0. 边界与口径

- **wizard 产 spec(配方);产物配置页改活旋钮**:wizard 是生成期采集层(`spec` = 配方);运行期行为性配置由产物自身分页 `/config` 管。两者不混(`00-overview.md` §3）。
- **wizard 只收结构,行为性烤默认**:向导 UI 只问「生成什么」,不展示 llms/prompts/budget/context;后端对缺省项烤可用默认值(默认 LLM profile 指向 `OPENAI_API_KEY`/`OPENAI_BASE_URL`、`model` **故意留空**、默认 system prompt、内置工具开、`budget.max_steps=8`)使产物开箱即跑。理由:① 一个生成器对应多个产物,各配自己的 LLM;② 向导选项过多劝退新手;③ 初值要带进产物但不必在向导露出。`model` 留空 → 产物在用户填好 model 前门控对话(web `hasLLM` 要求非空 model),避免半配置状态用空/猜测 model 打 API。显式传入(或手写 spec)优先于默认。
- **语言选择贯穿(UI 语言)**:向导顶部单一语言选择贯穿到 ① 向导 UI、② 产物 web 默认 UI 语言(经 `spec.language` 种子化,运行期浏览器仍可切并记忆)。Agent 回答语言不在向导设(模型按用户输入语言自动回答;想固定在产物 Prompts 改)。
- **显示名 vs 包名**:新增 spec 字段 `display_name`(人类可读,用于产物 UI 标题/header + README,空则回落 `project_slug`);向导输入显示名并由它派生 `project_slug`(snake_case,可手改)。
- **spec 仍是全字段**(配方):`HarnessSpec` 字段集不变;差异只在向导 UI 暴露哪些——结构暴露、行为性烤默认。手写 spec / `--mcp-server` / 产物配置页仍可改全部行为性字段。
- **依赖隔离**:fastapi/uvicorn 进 `harnessmith[wizard]` extra;questionary 进核心 `dependencies`(终端向导用,非产物);核心 CLI、`uvx harnessmith new`、产物均不含 fastapi/uvicorn。

## 1. 交付物

生成器侧(`harnessmith/`):

- `spec.py` — `HarnessSpec` 新增 `display_name: str | None`(纯标签,不进 `config.yaml`)+ `language: Literal["en","zh"] = "en"`(产物 web 默认 UI 语言种子）。
- `scaffold.py` — 生成器/Web 向导/CLI 向导**共享**的烤默认(`BAKED_DEFAULTS`/`with_defaults`)、catalog 策展(`WIZARD_CATALOG_ORDER`/`_DEFAULT`/`curated_catalog`)、HITL 策略常量、`slugify()`。**纯 stdlib，不引 FastAPI** → 核心 `uvx harnessmith new` 仍 FastAPI-free。
- `generator.py` — 渲染上下文加 `display_name`(= `spec.display_name or spec.project_slug`)+ `language`;`config.yaml` context 块从 `spec.context` 种子化。
- `wizard/`(`[wizard]` extra 门控):`wizard/app.py`(FastAPI:`GET /`、`GET /meta`、`POST /spec`〔对缺省行为性字段烤默认 → `HarnessSpec` 校验 → spec YAML + `harnessmith new` 命令〕、`POST /generate`〔render-only,可选一键拉起〕)+ `wizard/static/index.html`（无构建精简单页:首项语言下拉 + i18n 字典 + 只两组结构选项 + 生成产物)。
- `cli_wizard.py`(questionary)— `build_spec(answers)`（纯函数）+ `run_wizard()`（问 6 项结构选项,Ctrl-C → abort）。约 180 行,不复制任何生成逻辑（复用 `scaffold` 烤默认 + 现成 `generate()`)。
- `cli.py` — `harnessmith wizard`(懒加载 Web 向导,默认自动挑空闲端口 + 打印地址 + `--open`);`new` 无 `--spec/--preset` 且 stdin 是 tty → 跑终端交互向导（`--no-input` / 非 tty 报错指路)。
- `pyproject.toml` — `[project.optional-dependencies] wizard = [fastapi, uvicorn]`;`questionary` 进核心 `dependencies`。
- 根 `HarnessSmith.{bat,sh}` 一键启动器（Web/CLI 菜单)。

产物侧(`interfaces.web` 门控):

- `interfaces/web_index.html.j2` — Config 视图重组为按功能子 tab + 顶部语言切换（`{{ language }}` 种子化 + localStorage 记忆);LLM tab 每 profile 带写入式 set-key（写 `.env`、不回显）+「测试」按钮（`POST /test-llm` 走与 loop 同一条 `complete` 路径做真实一问）+ 角色下拉（generation/compaction,空 = 回落首个 profile)。标题/header 用 `{{ display_name }}`。
- `harness/config.py` — `set_env_value(name, value)`(只写本地 gitignored `.env`、单行防注入、env 名校验);单价字段 `input_cost_per_million`/`output_cost_per_million`（per-million、货币无关);`reasoning_effort`（顶层,仅显式选了才发,默认不传)。
- `interfaces/cli.py` — `<pkg> set-key <ENV_NAME>`(隐藏输入);`serve` 默认自动挑空闲端口 + `--open`。
- 产物模板 `__launch_name__.{sh,bat}.j2` — 渲染成 `<显示名>.{sh,bat}` 一键启动脚本（文件名按 `display_name` 清洗，非法字符回落 slug);动作 = web 时 `serve --open`、否则 `chat`。
- 测试 + 产物 `README`/`AGENTS`。

## 2. 实现要点

- **结构-only 表单 + 烤默认**:向导 UI 只暴露结构控件;`scaffold.BAKED_DEFAULTS` 仅在字段缺省时填(显式优先)。显示名→slug 前端逐级派生（`lower / 非字母数字→_ / 去首尾_ / 数字开头补_`)。
- **catalog 在向导 = 策展子集**：显示 fetch/ddg-search/git/desktop-commander（默认勾前三项、DC 在最后),隐藏 github（需 token）与 time（冷门）；catalog 本体不变（CLI `--mcp-server` 照常可用)。
- **产物分页配置页**:`GET /config` 读 → 各功能 tab 表单 → Save 整体 patch（后端 Pydantic 再校验);只改行为性。语言切换纯前端 + localStorage。
- **context 两层增强**:context 由单一阈值触发重构为**触发条件 / 策略两层薄注册表**——`triggers`(内置 `max_tokens`/`max_turns`/`window_pct`,`combine: or/and` 组合)定何时压、`strategy`（truncate/summarize/none + `@register_strategy`/`@register_condition` 用户可自加）定怎么压;**默认策略 = `summarize`**,默认触发后续改为 usage 驱动的 `window_pct`(详见 [`00-overview.md`](./00-overview.md) §6「context 默认」行 + [`15-llm-robustness-and-context.md`](./15-llm-robustness-and-context.md))。`summarize` 缺 compaction 角色时回落首个 profile（用 generation 模型做摘要）。
- **扩展可发现性**:产物 `GET /registries` 内省 `STRATEGIES`/`CONDITIONS`/`PARADIGMS`/memory backends（纯名字)+ CLI `info` 列「已注册 vs 已启用」;Web Context/Paradigms tab 据此渲染下拉/勾选列表、对未注册名字标 ⚠ + 提示「可 `@register_*` 自定义,import 后即现」。
- **写入式 `.env` 密钥助手**:CLI `set-key` + Web `POST /env` / LLM tab 把 key/base_url 真值只写本地 gitignored `.env`、write-only 不回显、绝不进 `config.yaml`/spec/trace/日志。keyring 仍 v1+。生成器向导始终不收 key。
- **跨平台启动健壮性**：一键启动脚本与向导一键生成在缺 uv / 缺 Node 时带 y/N 确认地自举（uv 走 winget/官方安装器或 pip 清华源、Node 走便携二进制),并对 `uv sync`/产物 MCP 子进程做镜像源与代理自动解析（探测官方源不可达 → 用国内镜像;读系统代理注入 npx/uvx 子进程);一键生成展示分步进度条 + 实时日志尾 + 秒表。**不偷偷跑第三方 GitHub 代理脚本**(供应链信任红线)。这些是生成器侧/启动脚本的便利,产物本身不依赖向导。
- **代理探测一致性 + 可选包索引**(后补):各处「PyPI 可达性」探测统一走系统代理——`curl`(根启动器 `HarnessSmith.bat/.sh` 与产物 `__launch_name__.bat/.sh`)本身不读 WinINET / macOS GUI 代理,故探测前先把系统代理写进 `HTTP(S)_PROXY`(Win 读注册表、macOS 读 `scutil --proxy`、Linux 依赖既有 env),让 `curl` 探测与 `uv`/`urllib`(本就走系统代理)看到同一条网,避免在公司代理后误判 PyPI 不可达而切到「经此代理根本不通」的清华镜像。向导一键启动新增**可选「包索引」旋钮**(留空=自动;优先级 显式 > env `UV_DEFAULT_INDEX` > 自动探测),`/generate` 经 `index_url` 串到 `_uv_sync`;`_uv_sync` 首行把本次实际所用源(explicit/env-pinned/auto-mirror/auto-official)写进 `.setup.log` 便于事后诊断。**对墙外 / 墙内无代理 / 代理三类用户均无行为负面影响**(默认不变,唯一全局新增是 `.setup.log` 多一行说明)。

## 3. 退出门禁

- wizard（结构-only 表单)产合法 spec 并能生成可跑产物:`POST /spec` → 烤默认 → `HarnessSpec` 校验 → 写 spec → `generate()` → `uv lock` → `uv sync`+import+mock+`pytest` 全绿。
- 结构-only 表单 + 烤默认:向导 UI 只暴露结构控件;烤出默认 LLM/prompt/budget/tools 使产物完整;显式行为性字段优先于默认。
- wizard 不泄密 / 不进产物:只采集/回显 env 名;核心 `dependencies` 不含 fastapi/uvicorn。
- catalog 预填经 wizard 落 `config.yaml`;`display_name` 渲染进标题/README,未设回落 slug。
- 产物配置分页 + 语言(en/zh);语言贯穿(向导语言 → `spec.language` → 产物 web 默认);`spec.language` 默认 `en`、非法值被拒。
- context 种子化 + 条件/策略两层(`triggers` + `@register_strategy`/`@register_condition`);扩展可发现性(`GET /registries` + CLI `info` + web 渲染下拉 + 未注册标 ⚠)。
- 终端交互向导:`build_spec` 烤默认 + run_wizard 跑通 + 取消 abort + FastAPI 隔离(子进程守卫核心向导不 import FastAPI);非交互/`--no-input` 报错指路。
- 大改动回归(动 schema `display_name`/`language` + 跨 ≥3 文件):golden 全量 + Docker + `uvx harnessmith new` 冒烟;无框架断言。`ReadLints` clean。

## 4. 关键决策

- **① wizard 字段 = 全覆盖结构 + 按功能分页**(产物配置页负责行为性)。
- **② wizard 瘦身为结构-only + 行为性烤默认**;语言优先 + 双语 + 贯穿(UI);显示名派生 slug（加 `spec.display_name`,改 schema）；产物不做 wizard、只做分页配置页;LLM 维持 provider-agnostic（原生双规范见 Slice 12);写入式 `.env` 助手；端口自动侦测 + 双语语言标签。
- **⑤ context 条件/策略改造**：① 轮数 + token 可组合触发条件（`triggers` + `combine: or/and`,dict 形态);② 可扩展走薄注册表 + 装饰器（`@register_strategy`/`@register_condition`,和 tools/paradigms 同套，非运行期抽象层);③ 默认策略 = `summarize`（缺 compaction 角色回落首个 profile)。
- **⑥ 扩展可发现性**：`GET /registries` + Context/Paradigms tab 下拉/勾选 + 未注册 ⚠ + CLI `info` + AGENTS.md 专章。
- **软确认**:`POST /generate` 取 render-only（始终提供 spec 下载 / `new --spec` 接力);无构建单页（Tailwind CDN);`_BAKED_DEFAULTS` 仅缺省时填;终端向导用 questionary、与 Web 表单共享 `scaffold` 后端。

## 5. 本 slice 注意

- **不进产物 / 不绑框架**:wizard 仅生成器侧、FastAPI 非 agent 编排框架;产物不依赖 wizard。
- **密钥红线**(`CLAUDE.md §6.5`):向导表单 / 回显 / 产出 spec、产物配置页 / `/config` 只存 env 变量名;写入式 `.env` 助手 write-only。生成器向导始终不收 key。
- **配方 vs 活旋钮**(`00-overview.md` §3）:wizard 产 `spec`（配方);产物分页 `/config` 改运行期行为性配置;结构性只能重新生成。
- **薄**:默认产物（`web:false`）零改动、零新增依赖;产物 Web 分页/i18n 是单页前端内的事,`web.py` 后端不变。
- **v1+ 衔接**:原生 Anthropic 双规范见 [`125-slice-12-anthropic-dual-spec.md`](./125-slice-12-anthropic-dual-spec.md);`/config` 与公开面隔离(v1+)仍是发布前提。
