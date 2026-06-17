# 02·12 - Slice 11:MCP 健康 / 管理(产物自持的 MCP 控制面)

> 目标:给**已开启 MCP 的生成产物**(`spec.mcp.enabled`)加一套**运行期 MCP 控制面**——一个产物 Web 的 **MCP 管理页**(列出已配置 server + 连接状态红绿点 + 增删改 server 配置 + 热重连)+ **Tools 页每个 MCP 一个「大复选框」**(该 server 全部工具的总开关)+ **CLI `mcp status`**(连通性自检)。配套修三件一致性:① 新增 **SSE 传输**(兼容老 server);② Tools 页 MCP 工具状态与 server 真实连接状态一致、及时刷新;③ 下发给 LLM 的工具集与 Tools 页所见严格一致。底座做法是把「`serve` 启一次就丢句柄」的 MCP 升级为 **web 进程常驻 `McpManager` 作唯一真相源 + 保存即热重连 + 工具注册表重同步**。
>
> 前置:Slice 4(MCP 工具)、Slice 3(产物 Web `/config`)、Slice 10(HITL 确认)门禁全绿。
>
> 仍守「配方 vs 活旋钮」:**生成期只决定有无 MCP 能力**(`spec.mcp.enabled`,Slice 4 已定,本片**不改 spec schema**);server/tool/传输全运行期 `config.yaml`,本片把它们做成**面板可改 + 即时热重连生效**。关掉 MCP 的产物零 MCP 痕迹不变。

## 0. 边界与口径

- **生成期 vs 运行期(不变)**:`spec.mcp.enabled` 仍是唯一生成期开关,本片不新增 spec 字段、不改 schema。新增的 `transport` 字段、面板增删改、热重连全是运行期。
- **常驻 manager = 唯一真相源(本片核心认知)**:把 web 进程的 manager 存进 `app.state`、连接全部已配置 server,作所有 MCP 视图(管理页/Tools 页/状态)与 LLM 工具集的同一来源。修「面板看到的 / 实际在跑的 / 给 LLM 的」三套状态不一致的硬伤。
- **连接策略**:web `serve`(常驻)连接 `config.mcp.servers` 里的**全部** server(为管理页提供活的连接状态 + 工具发现),**只把 allowlist 内的工具注册进 registry**(LLM 只见启用的);CLI `run`/`chat`(一次性)沿用 Slice 4 的「有≥1 启用工具才启动该 server」;CLI `mcp status` 显式连接全部。
- **server 启停语义 = Tools 页大复选框**:**不加 per-server `enabled` 字段**。「启用 / 停用一个 server」= Tools 页该 server 的大复选框(= 它下面全部工具小复选框的总开关);彻底移除一个 server = 管理页「删除」。即:server 配置存在就连上、出现在 Tools 页;用不用它的工具由大/小复选框(allowlist)定。
- **安全面(全功能编辑,守 `00-overview.md` §4 两轴 + §10 红线)**:面板可增删/编辑 stdio(`command`/`args`/`env名`)与远程(`url`/`auth_env名`/`transport`)server。**网页能新增 stdio server = 能让产物 spawn 任意本地命令**,是**新的安全面**——按**威胁模型 A(本地可信、防手滑)**定位,**不是对不可信对手的强制边界**。文档须讲明「勿对公网暴露 `/config`/`/mcp`」;「管理员托管 + 对外发布」拓扑下需配合 `/config` 与公开面隔离(v1+),本片把 MCP 管理面一并纳入该隔离的保护对象。
- **密钥红线不变**:server 配置只存 `env名`/`auth_env名`,真值经 `.env`/进程环境解析;面板增删改 server 绝不收/不回显真值。
- **复用既有机制**:条件渲染、依赖落位、tool allowlist 过滤、HITL 确认(Slice 10)、`/config` 回写(Slice 3 `ruamel` round-trip)全部复用;新增逻辑收敛在 `mcp.py`(常驻管理 + 重连)、`web.py`(`/mcp/*` 端点 + 管理页)、`web_index.html`(MCP 标签 + Tools 大复选框)、`cli.py`(`mcp status`)。

## 1. 交付物

### 生成器侧
- `wizard/app.py` / `scaffold.py` — **DC 默认启用 + HITL 默认**:catalog 默认勾选加入 `desktop-commander`(表单排最后并带「高风险/需 Node/HITL 确认」说明);烤默认新增 `confirm: "high"`(产物默认对所有 `risk=high` 工具走 HITL 逐次确认)。**仅作用于 wizard 产物**;`coding-assistant` preset / CLI 默认不强加。`confirm: high` 走生成期渲染变量(`generate(confirm_default=...)`),不进 spec schema。
- `catalog/mcp_servers.yaml` — desktop-commander 条目补 `transport: stdio`;远程条目可标 `transport: sse`/`http` 作示例。

### 生成产物侧(`spec.mcp.enabled` 门控,关掉零痕迹不变)
- `harness/config.py` — `McpServerConfig` 新增运行期字段 `transport: Literal["stdio","http","sse"] | None = None`(留空按形态推断:`command`→stdio、`url`→http;设了则权威)。校验:`stdio` 必须有 `command`、`http`/`sse` 必须有 `url`。运行期旋钮 `McpConfig.proxy/npm_registry/pip_index`(覆盖自动探测,仅值)+ `McpConfig.connect_max_retries`(默认 4;连接自愈重试上限,0=关)。
- `harness/mcp.py`(约 250 行,仍单文件、无新抽象层)—
  - `_open_streams` 新增 **SSE 分支**(`sse_client(url, headers=...)`),按 `transport` 三选一,远程仍注入 `auth_env` Bearer header。
  - `McpManager`:连接传入的全部 server(web 常驻路径传全部;CLI 一次性路径传子集);**每个 server 一个长期 Task 同时拥有连接、session 生命周期与 `call_tool` 执行**(dispatcher 只投递请求,避免跨 task 用 session);连接超时用同 task 内的 `asyncio.timeout()`;失败隔离进 `errors`,展开 `ExceptionGroup` 叶子错误。轻量 `status()`(每 server `connected/connecting/error/tool_count`,读缓存不重连)+ 单 server `reconnect_server(name)`(只重连一个,其余不动)。
  - **热重连**:模块级 `rebuild_manager(old, config)`(新 manager `start` 成功后再 `close` 旧的;新建整体失败则保留旧的并返回错误,面板不自锁;per-server 失败隔离标红可重试)。
  - **注册表重同步**:`sync_mcp_tools(config, manager, registry=None)` = 先移除 registry 里所有 `<server>__<tool>` 旧条目,再按当前 allowlist + `manager.discovered` 注册——保证 registry 与「当前 config + 当前连接」一致。
