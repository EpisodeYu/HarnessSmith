# 02·02 - Slice 1:黄金路径(核心里程碑)

> 目标:生成一个**无 agent 框架、薄、在任意环境可跑通一次工具调用、可读可改**的 harness。本片绿了,立项假设即被验证。
>
> 前置:Slice 0 门禁全绿。

## 1. 交付物

生成产物模板核心(framework-free,均在 `harnessmith/templates/`):

- `config.py` — 加载 `config.yaml` + `.env` + Pydantic 校验(`pydantic-settings`);密钥按 **env 引用名**解析(真值不入产物代码 / 不入 git)。
- `llm.py` — openai SDK 适配,**Chat Completions + `tools`**,`base_url` provider-agnostic;先支持单 profile(角色路由留 Slice 2)。
- `loop.py` — 原生 function-calling 循环(TAO/ReAct 语义)+ 停止条件 / 错误处理 + Hooks 调用点 + **预算停止**(预算最终形态 = 按 LLM 持久 cost 账本,见 [`00-overview.md`](./00-overview.md) §6 决策表「预算」行)。
- `tools.py` — 工具注册表(装饰器)+ 风险标记;高风险工具(shell/写文件)**默认关,allowlist 显式开**;含 1–2 个内置安全示例工具(`get_current_time`/`calculator`)。
- `hooks.py` — 生命周期 hook 接口与默认空实现。
- `trace.py` — 每次 run 的 JSONL trace + token / 成本计数。
- `prompts.py` — 系统提示拼装。
- `mock.py` — 产物内置 mock LLM:产出可断言的 tool_call 序列,`cli --mock`/Docker/冒烟自检/产物自带测试共用,真正「无 key 跑通一次工具调用」。
- `interfaces/cli.py` — `run` 一问一答。

生成器侧:

- `generator.py` 增 `uv lock` + **生成后冒烟自检**(`uv sync` + import + mock 跑一步 + `pytest -q`);`cli.py` 增 `doctor` 预检 + `--no-verify`。subprocess 调 uv 时清洗环境(剥离 `VIRTUAL_ENV`/`UV_PROJECT_ENV`/`PYTHONPATH`),避免把父环境解释器泄漏进新仓库。
- 产物模板增**可运行性文件**:`uv.lock`(生成时锁)+ `.python-version` + `requirements.txt`(uv 导出)+ `Dockerfile` + `.dockerignore` + `.devcontainer/devcontainer.json`(基于官方 uv 镜像)。Docker `ENTRYPOINT` 直接调用 venv 内 console script(`docker run` 零再同步、零联网即跑)。
- `presets/coding-assistant`:可生成可跑的最小 preset spec。
- 产物 `README.md`(首条命令 `uv sync` → `uv run <pkg> run`)+ `AGENTS.md`(加工具 / 换模型 / 插 hook 指南)。
- 产物测试依赖走 uv 原生 `[dependency-groups] dev = ["pytest"]`(`uv sync` 默认安装)。

## 2. 任务拆解

- **模板核心**:按 §1 逐个落地,保持薄(`CLAUDE.md §2`)。loop 用 `generation` 角色取 client(本片可硬绑唯一 profile,接口预留角色路由)。
- **可运行性保障**(详见 `00-overview.md` §7):uv 契约(`uv.lock` + `.python-version`,`uv sync` 一键就绪)+ 默认 Docker(`docker build && docker run` 得到与宿主无关的环境)+ 生成后冒烟自检默认开(`--no-verify` 可关)+ `harnessmith doctor` 预检。
- **黄金快照测试**(本片核心测试):用 coding-assistant preset 生成项目 → `uv sync && pytest` → mock LLM 跑通一次 function-calling(含一次工具调用)。

> **定价 / token 预算落位**:费率随 provider 变,故定价与 token 预算只落生成产物**运行期** `config.py`(默认无限制),`config.yaml` 以注释提示——它们是部署期旋钮,运行期可配更合理。`HarnessSpec` 不为此改动。

## 3. 退出门禁(= `00-overview.md` §7 全部 blocker)

- 黄金快照:preset 生成 → `uv sync && pytest` 全绿 → mock 跑通一次工具调用。
- 断言生成的 `pyproject.toml`(及 `uv.lock`/`requirements.txt`)不含 langchain/langgraph/adk。
- 生成后冒烟自检通过(默认开,`--no-verify` 可关)。
- Docker 可运行:生成产物 `docker build` 成功 + `docker run` 跑通 mock 一步。
- 生成项目 CLI 一问一答可跑通(mock 后端)。
- 扩展点:新注册一个 demo tool + 挂一个 hook 的测试,无需改核心代码即生效。
- 可观测:一次 run 产出结构正确的 JSONL trace + token/成本断言。
- 预算停止单测。
- 密钥不入 git:`config.yaml`/`harness.spec.yaml` 不含明文密钥的断言。
- 生成器自身:spec 校验、模板渲染单测、`uvx harnessmith new` 冒烟。
- coding-assistant preset 能成功生成并通过其 pytest。
- `ReadLints` clean。

## 4. 关键决策

- **立项假设验收**:生成产物够薄(核心循环 `loop.py` 在 150–300 行目标内;harness 核心模块合计精简)、可读、在任意环境可跑、零 agent 框架(`pyproject`/`uv.lock`/`requirements.txt` 三处断言)。立项假设成立。

## 5. 本 slice 注意

- **红线**:产物里出现任何 agent 编排框架依赖 = 直接失败(`CLAUDE.md §6.3`)。
- **薄**:核心循环目标 150–300 行;超出明显即停问人(`CLAUDE.md §6.8`)。
- **密钥**:trace / 日志 / spec 快照 / git 任一路径出现明文 key 即失败(`CLAUDE.md §6.5`)。
- Chat Completions 是已定决策;若实现中发现需切 Responses,先停问人(`CLAUDE.md §6.4`)。
