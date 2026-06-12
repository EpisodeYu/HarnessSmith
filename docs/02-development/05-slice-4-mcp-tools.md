# 02·05 - Slice 4:MCP 工具(可选能力)

> 目标:给生成产物加一个**可选的** MCP 工具能力——开启后能连本地 **stdio** 与远程 **HTTP/SSE** 的 MCP server,把工具注册进**既有**工具注册表,经 **allowlist** 控制对模型可见、沿用 Slice 1 风险标记。**生成期只决定「要不要带 MCP 功能」(一个 spec 开关 + `mcp` 依赖);连哪些 server、用哪些 tool、用哪种传输,全是运行期 `config.yaml`**。关掉则产物零 MCP 痕迹、不含 `mcp` 依赖。默认产物仍是薄核心。
>
> 前置:Slice 3 门禁全绿。
>
> 命中两处 `CLAUDE.md §6`:**§6.1** `HarnessSpec` 新增 `mcp.enabled: bool = False`(与 `interfaces.web` 同量级,只一个 bool);**§6.6 + 改全局决策** 远程 HTTP/SSE 传输纳入 MVP(取代「仅 stdio」),联网 MCP registry 仍 v1+。

## 0. 边界与口径

- **生成期 vs 运行期**:
  - **生成期(唯一必须,结构性)**:`spec.mcp.enabled`。为真才渲染 `harness/mcp.py`、把 `mcp` 依赖写进 `pyproject`/`uv.lock`/`requirements.txt`、在 `config.py`/`config.yaml` 渲染 `mcp:` 段。运行期变不出来,所以它是「薄」的边界。
  - **运行期(全可改,行为性)**:连哪些 server(stdio 的 `command/args/env` 或远程的 `url/auth_env`)、每个 tool 是否 allowlist、用哪种传输——全落 `config.yaml`,加/删/换 server 不用重新生成;tool allowlist 还能走 Slice 3 `/config` 面板当场改。
- **传输:stdio + 远程 HTTP/SSE 都做**。某 server 配了 `command` 走 stdio、配了 `url` 走远程,运行期按 config 形态自动选,不引入第二个生成期开关。联网 MCP registry 仍不做(v1+)。
- **catalog 挪到 Slice 6**:`catalog/mcp_servers.yaml` 不编译进产物,只是 wizard/CLI 帮用户预填 `config.yaml` server 条目的便捷数据源。Slice 4 不依赖 catalog 即可跑通。
- **真正的安全闸 = 运行期 tool allowlist + 风险标记(高风险默认关)+ 密钥按 env 名注入**。用户天然能自带 server(改 `config.yaml`),无「白名单」概念。MCP 是**模型 A 护栏**(防手滑 + 高风险默认关),非对手级强制(`00-overview.md` §4)。
- **复用既有机制**:条件渲染走 Slice 3 `CONDITIONAL_TEMPLATES`;依赖落位沿用方案 A;MCP 工具注册进**同一个** `tools.Registry`、走**同一套** allowlist 与 `loop`/`trace`,**`loop.py` 与 `tools.Registry` 核心零改动**。

## 1. 交付物

生成器侧:

- `spec.py` — `HarnessSpec` 新增 `mcp: Mcp`(`Mcp` 子模型 `extra="forbid"`)。最小形态 `enabled: bool = False`;可选 `servers`(初值种子,仅把示例 server 预写进生成的 `config.yaml`)。
- `generator.py` — `CONDITIONAL_TEMPLATES` 注册 MCP 模板谓词:`harness/mcp.py`、`tests/test_mcp.py`、`tests/_mcp_dummy_server.py` 仅在开启时写出。
- `pyproject.toml.j2` — `{% if spec.mcp.enabled %}` 加 `mcp` 依赖(pin 版本);关掉整段不渲染。
- `config.py.j2` / `config.yaml.j2` — 条件块渲染 MCP 运行期模型 + `mcp:` 段;关掉时无 mcp 痕迹。
- 一份 mcp-enabled 测试 fixture spec;`coding-assistant` preset 保持不开 MCP(golden 仍薄)。

生成产物侧(`mcp.enabled` 门控):

- `harness/mcp.py` — 薄 MCP 适配层(目标 100–150 行代码):
  - `McpServerConfig` / `McpConfig`(运行期 Pydantic,`extra="forbid"`):每条 `name` + 二选一形态——**stdio**(`command`/`args`/可选 `env`:要转发进子进程的 **env 变量名**列表)或**远程**(`url`/可选 `auth_env`:Bearer token 的 env 名 / 自定义 header env 映射)。绝不在 config 里存明文。
  - `McpManager` — 后台线程 + 专属 asyncio 事件循环:按 server 形态选 `stdio_client` / `streamablehttp_client` / `sse_client`,建 `ClientSession`、`initialize` + `list_tools`,经 `AsyncExitStack` 保持会话;对外只暴露**同步** `call(...)`(`run_coroutine_threadsafe` 桥接)。异步全部关在本模块内,外部接口同步,`loop.py`/`tools.py` 核心零改动。失败隔离:某 server 连不上 / `list_tools` 失败 → 记日志 + 跳过,不崩整个 harness。
  - `register_mcp_tools(registry, config, manager)` — 把发现的 MCP 工具包成 `tools.Tool`(`parameters` 取 `inputSchema`,`func` 调 `manager.call` 的同步闭包,`risk` 取注解默认 `high`),**只注册 allowlist 内的工具**;命名加 `{server}__{tool}` 前缀避免冲突。