- `harness/tools.py`(核心微改,克制)— `Registry` 加 `unregister(name)` 与 `remove_where(predicate)`(供 MCP 重同步移除旧条目)。不改 loop、不改 `active_names`/`call` 语义。
- `interfaces/web.py` — manager 升格为 `app.state` 常驻 + `/mcp/*`:
  - `create_app` 不在构造期暖机(置 None);`serve` 把 `_ensure_mcp_manager` 丢到 **daemon 线程**后立即 `uvicorn.run`,**端口秒开**;页面轮询 `/mcp/status` 看连接进度,chat 在 manager 就绪后自动拿到 MCP 工具(`/mcp`+chat 处理器 lazy `_ensure_mcp_manager`,与后台暖机经锁 + 幂等收敛到同一次连接)。进程退出 `close()`。
  - `GET /mcp/status` — 读常驻 manager `status()`(每 server `{name, transport, connected/connecting, error, tool_count, enabled_count, connecting_seconds, log_tail}`,不每次重连)。
  - `GET /mcp/discover` — 读常驻 manager `discovered`,**非阻塞**(返回 `pending` + per-server `connecting/connected`),Tools 页轮询、哪个 server 先就绪先显示其工具。
  - `POST /mcp/servers`(upsert)/ `DELETE /mcp/servers/{name}` — 校验(只收 env 名)→ `save_config` 回写(`ruamel` 保留注释)→ `rebuild_manager` 热重连 + `sync_mcp_tools` 重同步 → 返回新 `status()`。**新增 server 默认启用其全部工具**:仅当是全新 server(名未出现过)且 allowlist 里还没有它的任何条目时,自动追加一条 `<server>__*` 通配(与 preset 预填 server 一致),使其工具一连上即可用、而非默认全关;**编辑已存在的 server 绝不重加通配**,以免覆盖用户手动收窄的 allowlist。
  - `POST /mcp/reconnect` + `POST /mcp/servers/{name}/reconnect` — 手动热重连/重扫(整体 / 单 server)。
  - `POST /config` 的 MCP 联动:`tools`(allowlist,含 Tools 页大/小复选框)被改 → 追加 `sync_mcp_tools(...)`(无需重连,只按已发现工具增删 registry 条目)——修「启用了页面上的 MCP 工具但 LLM 拿不到」的关键。`mcp` 不进 `_EDITABLE_FIELDS`(server 改走专用 `/mcp/servers` 统一触发重连)。
- `interfaces/web_index.html` —
  - **新增 MCP 配置标签**(`CFG_TABS` 加 `"mcp"`,仅 `spec.mcp.enabled`):server 列表(状态红/黄/绿点 + server 名 + transport + 工具计数/错误)、每 server 可编辑/删除、底部「+ 添加 server」表单、重连/刷新;轮询 `/mcp/status`;connecting 时黄点呼吸闪烁 + 显示「connecting… Ns · <最新 stderr 行>」。中英 i18n。
  - **Tools 页大复选框**:每个 MCP server 折叠组 `<summary>` 加主复选框(全开/全关/部分三态,联动小框、纳入 allowlist 回写);组标题状态色与 `/mcp/status` 红绿一致(server 掉线标红、其工具置灰)。
- `interfaces/cli.py` — 新增 `mcp` 子命令组(仅 `spec.mcp.enabled`):`mcp status`(连接全部、`list_tools`,打印每 server 🟢/🟡/🔴 + transport + 工具计数〔启用/总〕+ 不可达错因 + 缺 launcher 提示);`mcp warm`(预拉 server 包;首跑由 `serve`/`chat` 自动触发,本命令为手动/强制重拉,见 §2)。**产物本无 `doctor` 命令**(`harnessmith doctor` 是生成器脚手架预检),健康自检即 `mcp status`。
- `README.md` / `AGENTS.md` — 「MCP 管理」章节(管理页用法、`transport` 选择、面板增删改 = 本地可信能力勿对公网暴露、`mcp status`、DC 默认开 + HITL 确认)。

### 后续增强 · MCP 密钥面板可填(本次,补「auth 闭环」)

> 背景:原片 server 卡片只暴露 `auth_env`/`env` 的**变量名**,无处填**值** —— 远程带 key 的 server(如 SaaS MCP)必须手改 `.env` 才能用,面板「开箱即用」在 Bearer 之外断在密钥这一步。本次只补「让所需字面量在面板可填 + 脱敏」,不改传输/不加方案(自定义 header / OAuth 仍 v1+,需小改 `harness/mcp.py`)。

