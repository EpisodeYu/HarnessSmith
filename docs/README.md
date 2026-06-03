# HarnessForge 文档

| 文档 | 内容 |
| --- | --- |
| [00-research-and-feasibility.md](./00-research-and-feasibility.md) | Agent harness 概念调研(2026)、竞品盘点、立项意义、可行性与难度评估 |
| [01-project-plan.md](./01-project-plan.md) | 立项方案:定位/差异化、目标用户与成功指标、MVP 范围(分层)、设计原则、架构、关键技术决策、生成产物可运行性保障、验证标准、路线图(垂直切片)、风险 |
| [02-development/](./02-development/) | 分步开发文档(vibe coding + 垂直切片):总览/门禁/决策总表 + Slice 0–3 子文档。协作硬约束见项目根 [`CLAUDE.md`](../CLAUDE.md) |

> 开发协作模式:**Agent 主导执行,人主导决策/验证/环境与密钥配置**。入场顺序见 [`CLAUDE.md §11`](../CLAUDE.md)。

## 速读

- **是什么**:一个"配置即生成"的代码生成器。通过 CLI / Web 向导采集需求,产出一套**不绑定 agent 编排框架(LangChain/LangGraph/ADK)**、用户完全拥有可删改的独立 agent harness 代码仓库;生成后不再依赖 HarnessForge。
- **三个差异点**:无 agent 框架锁定(不是"无依赖")、own-your-code(eject 即所得)、配置即生成。
- **MVP 黄金路径(L1)**:原生 function-calling 循环(Chat Completions)→ 工具注册表 → 预算停止 → JSONL trace → CLI;并随产物落地**可运行性保障**(uv 契约 + 默认 Docker + 生成后冒烟自检)。MCP(stdio + 远程 HTTP/SSE,2026-06-03 定向)/ 多 profile 角色路由 / 极简 Web chat / 上下文策略为 L2;RAG ingest / 联网 MCP registry / Web 配置热重载等为 L3。
- **当前阶段**:规划完成,尚未开始编码。实现按 [02-development/](./02-development/) 的垂直切片推进(Slice 1 黄金路径为核心里程碑),协作守则见 [`CLAUDE.md`](../CLAUDE.md)。
