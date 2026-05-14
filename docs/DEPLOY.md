# 部署手册

把项目从零部署到一台云服务器上，跑 HTTPS 域名访问的完整流程。

线上版本部署在腾讯云 Lighthouse（2 vCPU / 4 GB / Ubuntu 22.04），域名 `youshi.fun`。

---

## 0. 服务器清单

最小可用配置：

- Linux 服务器（推荐 Ubuntu 22.04 LTS，2 vCPU / 4 GB RAM / 40 GB SSD）
- 一个已备案的域名（国内服务器）
- PostgreSQL 14+（云托管或自部署）
- Redis 6+
- nginx
- Python 3.12+，使用 [uv](https://docs.astral.sh/uv/) 包管理
- Node.js 20+ 用于前端构建

---

## 1. 域名与 DNS

注册商（阿里云 / 腾讯云 / Cloudflare 等）控制台添加 A 记录：

```
youshi.fun          A     <server-ipv4>      TTL 600
www.youshi.fun      A     <server-ipv4>      TTL 600
```

> 国内服务器需先完成 ICP 备案，否则 80/443 端口无法对外访问。
> 海外服务器（如 Cloudflare）则跳过备案，但国内访问速度会差一些。

验证生效：

```bash
dig youshi.fun +short
# 应当返回 <server-ipv4>
```

---

## 2. PostgreSQL

```bash
sudo apt update && sudo apt install -y postgresql-14

sudo -u postgres psql <<'EOF'
CREATE USER youshi WITH PASSWORD 'CHANGE_ME_STRONG_RANDOM_PASSWORD';
CREATE DATABASE youshi_prod OWNER youshi;
EOF
```

确认 `/etc/postgresql/14/main/postgresql.conf` 的 `max_connections >= 100`（默认就是）。

如果用云托管（腾讯云 PostgreSQL / 阿里云 RDS），直接在控制台创建实例并把连接串放进 `.env`。

---

## 3. Redis

```bash
sudo apt install -y redis-server
sudo systemctl enable --now redis
redis-cli ping     # 期望: PONG
```

跨机部署时打开外网访问 + 设置 `requirepass`，连接串改成 `redis://:<password>@<host>:6379/0`。

---

## 4. 应用代码

```bash
# 4.1 起 service account
sudo useradd -r -m -d /opt/youshi -s /bin/bash youshi

# 4.2 拉代码
sudo -u youshi git clone https://github.com/<you>/youshi-bazi /opt/youshi
cd /opt/youshi/server

# 4.3 装 uv（如果没装）
curl -LsSf https://astral.sh/uv/install.sh | sh

# 4.4 装依赖
sudo -u youshi uv sync --frozen --no-dev

# 4.5 配置环境变量
sudo -u youshi cp .env.example .env
sudo -u youshi vim .env     # 按下表填实际值

# 4.6 应用数据库 migration
sudo -u youshi uv run alembic upgrade head
```

### .env 关键项

| 项 | 推荐值 | 说明 |
|---|---|---|
| `ENV` | `prod` | 控制日志格式与错误响应 |
| `LOG_LEVEL` | `INFO` | |
| `DATABASE_URL` | `postgresql+asyncpg://youshi:PASS@HOST:5432/youshi_prod` | async driver 必须 |
| `REDIS_URL` | `redis://localhost:6379/0` | 多 worker 必填，否则分布式锁失效 |
| `ENCRYPTION_KEK` | 64 hex | `python -c "import secrets; print(secrets.token_hex(32))"` |
| `LLM_API_KEY` | 真实 key | OpenAI-compatible API key |
| `LLM_BASE_URL` | 供应商端点 | 例如 `https://api.deepseek.com/v1` |
| `LLM_MODEL` | 主回答模型 | 思考强度高 / 长上下文 |
| `LLM_FAST_MODEL` | 快速模型 | router / chips |
| `LLM_FALLBACK_MODEL` | 备用模型 | 主模型超时降级 |
| `CORS_ORIGINS` | 留空 | 同源 nginx 反代不需要 |
| `RATE_LIMIT_PER_MINUTE` | `60` | 用户/分钟，Redis 化后跨 worker 准确 |
| `DB_POOL_SIZE` | `20` | |
| `DB_MAX_OVERFLOW` | `30` | 总 50/worker，4 worker = 200 总连接 |

---

## 5. 后端进程（systemd）

```bash
sudo cp /opt/youshi/deploy/uvicorn.service /etc/systemd/system/youshi.service
# 改 worker 数：--workers N，按 CPU 核数；2 vCPU 建议 2-3 workers
sudo systemctl daemon-reload
sudo systemctl enable --now youshi
journalctl -u youshi -f
# 期望最后一行: Application startup complete.
```

健康检查：

```bash
curl http://127.0.0.1:3101/api/health
# {"status":"ok",...}
```

---

## 6. 前端构建

```bash
cd /opt/youshi/frontend
sudo -u youshi npm ci
sudo -u youshi npm run build
# 产物在 /opt/youshi/frontend/dist
```

`vite.config.js` 的 `proxy` 只在 dev 生效，生产 nginx 直接路由，不会冲突。

---

## 7. nginx 反代 + HTTPS

```bash
sudo apt install -y nginx
sudo cp /opt/youshi/deploy/nginx.conf /etc/nginx/sites-available/youshi
# 编辑文件，把所有 youshi.fun 替换成你的真实域名
sudo vim /etc/nginx/sites-available/youshi
sudo ln -s /etc/nginx/sites-available/youshi /etc/nginx/sites-enabled/
sudo rm /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx
```

### Certbot 签 SSL

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d youshi.fun -d www.youshi.fun \
  --non-interactive --agree-tos -m you@example.com
```

certbot 会自动：

1. 校验域名所有权（HTTP-01 challenge）
2. 申请 Let's Encrypt 证书（3 个月有效）
3. 改写 nginx 配置加入 `listen 443 ssl` + 证书路径
4. 装一个 cron 自动续签（`/etc/cron.d/certbot`）

### nginx 关键配置

`deploy/nginx.conf` 的核心点：

```nginx
# HTTPS 重定向
server {
    listen 80;
    server_name youshi.fun www.youshi.fun;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name youshi.fun www.youshi.fun;

    ssl_certificate     /etc/letsencrypt/live/youshi.fun/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/youshi.fun/privkey.pem;

    # 静态资源长缓存
    location /assets/ {
        root /opt/youshi/frontend/dist;
        expires 1y;
        add_header Cache-Control "public, immutable";
    }

    # 前端 SPA 入口
    location / {
        root /opt/youshi/frontend/dist;
        try_files $uri /index.html;
    }

    # API 反代 + SSE 优化
    location /api/ {
        proxy_pass http://127.0.0.1:3101;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # SSE 关键参数
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 300s;
        chunked_transfer_encoding on;
    }

    # HSTS
    add_header Strict-Transport-Security "max-age=63072000; includeSubDomains" always;
}
```

---

## 8. 验收

```bash
# 健康
curl https://youshi.fun/api/health
# {"status":"ok",...}

# 静态资源长缓存
curl -I https://youshi.fun/assets/index-*.js | grep -i cache-control
# cache-control: public, max-age=31536000, immutable

# HTTPS 重定向
curl -I http://youshi.fun
# 301 Moved Permanently -> https://youshi.fun/

# SSL 证书有效期
echo | openssl s_client -servername youshi.fun -connect youshi.fun:443 2>/dev/null \
  | openssl x509 -noout -dates
```

**SSE 验收**：手工开浏览器，发一条 > 30s 的长问题，DevTools → Network → EventStream，看 chunk 持续到达不被切断。

---

## 9. 监控（最小三件套）

### 探活

UptimeRobot / Pingdom 5 分钟探一次 `/api/health`。

### 日志

```bash
journalctl -u youshi -f                        # 实时
journalctl -u youshi --since "5 min ago"       # 最近
journalctl -u youshi | grep -E "ERROR|Traceback"  # 错误集中查看
```

规模大了上 Sentry / Logflare。

### PG 慢查询

编辑 `/etc/postgresql/14/main/postgresql.conf`：

```
log_min_duration_statement = 500   # > 500ms 的 query 落盘
log_line_prefix = '%t [%p] %u@%d '
```

重启 PG：`sudo systemctl restart postgresql`。

---

## 10. 故障定位 cheatsheet

| 症状 | 第一步看哪 |
|---|---|
| 用户全部 503 | `journalctl -u youshi --since "5 min ago"` |
| 部分用户 503 | nginx access log，找 5xx 集中的 IP/路径 |
| SSE 30s 断流 | `proxy_read_timeout`，本配置已 300s |
| `CONVERSATION_BUSY` 频繁 | 用户多标签同 conv 并发；或 Redis 锁泄露 `redis-cli KEYS 'lock:*'` |
| `RATE_LIMITED` 频繁 | `redis-cli ZCARD rl:sess:...` 看实际打了多少 |
| DB pool 耗尽 | `pg_stat_activity` 看连接数；多半是 SSE 长连接 hold 住 |
| SSL 续签失败 | `sudo certbot renew --dry-run`，看 challenge 失败原因 |

---

## 11. Docker 部署（备选）

如果不想自己装环境，用 `deploy/Dockerfile.tencent`：

```bash
cd /opt/youshi
docker build -f deploy/Dockerfile.tencent -t youshi:latest .
docker run -d --name youshi \
  --restart unless-stopped \
  -p 3101:3101 \
  --env-file server/.env \
  -v /opt/youshi/data:/data \
  youshi:latest
```

或者 `docker compose -f deploy/docker-compose.tencent.yml up -d`，里面把 nginx + Redis 一起编排好。

---

## 12. 扩容路径

按当前架构能扛 **~100 同时活跃用户、~15 同时聊天连接**。再大需要：

1. **多机部署**：另起一台 backend，nginx 加 `upstream` 多个 server；Redis 已经是 shared 的，sticky session 也可省
2. **PG 读写分离**：读 query 走 replica（用 `DB_READ_URL` 区分）
3. **SSE 不 hold DB**：refactor 成"streaming 期间写 Redis、done 才落 PG"（注释里有 TODO）
4. **LLM API key pool**：单 key 有 RPM 上限，多 key 轮询突破
5. **CDN**：静态资源前置 Cloudflare / 腾讯云 CDN，国内首屏可降到 < 1s

---

## 13. 备份

```bash
# 数据库每日凌晨备份
echo '0 3 * * * youshi pg_dump -h localhost -U youshi youshi_prod \
  | gzip > /opt/youshi/backups/db-$(date +\%F).sql.gz' \
  | sudo tee /etc/cron.d/youshi-backup

# 保留 30 天
find /opt/youshi/backups -name "db-*.sql.gz" -mtime +30 -delete
```

定期把备份上传到 S3 / 腾讯云 COS 做异地容灾。