- `interfaces/web_index.html` — server 卡片把 `auth_env`/`env` 从主网格挪进一个**折叠的「Auth(令牌/密钥)」区**(仿 LLM 卡片「高级」)。区内:① 远程 Bearer:`auth_env`(名)+ **只写值框 + 写入 .env 按钮**(复用 LLM 的 `keyRow`,`POST /env`);② stdio:`env`(逗号分隔名列表)+ 对每个已声明名各渲染一行**只写值框 + 写入 .env**。脱敏沿用 LLM 同款:已设显示掩码占位、聚焦清空可改、留空恢复掩码、**值绝不回显**;`saveMcpSecret` 复用 `/env`。i18n 加 `mcp_auth_section`(中英)。
- `interfaces/web.py` — `GET /env-status` 纳入 MCP 的 `auth_env` + stdio `env` 名(`{NAME: bool}`,仅布尔),面板据此对已设 MCP 密钥显掩码、未设可提示;仍只回布尔不回值。
- `generator.py` — `.env.example` 的 `env_names` 在 `spec.mcp.enabled` 时追加预填 server 的 `auth_env` + `env` 名(**仅名、永不写值**),用户知道该填哪些。
- **密钥红线不破**:server 配置(`/mcp/servers` / `config.yaml`)仍只存 env 名;密钥**值**走 Slice 3 既有 write-only `/env` 通道入 `.env`,不进 `config.yaml`/trace/日志/响应。

### 后续增强 · Node 启动健壮性 + 默认搜索改多引擎(本次)

> 背景:墙内 Windows 实测两处痛点 —— ① **npx 启动 Node 系 server 不可靠**:`npx` 每次启动都往临时 `_npx` 缓存重装/暂存包,Windows 上该 stage/cleanup 步骤被杀软/索引器/文件锁触发 `EPERM: rmdir` / `EBUSY`,握手前连接就被关(`McpError: Connection closed`);② **单引擎 Bing 爬虫脆**(且实测有 stdout 污染 bug 致握手超时)。本次在不改 spec schema 的前提下兜底。

- **Node server 改「装一次 + `node` 直跑」(`harness/mcp.py`)**:npx 系 server **运行期不再走 `npx`**。warm/prefetch 用 `npm install --prefix .harness/mcp-node/<server>` 把**钉版本**包装进**按 server 独立的固定目录**(`_node_install_dir`),连接时从其 `package.json` 的 `bin` 解析入口、用 `node <bin>` **直接启动**(`_node_bin_path`/`_node_server_args`)——无 `_npx`、无每次启动的 stage/cleanup,启动路径不再触发 `EPERM`;`_node_satisfied`(钉版本已装即跳过 `npm install`)让后续连接**离线秒连**。缺 `node` 仍 `FileNotFoundError`→不重试转红;包没装好是 `RuntimeError`→可重试(prefetch 补装、自愈)。Windows 上 `node` 是 `.exe` 直起(`_windows_stdio_command` 不加 cmd.exe shim),`npm`(install 期)才是 `.cmd` shim。
- **`McpServerConfig.env_const`(字面量非密钥 env)**:dict,注入 stdio 子进程环境,**权威覆盖外部同名 env**(`env[key]=value`,非 setdefault)。理由:它是 per-server 的**必需**字面量(如 `MODE=stdio`,强制 open-websearch 纯 stdio),且名字可能很通用(`MODE`!)—— 启动 harness 的 shell 里若残留 `MODE=web`,用 setdefault 会被它压过,子进程拿到 `MODE=web` 后 open-websearch **两个 transport 都不启动 → 立即退出 → `Connection closed`**(并打印 "Server mode: WEB")。故 env_const 必须赢;要改就改 `config.yaml` 的 env_const,而非外部 env。与 `env`(密钥名,走 `.env`)正交,**不碰密钥红线**、面板 Auth 区不显示它。catalog `env_const` → `server_entry()` → `config.yaml`。
- **默认搜索 server 换 `web-search`(open-websearch,Node、多引擎、免 key)**:多引擎(Bing/Baidu/DuckDuckGo/Brave/Sogou/…)带探活 + 自动 failover,单引擎慢/不可达不致全挂,比单引擎 Bing 爬虫稳得多。**删除 `bing-search`**(单引擎 + 实测 stdout 污染);`ddg-search` 保留为 uvx 系备选(无 Node 时可用)。preset/wizard 默认勾选从 bing-search 改 web-search。工具描述只说「某些网络下个别引擎可能不可达、会自动 failover」,**不提敏感关键字**。
- **warm/状态/超时三处兜底**:① warm 对 npm「仅 cleanup 警告致非零退出」按**已装成功**处理(`_node_satisfied` 为准,不看 exit code);② `status().log_tail` 让**实时自愈 note 优先于陈旧的 prefetch「ready」**,并在 prefetch 后写「connecting (MCP handshake)」标记,杜绝「显示 ready 但其实卡在握手」的误导;③ 握手超时的 `_connect_error` 提示补「若包已就绪仍超时,多半是该 server 往 stdout 写了非 JSON-RPC 文本(server 端 bug)」;④ 启动/warm 日志去 `…`,改 ASCII `...`(Windows 控制台不再乱码)。
- **Node 安装跳过浏览器二进制下载(墙内必需)**:`npm install` Node 系包时,某些**传递依赖**的 postinstall 会从 Google CDN 拉 ~150MB Chrome(实测 `desktop-commander → md-to-pdf → puppeteer`)——墙内不可达,会让整个 `npm install` **退非零、包树残缺**,运行期 `node <bin>` 再因缺模块崩溃成 `McpError: Connection closed`。`_warm_one_server` 对 **Node 安装**(`_npx_package` 非空)注入 `PUPPETEER_SKIP_DOWNLOAD=true` / `PUPPETEER_SKIP_CHROMIUM_DOWNLOAD=true`(老版名)/ `PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1`(`_NODE_INSTALL_SKIP_DOWNLOAD`,`setdefault` 不覆盖用户已设值),跳过下载让**安装与启动都过**;预填工具不需要内置浏览器(DC 的终端/文件工具、open-websearch 的 request 抓取都不依赖它,浏览器能力本就惰性加载)。uvx 安装不注入(npm 生态专用)。

