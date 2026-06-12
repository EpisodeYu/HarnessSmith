# 02·075 - Slice 6B:全局 rule(always-apply 项目规则注入)

> 目标:让产物支持**全局 rule 文件注入**——把开放标准的 `AGENTS.md` / `CLAUDE.md` / `.cursor/rules` 模式落到产物里:`config.yaml` 的 `prompts.rules_files` 列出若干 markdown 文件,其正文被注入**每一轮**系统提示。与 Slice 6 的标准 SKILL 同源(都是「文件 → 提示注入」),但 **rule 是常驻**(每轮都在),SKILL 是**按需**(相关才加载)。
>
> 紧接 Slice 6、在 wizard(Slice 7)之前的薄增量(文件 `075-` 排在 Slice 6 与 Slice 7 之间)。
>
> **薄/红线**:零新增依赖(只读文件 + 拼字符串);纯运行期行为(`config.yaml` 活旋钮),`spec.prompts.rules_files` 仅作初值种子;非框架、非 DSL。

## 0. 边界与口径

- **rule vs SKILL**:rule = 常驻(每轮注入全文,适合「始终遵守」的项目约定);SKILL = 按需(只注入 name+description,相关时才 `read_skill` 读正文)。两者互补,机制同源。
- **配方 vs 活旋钮**(`00-overview.md` §3):`prompts.rules_files` 是运行期权威(`config.yaml` 可随时增删文件,不重生成);`spec.prompts.rules_files` 只是生成期种子。
- **天花板 vs 地板**:rule 是 prompt 文本注入(行为轴),非安全边界;护栏仍靠 tool allowlist + 风险标记(结构轴)。
- **缺文件即跳过**:列了但文件不存在 → 静默跳过(不报错),所以「先配后写」或共享他工具的规则文件都安全。

## 1. 交付物

- `harnessmith/spec.py` — `Prompts` 新增 `rules_files: list[str] = []`(生成期种子)。
- 产物 `harness/config.py` — `PromptsConfig` 新增 `rules_files`(运行期旋钮)。
- 产物 `harness/prompts.py` — 新增 `_load_rules(config)`:按 `prompts.rules_files` 顺序读 markdown、拼成 "Project rules (always follow):" 段,插在 system 之后、skills/environment 之前;**始终生成**(空列表 = 零效果)。
- 产物 `config.yaml` — 渲染 `prompts.rules_files`(seed 自 spec)+ 注释说明。
- `harnessmith/templates/RULES.md.j2` — starter 规则文件,**仅当 `"RULES.md" in spec.prompts.rules_files` 时生成**,否则产物零 rule 文件痕迹。
- `coding-assistant` preset — seed `prompts.rules_files: [RULES.md]`(旗舰 preset 开箱演示)。
- 测试 + 文档(本片 + 产物 `AGENTS.md`/`README` + `00-overview.md`)。

## 2. 任务拆解

1. spec/config 双侧加 `rules_files` 字段(同名,1:1 渲染)。
2. `prompts.py` 加 `_load_rules` 并接入 `build_system_prompt`(无条件、空即 no-op)。
3. `config.yaml.j2` 渲染旋钮 + 注释;`RULES.md.j2` 条件渲染;coding-assistant seed。
4. 测试(生成器快测 + 产物自带）+ golden/docker 回归。

## 3. 退出门禁

- 黄金路径:coding-assistant(seed rules)生成 → `uv sync && pytest`(产物自带 rule 注入测试绿)→ mock 跑通一次工具调用。
- rule 注入生效:`build_system_prompt` 含规则文件正文;缺文件静默跳过。
- 薄/零痕迹:thin example(无 rules)不落 `RULES.md`、`config.yaml` 仅 `rules_files: []`;无新增依赖。
- 种子进快照:seed 的 `rules_files` 作配方落 `harness.spec.yaml`(只含文件名,无密钥)。
- 大改动回归(动 `HarnessSpec` + 跨 ≥3 文件):golden 全量 + Docker build/run mock。
- `ReadLints` clean。

## 4. 关键决策

- **① 做薄版全局 rule、排为小 slice**(对位 Claude Code/Cursor rule;配置级 shell hook 仅记 v1+ backlog)。
- **② spec 面加 `prompts.rules_files` 初值种子**(让 preset/wizard 可播种;触发 `CLAUDE.md §6` 改 `HarnessSpec`)。
- **软确认**:字段名 spec/config 同取 `rules_files`(1:1 映射);starter 文件名 `RULES.md` 且仅 seed 时生成;注入位置在 system 之后、skills 之前;段首固定 "Project rules (always follow):"。

## 5. 本 slice 注意 / 留给后续

- **基座 `system` 默认**:rule 文件拼在 `system` 之后,`prompts.system` 的缺省值是一版薄通用 agent 基座(对标 Claude Code/Codex/Cursor/opencode 的共性准则:agent 身份 + 用工具别瞎猜 + 诚实不编造 + 简洁少 emoji + 最小改动 + 规则文件优先)。单一文本同源于 `scaffold.DEFAULT_SYSTEM_PROMPT` / 产物 `harness/prompts.py` 的 `_DEFAULT_SYSTEM`(逐字一致),并以 YAML 字面块烤进 `config.yaml`(可见可改)。
- **CLAUDE.md 约定自动识别**:`_load_rules` 在显式 `rules_files` 之外,**自动发现根目录 `CLAUDE.md`** 并注入(去重、缺失跳过),`_CONVENTION_RULE_FILES = ("CLAUDE.md",)`。**`AGENTS.md` 故意排除**:产物里它是「如何扩展本 harness」的开发者指南(~400 行),不是运行期 rule;要注入须显式列进 `rules_files`。
- **wizard(Slice 7)需覆盖 `prompts.rules_files`**。
- **配置级 shell hook(Claude Code/Cursor 风格,事件→shell 命令、可 veto)= v1+ backlog**:代码级 `Hooks` 已覆盖同等能力,且与 Slice 10 HITL 确认 hook 重叠、引入「配置跑任意 shell」新安全面,故缓做。
- **不做**:rule 的 glob / 描述触发 auto-attach(Cursor 进阶特性)——只做「always-apply 文件列表」薄版;按需触发交给 SKILL(Slice 6)。
- **后续(Slice 3)**:产物 Web 的 Prompts 标签把 `rules_files` 从「路径清单 textarea」改为每文件可编辑正文,机制不变(详见 [`04-slice-3-product-web.md`](./04-slice-3-product-web.md) §2.5）。
