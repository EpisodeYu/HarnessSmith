# HarnessSmith 文档

开发与设计文档收敛在 [`02-development/`](./02-development/) 一处。入口是 [`02-development/00-overview.md`](./02-development/00-overview.md)——「设计与决策」主参考(定位、范围、设计原则、架构、关键技术决策、能力路线图、命名与红线);各能力的详细设计见同目录下的切片子文档。协作硬约束见项目根 [`CLAUDE.md`](../CLAUDE.md)。

| 文档 | 内容 |
| --- | --- |
| [`02-development/00-overview.md`](./02-development/00-overview.md) | 设计与决策主参考(唯一口径) |
| [`02-development/01-slice-0`…`13-slice-13`](./02-development/) | 各能力切片子文档(骨架 / 黄金路径 / 路由+上下文 / 产物 Web / MCP / 多范式 / 工具基线+SKILL / 全局 rule / wizard / 会话 / 记忆 / 停止续聊重问 / HITL+ask / MCP 管理 / TUI) |
| [`02-development/125-slice-12-anthropic-dual-spec.md`](./02-development/125-slice-12-anthropic-dual-spec.md) | 原生 OpenAI+Anthropic 双规范 + 推理流式 |
| [`02-development/14-forge-add-incremental-regeneration.md`](./02-development/14-forge-add-incremental-regeneration.md) | `forge add` 增量再生成 / 模板升级(v1+ 结构性护城河设计) |
| [`02-development/15-llm-robustness-and-context.md`](./02-development/15-llm-robustness-and-context.md) | LLM 上下文工程正确性 + 调用鲁棒性 |

## 速读

- **是什么**:一个「配置即生成」的代码生成器。通过 CLI / Web 向导采集需求,产出一套**不绑定 agent 编排框架(LangChain/LangGraph/ADK)**、用户完全拥有可删改的独立 agent harness 代码仓库;生成后不再依赖 HarnessSmith。
- **三个差异点**:无 agent 框架锁定(不是「无依赖」)、own-your-code(eject 即所得)、配置即生成。
- **能力概览**:原生 function-calling 循环 + 工具注册表 + 多范式(agent/plan/ask)+ MCP 工具 + Agent Skills + 全局 rule + 会话持久化 + 跨会话记忆 + 停止/继续/重问 + HITL/ask_question 交互 + 双协议 LLM(OpenAI 兼容 + 原生 Anthropic)+ 上下文管理 + 按 LLM 成本账本 + JSONL trace;可选 Web/TUI 接口;并随产物落地可运行性保障(uv 契约 + 默认 Docker + 生成后冒烟自检)。详见 [`00-overview.md`](./02-development/00-overview.md)。
