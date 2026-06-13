# 02·07 - Slice 6:工具基线 + 标准 SKILL

> 目标:让生成产物**真正能干活**,两件:① **工具基线(MCP 预设)**——产物默认只有 time/calculator 玩具工具,故基线能力**全由 MCP 预设提供、不自写 built-in**:`fetch` / `ddg-search`(免 key 联网搜索)/ `git` / Desktop Commander 经 catalog 预填;`catalog/mcp_servers.yaml` 供 wizard/CLI 预填 `config.yaml` 并指向 marketplace 快捷扩展;离线靠**生成期预热 + Docker 烤镜像**。② **标准 SKILL**——支持 **Agent Skills 开放标准**(`SKILL.md`,Claude/Cursor/Codex 等 25+ 工具通用),渐进披露三级。
>
> 前置:Slice 4(MCP opt-in)+ Slice 5(范式)。
>
> SKILL 放本片因**技能依赖工具**(读 `SKILL.md` 正文、跑脚本都靠文件/shell 工具)。

## 0. 边界与口径

- **基线能力来自 MCP,不自写 built-in**:产物默认只有 time/calculator → agent 无法发挥。基线能力**全由 MCP server 提供**(直接吃成熟生态),免造轮子 + 维护。
- **生成期 vs 运行期(守 Slice 4)**:`spec.mcp.enabled` 是唯一生成期开关;连哪些 server / 用哪些 tool / 传输全运行期 `config.yaml`。catalog 选中的 server 落产物 `config.yaml mcp.servers`(运行期文件),不进 spec/快照;`env`/`auth_env` 仅 env 变量名。
- **catalog 非安全闸**:便捷数据源 + 基线来源,非编译进产物;真正安全闸 = 运行期 tool allowlist + 风险标记 + 密钥按 env 名。
- **预填 allowlist = 每 server 一条 `<server>__*` 通配,默认全开**:即所有预填 server 的全部工具(含写/shell)默认启用,通配匹配在 `tools.in_allowlist` 实现。**风险分级仍生效**:`safe_tools` 内的读类(status/log/diff/show、fetch、ddg-search 等)标 `risk=safe`(只读范式 plan/ask 可用),其余 `risk=high`(仅 agent)。收窄方式:把通配换成显式 `<server>__<tool>` 行,或在 web Tools 面板逐个勾。
- **SKILL 依赖工具**:`SKILL.md` 正文与脚本要靠文件读 / shell 工具(MCP 基线的 Desktop Commander/filesystem 提供);SKILL 脚本 = 高风险默认关。
- **离线/首跑联网**:`uvx`/`npx` server 首跑需联网拉包(之后缓存可 `--offline`)。缓解:生成期预热缓存 + Docker build 烤进镜像;优先 uvx 系(uv 已是硬依赖,免 Node);默认开项选「本就需联网」的 fetch/ddg-search。

## 1. 交付物

生成器侧:

- `harnessmith/catalog/mcp_servers.yaml`(Slice 4 挪来)— 静态精选 MCP server 清单,含基线 server `fetch`(`uvx mcp-server-fetch`)、`ddg-search`(`uvx duckduckgo-mcp-server`,免 key)、`git`(`uvx mcp-server-git`)、Desktop Commander(`npx @wonderwhy-er/desktop-commander`)+ 各项 `name`/`description`/传输形态/所需 env 变量名/`safe_tools`/风险/来源。git 条目**不带 `--repository` 钉死**(各 git 工具的 `repo_path` 是必填参数,钉死会让 server 在非 git 目录直接退出而误标红;去掉后 server 在任意 cwd 都健康,调用到非仓库路径只是该次 `isError`)。
- `harnessmith/generator.py` — `mcp.enabled` 时把基线/选中 server 合并进产物 `config.yaml mcp.servers`;生成期预热缓存(`uvx <server> --help` 拉进 uv 缓存,可 `--no-prewarm` 跳过)。
- `harnessmith/templates/Dockerfile.j2` — `mcp.enabled` 时 build 阶段预热把 server 烤进镜像 + `ENV UV_OFFLINE=1` → 容器开箱即用、运行期离线。
- `harnessmith/cli.py` — `new --mcp-server <name>`(从 catalog 预填)。
- preset 调整:`coding-assistant` 升级为 MCP 基线;另保留一个极薄 example(不开 MCP)供 thin/golden 断言。

