# 02·04 - Slice 3:产物 Web(自持)

> 目标:给生成产物加一个**可选的、自持的 Web 接口**——FastAPI + **SSE token 级流式 chat** + **运行期 `/config` 配置面板**(行为性配置全可改)。spec 开关 `interfaces.web` 控制是否生成,**关掉则产物零 Web 痕迹、不含 fastapi/uvicorn 依赖**。默认产物仍是 Slice 1 的薄核心。
>
> 前置:Slice 2 门禁全绿。
>
> 本片首次给生成器引入「**按 spec 条件渲染文件**」机制(`web.py`/`web_index.html`/`test_web.py`/web 依赖随 `interfaces.web` 进出),为 Slice 4(MCP)、Slice 5(范式)复用。`HarnessSpec.interfaces.web` 字段 Slice 0 已预留 → 未改 schema。

## 1. 交付物

生成器侧(`harnessmith/`):

- `generator.py` — 新增**条件渲染机制** `CONDITIONAL_TEMPLATES`(相对模板路径 → `predicate(spec) -> bool`),渲染循环命中谓词且为假则跳过该文件。显式、可读、后续 slice 复用。
- `pyproject.toml.j2` — `{% if interfaces.web %}` 加 Web 依赖;**关掉则整段不渲染**。**依赖落位 = 方案 A**:`web=true` 时 `fastapi`/`uvicorn`/`ruamel.yaml` 直接进 `dependencies`(`uv sync`/Docker/`smoke_check` 零改动即装上),测试依赖 `httpx` 进 dev 组。门禁硬要求:`web=false` 时 `pyproject`/`uv.lock`/`requirements.txt` 三处均**不含** fastapi/uvicorn/httpx/ruamel。
- 一份 web-enabled 测试 fixture spec;`coding-assistant` preset 默认 `web: false`(golden 仍薄)。

生成产物侧——流式核心(**始终生成**,非 web 门控):

- `harness/llm.py` — `LLMClient` Protocol + `OpenAIClient` 增 `stream(messages, tools, on_delta)`:Chat Completions `stream=True`,逐块累积 content/tool_calls/usage,文本段回调 `on_delta`,返回与 `complete()` 同形的 `LLMResponse`(仍 Chat Completions,未切 Responses / 未换 SDK)。
- `harness/loop.py` — `run()` 增可选 `on_delta`;有则走 `stream`、否则 `complete`(核心逻辑不变,仅多一处分支)。
- `harness/mock.py` — `MockLLM.stream()` 复用 `complete()` 逐词回调,离线可测流式。
- `interfaces/cli.py` — `run` 增 `--stream/--no-stream`(默认 `false`,保持 Slice 1 行为)。

生成产物侧——Web 接口(`interfaces.web` 门控):

- `interfaces/web.py` — FastAPI 应用(薄):
  - `GET /` — 单页前端(无构建,Tailwind CDN),含 chat 视图 + config 面板视图。
  - `/chat`(SSE)— `Hooks` 子类 + 后台线程驱动 `loop.run()`,推 `token`(默认开)/ `tool_call` / `tool_result` / `step` / `final` 事件。`?stream=false` 退化为纯进度事件 + 单次 `final`(供测试/程序化调用)。
  - `GET /config` / `POST /config` — 读 / 改运行期**行为性配置**(`_EDITABLE_FIELDS = llms/roles/prompts/tools/context/observability/budget`),改后进程内即时生效**且回写 `config.yaml`**(见 §2.4);绝不读写密钥真值(只可见 env 引用名)。结构性配置(`version`/`project_slug`)与 `secrets` 不可改。
  - `POST /env` — write-only 写 `.env`(不回显);`GET /env-status` — 仅返回 `{NAME: bool}`(各 `api_key_env`/`base_url_env` 是否已设值),**布尔ONLY、key 与 url 一视同仁、绝不回读任何值**,供前端把已设的 key/url 渲染成统一长度的假星号占位(`data-masked`;聚焦清空可改、仍为占位则跳过写入,占位永不入 `.env`);`GET /rules` / `POST /rules` — 读写 rule 文件正文(限仓库内相对路径);`GET /registries` — 内省注册表;系统页相关端点(见 §2.5)。
- `interfaces/web_index.html` — 单页前端(`{{ display_name }}` 标题)。
- `interfaces/cli.py` — 条件新增 `serve` 子命令(默认 `127.0.0.1`,带 `--mock`)。
- `tests/test_web.py`(web 门控)。
- `README.md` / `AGENTS.md` — Web + 流式用法、`/config` 面板说明、"Web 依赖仅 `web: true` 时存在"。

