# 02·05 - Slice 4:MCP 工具(可选能力:生成期只 on/off,server/tool/传输全运行期)

> 目标:给生成产物加一个**可选的** MCP 工具能力——开启后,产物能连本地 **stdio** 与远程 **HTTP/SSE** 的 MCP server,把它们的工具注册进**既有**工具注册表,经 **allowlist** 控制对模型可见、沿用 Slice 1 的**风险标记**。**生成期只决定"要不要带 MCP 功能"(一个 spec 开关 + `mcp` 依赖);连哪些 server、用哪些 tool、用哪种传输,全是运行期 `config.yaml` 配置**(可经 Slice 3 `/config` 面板改 allowlist)。关掉则产物**零 MCP 痕迹、不含 `mcp` 依赖**。属 `01-project-plan.md` 的 **L2**,**默认产物仍是 Slice 1/2/3 的薄核心**(`coding-assistant` preset 保持不开 MCP)。
>
> 前置:Slice 3 门禁全绿(已 ✅)。
>
> **状态:✅ 已完成(退出门禁 §3 全绿;§4① spec 字段 2026-06-05 人已签字方案 A)。** `uv run pytest` 45 fast green(+4:spec mcp 校验 ×2、generator 关/开 MCP ×2)+ `uv run pytest -m golden` 5 green(+1:**mcp 端到端**——生成 mcp 产物 → `uv lock`(解析装 `mcp` SDK)→ `uv sync` → 产物 `pytest` 含 `test_mcp.py` 的**真实 stdio 工具调用** + allowlist 过滤 + 远程 header 注入,全绿;preset/web/uvx/docker 回归全绿)。`ReadLints` clean。命中的两处 `CLAUDE.md §6` 均已落地:
> - **§6.1**:`HarnessSpec` 新增 `mcp.enabled: bool = False`(与 `interfaces.web` 同量级)——**人 2026-06-05 签字方案 A**(只一个 bool,server/tool/传输全运行期)。
> - **§6.6 + 改全局决策**:**远程 HTTP/SSE 传输纳入 MVP**(原"仅 stdio"被取代)——**人 2026-06-03 已定向**;联网 MCP registry 仍不做(v1+)。已同步 `00-overview §3` 决策表与 `01-project-plan §3/§5`。
>
> **实现说明(与计划的细化)**:① **运行期 MCP 配置模型**(`McpServerConfig`/`McpConfig`)落产物 `config.py`(条件块),与 Slice 2 `ContextConfig` 同构——按 §2.2;`mcp.py` 仅持桥接 + 注册逻辑,实测 **183 行 / 147 行代码**(在 100–150 薄区间)。② **双传输**:`command` → stdio,`url` → 远程;远程 client 用 `hasattr` 探测兼容 SDK <2(`streamablehttp_client(headers=)`)与 >=2(`streamable_http_client(http_client=)`)的改名,依赖 pin `mcp>=1.16,<2`。③ **关 MCP 逐字一致**:实测关掉时 `config.py`/`config.yaml`/`cli.py` 与 Slice 3 字节一致(条件块用对齐空行的内联 jinja),`pyproject`/`uv.lock`/`req` 三处不含 `mcp`。④ **`/config` 改 MCP allowlist**:MCP 工具就是 `registry` 普通条目、走同一套 `tools[].enabled` 过滤,故 `/config` 编辑路径与内置工具同一套(Slice 3 已测)——本片由 `test_mcp.py` 证明 allowlist 决定 MCP 工具是否注册/暴露,未再立 MCP 专属 web fixture(见 §3)。⑤ **Windows stdio 兼容(2026-06-09 修)**:`npx` 在 Windows 上是 `.cmd` 批处理 shim,`CreateProcess`(asyncio 子进程底层)无法直接执行,导致 `[WinError 2] 系统找不到指定的文件`、server 连不上(状态显示 `5/0 工具`、工具数 0)。`_open_streams` 经 `_windows_stdio_command` 处理:Windows 下用 `shutil.which` 解析命令,凡解析到 `.cmd`/`.bat` 的(如 `npx`)改用 `cmd /c <命令> <参数...>` 启动;`.exe`(`uvx`/`python`)与非 Windows 平台**原样直起**,不受影响。新增 `test_windows_wraps_cmd_shim_for_stdio` / `test_non_windows_leaves_stdio_command_untouched` 覆盖。⑥ **并发连接(2026-06-09 改)**:`McpManager` 由"单 stack 串行连接"改为**每 server 一个 task 并发连接**——每个 task 用自己的 `AsyncExitStack` 进/出该 server 的 session(anyio 要求 session 在同一 task 进出),`_run_server` 连上(或超时/失败隔离进 `errors`)后置位 `done` 事件并挂起到 `close()`;`_main` 等所有 `done` 后才 `set_ready`。启动耗时从 Σ(各 server) 降到 max(各 server)(配合 Slice 11 serve 后台暖机,端口已秒开,这只缩短工具就绪时间)。新增 `test_connects_multiple_servers_concurrently` 覆盖 >1 server 的并发连接 + 调用 + 清理。⑦ **allowlist 通配(2026-06-09,人定向)**:支持 `<server>__*` 条目=启用该 server **现在及将来发现的全部工具**。新增 `tools.in_allowlist(name, enabled)`(精确名或 `server__*` 通配),`register_mcp_tools` 与 `Registry.active_names` 共用——两层门禁(注册期 + offer 期)一致。catalog 预填(`allowlist_entries`)改为每 server 一条 `<server>__*: true`,故**所有预填 server 全部工具默认开**(写/shell 也开);`safe_tools` 仍决定 risk 分级(读类 safe、其余 high),plan/ask 仍只拿到 safe。web Tools 面板:通配项不渲染成单行、整服勾满回存为 `server__*`、`/mcp/status` 与 `/mcp/discover` 的 enabled 计数识别通配;CLI `mcp status` 同理。新增 `test_wildcard_enables_all_server_tools` / `test_disabled_wildcard_enables_nothing`(产物自带)。⑧ **首跑健壮性 + 非阻塞连接 + 单 server 重连(2026-06-10,用户实测反馈驱动;与远程 Windows 稳定性修复合并)**:`McpManager` 增 `begin()`(非阻塞启动,连接在后台线程跑)/ `wait_ready()` / `wait_server_ready(name)`;`status()` 增第三态 `connecting`(线程在跑、既未连上也无错=连接中)。每 server 持独立 `settled` 事件 + **自己的 inbox**,`reconnect_server(name)` **单独重连一个 server**(同 task 内优雅停旧 task→重 spawn,不碰其他;`_restart` 先摘 inbox 让 dispatcher 在重连窗口快速报错)。**与 §6 的稳定性修复一并保留**:连接用同 task 的 `asyncio.timeout`(非 `wait_for`)、**每个 server task 同时拥有连接/会话/`call_tool` 执行**(dispatcher 只投递到该 server inbox)、错误经 `_format_exception` 解包、`connect_timeout_seconds` 默认 **120s**。web 侧 `_ensure_mcp_manager` 改非阻塞 + 后台 `wait_ready→sync_mcp_tools`(`/mcp/status` 不再阻塞、能立刻显示"连接中");新增 `POST /mcp/servers/{name}/reconnect`;前端绿/黄/红三色点 + 每 server 重连按钮 + `connecting` 时轮询收敛(`scheduleMcpPoll`,仅 MCP 标签可见时)。**GFW**:stdio 子进程在 `pypi.org`/`registry.npmjs.org` 不可达且用户未自设时,自动注入清华 PyPI(`UV_DEFAULT_INDEX`)/ npmmirror(`npm_config_registry`)——墙外探测通过即零注入(`_mirror_env`,启动探一次,off 主线程);Node 缺失由 `_windows_stdio_command` 给可读错误。新增/更新产物测试:`test_status_reports_connecting_field` / `test_reconnect_server_restarts_one_in_place` / `test_begin_is_non_blocking_then_wait_ready` / `test_format_exception_surfaces_taskgroup_leaves` / `test_mirror_env_only_injects_when_official_index_unreachable`;web 侧 `test_mcp_reconnect_single_server` / `test_index_has_per_server_reconnect_and_connecting_dot`,`test_mcp_status_reports_live_server_health` 改为断言"先 connecting 后 connected"。
>
> **2026-06-10 修正**:上条历史说明中的 Windows 启动与并发超时细节已细化:实际实现为 `.cmd/.bat` 经 `cmd.exe /d /c <resolved.cmd>` 启动,launcher 缺失时提前给出安装 Node.js/uv 或修改 `config.yaml` 的诊断;并发连接的超时从 `asyncio.wait_for(coro)` 改为同 task 内的 `asyncio.timeout()`,避免 MCP/anyio context 在不同 task 进出。

