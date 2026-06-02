# 02·01 - Slice 0:骨架

> 目标:把"spec → 渲染 → 写出仓库"这条管道打通,能生成一个**空壳但结构正确**的产物仓库。本片不实现 harness 运行逻辑(那是 Slice 1)。
>
> 前置:无。这是第一片。

## 1. 交付物

- `harnessforge/spec.py` — `HarnessSpec` Pydantic v2 模型,**最小字段集**:`version` / `project_slug` / `llms`(profile 列表占位)/ `roles` / `interfaces` / `tools`(占位)/ `observability`。rag / context / secrets backend 字段**预留但本片不展开**。
- `harnessforge/generator.py` — 加载 spec(YAML)→ Jinja2 渲染 `templates/` → 写出独立仓库 → 拷入 `harness.spec.yaml` → `git init`;**重跑检测到已存在则警告不覆盖**。
- `harnessforge/cli.py` — Typer 入口,先实现 `new`(`--spec`)。
- `harnessforge/templates/` — 最小模板:`pyproject.toml` + `README.md` + `.env.example` + `LICENSE` + 空 `src/<pkg>/__init__.py` + 占位 `harness.spec.yaml`。
- `tests/` — spec 校验单测 + 渲染单测(渲染后文件存在 + 关键占位被替换)。
- 一份**示例 `spec.yaml`**(最小可生成)。

## 2. 任务拆解

### 2.1 HarnessSpec(最小)
- Pydantic v2 模型 + YAML 加载;非法字段 / 缺必填 → 清晰报错。
- `version` 字段为后续模板兼容铺垫(见 `00-overview §3`)。

### 2.2 渲染引擎
- Jinja2 `Environment`,变量来自 spec;`project_slug` 决定包目录名。
- 写仓库:目标目录不存在才写;已存在则**警告不覆盖**(保护用户改动)。
- 拷 `harness.spec.yaml`(spec 快照,**不含明文密钥**)。
- `git init` 生成的仓库。

### 2.3 CLI
- `harnessforge new <dir> --spec <spec.yaml>`,渲染并落盘。

## 3. 退出门禁(全绿才算完成)

- [ ] spec 校验单测绿(合法通过 / 非法报错)。
- [ ] 渲染单测绿:用示例 spec 生成到临时目录,断言文件结构正确、占位被替换、`harness.spec.yaml` 已拷入且无密钥明文。
- [ ] 重跑同目录会警告不覆盖(单测)。
- [ ] 生成的 `pyproject.toml` 已断言**不含** langchain/langgraph/adk(即便此时还没运行逻辑,模板就要立规矩)。
- [ ] `ReadLints` clean。

## 4. 必须人审的决策点

- `HarnessSpec` 最小字段集是否合理(字段名 = 后续 `config.yaml` 字段,改动成本高)。

## 5. 本 slice 注意

- **两层心智**:本片几乎全在生成器层;模板里先放占位,真实 harness 代码留给 Slice 1。
- **薄**:模板别提前塞 fastapi/mcp/sqlite-vec 等依赖,`pyproject.toml` 默认依赖留到 Slice 1 按需加。
- 改 `HarnessSpec` 字段属 `CLAUDE.md §6.1` 触发条件,定稿前与人确认。