生成产物侧(SKILL 由 `spec.skills.enabled` 门控):

- `src/<pkg>/harness/skills.py`(`skills.enabled` 时生成,≈ 60–130 行)— 标准 Agent Skills 支持:
  - **L1 发现/注入**:扫描技能目录(默认 `skills/`,可配 `.claude/skills`/`.cursor/skills`/`.agents/skills`)下 `*/SKILL.md`,用已有 `pyyaml` 解析 frontmatter(`name`/`description`,可选 `disable-model-invocation`/`paths`),把 `name + description (+ 路径)` 注入系统提示。
  - **L2 加载正文**:标准即「模型用文件工具读 `SKILL.md`」(MCP 基线已提供文件读);为不依赖 MCP,提供极薄内置 `read_skill(name)` 工具(读该技能 `SKILL.md` 正文,低风险)。
  - **L3 脚本/资源**:模型用 shell/文件工具按需跑 `scripts/`、读 `references/`/`assets/`(无 harness 代码;脚本 = 高风险默认关)。
- `src/<pkg>/harness/prompts.py` — `skills.enabled` 时把可用技能 L1 元数据拼进系统提示(渐进披露,~100 token/技能)。
- `src/<pkg>/interfaces/cli.py` / `web.py` — 可选 `/skill-name` 手动触发(honor `disable-model-invocation`)。
- `spec.py` — 新增 `skills` 开关(最小:`skills.enabled: bool = False`)。
- `tests/` + `README.md` / `AGENTS.md`。

## 2. 任务拆解

- **MCP 基线预设**:preset `config.yaml` 预填 fetch/ddg-search/git/Desktop Commander,allowlist 用 `<server>__*` 通配默认全开;`safe_tools` 标读类。无启用工具的 server 保持休眠(不启进程)。
- **catalog(静态精选 + 基线来源)**:含基线四项 + 候选(官方 `time`/`memory`/`sequential-thinking`,归档 `github` 需 token、`postgres` 需连接串)。每条标传输形态、env 名、`safe_tools`、风险、来源。
- **离线缓解**:生成期 `uvx <server> --help` 预热(可跳过)+ Docker build 烤镜像;优先 uvx 系(免 Node),Desktop Commander 为 Node 系(文档注明)。
- **marketplace 快捷扩展(非预置,守红线)**:文档/AGENTS 指向 Smithery/Glama/MCP.so/官方 Registry,其 JSON 配置粘进 `config.yaml mcp.servers` 即用;SaaS 集成走 Composio 等 remote MCP（`url`+`auth_env`），不引框架包。
- **环境感知注入**:预置但禁用的 server(名 + description + 如何在 `config.yaml` 开)+ `platform.system()` + shell 提示由系统提示主动暴露,让用户/agent 不会「没注意到开关」、并在 Windows 写 PowerShell/cmd 而非 bash。仅 `spec.mcp.enabled` 且 servers 非空时注入,薄。
- **标准 SKILL L1/L2/L3** + `spec.skills.enabled` 门控(关掉零痕迹)。

## 3. 退出门禁

