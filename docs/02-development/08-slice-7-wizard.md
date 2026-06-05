# 02·08 - Slice 7:wizard(单页表单产 spec + 可选一键生成)

> 目标:把"采集 spec"从手写 YAML / preset 升级为**单页向导**——`harnessforge/wizard/`(FastAPI + 无构建单页,Tailwind CDN + 原生 JS)采集 `HarnessSpec` 全字段(基础/高级分组),`POST /spec` 校验并产合法 spec(可下载)+ 可选一键调既有 `generate()`。wizard 是**生成器侧工具**,不进产物、产物不依赖它(`01 §1`)。属 `01-project-plan.md` 的 **L2(生成期 Web wizard,人已定向)**。
>
> **本片由 2026-06-05 重切而来**:原 Slice 5 过大,拆为 Slice 5(范式)/ Slice 6(工具基线 + SKILL)/ Slice 7(本片:wizard)。wizard 放最后,因它是**对已稳定 spec 的 GUI**——需覆盖 Slice 5 的 `paradigms`、Slice 4/6 的 `mcp.enabled` + catalog、Slice 6 的 `skills.enabled` 等字段。
>
> 前置:Slice 5(范式)+ Slice 6(工具基线 + SKILL)门禁全绿(spec 字段集稳定)。
>
> **状态:📝 规划中(子文档已立)。字段面经人 2026-06-05 定稿**(全覆盖 + 基础/高级分组,见 §4①)。退出门禁(§3)暂全空,实现且自验证全绿后回填。
>
> **红线提醒**:FastAPI/uvicorn 是通用 Web 库、**非 agent 编排框架**(`01 §1`),且仅进**生成器侧** `harnessforge[wizard]` extra,**不污染 `uvx harnessforge new` 核心链路、不进产物**。**密钥红线**:wizard 只采集/回显 env 变量名,绝不收/不回显密钥真值(`CLAUDE.md §6.5`)。

## 0. 边界与口径(开工前先对齐)

- **wizard 产 spec,不是运行期配置面板**:它是**生成期**采集层(`spec` = 配方);运行期行为性配置由产物自身 `/config`(Slice 3)管。两者不混(决策④,`01 §4`)。
- **覆盖稳定后的 spec 全字段**:含 Slice 5 `paradigms`(多选 + 默认)、Slice 4/6 `mcp.enabled` +(开时)catalog 多选预填 server、Slice 6 `skills.enabled`、以及 llms/roles/prompts/tools/interfaces/observability/budget/context。
- **无构建单页**:复用产物 web 的形态(Tailwind CDN + 原生 `fetch`,`01 §6` 自主细节);唯一动态来源是后端给的字段元数据 / catalog 列表。
- **依赖隔离**:fastapi/uvicorn 进 `harnessforge[wizard]` extra;核心 `harnessforge` 依赖(typer/jinja2/pydantic/pyyaml)不变 → `uvx harnessforge new` 不拉 fastapi。

## 1. 交付物

- `harnessforge/wizard/`(新目录,`harnessforge[wizard]` extra 门控)— FastAPI + 单页静态表单:`GET /` 表单(字段面见 §2.1);`POST /spec` 用 `HarnessSpec` 校验 → 返回 YAML + 字段级错误回显 + 可选一键 `generate()`。
- `harnessforge/cli.py` — `harnessforge wizard`(起 uvicorn,默认 `127.0.0.1`,类产物 web 的 `serve`)。
- wizard 单页前端(`wizard/static/index.html` 或内联)— 沿用产物 web 的无构建形态;基础/高级折叠;`mcp.enabled` 时显示 catalog 多选。
- 测试 fixture + `fastapi.testclient` 端到端测试。

## 2. 任务拆解

