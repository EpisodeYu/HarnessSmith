# HarnessForge 立项方案 (MVP)

> 配套背景见 [00-research-and-feasibility.md](./00-research-and-feasibility.md)。
>
> 本版相对初稿做了三件事:**收敛 MVP 到一条端到端黄金路径**、**路线图改为垂直切片**、**明确关键技术决策**。RAG / Web 配置热重载 / HTTP-SSE MCP / keyring 等降级为 MVP 后续增强(本地自用阶段不需要)。

## 1. 定位与差异化

一句话:**create-next-app for agent harnesses —— 无 agent 框架锁定 + own-your-code。**

调研结论(2026):harness = `Agent = Model + Harness` 里除模型外的一切(编排循环/上下文工程/工具执行/沙箱/记忆/护栏/可观测)。术语在 2026 年才标准化,趋势是"模型越强、harness 越薄"。

竞品空位:`create-agent-app` 绑 LangGraph、`create-google-adk-agent` 绑 ADK、`full-stack-ai-agent-template` 多框架且静态模板;无代码平台托管且隐藏 harness。**没有"无 agent 框架锁定 + 可视化配置 + 生成你拥有的薄 harness 代码"的对位项目。** 三个必须打透的差异点:
- **无 agent 框架锁定(不是"无依赖")**:生成代码零 LangChain/LangGraph/ADK 等 **agent 编排框架**依赖,循环是你自己的。底座只用通用库(openai SDK / pydantic / typer 等),这些不是 agent 框架,不构成锁定。
- **own-your-code(eject 即所得)**:产出独立仓库,可读可删改;**生成后不再依赖 HarnessForge**。
- **配置即生成**:CLI/向导采集 spec → 一键渲染。

> 措辞修正:初稿用 "framework-free" 容易被质疑"那 FastAPI/Pydantic 算不算框架"。真实主张是**不绑定 agent 编排框架**,故全文统一表述为"无 agent 框架锁定"。

## 2. 目标用户与成功指标

**目标用户(MVP 阶段)**:先服务**作者本人 / 独立开发者**——想从零拥有一份可读可改、不绑框架的 agent harness,本地自用为主。这一画像直接决定 MVP 取舍:**不需要** Web 配置面板、多人协作密钥管理、生产级权限;**需要**一条"几分钟生成 → 跑通 → 易改"的路径。AI infra / 内部工具团队是 v1 之后再考虑的扩展人群。

**成功指标(以"时间到价值 + 代码可拥有"衡量,而非"功能写完")**:
- `harnessforge new --preset coding-assistant` 后 **5 分钟内**:生成项目 → 配好一个 key → mock/真实跑通一次带工具调用的对话。
- 生成产物核心代码(`harness/` 目录)保持**精简可通读**(目标量级:核心循环 150–300 行,整体远小于一个框架)。
- 使用者能在 **30 分钟内新增一个自定义 tool 并跑通**(加函数 + 注册,不动循环)。
- 生成项目 `uv sync && pytest` 全绿;`pyproject.toml` 不含 langchain/langgraph/adk。

## 3. MVP 范围(分层)

把范围分三层。**MVP 完成 = L1 全做 + L2 尽量做**;L3 推迟到 v1+。

### L1 — 黄金路径(必做,决定立项能不能成立)
- **spec**:`HarnessSpec` Pydantic 模型 + YAML(带 `version`)。
- **generator**:Jinja2 加载 spec → 渲染 → 写出独立仓库 + 拷入 `harness.spec.yaml` + `git init`;重跑警告不覆盖。
- **薄模板核心(无 agent 框架)**:config / llm / loop / tools / prompts / trace。
- **原生 function-calling 循环**:用 API 的 `tool_calls`(TAO/ReAct 语义),含停止条件/最大步数/错误处理;**走 Chat Completions API**(见 §6)。
- **工具注册表**:装饰器注册,新增 tool = 加函数 + 注册,不改循环;含 1–2 个内置安全示例工具。
- **CLI(Typer)**:`run` 一问一答。
- **JSONL trace + token/成本计数**。
- **基础预算停止**:步数(轮次)/时间/**token**/成本超限即停(4 维,任意组合,命中第一个即停)。预算与按 token 计的单价均为**运行期可配**(`config.yaml`),"按费用"需配对应 LLM 的输入/输出单价。
- **mock LLM 测试** + README + AGENTS.md(扩展指南)+ LICENSE(MIT) + .env.example。
- **可运行性保障(详见 §7)**:uv 契约(随仓库带 `uv.lock` + `.python-version`,uv 自动下载匹配 Python + 隔离 venv)+ **默认生成 `Dockerfile`/`.devcontainer`**(前期即纳入)+ `requirements.txt` pip 兜底 + 生成器对新仓库**冒烟自检**。
- **1 个 preset**(coding-assistant)+ 空白示例 spec。

