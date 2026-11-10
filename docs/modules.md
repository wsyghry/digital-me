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
| `run.ps1` | 一键启动：检查环境 → 建 `.venv` → 装依赖 → 起服务 | 不做业务逻辑 | ✅ |

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
| `main.py` | 创建 FastAPI 实例、注册路由、托管 `web/` 静态文件、启动时建库 | 只做组装，不写业务 | ✅ |
| `config.py` | 读 `.env`、算绝对路径、定义常量 | 全项目唯一读环境变量的地方 | ✅ |
| `api/routes.py` | 所有 HTTP 接口，一个接口一个函数（清单见下） | 只做：取参数、调 service、返回结果 | ✅ |
| `api/schemas.py` | 请求/响应模型（Pydantic），顺带做参数校验与文档 | 不放业务规则 | ✅ |
| `db/schema.sql` | 建表、索引、FTS 虚拟表、同步触发器 | 数据结构的唯一出处，改动要同步更新 data-schema.md | ✅ |
| `db/store.py` | 连接管理、插入（算指纹去重）、改写、删除、检索、导出、统计 | 唯一可以直接写 SQL 的文件 | ✅ |
| `services/retrieve.py` | 把用户输入变成查询：分词、拼短语、两路检索（FTS / LIKE）、排序截断 | 不直接开数据库连接，向 store 要 | ✅ |
| `services/llm.py` | 调 DeepSeek：超时、重试、401/402/429 错误翻译成人话 | 唯一发起对外网络请求的文件 | ✅ |
| `services/persona.py` | 拼人格提示词：读 `prompts/persona.md` + 取最近几条我自己的真实发言当语气样本 | 不改数据库，只读；样本固定不随机，提示词前缀稳定才能吃缓存价 | ✅ |
| `services/chat.py` | 问答编排：整句退成二元组检索 → 命中才拼上下文 → 调模型 → 附引用 | 没命中直接回「没记过」，一个 token 都不花 | ✅ |
| `services/draft.py` | 拟稿：对方说了什么 + 我想表达什么 → 2~3 条候选，会洗掉模型加的编号和引号 | 只生成草稿，绝不自动发送 | ✅ |
| `services/ingest.py` | 导入：jsonl 逐行校验（时间、正文必填）、算指纹、批量入库、出报告 | 不改写原文 | ⏳ P3 |

### `app/prompts/` —— 提示词正文

| 文件 | 作用 | 阶段 |
|---|---|---|
| `persona.md` | 人格设定：你是谁、怎么说话、什么绝对不许做（编造记忆、替人做决定、透露他人隐私） | ✅ |
| `ask.md` | 问答模板：怎么用检索到的片段回答、怎么承认不知道、怎么标注来源 | ✅ |
| `draft.md` | 拟稿模板：语气、长度、两条候选、只输出草稿 | ✅ |

单独成 `.md` 的原因：「像不像你」是这个项目的核心，语气要反复试。改 md 文件不用碰 Python，也不用重启进程。

### `web/` —— 前端（不需要打包）

| 文件 | 作用 | 阶段 |
|---|---|---|
| `index.html` | 页面骨架，三个页签：记录 / 搜索 / 分身 | ✅ |
| `app.js` | 所有交互，用原生 fetch 调接口 | ✅ |
| `style.css` | 样式，暗色为主，对齐个人网站的气质 | ✅ |
| `manifest.webmanifest` | 让手机浏览器能「添加到主屏幕」，像 App 一样全屏打开 | ✅ |

### `data/` —— 运行时数据

| 路径 | 内容 | 备注 |
|---|---|---|
| `data/me.db` | 全部消息、人物、会话 + 全文索引 | 一个文件就是全部，备份=拷它 |
| `data/raw/` | 微信 / QQ 导出的原始文件 | 原始文件不动，清洗结果另存 |

`data/` 整个不进 git，程序首次启动自动创建。

### `scripts/` 与 `tests/`

