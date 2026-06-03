# 02·00 - 开发规划总览

> Plan 第 3 部分(开发)的入口。本目录按**垂直切片(vertical slice)**拆分,每个切片是一个端到端可生成 + 可跑 + 测试绿的增量。
>
> 本项目采用 **vibe coding 模式**:Agent 主导执行、人主导决策与节奏。协作硬约束见项目根 `CLAUDE.md`;定位 / 范围 / 决策见 `docs/01-project-plan.md`。下文"开发者要做 X"一律理解为"Agent 要做 X,由人按切片门禁验收"。

## 0. Agent 入场指南

1. 读完 `CLAUDE.md` + `docs/01-project-plan.md`。任一条不清楚,停下问人。
2. 以**代码 / 测试的实际状态**确认当前进展,不要只信文档默认描述。
3. 找到当前切片(见 §2):上一个切片门禁未全绿 → 从它继续;已完成且下一个没开始 → 主动问人"要不要进下一片"。
4. 在该切片子文档里挑 1 个未完成"交付物"作为本次任务。
5. 按 `CLAUDE.md §7` 的 plan → implement → self-verify → handoff 循环走,完成后输出 §8 完成报告。

> **不要**一次把所有子文档读完当上下文。每次只读当前切片相关的那一两份。

## 1. 为什么用垂直切片(而非瀑布式横向模块)

- 本项目是**生成器 + 薄产物**,最大风险是"集成留到最后才炸 / 复杂度失控"。垂直切片让每片都端到端跑通,**最早验证差异化**(无 agent 框架 + own-your-code + 可运行)。
- 不按 `loop / llm / tools / rag / web` 横向逐个堆完再集成。每个切片纵向穿过"spec → 生成 → 产物可跑 → 测试绿"。
- 切片之间有**完成门禁**:上一片门禁不全绿,不进下一片(除非某任务独立且人明确允许)。门禁内部的任务拆分与排序由 Agent 自主决定。

## 2. 切片路线图与完成门禁

```mermaid
graph LR
    S0["Slice 0 骨架<br/>spec + 渲染引擎"] --> S1["Slice 1 黄金路径 ★<br/>生成可跑的薄 harness"]
    S1 --> S2["Slice 2 路由+上下文<br/>profiles/role + context"]
    S2 --> S3["Slice 3 产物 Web<br/>chat SSE + /config 面板"]
    S3 --> S4["Slice 4 MCP 工具<br/>stdio + catalog + allowlist"]
    S4 --> S5["Slice 5 wizard+范式<br/>表单产 spec + 多范式渲染"]
    S5 --> V["v1+ (非 MVP)<br/>multi-agent / 周期预算 / RAG / 远程 MCP / …"]
```

> **切分说明(人已定向,2026-06)**:原"Slice 2 接口与配置 / Slice 3 工具生态"过胖(各捆了 3–4 件独立能力),已按中粒度重切为 S2–S5,每片 = 一个内聚能力。旧子文档 `03-slice-2-interfaces-and-config.md` / `04-slice-3-tools-ecosystem.md` 已被取代(内容拆入下表;细节见 git 历史)。