## 0. 边界与口径(开工前先对齐)

- **生成期 vs 运行期(本片的核心认知,纠正初版)**:按"配方 vs 活旋钮"决策(决策④,`01 §4` / `00-overview §3`)——
  - **生成期(唯一必须,结构性)**:`spec.mcp.enabled`。为真才渲染 `harness/mcp.py`、把 `mcp` 依赖写进 `pyproject`/`uv.lock`/`requirements.txt`、在 `config.py`/`config.yaml` 渲染 `mcp:` 段。运行期变不出来(不能凭空装依赖/生代码),所以它是"薄"的边界。
  - **运行期(全可改,行为性)**:连哪些 server(stdio 的 `command/args/env` 或远程的 `url/auth_env`)、每个 tool 是否 allowlist、用哪种传输——全落 `config.yaml`,加/删/换 server **不用重新生成**;tool allowlist 还能走 Slice 3 `/config` 面板当场改。
- **传输:stdio + 远程 HTTP/SSE 都做**(人 2026-06-03 定向)。某 server 配了 `command` 走 stdio、配了 `url` 走远程——**运行期按 config 形态自动选**,不引入第二个生成期开关(软确认,§4)。**联网 MCP registry**(自动拉取 server 清单)仍**不做**(v1+)。
- **catalog 挪到 Slice 5**:`harnessmith/catalog/mcp_servers.yaml` 不编译进产物,只是 `wizard`(Slice 5)/CLI 帮用户**预填 `config.yaml` server 条目**的便捷数据源("点一下 GitHub MCP"省得手敲 URL)。**Slice 4 不依赖 catalog 即可跑通**(server 直接写 `config.yaml`);本片不立 catalog 文件。
- **配方 vs 活旋钮兑现**:MCP 能力有无=结构性=spec(一个 bool);server/tool/传输=行为性=运行期。用户**天然能自带 server**(改 `config.yaml` 即可),无需经 spec/catalog 把关——故无"白名单"概念。**真正的安全闸 = 运行期 tool allowlist + 风险标记(高风险默认关)+ 密钥按 env 名注入**(见 §5)。
- **两轴 / 天花板 vs 地板(口径,见 `01 §4`)**:MCP 的**结构天花板 = `mcp.enabled`**(能力代码有无);开启后用户天然能自带 server、运行期 allowlist 在已发现工具里**只收窄不扩张**。故 MCP 是**模型 A 护栏**(可信用户防手滑 + 高风险默认关),**不是对不可信收件人的强制边界**——`/config` / `config.yaml` 改 allowlist 不构成安全保证;真要对手级隔离须靠容器 / 自托管 / server 后端凭证作用域(守"不做生产级权限系统")。上一条"安全闸"按此理解为护栏(模型 A),非强制(模型 B)。
- **复用既有机制,不另起炉灶**:条件渲染走 Slice 3 的 `generator.CONDITIONAL_TEMPLATES`;依赖落位沿用 Slice 3 方案 A(开关为真直接进 `dependencies`);MCP 工具注册进**同一个** `tools.Registry`、走**同一套** `config.enabled_tool_names()` + `registry.active_names(...)` allowlist、走**既有** `loop`/`trace`,**`loop.py` 与 `tools.Registry` 核心零改动**。