### L2 — MVP 后半段(适合做,锦上添花)
- **MCP 工具**:仅 **stdio(本地)** 传输 + 精选静态 catalog + allowlist。
- **第 2 个 preset**(rag-research 骨架,RAG 实现可桩)。
- **极简 Web chat**:FastAPI + SSE 流式聊天页(不含 `/config` 面板)。
- **多 LLM profile + 角色路由**:命名 profile + `generation`/`compaction`/`embedding` 角色,`client_for(role)` 解析。
- **上下文管理**:`max_context_tokens` + **truncate 或 summarize 二选一**(先做 truncate,summarize 用 compaction profile)。
- **生成期 Web wizard**:单页表单产出 spec(L1 先用 CLI + preset 顶替,这里再补 GUI)。

### L3 — 推迟到 v1+(明确不在 MVP)
- Web `/config` 运行期热重载面板、密钥只写不回显面板、HTTP/SSE 远程 MCP、完整 HITL Web 交互时序、RAG 最小 ingest 闭环 + sqlite-vec、keyring 密钥后端、context offload(大输出落盘)。
- **单 agent 多范式**(候选):仅以"生成期 spec 开关 → 渲染不同 `loop.py` 模板"实现(plan-execute、reflection 等),不引入运行期编排/范式抽象层(那是被禁的"框架抽象层")。
- 原 v2 项:沙箱、多 agent 范式、tracing UI、跨会话记忆、评测 harness、联网 MCP registry、`forge add/regenerate`。**multi-agent 维持"明确不做"(见 §6)**;纳入需定位级变更 + 人审。

> 说明:RAG / MCP 双传输 / Web 配置这些是竞品已有的"通用能力",做得再好也证明不了差异化;先用 L1 证明"无框架 + own-your-code"跑得通,再纵向叠。

## 4. 设计原则:薄优先 + 可扩展 + 生成器/产物分离

**生成器能力 ≠ 默认产物模板**(化解"薄 harness"与"功能多"的张力):
- 默认产物模板保持**极薄**;RAG / MCP / context 高级策略 / Web 等通过 **spec 开关**按需生成,不塞进默认产物。
- 用户拿到的就是"够用且能通读"的最小 harness,高级件想要才有。

**可扩展(核心卖点,与无框架同级)**:
- 薄抽象、清晰模块边界:loop / llm / tools / context 各单一职责,可独立替换。
- 工具用注册表(装饰器)注册;新增 tool = 加函数 + 注册。
- 生命周期 Hooks:`before_step / after_step / before_tool / after_tool / on_error`,挂护栏/日志不动核心。
- LLM / embedding / 向量存储走 Protocol 接口,可替换实现。
- 关键扩展点内联注释 + AGENTS.md 专章。

**统一配置(轻量版)**:
- 单一 `config.yaml`(非密钥:llms/roles/context/tools/interfaces)+ `.env`(密钥真值,gitignored);`config.yaml` 只存 env 引用名(如 `api_key_env: OPENAI_API_KEY`)。
- `harness/config.py` 启动加载 + Pydantic 校验,作为全局唯一入口。**运行期热重载推迟到 L3**(MVP 改配置后重启即可,本地自用足够)。
- 生成期 `HarnessSpec` 与运行期 `config.yaml` 字段对齐,降低认知负担。

## 5. 架构

两层:**生成器(HarnessForge 本体)** 与 **生成产物(独立 harness 仓库)**。

```mermaid
flowchart LR
  user[User] --> entry["CLI (L1) / Web Wizard (L2)"]
  entry --> spec["HarnessSpec (Pydantic, YAML)"]
  spec --> gen["Generator (Jinja2)"]
  templates["Template Library (no agent framework)"] --> gen
  catalog["MCP Catalog (L2)"] -.-> gen
  gen --> repo["Generated Repo (owned)"]
  subgraph repoInner [Generated Repo]
    config["harness/config.py"]
    loop["harness/loop.py function-calling + budget"]
    llm["harness/llm.py Chat Completions (+profiles L2)"]
    tools["harness/tools.py (+MCP stdio L2)"]
    trace["harness/trace.py JSONL + cost"]
    cli["interfaces/cli.py run"]
    web["interfaces/web.py chat SSE (L2)"]
    ctx["harness/context.py (L2)"]
    rag["harness/rag.py (L3)"]
  end
  repo --> repoInner
```

