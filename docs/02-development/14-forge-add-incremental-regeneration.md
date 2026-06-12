# 14 · `forge add` / 增量再生成 + 模板升级（v1+ 结构性护城河设计）

> 一份面向 **v1+** 的详细设计，不改任何已定全局决策。被判定为**唯一的结构性护城河**：竞品（托管平台 / 你 import 的框架）结构上做不到，因为它们都不交付一份你拥有的代码。
> 口径基准：[`00-overview.md`](./00-overview.md) §4（结构轴 / 行为轴、天花板 / 地板）、§8（路线图，本特性在 v1+，先做 Phase 1 安全子集）。

## 1. 要解决的问题:own-your-code 的「税」

HarnessSmith 的卖点是 own-your-code：产出一份你拥有、可读可删改、生成后不再依赖 HarnessSmith 的仓库。但这份自由有一个固有代价：

> 我生成了一个 CLI-only 的薄 harness，改了 `paradigms/agent.py` 的提示拼装、给 `tools.py` 加了三个自定义工具。两周后我想加 Web 界面 / 开 MCP / 再加一个 `plan` 范式——难道要重新 `harnessmith new` 一遍、把我的编辑全丢掉、再手工搬回去？

这正是 `create-next-app` 生态用 **codemod / `add` 子命令** 解决的问题。目前 HarnessSmith 只有：生成期一次性 `harnessmith new`（全量渲染 + `git init` + `uv lock` + 冒烟自检）+ 重跑保护（到已存在目录警告不覆盖）——这意味着「加能力」目前无路可走，只能手抄。

结论：**own-your-code 越成功（用户越敢改代码），「加能力」的痛越尖锐。** 不解决它，「薄 + 拥有」会在第二次需求到来时反噬体验。

## 2. 为什么这是护城河(竞品结构上学不来)

| 对手形态 | 为什么做不到 `forge add` |
|----------|--------------------------|
| 无代码 / 托管平台 | 你没有代码可被 `add`——能力藏在平台后端，加功能 = 改它的配置，仍是锁定 |
| 你 import 的框架 | 框架的「加能力」= `pip install` 一个包，不改你的循环；没有「把生成的代码增量演进」这件事 |
| 静态脚手架（cookiecutter 类） | 一次性吐模板，没有回头路；改了就回不去，升级 = 重抄 |

**只有「生成你拥有的代码 + 留着 spec 快照」的形态，才能既给你完整的代码所有权、又能在事后安全地增量长出新能力。** 这把 §4 的「结构轴 / 能力天花板」从一次性变成可演进。

## 3. 三种操作,必须精确区分

| 操作 | 语义 | 改什么 | 现状 |
|------|------|--------|------|
| **`add`** | 结构轴新增一段缺席的能力代码（web / mcp / skills / 一个内置范式） | 新增文件 + 受控插入扩展点 + 回写 `harness.spec.yaml` + 重跑 `uv lock` | 未做（本文主体） |
| **`upgrade`** | 把产物的模板版本演进到新生成器版本（bugfix / 新默认） | 对已生成文件做 codemod / 3-way merge，靠 `harness.spec.yaml` 的 `version` 定位基线 | 未做（最难，Phase 3） |
| **`regenerate`** | 用（可能改过的）spec 重生成整仓 | 全量覆盖 | 仅有「重跑警告不覆盖」；安全的整仓覆盖未做 |

本文聚焦 **`add`**（价值最高、最可分阶段），`upgrade` 给出方向但承认是深水区。

## 4. 关键使能件:产物自带的 `harness.spec.yaml`

`harnessmith new` 已把完整 spec 快照拷进产物根（`harness.spec.yaml`）。这是 `forge add` 的支点：

```
forge add web 的本质 =
  读 product/harness.spec.yaml          # 当前结构状态
  → 校验 + 变更（interfaces.web = true） # 结构轴新增
  → 只渲染该变更引入的「缺席」文件         # 增量,不碰已有
  → 回写 harness.spec.yaml + uv lock      # 状态自洽
  → git diff 让用户审阅                   # 可预测
```

因为 spec 快照在、且 spec 是声明式的，`forge add` = 「把声明从 A 改成 A+web，并补齐 A→A+web 的代码增量」。