## 1. 交付物

生成器侧(`harnessmith/`):

- `harnessmith/spec.py` — `HarnessSpec` 新增 `mcp: Mcp`(`Mcp` 子模型,`extra="forbid"`)。**最小形态**:`enabled: bool = False`;可选 `servers`(初值种子,仅用于把示例 server 预写进生成的 `config.yaml`,**非生成期语义**,可省)。**字段需人审签字(§4①)**。
- `generator.py` — 在 `CONDITIONAL_TEMPLATES` 注册 MCP 模板谓词(`lambda spec: spec.mcp.enabled`):`harness/mcp.py`、`tests/test_mcp.py`、`tests/_mcp_dummy_server.py` 仅在开启时写出。
- `pyproject.toml.j2` — `{% if spec.mcp.enabled %}` 条件块加 `mcp` 依赖(pin 版本);**关掉则整段不渲染**(满足"关 MCP 不含 `mcp`"门禁,三处:`pyproject`/`uv.lock`/`requirements.txt`)。
- `config.py.j2` — `{% if spec.mcp.enabled %}` 条件块:`import` MCP 运行期模型 + 给 `Config` 加 `mcp` 字段;**关掉时 `config.py` 无 mcp 字段、无 import、无 MCP 痕迹**。
- `config.yaml.j2` — 开启时渲染带注释的 `mcp:` 段(`servers:` 可空或写 spec 初值种子);若有初值 server,顺带把其工具按 allowlist 写进 `tools:`(高风险默认 `enabled: false`,沿用 Slice 1 约定)。
- 一份 **mcp-enabled 测试 fixture spec**(`mcp.enabled: true`)供黄金 / 集成测试;`coding-assistant` preset **保持不开 MCP**(golden 仍薄)。

