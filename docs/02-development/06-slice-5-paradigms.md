# 02·06 - Slice 5:多范式 + 范式注册表/扩展(生成期多选 → 共存薄循环 + 运行期每轮切 + 用户可自加范式)

> 目标:① **多范式**——生成期**多选**循环范式(**Agent/Plan/Ask**,对齐 Cursor 三件套),渲染出**共存**的薄循环,产物**运行期每轮可切一种**(类 Cursor agent/ask/plan;CLI `--mode` + Web 下拉);② **范式可扩展(本片核心卖点)**——产物运行期**允许用户自加范式**:与 tools 同款的**薄注册表 + 装饰器**(`@register_paradigm`),写个函数 + 注册 + 配进 `config.yaml` 即生效。属 `01-project-plan.md` 的 **L3 候选(人已定向)**。
>
> **范式集修订(2026-06-05,人定向,见 §4②′)**:初版定 `react/plan/ask/reflection`,落地后经业界调研(Cursor/Claude 只暴露 Agent/Ask/Plan、无 reflection 开关;reflection 在产品里要么被推理模型内化、要么是**靠真实成功信号条件触发**的事后重试,无信号自评是反模式)定为 **`agent/plan/ask`**:`react`→`agent`(对齐主流命名 + 本就是默认 tool-calling 循环);**删掉独立 `reflection` 范式与轮数旋钮**——agent 循环已"在线自纠"(工具报错喂回→重试),真正的 Reflexion(验证器门控重试)改作 `AGENTS.md` 的**用户自有扩展范例**(需用户自备成功信号,守"不替用户假设成功信号 + 薄")。
>
> **本片范围(2026-06-05 重切)**:原 Slice 5 过大,已拆为三片——**Slice 5 = 多范式 + 注册表(本片)**;**Slice 6 = 工具基线(MCP fetch/git/Desktop Commander)+ catalog + 标准 SKILL**(见 `07-slice-6-tools-and-skills.md`);**Slice 7 = wizard 表单产 spec**(见 `08-slice-7-wizard.md`)。
>
> 前置:Slice 4 门禁全绿(已 ✅)。
>
> **状态:✅ 已完成(2026-06-05;范式集 `agent/plan/ask` 修订版)。** 门禁(§3)全绿:生成器快测 54、多范式生成产物自带测试 30(agent/plan/ask + 自定义范式扩展 + 只读边界 + web 下拉/SSE)、golden 6(含多范式 + uvx + Docker);**本机 LiteLLM(`mimo-v2.5-pro`)真实冒烟 agent/plan/ask 全跑通**(agent 真实工具调用→437;plan 出只读计划;ask 只读答;未启用 `--mode reflection` 干净报错退出 2);`ReadLints` clean。核心设计经人 2026-06-05 定向定稿(范式多选 + 运行期每轮切 + Plan/Ask 只读 + 默认取首项 + Build 推迟;可扩展薄注册表+装饰器 / 每范式自包含 / 注册表始终存在 / 运行期清单进 `config.yaml`,见 §4 ①–⑪),**范式集当日二次修订为 `agent/plan/ask`(§4②′)**。**命中 `CLAUDE.md §6.1`**(新增 `paradigms` 字段)**与 §6.8/§6.10**(重塑核心 `loop.py` 为范式注册表)——人已签字定向。实现说明见 §6。
>
> **重要:默认产物不再逐字一致(人已定向放宽薄)**:范式注册表**始终存在**(即便只选 agent),故默认产物相对 Slice 1–4 **结构上引入 `harness/paradigms/` 注册表 + `config.yaml` 的 `paradigms:` 段**;门禁改为"**行为一致**(golden mock 路径不变)+ 无新增依赖",不再要求逐字一致(§3)。**这是对 Slice 1 核心里程碑 `loop.py` 的架构改动**,按 `CLAUDE.md §6` 人已定向:**扩展性 / 解耦优先于薄**。
>
> **红线提醒(本片有真实张力,务必记牢)**:范式注册表是**与 tools 注册表同款的 own-your-code 薄扩展点**(`dict[name→callable]` + 装饰器 + 统一 `Paradigm` 契约),**不是** `01 §6` 禁止的"**运行期范式抽象层 / 动态图引擎 / 工作流 DSL / 通用编排框架**"。运行期"每轮选范式"是**固定/已注册模式集的写死按名分发**,每个范式是用户可读可删的自有代码。**supervisor multi-agent(agent 即 tool)仍排 v1+**;用户当然可以自己写一个 multi-agent 范式注册进去(那是用户的 own-code,非 HF 出框架)。