生成器目录(仓库根 `/home/s1yu/HarnessForge`,独立 git repo,MIT;支持 `uvx harnessforge new` 免安装一次性运行):
- `harnessforge/spec.py` — `HarnessSpec`(version/project_slug/llms/roles/prompts/tools/interfaces/observability/budget;context/rag/secrets backend 字段预留但 MVP 不全实现)。
- `harnessforge/generator.py` — 渲染模板 → 写出仓库 + 拷入 `harness.spec.yaml` + `git init` + `uv lock` + 重跑警告不覆盖 + 生成后冒烟自检(`uv sync`+`pytest`+mock 跑一步)。
- `harnessforge/cli.py` — Typer 入口(`new`、`--spec`、`--preset`、交互模式、`doctor` 预检、`--no-verify` 关闭冒烟自检)。
- `harnessforge/catalog/mcp_servers.yaml` — 精选静态 MCP catalog(L2)。
- `harnessforge/presets/` — coding-assistant(L1)+ rag-research 骨架(L2)+ 空白示例。
- `harnessforge/templates/` — 生成产物 Jinja2 模板。
- `harnessforge/wizard/`(L2)— FastAPI + 单页静态表单。

生成产物仓库骨架(无 agent 框架):
- `pyproject.toml` — 最小依赖:`openai`、`pydantic`、`pydantic-settings`、`pyyaml`、`typer`;`fastapi`/`uvicorn`、`mcp`、`sqlite-vec`、`keyring` 按 spec 开关进 extra;**断言无 langchain/langgraph/adk**。
- `config.yaml` + `harness.spec.yaml` + `.env.example` + `LICENSE`(MIT)。
- **可运行性文件(§7)**:`uv.lock` + `.python-version` + `requirements.txt`(uv 导出兜底)+ `Dockerfile` + `.dockerignore` + `.devcontainer/devcontainer.json`(基于官方 `ghcr.io/astral-sh/uv` 镜像)。
- `src/<pkg>/harness/config.py` — 加载 `config.yaml`+`.env` + Pydantic 校验 + 密钥按 env 引用名解析。
- `src/<pkg>/harness/loop.py` — 原生 function-calling 循环(Chat Completions)+ Hooks 调用点 + 预算停止。
- `src/<pkg>/harness/hooks.py` — 生命周期 hook 接口与默认空实现(扩展点)。
- `src/<pkg>/harness/llm.py` — openai SDK 适配(base_url,provider-agnostic);profile 注册表 + `client_for(role)`(L2)。
- `src/<pkg>/harness/tools.py` — 注册表(装饰器)+ 风险标记;MCP stdio client(L2)。
- `src/<pkg>/harness/trace.py` — 每次 run 的 JSONL trace + token/成本计数。
- `src/<pkg>/harness/prompts.py` — 系统提示拼装。
- `src/<pkg>/harness/context.py`(L2)— truncate / summarize。
- `src/<pkg>/harness/rag.py`(L3)。
- `src/<pkg>/interfaces/cli.py` — `run`(L2 增 `ingest`)。
- `src/<pkg>/interfaces/web.py`(L2)— `/chat` SSE。
- `tests/` + `README.md` + `AGENTS.md`(扩展指南)+ `.env.example`。

## 6. 关键技术决策

已定(用户拍板):
- 名称 **HarnessForge**;生成器包/CLI `harnessforge`,产物默认包名 `agent_harness`(spec `project_slug` 可覆盖)。
- 仓库 `/home/s1yu/HarnessForge`,独立 git repo,**MIT**;GitHub `EpisodeYu/HarnessForge`。
- LLM 底座:**openai 官方 SDK + base_url**(provider-agnostic)。
- 循环:**原生 function-calling**(非文本解析 ReAct)。