| 切片 | 子文档 | 主交付物 | 完成门禁(全绿才算完成) | 必须人审的决策点 |
|------|--------|----------|--------------------------|------------------|
| **Slice 0** 骨架 | [`01-slice-0-scaffold.md`](./01-slice-0-scaffold.md) | `HarnessSpec` 最小字段 + Jinja2 生成引擎 + 写出仓库 / 拷 spec / `git init` / 重跑警告 | spec 校验 + 渲染单测绿;能生成一个空壳仓库;`ReadLints` clean | spec 最小字段集是否合理 |
| **Slice 1** 黄金路径 ★核心里程碑 | [`02-slice-1-golden-path.md`](./02-slice-1-golden-path.md) | 薄模板核心(config/llm/loop/tools/hooks/trace/prompts/mock)+ 原生 function-calling(Chat Completions)+ 工具注册表 + 预算停止 + CLI `run` + JSONL trace + 可运行性保障(uv 契约 + 默认 Docker + 冒烟自检)+ coding-assistant preset。**状态:✅ 已完成(38 fast + 3 golden;ReadLints clean;§4 人审已签字)** | `01-project-plan.md §8` **全部 blocker** 通过(黄金快照、无框架断言、生成后冒烟、Docker 冒烟、CLI、tool+hook、trace、预算停止、密钥不入 git、`uvx` 冒烟、preset 生成并 pytest)✅ | **立项假设成立——人已签字 ✅** |
| **Slice 2** 路由 + 上下文 | [`03-slice-2-routing-and-context.md`](./03-slice-2-routing-and-context.md) | 多 LLM profile + `client_for(role)`(generation/compaction/embedding),loop 按角色取 client;context `truncate`(默认)+ 可选 `summarize`(走 compaction 角色)。**状态:✅ 已完成(38 fast + 3 golden;产物自带测试 14;ReadLints clean)** | non-blocker 测试绿:`client_for(role)` 路由(mock)、context 策略单测;关 summarize 时仍薄 ✅ | 角色集合/默认 context 策略是否合理(软确认,无硬门槛) |
| **Slice 3** 产物 Web(自持) | (开工时立子文档) | 产物 `interfaces/web.py`:FastAPI + **SSE 流式 chat** + **运行期 `/config` 配置面板**(决策④:行为性配置全可改);spec 开关,关掉则不含 fastapi/uvicorn 依赖 | `/chat` SSE 流式(mock)测试;`/config` 改运行期配置生效;关 Web 时 `pyproject` 不含 fastapi/uvicorn(薄验证) | Web/UX 一眼是否可用;配置面板可改字段范围 |
| **Slice 4** MCP 工具 | (开工时立子文档) | `harnessforge/catalog/mcp_servers.yaml` 静态 catalog;产物 MCP client(**仅 stdio**)+ allowlist + 沿用 Slice 1 风险标记;spec 开关(关掉不含 `mcp`) | MCP stdio 工具调用测试(本地 stdio mock server);非 allowlist tool 不注册;关 MCP 时 `pyproject` 不含 `mcp` | catalog 收录哪些 server(安全审,优先 vendor 维护) |
| **Slice 5** wizard + 范式 | (开工时立子文档) | `harnessforge/wizard/`(FastAPI + 单页静态表单,无构建)产合法 spec;**范式扁平多选** ReAct/Plan/Reflection → 渲染对应 `loop.py` 模板 | wizard 产出的 spec 校验通过并能 `generator` 生成;各范式渲染的产物 `uv sync && pytest` 绿 | wizard 字段是否齐/对外可读;范式默认集 |
| **Slice 6+ (v1+)** | (暂不立子文档) | **supervisor multi-agent**(agent 即 tool,固定拓扑,opt-in)、**周期预算**(天/周/月,持久化可选模块)、RAG ingest + sqlite-vec、HTTP/SSE 远程 MCP、`/config` 热重载进阶、keyring、完整 HITL Web、context offload | 各项做到即验(见 `01 §7 Non-blocker`) | **不在 MVP**;进入前需人决定排期 |

> **循环范式 / multi-agent(候选,v1+;人已定向)**:默认 loop 是单一原生 function-calling(ReAct/TAO),薄+无框架的核心卖点。扩展走 **wizard 扁平多选 + "生成期 spec 开关 → 渲染对应 `loop.py` 模板"**:① **单 loop 范式** ReAct(默认)/ Plan(Ask-Plan)/ Reflection;② **一种 supervisor multi-agent 模式**——以 "agent 即 tool"(子 agent = 再跑一个 `run()`)固定拓扑生成为**自有代码**,opt-in。**红线**:不做通用多 agent 编排框架 / 工作流 DSL / 动态图引擎 / 运行期范式抽象层(那是 `01 §6` 禁止的"框架抽象层")。multi-agent 定位措辞已按此细化(见 `01 §6`)。

> **周期预算(候选,v1+;人已定向)**:per-run 的 4 维上限(步数/时间/token/费用)已在 Slice 1 落地。"X/天·周·月"的周期配额需**跨 run 持久化用量账本**(本地 JSON,上 Web/多进程再换 sqlite+锁),**做成 spec 勾选的可选模块**(默认不生成,保持薄),与 Web/护栏一并做,不进当前 MVP 核心。

