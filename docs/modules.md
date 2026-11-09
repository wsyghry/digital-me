# 模块说明 · 分身志

> 这份文件回答一个问题：**每个文件夹、每个文件到底是干什么的，改东西该动哪个。**
> 结构怎么来的、为什么这么分见 [decisions-digital-me.md](decisions-digital-me.md)；
> 怎么跑起来见 [usage.md](usage.md)；以后怎么改得更好见 [optimization.md](optimization.md)。

状态标记：✅ 已存在（当前阶段就是文档和空目录）、⏳ 计划中。

---

## 一、三层结构

一次请求永远按这个方向走：**前端 `web/` → 接口层 `app/api/` → 业务层 `app/services/` → 数据层 `app/db/` → `data/me.db`**。

- **前端**：只负责显示和把用户动作变成 HTTP 请求，不含任何判断逻辑。
- **接口层**：收参数、校验、调用业务函数、组装返回。它是唯一知道「HTTP」这回事的地方。
- **业务层**：真正干活的地方——怎么检索、怎么拼提示词、怎么调模型。它不知道请求是 GET 还是 POST。
- **数据层**：只有它认识 SQL。业务层要数据就调它的函数，不自己拼 SQL。
- **两个对外口子**：`app/db/` 通向本地 SQLite 文件，`app/services/llm.py` 通向 DeepSeek。除此之外没有任何别的地方出去。

带箭头和分组的完整图见 [architecture.html](architecture.html)（浏览器直接打开，可切暗色、可导出图片）。

**三条铁律**（写代码时守住，改需求时才不会牵一发动全身）：

1. **接口层不写 SQL**：`app/api/` 里出现 `SELECT` 就是放错地方了。
2. **数据层不调模型**：`app/db/` 不许 import `llm`，它不知道世界上有 AI。
3. **业务层不碰 HTTP**：`app/services/` 不解析请求、不返回 Response 对象，只接收普通 Python 参数。

依赖方向永远单向 `api → services → db`，反向 import 一律禁止。

---

## 二、逐文件说明

### 根目录

| 文件 | 作用 | 不做什么 | 状态 |
|---|---|---|---|
| `README.md` | 项目首页：是什么、怎么分、怎么开始 | 不写细节，细节在 docs/ | ✅ |
| `.env.example` | 配置模板，复制成 `.env` 填值 | 不含真实密钥 | ✅ |
| `.env` | 你的真实配置与 API Key | 不进 git | 本地生成 |
| `.gitignore` | 排除密钥、数据、虚拟环境、构建产物 | | ✅ |
| `requirements.txt` | Python 依赖清单 | 不锁死版本，用 `>=` | ✅ |
| `run.ps1` | 一键启动：检查环境 → 建 `.venv` → 装依赖 → 起服务 | 不做业务逻辑 | ⏳ P1 |

### `docs/` —— 文档区

| 文件 | 作用 |
|---|---|
| `decisions-digital-me.md` | 决策记录：定了什么、为什么。改主意要在这里标注被谁取代 |
| `data-schema.md` | 数据表字段、检索策略、导入格式、实测性能 |
| `modules.md` | 本文件：每个文件干什么、改哪里 |
| `usage.md` | 操作手册：怎么装、怎么用、出问题怎么办 |
| `optimization.md` | 优化清单：哪里能更好、什么代价、什么时候做 |
| `roadmap.md` | 阶段计划与验收标准 |
| `architecture.html` | 可视化架构图，浏览器直接打开，可亮/暗切换、可导出图片 |

### `app/` —— 后端

| 文件 | 作用 | 关键约束 | 阶段 |
|---|---|---|---|
| `main.py` | 创建 FastAPI 实例、注册路由、托管 `web/` 静态文件、启动时建库 | 只做组装，不写业务 | ⏳ P1 |
| `config.py` | 读 `.env`、算绝对路径、定义常量 | 全项目唯一读环境变量的地方 | ⏳ P1 |
| `api/routes.py` | 所有 HTTP 接口，一个接口一个函数 | 只做：取参数、调 service、返回结果 | ⏳ P1 |
| `api/schemas.py` | 请求/响应模型（Pydantic），顺带做参数校验与文档 | 不放业务规则 | ⏳ P1 |
| `db/schema.sql` | 建表、索引、FTS 虚拟表、同步触发器 | 数据结构的唯一出处，改动要同步更新 data-schema.md | ⏳ P1 |
| `db/store.py` | 连接管理、插入（算指纹去重）、查询、检索、统计 | 唯一可以直接写 SQL 的文件 | ⏳ P1 |
| `services/retrieve.py` | 把用户输入变成查询：分词、拼短语、两路检索（FTS / LIKE）、排序截断 | 不直接开数据库连接，向 store 要 | ⏳ P1 |
| `services/llm.py` | 调 DeepSeek：超时、重试、错误翻译成人话 | 唯一发起对外网络请求的文件 | ⏳ P2 |
| `services/persona.py` | 拼人格提示词：读 `prompts/persona.md` + 抽若干条我自己的真实发言当语气样本 | 不改数据库，只读 | ⏳ P2 |
| `services/chat.py` | 问答编排：检索命中 → 拼上下文 → 调模型 → 附上引用来源 | 不让模型凭空回答，没命中就说没有 | ⏳ P2 |
| `services/draft.py` | 拟稿：对方说了什么 + 我想表达什么 → 2 条候选回复 | 只生成草稿，绝不自动发送 | ⏳ P2 |
| `services/ingest.py` | 导入：jsonl 逐行校验（时间、正文必填）、算指纹、批量入库、出报告 | 不改写原文 | ⏳ P3 |