本版新增/明确:
- **LLM API 面:走 Chat Completions + `tools`,不用 Responses API。** 理由:Responses 基本是 OpenAI 专属,而绝大多数第三方/本地 OpenAI 兼容端点(vLLM、together、groq 等)只实现 `/v1/chat/completions`;选 Chat Completions 才能兑现 provider-agnostic + base_url 的承诺。
- **安全(轻量,本地自用)**:MVP 不做沙箱/keyring/写不回显面板/全链路 redaction。只保两条硬约束——(1) **密钥不入 git**:`config.yaml`/`harness.spec.yaml` 只存 env 引用名,真值放 `.env`(gitignored);(2) **高风险工具(shell/写文件)默认不内置 / 默认关,仅 allowlist 显式开启**。HITL 确认与更强 redaction 推迟到有真实多环境/共享需求时再加。
- **API/SDK 版本与发布**:Python 3.11+;依赖 pin 版本;MCP/sqlite-vec 等仅在对应 L2/L3 模块引入并标平台要求;发布前查 PyPI 包名 `harnessforge` 是否重名;模板与产物的兼容靠 spec `version` 字段标注。
- **可运行性契约**:产物以 **uv** 为唯一环境契约(带 `uv.lock` + `.python-version`,uv 自动管 Python 与隔离 venv);**默认生成 `Dockerfile` + `.devcontainer`** 作为环境无关的运行保障(前期即纳入,非可选);生成器**默认对新仓库冒烟自检**(`uv sync` + `pytest` + mock 跑一步),`requirements.txt` 提供 pip 兜底。详见 §7。

自主细节(实现时可调):模板引擎 Jinja2;spec 用 Pydantic v2 + YAML;运行期配置 pydantic-settings;Web 无构建单页(Tailwind CDN);context 默认 `truncate`(summarize 为 L2 可选)。

**明确不做(保护定位)**:不做生产级权限系统、云托管、工作流编排 DSL、框架抽象层、在线 MCP registry、沙箱、多 agent、跨会话长期记忆。

## 7. 生成产物可运行性保障

目标:让生成产物在用户各异的环境中**开箱即跑**,把环境配置负担降到最低,并由生成器**主动验证**可运行性。原则:**复用 uv + 容器两条成熟路径,不自造环境/依赖/版本管理层,也不为减依赖而手写 Web/SSE 轮子**。

1. **uv 作为唯一环境契约**:产物随仓库带 `pyproject.toml` + `uv.lock` + `.python-version`。uv 自动下载匹配的托管 Python(用户无需预装 3.11)、自动建隔离 venv(不污染全局)、`uv sync` 一键就绪。README 首条命令即 `uv sync` → `uv run <pkg> run`;生成器本体走 `uvx harnessforge new`,全链路 uv 一致。
2. **依赖最小化由 spec 决定**:默认产物只含纯 Python / 通用 wheel 依赖(`openai` / `pydantic` / `pydantic-settings` / `pyyaml` / `typer`),零编译、任意 OS 可装。Web(`fastapi`/`uvicorn`)、MCP(`mcp`)、RAG(`sqlite-vec`)、keyring 等按 spec 开关进 `optional-dependencies`,未启用则不安装——"生成什么才依赖什么"。
3. **生成期锁定**:生成器写完仓库后跑 `uv lock`(universal resolution,跨平台),用户拿到已解析好的确定依赖集,避免解析漂移。
4. **生成后冒烟自检(默认开)**:生成器对新仓库执行 `uv sync` → import 自检 → mock LLM 跑一步 function-calling → `pytest -q`,全绿才报"可运行",失败给可读错误与修复建议;`--no-verify` 可关。另提供 `harnessforge doctor` 预检(uv 是否在、网络是否通、磁盘/权限)。
5. **Docker 一等公民(默认生成,前期纳入)**:每个产物默认生成 `Dockerfile` + `.dockerignore` + `.devcontainer/`(基于官方 `ghcr.io/astral-sh/uv` 镜像)。`docker build && docker run` 即得到与宿主完全无关的确定运行环境;Web 接口暴露端口,CLI 可进容器交互。面向"环境实在各异 / 不想动本机"的用户,这是最强的可运行性兜底,故**不作为可选项,前期即随产物产出**。
6. **pip 兜底路径**:`uv export --format requirements-txt` 同时产出 `requirements.txt`,README 提供 `python -m venv` + `pip install -e .` 备选;主推 uv,但不强制用户安装 uv。
7. **原生依赖兜底(L3)**:`sqlite-vec` 落地时配 numpy 余弦的纯 Python 兜底,缺平台 wheel 也能跑 RAG。

不做:不自写依赖/虚拟环境/Python 版本管理器(交给 uv);不为省依赖而手写 Web/SSE(保留 FastAPI)。

## 8. 验证标准(分 blocker / non-blocker)