## 0. 边界与口径(开工前先对齐)

- **可扩展性 > 薄(本片基调,人已定向)**:范式是产物核心卖点"高度可扩展 + own-your-code"的主战场。当"薄"与"用户能否自由改/加范式"冲突时,**优先扩展与解耦**(`CLAUDE.md §2` 的薄默认在此让位,经人 2026-06-05 明确)。但**单个范式仍应可通读**(各自 loop 量级,贴 `01 §2`),薄的让步只针对"多份自包含 + 注册表"带来的总量增长,不是给单个范式注水。
- **生成期 vs 运行期(决策④,`01 §4` / `00-overview §3`)**:
  - **渲染哪些内置范式 + 注册表是否存在 = 结构性 = 生成期**(`spec.paradigms` 选内置范式;**注册表始终渲染**)。`spec.paradigms[0]` 作 `config.yaml` 默认范式的**初值种子**。
  - **运行期启用哪些 / 默认哪个 / 用户自加的范式 = 行为性 = 运行期 `config.yaml`**(`paradigms.enabled` 列表 + `paradigms.default`),`/config` 可改;**用户自定义范式(own-code,装饰器注册)在此登记**,选不出没注册的范式(天花板内收窄,`01 §4`)。
- **范式扩展点 = tools 同款薄注册表(非框架)**:产物 `harness/paradigms/` 持 `register_paradigm` 装饰器 + `dict` 注册表 + `Paradigm` 契约;**新增范式 = 写函数 + 注册 + 配进 `config.yaml`**,与"新增 tool = 加函数 + 注册"完全平行(`01 §4` 已确立的扩展哲学)。**禁**把它做成动态图 / DSL / 运行期抽象引擎(红线)。
- **解耦:每范式自包含**:`agent/plan/ask` 各一份独立编排文件,**互不 import**;改一个绝不波及其他(满足"改 agent 不影响 ask")。共享的只有稳定底层 infra(`llm`/`tools`/`trace`/`context`/`hooks`,本就单一职责模块,`01 §4`);改这些是有意的跨切关注,与范式解耦无关。
- **只读范式靠工具过滤**:plan/ask 的"只读"= 只 offer 非高风险工具(复用 Slice 1 风险标记);属**模型 A 护栏**,非对手级强制(own-code 可改源码,`01 §4`)。

## 1. 交付物

生成器侧(`harnessforge/`):

- `harnessforge/spec.py` — `HarnessSpec` 新增 **`paradigms: list[Literal["agent","plan","ask"]] = ["agent"]`**(选渲染哪些内置范式;校验非空 + 去重;**首项作 `config.yaml` 默认范式初值种子**)。改 schema → `CLAUDE.md §6.1`;字段+运行期配置形态已定稿(§4⑪,集修订见 §4②′)。spec.py 落地时同步 `01 §5` + `00-overview §3`。
- `harnessforge/generator.py` — **始终渲染** `harness/paradigms/` 注册表 + `agent`;`plan`/`ask` 按 `'<p>' in spec.paradigms` **整文件条件渲染**(每范式独立文件,复用 Slice 3 `CONDITIONAL_TEMPLATES`);`config.yaml` 渲染 `paradigms:` 段(`enabled` = 选中集合,`default` = 首项)。
- 多范式 fixture(测试内 `spec.paradigms = ["agent","plan","ask"]`,同 web/mcp 模式)+ 一个**用户自定义范式扩展测试**;`coding-assistant` preset 范式保持默认 `["agent"]`(其 MCP 基线升级见 Slice 6)。

