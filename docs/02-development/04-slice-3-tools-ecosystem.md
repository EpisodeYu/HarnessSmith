# 02·04 - Slice 3:工具生态

> 目标:接入 MCP 工具(本地 stdio)与生成期可视化向导,补齐"配置即生成"差异化的 GUI 一环。均为 `01-project-plan.md` 的 **L2**。
>
> 前置:Slice 2 门禁全绿。

## 1. 交付物

- `harnessforge/catalog/mcp_servers.yaml` — 精选**静态** MCP server 目录(如 github / filesystem / fetch),标注来源与更新日期。
- 产物 `harness/tools.py` 升级 — MCP client(**仅 stdio 本地传输**)+ allowlist 控制启用哪些 tool + 风险标记沿用 Slice 1。
- `harnessforge/wizard/` — FastAPI + 单页静态前端(vanilla JS + Tailwind CDN,**无构建步骤**),分区表单产出合法 `spec.yaml`。
- `harnessforge/cli.py` 增 `wizard` 子命令(或 `new --interactive` 拉起向导)。
- MCP 与 wizard 的 spec 字段开关 + 渲染分支。

## 2. 任务拆解

### 2.1 MCP stdio 接入
- 用官方 MCP Python SDK,仅 stdio 传输(HTTP/SSE 远程推迟到 L3)。
- allowlist:spec 里声明启用哪些 tool;未在 allowlist 的不注册。
- `mcp` 依赖进 `optional-dependencies`,仅启用 MCP 时安装。

### 2.2 静态 catalog
- 离线、确定、可审查的 server 列表;标来源 + 更新日期(版本漂移可控)。
- 安全:工具元数据会被 agent 当指令,优先选 vendor 维护的 server。

### 2.3 生成期 wizard
- 单页表单,字段**对齐 `HarnessSpec`**;产出的 spec 必须能直接喂给 `generator`。
- 无构建:Tailwind CDN + 原生 JS,后端 FastAPI 提供表单页 + 提交端点。

## 3. 退出门禁(对应 `01 §8` Non-blocker)

- [ ] MCP stdio:从 catalog 选 / 手动加一个 server,allowlist 放行的 tool 能被循环调用(可用本地 stdio mock server 测试)。
- [ ] 未在 allowlist 的 tool 不被注册(单测)。
- [ ] wizard 表单提交产出的 spec 校验通过,并能 `generator` 生成项目。
- [ ] 关掉 MCP 开关时,生成的 `pyproject.toml` 不含 `mcp`(薄验证)。
- [ ] `ReadLints` clean。

## 4. 必须人审的决策点

- catalog 收录哪些 MCP server(安全审:优先 vendor 维护、收紧权限)。
- wizard 字段集是否齐、是否对外可读。

## 5. 本 slice 注意

- **仅 stdio**:HTTP/SSE 远程是 L3,本片不做(`00-overview §3`);若有人要求加,属跨 slice 范围调整,走 `CLAUDE.md §6.6` 人审。
- **安全**:MCP 工具默认遵循 Slice 1 的风险标记 + allowlist;高风险默认关。
- 静态 catalog 的来源 / 日期标注是版本漂移对策(`01 §9` 风险),别省。
