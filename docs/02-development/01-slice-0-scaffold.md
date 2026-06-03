# 02·01 - Slice 0:骨架

> 目标:把"spec → 渲染 → 写出仓库"这条管道打通,能生成一个**空壳但结构正确**的产物仓库。本片不实现 harness 运行逻辑(那是 Slice 1)。
>
> 前置:无。这是第一片。
>
> **状态:✅ 已实现并通过退出门禁(`uv run pytest` 25 green;CLI 端到端冒烟通过)。** 实现与下文描述一致;与初版计划的偏差已在各节用"实现说明"标注。

## 1. 交付物

- `harnessforge/spec.py` — `HarnessSpec` Pydantic v2 模型,**字段集(v0.1 定稿)**:`version` / `project_slug` / `llms`(profile 列表占位)/ `roles` / `prompts`(system/persona,Slice 1 消费)/ `tools`(占位)/ `interfaces` / `observability` / `budget`(max_steps/max_seconds/max_cost_usd,Slice 1 落地预算停止)。context / rag / secrets backend 字段**预留但本片不展开**。全模型 `extra="forbid"`。
- `harnessforge/generator.py` — 加载 spec(YAML)→ Jinja2 渲染 `templates/` → 写出独立仓库 → 写入 `harness.spec.yaml`(spec 快照)→ `git init`;**重跑检测到目标非空则报错不覆盖**(`TargetExistsError`)。
- `harnessforge/cli.py` — Typer 入口,先实现 `new <dir> --spec <spec.yaml>`(含 `--git/--no-git`)。非法 spec → exit 2;重跑非空目录 → 警告 exit 1。
- `harnessforge/templates/` — 最小模板(`.j2`):`pyproject.toml` + `README.md` + `.env.example` + `LICENSE` + `.gitignore` + 空 `src/<pkg>/__init__.py`。
  - **实现说明**:`harness.spec.yaml` **不是模板**,由生成器按校验后的 spec 快照写出(见 2.2),保证它是真实快照而非静态占位。`.gitignore` 为自主新增(忽略 `.env` 与 trace 目录,落实"密钥不入 git")。
- `tests/` — `test_spec.py`(spec 校验:合法/非法字段/缺必填/坏 slug/roles 指向未知 profile/budget 非正值)+ `test_generator.py`(渲染:文件结构、占位替换、快照回环、`.env` 仅 env 名、无框架断言、重跑不覆盖、git init)。
- 一份**示例 `examples/spec.yaml`**(最小可生成,含 `prompts`/`budget` 示例)。

## 2. 任务拆解

### 2.1 HarnessSpec(最小)
- Pydantic v2 模型 + `load_spec()` YAML 加载;`extra="forbid"` 使非法字段 / 缺必填 → 清晰报错。
- `project_slug` snake_case 正则校验;`roles` 值必须指向已声明的 profile(交叉校验);`budget.*` 约束 `gt=0`。
- `version` 字段为后续模板兼容铺垫(见 `00-overview §3`)。

### 2.2 渲染引擎
- Jinja2 `Environment`(`StrictUndefined`,`keep_trailing_newline`),变量来自 spec;`project_slug` 决定包目录名(模板路径用 `__project_slug__` 占位)。
- 写仓库:目标目录不存在或为空才写;非空则**报错不覆盖**(`TargetExistsError`,保护用户改动)。
- 写 `harness.spec.yaml`:由 `spec.model_dump(mode="json", exclude_none=True)` 序列化,**只含 env 引用名、不含明文密钥**。
- `git init` 生成的仓库(可经 `--no-git` 关闭)。

### 2.3 CLI
- `harnessforge new <dir> --spec <spec.yaml>`,渲染并落盘;`--git/--no-git` 控制是否 `git init`。

## 3. 退出门禁(全绿才算完成)

- [x] spec 校验单测绿(合法通过 / 非法报错)。
- [x] 渲染单测绿:用示例 spec 生成到临时目录,断言文件结构正确、占位被替换、`harness.spec.yaml` 已写入且无密钥明文(可回环加载)。
- [x] 重跑同目录会报错不覆盖(单测 `TargetExistsError`,用户改动原样保留)。
- [x] 生成的 `pyproject.toml` 已断言**不含** langchain/langgraph/adk(即便此时还没运行逻辑,模板就要立规矩)。
- [x] `ReadLints` clean。
  - **实现说明**:代码层 clean;basedpyright 可能报 `yaml`/`pydantic` 导入解析 warning,属 IDE 解释器指向系统 Python(非 `.venv`)的环境问题,非代码缺陷(已在 `pyproject.toml` 加 `[tool.pyright]` venv 提示,`uv run pytest` 全绿佐证导入可解析)。

## 4. 必须人审的决策点

- [x] `HarnessSpec` 字段集是否合理(字段名 = 后续 `config.yaml` 字段,改动成本高)。
  - **决定(人已拍板)**:采纳最小字段集,并新增 `budget`(max_steps/max_seconds/max_cost_usd)与 `prompts`(system/persona);`secrets` 保留为预留 passthrough。定稿为 `version: "0.1"`。

## 5. 本 slice 注意

- **两层心智**:本片几乎全在生成器层;模板里先放占位,真实 harness 代码留给 Slice 1。
- **薄**:模板别提前塞 fastapi/mcp/sqlite-vec 等依赖,`pyproject.toml` 默认依赖留到 Slice 1 按需加。
- 改 `HarnessSpec` 字段属 `CLAUDE.md §6.1` 触发条件,定稿前与人确认(本片已确认,见 §4)。