生成产物侧(`harnessforge/templates/`):

- `src/<pkg>/harness/paradigms/`(**始终生成**)— 范式注册表 + 内置范式:
  - `__init__.py` — `Paradigm` 契约(统一签名,沿用 `loop.run` 形:`run(user_input, *, ...) -> RunResult`)+ `register_paradigm(name)` 装饰器 + `PARADIGMS: dict[str, Paradigm]` + `get_paradigm(name)` + 共享 plumbing(`assistant_message`/`run_tool`/`limit_message`);导入内置范式触发注册。**薄注册表,非编排引擎**(红线)。
  - `agent.py`(**始终**)— 现状 `loop.py` 的循环体,注册为 `"agent"`(默认)。全工具(allowlist + 风险);**在线自纠**:工具异常作为 `ERROR:` observation 喂回,模型下一步纠正。
  - `plan.py` / `ask.py`(按 `paradigms` 条件渲染)— **各自完全自包含**编排,互不 import:
    - **plan**:只读规划(对齐 Cursor)——只 offer 非高风险工具,plan 系统提示,**无论输入只产只读计划、不执行/不动手**;Plan→执行的 Build 切换**推迟**(§4⑥,backlog)。
    - **ask**:只读问答——只 offer 非高风险工具,ask 系统提示,不动手。
  - (**reflection 不再作内置范式**;事后自评-重试改作 `AGENTS.md` 的用户扩展范例——包一层 `agent.run` + 用户自备成功信号门控重试,见 §4②′。)
- `src/<pkg>/harness/loop.py` — 收敛为**薄分发入口**:`run(user_input, *, mode=None, config, ...)` → 解析 mode(缺省取 `config.paradigms.default`)→ `get_paradigm(mode)(...)`;`RunResult` 自 `paradigms` 再导出,保持 `from .loop import run, RunResult` 稳定。
- `src/<pkg>/harness/config.py` — 加 `ParadigmsConfig`(运行期:`enabled: list[str]` + `default: str`,`extra="forbid"`,校验 `default in enabled`,缺省 default 取 `enabled[0]`),与 Slice 2 `ContextConfig` 同构;`config.yaml` 渲染对应段。
- `src/<pkg>/interfaces/cli.py` — `run --mode <name>`(默认 `config.paradigms.default`);非法/未启用 mode 抛 `ValueError`、CLI 捕获报错退出 2。
- `src/<pkg>/interfaces/web.py`(若 web 开)— chat 加范式下拉(取 `enabled`,新增 `GET /paradigms`),每条消息带 `mode`,复用既有 SSE;`paradigms` 纳入 `/config` 可编辑。
- `tests/test_harness.py`(+ 范式断言)— 各范式 mock 跑通(agent 默认;plan/ask 只读不触发高风险)+ 非法 mode 报错 + **用户自定义范式扩展测试**(见 §3)。
- `README.md` / `AGENTS.md` — 增"循环范式"专章:范式集、运行期 `--mode`/下拉切换、`config.yaml paradigms:`、**"如何加一个你自己的范式"(写函数 + `@register_paradigm` + 配 enabled,与加 tool 平行)**、agent 在线自纠 + **Reflexion 作扩展范例(需真实成功信号)**、Plan 只读 + Build 推迟、为何是薄注册表而非框架。

## 2. 任务拆解

### 2.1 schema `paradigms` + 运行期配置(§6.1,已定稿 §4⑪;集修订 §4②′)
- 生成期 `HarnessSpec.paradigms: list[Literal["agent","plan","ask"]] = ["agent"]`;校验非空 + 去重(保序);首项种入 `config.yaml paradigms.default`。
- 运行期 `config.py` 新增 `ParadigmsConfig(extra="forbid")`:`enabled: list[str]` + `default: str`,校验 `default in enabled`(缺省取 `enabled[0]`);`Config` 加 `paradigms: ParadigmsConfig`,与 `ContextConfig` 同构。
- `config.yaml` 渲染 `paradigms: {enabled: [<选中范式>], default: <首项>}` + 注释"可加你自己注册的范式名进 enabled"。

