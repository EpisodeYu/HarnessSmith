# 02·12 - Slice 11:MCP 健康 / 管理(产物自持的 MCP 控制面)

> 目标:给**已开启 MCP 的生成产物**(`spec.mcp.enabled`)加一套**运行期 MCP 控制面**——一个产物 Web 的 **MCP 管理页**(列出已配置 server + 连接状态红绿点 + 增删改 server 配置)+ **Tools 页每个 MCP 一个"大复选框"**(该 server 全部工具的总开关)+ **CLI `mcp status`**(连通性自检)。配套修三件一致性硬伤:① 新增 **SSE 传输**(兼容老 server);② **Tools 页的 MCP 工具状态与 server 真实连接状态一致、及时刷新**;③ **下发给 LLM 的工具集与 Tools 页所见严格一致**。底座做法是把现有"`serve` 启一次就丢句柄"的 MCP 升级为 **web 进程常驻 `McpManager` 作唯一真相源 + 保存即热重连 + 工具注册表重同步**。
>
> 仍守"配方 vs 活旋钮":**生成期只决定有无 MCP 能力**(`spec.mcp.enabled`,Slice 4 已定,本片**不改 spec schema**);server/tool/传输全运行期 `config.yaml`,本片把它们做成**面板可改 + 即时热重连生效**。关掉 MCP 的产物**零 MCP 痕迹不变**。
>
> 前置:Slice 4(MCP 工具)、Slice 3(产物 Web `/config`)、Slice 10(HITL 确认)门禁全绿(均 ✅)。
>
> **状态:✅ 已实现(2026-06-09)。门禁全绿:生成器快测 124、生成产物自带测试 170(含 MCP 管理端点/状态/热重连/重同步/大复选框/transport·sse/wizard DC 默认)、golden 10 + Docker 2 全绿;CLI `mcp status`(连通 + 不可达标红 + 缺 launcher 提示)与产物 Web MCP 管理页经浏览器实测(红绿点 / 增删改热重连 / Tools 大复选框三态);`ReadLints` clean。六项决策人 2026-06-09 签字(见 §4)。**
>
> **实现说明(与计划的细化)**:① **`doctor`**:产物 CLI 本无 `doctor` 命令(`harnessforge doctor` 是**生成器**的脚手架预检,与产物无关),故 MCP 健康自检落为产物 `<pkg> mcp status`(typer 子命令组),**未在产物新增 doctor**。② **常驻 manager 连接策略**:web `serve` 启动即 `_ensure_mcp_manager` 连接全部已配置 server;CLI `run`/`chat` 一次性路径沿用"有≥1启用工具才起该 server";`mcp status` 显式连接全部。③ **`confirm: high` 走生成期渲染变量**(`generate(confirm_default=...)` → `config.yaml.j2`),**不进 spec schema**;仅 wizard `/generate` 传 `high`,CLI/preset 仍 `none`。④ **server 编辑端点**用专用 `/mcp/servers`(POST upsert / DELETE)+ `/mcp/reconnect`,**不**把 `mcp` 加进 `/config` 的 `_EDITABLE_FIELDS`(统一在专用端点触发热重连);`/config` 改 tool allowlist 后追加 `sync_mcp_tools` 重同步(无需重连)。
>
> **升格来由**:T2-G「MCP 健康自检 / 状态面板」(`03 §4`,缺口 #19)2026-06-07 由 v1+ backlog 升格为 Slice 11(三件套+记忆之后的首要方向)。Slice 3 已落地 **MCP 工具自动发现**(`GET /mcp/discover` + Tools 页扫描,见 `04-slice-3-product-web.md §4`);本片接手其"剩余项":健康/连接状态、面板增删/编辑 server(= `/config` 触安全面)、热重连,并补 SSE 传输与"页面↔server↔LLM"三方一致性。

---

## 0. 边界与口径(开工前先对齐)

- **生成期 vs 运行期(不变)**:`spec.mcp.enabled` 仍是**唯一**生成期开关(Slice 4),**本片不新增 spec 字段、不改 schema**(不触 `CLAUDE.md §6.1`)。新增的 `transport` 字段、面板增删改、热重连**全是运行期** `config.yaml` / `mcp.py` / `web.py` 的事。关 MCP 产物逐字一致不变。
- **常驻 manager = 唯一真相源(本片核心认知)**:现状 `serve` 调 `_start_mcp(config)` 启一次、**丢弃句柄**,且 `/mcp/discover` 每次**另起临时 manager** 扫描——两者分离,导致"面板看到的"与"实际在跑的"与"给 LLM 的"三套状态可能不一致(详见 §2.4 一致性硬伤)。本片把 web 进程的 manager **存进 `app.state`、连接全部已配置 server、作所有 MCP 视图(管理页/Tools 页/状态/CLI 经独立路径)与 LLM 工具集的同一来源**。
- **连接策略(自主决定,可改判)**:**web `serve`(常驻)连接 `config.mcp.servers` 里的全部 server**(为管理页提供活的连接状态 + 工具发现),**只把 allowlist 内的工具注册进 registry**(LLM 只见启用的)。**CLI `run`/`chat`(一次性)沿用 Slice 4 的"有≥1启用工具才启动该 server"**(单轮不为没用到的 server 白 spawn 子进程);**CLI `mcp status` 显式连接全部** server 报状态。这样长寿命的 web 进程是管理中枢、短命的 CLI 保持精简。
- **server 启停语义(决策 server_model=B,人 2026-06-09)**:**不加 per-server `enabled` 字段**。"启用 / 停用一个 MCP server"= Tools 页该 server 的**大复选框**(= 它下面全部工具小复选框的总开关);勾上=把该 server 的(全部已发现)工具加入 allowlist 并启用,取消=全关。**彻底移除一个 server = 管理页"删除"**(从 `config.yaml` 删条目 + 断连)。即:server **配置存在**就连上、出现在 Tools 页;**用不用它的工具**由大/小复选框(allowlist)定。
- **安全面(决策 edit_scope=full,人 2026-06-09;守 `01 §4` 两轴 + `§6` 红线)**:面板可增删/编辑 stdio(`command`/`args`/`env名`)与远程(`url`/`auth_env名`/`transport`)server。**网页能新增 stdio server = 能让产物 spawn 任意本地命令**,这是**新的安全面**——按**威胁模型 A(本地可信、防手滑)**定位:这是 own-code 本地控制面,**不是对不可信对手的强制边界**。文档须讲明"勿对公网暴露 `/config`/`/mcp`";"管理员托管 + 对外发布"拓扑下需配合 **`/config` 与公开面隔离**(仍排 Slice 13+,见 `04-slice-3-product-web.md §4` 与 `00-overview §2` Slice 13+),本片不做隔离本体,但把 MCP 管理面**一并纳入该隔离的保护对象**并在文档登记。
- **密钥红线(`CLAUDE.md §6.5`)不变**:server 配置只存 `env名`/`auth_env名`,真值经 `.env`/进程环境 `resolve_env` 解析;面板增删改 server **绝不收/不回显真值**(沿用 Slice 3 `/env` 写-only 助手填密钥)。
- **复用既有机制,不另起炉灶**:条件渲染、依赖落位、tool allowlist 过滤、HITL 确认(Slice 10)、`/config` 回写(Slice 3 `ruamel` round-trip)全部复用;新增逻辑收敛在 `mcp.py`(常驻管理 + 重连)、`web.py`(`/mcp/*` 端点 + 管理页)、`web_index.html`(MCP 标签 + Tools 大复选框)、`cli.py`(`mcp status` / `doctor`)。

---

## 1. 交付物

### 生成器侧(`harnessforge/`)

- `wizard/app.py` — **DC 默认启用 + HITL 默认**(决策 dc_default=high):
  - `_WIZARD_CATALOG_DEFAULT` 加入 `desktop-commander`(默认勾选);DC 在表单仍排最后并带"高风险/需 Node/HITL 确认"说明。
  - wizard 烤默认(`_BAKED_DEFAULTS`)新增 `confirm: "high"`(产物默认对所有 `risk=high` 工具走 HITL 逐次确认)。**这改动"高风险工具默认关"的全局安全基线**(详见 §4 决策点 + §5 注意),仅作用于 **wizard 产物**(`coding-assistant` preset / CLI 默认仍按 §0,不强加)。
  - DC 经 catalog 预填进 `config.yaml`(`mcp.servers` + 其工具入 allowlist 并 `enabled: true`);**仍只存 env 名,不收密钥**。
- `catalog/mcp_servers.yaml` — desktop-commander 条目补充 `transport: stdio`(已隐含);github 远程条目可标 `transport: sse` 或 `http` 作示例(数据源层,非安全闸)。
- 生成器测试:wizard `/meta` 含 DC 默认勾选 + 烤默认含 `confirm: high` 的断言;MCP-enabled fixture / golden 覆盖新端点与热重连(见 §3)。

### 生成产物侧(`harnessforge/templates/`,`spec.mcp.enabled` 门控,关掉零痕迹不变)

- `harness/config.py`(条件块)— `McpServerConfig` 新增运行期字段:
  - `transport: Literal["stdio", "http", "sse"] | None = None`:留空时按形态推断(`command`→stdio、`url`→http);设了则权威。`url` + `transport: sse` 走老式 HTTP+SSE。
  - 校验:`stdio` 必须有 `command`、`http`/`sse` 必须有 `url`;沿用"恰好一种传输"。
- `harness/mcp.py`(条件块,实测约 250 行 / ~202 代码行 —— 较 Slice 4 的 183/147 增量来自 SSE 分支 + `status()` + `sync_mcp_tools` + `rebuild_manager` 四处小函数,仍单文件聚合、无新抽象层,远在 300 内)—
  - `_open_streams` 新增 **SSE 分支**(`mcp.client.sse.sse_client(url, headers=...)`),按 `transport` 三选一(stdio / streamable-http / sse),远程仍注入 `auth_env` Bearer header。
  - `McpManager`:连接策略改为"连接传入的全部 server"(web 常驻路径传全部;CLI 一次性路径仍传"有启用工具的子集",由调用方决定),保留失败隔离、`discovered`/`errors`。新增轻量**存活/状态读取**(`status()` 返回每 server `connected/error/tool_count`,读 `_sessions`/`errors`/`discovered`,不重连)。
  - **热重连**:新增模块级 `rebuild_manager(old, config) -> McpManager`(关旧 + 建新 + `start`),失败隔离到 per-server `errors`(决策点②:整体不崩,失败 server 标红、面板可读错因、可重试)。
  - **注册表重同步**:新增 `sync_mcp_tools(config, manager, registry=None)` = 先**移除**registry 里所有 `<server>__<tool>` 旧 MCP 条目(见下 `tools.py`),再按当前 allowlist + `manager.discovered` 注册——保证 registry 与"当前 config + 当前连接"一致(支撑 §2.4 一致性)。`register_mcp_tools` 保留给 CLI 一次性路径,内部复用同一注册逻辑。
- `harness/tools.py`(核心微改,克制)— `Registry` 加 `unregister(name)` 与 `remove_where(predicate)`(供 MCP 重同步移除旧条目)。**不改 loop、不改 `active_names`/`call` 语义**;仅补"可移除"。
- `interfaces/web.py`(条件块)— 把 manager 升格为 `app.state` 常驻 + 新增 `/mcp/*`:
  - `create_app`(MCP 开启时)启动常驻 `McpManager(config.mcp)`(连全部 server)+ `sync_mcp_tools(...)` 注册 allowlist 工具,存 `app.state.mcp_manager`;进程退出 `close()`。`serve` 不再单独 `_start_mcp`(避免双份),改由 `create_app` 统一持有(CLI `serve` 透传 `config_path` 不变)。
  - `GET /mcp/status` — 读常驻 manager 的 `status()`:每 server `{name, transport, connected, error, tool_count, enabled_count}`(及时刷新的数据源,面板轮询/手动刷新都打它,**不每次重连**)。
  - `GET /mcp/discover`(沿用、改为读常驻 manager 的 `discovered`,不再另起临时 manager)— 返回每工具 `{name, short, description, listed, enabled}`,供 Tools 页渲染。
  - `POST /mcp/servers` — **新增或编辑**一个 server(按 name upsert):`McpServerConfig` 校验 → `save_config({"mcp": {...}}, config_path)` 回写(`ruamel` 保留注释)→ **`rebuild_manager` 热重连** + `sync_mcp_tools` 重同步 → 返回新 `status()`。仅收 env 名,拒密钥真值。
  - `DELETE /mcp/servers/{name}` — 删除 server(及其 `<name>__*` allowlist 条目)→ 回写 → 热重连 + 重同步。
  - `POST /mcp/reconnect` — 手动热重连/重扫(server 掉线后一键恢复)。
  - **`POST /config` 的 MCP 联动**:当 `tools`(allowlist)被改(含 Tools 页大/小复选框)→ 除现有"应用+回写"外,**追加 `sync_mcp_tools(...)`**(无需重连,只按已发现工具增删 registry 条目)——这是修"启用了页面上的 MCP 工具但 LLM 拿不到"的关键。`mcp` 不进 `_EDITABLE_FIELDS`(server 改走专用 `/mcp/servers` 以统一触发重连)。
  - 并发:重连/重同步在 `app.state.runs_lock` 下进行;在飞 run 用其已取的工具列表,管理动作影响后续 run(可接受,文档说明)。
- `interfaces/web_index.html`(条件块)—
  - **新增 MCP 配置标签**(`CFG_TABS` 加 `"mcp"`,仅 `spec.mcp.enabled`):server 列表,每行 **状态红绿点 + server 名 + transport + 工具计数/错误**;每 server 可**编辑**(`command`/`args`/`env名` 或 `url`/`auth_env名`/`transport`)、**删除**;底部"**+ 添加 server**"表单;"重连/刷新"按钮(打 `/mcp/reconnect` / `/mcp/status`)。轮询 `/mcp/status`(打开标签 + 定时,失败标红)。i18n 中英补全。
  - **Tools 页大复选框**(决策 server_model=B):每个 MCP server 折叠组的 `<summary>` 里加一个**主复选框**——勾/取消 = 批量勾选/取消该组全部工具(三态:全开/全关/部分);其状态与下方小复选框联动,纳入 `collectConfig` 的 allowlist 回写。组标题状态色与 `/mcp/status` 的红绿一致(server 掉线时标红、其工具置灰提示)。
- `interfaces/cli.py`(条件块)— 新增 **`mcp` 子命令组**(typer sub-app,仅 `spec.mcp.enabled`):
  - `mcp status` — 连接全部已配置 server(显式)、`list_tools`,打印每 server:🟢/🔴 连通 + transport + 工具计数(启用/总)+ 不可达错因;缺 launcher(`npx`/`node`/`uvx`,如 DC `requires: node`)给"装 Node/uv"提示。
  - **(实现说明)产物 CLI 本无 `doctor` 命令**(`harnessforge doctor` 是生成器脚手架预检),故 MCP 健康自检落为 `mcp status`,未在产物新增 `doctor`。
- `README.md` / `AGENTS.md` — 增"MCP 管理"章节:管理页用法、`transport: stdio/http/sse` 选择(老 server 用 sse)、面板增删改 = 本地可信能力勿对公网暴露、`mcp status`/`doctor`、DC 默认开 + HITL 确认怎么用。

---

## 2. 任务拆解

### 2.1 SSE 传输(兼容老 server)
- `McpServerConfig.transport`(`stdio`/`http`/`sse`,留空按形态推断);`_open_streams` 三分支:`stdio_client`(现有)/ `streamable_http`(现有,`http`)/ `sse_client`(**新增**,`sse`)。远程两种都注入 `auth_env` Bearer header。
- catalog/wizard 远程示例可标 `transport`;不引新依赖(`mcp` SDK 自带 `sse_client`)。
- 测试:`transport` 校验(stdio 无 command / http 无 url 报错)、sse 传输选择 + header 注入(本地回环或单测,无外网)。

### 2.2 常驻 manager + 热重连 + 注册表重同步(底座)
- `create_app`(MCP 开启)持有常驻 `McpManager`(连全部 server)+ `sync_mcp_tools` 注册 allowlist;`app.state.mcp_manager`;退出 `close()`。
- `rebuild_manager(old, config)`:关旧建新 `start`;per-server 失败隔离进 `errors`(决策点②:旧 manager 在新 manager `start` 成功后再 `close`;若新建整体失败则保留旧的并返回错误,不让面板把自己锁死)。
- `Registry.unregister`/`remove_where` + `sync_mcp_tools`(移除旧 `__` 条目 → 按当前 allowlist+discovered 重注册)。`loop`/`active_names` 不动。
- 测试:改 server 配置 → `/mcp/servers` → manager 重连 + registry 重同步(mock/真实 stdio dummy);重连失败标红不崩。

### 2.3 MCP 管理页(产物 Web 新标签)
- 前端 `mcp` 标签:server 列表(红绿点 + 名 + transport + 计数/错误)+ 编辑/删除/添加表单 + 重连/刷新;轮询 `/mcp/status`。
- 后端 `/mcp/status`(读常驻 manager)、`/mcp/servers`(upsert / delete,回写 + 热重连)、`/mcp/reconnect`。
- 仅收 env 名;路径/输入校验沿用既有风格;**结构性(`spec.mcp.enabled`)不可在此改**(那要重新生成)。
- 测试:`/mcp/status` 返回连接态;`/mcp/servers` 增/改/删 → 回写 config.yaml(注释保留)+ 重连生效 + 不泄密;无 server 短路。

### 2.4 Tools 页一致性 + 大复选框(需求 #2/#3/#4/#6)
- **#4 状态一致 + 及时刷新**:Tools 页 MCP 分组状态色 / 工具可用性读 `/mcp/status`(同一常驻 manager),server 掉线即红、其工具置灰;打开标签 + 定时刷新。**不再**用与运行态分离的临时扫描。
- **#3 LLM == 页面**:`POST /config` 改 allowlist 后追加 `sync_mcp_tools` → registry 立即与 allowlist 一致;`active_names` 据此过滤 → 下发给 LLM 的工具集 == 页面勾选 == registry。新启用一个之前没注册的 MCP 工具现在能被注册并下发(修核心硬伤)。
- **#6/#2 大复选框 = server 总开关**:每 server 组 `<summary>` 加主复选框(全开/全关/部分三态),批量改其工具 allowlist;"启用/停用 server"即此(决策 server_model=B)。
- 测试:启用一个先前未注册的 MCP 工具 → 下次 run 该工具进 `active_names`(mock);大复选框全开/全关联动小框 + 回写;server 掉线时页面标红、其工具不下发。

### 2.5 编辑 server 的安全面(决策 edit_scope=full)
- 全功能增删改(stdio + 远程)经 `/mcp/servers`;**绝不收密钥真值**(只 env 名)。
- 文档强调:这是**本地可信(威胁模型 A)**控制面,**勿对公网暴露 `/config`/`/mcp`**;"管理员托管+发布"拓扑下须 `/config` 与公开面隔离(Slice 13+,本片把 `/mcp/*` 一并登记为该隔离保护对象)。

### 2.6 CLI `mcp status`(决策 cli=include)
- `mcp` typer 子命令组 + `status`(连全部、报红绿/计数/错因/缺 launcher 提示)。MCP 关时不渲染。**(实现说明)** 产物无 `doctor` 命令(生成器才有),故不在产物扩 doctor。
- 测试:`mcp status` 对本地 stdio dummy 报连通 + 工具计数;不可达 server 报红不崩(实测)。

### 2.7 wizard:DC 默认启用 + HITL 默认(决策 dc_default=high)
- `_WIZARD_CATALOG_DEFAULT` 加 `desktop-commander`;`_BAKED_DEFAULTS` 加 `confirm: "high"`。
- 仅作用于 wizard 产物;`coding-assistant` preset / CLI 默认不强加(保持各自现状,文档说明)。
- DC 需 Node:wizard/README 提示;`mcp status`/`doctor` 检测缺 Node;Docker 基线说明(npx 需 Node,离线/容器策略沿用 Slice 6)。
- 测试:wizard 产物默认含 DC 启用 + `confirm: high`;mock 跑通(DC 实际需 Node,测试用 mock/失败隔离覆盖,不强依赖 Node 装好)。

---

## 3. 退出门禁(对应 `01 §8` Non-blocker,做到即验)

- [x] **SSE 传输**:`transport` 校验 + `sse_client` 选择 + header 注入(`test_mcp.py::test_transport_field_selects_kind_and_validates` + 既有 `_bearer_headers` 单测,无外网)。
- [x] **常驻 manager 唯一真相源**:web 进程 manager 存 `app.state`、连全部 server、注册 allowlist 工具;`/mcp/status`/`/mcp/discover` 读它(不另起临时 manager;`_ensure_mcp_manager`)。
- [x] **热重连**:`/mcp/servers`(增/删)→ 回写 `config.yaml`(`ruamel` 注释保留)+ manager 重连 + registry 重同步(`test_web.py::test_mcp_add_and_delete_server_persists_and_reconnects`);重连失败 server 标红不崩(`mcp status` 实测 broken server;决策点②)。
- [x] **#3 LLM==页面**:启用先前未注册的 MCP 工具 → 该工具进 registry/`active_names`(`test_web.py::test_config_enabling_mcp_tool_registers_it_for_the_model` + `test_mcp.py::test_sync_mcp_tools_resyncs_registry`)。
- [x] **#4 状态一致**:Tools 页 / 管理页状态读 `/mcp/status`(同一常驻 manager);server 掉线即红(浏览器实测 broken 红点 + Tools 组红字错误)。
- [x] **#6 大复选框**:server 主复选框全开/全关/部分三态 + 联动小框 + 回写 allowlist(浏览器实测 1/2 显示 indeterminate;`test_web.py::test_index_has_mcp_management_ui` 断 `mcp-master`)。
- [x] **CLI `mcp status`**:连通性 + 工具计数 + 不可达标红 + 缺 launcher 提示(对真实 stdio dummy + broken server 实测;`McpManager.status()` 由 `test_status_reports_connection_and_tool_count` 覆盖)。
- [x] **wizard DC 默认 + HITL**:wizard 产物默认 DC 勾选 + `confirm: high`(`test_wizard.py::test_meta_catalog_curates_order_defaults_and_hides_niche` 含 DC;`_with_default_tools` 启用 DC 工具;生成产物渲染 `confirm: high` 实测)。
- [x] **不泄密**:`/mcp/status` 仅回 env 名(`config` 字段无真值);server 增删改只收 env 名;trace/日志不回显(沿用 Slice 4)。
- [x] **关 MCP 零痕迹**:`spec.mcp.enabled=false` 产物不含 `mcp.py`/MCP 标签/`/mcp/*`/`mcp` CLI 段(条件渲染 + `test_generator` 既有断言;`thin` golden `uv.lock` 不含 `mcp`)。
- [x] **薄**:`mcp.py` 实测约 250 行(含常驻管理 + 重连 + 重同步 + SSE + status,仍单文件聚合,无新抽象层);`loop.py`/`active_names`/`call` 语义不变;`Registry` 仅加 `unregister`/`remove_where`。
- [x] **大改动回归(动 mcp.py/web.py/cli.py/config.py + Registry 核心微改 + 跨≥3 文件,触 `§5.2`)**:全量 golden 10 + Docker 2(MCP/web/baseline 产物)+ `uvx harnessforge new` 冒烟全绿。
- [x] **黄金路径回归**:`coding-assistant`(含 MCP baseline)golden 端到端绿;关 MCP 的 `thin`/example golden 绿。`ReadLints` clean。

---

## 4. 必须人审的决策点(均人 2026-06-09 签字)

- [x] **① DC 默认启用 + 默认 `confirm: high`(触 `CLAUDE.md §6` 全局安全基线,人 2026-06-09 签字)**:wizard 产物默认启用 desktop-commander(shell + 全盘文件读写)、并默认对所有 `risk=high` 工具走 HITL 逐次确认。**这是"高风险工具默认关"基线的有意松动**——仅限 wizard 产物;安全由 **HITL(Slice 10)** 兜底(威胁模型 A:可信但会手滑;HITL 非安全边界,真隔离仍靠 Docker / 生成期不编译,见 `01 §4`)。`coding-assistant` preset / CLI 默认不强加。已同步 `00-overview §3` 安全行 + `01 §6` 实现说明。
- [x] **② 热重连失败的回退/报错形态(人 2026-06-09)**:per-server 失败隔离(失败 server 标红 + 面板可读错因 + `/mcp/reconnect` 可重试);`rebuild_manager` 新 manager `start` 成功后再 `close` 旧的,新建整体失败则保留旧 manager 并返回错误(面板不自锁)。
- [x] **③ server 启停 = Tools 页大复选框(server_model=B,人 2026-06-09)**:不加 per-server `enabled` 字段;大复选框 = 该 server 全部工具 allowlist 的总开关;彻底移除 = 管理页删除。
- [x] **④ SSE = 显式 `transport` 字段(人 2026-06-09)**:`stdio`/`http`/`sse`,留空按形态推断;老 server 用 `sse`。运行期字段,不进 spec。
- [x] **⑤ 编辑范围 = 全功能 + 文档限定本地可信(edit_scope=full,人 2026-06-09)**:面板可增删改 stdio + 远程 server;新增 stdio = 新安全面,文档强调勿对公网暴露,纳入 Slice 13+ `/config` 隔离保护对象。
- [x] **⑥ 架构 = web 常驻 manager 唯一真相源 + 热重连 + 注册表重同步(arch=persistent,人 2026-06-09)**;CLI `mcp status` 纳入本片(cli=include;产物无 `doctor`,健康自检即 `mcp status`,见头部实现说明①)。
- **软确认(非阻塞,`§5.3`,可一句话改判)**:web `serve` 连接全部已配置 server(管理页活状态来源),CLI 一次性路径仍只起"有启用工具"的 server;`/mcp/status` 读缓存状态 + 手动重连,不每次重连。

---

## 5. 本 slice 注意

- **薄**:关 MCP 产物逐字一致零痕迹不变;`mcp.py` 实测约 250 行(增量来自 SSE/status/sync/rebuild 四处小函数,仍单文件、无新抽象层,< 300)。MCP 管理页是 `spec.mcp.enabled` 门控的可选件,不进默认薄核心。
- **核心克制**:`loop.py` 不动;`active_names`/`call` 语义不变;`Registry` 只加 `unregister`/`remove_where`(为重同步)。一致性靠"重同步 registry",不引新抽象层 / 不改循环(守 `§6.8/§6.10`)。
- **密钥红线(`§6.5`)**:server 增删改只收 env 名;`/mcp/*` 响应 / trace / 日志不回显真值;密钥真值仍走 Slice 3 `/env` 写-only。
- **安全面(新)**:网页增 stdio server = 让产物 spawn 任意命令 = 威胁模型 A 本地控制面,**非**对手强制边界;文档强调勿对公网暴露 `/config`/`/mcp`,"托管+发布"拓扑须 `/config` 与公开面隔离(Slice 13+,`/mcp/*` 纳入保护)。DC 默认开靠 HITL 兜底,但 HITL 也非安全边界(`01 §4`)。
- **DC / Node 依赖**:DC 默认开需 Node(npx);缺 Node 时失败隔离(管理页标红 + `mcp status`/`doctor` 提示装 Node),不崩产物。Docker/离线沿用 Slice 6(uvx server 可烤镜像;Node server 需镜像带 Node,文档说明)。
- **不绑框架**:`mcp` 是协议 SDK,非 agent 编排框架,仅 `mcp.enabled` 时进产物;管理面是产物自持,**HarnessForge 不做中心化 MCP 配置/托管**(守"生成后不再依赖 HarnessForge")。
- **联网 MCP registry / `forge add` 增量接 server** 仍 v1+(Slice 13+),不在本片。