生成产物侧(`harnessmith/templates/`,`mcp.enabled` 门控,默认不生成):

- `src/<pkg>/harness/mcp.py` — **薄** MCP 适配层(目标 100–150 行,超薄即停问人 `CLAUDE.md §6.8`):
  - `McpServerConfig` / `McpConfig`(运行期 Pydantic 模型,`extra="forbid"`):`servers: list`,每条 `name` + 二选一形态——**stdio**(`command` / `args` / 可选 `env`:要转发进子进程的 **env 变量名**列表,真值经 `.env`/进程环境解析,**绝不在 config 里存明文**)或**远程**(`url` / 可选 `auth_env`:Bearer token 的 env 名 / 可选自定义 header env 映射)。
  - `McpManager` — 持有**后台线程 + 专属 asyncio 事件循环**:启动时按每个 server 的 config 形态选 `mcp` SDK 的 `stdio_client` 或 `streamablehttp_client`/`sse_client`,建 `ClientSession`、`initialize` + `list_tools`,经 `AsyncExitStack` 保持会话;对外只暴露**同步** `call(server, name, arguments_json) -> str`(`run_coroutine_threadsafe(...).result()` 桥接)。异步全部关在本模块内,外部接口同步,故 `loop.py`/`tools.py` 核心零改动。进程退出时关栈。
  - `register_mcp_tools(registry, config, manager)` — 把发现的 MCP 工具包成 `tools.Tool`(`parameters` 取 MCP 的 `inputSchema`,`func` 是调 `manager.call(...)` 的同步闭包,`risk` 取注解默认 `high`),注册进**既有** `registry`。**只注册 allowlist 内的工具**(`config.enabled_tool_names()`)——兑现门禁"非 allowlist tool 不注册";命名加 `{server}__{tool}` 前缀避免与内置/跨 server 冲突。
  - **失败隔离**:某 server 连不上 / `list_tools` 失败 → 记日志 + 跳过该 server,不崩整个 harness(沿用 `_run_tool` 的"工具错误不崩 loop"风格)。