### `app/prompts/` —— 提示词正文

| 文件 | 作用 | 阶段 |
|---|---|---|
| `persona.md` | 人格设定：你是谁、怎么说话、什么绝对不许做（编造记忆、替人做决定、透露他人隐私） | ⏳ P2 |
| `ask.md` | 问答模板：怎么用检索到的片段回答、怎么承认不知道、怎么标注来源 | ⏳ P2 |
| `draft.md` | 拟稿模板：语气、长度、几条候选、不给什么建议 | ⏳ P2 |

单独成 `.md` 的原因：「像不像你」是这个项目的核心，语气要反复试。改 md 文件不用碰 Python，也不用重启进程。

### `web/` —— 前端（不需要打包）

| 文件 | 作用 | 阶段 |
|---|---|---|
| `index.html` | 页面骨架，三个页签：记录 / 搜索 / 分身 | ⏳ P1 |
| `app.js` | 所有交互，用原生 fetch 调接口 | ⏳ P1 |
| `style.css` | 样式，暗色为主，对齐个人网站的气质 | ⏳ P1 |
| `manifest.webmanifest` | 让手机浏览器能「添加到主屏幕」，像 App 一样全屏打开 | ⏳ P1 |

### `data/` —— 运行时数据

| 路径 | 内容 | 备注 |
|---|---|---|
| `data/me.db` | 全部消息、人物、会话 + 全文索引 | 一个文件就是全部，备份=拷它 |
| `data/raw/` | 微信 / QQ 导出的原始文件 | 原始文件不动，清洗结果另存 |

`data/` 整个不进 git，程序首次启动自动创建。

### `scripts/` 与 `tests/`

| 文件 | 作用 | 阶段 |
|---|---|---|
| `scripts/import_jsonl.py` | 命令行批量导入，打印导入报告 | ⏳ P3 |
| `scripts/backup.ps1` | 把 `me.db` 拷到指定目录，文件名带日期 | ⏳ P4 |
| `tests/conftest.py` | 测试夹具：每次用临时数据库，绝不碰真实数据 | ⏳ P1 |
| `tests/test_store.py` | 存储与检索（含两字查询、特殊字符、去重） | ⏳ P1 |
| `tests/test_api.py` | 接口行为（正常、缺参、超长） | ⏳ P1 |

---

## 三、三条主链路（按文件走一遍）

**记一句话**

1. `web/app.js` 把输入发给 `POST /api/messages`
2. `app/api/routes.py` 校验参数 → 调 `services` 里对应的写入函数
3. `db/store.py` 算指纹（时间+来源+会话+发送者+正文 的哈希），重复就跳过
4. `schema.sql` 里定义的触发器把正文同步进 `messages_fts`
5. 返回新记录 id，前端插到列表顶部

**搜一个词**

1. `web/app.js` → `GET /api/search?q=...`
2. `services/retrieve.py` 按空格切词，每个词转成短语
3. 词都 ≥3 字 → `db/store.py` 走 FTS5 `MATCH`；有短词 → 走 `LIKE` 兜底
4. 结果按时间倒序、去重、截断到前 N 条，带上会话名和来源回前端

**问一个问题**

1. `web/app.js` → `POST /api/chat`
2. `services/chat.py` 先调 `retrieve.py` 取相关记录（这就是「记忆」）
3. `persona.py` 拼系统提示（人格 + 语气样本），`ask.md` 拼问答模板
4. `llm.py` 调 DeepSeek：只有「问题 + 命中的几条片段」离开本机
5. 返回答案 + 引用了哪几条记录；没检索到就直说不知道，不外推

---

## 四、想改什么，动哪里

| 想改的东西 | 动这个文件 | 别动 |
|---|---|---|
| 分身说话的语气、口头禅 | `app/prompts/persona.md` | 不用碰代码 |
| 问答时引用几条、怎么措辞 | `app/prompts/ask.md` | |
| 回答太长/太短、几条候选 | `app/prompts/draft.md` + `services/draft.py` 的参数 | |
| 换模型厂商（如通义、Kimi） | 只改 `services/llm.py`（接口地址、请求体、返回解析） | 其他文件不用动 |
| 检索排不准 | `services/retrieve.py`（排序、截断、短词策略） | |
| 加字段、加表 | `db/schema.sql` + `db/store.py`，再更新 `docs/data-schema.md` | 别在 routes.py 里加 SQL |
| 加一个接口 | `api/routes.py` + `api/schemas.py` | 业务逻辑放 services |
| 界面改版 | `web/` 三个文件 | 不用重新打包，刷新即可 |
| 部署到服务器 | 见 `docs/usage.md` 第 8 节 | 不用改代码，搬 `me.db` 就行 |

---

## 五、命名与路径约定

- 数据库列名、jsonl 字段名：`snake_case`，全小写
- Python 函数：动词开头（`insert_message`、`search_messages`、`build_context`）
- 接口路径：`/api/` 下，资源用复数（`/api/messages`），动作类用动词（`/api/search`、`/api/chat`）
- 时间统一 ISO 8601 带时区（`2021-06-01T21:30:00+08:00`），库里以文本存，排序即按字典序，正确
- 项目路径全 ASCII（`D:\agent\digital-me`），数据路径可以中文，但建议也别放中文目录
