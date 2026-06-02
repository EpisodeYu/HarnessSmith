# HarnessForge 文档

| 文档 | 内容 |
| --- | --- |
| [00-research-and-feasibility.md](./00-research-and-feasibility.md) | Agent harness 概念调研(2026)、竞品盘点、立项意义、可行性与难度评估 |
| [01-project-plan.md](./01-project-plan.md) | 立项方案:定位/差异化、MVP 范围、设计原则、架构、验证标准、已确认决策、路线图 |

## 速读

- **是什么**:一个"配置即生成"的代码生成器。通过 Web 向导 / CLI 采集需求,产出一套**不依赖 LangGraph/LangChain**、用户完全拥有可删改的独立 agent harness 代码仓库。
- **三个差异点**:framework-free、own-your-code(eject 即所得)、配置即生成。
- **MVP 闭环**:多 LLM profile + 角色路由 → 原生 function-calling 循环 → MCP 工具(stdio+HTTP)→ 可选 RAG(含 ingest)→ 上下文预算管理 → 轻量护栏 + 可观测 → CLI/Web 调用。
- **当前阶段**:规划完成,尚未开始编码。实现按 [01-project-plan.md](./01-project-plan.md) 第 9 节路线图推进。
