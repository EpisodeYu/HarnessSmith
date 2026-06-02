# 02·02 - Slice 1:黄金路径 ★(核心里程碑)

> 目标:生成一个**无 agent 框架、薄、在任意环境可跑通一次工具调用、可读可改**的 harness。**本片绿了,立项假设即被验证。**
>
> 前置:Slice 0 门禁全绿。

## 1. 交付物

生成产物模板核心(framework-free,均在 `harnessforge/templates/`):

- `config.py` — 加载 `config.yaml` + `.env` + Pydantic 校验;密钥按 **env 引用名**解析(真值不入产物代码 / 不入 git)。
- `llm.py` — openai SDK 适配,**Chat Completions + `tools`**,`base_url` provider-agnostic;先支持单 profile(角色路由留 Slice 2)。
- `loop.py` — 原生 function-calling 循环(TAO/ReAct 语义)+ 停止条件 / 最大步数 / 错误处理 + Hooks 调用点 + **预算停止**(步数 / 时间 / 成本)。
- `tools.py` — 工具注册表(装饰器)+ 风险标记;高风险工具(shell/写文件)**默认关,allowlist 显式开**;含 1–2 个内置安全示例工具。
- `hooks.py` — 生命周期 hook 接口与默认空实现。
- `trace.py` — 每次 run 的 JSONL trace + token / 成本计数。
- `prompts.py` — 系统提示拼装。
- `interfaces/cli.py` — `run` 一问一答。

生成器侧:

- `generator.py` 增 `uv lock` + **生成后冒烟自检**(`uv sync` + import + mock 跑一步 + `pytest -q`);`cli.py` 增 `doctor` 预检 + `--no-verify`。
- 产物模板增**可运行性文件**:`uv.lock`(生成时锁)+ `.python-version` + `requirements.txt`(uv 导出)+ `Dockerfile` + `.dockerignore` + `.devcontainer/devcontainer.json`(基于 `ghcr.io/astral-sh/uv` 镜像)。
- `presets/coding-assistant`:可生成可跑的最小 preset spec。
- 产物 `README.md`(首条命令 `uv sync` → `uv run <pkg> run`)+ `AGENTS.md`(加工具 / 换模型 / 插 hook 指南)。
- **mock LLM**:测试用,产出可断言的 tool_call 序列,开发无需真 key。

## 2. 任务拆解

### 2.1 模板核心
按 §1 逐个模板落地,保持薄(`CLAUDE.md §2`)。loop 用 `generation` 角色取 client(本片可硬绑唯一 profile,接口预留角色路由)。

### 2.2 可运行性保障(详见 `01-project-plan.md §7`)
- uv 契约:产物带 `uv.lock` + `.python-version`,`uv sync` 一键就绪。
- 默认 Docker:`docker build && docker run` 得到与宿主无关的环境。
- 生成后冒烟自检默认开,`--no-verify` 可关;`harnessforge doctor` 预检。

### 2.3 黄金快照测试(本片的核心测试)
用 coding-assistant preset 生成项目 → `uv sync && pytest` → mock LLM 跑通一次 function-calling(含一次工具调用)。

## 3. 退出门禁(= `01-project-plan.md §8` 全部 Blocker,全绿才算完成)

- [ ] 黄金快照:preset 生成 → `uv sync && pytest` 全绿 → mock 跑通一次工具调用。
- [ ] 断言生成的 `pyproject.toml` 不含 langchain/langgraph/adk。
- [ ] **生成后冒烟自检通过**(默认开)。
- [ ] **Docker 可运行**:生成产物 `docker build` 成功 + `docker run` 跑通 mock 一步。
- [ ] 生成项目 CLI 一问一答可跑通(mock 后端)。
- [ ] 扩展点:新注册一个 demo tool + 挂一个 hook 的测试,无需改核心代码即生效。
- [ ] 可观测:一次 run 产出结构正确的 JSONL trace + token/成本断言。
- [ ] 预算停止单测(步数/时间/成本超限即停)。
- [ ] 密钥不入 git:`config.yaml`/`harness.spec.yaml` 不含明文密钥的断言。
- [ ] 生成器自身:spec 校验、模板渲染单测、`uvx harnessforge new` 冒烟。
- [ ] `ReadLints` clean。

## 4. 必须人审的决策点

- **验收立项假设**:生成产物是否够薄、可读、在任意环境可跑、零 agent 框架。这是项目能不能成立的签字点(`CLAUDE.md §6` 触发)。

## 5. 本 slice 注意

- **红线**:产物里出现任何 agent 编排框架依赖 = 直接失败(`CLAUDE.md §6.3`)。
- **薄**:核心循环目标 150–300 行;超出明显即停问人(`CLAUDE.md §6.8`)。
- **密钥**:trace / 日志 / spec 快照 / git 任一路径出现明文 key 即失败(`CLAUDE.md §6.5`)。
- Chat Completions 是已定决策;若实现中发现需切 Responses,先停问人(`CLAUDE.md §6.4`)。