### 后续修复 · 保存配置不再静默抹掉 MCP allowlist(本次)

> 现象(墙内实测,bug):新产物只配了 LLM、确认 MCP 全部连上、没动其它配置页,但模型拿不到任何 MCP 工具、系统提示反把它们列为「已禁用」,必须去 Tools 页手动勾选才好。根因不在连接、也不在生成期(生成的 `config.yaml` 确有 `<server>__*` 通配)——在产物 Web 前端 `web_index.html` 的 `collectConfig()`。

- **根因**:`POST /config` 的 `tools`(allowlist)由前端 `collectConfig()` **从 DOM 整表重建后整体替换**。而 MCP 通配 `<server>__*` 在 Tools 页**未做 discover 扫描前根本不渲染成任何复选框/`details`**(`buildTools()` 把通配只收进 `wildServers`、显式跳过 `__*` 行)。于是用户**没先打开 Tools 页**就从 LLM(或任意非 Tools)页点保存时,`collectConfig()` 产出的 `tools` **只含内置工具**,通配被静默抹除并经 `save_config` 落盘——`mcp.servers` 仍在(照常连接、管理页显示已连),但 allowlist 空了,`active_names`/`_environment_note` 都判定这些 server「无启用工具」。这是把目标 ③「下发给 LLM 的工具集与 Tools 页所见严格一致」反向打穿的一条隐蔽路径(不同于既有退出门禁「LLM == 页面」只覆盖的「勾选新工具即生效」)。
- **修复(`interfaces/web_index.html` · `collectConfig()`)**:DOM 只对**本次确实渲染了工具复选框**的 server 视为权威(记入 `renderedServers`,仅当该 `details` 有 `.tool-en` 复选框时计入);对**未渲染**的 server(Tools 页没开过,或还在连接、尚无工具),从 `cfg.tools`(上次 `GET /config` 的真相)**逐条回写**其 allowlist 条目(通配或显式),`<server>__*` 与显式 `<server>__<tool>` 都按 `__` 前缀归属到 server。既保留「整 server 全开折叠成单条通配」「取消勾选即收窄/停用」等既有交互,又杜绝「从别的页保存把通配冲掉」。附带改善:Tools 页开了但某 server **连接失败/仍在连(0 工具)** 时其通配也不再被「看一眼就丢」。
- **验证**:浏览器实测复现(生成 web+4 MCP server 产物 → serve --mock → 仅在 LLM 页填 model 后保存 → 修复前 `config.yaml` 与 `/config` 的四条通配全失、Tools 页四个 server 显示 `0/N` 未勾选;修复后四条通配保留、Tools 页 `1/1`·`6/6`·`12/12`·`26/26` 全勾)。新增守卫测试 `test_web_config_save_preserves_undiscovered_mcp_allowlist`(断言 `collectConfig` 含 `renderedServers` 权威判定 + `!renderedServers.has(server)` 的 `cfg.tools` 回写);生成器全量快测 + 产物自带测试全绿。

### 后续增强 · Web 访问能力增强(Bocha 墙内搜索 + Jina Reader 复杂网页阅读)(本次)

> 背景:基线 web 能力只有免 key 的 `web-search`(open-websearch 多引擎爬虫)与 `fetch`(`mcp-server-fetch`,静态 httpx + readability,**不执行 JS**)。两处短板:① 墙内对高质量、合规、带摘要的搜索有需求,免 key 爬虫覆盖与稳定性有限;② 复杂 / JS 渲染 / 反爬网页上 `fetch` 抓不到正文。本次只在 **catalog 加两个 opt-in 候选** + 向导可选,不改 spec schema、不进默认 preset、不给默认产物加运行期依赖。

- **catalog 两条**(`catalog/mcp_servers.yaml`,Extra candidates 区):
  - `bocha` —— 墙内合规、**带 key** 搜索(博查)。`uvx mcp-bocha-search`(`requires: uv`,可预热 / 烤进 Docker 离线),`env: [BOCHA_API_KEY]`(仅 env 名)。工具 `bocha_web_search` / `bocha_ai_search` 均只读 → `risk: safe`(plan/ask 可用)。**key 必需**:未配置时工具返回 "API key is not configured" 错误串(不崩),harness 仍连上,agent 回退到免 key 的 `web-search`。
  - `jina-reader` —— 复杂 / JS 网页阅读,**remote MCP**(Streamable HTTP)。`url: https://mcp.jina.ai/v1` + `auth_env: JINA_API_KEY`(Bearer,仅名)。headless 渲染 JS、输出干净 markdown。`read_url`/`parallel_read_url`/`search_web` 标 `safe`(其余发现工具按 `high` 兜底)。**key 实为必需**:实测 `mcp.jina.ai/v1` 网关对**所有**工具(含 `read_url`)都鉴权,未配 `JINA_API_KEY` 一律返回 HTTP 401(免 key 的是 raw `https://r.jina.ai/<url>` 前缀,本 MCP 不走它);免费 key 见 https://jina.ai 。`_bearer_headers` 在 key 未设时返回空头匿名连接(连得上但工具 401)。墙内对 `mcp.jina.ai`/`r.jina.ai` 一般**直连可用**(无需代理),稳定性需实测。
