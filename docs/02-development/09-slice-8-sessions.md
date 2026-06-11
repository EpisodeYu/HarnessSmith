# 02·09 - Slice 8:会话持久化(resume / --continue / chat REPL)

> 目标:给生成产物补上事实标准 harness 的基础交互契约——**接着上一轮聊 / 恢复昨天的会话**。一次对话的消息正文落本地(`.harness/sessions/<id>.json`),CLI 加 `run --continue`/`--resume <id>` + 新增 `chat` 多轮 REPL,Web `/chat` 可按 `session` 续聊 + 会话列表。
>
> **缘起**:对标 2026 事实标准(Claude Code/Codex/Cursor/Cline 全员默认"恢复会话")发现的标配缺口,人 2026-06-07 立为 v1 必做切片(对标分析见 `../03-feature-landscape-and-proposals.md §3 T1-A`)。
>
> **状态:✅ 已完成(2026-06-07)。门禁全绿**:生成器快测 117 + golden 11(含 web/preset/多范式/mcp/skills/uvx + docker 2)+ 产物自带 `test_sessions.py` 9 + `test_web.py` 28(含 3 个会话续聊)全绿;`ReadLints` clean。
>
> **薄/红线**:零新增依赖(`json` + `Path`);纯运行期机制(`sessions` 活旋钮),**不改 spec schema、不改 LLM API 面**(不触 `CLAUDE.md §6`);属 §5.2 大改动(动范式核心 + 跨多文件,已跑全量回归)。

## 0. 边界与口径

- **会话正文 vs trace**:trace(`harness/trace.py`)只记角色/工具名/计数、**不记消息正文**;会话要"可续"必须存**消息正文**(含 assistant `tool_calls` + tool 结果),这是与 trace 不同的定位。**密钥不受影响**:api key 只在 `.env`,**永不进 `messages`**,所以"会话文件不含密钥"成立(门禁有断言)。
- **存的是会话正文,不含 system**:存储的 `messages` 去掉 system 消息;续聊时 system 由 `config` **每轮重建**,所以续聊后 prompt / rules / 采样等配置改动**即时生效**(不被旧 system 钉死)。
- **天花板 vs 地板**:会话是行为机制(行为轴),非安全边界;护栏仍靠 tool allowlist + 风险标记(结构轴,`01 §4`)。
- **默认开但可关**:`sessions.enabled` 默认 `true`(每次 `run` 自动写一份可续会话);`false` 时不落盘、行为退回单轮、零开销。机制始终在模板里(薄,~50 行),同 trace 的"始终生成、config 门控"。

## 1. 已拍板决策(人 2026-06-07,选择器确认)

- **① 存储**:默认开;每次 `run` 自动写 `.harness/sessions/<id>.json`(**单文件存整段 messages**,非 JSONL);`--continue` 接**最近一次**(按文件 mtime)。
- **② CLI**:**两者都做** —— `run --continue` / `--resume <id>`(单轮跨调用接力)+ 新增 `chat` 多轮 REPL(一次坐下连续多轮)。
- **③ Web**:**续聊纳入本片** —— `/chat?session=<id>` 后端载/存 + 前端记 session、"新会话"按钮、会话列表 + 历史渲染。

## 2. 交付物

### 共享脊柱(history 注入 + 取回 messages)
- 产物 `harness/paradigms/__init__.py`(模板)— `RunResult` 加 `messages: list[dict]`(本轮结束、**去掉 system** 的会话正文)。
- 产物 `harness/paradigms/{agent,plan,ask}.py`(模板)— 三处同构:加 `history: list[dict] | None = None` 参数;拼装 `[system] + (history or []) + [user]`;返回 `messages=messages[1:]`。
- 产物 `harness/loop.py`(模板)— `run()` 加 `history` 参数并透传。