### 2.2 范式注册表(始终存在,薄,非抽象层)
- `harness/paradigms/__init__.py`:`Paradigm` 契约 + `register_paradigm` + `PARADIGMS` + `get_paradigm`。**与 tools 注册表同款薄度**;禁动态图/DSL/编排引擎(红线)。`loop.py` 收为分发入口。
- **始终渲染**(连只选 agent)→ 默认产物结构变(§3 不再要求逐字一致)。

### 2.3 内置范式自包含(最大解耦,放宽薄)
- `agent/plan/ask` **各一份独立文件,互不 import**;改一个不波及其他。共享仅稳定 infra(`llm`/`tools`/`trace`/`context`/`hooks`)+ `paradigms/__init__` 的契约/plumbing。允许范式间有重复循环代码——以解耦/可改为先(人已定向)。**单个范式仍保持可通读**(各自 loop 量级);若某范式异常臃肿再停问人。

### 2.4 只读范式(plan/ask)
- 各自 offer 非高风险工具(复用 Slice 1 风险标记,`05-slice-4 §5` 同款闸);plan 出只读计划不执行(Build 推迟);ask 只读问答。Plan/Ask 都只读,区别在提示意图。**模型 A 护栏**(防手滑),非对手级强制(own-code 可改源码,`01 §4`)。

### 2.5 运行期切换 + 清单(both 入口,落 config.yaml)
- `config.yaml paradigms:`(`enabled` + `default`),`/config` 可改;**用户自定义范式(装饰器注册)登记进 `enabled`**。CLI `run --mode`;Web per-message 下拉(取 `enabled`);默认 `config.paradigms.default`;非法/未启用 mode 处理得当。

## 3. 退出门禁(对应 `01 §8` Non-blocker,做到即验;✅ 2026-06-05 全绿回填)

- [x] **多范式渲染可跑**:`paradigms: [agent, plan, ask]` 生成 → `uv sync && pytest` 绿(产物 30 测试)→ mock 跑通每种(agent 工具调用;plan 只读出计划且不触发高风险工具;ask 只读问答)。golden `test_golden_multi_paradigm_*` 覆盖。
- [x] **运行期切换**:CLI `--mode` 三种都跑(本机真实 LiteLLM 验证 agent/plan/ask);Web `/paradigms` + 下拉每条切(`test_web` 覆盖 SSE+mode);默认取 `config.paradigms.default`;非法/未启用 mode 由 `loop.run` 抛 `ValueError`、CLI 捕获报错退出 2(`test_unknown_or_disabled_mode_raises` + 真实 `--mode reflection` 报错验证)。
- [x] **范式可扩展(本片核心门禁)**:`test_custom_paradigm_registers_and_runs_without_touching_builtins` —— 新写 `@register_paradigm("demo")` + 加进 `paradigms.enabled` → `--mode demo` 跑通,**不改任何内置范式文件 / 不改注册表核心**。
- [x] **范式解耦**:`test_paradigm_files_do_not_import_each_other` 断言 agent/plan/ask 互不 import;各自自包含 loop。
- [x] **只读边界**:`test_plan_mode_is_read_only` / `test_ask_mode_is_read_only` —— 高风险工具(`risk="high"`)未被 offer / 未执行;实现为 `registry.active_names(..., allow_high_risk=False)`。
- [x] **注册表始终存在 + 默认行为一致**:agent-only 产物含 `paradigms/`(`__init__`+`agent`)+ `config.yaml paradigms:` 段(`test_paradigm_registry_and_agent_are_always_generated`);golden mock 行为与 Slice 1–4 一致(非逐字)、**无新增运行期依赖**;`pyproject`/`uv.lock`/`requirements.txt` 不含 langchain/langgraph/adk(golden 断言)。
- [x] **薄(放宽后仍守底线)**:单个范式 ≈ 原 loop 量级(agent ~150 行,plan/ask 同形);注册表/分发是薄 `dict`+装饰器 + 写死按名分发,**非动态图/DSL/编排引擎**。
- [x] **黄金路径回归**:`coding-assistant`(范式默认 `["agent"]`)golden + docker + uvx 全绿;结构含范式注册表、行为不变。
- [x] `ReadLints` clean(生成器侧 + 生成产物 `py_compile` 全过)。
- [x] (大改动 §5)全量黄金 + Docker + `uvx` 冒烟全绿(动 `HarnessSpec.paradigms` + 核心 `loop.py` 重塑)。

