# 02·07 - Slice 6:工具基线 + 标准 SKILL(MCP 预设让 agent 开箱可用 + Agent Skills 支持)

> 目标:让生成产物**真正能干活**,两件:① **工具基线(MCP 预设)**——产物默认只有 time/calculator 玩具工具,故基线能力**全由 MCP 预设提供、不自写 built-in**:`fetch` 默认开、`git` 读类默认开/写类默认关、Desktop Commander 预填一键开;`harnessforge/catalog/mcp_servers.yaml` 供 wizard/CLI 预填 `config.yaml` 并指向 marketplace 快捷扩展;离线靠**生成期预热 + Docker 烤镜像**。② **标准 SKILL**——支持 **Agent Skills 开放标准**(`SKILL.md`,Claude/Cursor/Codex 等 25+ 工具通用),渐进披露三级,让产物直接讲可移植的 Skills。属 `01-project-plan.md` 的 **L2/L3(人已定向)**。
>
> **本片由 2026-06-05 重切而来**:原 Slice 5 过大,拆为 Slice 5(范式)/ Slice 6(本片:工具基线 + SKILL)/ Slice 7(wizard)。SKILL 放本片因**技能依赖工具**(读 `SKILL.md` 正文、跑脚本都靠文件/shell 工具)。
>
> 前置:Slice 4(MCP opt-in,已 ✅)+ Slice 5(范式,见 `06-slice-5-paradigms.md`)。
>
> **状态:🚧 进行中。Part A(MCP 工具基线)✅ 已完成(2026-06-05);Part B(标准 SKILL)📝 待开工**。方向 + 决策①–⑥经人 2026-06-05 定稿(MCP 预设做基线 / 不自写 built-in / fetch 默认开 / git 预置 / DC 预填默认关 / 生成期预热 + Docker 烤镜像 / 风险按工具分级 B / `spec.skills` 仅 enabled、dirs 走运行期 B / split 推进,见 §4)。门禁见 §3(Part A 项已勾)。
>
> **红线提醒**:① 能力来自成熟 MCP 生态,**不自写 built-in**(免造轮子+维护);**不做联网 MCP registry / `forge add`**(v1+);marketplace 只走"文档 + 粘贴式 config";SaaS 平台(Composio 等)只作 **remote MCP**(`url`+`auth_env`,落 Slice 4 已支持的远程传输),**不引其框架包**。② SKILL = 提示注入 + 文件读 + 用工具跑脚本,**不引框架**;高风险(脚本/写/shell)默认关(`01 §6`)。

## 0. 边界与口径(开工前先对齐)

- **基线能力来自 MCP,不自写 built-in(人 2026-06-05 定稿)**:产物默认只有 time/calculator → agent 无法发挥。基线能力**全由 MCP server 提供**(直接吃成熟生态):`fetch` 默认开、`git` 读默认开、Desktop Commander 预填默认关(一键开)。
- **生成期 vs 运行期(守 Slice 4 签字)**:`spec.mcp.enabled` 是唯一生成期开关(决定带不带 MCP 能力 + `mcp` 依赖);**连哪些 server / 用哪些 tool / 传输全运行期 `config.yaml`**(`05-slice-4 §4①`)。catalog 选中的 server **落产物 `config.yaml mcp.servers`(运行期文件),不进 spec/快照**;`env`/`auth_env` 仅 env 变量名。
- **catalog 非安全闸**(沿用 `05-slice-4 §0/§5`):便捷数据源 + 基线来源,非编译进产物;**真正安全闸 = 运行期 tool allowlist + 风险标记(高风险默认关)+ 密钥按 env 名**。
- **SKILL 依赖工具**:`SKILL.md` 正文与脚本要靠**文件读 / shell 工具**(本片 MCP 基线的 Desktop Commander/filesystem 提供)→ SKILL 与工具基线同片最顺。SKILL 的脚本=高风险,默认关,守红线。
- **离线/首跑联网(人选 prewarm_and_docker)**:`uvx`/`npx` server 首跑需联网拉包(之后缓存可 `--offline`),纯离线从零=无该 server 工具。缓解:生成期预热缓存 + Docker build 烤进镜像;优先 uvx 系(uv 已是硬依赖,免 Node);默认开项选"本就需联网"的 `fetch`。

## 1. 交付物

生成器侧(`harnessforge/`):