- 基线开箱可用:`coding-assistant` 生成 → 预填 server 工具按通配 allowlist 开、mock 可调;读类工具供只读范式;`uv sync && pytest` 绿。
- 离线/Docker:生成期预热后产物可离线用已缓存 server;Docker build 暖缓存 + `UV_OFFLINE=1`,`docker run --network none` 离线跑通 mock 一步。
- catalog 落 `config.yaml`:选中 server → 产物 `config.yaml mcp.servers` 含条目(env/auth 仅名、`safe_tools` 标读类),不进 spec/快照。
- 极薄 example 仍薄:`examples/spec.yaml`(无 MCP)不含 `mcp` 依赖、与 Slice 4 薄基线一致。
- SKILL 发现 + 注入:样例 skill → L1 `name+description` 进系统提示;`disable-model-invocation` 的只 `/name` 触发。
- SKILL 加载并遵循(mock):模型 `read_skill(name)` 读正文 → 按指令完成一步;`read_skill` 低风险且经 allowlist 门控。
- SKILL 关掉零痕迹:`skills.enabled=false` 产物无 `skills.py`/`read_skill`/提示注入/样例。
- `ReadLints` clean;大改动回归(全量黄金 + Docker + `uvx` 冒烟)。

## 4. 关键决策

- **① MCP 预设做基线(不自写 built-in)**:基线能力全由 MCP 提供;离线靠生成期预热 + Docker 烤镜像;海量扩展走 marketplace 文档 + Composio 式 remote MCP。
- **② 官方 `git` 预置**:`uvx mcp-server-git` 进基线;catalog 不钉死 `--repository`(理由见 §0)。
- **③ 标准 SKILL 支持放本片**(与工具基线一起)。
- **④ `spec.skills` 字段**:只加结构性开关 `skills.enabled: bool = False`(对齐 `mcp.enabled`);技能目录是运行期行为旋钮(`config.yaml skills.dirs`,默认 `["skills"]`),不进 spec。
- **⑤ MCP 工具风险分级**:不再「一律 HIGH」,改按工具风险标注(catalog 标 fetch/ddg-search/git/desktop-commander 读类为 `safe`、写/shell/config-mutating 类为 `high`;`McpServerConfig.safe_tools` 字段,`register_mcp_tools` 据此设 `risk`)。只读范式 plan/ask 也能用读类;未列入 `safe_tools` 的发现工具一律 `high`(fail-safe)。**DC 读类必须标 safe**——否则装了 Desktop Commander 作基线能力的产物在 plan/ask 下完全没有文件读取能力(读文件/列目录/搜代码全被挡)。
- **⑥ 推进方式 = split**:先做 Part A(工具基线 + catalog + 离线/Docker + 风险分级),再做 Part B(标准 SKILL)。
- **⑦ 联网搜索进基线**:`ddg-search`(免 key)进 catalog 并默认开,给 agent 真正的「搜→读」。
- **⑧ shell/写默认关如何不「静默失能」**:shell/写仍默认关(DC 一键开、需 Node),但系统提示注入「环境感知」暴露预置但禁用的能力 + 如何开。
- **⑨ Windows**:同一处环境感知注入 `platform.system()` + shell 提示;README/AGENTS 补 Windows 注意(优先 Docker/Linux;`fetch` 原生 Windows 需 `PYTHONIOENCODING=utf-8`)。

## 5. 本 slice 注意

- **能力来自 MCP(非 built-in)**:`coding-assistant` 因此带 `mcp` 依赖(不再极薄),另留无 MCP 的极薄 example 守 thin/golden。
- **红线**:不做联网 MCP registry/`forge add`(v1+);Composio 等只作 remote MCP、不引框架包;SKILL 是提示注入 + 文件读 + 工具跑脚本,不引框架。
- **密钥红线**(`CLAUDE.md §6.5`):catalog / `config.yaml` / SKILL frontmatter 只存 env 变量名。
- **离线**:首跑联网拉 server 包属固有代价;生成期预热 + Docker 烤镜像把它前移;优先 uvx 系。
- **SKILL 薄**:`skills.py` 控制在 ≈ 60–130 行;超薄停问人(`CLAUDE.md §6.8`)。
