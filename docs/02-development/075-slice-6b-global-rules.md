# 02·075 - Slice 6B:全局 rule(always-apply 项目规则注入)

> 目标:让产物支持**全局 rule 文件注入**——把开放标准的 `AGENTS.md` / `CLAUDE.md` / `.cursor/rules` 模式落到产物里:`config.yaml` 的 `prompts.rules_files` 列出若干 markdown 文件,其正文被注入**每一轮**系统提示。与 Slice 6 的标准 SKILL 同源(都是"文件 → 提示注入"),但 **rule 是常驻**(每轮都在),SKILL 是**按需**(相关才加载)。
>
> **本片缘起(人 2026-06-05 定向)**:对位 Claude Code / Cursor 的两类能力时确认——产物已有**代码级生命周期 hook**(Slice 1 `hooks.py`),但**缺"常驻 rule 文件"这一档**。人选"做薄版、近期排一个小 slice"(配置级 shell hook 仅记 v1+ backlog,见 `00-overview §2` Slice 11+)。
>
> **编号说明**:紧接 Slice 6、在 wizard(Slice 7)之前的薄增量;为不扰动 wizard / v1+(Slice 8+)既有编号,记为 **Slice 6B**(文件 `075-` 排在 `07-`(Slice 6)与 `08-`(Slice 7)之间)。
>
> **状态:✅ 已完成(2026-06-05)。门禁全绿**:生成器快测 75(+2:机制始终生成 / seed 时产 starter)+ 产物自带测试(+2:rule 注入 / 无 rule 零段落)+ golden 8(非 docker)+ docker 2 全绿;`ReadLints` clean。
>
> **薄/红线**:零新增依赖(只读文件 + 拼字符串);纯运行期行为(`config.yaml` 活旋钮),`spec.prompts.rules_files` 仅作**初值种子**(决策④ 配方 vs 活旋钮,`01 §4`);非框架、非 DSL。

## 0. 边界与口径

- **rule vs SKILL**:rule = 常驻(每轮注入全文,适合"始终遵守"的项目约定);SKILL = 按需(只注入 name+description,相关时才 `read_skill` 读正文)。两者互补,机制同源。
- **配方 vs 活旋钮**(决策④,`01 §4`):`prompts.rules_files` 是**运行期权威**(`config.yaml` 可随时增删文件、改列表,不重生成);`spec.prompts.rules_files` 只是**生成期种子**,渲染进 `config.yaml` 后即以运行期为准。
- **天花板 vs 地板**:rule 是 prompt 文本注入(行为轴),**非安全边界**——own-code 用户可改 `config.yaml`/规则文件;护栏仍靠 tool allowlist + 风险标记(结构轴,`01 §4`)。
- **缺文件即跳过**:列了但文件不存在 → 静默跳过(不报错),所以"先配后写"或共享他工具的规则文件都安全。

## 1. 交付物

- `harnessforge/spec.py` — `Prompts` 新增 `rules_files: list[str] = []`(生成期种子;`extra="forbid"` 下声明字段)。
- 产物 `harness/config.py`(模板)— `PromptsConfig` 新增 `rules_files`(运行期旋钮)。
- 产物 `harness/prompts.py`(模板)— 新增 `_load_rules(config)`:按 `prompts.rules_files` 顺序读 markdown、拼成 "Project rules (always follow):" 段,插在 system+persona 之后、skills/environment 之前;**始终生成**(空列表 = 零效果)。
- 产物 `config.yaml`(模板)— 渲染 `prompts.rules_files`(seed 自 spec)+ 注释说明。
- `harnessforge/templates/RULES.md.j2` — starter 规则文件,**仅当 `"RULES.md" in spec.prompts.rules_files` 时生成**(`generator.py` `CONDITIONAL_TEMPLATES`),否则产物零 rule 文件痕迹。
- `coding-assistant` preset — seed `prompts.rules_files: [RULES.md]`(旗舰 preset 开箱演示)。
- 测试:生成器快测 2(机制始终生成且 thin 不落 RULES.md;seed 时落 starter 且进快照)+ 产物自带测试 2(rule 注入生效、缺文件跳过;无 rule 时无段落)。
- 文档:本片 + `AGENTS.md`/`README`(产物)+ `00-overview` §2/§3 + `01-project-plan` §5。

## 2. 任务拆解(均已完成)

1. spec/config 双侧加 `rules_files` 字段(同名,1:1 渲染)。
2. `prompts.py` 加 `_load_rules` 并接入 `build_system_prompt`(无条件、空即 no-op)。
3. `config.yaml.j2` 渲染旋钮 + 注释;`RULES.md.j2` 条件渲染;coding-assistant seed。
4. 测试(生成器快测 + 产物自带)+ golden/docker 回归。

## 3. 退出门禁(全绿)

- [x] **黄金路径**:coding-assistant(seed rules)生成 → `uv lock` → `uv sync && pytest`(产物自带 rule 注入测试绿)→ mock 跑通一次工具调用。
- [x] **rule 注入生效**:产物 `build_system_prompt` 含规则文件正文;缺文件静默跳过(产物自带测试)。
- [x] **薄/零痕迹**:thin example(无 rules)不落 `RULES.md`、`config.yaml` 仅 `rules_files: []`;无新增依赖(`uv.lock` 不含 langchain/langgraph/adk)。
- [x] **种子进快照**:seed 的 `rules_files` 作配方落 `harness.spec.yaml`(只含文件名,无密钥)。
- [x] **大改动回归**(动了 `HarnessSpec` + 跨 ≥3 文件):golden 全量(thin/preset/web/mcp/skills/多范式/uvx)+ Docker build/run mock 全绿。
- [x] `ReadLints` clean。

## 4. 必须人审的决策点

- [x] **① 做薄版全局 rule、排为小 slice——人 2026-06-05 定向**(对位 Claude Code/Cursor rule;配置级 shell hook 仅记 v1+ backlog)。
- [x] **② spec 面加 `prompts.rules_files` 初值种子——人 2026-06-05 选定**(让 preset/wizard 可播种;触发 `CLAUDE.md §6` 改 `HarnessSpec`,人已签)。
- **软确认(非阻塞,`CLAUDE.md §5.3`)**:字段名 spec/config 同取 `rules_files`(1:1 映射);starter 文件名 `RULES.md` 且仅 seed 时生成;注入位置在 persona 之后、skills 之前;段首固定 "Project rules (always follow):"。

## 5. 本 slice 注意 / 留给后续

- **wizard(Slice 7)需覆盖 `prompts.rules_files`**:已在 `08-slice-7-wizard.md` §2.1 高级组登记。
- **配置级 shell hook(Claude Code/Cursor 风格,事件→shell 命令、可 veto)= v1+ backlog**(`00-overview §2` Slice 11+):代码级 `Hooks` 已覆盖同等能力(own-code 写子类即可),且与 v1+ HITL 确认 hook 重叠、引入"配置跑任意 shell"新安全面,故缓做。
- **不做**:rule 的 glob / 描述触发 auto-attach(Cursor 进阶特性)——MVP 只做"always-apply 文件列表"薄版;按需触发交给 SKILL(Slice 6)。