- `harnessforge/catalog/mcp_servers.yaml`(Slice 4 挪来)— 静态精选 MCP server 清单,含**基线 server** `fetch`(`uvx mcp-server-fetch`)、`git`(`uvx mcp-server-git`)、Desktop Commander(`npx @wonderwhy-er/desktop-commander`)+ 各项 `name`/`description`/传输形态/所需 **env 变量名**/风险/来源+日期。
- `harnessforge/generator.py` — `mcp.enabled` 时把基线/选中 server 合并进产物 `config.yaml mcp.servers`;**生成期预热缓存**(`uvx <server> --help` 拉进 `~/.cache/uv`,可 `--no-verify`/`--no-prewarm` 跳过)。
- `harnessforge/templates/Dockerfile.j2` — `mcp.enabled` 时 build 阶段预热/`uv tool install` 把 server 烤进镜像 → 容器开箱即用、运行期离线。
- `harnessforge/cli.py` — `new --mcp-server <name>`(从 catalog 预填)。
- preset 调整:`coding-assistant` 升级为 **MCP 基线**(`mcp.enabled: true` + fetch 开 + git 读开/写关 + Desktop Commander 预填关);**另保留一个极薄 example**(不开 MCP)供 thin/golden 断言。

生成产物侧(`harnessforge/templates/`,SKILL 由 `spec.skills.enabled` 门控):

- `src/<pkg>/harness/skills.py`(`skills.enabled` 时生成,目标 ≈ 60–120 行)— 标准 Agent Skills 支持:
  - **L1 发现/注入**:扫描技能目录(默认 `skills/`,可配 `.claude/skills/`、`.cursor/skills/`、`.agents/skills/`)下 `*/SKILL.md`,用已有 `pyyaml` 解析 frontmatter(`name`/`description`,可选 `disable-model-invocation`/`paths`/`allowed-tools`),把 `name + description (+ 路径)` 注入系统提示(经 `prompts.py`)。
  - **L2 加载正文**:标准即"模型用文件工具读 `SKILL.md`"——本片 MCP 基线已提供文件读 → 可零额外代码;为不依赖 MCP,提供极薄内置 `read_skill(name)` 工具(读该技能 `SKILL.md` 正文,低风险)。
  - **L3 脚本/资源**:模型用 shell/文件工具(Desktop Commander)按需跑 `scripts/`、读 `references/`/`assets/` → 无 harness 代码;脚本=高风险默认关。
- `src/<pkg>/harness/prompts.py` — `skills.enabled` 时把可用技能 L1 元数据拼进系统提示(渐进披露,~100 token/技能)。
- `src/<pkg>/interfaces/cli.py` / `web.py` — 可选 `/skill-name` 手动触发(honor `disable-model-invocation`)。
- `spec.py` — 新增 `skills` 开关(最小:`skills.enabled: bool = False`,可选 `dirs`)。**改 schema → `CLAUDE.md §6.1`**(§4③ 已定向,字段 implement 前定稿)。
- `tests/` — MCP 基线:`fetch`/`git` 默认 allowlist、DC 预填默认关;SKILL:放一个样例 skill,mock 模型"读 `SKILL.md` → 遵循"跑通,断言 L1 注入 + L2 读取 + 非 allowlist 不暴露。
- `README.md` / `AGENTS.md` — 增"接 MCP 工具/基线"、"离线/Docker"、"加一个 Skill(放 `skills/<name>/SKILL.md`)"、marketplace 扩展说明。

## 2. 任务拆解

### 2.1 MCP 基线预设(fetch / git / Desktop Commander)
- preset `config.yaml` 预填三者;allowlist:`fetch` 工具 `enabled: true`(低风险);`git` 读类(status/log/diff/show)`true`、写类(commit/push)`false`;Desktop Commander 全部 `false`(一键开)。
- **风险标记注意**:现状 `register_mcp_tools` 把 MCP 工具一律标 `risk=HIGH`;"低风险默认开 fetch/git 读"靠 preset 显式 allowlist,或加按 server/tool 的风险分级(留实现细化,见 §4 软确认)。

### 2.2 catalog(静态精选 + 基线来源)
- 含基线三项 + 候选(官方 `time`/`memory`/`sequential-thinking`/`everything`;归档常用 `github` 需 `GITHUB_PERSONAL_ACCESS_TOKEN`、`postgres` 需连接串)。每条标传输形态、env 名、风险、来源+日期(`01 §10` pin 版本)。
- 除基线三项外是否再预置更多,可后续按需增补,不阻塞本片。