## 2. 任务拆解

### 2.1 条件渲染机制(生成器核心,本片新能力)
`generator.py` 维护显式 `CONDITIONAL_TEMPLATES`(相对路径 → `predicate(spec)`),渲染循环命中谓词且为假则跳过。显式、可读、Slice 4/5 直接复用。

### 2.2 Web 依赖落位(关掉必须不含)
进 `dependencies`(方案 A):`uv sync`/Docker/`smoke_check` 零改动即装上,最薄。门禁硬要求 `web=false` 时三处(pyproject/lock/req)均不含 fastapi/uvicorn/httpx/ruamel。

### 2.3 SSE 流式 chat(token 级 + 进度事件,可选)
- **进度事件**:web 层 `Hooks` 子类把 `tool_call/tool_result/step/error` 投线程安全队列;`loop.run()` 后台线程跑,SSE 生成器从队列取并 `yield`,最后推 `final`。
- **token 级流式**:`LLMClient.stream(...)` 用 `stream=True` 累积并对文本段回调 `on_delta`;web `on_delta` 把文本作 `event: token` 推入队列,前端逐字追加。
- **可选**:产物 Web 始终 token 级流式(`?stream=` 服务端参数保留供测试);CLI `--stream/--no-stream`(默认关);库级传 `on_delta`。
- mock `stream()` 逐词发 token,无 key 验证流/非流两路。
- 流式下用量:`stream_options.include_usage` 取末块 usage;provider 不支持则 usage=0(与「profile 无单价」同一注意点)。

### 2.4 运行期 `/config` 面板(行为性全可改 + 回写)
- 读:`GET /config` 返回行为性字段(脱敏:只给 env 引用名)。改:`POST /config` Pydantic 重校验后更新进程内 `Config` 当场生效。
- **回写 `config.yaml`**:经 `config.py::save_config` 用 **`ruamel.yaml` 注释保留 round-trip**——读现有文件 → deep-merge 可编辑字段 → 写回,块级/字段注释 + 「被注释的可选项菜单」保留(列表 llms/tools 整体替换时元素行内注释会丢,可接受)。`create_app(config_path=...)` 记录回写路径,`serve` 透传 `--config`;传内存 config 且无路径时不落盘。`ruamel.yaml` 仅随 `interfaces.web` 进依赖。文件 watch 热重载(监听外部对 config.yaml 的改动)仍属 v1+。
- **范围**:可改 = prompts / budget / tools.enabled(allowlist;高风险工具仍受 `tools.py` 风险标记约束)/ context / profile 采样 / 定价 / paradigms。不可改 = 结构性(接口/模块/范式拓扑 = 代码,需重新生成)。

### 2.5 系统页 + 配置体验(纯前端 UX,关 Web 零痕迹、零新增依赖)
- **主题切换**:浅色(默认)/ 深色两档,纯前端 localStorage,`<head>` 内联脚本首屏即应用防闪烁,深色用受控 CSS 覆盖(非逐元素 `dark:`)。
- **流式开关**:系统页 Enable/Disable(默认 Enable),客户端偏好驱动 `/chat?stream=`。
- **配置导入/导出**:`GET /system/config-export`(下载整份 `config.yaml`,只含 env 名、永不含密钥真值)/ `POST /system/config-import`(`Config.model_validate` 校验 → 进程内替换 + 重挂逻辑 → 写回)。本地可信控制面,勿对公网暴露。
- **语言**:仅在系统页切换(en/zh),localStorage 记忆。
- **未保存守卫**:面板编辑仅在 DOM,点 Save 才 `POST /config`;脏标记用比较法(`configSnapshot()` ≠ 基线才算脏,重建拆字段的杂散事件不误标脏)、切走前 `confirm`、切回 `!dirty` 才重载。
- **Tools 分组**:前端按名分组渲染「你的工具」/ 内置工具 / 每个 MCP server 一个折叠组;`enabled` 是运行期实时开关、`config.yaml` 列出 = 声明进 allowlist 宇宙。
- **rule 文件面板内编辑正文**:每文件 `[路径输入 + markdown 正文框 + 删除]` + 「添加规则文件」;后端 `GET/POST /rules` + `_safe_repo_path`(仅允许仓库内相对路径,绝对路径/`..` 穿越一律 400)。保存折进主 Save。自动识别的约定文件(根 `CLAUDE.md`)以 `auto:true` 只读路径 + 「自动」标记显示、正文可编辑但不计入显式 `rules_files`。
- **MCP 工具自动发现**:`GET /mcp/discover`(对配置 server 连一次 + `list_tools`,失败按 server 隔离),Tools 标签打开即扫描,勾上即写入 allowlist 并启用。健康/增删改/热重连归 Slice 11(见 [`12-slice-11-mcp-management.md`](./12-slice-11-mcp-management.md))。

