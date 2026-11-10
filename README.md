# 分身志 · digital-me

> 我的个人数据库与数字分身。
> 把散在微信、QQ 和脑子里的话收拢成一处，能搜、能回忆、能替你拟话。

**状态：P1 + P2 可用（2026-11-10）。本机能记、能看、能搜、能改、能删、能导出；分身能基于自己的记录回答并标出引用，也能拟回复草稿；手机在同一 WiFi 下可访问；导入、上云还没做。**

---

## 一、它是什么

| 是 | 不是 |
|---|---|
| 一个只属于你的私人语料库，数据存在你自己机器上 | 不是公开的聊天产品，不服务别人 |
| 一个能按你语气说话、但**只依据真实记录**回答的助手 | 不是通用聊天机器人，不会凭空编你不知道的事 |
| 一个帮你把消息拟好、你点一下再发的「草稿机」 | 不是自动代聊工具，不会伸手进微信替你发 |
| 一个可以随时往里写一句话的抽屉 | 不是笔记软件的替代品，不追求编辑体验 |

一句话：**它记得你说过什么，并且只说你确实说过的。**

---

## 二、架构（一张图看懂数据怎么走）

完整的可视化架构图在 [`docs/architecture.html`](docs/architecture.html)（用 archify 生成，可点开看）。

文字版的链路是这样：

```
入口（手机网页 / 电脑浏览器）
   │  记一句话、搜一个词、问一个问题、要一条回复草稿
   ▼
app/api/routes.py          接口层：只做收参、校验、调服务
   ▼
app/services/*             业务层
   ├── retrieve.py           检索：把问题变成要找的记录（关键词 → 以后加向量）
   ├── persona.py            人格：拼出「像你」的提示词 + 抽语气样本
   ├── chat.py               问答编排：检索 → 拼上下文 → 调模型
   ├── draft.py              拟稿：按对方的话 + 你的意图生成备选回复
   └── ingest.py             导入：jsonl / 微信 / QQ 三种适配
   ▼
app/db/store.py            数据层：唯一碰 SQLite 的地方
   ▼
data/me.db                 全部数据，一个文件，拷走就是备份
```

两处对外接触点，各自只有一个出口：

- **DeepSeek API**（项目外部）—— 只在 `app/services/llm.py` 里被调用
- **SQLite**（内嵌，不是服务）—— 只在 `app/db/store.py` 里被访问

所以以后想换模型、换数据库，各自只改一个文件。

---

## 三、目录与文件地图

```
digital-me/
├── README.md                    本文件，架构总览与文件说明　✅
├── .env.example                 配置模板，复制成 .env 后填写　✅
├── .gitignore                   排除 .env、data/、.venv、.archify　✅
├── requirements.txt             Python 依赖（fastapi / uvicorn / httpx / python-dotenv）　✅
├── run.ps1                      一键启动 / 停止（-Background 后台、-Stop 停止）　✅
│
├── docs/                        文档区，给人看的
│   ├── modules.md               每个文件干什么、改哪里，先从这份看起　✅
│   ├── usage.md                 怎么装、怎么用、出问题怎么办　✅
│   ├── optimization.md          哪里能优化、代价多少、什么时候做　✅
│   ├── decisions-digital-me.md  决策记录：每条为什么这么定　✅
│   ├── data-schema.md           数据表字段、检索方式与实测性能　✅
│   ├── roadmap.md               P0~P5 阶段计划与验收标准　✅
│   ├── pending.md               还没做的功能清单、今晚可直接跑的步骤　✅
│   └── architecture.html        可视化架构图（archify 生成）　✅
│
├── app/                         后端
│   ├── main.py                  入口：创建应用、挂路由、托管 web/　✅
│   ├── config.py                配置：读 .env、定义路径与常量　✅
│   ├── api/
│   │   ├── routes.py            所有 HTTP 接口，一个接口一段　✅
│   │   └── schemas.py           请求/响应模型（Pydantic）　✅
│   ├── db/
│   │   ├── schema.sql           建表与索引，数据结构的唯一出处　✅
│   │   └── store.py             增删查改、全文检索　✅
│   ├── services/
│   │   ├── llm.py               DeepSeek 调用，唯一对外请求处　✅
│   │   ├── retrieve.py          检索编排：FTS 命中 + 短词兜底　✅
│   │   ├── persona.py           人格提示词组装、语气样本抽取　✅
│   │   ├── chat.py              问答编排：先检索，没命中不调模型　✅
│   │   ├── draft.py             回复草稿生成，只出草稿不发　✅
│   │   └── ingest.py            导入适配（jsonl / 微信 / QQ）　⏳ P3
│   └── prompts/                 提示词正文，改语气不用改代码
│       ├── persona.md           人格设定（你是谁、怎么说话、什么不许做）　✅
│       ├── ask.md               问答模板　✅
│       └── draft.md             拟稿模板　⏳ P2
│
├── web/                         前端（无构建步骤，改完刷新即可）
│   ├── index.html               页面骨架与三个页签　✅
│   ├── app.js                   交互逻辑，全部 fetch 调用　✅
│   ├── style.css                样式　✅
│   └── manifest.webmanifest     让手机能「添加到主屏幕」　✅
│
├── data/                        运行时数据（不进 git，程序首次启动自动创建）
│   ├── me.db                    全部数据（首次启动自动生成）
│   └── raw/                     微信 / QQ 导出的原始文件先放这里
│
├── scripts/                     一次性或命令行工具
│   ├── import_jsonl.py          把 jsonl 批量灌进库　⏳ P3
│   └── backup.py                备份 me.db（运行中也能安全拷）　✅
│
└── tests/                       测试
    └── test_core.py             去重、两字/三字/标点检索、改删导出　✅
```

