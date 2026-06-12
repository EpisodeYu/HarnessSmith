# 02·06 - Slice 5:多范式 + 范式注册表/扩展

> 目标:① **多范式**——生成期**多选**循环范式(**Agent/Plan/Ask**,对齐 Cursor 三件套),渲染出**共存**的薄循环,产物**运行期每轮可切一种**(CLI `--mode` + Web 下拉);② **范式可扩展(本片核心卖点)**——产物运行期**允许用户自加范式**:与 tools 同款的**薄注册表 + 装饰器**(`@register_paradigm`),写个函数 + 注册 + 配进 `config.yaml` 即生效。
>
> 前置:Slice 4 门禁全绿。
>
> 命中 `CLAUDE.md §6.1`(新增 `paradigms` 字段)与 §6.8/§6.10(重塑核心 `loop.py` 为范式注册表)。**默认产物不再与 Slice 1–4 逐字一致**:范式注册表始终存在(即便只选 agent),门禁改为「行为一致(golden mock 路径不变)+ 无新增依赖」——**扩展性 / 解耦优先于薄**。

## 0. 边界与口径

- **可扩展 > 薄(本片基调)**:范式是产物核心卖点「高度可扩展 + own-your-code」的主战场。当「薄」与「用户能否自由改/加范式」冲突时,**优先扩展与解耦**(`CLAUDE.md §2` 的薄默认在此让位)。但单个范式仍应可通读(各自 loop 量级)。
- **范式集 = `agent/plan/ask`**:`agent` = ReAct 式 tool-calling 循环(默认)。**不做独立 `reflection` 范式**——业界(Cursor/Claude)只暴露 Agent/Ask/Plan、无 reflection 用户开关;agent 循环已「在线自纠」(工具报错喂回→重试),真正的 Reflexion(验证器门控重试)需用户自备成功信号,作 `AGENTS.md` 用户扩展范例(守「薄 + 不替用户假设成功信号」)。
- **生成期 vs 运行期**(`00-overview.md` §3/§4):
  - 渲染哪些内置范式 + 注册表是否存在 = 结构性 = 生成期(`spec.paradigms`;**注册表始终渲染**)。`spec.paradigms[0]` 作 `config.yaml` 默认范式初值种子。
  - 运行期启用哪些 / 默认哪个 / 用户自加的范式 = 行为性 = 运行期 `config.yaml`(`paradigms.enabled` + `paradigms.default`),`/config` 可改;选不出没注册的范式(天花板内收窄)。
- **范式扩展点 = tools 同款薄注册表(非框架)**:`harness/paradigms/` 持 `register_paradigm` 装饰器 + `dict` 注册表 + `Paradigm` 契约;新增范式 = 写函数 + 注册 + 配进 `config.yaml`。**禁**动态图 / DSL / 运行期抽象引擎(红线)。
- **解耦:每范式自包含**:`agent/plan/ask` 各一份独立编排文件,**互不 import**;改一个绝不波及其他。共享的只有稳定底层 infra(`llm`/`tools`/`trace`/`context`/`hooks` + `paradigms/__init__` 的契约/plumbing)。
- **只读范式靠工具过滤 + 执行期拒绝**:plan/ask 的「只读」= offer 期只 offer 非高风险工具(`active_names(..., allow_high_risk=False)`)+ **执行期拒绝集合外调用**(`run_tool(..., allowed=set(active))`,模型即便 hallucinate 一个未 offer 的 high 工具也不会被执行,返回 ERROR observation 供自纠)。属**模型 A 护栏**,非对手级强制(own-code 可改源码)。

## 1. 交付物

生成器侧:

- `spec.py` — `HarnessSpec` 新增 **`paradigms: list[Literal["agent","plan","ask"]] = ["agent"]`**(选渲染哪些内置范式;校验非空 + 去重保序;首项作 `config.yaml` 默认范式初值种子)。
- `generator.py` — **始终渲染** `harness/paradigms/` 注册表 + `agent`;`plan`/`ask` 按 `'<p>' in spec.paradigms` 整文件条件渲染;`config.yaml` 渲染 `paradigms:` 段(`enabled` = 选中集合,`default` = 首项)。
- 多范式 fixture + 一个用户自定义范式扩展测试;`coding-assistant` preset 范式保持默认 `["agent"]`。

生成产物侧:

- `harness/paradigms/`(**始终生成**):
  - `__init__.py` — `Paradigm` 契约(签名沿用 `loop.run` 形,返回 `RunResult`)+ `register_paradigm(name)` 装饰器 + `PARADIGMS: dict` + `get_paradigm(name)` + 共享 plumbing(`assistant_message`/`run_tool`/`limit_message`/`final_assistant_message`)。薄注册表,非编排引擎。
  - `agent.py`(始终)— 现状循环体,注册为 `"agent"`(默认)。全工具;在线自纠(工具异常作为 `ERROR:` observation 喂回)。
  - `plan.py` / `ask.py`(条件渲染)— 各自完全自包含、互不 import:plan = 只读规划(只产只读计划、不执行,Build 切换推迟);ask = 只读问答。
