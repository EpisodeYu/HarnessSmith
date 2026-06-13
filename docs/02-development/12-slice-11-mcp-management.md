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
- `harness/config.py` — `McpServerConfig` 新增运行期字段 `transport: Literal["stdio","http","sse"] | None = None`(留空按形态推断:`command`→stdio、`url`→http;设了则权威)。校验:`stdio` 必须有 `command`、`http`/`sse` 必须有 `url`。运行期旋钮 `McpConfig.proxy/npm_registry/pip_index`(覆盖自动探测,仅值)。
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
- `interfaces/cli.py` — 新增 `mcp` 子命令组(仅 `spec.mcp.enabled`):`mcp status`(连接全部、`list_tools`,打印每 server 🟢/🟡/🔴 + transport + 工具计数〔启用/总〕+ 不可达错因 + 缺 launcher 提示);`mcp warm`(手动预拉 server 包,见 §3)。**产物本无 `doctor` 命令**(`harnessmith doctor` 是生成器脚手架预检),健康自检即 `mcp status`。
- `README.md` / `AGENTS.md` — 「MCP 管理」章节(管理页用法、`transport` 选择、面板增删改 = 本地可信能力勿对公网暴露、`mcp status`、DC 默认开 + HITL 确认)。

## 2. 跨平台运行期健壮性(收敛在 `mcp.py` + 启动脚本)

stdio MCP server(尤其 npx 系如 desktop-commander)在异构环境的首跑健壮性:

- **Windows launcher 兼容**:`.cmd/.bat` shim(如 `npx`)经 `cmd.exe /d /c <resolved.cmd>` 启动;`.exe`/非 Windows 原样直起;launcher 缺失在进入 transport 前给「装 Node.js/uv 或改 config」的可读错误,避免裸 `[WinError 2]`。
- **取数(源 + 代理)自动解析**:npx/npm 不读系统代理,故产物启动 npx/uvx 子进程时 `_stdio_net_env` 用 HTTP 探测在「override / 官方 / 镜像」× 「直连 / 走代理」候选里取首个可达源,注入 `npm_config_registry`/`UV_DEFAULT_INDEX`(+ 命中代理则 `HTTP(S)_PROXY`);`setdefault` 不覆盖用户已设值。运行期旋钮 `mcp.proxy/npm_registry/pip_index` 可覆盖。只动 index,不碰 managed-Python 下载(供应链信任红线)。
- **可读报错 + 预热**:连接失败经 `_connect_error` 翻译为可读建议;`mcp warm`(fetch-only,opt-in 手动预拉,不进向导 job 以免阻塞产物页打开)。
- **首连实时进度 + 工具增量**:`status()` 经 `stdio_client(errlog=临时文件)` 捕获 npx/uvx 拉包 stderr,管理页/Tools 页 amber 时显示进度;`/mcp/discover` 非阻塞 + Tools 页轮询,先就绪先显示,不被慢/失败者卡住。
- **便携 Node 自举**:仅当预填了 Node 系 server 时,产物启动脚本与向导一键 job 在缺 Node 时引导下便携 Node(pin LTS,本会话 prepend PATH);跳过/失败均不致命。
- 详见 [`08-slice-7-wizard.md`](./08-slice-7-wizard.md) §2 的跨平台启动健壮性条目(同源机制)。

## 3. 退出门禁

- SSE 传输:`transport` 校验 + `sse_client` 选择 + header 注入(无外网)。
- 常驻 manager 唯一真相源:web 进程 manager 存 `app.state`、连全部 server、注册 allowlist 工具;`/mcp/status`/`/mcp/discover` 读它;`serve` 端口秒开(`_ensure_mcp_manager` 在 daemon 线程、早于 `uvicorn.run`)。
- 热重连:`/mcp/servers`(增/删)→ 回写 `config.yaml`(注释保留)+ manager 重连 + registry 重同步;重连失败 server 标红不崩。单 server `reconnect_server` 只重连一个 + connecting 三态。
- LLM == 页面:启用先前未注册的 MCP 工具 → 该工具进 registry/`active_names`。
- 状态一致:Tools 页 / 管理页状态读 `/mcp/status`(同一常驻 manager);server 掉线即红。
- 大复选框:server 主复选框全开/全关/部分三态 + 联动小框 + 回写 allowlist。
- CLI `mcp status`:连通性 + 工具计数 + 不可达标红 + 缺 launcher 提示(对真实 stdio dummy + broken server)。
- wizard DC 默认 + HITL:wizard 产物默认 DC 勾选 + `confirm: high`。
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