- `src/<pkg>/interfaces/cli.py` — `run`/`serve` 启动路径在 `mcp.enabled` 时建 `McpManager` + `register_mcp_tools`(条件块,关掉时整段不渲染)。
- `src/<pkg>/interfaces/web.py`(若 `interfaces.web` 也开)— `/config` 把 **MCP tool 的 allowlist 纳入运行期可编辑当场生效**(复用既有 `tools[].enabled` 路径,只是过滤,不需重连);**server 列表增删改 = 改 `config.yaml` 重启生效**,热重连排 v1+(见 §2.5)。
- `tests/test_mcp.py` + `tests/_mcp_dummy_server.py`(MCP 门控)— 用 `mcp` SDK 写一个**本地 stdio mock server**(暴露 1 个安全 echo/add 工具),产物自带测试:经**真实 stdio 子进程**跑通 `list_tools` → `call_tool` → 断言**只有 allowlist 内的工具被注册**、调用结果正确、风险标记生效;**远程路径**至少覆盖"按 `url` 选 streamable-http client + `auth_env` 注入 Authorization header"(本地回环 http server 冒烟,或对传输选择 + header 注入做单测)。**全程本地、无外网、无 key**。
- `README.md` / `AGENTS.md` — 增"接 MCP 工具"章节(`config.yaml` 怎么加 stdio / 远程 server、`auth_env`/`env` 按 env 名注入、allowlist、风险标记、"MCP 依赖仅 `mcp.enabled` 时存在")。

## 2. 任务拆解

### 2.1 spec.mcp.enabled(触发 §6.1,需人审定稿)
- 现状:`HarnessSpec` 无 `mcp` 字段,也无 `mcp` 预留 passthrough(只有 `context`/`rag`/`secrets`)。新增 `mcp` 子模型 → 改 schema → **`CLAUDE.md §6.1` 触发**,定稿前停下请人 approve(§4①)。
- **最小形态**(待人审):生成期只认 `enabled`;`servers` 即便写在 spec 里也只作"写进生成 `config.yaml` 的初值种子",不改变生成期语义。守"薄":不让 spec 承担 server 编排,运行期才是 server 的权威源。

### 2.2 产物运行期 MCP 配置(不进 HarnessSpec,与 context 同构)
- `McpConfig`/`McpServerConfig` 落产物 `config.py`(条件块)——这是**运行期专属**配置,与 Slice 2 的 `ContextConfig` 同构(运行期模型不进 `HarnessSpec`),故**不触发 §6.1**。
- 导入方向:模型定义在 `config.py` 的 `{% if spec.mcp.enabled %}` 块内,`Config` 加 `mcp` 字段;`mcp.py` 反过来 `from .config import McpConfig`,避免循环依赖。
- 关掉时 `config.py` 该块整段不渲染 → 默认产物 `config.py` 与 Slice 3 逐字一致。

### 2.3 产物 MCP 适配层(薄 + 双传输 + 同步外壳 + 零 loop 改动)
- **同步/异步桥**:`mcp` SDK 是 asyncio。`McpManager` 把事件循环 + 会话关进后台线程,对外只给同步 `call()`。工具就是普通 `Tool`,走既有 `registry.call` → 既有 trace 事件(`tool_call`/`tool_result`),**`loop.py` 不动**。
- **双传输按 config 形态选**:`command` → `stdio_client`;`url` → `streamablehttp_client`(回退 `sse_client`)。共享 `ClientSession`/`list_tools`/`call_tool`/注册逻辑,传输差异只在"进哪个 client 上下文",增量小(软确认 §4:不加第二个生成期开关)。
- **allowlist = 注册门槛**:`register_mcp_tools` 只对 `config.enabled_tool_names()` 内的工具建 `Tool` 并注册;未 allowlist 的 MCP 工具**不注册不暴露**。运行期切 `tools[].enabled` 仍按既有 `active_names` 过滤是否 offer 给模型。
- **命名 / 风险**:`{server}__{tool}` 前缀(满足 function-calling 名字符集 `[A-Za-z0-9_-]`);MCP 工具 `risk` 默认 `high`(外部代码,保守),高风险默认不 allowlist。
- **薄红线**:`mcp.py` 控制在 100–150 行;桥接 + 生命周期 + 双传输若把它撑厚明显超薄,先停问人(`CLAUDE.md §6.8`)。

### 2.4 依赖落位(关掉必须不含)
- 沿用 Slice 3 **方案 A**:`mcp.enabled` 为真时 `mcp` 直接进 `dependencies`(`uv sync`/Docker/`smoke_check` 零改动即装上);为假时整段不渲染。
- **门禁硬要求**:`mcp.enabled=false` 时 `pyproject.toml` / `uv.lock` / `requirements.txt` 三处均**不含** `mcp`(沿用 Slice 1/3 三处洁净断言)。`mcp` SDK 为纯 Python,不破坏 uv 跨平台契约;**pin 版本**(`01 §6`/§10)。