### 2.3 离线缓解:生成期预热 + Docker 烤镜像
- 生成期 `generate()` 顺带 `uvx <server> --help` 预热(生成本就需网);可跳过。
- `Dockerfile.j2` build 阶段预热/`uv tool install` 把 server 烤进镜像。
- 优先 uvx 系(免 Node);Desktop Commander 为 Node 系,开它需 Node(文档注明)。

### 2.4 marketplace 快捷扩展(非预置,守红线)
- 文档/AGENTS 指向 Smithery/Glama/MCP.so/官方 Registry/ModelScope(中文),其 JSON 配置粘进 `config.yaml mcp.servers` 即用(与我们格式同构)。
- SaaS 集成走 **Composio 等 remote MCP**(`url`+`auth_env`,Slice 4 远程传输),**不引框架包**。`forge add`/联网 registry 留 v1+。

### 2.5 标准 SKILL — L1 发现 + 注入
- `skills.py` 扫描技能目录解析 frontmatter,把 `name+description(+路径)` 注入系统提示(经 `prompts.py`)。honor `disable-model-invocation`(仅手动 `/name`)与 `paths`(按文件范围才浮现,可选)。

### 2.6 标准 SKILL — L2 加载正文
- 优先复用文件读工具(MCP 基线);另给极薄内置 `read_skill(name)`(低风险)使无 MCP 时也能读正文。模型按 description 自选或 `/skill-name` 手动触发后载入正文。

### 2.7 标准 SKILL — L3 脚本/资源 + spec 开关
- `scripts/`/`references/`/`assets/` 由模型经 shell/文件工具按需用(无 harness 代码;脚本=高风险默认关)。
- `spec.skills.enabled` 门控 `skills.py`/`read_skill`/提示注入;关掉零痕迹。`allowed-tools` frontmatter(实验性)MVP 可先忽略或映射到 allowlist。

## 3. 退出门禁(对应 `01 §8` Non-blocker,做到即验;实现后回填)

> **Part A(工具基线)状态:✅ 已完成(2026-06-05)**。生成器快测 68(新增 catalog/prefill/preset/Dockerfile bake 用例);coding-assistant 产物自带测试 25(含 MCP 风险分级 `safe`/`high` + 只读范式可用 `fetch`/`git` 读);golden 非 docker 7 全绿(thin example / MCP 基线 prefill 真实启动 fetch+git / web / 多范式 / `uvx` 冒烟);docker golden 2 全绿(基线 `docker build` + `docker run --network none` 离线跑通 mock 一步)。Part B(SKILL)未开工。

- [x] **基线开箱可用**:`coding-assistant` 生成 → `fetch`/`git` 读类默认 allowlist 开、mock 可调;Desktop Commander 预填但 allowlist 默认关(全 high、未被 offer,且因无启用工具**不被启动**);`uv sync && pytest`(含 `test_mcp.py`)绿。
- [x] **离线/Docker**:生成期 `prewarm_mcp_servers`(`uvx <pkg> --help` 暖 uv 缓存,可 `--no-prewarm`)后产物可离线用已缓存 server;Docker build 暖缓存 + `ENV UV_OFFLINE=1`,`docker run --network none` 离线跑通 mock 一步(已 golden 验证)。
- [x] **catalog 落 `config.yaml`**:选中 server → 产物 `config.yaml mcp.servers` 含条目(env/auth 仅名、写类默认关、`safe_tools` 标读类),**不进 spec/快照**(`test_mcp_prefill_servers_do_not_leak_into_spec_snapshot`)。
- [x] **极薄 example 仍薄**:`examples/spec.yaml`(无 MCP)→ 不含 `mcp` 依赖、与 Slice 4 薄基线一致(`test_golden_thin_example_stays_thin_and_smoke_passes`)。
- [ ] **SKILL 发现 + 注入**(Part B):放样例 skill → L1 `name+description` 进系统提示;`disable-model-invocation` 的不自动注入正文(只 `/name` 触发)。
- [ ] **SKILL 加载并遵循(mock)**(Part B):模型读 `SKILL.md` 正文(经文件工具或 `read_skill`)→ 按其指令完成一步;非 allowlist 工具不被技能调用。
- [ ] **SKILL 关掉零痕迹**(Part B):`skills.enabled=false` 产物无 `skills.py`/`read_skill`/提示注入。
- [x] `ReadLints` clean(Part A)。
- [x] (大改动 §5)全量黄金 + Docker + `uvx` 冒烟全绿(动 `Dockerfile`/`generator`/`catalog`/presets;`spec` 未动,Part A 无 schema 变更)。