**Blocker(MVP 必过,对应 L1)**:
- 黄金快照:示例/preset spec 生成项目 → `uv sync && pytest` 全绿 → 用 **mock LLM** 跑通一次 function-calling 循环(含一次工具调用)。
- **生成后冒烟自检通过**:生成器对新仓库 `uv sync` + import + mock 跑一步 + `pytest -q` 全绿(默认开,`--no-verify` 可关)。
- **Docker 可运行**:生成的 `Dockerfile` 能 `docker build` 成功,并 `docker run` 跑通 mock 一步(冒烟)。
- 断言生成的 `pyproject.toml` 不含 langchain/langgraph/adk。
- 生成项目 CLI 一问一答可跑通(mock 后端)。
- 扩展点:新注册一个 demo tool + 挂一个 hook 的测试,验证无需改核心代码即生效。
- 可观测:一次 run 产出结构正确的 JSONL trace + token/成本计数断言。
- 护栏:预算停止(步数/时间/成本超限即停)单测。
- 密钥不入 git:`config.yaml`/`harness.spec.yaml` 不含明文密钥的断言。
- 生成器自身:spec 校验、模板渲染单测、`uvx harnessforge new` 冒烟;`ReadLints` 无新增告警。
- coding-assistant preset 能成功生成并通过其 pytest。

**Non-blocker(L2/L3,做到即验,不卡 MVP)**:
- MCP stdio 工具调用通过、第 2 个 preset、Web `/chat` SSE 流式(mock)、多 profile `client_for(role)` 路由、context 策略单测;(L3)RAG ingest → 检索 → 注入端到端、`/config` 热重载、HITL 确认时序。

## 9. 路线图(垂直切片)

不按模块横向堆,按**端到端切片**纵向推进,每片都能跑通:

- **Slice 0 — 骨架**:`HarnessSpec` 最小字段 + Jinja2 生成引擎 + 写出仓库/拷 spec/git init + 渲染单测。产物:能生成一个空壳仓库。
- **Slice 1 — 黄金路径(核心里程碑)**:薄模板核心(config/llm/loop/tools/trace/prompts)+ 原生 function-calling(Chat Completions)+ 工具注册表 + 1 个内置工具 + 预算停止 + CLI `run` + JSONL trace + mock LLM 测试 + coding-assistant preset + README/AGENTS;**可运行性保障同期落地**(uv 契约 `uv.lock`+`.python-version`、默认 `Dockerfile`/`.devcontainer`、生成后冒烟自检、`requirements.txt` 兜底,见 §7)。**到此立项假设已被验证**:能生成一个无框架、**在任意环境**可跑通一次工具调用、可读可改的 harness。
- **Slice 2 — 接口与配置**:极简 Web chat(SSE)+ 多 profile 角色路由 + context(truncate,可选 summarize)+ 第 2 个 preset 骨架。
- **Slice 3 — 工具生态**:MCP stdio + 静态 catalog + allowlist;生成期 Web wizard。
- **Slice 4(v1+)**:RAG ingest + sqlite-vec、HTTP/SSE MCP、`/config` 热重载、keyring、完整 HITL Web、context offload。
- 全程伴随:`uvx` 打包、docs(突出无框架 + eject + own-your-code)、golden 测试随切片增量补充(**不再集中堆到最后**)。

## 10. 主要风险

- **环境多样性 / 可运行性**:不同 OS / Python 版本 / 无 uv / 无网络都可能让产物跑不起来。对策见 §7:uv 契约(自动管 Python + 隔离 venv)+ 默认最小依赖 + **默认产出 Docker** + 生成后冒烟自检 + pip 兜底。
- **scope 蔓延**:严守分层,L3 坚决推迟;每个 slice 必须端到端可跑再进下一片。
- **差异化锐度**:README/向导文案强调"把你原本会手写的 harness 生成出来,且生成后不再依赖 HarnessForge"。
- **provider 兼容**:以 Chat Completions + base_url 为准;`tool_calls` 在不同 provider 的细微差异需在 `llm.py` 收敛。
- **增强项复杂度**:trace/预算/context 要薄、默认可关,避免侵蚀"薄 harness"卖点。
- **(L2/L3)依赖漂移与平台兼容**:MCP/sqlite-vec pin 版本、catalog 标来源日期、sqlite-vec 标平台要求并备 numpy 余弦兜底。

## 11. 命名(已定)

- 项目名 **HarnessForge** —— 寓意"锻造你自己的 harness",最贴合 eject/生成 + 自有的差异化定位。
- 生成器 CLI/包:`harnessforge`;PyPI/仓库名同名(发布前需查重)。
