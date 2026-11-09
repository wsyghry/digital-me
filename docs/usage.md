# 使用手册 · 分身志

> 这份文件回答：**怎么装、怎么用、出问题怎么办。**
> 每个文件干什么见 [modules.md](modules.md)；以后怎么优化见 [optimization.md](optimization.md)。

---

## 〇、现在能用什么

| 功能 | 现在 | 什么时候有 |
|---|---|---|
| 看结构、读决策 | ✅ 可以 | 已经写好 |
| 记一句话 | ⏳ 不能 | P1 |
| 搜自己的记录 | ⏳ 不能 | P1 |
| 分身回答、拟稿 | ⏳ 不能 | P2（需要 API Key） |
| 导入微信 / QQ 历史 | ⏳ 不能 | P3（有账号风险，单独决策） |
| 手机随时访问 | ⏳ 不能 | P4 之后才是真正随时（本机阶段电脑要开机） |

下面命令里的路径按本机实际情况写的，换机器要改。

**第二节起的命令是按 P1 交付后的样子写的**——现在照抄会提示 `run.ps1` 不存在，这是正常的；P1 会按这份手册实现，交付时逐条对一遍。

---

## 一、一次性准备

**1. 确认 Python**

```powershell
D:\python\python3.12.2\python.exe --version   # 应为 3.12.x
```

**2. 进项目目录**

```powershell
cd D:\agent\digital-me
```

**3. 建虚拟环境并装依赖**（P1 起，`run.ps1` 会自动做；想手动就这样）

```powershell
D:\python\python3.12.2\python.exe -m venv .venv
.\.venv\Scripts\python.exe -m pip install -U pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

**4. 配置**

```powershell
Copy-Item .env.example .env
notepad .env
```

`.env` 里只有 `DEEPSEEK_API_KEY` 是真正需要填的，且 P2 才用得上。不填，记录和搜索照常工作。

> API Key 从 https://platform.deepseek.com/ 的「API keys」页面创建。充值按量，几元够用很久。

---

## 二、启动与停止

```powershell
cd D:\agent\digital-me
.\run.ps1
```

看到 `Uvicorn running on http://0.0.0.0:8000` 就成了。浏览器打开 http://localhost:8000 。

- **停止**：在那个窗口按 `Ctrl + C`
- **后台长跑**（不想一直开着窗口）：`.\run.ps1 -Background`，之后用 `.\run.ps1 -Stop` 关

等价的手动命令（调试时用，改动自动重载）：

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

---

## 三、电脑上用

| 想干的事 | 怎么做 |
|---|---|
| 记一句话 | 「记录」页签，输入框打字，`Ctrl + Enter` 发送 |
| 看最近的记录 | 打开就是，按时间倒序 |
| 搜索 | 「搜索」页签，输入关键词回车。三个字以上走全文索引，两个字走兜底，都能搜到 |
| 按来源/时间筛 | 搜索页的筛选条（P1 后期加） |
| 问分身 | 「分身」页签输入问题，回答下面会列出它引用了哪几条记录 |
| 拟一条回复 | 分身页签的「拟稿」：贴上对方的话 + 你大概想说什么，出 2 条候选 |

---

## 四、手机上用（本机阶段）

前提：手机和电脑连同一个 WiFi，电脑开着服务。

**1. 查电脑局域网 IP**

```powershell
Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*' } | Select-Object IPAddress, InterfaceAlias
```

挑 `InterfaceAlias` 是 Wi-Fi 或以太网的那条，形如 `192.168.1.23`。

**2. 手机浏览器打开** `http://192.168.1.23:8000`

**3. 打不开先查这两件事**

- 服务是不是绑定了 `0.0.0.0`（不是 `127.0.0.1`）
- Windows 防火墙有没有拦。首次启动会弹提示，要选「允许专用网络」。万一选了拒绝：

```powershell
New-NetFirewallRule -DisplayName "分身志 8000" -Direction Inbound -LocalPort 8000 -Protocol TCP -Action Allow -Profile Private
```

**4. 加到主屏幕**：Chrome 菜单 →「添加到主屏幕」。之后点图标全屏打开，跟 App 差不多。

**5. 语音输入**：不自己做录音。用手机输入法的麦克风键（讯飞、搜狗、Gboard 都行），说完整句转成文字，再按发送。这样最省事，识别质量也比自己接语音 API 好。

> 本机阶段的硬限制：电脑关机、休眠、换 WiFi，手机就打不开。要真正随时可用，得走第八节的上云。

---

## 五、分身怎么用才不出错

P2 上线后：

| 问法 | 效果 |
|---|---|
| 「我上周记的那个取件码」 | 好。有具体线索，检索能命中 |
| 「我最近在纠结什么事」 | 一般。要靠检索把相关记录捞出来，捞不到就会说不知道 |
| 「帮我编一段没发生过的事」 | 它会拒绝。人格提示词里写死了「不知道就说不知道」 |

**拟稿的正确用法**：不是让它替你聊天，是让它替你想措辞。

1. 把对方发来的话贴进去
2. 写一句你想表达的意思，比如「不太想去，但别伤感情」
3. 拿到 2 条候选，自己改一改再发

**绝对不要**做的事：把它接到微信上自动回复。那是冒充，会封号，也可能违法。理由见 [decisions-digital-me.md](decisions-digital-me.md) 的 D2。

---

## 六、导入历史记录（P3）

**格式**：一行一条 JSON，UTF-8 编码，字段如下（完整说明见 [data-schema.md](data-schema.md)）。

