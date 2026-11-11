# 部署到云服务器（P4）

目标：手机上随时能用，家里电脑关着也行。整套东西只占一台最小的机器。

推荐：**腾讯云轻量应用服务器 2 核 2G，香港地域**（免 ICP 备案，35 元/月上下）。
大陆地域必须先备案才能开 80/443，备案要 1~20 天，所以第一台买香港。

## 一、要买什么

| 项 | 说明 | 大概价格 |
|---|---|---|
| 轻量 2C2G | Ubuntu 24.04，40 GB SSD / 100 GB 流量 | 35 元/月 |
| 域名 | 已有 `wsghaoren.cn`，加一条 `me.wsghaoren.cn` 解析即可 | 0 元 |
| DeepSeek API | 按量，正常用每月几块钱 | 见 `/api/cost` |

买完在控制台做两件事：

1. 防火墙放行 `80`、`443`（轻量的「防火墙」页面加规则）。
2. 域名解析加一条 `A` 记录：`me` → 服务器公网 IP。

## 二、服务器上装什么

```bash
# 1. 基础环境
sudo apt update && sudo apt install -y python3.12 python3.12-venv git caddy

# 2. 拉代码（用公开仓库，别把 .env 和 data 带上服务器以外的地方）
sudo mkdir -p /srv && cd /srv
sudo git clone https://gitee.com/im-a-good-person-you-know/digital-me.git
sudo chown -R $USER:$USER /srv/digital-me && cd /srv/digital-me

# 3. 虚拟环境与依赖
python3.12 -m venv .venv
./.venv/bin/pip install -r requirements.txt

# 4. 配置：真实 Key 只写在这台机器的 .env 里
cp .env.example .env && chmod 600 .env
# 编辑 .env，填 DEEPSEEK_API_KEY；把 HOST 改成 127.0.0.1（Caddy 在前面挡着）
```

`.env` 里在服务器上要改的三行：

```
ME_HOST=127.0.0.1
ME_PORT=8000
ME_PASSWORD=给自己定一个口令
```

> `ME_PASSWORD` 不填，整库就对着公网裸奔：任何人扫到域名都能读、能删、能导走。填了之后首页先要输一次口令，cookie 管 30 天。

## 三、开机自启（systemd）

`deploy/digital-me.service` 已经写好，复制过去即可：

```bash
sudo cp deploy/digital-me.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now digital-me
systemctl status digital-me --no-pager
curl -s http://127.0.0.1:8000/api/health
```

## 四、HTTPS（Caddy 自动签证书）

`deploy/Caddyfile` 里把域名换成你自己的：

```bash
sudo cp deploy/Caddyfile /etc/caddy/Caddyfile
sudo systemctl reload caddy
```

Caddy 会自动申请 Let's Encrypt 证书。打开 `https://me.wsghaoren.cn` 应该直接能用，
第一次可能要等十几秒。手机浏览器菜单里「添加到主屏幕」，以后就是个 App。

## 五、数据迁过去

在**本机**打包当前库（服务可以开着，`backup.py` 用的是 SQLite 官方备份接口）：

```powershell
.\\.venv\\Scripts\\python.exe scripts\\backup.py
```

把 `backups\\me-最新.db` 用 `scp` 传到服务器：

```bash
scp backups/me-20261111-210315.db ubuntu@<服务器IP>:/srv/digital-me/data/me.db
```

然后重启服务：`sudo systemctl restart digital-me`。打开页面右上角条数应该对得上。

## 六、部署后的验收（五条都过才算完）

1. 手机用**流量**（不是 WiFi）打开 `https://me.你的域名`，地址栏有小锁
2. 未登录时直接访问首页会被跳到登录页；`curl -sI https://me.你的域名/api/messages` 返回 401（不是 200、不是 500）
3. 输口令进去，右上角条数与本机一致
4. 记一条 → 本机刷新能看到（或反过来）；问答能引用到真实记录
5. 删一条测试数据 → `scripts/restore.ps1` 从最近备份恢复，条数回来

## 七、每天的备份

服务器上：

```bash
crontab -e
# 每天 3:10 备份，只留 14 份
10 3 * * * cd /srv/digital-me && ./.venv/bin/python scripts/backup.py --keep 14 >> backups/cron.log 2>&1
```

备份在本机磁盘上，机器挂了就一起没了。要更稳就再加一步同步到自己电脑（`scp`）或对象存储。

## 常见问题

| 症状 | 原因 | 怎么办 |
|---|---|---|
| 打开是 404 | Caddy 里域名没改 / 解析没生效 | `dig me.你的域名` 看解析，`journalctl -u caddy -n 50` 看日志 |
| 502 | 后端没起来 | `systemctl status digital-me`，再看 `journalctl -u digital-me -n 50` |
| 能打开但问答 503 | 服务器上的 `.env` 没填 Key | 填完 `systemctl restart digital-me` |
| 证书签不下来 | 80 端口没放行 | 检查轻量防火墙和 `ufw status` |
| 中文乱码 | 服务器 locale | `sudo locale-gen zh_CN.UTF-8` |

## 安全线

- `.env` 权限 600，权限之外谁也别给。
- 不要在这台机器上放别人的聊天记录副本；导入在本机做，只把 `me.db` 搬过去。
- 服务器上的 `data/me.db` 是明文 SQLite，机房能碰到磁盘的人就能读。真要更严，可以开磁盘加密（云厂商的加密盘）或改用 SQLCipher——但那是另一个量级的复杂度，先不上。