### 2.1 字段面(全覆盖 + 基础/高级分组,已定稿 §4①)
- **基础组**:`project_slug`;1 个 llm profile(`model`/`api_key_env`/`base_url_env`);`prompts.system`;内置 tools 勾选(高风险标注、默认关);`interfaces.web`;`mcp.enabled`;`skills.enabled`;`paradigms` 多选 + 默认。
- **高级折叠**:多 llm profile + 采样(`temperature`/`max_tokens`)+ 单价(`prompt_cost_per_1k`/`completion_cost_per_1k`);`roles`;`prompts.persona`;`prompts.rules_files`(Slice 6B,全局 rule 文件列表种子);`budget` 四维(steps/seconds/tokens/cost);`context`(strategy/max_context_tokens/keep_last_turns);`observability`(trace/trace_dir);`mcp.enabled` 时从 catalog(Slice 6)多选 server。

### 2.2 后端校验 + 产出
- `POST /spec`:Pydantic(`HarnessSpec`)校验 → 返回合法 spec YAML(可下载)+ 字段级错误回显。**密钥红线**:只采集 env 变量名、不回显真值。
- **产 spec vs 直接生成**(软确认 §4):倾向"产合法 spec(可下载)+ 一键调既有 `generate()`";若 `generate()` 的 `uv lock`/`smoke_check`/预热 长耗时卡 UI,则退"只产 spec、由 `harnessforge new --spec` 接力"。

### 2.3 依赖隔离
- fastapi/uvicorn 进 `harnessforge[wizard]` extra;`harnessforge wizard` 起服务;不进产物、不污染核心 CLI。

## 3. 退出门禁(对应 `01 §8` Non-blocker,做到即验;实现后回填)

- [ ] **wizard 产合法 spec**:表单(含 `paradigms` 多选+默认、`mcp.enabled`+catalog 预填、`skills.enabled`)→ `POST /spec` 经 `HarnessSpec` 校验通过、能 `generate()` 出可跑产物(`fastapi.testclient` 端到端,无需真浏览器)。
- [ ] **wizard 不泄密 / 不进产物**:只采集/回显 env 名,无密钥真值;依赖仅 `harnessforge[wizard]` extra,核心 CLI 与产物不含 fastapi/uvicorn(薄验证)。
- [ ] **catalog 预填经 wizard 落 `config.yaml`**:wizard 选中 server → 生成产物 `config.yaml mcp.servers` 含该条目(env 仅名、高风险默认关)。
- [ ] **wizard 字段对外可读(人审)**:起 `harnessforge wizard` 实际点一遍,字段集/措辞/默认对非作者用户友好(类 Slice 3 web 真实验收)。
- [ ] `ReadLints` clean。

## 4. 必须人审的决策点

- [x] **① wizard 字段 = 全覆盖 + 基础/高级分组——人 2026-06-05 定稿**:字段面见 §2.1;产 spec + 一键生成;只采集 env 名。
- [ ] **② wizard 字段是否齐 / 对外可读(实现后真实验收)**:起 wizard 点一遍(类 Slice 3 web),确认覆盖与措辞。
- **软确认(非阻塞,`CLAUDE.md §5.3`)**:产 spec + 可选一键 `generate()`(卡 UI 则退"只产 spec、`new --spec` 接力");无构建单页(Tailwind CDN);wizard 依赖进 `[wizard]` extra。

## 5. 本 slice 注意

- **不进产物 / 不绑框架**:wizard 仅生成器侧、FastAPI 非 agent 编排框架(`01 §1`);产物不依赖 wizard(守"生成后不再依赖 HarnessForge")。
- **密钥红线**(`CLAUDE.md §6.5`):表单 / 回显 / 产出 spec 只存 env 变量名。
- **配方 vs 活旋钮**(决策④,`01 §4`):wizard 产 `spec`(配方);运行期行为性配置交产物 `/config`(Slice 3)。
- **覆盖随 spec 演进**:本片在 Slice 5/6 之后做,确保字段面覆盖 `paradigms`/`mcp.enabled`/`skills.enabled` 等最终字段;若 spec 再增字段,wizard 同步补。