| 文件 | 作用 | 阶段 |
|---|---|---|
| `scripts/backup.py` | 用 SQLite backup API 备份 `me.db`，服务运行中也能安全拷，默认存到 `backups/` | ✅ |
| `scripts/check.ps1` | 一键自检：venv、28 项单元测试、服务健康、关键文件；只读，不联网不花钱 | ✅ |
| `scripts/import_jsonl.py` | 命令行批量导入，打印导入报告 | ⏳ P3 |
| `tests/test_core.py` | 关键路径测试：去重、两字/三字/标点检索、改后重建索引、删除、导出。用临时库，不碰真实数据 | ✅ |

跑测试：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

> 只覆盖会算错的地方。界面点了好不好看，靠人看，不写测试。

### 接口清单（现在能用的）

| 方法 | 路径 | 干什么 |
|---|---|---|
| `POST` | `/api/messages` | 记一条，重复内容返回 `duplicated: true` |
| `GET` | `/api/messages?limit=&before_id=&start=&end=` | 按时间倒序取一页，`before_id` 往前翻，`start`/`end` 按日期筛 |
| `PATCH` | `/api/messages/{id}` | 改正文，索引自动跟着重建；改成和别的记录一样会 409 |
| `DELETE` | `/api/messages/{id}` | 删一条，不存在回 404 |
| `GET` | `/api/search?q=&start=&end=` | 两路检索：≥3 字走 FTS，短词走 LIKE；可加日期范围 |
| `GET` | `/api/days` | 日期索引：哪天有几条，给下拉框用 |
| `GET` | `/api/export.md` | 全部记录导成 Markdown（按日期分组） |
| `POST` | `/api/chat` | 提问：检索命中才调模型，返回答案 + 引用；没配 Key 回 503 |
| `POST` | `/api/draft` | 拟稿：`theirs` + `intent` → 2~3 条候选（只出草稿） |
| `GET` | `/api/health` | 条数、库体积、`llm`（Key 是否已配） |

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

**按日期翻**

1. `web/app.js` 的日期条（全部 / 今天 / 昨天 / 近 7 天 / 下拉选某天）算出 `start`、`end`
2. 列表 → `GET /api/messages?start=&end=`；搜索 → `GET /api/search?q=&start=&end=`
3. `db/store.py` 的 `_date_clause()` 把日期变成 `substr(ts,1,10)` 的比较（`ts` 是带时区的 ISO 串，前 10 位就是本地日期）
4. 下拉框的可选日期来自 `GET /api/days` → `store.days()`，按天 `GROUP BY` 数条数
5. 前端拿到结果后按天插小标题（`11月10日 · 周二`），列表与搜索共用 `dayHeadEl()`

**改一条 / 删一条 / 导出**

1. 改：`web/app.js` → `PATCH /api/messages/{id}` → `routes.py` → `store.update_message()` 重算指纹 → `schema.sql` 的触发器同步改 `messages_fts`（改完旧词就搜不到了，测试里专门验这一条）
2. 删：`DELETE /api/messages/{id}` → `store.delete_message()` → 触发器把索引里的那条一并删掉
3. 导出：`GET /api/export.md` → `store.export_markdown()` 按日期分组拼 Markdown → 浏览器直接下载

**问一个问题**

1. `web/app.js` → `POST /api/chat`
2. `services/chat.py` 调 `retrieve.search_for_question()`：整句在中文里搜不到，先切成相邻两字，按命中的二元组个数排序（这就是「记忆」）
3. 一条都没命中 → 直接返回「我没记过这件事」，**不调模型、不花钱**
4. `persona.py` 拼系统提示（人格 + 语气样本），`ask.md` 拼问答模板，只塞命中的那几条
5. `llm.py` 调 DeepSeek：只有「问题 + 命中的几条片段」离开本机
6. 返回答案 + 引用了哪几条记录，前端把引用单独列出来

**拟一条回复**

1. `web/app.js` → `POST /api/draft`，带上对方原话 + 我想表达的意思
2. `services/draft.py` 用同一份人格提示词 + `draft.md` 模板调模型
3. `parse_candidates()` 洗掉编号、引号、多余空行，最多留 3 条
4. 前端只渲染草稿 + 「复制」按钮，没有发送入口——发不发由人决定

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