```json
{"ts":"2021-06-01T21:30:00+08:00","source":"wechat","conv":"老王","sender":"me","is_me":1,"text":"明天在老地方见","kind":"text"}
{"ts":"2021-06-01T21:31:12+08:00","source":"wechat","conv":"老王","sender":"老王","is_me":0,"text":"九点行吗","kind":"text"}
```

| 字段 | 必填 | 说明 |
|---|---|---|
| `ts` | 是 | 时间，带时区；不带时区按 +08:00 处理 |
| `text` | 是 | 正文；图片语音存占位，如 `[图片]` |
| `source` | 是 | `wechat` / `qq` / `note` / `import` |
| `conv` | 否 | 会话名；随手记留空 |
| `sender` | 是 | 显示名；自己发的写 `me` |
| `is_me` | 是 | 1 = 我发的，0 = 别人 |
| `kind` | 否 | 默认 `text` |

**导入**：

```powershell
.\.venv\Scripts\python.exe scripts\import_jsonl.py data\raw\wechat-2024.jsonl
```

**看报告**：脚本最后会打印总行数、新增、跳过重复、丢弃原因、时间跨度、各来源条数。丢弃率高通常是时间格式不对或正文为空。

**重复导入不会产生重复数据**，靠指纹去重，放心重跑。

---

## 七、备份与迁移

数据全在 `data/me.db` 一个文件里。

```powershell
# 停服务后
Copy-Item data\me.db "D:\备份\me-$(Get-Date -Format yyyyMMdd).db"
```

- **迁移到新电脑/服务器**：拷 `me.db` 过去，改 `.env` 里的 `ME_DB` 指向它，启动即可
- **别在服务运行时直接拷**：可能拷到写入一半的文件。要么停服务，要么用 `scripts/backup.ps1`（P4，内部用 SQLite 的备份接口，运行中也安全）
- `.env` 不跟着数据库走，要单独另存（里面有 Key）

---

## 八、部署到云（P4，等本机跑顺了再做）

1. 买轻量服务器：腾讯云香港 2 核 2G（免备案），35 元/月上下
2. 系统选 Ubuntu 24.04，装 Python 3.12
3. 上传代码（不含 `.env`、`data/`）与 `me.db`
4. 用 systemd 常驻，Caddy 反代 + 自动 HTTPS
5. 域名 A 记录指向服务器 IP
6. 手机流量下访问 `https://你的域名`

细节命令 P4 阶段会补一份 `docs/deploy.md`，现在别急着照搬。

**备案提醒**：大陆地域的 80/443 必须 ICP 备案才通，1~20 天；香港免备案，延迟略高但对一个人用完全够。

---

## 九、出问题先看这里

| 现象 | 原因 | 怎么办 |
|---|---|---|
| `run.ps1` 无法加载，提示禁止运行脚本 | PowerShell 执行策略 | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |
| 端口 8000 被占用 | 上次没关干净 | `Get-NetTCPConnection -LocalPort 8000 \| Select-Object OwningProcess` 找到进程后 `Stop-Process -Id <PID>` |
| 手机打不开，电脑上能开 | 只绑了 127.0.0.1，或防火墙 | 见第四节第 3 条 |
| 搜不到明明记得的词 | 两字词、或用词跟原文差太多 | 换原文里更可能出现的三个字再试；实在搜不到是向量检索要解决的，见 optimization.md |
| 搜带括号/引号的词页面报错 | 查询串没转义（已修的坑） | 更新到最新代码；这是 P1 就该测的用例 |
| 分身回答「接口错误 401」 | API Key 错或没充钱 | 检查 `.env` 的 `DEEPSEEK_API_KEY`，去平台看余额 |
| 分身回答「接口错误 402」 | 余额不足 | 充值，或先用免费额度 |
| 分身很慢 | 高峰时段（工作日 9-12、14-18） | 错峰用；空闲时段价格还便宜一半 |
| 数据库被锁 `database is locked` | 两个进程同时写 | 只跑一个服务实例；P1 会开 WAL 模式缓解 |
| 中文路径下 pip 报错 | 中文编码问题 | 项目放纯英文路径，本项目已在 `D:\agent\digital-me` |

---

## 十、日常节奏建议

- **每天**：随手记两三句。第一人称的增量数据比历史语料更值钱，因为它就是你现在在想的事
- **每周**：搜一次这周记的东西，看看检索顺不顺手——不顺就是该改 `retrieve.py` 的信号
- **每月**：备份一次 `me.db`，顺便看眼体积
- **导入历史**：等 P1、P2 用顺了再碰。先有能用的工具，再灌大数据，出问题才知道是工具的还是数据的

---

## 十一、代码存档（只在改了代码时用）

规则见 [decisions-digital-me.md](decisions-digital-me.md) 的 D7：每个功能能跑就提交，两个远程都推。

```powershell
cd D:\agent\digital-me
git status                              # 先看改了什么
git add -A
git commit -m "feat: 记录与搜索跑通"     # 前缀说明改动类型，描述写中文
git push gitee main                     # 两个都要推
git push github main
```

**推不动怎么办**：本机 git 全局配了代理 `127.0.0.1:10090`，代理软件没开时所有远程都会连不上（包括 gitee）。先把代理开起来再推；也可以临时绕过：

```powershell
git -c http.proxy= -c https.proxy= push gitee main
```

绕过只对网络能直连的环境有效，github 基本不行。

**数据不进仓库**：`.env`（含 Key）、`data/`（你的全部记录）、`.archify/`（生成过程的中间产物）都在 `.gitignore` 里。真要不小心提交了密钥，去平台把 Key 作废重发，别只删文件。