> **不破「生成后不再依赖 HarnessSmith」**：产物**运行期**永远不 import `harnessmith`。`forge add` 是**可选的开发期便利**（你再次主动调用生成器作用在你的仓库上，等同 codemod 工具），不是运行期依赖。不用它产物照跑。

## 5. 核心难点:把代码生成进「用户已编辑过的仓库」

整仓一次性渲染是干净的；增量渲染进可能被编辑过的文件才是真问题。三条要守：

1. **幂等**：`forge add web` 跑两次 = 跑一次的状态（不重复插入、不二次破坏）。
2. **不毁编辑**：绝不静默覆盖用户改过的文件；冲突要么自动安全合并、要么停下让用户裁决。
3. **可预测**：每次 `add` 必须能 `--dry-run` 看清将改哪些文件、并以 `git diff` 形式落地（要求 clean working tree 或显式 `--force`）。

**扩展点（注册表）就是天然的「缝」。** 产物可扩展处都是注册表 + 装饰器：`tools`（`@tool`）、`paradigms`（`@register_paradigm`）、`context`（`@register_strategy`/`@register_condition`）。新增项多数只是新增一个文件——但要让它「被发现」，当前实现需要一行 import（如 `paradigms/__init__.py` 的内置范式 import 块是 Jinja 条件块）。这把 `add` 分成两档难度：

- **A. 纯新增、零改已有文件**：能力的「接线」发生在运行期 `config.yaml`。例：开一个 MCP server（写 `config.yaml mcp.servers`）、加一个 skill 目录、加一个工具进 `tools.enabled`。这些今天就能安全做。
- **B. 需受控插入到代码扩展点**：能力要落新代码文件 + 一行接线（新范式文件 + `__init__` import；开 web 要新增 `interfaces/web.py` 且 `pyproject` 加依赖）。需要「锚点插入」或改造发现机制。

> **设计岔路**：若把范式注册表从「显式 import」改成「扫描目录自动发现」，则 `forge add paradigm` / 用户自加范式都退化成纯新增一个文件（A 档）。代价是牺牲一点「显式即薄」的可读性。建议：仅对范式这一个高频扩展点评估自动发现，其余维持显式。见 §8 未决项②。

## 6. 分阶段落地(薄优先、风险递增)

### Phase 0 — 已有
`new` 全量渲染 + 重跑警告不覆盖。`forge add` 站在它之上。

### Phase 1 — 安全子集:纯新增 + 运行期接线(A 档,先做)
只做「不碰任何已有代码文件」的 add：
- **运行期能力**：`forge add mcp-server <name>`（写 `config.yaml`，复用 catalog 预填逻辑）、`forge add skill <name>`（新建 `skills/<name>/SKILL.md`）、把工具加进 `tools.enabled`。零代码改动、最低风险。
- **前置条件**：要求 git working tree clean（或 `--force`）；先 `--dry-run` 打印将改文件；变更后回写 `harness.spec.yaml`（若涉及结构）+ 重跑 `uv lock`（若涉及依赖）+ 冒烟自检。
- **价值**：覆盖「事后接一个数据源 / 加一个技能」的高频诉求，且实现简单（写文件 + 校验）。

### Phase 2 — 受控插入到扩展点(B 档)
做「新增文件 + 一处接线」的 add：`forge add web`、`forge add mcp`、`forge add paradigm plan`、`forge add skills`。两种插入机制（可并用）：
1. **结构化插入**：spec 改 flag → 只渲染那些条件命中的「缺席文件」+ 改 `pyproject.toml` 的 optional-dependencies（结构化编辑 TOML，不做正则）。生成器已有「按 spec 条件渲染文件」机制，`add` 复用它、只渲染 delta。
2. **锚点标记插入**：对必须改的少量「接线点」放显式锚点注释（如 `# >>> harnessmith:paradigm-imports`），`add` 只在锚点间幂等插入。用户没动锚点 → 干净插入；动了 → 停下提示手工接线。
- **冲突策略**：能 `git apply` 的补丁就 apply；冲突就留给用户（写出 `.rej` 或在 diff 里标冲突），绝不静默覆盖。
- **每步收尾**：回写 spec + `uv lock` + 冒烟自检 + 打印 `git diff --stat`。