## 4. 必须人审的决策点

- [x] **① MCP 预设做基线(不自写 built-in)——人 2026-06-05 定稿**:`fetch` 默认开 + Desktop Commander 预填默认关;离线靠生成期预热 + Docker 烤镜像;海量扩展走 marketplace 文档 + Composio 式 remote MCP。
- [x] **② 官方 `git` 预置——人 2026-06-05**:`uvx mcp-server-git` 进基线;读类默认开、写类(commit/push)默认关。
- [x] **③ 标准 SKILL 支持放本片(与工具基线一起)——人 2026-06-05**:Agent Skills 开放标准(`SKILL.md` + 渐进披露),`skills.py` 发现+注入 + `read_skill`/文件工具读正文 + 脚本经工具跑;`spec.skills.enabled` 门控。
- [x] **④ `spec.skills` 字段最终签字(`CLAUDE.md §6.1`)——人 2026-06-05 选 B**:spec **只加结构性开关 `skills.enabled: bool = False`**(对齐 `mcp.enabled` 先例);**技能目录是运行期行为旋钮**,落 `config.yaml skills.dirs`(默认 `["skills"]`,可加 `.claude/skills`/`.cursor/skills`/`.agents/skills`),**不进 spec**。
- [x] **⑤ MCP 工具风险分级——人 2026-06-05 选 B**:不再"一律 HIGH",改**按工具风险标注**——catalog 标 `fetch` 与 `git` 读类(status/log/diff/show…)为 `safe`、写类(commit/add/push…)为 `high`;`McpServerConfig` 增 `safe_tools` 字段,`register_mcp_tools` 据此设 `risk`。这样**只读范式 plan/ask(`allow_high_risk=False`)也能用 fetch/git 读**,"低风险默认开"有据。未列入 `safe_tools` 的发现工具一律按 `high`(fail-safe)。
- [x] **⑥ 推进方式——人 2026-06-05 选 split**:**先做 Part A(MCP 工具基线 + catalog + 离线/Docker + 风险分级)**跑绿 §3 相关门禁并 commit,**再做 Part B(标准 SKILL)**单独跑绿门禁 commit。
- **软确认(已自主定,`CLAUDE.md §5.3`)**:基线 allowlist = fetch 开 / git 读开写关 / DC 全关(预填一键开);catalog 除基线三项外按需收候选(官方 `time`/`memory`/`sequential-thinking`/`everything`,归档 `github`/`postgres`),不阻塞本片;`read_skill` 内置工具=低风险默认可读(只读技能目录内 `SKILL.md`);SKILL 注入点在 `prompts.build_system_prompt`(所有范式共用)。

## 5. 本 slice 注意

- **能力来自 MCP(非 built-in)**:不自写工具(免造轮子+维护);`fetch`/`git` 读默认开、Desktop Commander/写/shell 默认关(守 `01 §6`)。`coding-assistant` 因此带 `mcp` 依赖(不再极薄),另留无 MCP 的极薄 example 守 thin/golden。
- **红线**:不做联网 MCP registry/`forge add`(v1+);Composio 等只作 remote MCP、不引框架包;SKILL 是提示注入+文件读+工具跑脚本,不引框架。
- **密钥红线**(`CLAUDE.md §6.5`):catalog / `config.yaml` / SKILL frontmatter 只存 env 变量名,不写真值。
- **离线**:首跑联网拉 server 包属固有代价;生成期预热 + Docker 烤镜像把它前移到生成期;优先 uvx 系(免 Node),Desktop Commander 需 Node(文档注明)。
- **SKILL 薄**:`skills.py` 控制在 ≈ 60–120 行(发现+解析+注入);超薄停问人(`CLAUDE.md §6.8`)。
- **大改动回归**(`CLAUDE.md §5.2`):动 `Dockerfile`/`generator`/`spec`/presets,完成前全量黄金 + Docker + `uvx` 冒烟。