- `interfaces/cli.py` — `run`/`serve` 启动路径在 `mcp.enabled` 时建 `McpManager` + `register_mcp_tools`(条件块)。
- `interfaces/web.py`(若 `interfaces.web` 也开)— `/config` 把 MCP tool allowlist 纳入运行期可编辑当场生效(复用既有 `tools[].enabled` 路径)。server 增删改 + 热重连归 Slice 11。
- `tests/test_mcp.py` + `tests/_mcp_dummy_server.py` — 本地 stdio mock server,经真实 stdio 子进程跑通 `list_tools` → `call_tool`,断言只有 allowlist 内的工具被注册、调用结果正确、风险标记生效;远程路径覆盖传输选择 + `auth_env` 注入 Authorization header。全程本地、无外网、无 key。
- `README.md` / `AGENTS.md` — 「接 MCP 工具」章节。

## 2. 实现要点

- **同步/异步桥**:`mcp` SDK 是 asyncio。`McpManager` 把事件循环 + 会话关进后台线程,对外只给同步 `call()`;工具就是普通 `Tool`,走既有 `registry.call` → 既有 trace 事件。**`loop.py` 不动**。
- **双传输按 config 形态选**:`command` → stdio;`url` → streamable-http(回退 sse)。共享 `ClientSession`/`list_tools`/`call_tool`/注册逻辑;依赖按 SDK 版本兼容(`hasattr` 探测改名)、pin 版本。
- **allowlist = 注册门槛**:`register_mcp_tools` 只对 allowlist 内工具建 `Tool` 并注册;未 allowlist 的不注册不暴露。支持 `<server>__*` 通配(启用该 server 现在及将来发现的全部工具),通配匹配在 `tools.in_allowlist` 实现,`register_mcp_tools` 与 `Registry.active_names` 共用(注册期 + offer 期两层门禁一致)。
- **命名 / 风险**:`{server}__{tool}` 前缀(满足 function-calling 名字符集);MCP 工具默认 `risk=high`(外部代码,保守),高风险默认不 allowlist。读类工具可经 `safe_tools` 标 `safe`(供只读范式),见 Slice 6。
- **依赖落位(关掉必须不含)**:沿用方案 A;`mcp.enabled=false` 时三处不含 `mcp`。
- **Windows / 代理 / 并发等运行期健壮性**:stdio 子进程在 Windows 的 `.cmd` shim 兼容、并发连接、首跑健壮性、镜像源/代理自动解析等运行期加固随后续在 Slice 11 一并完善,详见 [`12-slice-11-mcp-management.md`](./12-slice-11-mcp-management.md)。

## 3. 退出门禁

- MCP stdio 工具调用(本地 stdio mock server,真实子进程):`list_tools` + `call_tool` 跑通,结果正确。
- 远程传输路径覆盖:`url` server 选远程传输 + `auth_env` 注入 Bearer header(无外网)+ 传输二选一校验。
- 非 allowlist tool 不注册;风险标记生效(`risk=HIGH`,`enabled: false` 不注册)。
- 关 MCP 时薄验证:`mcp.enabled=false` 产物不含 `harness/mcp.py`/相关测试,`config.py` 无 mcp,`pyproject`/`uv.lock`/`requirements.txt` 不含 `mcp`。
- 开 MCP 时可跑:生成 → `uv lock` → `uv sync && pytest`(装上 `mcp` SDK)→ 冒烟自检。
- MCP allowlist 运行期可控(allowlist 决定是否注册/暴露;`/config` 编辑路径与内置工具同一套)。
- 黄金路径回归(关 MCP)golden/docker/uvx 全绿。
- `mcp.py` 体量符合「薄」;`ReadLints` clean。

## 4. 关键决策

- **① `HarnessSpec` 新增 `mcp.enabled`(`CLAUDE.md §6.1`,方案 A)**:只加 `mcp.enabled: bool = False`(server/tool/传输全运行期 `config.yaml`)。
- **② 远程 HTTP/SSE 传输纳入 MVP(改全局决策)**:原「仅 stdio」被取代;远程托管(HTTP/SSE Streamable)进本片,联网 MCP registry 仍 v1+。
- **软确认**:不加第二个生成期开关(stdio + 远程都由 `config.yaml` 形态运行期决定);同步/异步桥 = 后台线程 + 专属事件循环 + 持久会话 + 同步 `call()`;命名前缀 `{server}__{tool}`;MCP 工具默认 `risk=high`、默认不 allowlist;失败隔离;`/config` 的 MCP 范围只让 tool allowlist 运行期当场改(server 增删改 + 热重连排 Slice 11);catalog 挪 Slice 6。

## 5. 本 slice 注意

- **薄**:默认产物(不开 MCP)与 Slice 1/2/3 逐字一致——零新增依赖、零 MCP 文件、`config.py`/`config.yaml` 零 mcp 段。`mcp.py` 自身保持薄。
- **核心克制**:MCP 工具注册进既有 `registry`、走既有 `loop`/`trace`,不改 `loop.py`、不改 `tools.Registry` 核心;所有 MCP 特定逻辑收在 `mcp.py`。
- **不绑框架**:`mcp` 是协议 SDK,不是 agent 编排框架;仅在 `mcp.enabled` 时进产物。
- **密钥红线**(`CLAUDE.md §6.5`):stdio 的 `env` 与远程的 `auth_env`/header **只存 env 变量名**,真值经 `.env`/进程环境注入;绝不写进 spec/catalog/config.yaml/trace/日志。
- **配方 vs 活旋钮**(`00-overview.md` §3):MCP 能力有无 = 结构性(spec,重新生成);server/tool/传输 = 行为性(运行期)。
