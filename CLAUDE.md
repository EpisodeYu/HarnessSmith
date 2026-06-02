# CLAUDE.md — HarnessForge 项目守则

> Agent 进入本项目（**vibe coding 模式**）入场必读。本文件是 Agent 工作的**硬约束**。
> 项目定位 / 范围 / 决策以 `docs/01-project-plan.md` 为准；开发节奏与切片门禁见 `docs/02-development/00-overview.md`。
>
> **Tradeoff**：偏向"先把事情做对"。显然小到不值得讨论的操作自己判断,别让流程把简单任务搞复杂。

## 0. 协作模式与角色边界

本项目**主要由 Agent 开发**,人只负责决策、验证、以及"只能人做"的环境配置。

| 角色 | 负责 | 不做 |
|------|------|------|
| **Agent(你)** | 写生成器与模板代码、写/跑测试、调试、维护文档与变更记录、按 slice 自驱推进、提交 PR、写完成报告 | 不替人拍板产品决策、不动用钱/联网批量/破坏定位的事、不直接 push `main` |
| **人** | 方向与验收、slice 关键决策点签字、**环境与密钥配置(见 §0.1)**、合并 PR、对外发布 | 不写代码、不做 Agent 已能自动化的事 |

**一句话**:Agent 负责"怎么做",人负责"做不做、装环境、给 key、何时发布"。
开发文档里写"开发者要做 X"一律理解为"**你(Agent)要做 X**,由人按切片节奏验收"。

### 0.1 只能由人配置的环境(Agent 不代劳)

- 安装本机工具链:`uv`、`docker`(Agent 不改系统级配置、不装系统包)。
- **API key / `.env` 真实值**:Agent 只维护 `.env.example`,**绝不写入真实 `.env`、绝不把 key 写进任何被 git 跟踪的文件**。日常开发用 **mock LLM**,不需要真 key;只有"真实 LLM 冒烟 / 对外演示"才需要人提供 key。
- PyPI 发布凭证、GitHub 仓库设置、合并 PR、push `main`。

> Agent 需要某个 key / 环境时:在 plan 阶段列出所需 `.env` key 名与用途,**停下来请人配置**,不要自己编造或跳过。

## 1. Think Before Coding

**不要假设。不要藏起困惑。把权衡显式说出来。** 动手前:声明假设,不确定就问;多种合理解读时列出来让人选;有更简单的方案先说一声。宁可开工前多问 1 个问题,不要跑了 30 分钟才发现方向错了。

## 2. Thin First(薄优先 —— 本项目核心卖点,硬约束)

- 默认产物模板保持**极薄**:核心循环目标 150–300 行,整体远小于一个框架。
- 不做没要求的功能;一次性代码不先抽象;不为"以后可能要"加灵活性。
- 高级能力(RAG / MCP / context 策略 / Web)只通过 **spec 开关**生成,不塞进默认产物。
- 200 行能压到 50 行就重写。

## 3. Surgical Changes

只动该动的,只清理自己制造的烂摊子。不"顺手优化"无关代码或格式;不重构没坏的东西;沿用现有风格;发现 dead code **提一句**,别擅自删。

## 4. 两层心智:生成器 vs 生成产物(本项目特有)

你写的是一个**生成器**,它渲染出**独立的生成产物仓库**。任何时候分清你在改哪一层:

- 改 `harnessforge/`(生成器本体):spec / 渲染引擎 / CLI / 向导 / catalog / presets。
- 改 `harnessforge/templates/`(产物模板):渲染后才是用户拿到的代码。
- **测试必须覆盖"生成产物"本身**:生成 → `uv sync` → `pytest` → mock LLM 跑通一次工具调用,而不只是测生成器。

## 5. 目标驱动 + 测试硬门槛(按生成器项目定制)

"完成"的硬门槛见 §5.1,没达到 = 没完成,别用"逻辑简单不用测"或"先合后补"做借口。
例外:纯文档 / 纯注释 / 纯重命名(改名工具已覆盖全部引用)可不加测试,但要在完成报告里点名说明。

### 5.1 黄金测试是"完成"的硬门槛

任何被宣称完成的功能必须:

- 新增 / 改动的生成器或模板代码**有自动化测试**(unit 或 integration)。
- **黄金路径绿**:用示例 / preset spec 生成项目 → `uv sync && pytest` 全绿 → mock LLM 跑通一次 function-calling(含一次工具调用)。
- 断言生成的 `pyproject.toml` **不含 `langchain`/`langgraph`/`adk`**。
- **可运行性自检绿**:生成后冒烟(`uv sync` + import + mock 跑一步 + `pytest -q`)。
- `ReadLints`(IDE 诊断)无新增 error / warning。