**Agent 行为提示**:

- 切片之间不要"偷跑":Slice 1 门禁没勾完不要开 Slice 2(除非任务独立且人明确允许)。
- 每片"必须人审的决策点"由人 approve,Agent 不能自行通过(`CLAUDE.md §6` 触发条件)。
- Slice 1 是核心里程碑:**它绿了,才证明这个项目方向成立**;它没绿之前,Slice 2/3 的价值都打折。

## 3. 全局决策总表(唯一口径)

> 子文档若出现不同写法,以本表为准并同步修订。改本表 = 改全局决策,走 `CLAUDE.md §6` 人审。详见 `01-project-plan.md §6`。

| 决策项 | 统一口径 |
|--------|----------|
| 名称 / 包 | 项目 `HarnessForge`;生成器包/CLI `harnessforge`;产物默认包名 `agent_harness`(spec `project_slug` 可覆盖) |
| 许可 / 仓库 | MIT;`/home/s1yu/HarnessForge`,GitHub `EpisodeYu/HarnessForge` |
| LLM 底座 | openai 官方 SDK + `base_url`(provider-agnostic) |
| **LLM API 面** | **Chat Completions + `tools`,不用 Responses**(兼容第三方 / 本地 OpenAI 兼容端点) |
| 循环 | 原生 function-calling(非文本解析 ReAct) |
| 模板 / spec | Jinja2;`HarnessSpec` = Pydantic v2 + YAML,带 `version`;运行期 pydantic-settings |
| Python / 工具 | Python 3.11+;`uv`(lock + 自动管 Python + 隔离 venv) |
| **可运行性契约** | 产物随仓库带 `uv.lock` + `.python-version`;**默认生成 `Dockerfile` + `.devcontainer`**;生成器**默认对新仓库冒烟自检**;`requirements.txt` 作 pip 兜底 |
| 安全(轻量,本地自用) | 密钥不入 git(`config.yaml`/`harness.spec.yaml` 只存 env 引用名,真值放 `.env`);高风险工具(shell/写文件)默认关,仅 allowlist 显式开;沙箱 / keyring / 全链路 redaction 推迟 |
| MCP | MVP 仅 **stdio 本地**传输 + 手策静态 catalog;HTTP/SSE 远程 + 联网 registry 推迟到 L3/v2 |
| context 默认 | `truncate`(summarize 为 L2 可选;offload 为 L3) |
| 配置控制面 | **spec = 配方(生成什么 + 初值);`config.yaml` = 运行期权威活旋钮(行为性配置全可改)**;结构性变更(接口/模块/范式拓扑=代码)需重新生成或 `forge add`。运行期配置面板**生成进产物自身 Web**(产物自持),**HarnessForge 不做中心化配置/托管**(守"生成后不再依赖 HarnessForge") |
| 范式 / multi-agent | 默认 ReAct;扩展走 wizard 扁平多选 + spec 渲染不同 `loop.py`:单 loop 范式(ReAct/Plan/Reflection)+ **一种 supervisor multi-agent(agent 即 tool,固定拓扑,生成为自有代码,opt-in)**;**禁**通用多 agent 编排框架 / 工作流 DSL / 动态图引擎。排 v1+ |
| 预算 | per-run 4 维(步数/时间/token/费用)在核心;**周期配额(天/周/月)= spec 勾选的可选持久化模块**,默认不生成,排 v1+ |

## 4. 目录骨架

> 详见 `01-project-plan.md §5`。

