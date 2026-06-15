# AGENTS.md — HarnessSmith 快速上手

> 面向**在本仓库里干活的 Agent** 的导航地图：30 秒认清这是什么、代码在哪、怎么跑、怎么算"做完"。
> 这里只讲"怎么上手"；**硬约束与红线看 [`CLAUDE.md`](./CLAUDE.md)，定位 / 范围 / 决策总表看 [`docs/02-development/00-overview.md`](./docs/02-development/00-overview.md)**。两者冲突时以那两份为准。

## 1. 这是什么（一句话）

HarnessSmith 是 **agent harness 的代码生成器**（`create-next-app` for agent harnesses）：吃一份 `HarnessSpec`（YAML / preset / 向导采集），渲染出一个**完整、独立、无 agent 框架锁定**的 Python 仓库。生成的产物与本生成器**零运行期关系**——生成即脱离。

## 2. 两层心智（最重要，先记住）

任何改动，先问自己**改的是哪一层**：

| 层 | 位置 | 你在改什么 |
|---|---|---|
| **生成器本体** | `harnessmith/*.py`（`spec` / `generator` / `cli` / `scaffold` / `wizard` …） | spec schema、渲染引擎、CLI、向导、catalog、preset |
| **产物模板** | `harnessmith/templates/**/*.j2` | **渲染后**才是用户拿到的代码。改这里 = 改所有未来产物 |

推论：**测试必须覆盖"生成产物"本身**，不能只测生成器。黄金路径 = 生成 → `uv sync` → `pytest` → mock LLM 跑通一次 function-calling（见 §5）。

## 3. 仓库地图

```
harnessmith/                  # ← 生成器本体（这个包发布到 PyPI）
  spec.py                     # HarnessSpec（Pydantic v2 + YAML，extra=forbid）
  generator.py                # 渲染模板 → 写仓库 + git init + uv lock + 冒烟自检
  cli.py                      # Typer 入口：new / wizard / doctor
  scaffold.py                 # 生成器与 CLI 向导共享的烤默认 / slug 派生（纯 stdlib）
  cli_wizard.py               # 终端交互向导（questionary）
  node_bootstrap.py           # Node 系 MCP server 的离线预热 / node 直跑
  debuglog.py                 # 生成器侧 debug 日志
  catalog/mcp_servers.yaml    # 精选静态 MCP catalog（向导/CLI 预填数据源）
  presets/coding-assistant/   # 内置 preset（spec.yaml + mcp_prefill.yaml）
  wizard/                     # Web 向导（FastAPI 单页，[wizard] extra，绝不进产物）
  templates/                  # ← 产物模板（.j2）。渲染出的才是用户的代码
    src/__project_slug__/harness/    # 产物核心：loop/llm/llm_anthropic/tools/context/
                                     #   session/interaction/hooks/usage/trace/prompts/
                                     #   paradigms/ + mcp/skills/memory（opt-in）
    src/__project_slug__/interfaces/ # cli.py（+ web.py / web_index.html opt-in）
    tests/                           # 产物自带测试（mock LLM）
docs/02-development/          # 设计与切片文档（00-overview = 唯一口径）
tests/                        # ← 生成器自身的测试（test_spec / test_generator / test_golden …）
```

## 4. 常用命令（已验证）

```bash
uv sync                                              # 装生成器依赖
uv sync --extra wizard                               # 额外装 Web 向导依赖（FastAPI/uvicorn）

# 生成产物
uv run harnessmith new my-agent --preset coding-assistant   # 从 preset 非交互生成
uv run harnessmith new my-agent --spec ./harness.spec.yaml  # 从手写 spec 生成
uv run harnessmith new my-agent --no-verify                 # 跳过生成后冒烟（离线/快迭代）
uv run harnessmith wizard                                   # Web 向导
uv run harnessmith doctor                                   # 本机工具链预检

# 测试（golden 默认被 addopts 的 -m 'not golden' 排除）
uv run pytest -q                  # 快测（生成器单元 + 产物渲染，~200 例，约 20s）
uv run pytest -m golden           # 黄金快照：真生成 + uv sync + 产物 pytest（慢）
uv run pytest -m docker           # 需要 Docker daemon

# 发布前
uv build                          # 产 sdist + wheel 到 dist/
uvx twine check dist/*            # 校验元数据 + README 渲染
```

> 默认开发用 **mock LLM**，不需要真 key（CLI `--mock`）。真 key / 联网 / 花钱属"只能人做"，见 `CLAUDE.md §0.1 / §6`。

## 5. "完成"的硬门槛（详见 `CLAUDE.md §5`）

宣称做完前，至少：

- [ ] 新增 / 改动的生成器或模板代码**有自动化测试**。
- [ ] **黄金路径绿**：preset/示例 spec 生成 → `uv sync && pytest` 全绿 → mock 跑通一次 function-calling（含一次工具调用）。
- [ ] 断言生成的 `pyproject.toml` **不含 `langchain`/`langgraph`/`adk`**。
- [ ] 生成后冒烟自检绿；`ReadLints` 无新增告警。
- [ ] 动了 `HarnessSpec` / 模板核心 / 跨 ≥3 文件 → 额外跑 §5.2 回归（全量黄金 + Docker 冒烟 + `uvx harnessmith new` 冒烟）。

## 6. 红线速记（命中即停，详见 `CLAUDE.md §6`）

- **绝不**在产物里引入任何 agent 编排框架（LangChain/LangGraph/ADK）——定位红线。
- **薄优先**：默认产物核心循环 150–300 行；重能力（MCP/Web/skills/memory）只走 **spec 开关**，关闭 = 代码与依赖中均不存在。
- 改 `HarnessSpec` 字段语义、给**默认产物**加运行期依赖、改 LLM API 面、任何让**密钥进 git/spec/trace/日志**的路径 → 先停下请人审。
- **密钥**只进 gitignored `.env`；`config.yaml` / spec 只存 env 引用名。

## 7. HarnessSpec 速览（结构旋钮，决定生成什么）

`harnessmith/spec.py` 的 `HarnessSpec`（顶层字段）：

`version` · `project_slug`（产物包名，默认 `agent_harness`）· `display_name`（产物 UI/README 显示名）· `language`（产物 Web 默认语言 `en`/`zh`）· `llms`（每 profile 选 `provider: openai|anthropic`）· `roles` · `prompts`（`system` + `rules_files`）· `tools` · `paradigms`（`agent`/`plan`/`ask` 多选，默认 `["agent"]`）· `interfaces`（`cli`/`web`/`tui`）· `mcp.enabled` · `skills.enabled` · `memory.enabled` · `observability` · `context`（种子）· `rag`/`secrets`（预留）。

口径：**spec = 配方（生成什么 + 初值，结构轴）；产物 `config.yaml` = 运行期权威（行为轴）**。结构变更要重新生成，行为变更不用。

## 8. 入场阅读顺序

1. `README.md` —— 速览定位与产物能力。
2. `CLAUDE.md` —— 协作硬约束与红线（**必读**）。
3. `docs/02-development/00-overview.md` —— 定位 / 范围 / 决策总表 / 切片地图（**唯一口径**）。
4. 按当前任务**只读**相关 slice 子文档（`docs/02-development/` 下），别把全部塞进上下文。