### 2.5 /config 面板的 MCP 范围(本片只做"安全且无状态"的那部分)
- **可运行期当场改**:MCP tool 的 allowlist(`tools[].enabled`)——纯过滤,复用 Slice 3 既有路径,改完后续 `/chat` 立即生效。
- **暂走重启**:server 列表的增删改——改 server 需重建 `McpManager` + 重连子进程/远程会话,是**有状态重连**;本片 server 列表经 `config.yaml` + 重启生效,**热重连排 Slice 11 MCP 健康/管理**(`00-overview §2` Slice 11)。`/config` 对 server 可只读展示,不在本片做"改 server 即热重连"。

### 2.6 catalog(本片不做,挪 Slice 5)
- catalog 是 wizard/CLI 的预填便捷数据源,不进产物、不是安全闸。Slice 4 用直接写 `config.yaml` 的 fixture 跑通管线;catalog 的收录、来源标注、热门预设清单随 Slice 5 wizard 一起做。

## 3. 退出门禁(对应 `01 §8` Non-blocker,做到即验)

- [x] **MCP stdio 工具调用**(产物自带测试,本地 stdio mock server,真实子进程):`list_tools` + `call_tool` 跑通,结果正确。(`test_mcp.py::test_stdio_discovers_and_calls_tool`)
- [x] **远程传输路径覆盖**:`url` server 选远程传输 + `auth_env` 注入 `Authorization: Bearer` header(`_bearer_headers` 单测,resolve_env 经 env 名;无外网)+ 传输二选一校验。(`test_mcp.py::test_remote_server_injects_bearer_header` / `test_server_requires_exactly_one_transport`)
- [x] **非 allowlist tool 不注册**:dummy 暴露 echo+add,allowlist 只放 echo → `add` 未注册到 registry、`registry.get("dummy__add")` 抛 `ToolError`。(`test_mcp.py::test_non_allowlisted_tool_is_not_registered`)
- [x] **风险标记生效**:MCP 工具 `risk=HIGH`;allowlist 条目 `enabled: false` → 不注册。(`test_mcp.py::test_stdio_discovers_and_calls_tool` 断 `risk==HIGH` / `test_disabled_allowlist_entry_is_not_registered`)
- [x] **关 MCP 时薄验证**:`mcp.enabled=false` 产物不含 `harness/mcp.py`/`tests/test_mcp.py`/`_mcp_dummy_server.py`,`config.py` 无 mcp(字节一致),`pyproject` 不含 `mcp`,CLI 启动路径无 MCP;golden 另断言 `uv.lock`/`requirements.txt` 不含。(`test_generator.py::test_mcp_disabled_omits_mcp_files_and_deps` + golden)
- [x] **开 MCP 时可跑**:mcp-enabled spec 生成 → `uv lock` → `uv sync && pytest` 全绿(含 `test_mcp.py`,装上 `mcp` SDK)→ 冒烟自检通过。(`test_golden.py::test_golden_mcp_enabled_generates_locks_and_smoke_passes`;`test_generator.py::test_mcp_enabled_generates_files_and_deps` 快测断结构 + `py_compile`)
- [x] **MCP allowlist 运行期可控**:`test_mcp.py` 证明 allowlist(`tools[].enabled`)决定 MCP 工具是否注册/暴露;`/config` 编辑 `tools` 的当场生效路径与内置工具**同一套**(Slice 3 `test_web.py` 已测),MCP 工具是 `registry` 普通条目无需专属 web fixture。(`00-overview §2` 该格的"若同开 web"门禁据此由组合满足)
- [x] **黄金路径回归(关 MCP)**:`coding-assistant` preset 生成 → `uv sync && pytest` → mock 跑通一次工具调用,golden/docker/uvx 全绿,产物依然零 agent 框架、依然薄(无 `mcp`)。
- [x] `mcp.py` 体量符合"薄"(实测 183 行 / 147 行代码,在 100–150 区间;运行期配置模型已按 §2.2 落 `config.py`)。
- [x] `ReadLints` clean。