### 存储核心
- 产物 `harness/session.py`(模板,**新增,always-render**)— 极薄:`new_id()` / `load(id, dir)` / `save(id, messages, dir, mode)` / `latest(dir)` / `resolve(continue_, resume_id, dir)`。文件结构 `{"id","created","updated","mode","messages":[...]}`。
- 产物 `harness/config.py`(模板)— `SessionsConfig(enabled: bool = True, dir: str = ".harness/sessions")` + `Config.sessions` + 进 `_empty_sections_to_defaults`。运行期旋钮,**无 spec 字段**。

### CLI
- 产物 `interfaces/cli.py`(模板)— `run` 加 `--continue`/`--resume <id>`(载入 history → `run_loop(history=...)` → `save`,结尾打印 `session: <id>`);新增 `chat` REPL(`while` 提示 → 累积 + 每轮落盘 → `/exit`/EOF 退出;支持 `--continue/--resume` 进入已有会话);抽 `_mcp_setup(config)` helper 供 `run`/`chat`/`serve` 共用。

### Web
- 产物 `interfaces/web.py`(模板)— `/chat` 加 `session` 参数(载 history + 跑完 `save` + 首发 `event: session`);新增 `GET /sessions`(列 `{id,updated,mode,preview}`)、`GET /sessions/{id}`(回 messages 供前端回放)。
- 产物 `interfaces/web_index.html`(模板)— 当前 session 跟踪 + 每次 `/chat` 带上;"新会话"按钮;会话列表(点选 → 回放 + 接续);中英 i18n。

### 边角 + 测试 + 文档
- `.gitignore`(模板)— 加 `.harness/`(会话含对话正文,同 traces 不入 git)。
- `config.yaml`(模板)— 加 `sessions:` 块 + 注释。
- 产物 `AGENTS.md` / `README.md`(模板)— 会话续聊用法 + "会话文件不含密钥"。
- `tests/test_sessions.py`(模板,**新增,always-render**)+ `tests/test_web.py`(模板,加 Web 续聊)。
- 子文档(本文)+ `00-overview §2` Slice 8 行回填。

## 3. 退出门禁(全绿)

- [x] **黄金路径**:preset/web 生成 → `uv sync && pytest`(含会话用例)绿 → mock 跑通一次工具调用。
- [x] **多轮存取 + 历史预置**:`run` 写会话;`--continue`/`--resume` 后第二轮 messages 正确含第一轮正文(产物 `test_sessions` + CLI 实测 `--continue` users=2)。
- [x] **会话文件不含密钥**:env 设 key,断言 key 值不在会话文件(`test_session_file_has_no_secret`)。
- [x] **关闭仍薄**:`sessions.enabled=false` 不落盘、行为退回单轮(`test_cli_run_disabled_sessions_writes_nothing`);零新增依赖(golden `uv.lock` FORBIDDEN 断言不含 langchain/langgraph/adk)。
- [x] **Web 续聊**:`/chat?session=` → `/sessions/{id}` 回放;新会话隔离(`test_web.py` 3 例)。
- [x] **大改动回归**(动范式核心 + 跨 ≥3 文件):golden 全量 11(thin/preset/web/mcp/skills/多范式/uvx)+ Docker build/run mock 全绿。
- [x] `ReadLints` clean。

## 4. 必须人审的决策点(已拍板,见 §1)

- [x] **① 默认落盘 + 位置/格式 = `.harness/sessions/<id>.json` 单文件、默认开、`--continue` 接最近**(人 2026-06-07)。
- [x] **② CLI 形态 = `run --continue/--resume` + `chat` REPL 都做**(人 2026-06-07)。
- [x] **③ Web 续聊纳入本片**(人 2026-06-07)。
- **软确认(非阻塞,`CLAUDE.md §5.3`)**:存储去掉 system 只存正文;`sessions` 作运行期 config(无 spec 字段);会话 id = `uuid4().hex[:12]`(同 trace `run_id` 风格)。

## 4b. 后续增强(2026-06-07,人定向:对标 Google AI Studio)

实现并验收(产物快测 web 32 / sessions 10、golden 11 含 docker、真实浏览器冒烟):

