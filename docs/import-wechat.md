# 微信历史导入（P3）方案与分工

写于 2026-11-11。目标：把微信历史聊天导进 `data/me.db`，让「按日期翻」「搜旧事」「分身引用历史」三件事对历史数据同样成立。

## 一、两条路线

| | 路线 A：兜底通道（先做） | 路线 B：wechatauto-replica（批量） |
|---|---|---|
| 数据来源 | 微信自带「多选 → 合并转发 → 转发到其他应用」产出的 zip / txt | 读微信进程内存取密钥，解密本地 SQLCipher 库 |
| 依赖 | 无 | `wechatauto-replica` 1.2.10（PyPI，Apache-2.0） |
| 覆盖 | 一次一个会话（手动选） | 一次可导全部会话，可只导本人发言 |
| 风险 | 零（不碰密钥、不碰进程） | 只读、不注入、不发消息；仍需你明确同意 |
| 耗时 | 半天（写解析器 + 跑通链路） | 装依赖 5 分钟 + 导出 1~2 分钟 |
| 用途 | 先把「导入 → 写库 → 搜索 → 分身引用」验证通 | 验证通之后再灌几十万条 |

**顺序不能反**：先用路线 A 的小样本把链路跑通，再用路线 B 批量。否则一次导错，几万条脏数据要重来。

## 零、本机实测（2026-11-11 已验证）

工具装在独立环境 `D:\agent\_tools\wechat-export\.venv`（Python 3.12.2 / 64 位），与项目 `.venv` 隔离，不污染项目依赖。

| 检查项 | 实测结果 |
|---|---|
| 账号识别 | `wxid_rop4b7q3pe0322_91e3` |
| 数据库密钥 | **28/28 个库可解密** |
| 图片密钥 | 已拿到并缓存（之后可离线） |
| 控件树 | 拿不到（只影响「发消息 / 下载原图」，**不影响读**） |
| 会话总数 | **470 个** |
| 命令形态 | 子命令式：`doctor` / `sessions` / `messages` / `export` / `images` / `moments` / `labels` / `forward` / `send` / `addfriend` |
| 只读可用命令 | `doctor`、`sessions`、`messages --json`、`export`、`images`、`moments` |
| 禁用命令 | `send`、`forward`、`labels send`、`addfriend`、`remark`（会驱动微信窗口对外发消息，不碰） |

`messages --json` 的单条字段（与指南描述基本一致，但 `type` 是**中文串**而不是 int）：

```json
{"local_id": 34, "type": "文本", "sender_id": 2, "sender_username": "wxid_...",
 "create_time": 1794212602, "content": "...", "sort_seq": 1794212602000, "shard": "message__message_4.db"}
```

实测类型值：`文本`、`文件/链接/卡片`、`图片`、`系统消息`。

抽样统计（每会话取最近 200 条）：

| 口径 | 数字 |
|---|---|
| 自聊会话（发给自己） | 93 条 → 保留 46 条文本（**49.5%**），时间从 2023-09-26 起 |
| 最近 15 个会话合计 | 2019 条 → 1383 条文本（**68.5%**） |
| 其中本人发言 | **9 条（0.4%）** |

**结论：指南里的 22% 是「本人发言」口径，不是「文本占比」口径。** 最近 15 个会话几乎全是群，群里的文本量大但本人几乎不发言，所以想拿「我怎么说」的语料，主力在私聊，不能靠群聊。

三个已踩到的坑：

1. `messages.created_at` 是 `NOT NULL` 且没有默认值。绕开 `store.insert_message` 直接写 SQL 会报 `IntegrityError: NOT NULL constraint failed: messages.created_at`；如果用 `insert or ignore`，错误会被**静默吞掉**，表现为「读到 93 条、保留 0 条」。导库必须走 `store.insert_message`，或在 SQL 里显式补 `created_at`。
2. FTS 是 trigram，**少于 3 个字的查询不命中**（搜「文件」返回 0）。短词要靠 LIKE 兜底，或换更长的词验证。
3. `export` 生成的 txt 里非文本消息会显示成 `[非文本正文]` + 原始 XML，不适合直接作导入源；**导入走 `--json`**，格式稳定。

探针脚本：`D:\agent\digital-me\.archify\probe_wechat_import.py`（只读，写临时库，不碰 `me.db`）。

### 0.1 群聊导入与人物表（2026-11-11 晚，已验证）

- 群聊用同一个导入器，加 `--include-groups --limit-per-chat 300 --min-messages 20`：109 个群，读 23081 条 → 新增 **10058 条**，库内从 7357 涨到 **17478 条**（19636 KB）。
- 顺序：`db.get_messages(..., limit, offset)` 是**最新在前**，所以 `--limit-per-chat N` 取的是每群最近 N 条，符合「逐步放进来」。
- 发送者：群里 `sender_username` 是 wxid，导入时用 `db.get_nickname()` 换成昵称（如 `wxid_ssed57qzrgzq22` → 比奇堡）；私聊保持 wxid，避免指纹变化导致重复导入。
- 正文前缀：群消息正文常以「`wxid_xxx:` + 换行」开头，实测去掉 **8663 条**；只认 `wxid_` 开头或与 sender 完全相同的短 head，避免把 `data:` 这类正文误伤。
- 群名：部分群 `get_nickname()` 只返回 `xxx@chatroom`，`labels list` 又显示 0 个标签，所以群里没能解析出名字。前端 `whoLabel()` 退化成「群 · 昵称」，不显示 id。
- 人物表：`POST /api/persons/rebuild` 从 distinct conv + 群内 sender 归纳，**1036 人**；`convs` 表登记 `is_group`，重建时排除群名（否则「三国杀官方交流群」会混进人名单）。