## 4. 必须人审的决策点

- [x] **① `HarnessSpec` 新增 `mcp.enabled`(`CLAUDE.md §6.1` 硬门槛)——人 2026-06-05 签字方案 A**:只加 `mcp.enabled: bool = False`(不带 `servers` 初值种子;server/tool/传输全运行期 `config.yaml`)。`01-project-plan §5` + `00-overview §3` 决策表已同步。
- [x] **② 远程 HTTP/SSE 传输纳入 MVP(改全局决策,人 2026-06-03 已定向)**:原"仅 stdio"被取代;远程托管(HTTP/SSE Streamable)进本片,**联网 MCP registry 仍推迟 v1+**。已据此改 `00-overview §3` / `01 §3·§5`。
- **软确认(非阻塞,`CLAUDE.md §5.3`,可一句话改判)**:
  - **不加第二个生成期开关**:`mcp.enabled` 一旦开,`mcp.py` 同时支持 stdio + 远程;每 server 用哪种由其 `config.yaml` 形态(`command` vs `url`)运行期决定。
  - **同步/异步桥** = 后台线程 + 专属事件循环 + 持久会话 + 同步 `call()`(会话复用、loop 零改动);若把 `mcp.py` 撑厚超薄则停问人。
  - **命名前缀** `{server}__{tool}` 防冲突;**MCP 工具默认 `risk=high`、默认不 allowlist**;**失败隔离**某 server 起不来则跳过不崩。
  - **/config 的 MCP 范围** = 只让 tool allowlist 运行期当场改;server 列表增删走重启,**热重连排 v1+**。
  - **catalog 挪 Slice 5**(wizard 预填),Slice 4 不依赖 catalog。

## 5. 本 slice 注意

- **薄**:默认产物(不开 MCP)必须与 Slice 1/2/3 **逐字一致**——零新增依赖、零 MCP 文件、`config.py`/`config.yaml` 零 mcp 段。MCP 是 opt-in 高级件,不塞进默认核心。`mcp.py` 自身保持薄(`CLAUDE.md §2`)。
- **核心克制**:MCP 工具注册进**既有** `registry`、走**既有** `loop`/`trace`,**不改 `loop.py`、不改 `tools.Registry` 核心**;所有 MCP 特定逻辑(双传输 + 同步桥 + 注册 + 生命周期)收在 `mcp.py`。若被迫改 loop/registry 核心,先停问人(`CLAUDE.md §6.8/§6.10`)。
- **不绑框架**:`mcp` 是协议 SDK,**不是 agent 编排框架**,不违反定位红线(`01 §1`);但仅在 `mcp.enabled` 时进产物。
- **密钥红线**(`CLAUDE.md §6.5`):stdio 的 `env` 与远程的 `auth_env`/header **只存 env 变量名**,真值经 `.env`/进程环境用既有 `resolve_env` 解析后注入子进程 / 请求头;**绝不把真值写进 spec/catalog/config.yaml/trace/日志**。高风险工具默认关,仅 allowlist 显式开(沿用 Slice 1)。MCP 工具的参数/结果进 trace 时与现有 `tool_call`/`tool_result` 同路径,注意不把含密钥的实参回显(由用户对自带 server 负责)。
- **传输**:stdio + 远程 HTTP/SSE 都做(人 2026-06-03 定向);**`/config` 改 server 热重连**已排 **Slice 11 MCP 健康/管理**;**联网 MCP registry、`forge add` 增量接 server** 仍为 v1+,不在本片(`00-overview §2` Slice 11 / Slice 14+ / `01 §3` L3)。
- **配方 vs 活旋钮**(决策④,`01 §4`):MCP 能力有无 = 结构性(spec,重新生成);server/tool/传输 = 行为性(运行期 `config.yaml` / `/config`)。MCP 配置面属**产物自持**,HarnessSmith 不做中心化配置/托管。
- **catalog 漂移**(Slice 5 再细化):server 经 `npx`/`uvx` 拉取时注意 pin 版本(`01 §10` 依赖漂移与平台兼容)。