- **① Web 改 AI-Studio 式布局**:`web_index.html` 重构为**全高度双栏壳**——左侧固定栏(应用名 + "+ 新会话" + session 列表 + 底部 "⚙ 配置" 入口 + 语言),右侧主区全屏(顶部当前会话标题栏 + 聊天/配置切换)。session 由原下拉改为**侧栏列表**(标题显示、高亮当前、点选续聊)。`show()` 改驱动配置激活态 + 主标题,不再用顶部页签。
- **② 会话标题(LLM 生成,可配置 role)**:产物会话首轮**用 LLM 把首个问题压成短标题**,存入 `session.title`、经 SSE `title` 事件即时更新侧栏/标题栏。**标题 LLM = 可配置 role `title`**(与 `compaction` 同列,缺省回落 `generation`);`sessions.auto_title`(默认 true)开关;**Web 专属**(对标 Claude CLI:终端不自动起标题,故 CLI 不生成,仅会话文件带 `title` 字段)。时机=**先起标题再跑回答**(`title` 事件先于 `final`)。标题生成失败静默跳过(不影响对话,下轮重试)。prompt 参考 3GPP-Everything 的 `session_title.py`(只喂首问、要求仅输出标题、截断)。
- **③ 空会话处理**:空草稿(未发消息)**点"新会话"为 no-op**、**退出不持久化**(服务端只在完成一轮后落盘,空草稿永不产生文件);输入为空时发送被拦截(沿用既有)。
- **④ 侧栏会话重命名 / 删除(页面内联,非原生弹窗)**:每行 ✎ → 标题**就地变输入框**(Enter/失焦保存、Esc 取消);🗑 → 行内**就地展开** `删除 / 取消` 确认条(主题化、红色 Delete),点删除才发请求。`editingId`/`confirmingId` 驱动渲染,`commitRename`/`commitDelete` 提交;**不再用 `window.prompt`/`window.confirm`**(产物自带测试断言二者不出现)。后端 `session.py` 加 `set_title`/`delete`;`web.py` 加 `PATCH /sessions/{id}`(改标题、保留消息,缺会话 404)/ `DELETE /sessions/{id}`(幂等)。`_path` 用 `Path(id).name` 收窄,**杜绝路径穿越**(id 来自 URL)。删当前会话即回到空草稿。真机验证:✎→输入→Enter 改名落库、🗑→行内确认→删除清空。
- 交付物:`harness/session.py`(+`title` 存储/`title_of`/summaries 带 title;`set_title`/`delete`;`_path` 防穿越)、`harness/config.py`(`SessionsConfig.auto_title`)、`interfaces/web.py`(`_generate_title` + `/chat` auto_title + `title` SSE 事件 + `title` role 回落;`PATCH`/`DELETE /sessions/{id}`)、`interfaces/web_index.html`(壳重构 + 侧栏 + 标题 + 重命名/删除控件 + i18n)、`config.yaml`(`title` role 注释 + `sessions.auto_title`)。测试:`test_web.py`(+5:title 事件/持久化、auto_title 关、已设标题跳过、侧栏壳、重命名/删除路由)、`test_sessions.py`(+3:title 存储/保留、set_title+delete、路径穿越收窄)。

## 5. 本 slice 注意 / 留给后续

- **会话 ↔ trace 是两件事**:一次会话(可跨多 run)累积消息正文;每个 run 仍各写一份 trace(角色/计数)。二者目录不同(`.harness/sessions/` vs `traces/`),互不耦合。
- **压缩后的正文**:范式内 `fit_context` 可能折叠历史;存的是本轮结束后的(可能已压缩的)正文,使会话天然有界。
- **跨会话记忆(Slice 8B)** 紧随本片,**建在本片会话落盘基础设施之上**(记忆 = 自维护的少量长期笔记,与"会话历史"区分)。
- **不做**:会话级分支/编辑历史、多用户会话隔离(单租户,`01 §4`)、会话级预算账本(周期预算持久化 = Slice 14+)。