## 3. 退出门禁

- `/chat` SSE(mock):工具调用进度事件 + 末尾 `final`;默认 token 级流式发 `event: token`,`?stream=false` 则无 token 仍有 final。
- token 级流式核心:`MockLLM.stream` 逐 token 发文且总和等于 content;`loop.run(on_delta=...)` 把最终回答按 token 流出。
- `/config` 改运行期配置当场生效 + 回写 `config.yaml`(注释保留)+ 重载可见;无路径不落盘;非法值被 Pydantic 拒绝返 400。
- `/config` 不泄露密钥:响应只含 env 引用名;POST 的 `secrets`/结构性键被忽略。
- 关 Web 时薄验证:`interfaces.web=false` 产物不含 `web.py`/`web_index.html`/`test_web.py`,`pyproject`/`uv.lock`/`req` 不含 fastapi/uvicorn/httpx/ruamel,CLI 无 `serve`。
- 开 Web 时可跑:web-enabled spec 生成 → `uv lock` → `uv sync && pytest`(含 `test_web.py`)→ 冒烟自检。
- 黄金路径回归(关 Web)golden/docker/uvx 全绿;`web.py` 体量符合「薄」。
- `ReadLints` clean。

## 4. 关键决策

- **Web / UX 可用性**:单页 chat + config 面板可用、观感达标(经真实 LLM 浏览器验收)。
- **`/config` 可改字段范围**:`_EDITABLE_FIELDS = llms/roles/prompts/tools/context/observability/budget`;不可改结构性与 `secrets`。
- **`/config` 持久化 = 回写 `config.yaml`**(进程内即时生效 + 落盘,`ruamel` 保留注释)。理由:同一面板里 `.env`/rule 文件/memory 笔记都落盘,唯独 `/config` 只进内存会造成「每次重启 serve 都要重配」的反常识体验(尤其 wizard 产物 model 留空 + 重启即丢、chat 复被 gate)。
- **SSE 粒度 = token 级流式 + 进度事件,且可选**。
- **Web 依赖落位 = 方案 A**(直接进 `dependencies`)。
- **条件渲染机制 = `generator.CONDITIONAL_TEMPLATES`**,后续 slice 复用。
- **移除 `prompts.persona`**(改 spec schema):`persona` 在 `build_system_prompt` 里只是紧跟 `system` 后再拼一段文本,与写进 `system` 等价、无特殊语义,在 Prompts 配置页显得冗余。整条移除(spec / 产物 `PromptsConfig` / `config.yaml` / `prompts.py` / Web 输入框),只留 `system + rules_files`。
- **扩展可发现性 / 思考流可视化**等后续增量分别归 Slice 7、Slice 12(见对应子文档)。

## 5. 本 slice 注意

- **薄**:默认产物(`web: false`)与 Slice 1/2 完全一致,零新增依赖、零 Web 文件;`web.py` 自身保持薄。
- **核心改动克制**:进度事件复用既有 `Hooks`(不改 loop);token 级流式仅给 `loop.run()` 加一处可选 `on_delta` 分支,累积逻辑落在 `llm.py` 适配层。
- **密钥红线**(`CLAUDE.md §6.5`):`/config` 面板、SSE 事件、trace、日志任一路径出现明文 key 即失败;面板只可见 env 引用名;密钥真值经 `POST /env` write-only 写 `.env`。`GET /env-status` 只回 `{NAME: bool}` 是否已设,**key 与 url 都不回值**(url 也按 write-only 掩码,避免回读内嵌凭证/内网域名),前端据此显示假星号占位。
- **不绑框架**:FastAPI/uvicorn 是通用 Web 库,不是 agent 编排框架;仅在 `web=true` 时进产物。
- **配方 vs 活旋钮**(`00-overview.md` §3):`/config` 改运行期行为性配置;接口/模块/范式拓扑是结构性的,只能重新生成。Web 面板属产物自持。
- **发布拓扑前提**:`/chat` 与 `/config`(读 + 改运行期配置)挂同一 app、同端口、无鉴权;在「管理员托管 + 接口发布」拓扑下,**`/config` 须与公开面隔离**(鉴权 / 绑 localhost / 生成期开关)——隔离本体排 v1+(见 `00-overview.md` §8),也是 Slice 11 面板改 `mcp` 的前提。