### Phase 3 — 模板升级 `upgrade`(深水区,最后)
把已生成产物升到新生成器版本，靠三方合并：基线 = 用旧版生成器 + 产物的 `harness.spec.yaml` 重新渲染得到的「原始产物」；三方 = (基线, 新版渲染, 用户当前文件) → 标准 3-way merge。干净 hunk 自动并；冲突落 `git` 冲突标记交用户。**诚实**：3-way merge 进被深改的核心循环必然有冲突；`upgrade` 只承诺「把能自动并的并掉、其余清晰标出」，不是「无痛升级」。优先保证 Phase 1/2，`upgrade` 可长期停在「仅升级未被用户改过的文件 + 其余报告差异」的弱版本。

## 7. 命令面草图（实现前细化）

```bash
harnessmith add web                 # 开产物 Web 接口（新增 interfaces/web.py + 依赖）
harnessmith add mcp                 # 开 MCP 能力（新增 harness/mcp.py + mcp 依赖）
harnessmith add mcp-server fetch    # Phase 1：往 config.yaml 预填一个 catalog server
harnessmith add paradigm plan       # 增一个内置范式（新增文件 + 受控接线）
harnessmith add skill my-skill      # Phase 1：新建 skills/my-skill/SKILL.md
harnessmith upgrade                 # Phase 3：模板版本演进（3-way merge）

# 通用旗标
  --dry-run        # 只打印将改哪些文件 / diff，不落地（强制可预览）
  --force          # 允许在 dirty working tree 上操作（默认要求 clean）
  -C <path>        # 目标产物目录（默认 cwd）
```

约束：所有 `add`/`upgrade` 都 ① 在产物目录里、读其 `harness.spec.yaml`；② 默认要求 git clean、变更以 commit-able diff 落地；③ 收尾跑冒烟自检（沿用 `new` 的 `--no-verify` 旗标）；④ 失败给可读错误 + 回滚到操作前（git）。

## 8. 落地前需细化的设计点

1. **范围与排期**：先只做 **Phase 1 安全子集**（低风险、覆盖高频诉求）验证价值，再决定 Phase 2/3。
2. **范式发现机制**：是否把 `paradigms/` 由「显式 import」改为「目录自动发现」以让 `forge add paradigm` 纯新增？（牺牲一点显式可读性，换增量友好）
3. **`add` 是否允许改 `pyproject.toml`**：开 web/mcp 要加 optional-deps——走结构化 TOML 编辑（非正则）、且只动 `[project.optional-dependencies]`。
4. **clean-tree 前置**：默认要求 git working tree clean、否则拒绝（`--force` 跳过）。
5. **`upgrade` 的承诺边界**：明确对外只承诺「自动并可并的、清晰标冲突」，不承诺无痛升级。

## 9. 红线复核（对照 §10）

- **不让产物运行期依赖 HarnessSmith**：`forge add` 是开发期可选 codemod，产物运行不 import `harnessmith`；不用它产物照跑（§4 已讲死）。
- **不做中心化配置/托管**：`forge add` 在用户本机作用于本地仓库，不联网、不回传、无中心服务。
- **不引 agent 框架 / 不加运行期依赖到默认产物**：`add` 只渲染既有模板的 delta，依赖仍由 spec 开关决定。
- **不做在线 MCP registry**：`add mcp-server` 只从本地静态 catalog 预填，不联网拉 registry。
- **密钥不入 git/spec/trace**：`add` 写的是结构（代码 / `config.yaml` 的 env 名 / spec），绝不写 key 值。

## 10. 风险与未决

- **3-way merge 进深改核心循环**：本特性最硬的部分；缓解 = Phase 化、先 Phase 1、`upgrade` 给弱承诺。
- **锚点注释污染「薄/可读」卖点**：锚点要少而克制（只在真正需要接线的极少数文件）。
- **spec 快照与用户手改 `config.yaml` 漂移**：`add` 以 spec 为结构真相，但用户可能直接改了 `config.yaml`（行为轴）；`add` 只动结构、不覆盖行为值，合并 `config.yaml` 时只增不改已有键。
- **测试成本**：每个 `add <capability>` 都要有「生成 base → add → `uv sync && pytest` 绿 → 幂等重跑无变化」的黄金测试（`CLAUDE.md §5.1` 门槛对 `add` 同样适用）。

> 一句话：`forge add` 把 own-your-code 从「一次性吐代码」升级成「可增量演进的代码所有权」，是 HarnessSmith 区别于托管平台与框架的**结构性**优势。建议从 Phase 1 安全子集起步验证。
