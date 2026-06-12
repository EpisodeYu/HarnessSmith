# 02·02 - Slice 1:黄金路径 ★(核心里程碑)

> 目标:生成一个**无 agent 框架、薄、在任意环境可跑通一次工具调用、可读可改**的 harness。**本片绿了,立项假设即被验证。**
>
> 前置:Slice 0 门禁全绿。
>
> **状态:✅ 已完成(退出门禁 §3 全绿 + §4 人审已签字通过)。** `uv run pytest` 38 fast green + `uv run pytest -m golden` 3 green(全量黄金快照 / `uvx` 冒烟 / Docker build+run mock 一步);`ReadLints` clean。**立项假设(薄 / 可读 / 任意环境可跑 / 无 agent 框架)已被验证,人已签字。** 实现与下文一致,偏差以各节"实现说明"标注。

## 1. 交付物

生成产物模板核心(framework-free,均在 `harnessmith/templates/`):

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

**实现说明(与初版计划的偏差/细化)**:

- **HarnessSpec 未改**(避免 `CLAUDE.md §6.1`)。**定价**(`prompt_cost_per_1k`/`completion_cost_per_1k`,**2026-06-06 Slice 7 续重命名为 `input_cost_per_million`/`output_cost_per_million`、单位改 per-1M 且货币无关**,见 `08-slice-7-wizard.md §2.3 实现说明`)与 **token 预算**(`budget.max_tokens`)都只落在**生成产物运行期** `config.py`,默认无限制/`0.0`,`config.yaml` 以注释提示——它们是部署期旋钮(费率随 provider 变),运行期可配更合理(人已确认)。`spec.budget` 仍保留生成期默认 steps/seconds/cost 三项。
- **预算停止 = 4 维**:步数(轮次)/ 时间 / **token** / 费用,任意组合,命中第一个即停。"按费用"依赖对应 LLM profile 的非零单价,否则 cost 恒 0、永不触发(已在 `config.yaml`/`AGENTS.md` 写明)。
- **mock LLM 落在产物内** `harness/mock.py`(非仅测试夹具),因此 `cli.py --mock`、Docker、冒烟自检、生成产物自带测试可共用同一 mock,真正"无 key 跑通一次工具调用"。
- 产物**测试依赖**走 uv 原生 `[dependency-groups] dev = ["pytest"]`(`uv sync` 默认安装),而非 `optional-dependencies`——否则 `uv run pytest` 会落到临时解释器、找不到包(已踩坑修复)。
- **Docker** `ENTRYPOINT` 直接调用 venv 内 console script(非 `uv run`),`docker run` 零再同步、零联网即跑。
- **生成产物提交可运行性文件**:`uv.lock` + `requirements.txt` 由生成器在生成后跑 `uv lock`/`uv export` 产出(非模板)。`config.py` 用 `pydantic-settings` 读取 `.env`(`extra="allow"`)+ `os.environ` 解析按名引用的密钥。
- **生成器侧 subprocess 调 uv 时清洗环境**(剥离 `VIRTUAL_ENV`/`UV_PROJECT_ENV`/`PYTHONPATH` 等),否则在 `uv run`/`uvx harnessmith` 下会把父环境解释器泄漏进新仓库(已踩坑修复)。
- **打包**:移除了 Slice 0 冗余的 `force-include`(模板/preset 均随 `packages=["harnessmith"]` 进 wheel;preset 数据文件 `spec.yaml` 也随之打包),否则 `uvx`/`uv build` 会因重复路径构建失败(此前只做 editable install 未触发)。

## 2. 任务拆解

### 2.1 模板核心
按 §1 逐个模板落地,保持薄(`CLAUDE.md §2`)。loop 用 `generation` 角色取 client(本片可硬绑唯一 profile,接口预留角色路由)。

### 2.2 可运行性保障(详见 `01-project-plan.md §7`)
- uv 契约:产物带 `uv.lock` + `.python-version`,`uv sync` 一键就绪。
- 默认 Docker:`docker build && docker run` 得到与宿主无关的环境。
- 生成后冒烟自检默认开,`--no-verify` 可关;`harnessmith doctor` 预检。

### 2.3 黄金快照测试(本片的核心测试)
用 coding-assistant preset 生成项目 → `uv sync && pytest` → mock LLM 跑通一次 function-calling(含一次工具调用)。

## 3. 退出门禁(= `01-project-plan.md §8` 全部 Blocker,全绿才算完成)

- [x] 黄金快照:preset 生成 → `uv sync && pytest` 全绿 → mock 跑通一次工具调用。(`tests/test_golden.py::test_golden_preset_generates_locks_and_smoke_passes`;smoke 内含 `uv sync`+import+`run --mock`+`pytest`)
- [x] 断言生成的 `pyproject.toml` 不含 langchain/langgraph/adk。(并扩展断言 `uv.lock`/`requirements.txt` 同样干净)
- [x] **生成后冒烟自检通过**(默认开,`--no-verify` 可关)。(`generator.smoke_check`;CLI `new` 默认调用)
- [x] **Docker 可运行**:生成产物 `docker build` 成功 + `docker run` 跑通 mock 一步。(`test_golden.py::test_docker_build_and_run_mock_step`)
- [x] 生成项目 CLI 一问一答可跑通(mock 后端)。(`interfaces/cli.py run [--mock]`;smoke + docker 均经此路径)
- [x] 扩展点:新注册一个 demo tool + 挂一个 hook 的测试,无需改核心代码即生效。(生成产物 `tests/test_harness.py::test_register_tool_and_hook_without_touching_core`)
- [x] 可观测:一次 run 产出结构正确的 JSONL trace + token/成本断言。(`...::test_mock_runs_one_tool_call` / `...::test_trace_records_tokens_and_cost`)
- [x] 预算停止单测(步数/时间/**token**/成本超限即停)。(`...::test_budget_stop_on_max_steps|max_seconds|max_tokens|max_cost`)
- [x] 密钥不入 git:`config.yaml`/`harness.spec.yaml` 不含明文密钥的断言。(`tests/test_generator.py::test_config_yaml_renders_from_spec_without_secrets` + Slice 0 快照断言)
- [x] 生成器自身:spec 校验、模板渲染单测、`uvx harnessmith new` 冒烟。(`test_spec.py` / `test_generator.py` / `test_golden.py::test_uvx_harnessmith_new_smoke`)
- [x] `ReadLints` clean。

## 4. 必须人审的决策点

- [x] **验收立项假设**:生成产物够薄、可读、在任意环境可跑、零 agent 框架。**人已签字通过**(立项假设成立)。
  - 供审参考(实测):核心循环 `loop.py` = 151 行(含 docstring,在 150–300 目标内);harness 核心 8 模块合计 ≈ 713 行;默认产物依赖仅 `openai/pydantic/pydantic-settings/pyyaml/typer`,零 agent 框架(`pyproject`/`uv.lock`/`requirements.txt` 三处断言);`uvx harnessmith new --preset coding-assistant` 一条命令 → 生成 → 锁依赖 → 冒烟自检全绿;`docker run` 零额外动作跑通 mock 一步。

## 5. 本 slice 注意

- **红线**:产物里出现任何 agent 编排框架依赖 = 直接失败(`CLAUDE.md §6.3`)。
- **薄**:核心循环目标 150–300 行;超出明显即停问人(`CLAUDE.md §6.8`)。
- **密钥**:trace / 日志 / spec 快照 / git 任一路径出现明文 key 即失败(`CLAUDE.md §6.5`)。
- Chat Completions 是已定决策;若实现中发现需切 Responses,先停问人(`CLAUDE.md §6.4`)。