### 0.2 QQ 摸底结论（2026-11-11，只读 30 分钟，暂不做）

- 库：`D:\文档\Tencent Files\1500310681\nt_qq\nt_db\nt_msg.db` 1041 MB（仍在写）、`group_msg_fts.db` 405 MB、`profile_info.db` 28.3 MB、`group_info.db` 25.8 MB。
- 文件被 QQ 进程独占，要用 `[IO.File]::Open(..., FileShare::ReadWrite)` 才能读头。
- 前 16 字节：`53 51 4c 69 74 65 20 68 65 61 64 65 72 20 33 00`，即 **`SQLite header 3`**，不是 `SQLite format 3` → NTQQ 的 SQLCipher 变体，**页数据需密钥解密**。
- PyPI 没有可直接用的包：`qq-nt-db`、`qqnt`、`napcat`、`qq-nt`、`ntqq-db` 全 404；取密钥要读 QQ 进程内存，工具成熟度远低于微信的 `wechatauto-replica`。
- 结论：本轮不做。要做得先自研取密钥 + 解密（风险高），或走官方「消息管理器导出 txt」再写个小导入器（约半天）。

## 二、需要你做的事

1. **确认导入范围**（一句话即可）
   - 只导私聊？（推荐，隐私边界最清楚）
   - 还是也导群聊？群里别人的发言会进你的库。
2. **确认分身能否引用「别人的话」**
   - 现在分身只用 `is_me=1` 的样本学语气，但检索会命中所有记录。
   - 选项 A：检索也只看本人记录（最保守）；选项 B：能查到别人说的，回答时标注「这是对方说的」。
3. **同意我在本机装 `wechatauto-replica` 并读微信本地库**（路线 B 用；只读、不改微信、不发消息）。
4. **导样本**：微信里选一个会话，多选 30~50 条消息 → 右键「合并转发」→「转发到其他应用」，把产出的 zip 或 txt 放到 `D:\agent\digital-me\data\raw\wechat\`。
5. 导出期间**微信保持登录**，别退出、别切账号。

## 三、我做的事（按顺序）

| 步 | 做什么 | 产出 |
|---|---|---|
| 1 | 写 `scripts/import_wechat.py`：解析 txt/zip、字段映射、清洗、去重、按本地时区转 `ts` | 可 `--dry-run` 的导入器 |
| 2 | 拿你的样本先 dry-run：打印「读到 N 条 / 保留 M 条 / 比例」「按人、按天分布」 | 清洗比例报告（对照 22% 基准） |
| 3 | 真写库 + 建人物映射（wxid / 备注名 / 昵称 → `persons`） | 库里有历史数据，网页可翻可搜 |
| 4 | 验证：按日期翻到历史、搜旧事命中、分身引用并标注、导出 Markdown 含历史 | 截图 + 测试 |
| 5 | 你再决定是否上路线 B 批量；批量前加 `ext_id` 列（解决同秒同文被去重误杀） | 批量导入 |
| 6 | 更新 `docs/usage.md`、`docs/pending.md`、`docs/roadmap.md`，提交 | commit |

## 四、字段映射（路线 B 的 JSON → 我们的 `messages`）

| 来源字段 | 目标字段 | 规则 |
|---|---|---|
| `create_time`（Unix 秒） | `ts` | `datetime.fromtimestamp(sec).astimezone().replace(microsecond=0).isoformat()`，必须带本地时区偏移 |
| `chat_name` | `conv` | 私聊用对方名，群聊用群名 |
| `sender_username == self_username` | `is_me` | 1 / 0 |
| `content` | `text` | 清洗后 |
| `local_id` | `ext_id`（待加列） | 用于去重，避免「同秒同文」被 `fp` 误杀 |
| — | `source` | 固定 `wechat` |
| — | `kind` | 固定 `text` |

**时区是必须避开的坑**：日期索引按 `ts[:10]` 分组，若用 UTC 或裸 `strptime`，凌晨 0~8 点的消息会被算到前一天。

## 五、清洗规则

- 剔除非文本类型（图片、语音、视频、文件）、XML/卡片消息、系统消息（撤回、入群提示）、纯表情/纯符号。
- 长度上限 5000 字（实测有 103,275 字的合并转发 XML）。
- `type` 字段可能是 int，判断以 `content` 为主、`type` 为辅。
- 附带剔除：手机号、身份证号、银行卡号、验证码（正则粗筛 + 记录命中条数，不静默删除，交你过目）。

## 六、红线

- 只导**你自己账号**的记录，不碰他人账号。
- 导出文件留在本机 `data/`（已在 git 忽略），不上传、不进仓库、不进分发包。
- 只有「你的提问 + 命中的片段」会发给 DeepSeek，整库不出本机（沿用 D3）。
- 不承诺「绝对不封号」；路线 A 零风险，路线 B 是第三方只读工具，风险已说明，由你决定。

## 七、验收标准

- 网页「记录」页能翻到 2025 年甚至更早的消息，按天分组正确（凌晨消息不算到前一天）。
- 搜一个只存在于历史里的词能命中；搜一个只存在于别人发言里的词，按第二节的选择表现。
- 分身回答历史问题时给引用编号，且 `used_llm=true`。
- 导入重复执行两次，条数不翻倍。
- `scripts/check.ps1` 仍 `RESULT: PASS`。

## 八、时间

- 路线 A 全链路：半天（我今天就能做，只要你给样本）。
- 路线 B 批量：装依赖 + 摸底 30 分钟，清洗调参 1~2 小时，写库与人物消歧 2~3 小时。
- 合计到「历史数据能用」：**1 个工作日**（原估 1~3 天）。
