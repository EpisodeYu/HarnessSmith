# 02·09 - Slice 8:会话持久化(resume / --continue / chat REPL)

> 目标:给生成产物补上事实标准 harness 的基础交互契约——**接着上一轮聊 / 恢复昨天的会话**。一次对话的消息正文落本地(`.harness/sessions/<id>.json`),CLI 加 `run --continue`/`--resume <id>` + 新增 `chat` 多轮 REPL,Web `/chat` 可按 `session` 续聊 + 会话列表。
>
> 前置:Slice 7 门禁全绿。
>
> **薄/红线**:零新增依赖(`json` + `Path`);纯运行期机制(`sessions` 活旋钮),不改 spec schema、不改 LLM API 面;属大改动(动范式核心 + 跨多文件,跑全量回归)。

## 0. 边界与口径

- **会话正文 vs trace**:trace 只记角色/工具名/计数、不记消息正文;会话要「可续」必须存**消息正文**(含 assistant `tool_calls` + tool 结果)。**密钥不受影响**:api key 只在 `.env`、永不进 `messages`,所以「会话文件不含密钥」成立(门禁有断言)。
- **存的是会话正文,不含 system**:存储的 `messages` 去掉 system 消息;续聊时 system 由 `config` 每轮重建,所以续聊后 prompt / rules / 采样等配置改动即时生效。
- **天花板 vs 地板**:会话是行为机制(行为轴),非安全边界。
- **默认开但可关**:`sessions.enabled` 默认 `true`(每次 `run` 自动写一份可续会话);`false` 时不落盘、行为退回单轮、零开销。机制始终在模板里(薄,~50 行)。

## 1. 关键决策

- **① 存储**:默认开;每次 `run` 自动写 `.harness/sessions/<id>.json`(单文件存整段 messages,非 JSONL);`--continue` 接最近一次(按文件 mtime)。
- **② CLI**:两者都做 —— `run --continue` / `--resume <id>`(单轮跨调用接力)+ 新增 `chat` 多轮 REPL。
- **③ Web**:续聊纳入本片 —— `/chat?session=<id>` 后端载/存 + 前端记 session、「新会话」按钮、会话列表 + 历史渲染。

## 2. 交付物

### 共享脊柱(history 注入 + 取回 messages)
- 产物 `harness/paradigms/__init__.py` — `RunResult` 加 `messages: list[dict]`(本轮结束、去掉 system 的会话正文)。
- 产物 `harness/paradigms/{agent,plan,ask}.py` — 三处同构:加 `history: list[dict] | None = None`;拼装 `[system] + (history or []) + [user]`;返回 `messages=messages[1:]`。
- 产物 `harness/loop.py` — `run()` 加 `history` 参数并透传。

### 存储核心
- 产物 `harness/session.py`(**新增,always-render**)— 极薄:`new_id()` / `load(id, dir)` / `save(id, messages, dir, mode)` / `latest(dir)` / `resolve(continue_, resume_id, dir)`。文件结构 `{"id","created","updated","mode","title","messages":[...]}`。`_path` 用 `Path(id).name` 收窄防穿越。
- 产物 `harness/config.py` — `SessionsConfig(enabled: bool = True, dir: str = ".harness/sessions", auto_title: bool = True)` + `Config.sessions`。运行期旋钮,无 spec 字段。

### CLI / Web
- 产物 `interfaces/cli.py` — `run` 加 `--continue`/`--resume <id>`(载入 history → 跑 → save,结尾打印 `session: <id>`);新增 `chat` REPL(累积 + 每轮落盘 → `/exit`/EOF 退出;支持 `--continue/--resume`);抽 `_mcp_setup(config)` helper 供 `run`/`chat`/`serve` 共用。
- 产物 `interfaces/web.py` — `/chat` 加 `session` 参数(载 history + 跑完 save + 首发 `event: session`);`GET /sessions`(列 `{id,updated,mode,title,preview}`)、`GET /sessions/{id}`(回 messages 供回放)、`PATCH /sessions/{id}`(改标题)、`DELETE /sessions/{id}`(幂等)。会话首轮**自动起标题(临时标题 + LLM 并行精修)**:先用用户首条消息(裁剪到首行/≤40 字)作零成本临时标题、紧随 `run`/`session` 即时发 SSE `title`;再在后台线程并行用 LLM 精修(可配置 role `title`,缺省回落 `generation`)发第二个 `title` 覆盖,worker 收尾 `save` 时落盘其中胜出者,LLM 失败/超时则保留临时标题。**标题调用不再阻塞首事件**——`run`/`session` 先于标题发出,run_id 即时可用、Stop 立即可按,消除思考型模型(如 mimo)起标题导致的首事件长静默窗口。`sessions.auto_title` 开关;Web 专属。
- 产物 `interfaces/web_index.html` — 全高度双栏壳(左 session 侧栏 + 右全屏),会话列表、「新会话」、侧栏内联重命名/删除(不用 `window.prompt`/`window.confirm`)、中英 i18n。空草稿不新建/不持久化。

### 边角
- `.gitignore` 加 `.harness/`(会话含对话正文,同 traces 不入 git）。
- `config.yaml` 加 `sessions:` 块 + `title` role 注释。
- 产物 `AGENTS.md` / `README.md`(会话续聊用法 + 「会话文件不含密钥」)。
- `tests/test_sessions.py`(新增)+ `tests/test_web.py`(Web 续聊)。

## 3. 退出门禁

- 黄金路径:preset/web 生成 → `uv sync && pytest`(含会话用例)绿 → mock 跑通一次工具调用。
- 多轮存取 + 历史预置:`run` 写会话;`--continue`/`--resume` 后第二轮 messages 正确含第一轮正文。
- 会话文件不含密钥(env 设 key,断言 key 值不在会话文件)。
- 关闭仍薄:`sessions.enabled=false` 不落盘、行为退回单轮;零新增依赖。
- Web 续聊:`/chat?session=` → `/sessions/{id}` 回放;新会话隔离;侧栏重命名/删除路由 + 路径穿越收窄。
- 大改动回归(动范式核心 + 跨 ≥3 文件):golden 全量 + Docker build/run mock。
- `ReadLints` clean。

## 4. 本 slice 注意 / 留给后续

- **会话 ↔ trace 是两件事**:一次会话(可跨多 run)累积消息正文;每个 run 仍各写一份 trace。二者目录不同(`.harness/sessions/` vs `traces/`)。
- **压缩后的正文**:范式内 `fit_context` 可能折叠历史;存的是本轮结束后的(可能已压缩的)正文,使会话天然有界。
- **跨会话记忆(Slice 8B)** 紧随本片,建在本片会话落盘基础设施之上(记忆 = 自维护的少量长期笔记,与「会话历史」区分)。
- **不做**:会话级分支/编辑历史(重问见 Slice 9）、多用户会话隔离(单租户)、会话级预算账本(周期预算持久化 = v1+)。