### 5.2 "大改动"额外跑回归

判定:动了 `HarnessSpec`、模板核心,或跨 ≥ 3 个文件。额外跑:

- 全量黄金快照(示例 spec + 每个 preset 各生成并 `pytest`)。
- **Docker 冒烟**:生成产物 `docker build` 成功 + `docker run` 跑通 mock 一步。
- `uvx harnessforge new` 冒烟。

任一项失败 → 该功能**未完成**,先修,不要急着开下一项。

### 5.3 可自主决定(不必请示)

命名;实现细节 / 内部数据结构 / stdlib 选择;已在文档区间内的参数(默认 context 策略、预算默认值等);fixture / mock 风格 / 测试组织;在 `pyproject.toml` 已列家族内加可选依赖(如 `pytest-*`)。执行后在完成报告里一句话提一下。

## 6. 停下来问人 / 上报的触发条件(命中任一即停)

1. 改 `HarnessSpec` schema 字段或其语义(影响生成器与所有模板)。
2. 给**默认产物模板**新增运行期依赖,或把 L2/L3 依赖混进默认核心依赖(违反"薄")。
3. 在生成产物里引入任何 **agent 编排框架**(LangChain/LangGraph/ADK…)——**定位红线,绝不允许**。
4. 改 LLM API 面(Chat Completions ↔ Responses)或底座 SDK 选型。
5. 任何可能让**密钥进入 git / spec 快照 / trace / 日志**的路径。
6. 跨 slice 的范围调整:把 L3 提前进 MVP,或把 L1 推迟。
7. 需要真实 key / 联网 / 花钱:真实 LLM 跑批、发布到 PyPI、对外网开放端口。
8. 生成产物核心代码体积明显超"薄"目标(核心循环远超 300 行)。
9. 同一问题连续两次尝试都失败——别进"再试一遍"循环,停下说清卡点。
10. 多种合理实现且权衡不清,影响 ≥ 2 个模块 / 后续 slice。

上报格式:**[需要人介入]** + 触发第几条 / 在做什么 / 卡在哪 / 已试过什么(尝试 1·2 及结果)/ 可选项 A·B 及代价 / 我的倾向。等回复再继续。

## 7. Agent 标准工作循环:plan → implement → self-verify → handoff

- **plan**:读相关 slice 文档顶部"交付物";复述理解 + 实现计划(≤ 10 行);列会改的文件、新增测试、所需 `.env` key 名;命中 §6 就在 plan 阶段先停。
- **implement**:先用 Read/Grep/SemanticSearch 看现有代码沿用风格;小步走能 commit 就 commit;不碰无关代码。
- **self-verify**:跑 §5.1(大改动加 §5.2);自查 §1–§4 没违反;fail 先修不要假装看不见。
- **handoff**:按 `docs/02-development/00-overview.md §完成报告模板` 输出报告;Conventional Commits 提交。

## 8. 提交与分支

- **Conventional Commits**:`feat: / fix: / refactor: / docs: / chore: / test: / perf: / build: / ci:`。
- 一个 commit 一件事,不捎带无关改动。
- `main` 受保护;功能走 feature branch + PR;Agent **不直接 push `main`、不 `--force`、不跳 pre-commit hook**(除非人明确允许)。

## 9. 文档维护

- 改 `HarnessSpec` 字段:同步 `01-project-plan.md §5` + 相关 slice 文档。
- 改全局决策(罕见,走 §6 人审):必须改 `docs/02-development/00-overview.md` 的决策总表。
- 改 `.env.example` / 默认依赖:同步产物 README / AGENTS.md 与相关 slice 文档。
- 文档与代码相互引用的地方,**改一处必检另一处**。Agent 是这套文档体系的唯一维护者。

## 10. 语言与文风

- 人机对话默认中文;代码注释 / commit / 文档正文沿用各文件原有语言,勿强行翻译。
- 不写"// 自增计数器"这类废话注释;不在文档里写"我 / 我们"或 LLM 客套话。

## 11. 入场顺序(Agent 第一次进入本项目时)

1. 读 `README.md` 速览定位。
2. 读本文件(`CLAUDE.md`)—— 你正在读。
3. 读 `docs/01-project-plan.md`(定位 / 范围 / 关键决策)。
4. 读 `docs/02-development/00-overview.md`(当前 slice 与完成门禁)。
5. 按当前任务**只读**相关 slice 子文档;不要把全部文档塞进上下文。