- **向导**(`scaffold.py`):二者追加到 `WIZARD_CATALOG_ORDER` **末位**、**不**进 `WIZARD_CATALOG_DEFAULT`(默认不勾);它们是 key-based 升级件,非人人需要(且 Bocha key 必需)。勾选后其全部工具经 `<server>__*` 通配默认开(既有机制,无新代码)。
- **软偏好提示(优先使用,建议性 + 自带回退)**:`scaffold.apply_web_prefs(spec_data, server_names)` —— 当向导选中 `{bocha, jina-reader}` 任一时,把一行 `WEB_PREFERENCE_HINT`(优先用更强的搜索/阅读工具,**报错或无 key 时回退 `web-search`/`fetch`**)追加到产物种子 `prompts.system`。CLI 向导 `build_spec`、Web 向导 `_spec_from_body`(`/spec` + `/generate`)均在 `with_defaults` 后、校验前调用。**仅向导路径**(CLI `--mcp-server` / preset 不注入);**未选升级件时种子 system 与运行期 `_DEFAULT_SYSTEM` 字节一致**(不变量不破)。非硬路由(守不绑编排定位)。
- **密钥红线不变**:`config.yaml`/server 配置只存 `BOCHA_API_KEY`/`JINA_API_KEY` 名;真值走 Slice 3 既有 write-only `/env`(Web)/ CLI `set-key` 入 `.env`;`generator` 在 `mcp.enabled` 且预填二者时把名加入 `.env.example`(仅名)。
- **测试**:`test_catalog.py`(`test_bocha_is_keyed_uvx_china_search` / `test_jina_reader_remote_renders_complex_pages`);`test_cli_wizard.py`(选升级件→system 含偏好段、未选→字节一致);`test_wizard.py`(`/meta` 顺序末位 + 默认不勾、`/spec` 偏好按选择注入);`test_generator.py`(`test_web_access_upgrade_servers_prefill_into_config_and_env`:config.yaml 两 server + 通配、`.env.example` 两 key 名、pyproject 无 langchain/langgraph/adk)。全量快测 + 黄金路径全绿;`harnessmith new --mcp-server bocha jina-reader` 冒烟落盘正确。

### 后续修复 · 缺 key 的 server 可填 + 显式提示(本次)

> 背景:带 key 的 server(如 `bocha`)未配 key 时连接持续失败,manager 进**自愈重试**(amber `connecting`,期间不置 `error`),Web 面板每 1.5s 轮询 `/mcp/status` 后整表 `buildMcp()` 重建 DOM——把用户刚展开的「Auth(令牌/密钥)」折叠区**反复折叠**、半填的值也被抹掉,几乎没法填 key;且重试期无任何错误文案,用户看不出是「缺 key」。