## 4. 必须人审的决策点(①–⑪ 2026-06-05 已定向/定稿)

- [x] **① 范式多选 + 运行期每轮切(类 Cursor)——人 2026-06-05**:共存 + 每轮选一种;固定/已注册模式集写死按名分发(非抽象层)。
- [x] **② 范式集 = react / plan / ask / reflection——人 2026-06-05**(初版,已被 ②′ 修订)。
- [x] **②′ 范式集修订 = agent / plan / ask——人 2026-06-05(当日,落地后)**。依据:业界调研显示 Cursor/Claude 只暴露 **Agent/Ask/Plan**、无 reflection 用户开关;"单独 ReAct"是底座但不以 ReAct 之名暴露,故 `react`→`agent`。reflection 在产品里(a)被推理模型隐式内化,或(b)**靠真实成功信号(测试/校验/CI)条件触发**的事后重试——无信号自评是公认反模式("别让 agent 给自己打分")。故**删独立 `reflection` 范式与轮数旋钮**:agent 循环已"在线自纠"(工具报错喂回→重试)覆盖常见情形;真正的 Reflexion(验证器门控重试)改作 `AGENTS.md` 用户扩展范例(包 `agent.run` + 用户自备成功信号),守"薄 + 不替用户假设成功信号"。
- [x] **③ Plan/Ask 只读 = 只读/低风险工具、禁 write/shell——人 2026-06-05**;Plan 对齐 Cursor(只产只读计划不动手)。
- [x] **④ 切换入口 = CLI `--mode` + Web 下拉——人 2026-06-05**。
- [x] **⑤ 默认范式 = `paradigms` 首项(种入 `config.yaml`)——人 2026-06-05**。
- [x] **⑥ Plan→执行 Build 切换按钮 = 推迟——人 2026-06-05**(backlog → `00-overview §2` Slice 11+)。
- [x] **⑦ 范式可扩展 = 薄注册表 + 装饰器(同 tools)——人 2026-06-05**:运行期用户可自加范式,写函数 + `@register_paradigm` + 配 `enabled`。
- [x] **⑧ 解耦 = 每范式自包含、互不 import,放宽薄——人 2026-06-05**:改 agent 不影响 ask。
- [x] **⑨ 注册表始终存在(默认 agent 也有)——人 2026-06-05**:默认产物不再与 Slice 1–4 逐字一致,门禁改"行为一致 + 无新增依赖"。
- [x] **⑩ 运行期范式清单进 `config.yaml`(`enabled` + `default`)——人 2026-06-05**。
- [x] **⑪ `HarnessSpec.paradigms` 字段 + 运行期配置 + 注册表结构最终签字(`CLAUDE.md §6.1/§6.8`)——人 2026-06-05 定稿(枚举按 ②′ 落为 `agent/plan/ask`)**:① 生成期 `paradigms: list[Literal["agent","plan","ask"]] = ["agent"]`(非空 + 去重,首项种默认);② 运行期 `config.py` `ParadigmsConfig`(`enabled: list[str]` + `default: str`,`default in enabled`)+ `config.yaml` `paradigms: {enabled, default}`;③ 产物 `harness/paradigms/`(`register_paradigm` + `PARADIGMS` dict + `get_paradigm` + `Paradigm` 契约,签名沿用 `loop.run` 形、返回 `RunResult`),`loop.py` 收为薄分发入口。spec.py 落地时同步 `01 §5`。
- **软确认(非阻塞,`CLAUDE.md §5.3`)**:渲染机制 = 内置范式整文件条件渲染 + 注册表始终渲染;`loop.py` = 薄分发入口、`paradigms/` 持契约与 `RunResult`;事后反思(Reflexion)= 用户扩展范例、需真实成功信号门控(非内置范式);只读 = 排高风险(细粒度只读概念排 v1+)。