- `harness/loop.py` — 收敛为**薄分发入口**:`run(user_input, *, mode=None, config, ...)` → 解析 mode(缺省取 `config.paradigms.default`)→ `get_paradigm(mode)(...)`;`RunResult` 自 `paradigms` 再导出,保持 `from .loop import run, RunResult` 稳定。
- `harness/config.py` — `ParadigmsConfig`(`enabled: list[str]` + `default: str`,`extra="forbid"`,校验 `default in enabled`,缺省取 `enabled[0]`)+ `config.yaml` 对应段。
- `interfaces/cli.py` — `run --mode <name>`(默认 `config.paradigms.default`);非法/未启用 mode 抛 `ValueError`、CLI 捕获报错退出 2。
- `interfaces/web.py`(若 web 开)— chat 加范式下拉(取 `enabled`,`GET /paradigms`),每条消息带 `mode`;`paradigms` 纳入 `/config` 可编辑。
- `tests/test_harness.py` + `README.md` / `AGENTS.md`(「循环范式」专章:范式集、运行期切换、`config.yaml paradigms:`、如何加自己的范式、agent 在线自纠 + Reflexion 作扩展范例、Plan 只读 + Build 推迟、为何是薄注册表而非框架)。

## 2. 实现要点

- **共享 plumbing 落 `paradigms/__init__.py`**:`RunResult` 契约 + `Paradigm` Protocol + `register_paradigm`/`PARADIGMS`/`get_paradigm` + paradigm-agnostic 小工具集中于此。各内置范式 `from . import ...` 取用,**互不 import**;`loop.py` 仅按名分发。
- **`RunResult` 带 `mode` 字段**:各范式回填自身 `MODE`,CLI 摘要 / Web `final` 事件 / trace 均带 mode。
- **只读实现 = 双层**:offer 期 `active_names(..., allow_high_risk=False)`(对 `tools.py` 外科式增量,默认 `allow_high_risk=True`,旧调用不变)+ 执行期 `run_tool(..., allowed=set(active))` 拒绝集合外调用。属模型 A 护栏。
- **非法/未启用 mode = 报错(非回退)**:`loop.run` 抛 `ValueError` 列出 enabled;CLI 捕获打印并退出 2(更透明)。

## 3. 退出门禁

- 多范式渲染可跑:`paradigms: [agent, plan, ask]` 生成 → `uv sync && pytest` 绿 → mock 跑通每种(agent 工具调用;plan 只读出计划且不触发高风险;ask 只读问答)。
- 运行期切换:CLI `--mode` 三种 + Web `/paradigms` + 下拉每条切;默认取 `config.paradigms.default`;非法/未启用 mode 报错退出 2。
- 范式可扩展(本片核心门禁):新写 `@register_paradigm("demo")` + 加进 `paradigms.enabled` → `--mode demo` 跑通,**不改任何内置范式文件 / 不改注册表核心**。
- 范式解耦:断言 agent/plan/ask 互不 import。
- 只读边界:高风险工具未被 offer **且执行期拒绝集合外调用**(模型 hallucinate 未 offer 的 high 工具也不会被执行)。
- 注册表始终存在 + 默认行为一致:agent-only 产物含 `paradigms/`(`__init__`+`agent`)+ `config.yaml paradigms:` 段;golden mock 行为与 Slice 1–4 一致(非逐字)、无新增运行期依赖。
- 黄金路径回归 + 大改动回归(动 `HarnessSpec.paradigms` + 核心 `loop.py`):全量黄金 + Docker + `uvx` 冒烟全绿。
- `ReadLints` clean。

## 4. 关键决策

- **① 范式多选 + 运行期每轮切(类 Cursor)**:共存 + 每轮选一种;固定/已注册模式集写死按名分发(非抽象层)。
- **② 范式集 = agent / plan / ask**:`react`→`agent` 对齐主流命名;删独立 `reflection`(agent 已在线自纠;Reflexion 作 `AGENTS.md` 用户扩展范例,需真实成功信号)。
- **③ Plan/Ask 只读 = 只读/低风险工具、禁 write/shell**;Plan 对齐 Cursor(只产只读计划不动手)。
- **④ 切换入口 = CLI `--mode` + Web 下拉**。
- **⑤ 默认范式 = `paradigms` 首项(种入 `config.yaml`)**;Plan→执行 Build 切换推迟(v1+)。
- **⑦ 范式可扩展 = 薄注册表 + 装饰器(同 tools)**:运行期用户可自加范式。
- **⑧ 解耦 = 每范式自包含、互不 import,放宽薄**:改 agent 不影响 ask。
- **⑨ 注册表始终存在**:默认产物不再与 Slice 1–4 逐字一致,门禁改「行为一致 + 无新增依赖」。
- **⑩ 运行期范式清单进 `config.yaml`(`enabled` + `default`)**;`paradigms` 纳入 web `_EDITABLE_FIELDS`。

## 5. 本 slice 注意

- **可扩展 > 薄(本片基调)**:范式注册表 + 自包含范式会使产物比单 `loop.py` 大;这是有意为扩展/解耦付的代价。但单个范式仍须可通读。
- **定位红线(本片有真实张力)**:范式注册表 = own-your-code 薄扩展点(同 tools 注册表),运行期「每轮选范式」= 已注册模式集的**写死按名分发**;**禁**动态图 / DSL / 通用编排框架 / 运行期范式抽象层(`00-overview.md` §10)。supervisor multi-agent 仍 v1+;用户自写 multi-agent 范式属其 own-code。
- **核心架构改动**:本片重塑 Slice 1 里程碑的 `loop.py`(核心循环 → 范式注册表 + 自包含范式 + 薄分发);属 `CLAUDE.md §6.8/§6.10`。默认产物从此含范式注册表(重新基线)。
- **不绑框架**;**大改动回归**(动 `HarnessSpec` + 核心 `loop.py`,完成前全量黄金 + Docker + `uvx` 冒烟)。