```
HarnessForge/                      # 生成器本体(本仓库)
├── CLAUDE.md                      # Agent 守则
├── README.md
├── pyproject.toml                 # 生成器依赖(typer/jinja2/pydantic/pyyaml + dev: pytest)
├── docs/
│   ├── 00-research-and-feasibility.md
│   ├── 01-project-plan.md
│   └── 02-development/            # 本目录
├── harnessforge/
│   ├── spec.py                    # HarnessSpec
│   ├── generator.py               # 渲染 + 写仓库 + uv lock + 冒烟自检
│   ├── cli.py                     # new / --spec / --preset / doctor / --no-verify
│   ├── catalog/mcp_servers.yaml   # (Slice 3) 静态 MCP catalog
│   ├── presets/                   # coding-assistant / rag-research 骨架 / 空白示例
│   ├── wizard/                    # (Slice 3) FastAPI 单页表单
│   └── templates/                 # 生成产物 Jinja2 模板(见下)
└── tests/                         # 生成器单测 + 黄金快照测试

# 生成产物骨架(由 templates/ 渲染,用户拥有):
<pkg>/
├── pyproject.toml                 # 最小依赖;断言无 langchain/langgraph/adk
├── config.yaml + harness.spec.yaml + .env.example + LICENSE
├── uv.lock + .python-version + requirements.txt
├── Dockerfile + .dockerignore + .devcontainer/
├── src/<pkg>/harness/             # config/loop/llm/tools/trace/prompts/hooks (+context L2, +rag L3)
├── src/<pkg>/interfaces/          # cli.py (run) (+web.py SSE L2)
└── tests/ + README.md + AGENTS.md
```

## 5. 命名约定

- Python 包:生成器 `harnessforge`,产物 `<project_slug>`(默认 `agent_harness`),统一 snake_case。
- spec 文件:生成期 `harness.spec.yaml`;运行期 `config.yaml` + `.env`。
- 角色名:`generation` / `compaction` / `embedding`(可扩展)。
- 测试:`tests/test_*.py`;黄金快照测试单独标记(慢测,可 `-m golden`)。

## 6. 开发规则

- **Conventional Commits**;`main` **不受保护**,门禁全绿后 Agent 可直接 commit + push `main`(不 `--force`、测试未绿不推;见 `CLAUDE.md §8`)。
- **测试硬门槛**:黄金路径 + 可运行性自检,见 `CLAUDE.md §5`。生成器项目的"完成"以**生成产物能跑通**为准,不是"生成器代码写完"。
- **薄优先 + 两层心智**:见 `CLAUDE.md §2 / §4`。任何给默认产物加依赖的冲动,先回看 §3 决策表与 `CLAUDE.md §6`。

## 7. 本期不做(提醒)

> 出现冲动时回看。来自 `01-project-plan.md §6`。

不做:生产级权限系统、云托管、**通用多 agent 编排框架 / 工作流编排 DSL / 动态图引擎 / 运行期范式抽象层**、在线 MCP registry、沙箱、跨会话长期记忆、**HarnessForge 侧中心化配置/托管**;以及 L3/v1+ 项(RAG / HTTP-SSE MCP / `/config` 热重载 / keyring / 完整 HITL Web / context offload / 多范式 + 一种 supervisor multi-agent / 周期预算)在 MVP 内不做。

> **注**:multi-agent 不是一刀切禁掉——红线是"通用编排框架"。允许 v1+ 做**一个具体、固定拓扑、生成为自有代码的 supervisor 模式**(opt-in),详见 `01-project-plan.md §6`。

## 8. 完成报告模板(每个任务完成后输出)

```markdown
## 任务:<goal>(Slice N)

### 交付物
- <文件/模块/模板/测试变更点>

### 自验证结果
- [x] 黄金路径:示例/preset 生成 → `uv sync && pytest` 全绿 → mock 跑通一次工具调用
- [x] 无框架断言:生成的 pyproject 不含 langchain/langgraph/adk
- [x] 生成后冒烟自检:通过
- [x] (大改动)Docker 冒烟 / `uvx harnessforge new` 冒烟:通过
- [x] ReadLints:clean

### 留给人审的项
- <生成产物是否够薄/可读;UX;命名是否对外可读>

### 自主决策记录(CLAUDE.md §5.3)
- <一句话:选了什么 / 理由>

### 剩余风险 / 已知问题
- <记入 TODO 而非本任务范围的项>

### 下一步建议
- <自然的下一任务>
```

> 没有这份报告 → 任务未结束。5 段都不能空,但越简短越好。

## 9. 阅读顺序

`CLAUDE.md` → `01-project-plan.md` → 本文(`00-overview.md`)→ 当前切片子文档(只读相关那份)。