## 5. 本 slice 注意

- **可扩展 > 薄(本片基调,人已定向)**:范式注册表 + 自包含范式会使产物比单 `loop.py` 大;这是**有意为扩展/解耦付的代价**(`CLAUDE.md §2` 的薄默认在此让位)。但**单个范式仍须可通读**;若某范式臃肿失控再停问人(`CLAUDE.md §6.8`)。
- **定位红线(最重要,本片有真实张力)**:范式注册表 = **own-your-code 薄扩展点(同 tools 注册表)**,运行期"每轮选范式" = 已注册模式集的**写死按名分发**;**禁**动态图 / DSL / 通用编排框架 / **运行期范式抽象层**(`01 §6`)。supervisor multi-agent 仍 v1+;用户自写 multi-agent 范式属其 own-code,不是 HF 出框架。
- **核心架构改动**:本片重塑 Slice 1 里程碑的 `loop.py`(核心循环 → 范式注册表 + 自包含范式 + 薄分发);属 `CLAUDE.md §6.8/§6.10`,人已定向。默认产物从此**含范式注册表**(重新基线),门禁改"行为一致"。
- **配方 vs 活旋钮**(决策④,`01 §4`):渲染哪些内置范式 + 注册表存在 = 结构性(spec/代码);启用哪些/默认/用户自加范式 = 行为性(运行期 `config.yaml`/`/config`)。产物自持。
- **不绑框架**:范式注册表不引入 agent 编排框架(`01 §1`)。
- **大改动回归**(`CLAUDE.md §5.2`):动 `HarnessSpec` + 核心 `loop.py`,完成前全量黄金 + Docker + `uvx` 冒烟(§3 末条)。

## 6. 实现说明(2026-06-05 落地,与初版计划的偏差就地标注)

- **范式集 = `agent/plan/ask`(§4②′,推翻初版 react/plan/ask/reflection)**:`react`→`agent` 对齐 Cursor/Claude;**reflection 不再是内置范式**,事后自评-重试改作 `AGENTS.md` 用户扩展范例(包 `agent.run` + 用户自备成功信号门控重试)。理由见 §4②′ 与状态区调研结论。agent 循环保留"在线自纠"(工具异常 `ERROR:` 喂回→下一步纠正)。
- **共享 plumbing 落 `paradigms/__init__.py`**:`RunResult` 契约 + `Paradigm` Protocol + `register_paradigm`/`PARADIGMS`/`get_paradigm` + 三个 paradigm-agnostic 小工具(`assistant_message`/`run_tool`/`limit_message`)集中于 `__init__.py`。各内置范式 `from . import ...` 取用,**互不 import**;`loop.py` 仅 `from .paradigms import RunResult, get_paradigm` 并按名分发,`RunResult` 经 `loop` 再导出以保持 `from .loop import run, RunResult` 稳定。这是"稳定 infra 可共享、范式逻辑不共享"的折中(`CLAUDE.md §2` 薄默认在此让位于解耦,人已定向)。
- **`RunResult` 加 `mode` 字段**(默认 `"agent"`):各范式回填自身 `MODE`,CLI 摘要 / Web `final` 事件 / trace `run_start`+`run_end` 均带 mode;为契约的向后兼容增量,旧构造仍可用。
- **只读实现 = `Registry.active_names(..., allow_high_risk=False)`**:对 `tools.py` 的外科式增量(默认 `allow_high_risk=True`,旧调用不变);plan/ask 传 `False` 排除 `risk="high"`。属模型 A 护栏(`01 §4`),非对手级强制。
- **运行期范式清单可经 `/config` 改**:`paradigms` 已纳入 web `_EDITABLE_FIELDS`,与 `enabled`/`default` 运行期可调一致(决策⑩)。
- **非法/未启用 mode = 报错(非回退)**:`loop.run` 抛 `ValueError` 列出 enabled;CLI 捕获打印并退出 2(§4④ 允许"报错或回退",取报错以更透明)。