- **`interfaces/web_index.html` — 轮询不再打断编辑**:`loadMcp()` 在轮询路径下,当 `#cfg-mcp-list` 含焦点元素或有 `details[open]` 时只刷新 `mcpServers` 数据、**跳过 `buildMcp()`**(`if (!editing) buildMcp()`),编辑完成后的下一次轮询再重建。显式动作(save/reconnect/reconnect-all)仍各自直接重建,不受影响。
- **显式「缺 key / auth」提示(#2)**:`mcpServerCard` 据 `/env-status` 算 `missingSecrets`(声明了 `auth_env`/`env` 名但 `.env` 里未设的),server **未连上**且有缺失时在状态行显式标黄「⚠ needs API key / auth — set: `<NAME>`」(中英 i18n `mcp_needs_key`);判定只看 `envSet` 不依赖原始传输错误串(自愈重试期本就无 error)。
- **Auth 区自动展开**:缺 key 时 `mcpAuthSection(c, isNew, openByDefault)` 渲染为 `<details class='m-auth' open>`,用户无需翻找;手动收起记入 `mcpAuthDismissed`(`toggle` 事件),后续重建不再强行弹开(再次手动展开即清除)。与上面「编辑期不重建」协同:展开后轮询不再折叠它。
- **密钥红线不破**:仍只读 `/env-status` 布尔、值经既有 write-only `/env` 入 `.env`,提示与展开均不碰真值。
- **测试**:`test_web.py::test_index_flags_missing_mcp_key_and_keeps_auth_box_fillable`(提示 + 自动展开 + 轮询跳过编辑)。生成 web+mcp 产物 → `uv sync` → 全量 `pytest` 全绿、mock 一步跑通、pyproject 无 langchain/langgraph/adk。

### 后续修复 · auth 状态与连接状态解耦(红绿只表 server 自身、未 auth 显式提示且工具门禁)(本次)

> 现象(墙内实测,bug):带 auth 的 server 缺 key 时有两种割裂表现 ——(1)**bocha**(stdio `uvx mcp-bocha-search` + `env:[BOCHA_API_KEY]`)缺 key 时进程**启动即退出**,stdio 握手前被关 → 整 server **标红** `unhandled errors in a TaskGroup (1 sub-exception) (McpError: Connection closed)`,错误串完全不提「缺 key」;(2)**jina-reader**(remote `url` + `auth_env:JINA_API_KEY`)缺 key 时 `_bearer_headers` 返回空头**匿名连上**,网关允许 `initialize`/`list_tools`(握手成功)但每次 `call_tool` 回 401 → server **标绿**却一个工具都用不了。根因:红绿点完全由连接状态驱动,而「缺 key」提示当初被硬绑在 `!s.connected` 上(只覆盖 bocha 那种连不上),漏掉「连上但没 auth」;且后端/ Tools 页对 auth 全无概念,jina-reader 的工具经通配照常注册给 LLM → 调用即 401,把目标 ③「LLM == 页面」在这条路径打穿。

口径修正:**红绿点 = MCP server 自身连接状态(可达/连上 vs 连不上),不代表能否使用**;**auth 是独立一条轴**,显式提示 + 对「未 auth 即不可用」的 server 做工具门禁。判定信号无需新增 schema/config 字段 —— 复用既有约定「密钥走 `auth_env`/`env`(名,解析自 `.env`),字面量非密钥走 `env_const`」,故「声明了 `auth_env`/`env` 名但 `.env` 未设值」即「缺 auth」。在当前 catalog 上 9/9 精确(命中 bocha/jina-reader/github,零误伤六个免 key)。

- **`harness/mcp.py` 两个公共助手 + 注册门禁**:`missing_secrets(server)`(声明但未设的密钥名,**仅名**,两种传输/任何状态,纯提示用)、`auth_blocked(server)`(**硬门禁**,仅 `server.kind != "stdio"` 即 remote/`url` 且 `auth_env` 未设时为真)。`register_mcp_tools`/`sync_mcp_tools` **跳过 `auth_blocked` 的 server**——其工具不注册、不发给 LLM。**stdio 一律不硬扣**:进程能起来就是「无 key 也能跑」的证据,个别工具自己报错即可(与 bocha「回退 web-search」语义一致),避免误伤「可选 key」的自建 stdio server;remote 网关「匿名握手、调用必 401」决定了握手成功说明不了能用,而声明了 `auth_env` 基本即必需,故 remote 硬门禁高置信。
- **`interfaces/web.py`**:`/mcp/status` 与 `/mcp/discover` 每 server 增 `missing_secrets`(名列表)+ `needs_auth`(= `auth_blocked`);**仅名不回值**,密钥红线不破。
- **`interfaces/web_index.html` — 管理页提示解耦**:`mcpServerCard` 的 `needsSecret` 去掉 `!s.connected` 条件(`const needsSecret = !isNew && missingSecrets.length > 0`)——绿点的 jina-reader 也照样标黄「⚠ needs API key / auth — set: `<NAME>`」并自动展开 Auth 区;红绿点仍只反映连接本身。
- **`interfaces/web_index.html` — Tools 页门禁 + 失败归因**:`buildTools()` 据 `/mcp/discover` 的 `needs_auth` 把 **remote 硬门禁** server 的**大复选框 + 工具复选框置灰禁用**(`toolRow(..., disabled)` + master `disabled`)。友好提示「⚠ needs API key — set it in the MCP tab: `<NAME>`」(i18n `tools_needs_key`)的触发**与硬门禁解耦**:`showKey = blocked || (miss.length && !connected)` —— 即**任何"未连上且声明了未设密钥"的 server 也提示**(覆盖 stdio 的 bocha:缺 key 启动即退出 → 原始 `Connection closed`),且当缺 key 可解释失败时**用提示替代那条看不懂的传输错误串**(`err && !showKey` 才显示原始 error);已连上(在跑)的 server 不打扰。`discoverMcp` 轮询签名纳入 `connected`/`needs_auth`/`missing_secrets`,设 key 重连后提示/门禁自动解除。禁用的复选框仍保留真实 allowlist 态 → `collectConfig()` 原样回写,**不冲掉 `<server>__*` 通配**(设 key 后即自动可用)。
- **`interfaces/cli.py` · `mcp status`**:红绿点不变(连接轴);`auth_blocked` 的 server 补黄字「needs auth — set: X (tools withheld until set)」,其余「声明未设」补软提示「note: secret(s) not set: X」。
- **`catalog/mcp_servers.yaml`**:修 `bocha` 过时注释(实测缺 key 是**进程退出 / Connection closed 标红**,而非「仍连上、工具返回错误串」)。
- **密钥红线不破**:`/mcp/*` 仍只回 env 名 + 布尔,值经 write-only `/env` 入 `.env`,门禁判定只用 `resolve_env` 的存在性,不回显真值。
- **测试**:`test_mcp.py`(`test_auth_blocked_only_gates_remote_with_unset_bearer` / `test_register_withholds_auth_blocked_remote_tools`)、`test_web.py`(`test_mcp_status_decouples_auth_and_gates_only_remote` / `test_index_tools_page_greys_out_auth_gated_server` / `test_index_mcp_card_hint_decoupled_from_connection` / `test_index_tools_page_explains_missing_key_connect_failure`)。大改动回归(动 mcp.py/web.py/cli.py/web_index.html + catalog,跨 ≥3 文件):生成器快测 218 + 全量 golden 13 + Docker 2 + `uvx` 冒烟全绿;产物 `uv sync` → 全量 `pytest` 317 全绿、mock 一步跑通、JS 语法校验 OK、pyproject 无 langchain/langgraph/adk、`ReadLints` clean。

### 后续修复 · 编辑 MCP server 不再跳到列表末尾(本次)

> 现象(实测,bug):在 MCP 管理页改某个 server 的配置后点保存(save + 热重连),该 server 的卡片会跳到列表**最下方**;一旦用户排好顺序,每次编辑都打乱阅读位置。

- **根因**(`interfaces/web.py` · `upsert_mcp_server`):upsert 用「先按名过滤掉同名、再 `+ [server]` 追加」更新 `config.mcp.servers`,对**已存在**的 server 等于把它移到末尾;`/mcp/status` 按该顺序返回,前端 `buildMcp()` 照序渲染 → 卡片落到底部。
- **修复**:已存在则**原位替换**(`server if s.name == server.name else s`),仅**新增**才追加末尾(`existed` 已算好直接复用)。卡片阅读顺序稳定,回写的 `config.yaml` 顺序也不再漂。
- **测试**:`test_web.py::test_mcp_edit_server_keeps_its_position`(三个 server 改中间一个,断言返回顺序仍 `alpha/beta/gamma`)。生成 web+mcp 产物 → `uv sync` → 全量 `pytest` 321 全绿;生成器快测 218 全绿;`ReadLints` clean。

## 2. 跨平台运行期健壮性(收敛在 `mcp.py` + 启动脚本)

stdio MCP server(尤其 npx 系如 desktop-commander)在异构环境的首跑健壮性:

- **Windows launcher 兼容**:`.cmd/.bat` shim(如 `npx`)经 `cmd.exe /d /c <resolved.cmd>` 启动;`.exe`/非 Windows 原样直起;launcher 缺失在进入 transport 前给「装 Node.js/uv 或改 config」的可读错误,避免裸 `[WinError 2]`。
- **取数(源 + 代理)自动解析**:npx/npm 不读系统代理,故产物启动 npx/uvx 子进程时 `_stdio_net_env` 用 HTTP 探测在「override / 官方 / 镜像」× 「直连 / 走代理」候选里取首个可达源,注入 `npm_config_registry`/`UV_DEFAULT_INDEX`(+ 命中代理则 `HTTP(S)_PROXY`);`setdefault` 不覆盖用户已设值。运行期旋钮 `mcp.proxy/npm_registry/pip_index` 可覆盖。只动 index,不碰 managed-Python 下载(供应链信任红线)。
- **可读报错 + 自动预热(首跑即就绪)**:连接失败经 `_connect_error` 翻译为可读建议;**预热改为自动**:`warm_once`(sentinel `.harness/.mcp-warmed` 门控)在**首次 `serve`/`chat`** 连接前**前台**跑一遍 fetch-only 预拉,`_stream_subprocess` 把 npx/uvx 输出**逐行流式**写到终端 + 静默时发**心跳行**(冷下载不像卡死);**warm 跑过就写 sentinel(成功或失败都写)**——永久缺口(没 Node、本地已装但 registry 不可达)不会每次启动重 nag;真·瞬断由连接期 prefetch + 自愈补救。**后续启动直接跳过、秒连缓存**。一次性 `run`(脚本/Docker 路径,每次容器全新)**不预热**保持精简。catalog 里 npx/uvx 包**钉版本**(如 desktop-commander `@0.2.42`,非 `@latest`),预热缓存的就是连接要解析的那一份。手动 `mcp warm`(force,刷新 sentinel)仍在。

  > 翻转早先「`mcp warm` opt-in、不进 bootstrap 以免阻塞产物页打开」的取舍:现首跑前台预热(带进度)正是为消除「装完→MCP 超时→工具不可用→以为产物垃圾」的脏首跑;serve 仍**端口秒开**——只有「未预热过」的首跑会先跑预热,sentinel 命中后秒开不变。
- **两阶段连接 + 静默自愈(运行期兜底,覆盖没走 warm 的路径:web 后台连/重连按钮/新增 server/`run`)**:`_run_server` 拆成 ①**prefetch**(npx/uvx 经 `_warm_one_server` 用**可存活子进程**off-loop 预拉、进度进 errlog→`status().log_tail`,即便被杀 orphan 续传不丢进度)② **handshake**(`connect_timeout_seconds` 内 `initialize`+`list_tools`,缓存命中即快)。连接失败**后台带退避重试**至 `mcp.connect_max_retries`(默认 4;指数退避 base 5s、cap 60s):重试期清 error 保持 **amber**,耗尽才标 **red**;`shutdown`/`reconnect` 取消不重试(`CancelledError` 直接退出)。**两类失败不重试、立刻转 red**:① **缺 launcher**(没 Node/uv → `FileNotFoundError`,经 `_exc_has` 识别裸异常或 TaskGroup 叶子)——重试也变不出二进制;② **超总自愈预算** `_HEAL_DEADLINE_SECONDS`(300s)——兜住「每次握手都挂满 `connect_timeout`」的 server 别无限 churn。每次成功连接经 `on_connected(self)` 回调让属主**重同步 registry**(`McpManager(on_connected=…)`、`rebuild_manager(…, on_connected=…)`;web/CLI 都传 `sync_mcp_tools`)——否则自愈上来的 server 连上了但工具到不了模型。`mcp.connect_max_retries=0` = 关自愈、快速失败。
- **首连实时进度 + 工具增量**:`status()` 经 `stdio_client(errlog=临时文件)` 捕获 npx/uvx 拉包 stderr,管理页/Tools 页 amber 时显示进度;`/mcp/discover` 非阻塞 + Tools 页轮询,先就绪先显示,不被慢/失败者卡住。
- **stdout 纯净(JSON-RPC 契约)**:stdio 子进程的 stdout 必须只承载 JSON-RPC。Node 系 server 现以 `node <bin>` **直跑**(见 §1「后续增强」),启动时根本不跑 npm/npx → 不会有 `added N packages …` 安装摘要漏进 stdout;`web-search` 经 `env_const: {MODE: stdio}` 强制纯 stdio(否则默认 `both` 会另起 HTTP)。若某第三方 server 自身把非 JSON-RPC 文本写到 stdout(实测见过),握手会超时——`_connect_error` 已据此给出「疑似 server 端 stdout 污染」的提示。
- **便携 Node 自举**:仅当预填了 Node 系 server 时,产物启动脚本与向导一键 job 在缺 Node 时引导下便携 Node(pin LTS,本会话 prepend PATH);跳过/失败均不致命。
- 详见 [`08-slice-7-wizard.md`](./08-slice-7-wizard.md) §2 的跨平台启动健壮性条目(同源机制)。

## 3. 退出门禁

- SSE 传输:`transport` 校验 + `sse_client` 选择 + header 注入(无外网)。
- 常驻 manager 唯一真相源:web 进程 manager 存 `app.state`、连全部 server、注册 allowlist 工具;`/mcp/status`/`/mcp/discover` 读它;`serve` 端口秒开(`_ensure_mcp_manager` 在 daemon 线程、早于 `uvicorn.run`)。
- 热重连:`/mcp/servers`(增/删)→ 回写 `config.yaml`(注释保留)+ manager 重连 + registry 重同步;重连失败 server 标红不崩。单 server `reconnect_server` 只重连一个 + connecting 三态。
- 编辑保位:`upsert_mcp_server` 对已存在 server **原位替换**(仅新增才追加末尾),管理页卡片顺序稳定、`config.yaml` 顺序不漂。测试 `test_mcp_edit_server_keeps_its_position`。
- LLM == 页面:启用先前未注册的 MCP 工具 → 该工具进 registry/`active_names`。
- 状态一致:Tools 页 / 管理页状态读 `/mcp/status`(同一常驻 manager);server 掉线即红。
- 大复选框:server 主复选框全开/全关/部分三态 + 联动小框 + 回写 allowlist。
- CLI `mcp status`:连通性 + 工具计数 + 不可达标红 + 缺 launcher 提示(对真实 stdio dummy + broken server)。
- 首跑预热:`serve`/`chat` 首跑前台 `warm_once` 带流式进度 + 心跳、写 sentinel 后续跳过;`run` 不预热(Docker `run` 不变、不挂)。DC 钉版本(catalog 断言无 `@latest`)。
- Node 安装跳浏览器下载:`_warm_one_server` 对 Node 安装注入 `_NODE_INSTALL_SKIP_DOWNLOAD`(`PUPPETEER_SKIP_DOWNLOAD` 等,`setdefault` 不覆盖用户值);uvx 不注入。测试 `test_node_install_skips_browser_binary_download`。
- 两阶段 + 自愈:prefetch 先于 handshake;失败按 `connect_max_retries` 后台退避重试(amber→耗尽 red),成功经 `on_connected` 重同步 registry;`connect_max_retries=0` 快速失败不重试。
- wizard DC 默认 + HITL:wizard 产物默认 DC 勾选 + `confirm: high`。
- Web 访问增强:catalog 有 `bocha`(uvx + `env: [BOCHA_API_KEY]`,工具 safe)/ `jina-reader`(remote `url` + `auth_env: JINA_API_KEY`);向导二者末位 + 默认不勾;选中升级件→种子 `prompts.system` 含软偏好段、未选→字节一致;`--mcp-server bocha jina-reader` 落 config.yaml(两 server + 通配)+ `.env.example`(两 key 名,无值)。
- auth 与连接解耦:红绿点只表 server 自身连接;`missing_secrets`/`needs_auth` 进 `/mcp/status`+`/mcp/discover`;管理页缺 key 提示不再要求 `!connected`(绿点的 jina-reader 也标黄);`auth_blocked`(仅 remote+未设 `auth_env`)的 server 工具**不注册给 LLM** + Tools 页置灰禁用;stdio 不硬扣;设 key 重连即解除。
- 不泄密:`/mcp/status` 仅回 env 名;server 增删改只收 env 名;trace/日志不回显。
- 关 MCP 零痕迹:`spec.mcp.enabled=false` 产物不含 `mcp.py`/MCP 标签/`/mcp/*`/`mcp` CLI 段。
- 薄:`mcp.py` 仍单文件聚合、无新抽象层;`loop.py`/`active_names`/`call` 语义不变;`Registry` 仅加 `unregister`/`remove_where`。
- 大改动回归(动 mcp.py/web.py/cli.py/config.py + Registry 核心微改 + 跨 ≥3 文件):全量 golden + Docker + `uvx` 冒烟。`ReadLints` clean。

## 4. 关键决策

- **① DC 默认启用 + 默认 `confirm: high`(触 `CLAUDE.md §6` 全局安全基线)**:wizard 产物默认启用 desktop-commander、并默认对所有 `risk=high` 工具走 HITL 逐次确认。**这是「高风险工具默认关」基线的有意松动**——仅限 wizard 产物;安全由 **HITL(Slice 10)** 兜底(威胁模型 A;HITL 非安全边界,真隔离仍靠 Docker / 生成期不编译)。`coding-assistant` preset / CLI 默认不强加。
- **② 热重连失败的回退/报错**:per-server 失败隔离(标红 + 可读错因 + 可重试);`rebuild_manager` 新 manager `start` 成功后再 `close` 旧的,新建整体失败则保留旧 manager 并返回错误。
- **③ server 启停 = Tools 页大复选框**:不加 per-server `enabled` 字段;大复选框 = 该 server 全部工具 allowlist 的总开关;彻底移除 = 管理页删除。
- **④ SSE = 显式 `transport` 字段**:`stdio`/`http`/`sse`,留空按形态推断;老 server 用 `sse`。运行期字段,不进 spec。
- **⑤ 编辑范围 = 全功能 + 文档限定本地可信**:面板可增删改 stdio + 远程;新增 stdio = 新安全面,文档强调勿对公网暴露,纳入 v1+ `/config` 隔离保护对象。
- **⑥ 架构 = web 常驻 manager 唯一真相源 + 热重连 + 注册表重同步**;CLI `mcp status` 纳入本片(产物无 `doctor`)。

## 5. 本 slice 注意

- **薄**:关 MCP 产物逐字一致零痕迹不变;`mcp.py` 仍单文件、无新抽象层。MCP 管理页是 `spec.mcp.enabled` 门控的可选件,不进默认薄核心。
- **核心克制**:`loop.py` 不动;`active_names`/`call` 语义不变;`Registry` 只加 `unregister`/`remove_where`。一致性靠「重同步 registry」,不引新抽象层 / 不改循环。
- **密钥红线**(`CLAUDE.md §6.5`):server 增删改只收 env 名;`/mcp/*` 响应 / trace / 日志不回显真值;密钥真值仍走 Slice 3 `/env` write-only。
- **安全面(新)**:网页增 stdio server = 让产物 spawn 任意命令 = 威胁模型 A 本地控制面,非对手强制边界;勿对公网暴露 `/config`/`/mcp`,「托管+发布」拓扑须 `/config`(含 `/mcp/*`)与公开面隔离(v1+)。
- **DC / Node 依赖**:DC 默认开需 Node(npx);缺 Node 时失败隔离(管理页标红 + `mcp status` 提示装 Node),不崩产物。
- **不绑框架**:`mcp` 是协议 SDK,非 agent 编排框架,仅 `mcp.enabled` 时进产物;管理面是产物自持,HarnessSmith 不做中心化 MCP 配置/托管。
- **联网 MCP registry / `forge add` 增量接 server** 仍 v1+。
