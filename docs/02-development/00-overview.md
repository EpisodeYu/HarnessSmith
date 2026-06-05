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
    S3 --> S4["Slice 4 MCP 工具<br/>stdio + 远程 + allowlist"]
    S4 --> S5["Slice 5 多范式<br/>注册表 + 运行期切/扩展"]
    S5 --> S6["Slice 6 工具基线+SKILL<br/>MCP fetch/git/DC + Agent Skills"]
    S6 --> S7["Slice 7 wizard<br/>表单产 spec"]
    S7 --> V["v1+ (非 MVP, Slice 8+)<br/>multi-agent / 周期预算 / RAG / MCP registry / …"]
```

> **切分说明(人已定向,2026-06)**:原"Slice 2 接口与配置 / Slice 3 工具生态"过胖,已按中粒度重切为每片 = 一个内聚能力。**2026-06-05 再切**:原 Slice 5(wizard+范式+MCP 基线)过大,拆为 **Slice 5 多范式 / Slice 6 工具基线+SKILL / Slice 7 wizard**(原"Slice 6+ v1+"顺延为 Slice 8+)。旧子文档 `03-slice-2-interfaces-and-config.md` / `04-slice-3-tools-ecosystem.md` / `06-slice-5-wizard-and-paradigms.md` 已被取代(细节见 git 历史)。

| 切片 | 子文档 | 主交付物 | 完成门禁(全绿才算完成) | 必须人审的决策点 |
|------|--------|----------|--------------------------|------------------|
| **Slice 0** 骨架 | [`01-slice-0-scaffold.md`](./01-slice-0-scaffold.md) | `HarnessSpec` 最小字段 + Jinja2 生成引擎 + 写出仓库 / 拷 spec / `git init` / 重跑警告 | spec 校验 + 渲染单测绿;能生成一个空壳仓库;`ReadLints` clean | spec 最小字段集是否合理 |
| **Slice 1** 黄金路径 ★核心里程碑 | [`02-slice-1-golden-path.md`](./02-slice-1-golden-path.md) | 薄模板核心(config/llm/loop/tools/hooks/trace/prompts/mock)+ 原生 function-calling(Chat Completions)+ 工具注册表 + 预算停止 + CLI `run` + JSONL trace + 可运行性保障(uv 契约 + 默认 Docker + 冒烟自检)+ coding-assistant preset。**状态:✅ 已完成(38 fast + 3 golden;ReadLints clean;§4 人审已签字)** | `01-project-plan.md §8` **全部 blocker** 通过(黄金快照、无框架断言、生成后冒烟、Docker 冒烟、CLI、tool+hook、trace、预算停止、密钥不入 git、`uvx` 冒烟、preset 生成并 pytest)✅ | **立项假设成立——人已签字 ✅** |
| **Slice 2** 路由 + 上下文 | [`03-slice-2-routing-and-context.md`](./03-slice-2-routing-and-context.md) | 多 LLM profile + `client_for(role)`(generation/compaction/embedding),loop 按角色取 client;context `truncate`(默认)+ 可选 `summarize`(走 compaction 角色)。**状态:✅ 已完成(38 fast + 3 golden;产物自带测试 14;ReadLints clean)** | non-blocker 测试绿:`client_for(role)` 路由(mock)、context 策略单测;关 summarize 时仍薄 ✅ | 角色集合/默认 context 策略是否合理(软确认,无硬门槛) |
| **Slice 3** 产物 Web(自持) | [`04-slice-3-product-web.md`](./04-slice-3-product-web.md) | 产物 `interfaces/web.py`:FastAPI + **SSE chat,默认 token 级流式、可选**(`llm.stream`+`loop.run(on_delta)`,仍 Chat Completions)+ **运行期 `/config` 配置面板**(决策④:行为性配置全可改,进程内生效);spec 开关 `interfaces.web`,关掉则零 Web 痕迹、不含 fastapi/uvicorn。生成器新增**按 spec 条件渲染文件**机制。**状态:✅ 已完成,门禁全绿(41 fast + 4 golden);§4 两项人审 2026-06-03 经真实 LLM(`mimo-v2.5-pro`)验收已签字通过** | `/chat` token 流 / 非流(mock)测试 ✅;`/config` 改运行期配置生效 ✅;关 Web 时 `pyproject`/`lock`/`req` 不含 fastapi/uvicorn(薄验证)✅ | Web/UX 一眼是否可用 ✅;配置面板可改字段范围 ✅(2026-06-03 人已签字) |
| **Slice 4** MCP 工具 | [`05-slice-4-mcp-tools.md`](./05-slice-4-mcp-tools.md) | 产物 MCP client(**stdio + 远程 HTTP/SSE**,人 2026-06-03 定向)+ allowlist + 沿用 Slice 1 风险标记。**生成期只决定 on/off**(`spec.mcp.enabled` + `mcp` 依赖,关掉零痕迹);**server/tool/传输全运行期** `config.yaml`(tool allowlist 可经 Slice 3 `/config` 当场改)。catalog(预设便捷数据源)挪 Slice 5 wizard。**状态:✅ 已完成,门禁全绿(45 fast + 5 golden;新增 mcp 端到端真实 stdio 工具调用);`mcp.py` 147 行代码薄;关 MCP 字节一致零痕迹** | MCP stdio 工具调用测试(本地 stdio mock server)✅ + 远程传输路径覆盖 ✅;非 allowlist tool 不注册 ✅;关 MCP 时 `pyproject`/`uv.lock`/`req` 不含 `mcp` ✅ | ① 新增 `mcp.enabled` spec 字段(§6.1)**人 2026-06-05 签字方案 A ✅**;② 远程 HTTP/SSE 纳入 MVP(改全局决策,**人 2026-06-03 已定向 ✅**) |
| **Slice 5** 多范式 + 注册表 | [`06-slice-5-paradigms.md`](./06-slice-5-paradigms.md) | 生成期**多选**范式 **Agent/Plan/Ask**(对齐 Cursor 三件套) → 渲染**共存**的薄循环(各自自包含、互不 import),**产物运行期每轮可切一种**(类 Cursor agent/ask/plan;CLI `--mode`+Web 下拉;清单+默认进 `config.yaml`)**且用户可自加范式**(`harness/paradigms/` 薄注册表 + `@register_paradigm`,同 tools 扩展);Plan/Ask 只读。重塑核心 `loop.py` 为薄分发入口 + 范式注册表(始终存在)。**状态:✅ 已完成(2026-06-05;范式集 `agent/plan/ask` 修订版,见子文档 §4②′)。门禁全绿:生成器快测 54 + 多范式产物自带测试 30 + golden 6(含多范式/uvx/Docker);本机 LiteLLM(`mimo-v2.5-pro`)agent/plan/ask 真实冒烟全跑通;ReadLints clean** | ✅ 多范式生成 `uv sync && pytest` 绿 + 运行期切;✅ 用户自加范式可跑且不改内置/注册表核心;✅ 内置范式互不 import;✅ Plan/Ask 只读不触发高风险;✅ agent-only 行为与 Slice 1–4 一致(非逐字)+ 无新增依赖 | ①–⑪ 人 2026-06-05 定稿;**②′ 当日修订范式集 react/plan/ask/reflection → agent/plan/ask**(调研:Cursor/Claude 只有 Agent/Ask/Plan、无 reflection 开关;reflection 靠真实信号条件触发或被推理模型内化 → 删独立 reflection 范式,Reflexion 作用户扩展范例) |
| **Slice 6** 工具基线 + 标准 SKILL | [`07-slice-6-tools-and-skills.md`](./07-slice-6-tools-and-skills.md) | **MCP 预设做基线**(产物无内置实用工具→能力全由 MCP 提供、不自写 built-in):`ddg-search`(免 key 联网搜索)+ `fetch` 默认开 + `git` 读开/写关 + Desktop Commander 预填一键开(写/shell 默认关,且无启用工具不被启动);`catalog/mcp_servers.yaml`(新建)+ CLI `--mcp-server`/preset `mcp_prefill.yaml` 预填 `config.yaml`(不进 spec/快照);**按工具风险分级**(`safe_tools`→只读范式可用);**系统提示注入环境感知**(OS/shell + 预置但禁用能力如何开,守 §6 不破红线;含 Windows OS 提示);离线靠**生成期预热 + Docker 烤镜像(`UV_OFFLINE=1`)**;海量扩展走 marketplace 文档 + Composio 式 remote MCP。**标准 SKILL**:Agent Skills 开放标准(`SKILL.md` + 渐进披露)——`skills.py` 发现+注入(L1)+ `read_skill`/文件工具读正文(L2)+ 脚本经工具跑(L3);`spec.skills.enabled` 门控、目录走运行期 `config.yaml skills.dirs`。**状态:✅ 已完成(2026-06-05)。Part A(工具基线,commit `d83a85a`)+ Part B(标准 SKILL)门禁全绿:快测 70 + 产物 25/24 + golden 8 + docker 2(MCP 离线基线)** | 基线开箱可用(fetch/git 读默认开、DC 预填默认关)✅ + 离线/Docker 可用 ✅;catalog 落 `config.yaml`✅;极薄 example 仍薄 ✅;SKILL 发现+注入+加载并遵循(mock)✅ + 关 SKILL 零痕迹 ✅ | ① MCP 预设做基线 ✅;② 官方 git 预置 ✅;③ 标准 SKILL 放本片 ✅;④ `spec.skills`=仅 `enabled`、dirs 走运行期(B)✅;⑤ 风险按工具分级(B)✅;⑥ split 推进 ✅(人 2026-06-05) |
| **Slice 7** wizard | [`08-slice-7-wizard.md`](./08-slice-7-wizard.md) | `harnessforge/wizard/`(FastAPI + 无构建单页,`[wizard]` extra)采集 `HarnessSpec` 全字段(基础/高级分组,含 `paradigms`/`mcp.enabled`+catalog/`skills.enabled`)→ `POST /spec` 校验产合法 spec + 可选一键 `generate()`;只采集 env 名、不进产物。**状态:📝 规划中(字段面人 2026-06-05 定稿;放最后,覆盖稳定后的 spec 全字段)** | wizard 产合法 spec 能生成;不泄密/不进产物(核心 CLI 与产物无 fastapi/uvicorn);catalog 预填经 wizard 落 `config.yaml`;字段对外可读(实现后真实验收) | ① wizard 全覆盖+基础/高级分组 ✅(人 2026-06-05);② 字段是否齐/对外可读(实现后验收) |
| **Slice 8+ (v1+)** | (暂不立子文档) | **supervisor multi-agent**(agent 即 tool,固定拓扑,opt-in)、**周期预算**(天/周/月,持久化可选模块)、RAG ingest + sqlite-vec、**联网 MCP registry / `/config` 改 MCP server 热重连 / `forge add` 增量接 server**(MCP 远程 HTTP/SSE 传输本身已提前进 Slice 4)、**发布拓扑:`/config` 与公开面隔离**(管理面鉴权 / 绑 localhost / 生成期开关,使"管理员托管 + 接口发布"时 `/config` 不可被终端用户访问;人 2026-06-05 登记,见 `04-slice-3-product-web.md §4`)、`/config` 热重载进阶、keyring、完整 HITL Web、**工具调用 HITL 确认**(allow/reject/always-allow;内置可选 `before_tool` 确认 hook,**今天已可经 `before_tool` hook `raise`-veto 自实现**、v1+ 做成内置 + 干净 allow/deny 返回;**非交互/Web 必须默认拒绝**;**是否据此把 shell 默认开 = 改 §6 全局口径,待人签字**,人 2026-06-05 登记)、**MCP 状态自检/健康标注**(probe 每个配置 server 连通 + 工具计数 + 不可达标红 + 缺 Node 提示;CLI `<pkg> mcp status`/扩 `doctor` + `/config` 健康视图,对齐 Cursor MCP 面板;**复用现有 `McpManager.errors`/`discovered`**、run-start 补记 skipped;人 2026-06-05 登记)、context offload、**推理模型流式 UX**(reasoning 阶段显式提示/思考流,避免无反应等待;2026-06-03 真实 LLM 验收发现,详见 `04-slice-3-product-web.md §4`) | 各项做到即验(见 `01 §7 Non-blocker`) | **不在 MVP**;进入前需人决定排期 |

> **循环范式 / multi-agent(候选,人已定向)**:默认 loop 是单一原生 function-calling(ReAct/TAO),薄+无框架的核心卖点。扩展走 **wizard 生成期多选 + 产物侧薄范式注册表**(人 2026-06-05 定向,Slice 5):① **单 loop 范式集 Agent(默认)/ Plan / Ask**(对齐 Cursor 三件套;`agent` = ReAct 式 tool-calling 循环,**初版 react/plan/ask/reflection 当日修订为此**,见子文档 §4②′)——生成期**多选**进产物**共存**,**产物运行期每轮选一种**(类 Cursor agent/ask/plan;CLI `--mode` + Web 下拉;运行期清单 + 默认进 `config.yaml`,首项种默认);**Plan/Ask 只读**(只 offer 只读/低风险工具、禁 write/shell;Plan 对齐 Cursor 只产只读计划不动手,Build 切换推迟)。**反思**不作独立范式:agent 循环已"在线自纠"(工具报错喂回→重试),事后 Reflexion(验证器门控重试)作 `AGENTS.md` 用户扩展范例。**② 范式可扩展(核心卖点)**——产物 `harness/paradigms/` 持**与 tools 同款的薄注册表 + `@register_paradigm` 装饰器**,**运行期用户可自加范式**(写函数+注册+配 `enabled`);**内置范式各自自包含、互不 import**(改 agent 不影响 ask);**注册表始终存在**(连只选 agent 也有)→ 默认产物不再与 Slice 1–4 逐字一致(门禁改"行为一致+无新增依赖");**扩展性/解耦优先于薄**。运行期"每轮选范式" + "范式注册表" **实现为已注册模式集的写死按名分发(own-code),不是被禁的"运行期范式抽象层"/动态图/DSL/编排引擎**。③ **一种 supervisor multi-agent 模式**(agent 即 tool,固定拓扑,生成为自有代码,opt-in)——**排 v1+(Slice 8+)**;用户自写 multi-agent 范式属其 own-code。**红线**:不做通用多 agent 编排框架 / 工作流 DSL / 动态图引擎 / 运行期范式抽象层(`01 §6`)。详见 `06-slice-5-paradigms.md`。
>
> **工具基线 + 标准 SKILL(Slice 6,人 2026-06-05 定向)**:产物无内置实用工具 → 基线能力**全由 MCP 预设提供、不自写 built-in**(`fetch` 默认开 / `git` 读开写关 / Desktop Commander 预填一键开,离线靠生成期预热 + Docker 烤镜像;海量扩展走 marketplace 文档 + Composio 式 remote MCP,**不做联网 registry**)。并支持 **Agent Skills 开放标准**(`SKILL.md` 渐进披露:发现+注入 → 文件工具/`read_skill` 读正文 → 脚本经工具跑),`spec.skills.enabled` 门控、不引框架。详见 `07-slice-6-tools-and-skills.md`。

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
| MCP | **stdio 本地 + 远程 HTTP/SSE 传输都做**(人 2026-06-03 定向,取代原"仅 stdio");**生成期只决定 on/off**(`spec.mcp.enabled` + `mcp` 依赖),**server/tool/传输全运行期** `config.yaml`(用户可自带 server,无白名单;安全闸=tool allowlist + 风险标记 + 密钥按 env 名)。catalog(Slice 6)= MCP 预设的静态精选 + wizard/CLI 预填数据源(非编译进产物、非安全闸);**因产物无内置实用工具,Slice 6 起 MCP 预设兼做"基线能力来源"**(`fetch` 默认开 + `git` 读开/写关 + Desktop Commander 预填默认关,不自写 built-in;离线靠生成期预热 + Docker 烤镜像),海量扩展走 marketplace 文档 + Composio 式 remote MCP。**联网 MCP registry / `forge add` 仍推迟 v1+** |
| 范式 / 技能 扩展 | **范式(Slice 5)**:生成期多选 Agent/Plan/Ask(对齐 Cursor;初版 react/plan/ask/reflection 已修订,见子文档 §4②′)+ 产物侧薄注册表(`@register_paradigm`)运行期可自加、每轮可切;详上"循环范式"行 + 决策表无重复。**标准 SKILL(Slice 6)**:支持 **Agent Skills 开放标准**(`SKILL.md` + 渐进披露 L1 发现注入 / L2 文件工具或 `read_skill` 读正文 / L3 脚本经工具跑),`spec.skills.enabled` 门控、不引框架;技能脚本=高风险默认关。**两者都是 own-code 薄扩展点,禁框架/动态图/DSL** |
| context 默认 | `truncate`(summarize 为 L2 可选;offload 为 L3) |
| 配置控制面 | **spec = 配方(生成什么 + 初值);`config.yaml` = 运行期权威活旋钮(行为性配置全可改)**;结构性变更(接口/模块/范式拓扑=代码)需重新生成或 `forge add`。运行期配置面板**生成进产物自身 Web**(产物自持),**HarnessForge 不做中心化配置/托管**(守"生成后不再依赖 HarnessForge") |
| **权限 / 控制面两轴**(人 2026-06-03 定向) | **结构轴(生成期 = 能力天花板,生成器拥有)vs 行为轴(运行期 = 天花板内调参,`config.yaml`/`/config` 拥有)**。安全相关"能力面"属**结构轴**:tool allowlist 运行期只能**收窄不能扩张**,锁某能力 = 生成期**不编译进去**(缺席强制);`/config` 关工具是便利收窄、**非安全保证**。own-code 下生成器只能设**天花板**、设不了对代码所有者的**地板**。威胁模型 **A 护栏**(可信会手滑)= 生成器搞定;**B 对手强制** = 靠容器 / 自托管 / 后端凭证作用域,**守"不做生产级权限系统"**。**拓扑(2026-06-05 补)**:① 分发仓库 = 代码所有者 = 只有天花板没地板;② 管理员托管 + 接口发布(更常见)= 边界在网络接口 = 能对终端用户**强制地板**、运行期配置可改也安全,**前提 `/config` 须与公开面隔离**(见 §2 Slice 8+ backlog)。详见 `01 §4` |
| 范式 / multi-agent | 默认 Agent(ReAct 式);扩展走 wizard **生成期多选** + 产物侧**薄范式注册表**(人 2026-06-05 定向,Slice 5):范式集 **Agent/Plan/Ask**(对齐 Cursor 三件套;初版 react/plan/ask/reflection 当日修订,见子文档 §4②′)多选进产物**共存**、**运行期每轮选一种**(类 Cursor agent/ask/plan;CLI `--mode`+Web 下拉;运行期 `enabled`+`default` 进 `config.yaml`、首项种默认;**Plan/Ask 只读**=排高风险工具,Plan 只产只读计划、Build 推迟)。**反思不作独立范式**:agent 在线自纠 + Reflexion(验证器门控)作用户扩展范例。**范式可扩展(核心卖点)= 与 tools 同款薄注册表 + `@register_paradigm` 装饰器,运行期用户可自加范式**;内置范式各自自包含、互不 import;**注册表始终存在**(默认产物不再与 Slice 1–4 逐字一致,改"行为一致");**扩展/解耦优先于薄**。注册表/切换 = **已注册模式集的写死按名分发(own-code),非"运行期范式抽象层"**。**一种 supervisor multi-agent(agent 即 tool,固定拓扑,生成为自有代码,opt-in)排 v1+**;**禁**通用多 agent 编排框架 / 工作流 DSL / 动态图引擎 / 运行期范式抽象层 |
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
│   ├── generator.py               # 渲染(+按 spec 条件渲染)+ 写仓库 + uv lock + 冒烟自检
│   ├── cli.py                     # new / --spec / --preset / doctor / --no-verify
│   ├── catalog/mcp_servers.yaml   # (Slice 6) MCP 基线 + wizard/CLI 预填清单(fetch/git/DC...)
│   ├── presets/                   # coding-assistant(Slice 6 升级为 MCP 基线)/ 极薄 example / rag-research 骨架
│   ├── wizard/                    # (Slice 7) FastAPI 单页表单(harnessforge[wizard] extra)
│   └── templates/                 # 生成产物 Jinja2 模板(见下)
└── tests/                         # 生成器单测 + 黄金快照测试

# 生成产物骨架(由 templates/ 渲染,用户拥有):
<pkg>/
├── pyproject.toml                 # 最小依赖;断言无 langchain/langgraph/adk
├── config.yaml + harness.spec.yaml + .env.example + LICENSE
├── uv.lock + .python-version + requirements.txt
├── Dockerfile + .dockerignore + .devcontainer/
├── src/<pkg>/harness/             # config/loop/llm/tools/trace/prompts/hooks (+context L2, +mcp.py Slice 4 opt-in, +paradigms/ Slice 5 始终, +skills.py Slice 6 opt-in, +rag L3)
├── src/<pkg>/interfaces/          # cli.py (run, +--mode Slice 5) (+web.py SSE chat + /config + 范式下拉,Slice 3/5,opt-in)
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

不做:生产级权限系统、云托管、**通用多 agent 编排框架 / 工作流编排 DSL / 动态图引擎 / 运行期范式抽象层**、在线 MCP registry、沙箱、跨会话长期记忆、**HarnessForge 侧中心化配置/托管**;以及 L3/v1+ 项(RAG / 联网 MCP registry / `/config` 热重载 / keyring / 完整 HITL Web / context offload / **一种 supervisor multi-agent** / 周期预算)在 MVP 内不做。(注:**多范式(单 loop Agent/Plan/Ask)已进 Slice 5、工具基线 + 标准 SKILL 进 Slice 6**——它们不是被禁项;被禁的是"通用多 agent 编排框架 / 范式抽象层"。MCP 远程 HTTP/SSE 传输已于 2026-06-03 提前进 Slice 4/L2。)

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