**✅ = 已存在，⏳ = 待建（后面括号里是落在哪个阶段）。**

### 为什么这么分

- **一层只干一类事**：接口层不写业务，业务层不写 SQL，数据层不懂 HTTP。改需求时定位快。
- **提示词单独成文件**：这个项目的核心竞争力是「像你」，语气要反复调。放 md 里改，不用碰 Python。
- **data/ 独立**：所有会变的东西集中一处，备份就是拷文件夹，`.gitignore` 一拦也不会误提交。
- **web/ 免构建**：一个人维护的项目，不引入打包工具能省掉一半的调试时间。

---

## 四、快速开始

> 已可用。首次运行前需先建虚拟环境并装依赖（见下）。

```powershell
cd D:\agent\digital-me
.\run.ps1                      # 前台启动，会打印手机访问地址
# 或：.\run.ps1 -Background  后台跑；.\run.ps1 -Stop  停止
# 浏览器打开 http://localhost:8000
```

手机访问：同一 WiFi 下打开 `http://<电脑局域网IP>:8000`。

---

## 五、配置项（.env）

| 字段 | 说明 | 必填 |
|---|---|---|
| `DEEPSEEK_API_KEY` | 大模型密钥，没填则分身不可用，其余功能正常 | P2 起必填 |
| `LLM_BASE` | 接口地址，默认 `https://api.deepseek.com` | 否 |
| `LLM_MODEL` | 模型名，默认 `deepseek-flash` | 否 |
| `PERSONA_NAME` | 分身对外称呼，默认「我」 | 否 |
| `ME_DB` | 数据库路径，默认 `data/me.db` | 否 |

---

## 六、数据从哪来

| 来源 | 方式 | 阶段 |
|---|---|---|
| 随手记 | 手机网页打字或语音 | P1 |
| 微信 | PC 端导出 → 解密 → 清洗成 jsonl → 导入 | P3 |
| QQ | 同微信，另一套解析 | P3 |

导入统一格式（每行一条）：

```json
{"ts":"2021-06-01T21:30:00+08:00","source":"wechat","conv":"老王","sender":"me","is_me":1,"text":"明天几点","kind":"text"}
```

字段含义见 [`docs/data-schema.md`](docs/data-schema.md)。

---

## 七、路线图

详见 [`docs/roadmap.md`](docs/roadmap.md)。

| 阶段 | 内容 | 验收标准 |
|---|---|---|
| P0 | 骨架与文档 | 目录就位，本文可读 |
| P1 | 记录 + 搜索　✅ | 手机记一句，能搜到（已验证） |
| P2 | 分身对话 + 拟稿 | 回答引用真实记录，语气接近本人 |
| P3 | 微信/QQ 导入 | 能搜到三年前的旧事 |
| P4 | 部署到云服务器 | 外网可用，HTTPS 正常 |
| P5 | 对外窗口 / 语气微调 | 另议 |

---

## 八、明确不做与已知风险

- **不做自动代聊**：不接入微信协议、不 hook 客户端。以你的身份自动回复他人既有封号风险，也可能构成冒充。
- **不把整库丢给第三方**：只有「你问的那一句 + 检索到的几条片段」会发给模型。
- **他人的话属于他人**：语料里有大量别人说的内容，对外提供前必须脱敏，这是法律要求不是洁癖。
- **无独显**：本地不训练模型，微调只在云端临时租卡时进行。

---

## 九、文档索引

| 想了解 | 看这个 |
|---|---|
| 每个文件是干什么的、改东西该动哪 | [`docs/modules.md`](docs/modules.md) |
| 怎么装、怎么用、出问题怎么办 | [`docs/usage.md`](docs/usage.md) |
| 以后能怎么优化、什么时候做 | [`docs/optimization.md`](docs/optimization.md) |
| 为什么这么决定 | [`docs/decisions-digital-me.md`](docs/decisions-digital-me.md) |
| 数据表长什么样 | [`docs/data-schema.md`](docs/data-schema.md) |
| 后面怎么推进 | [docs/roadmap.md](docs/roadmap.md) |
| 还没做什么、今晚先干什么 | [docs/pending.md](docs/pending.md) |
| 架构长什么样 | [`docs/architecture.html`](docs/architecture.html) |
