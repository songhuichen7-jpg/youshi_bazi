# 生产部署清单

这份是给"内测就要按真生产标准跑"的清单。逐条对照,跑完再开放邀请码。

## 先决条件

- Linux 服务器(2 vCPU / 4 GB RAM 起步)
- PostgreSQL 14+ (云托管或自部署都行)
- Redis 6+ (多 worker 部署必须;单 worker 可以省)
- nginx
- Python 3.12+ + uv

## 1. PostgreSQL

```bash
# 创建库 + 用户
sudo -u postgres psql <<EOF
CREATE USER youshi WITH PASSWORD '...';
CREATE DATABASE youshi_prod OWNER youshi;
EOF

# 应用 migration
cd /opt/youshi/server
uv run alembic upgrade head
```

确认 `postgresql.conf` 的 `max_connections >= 100`,默认就是。

## 2. Redis

```bash
sudo apt install redis-server
sudo systemctl enable --now redis
# 测试
redis-cli ping     # 期望: PONG
```

如果 Redis 在另一台机器,确认网络 + 用 `requirepass` 加密码。

## 3. 后端部署

```bash
sudo useradd -r -m -d /opt/youshi -s /bin/bash youshi
sudo -u youshi git clone <repo> /opt/youshi
cd /opt/youshi/server
sudo -u youshi cp .env.example .env
sudo -u youshi vim .env       # 填实际值,见下方清单
sudo -u youshi uv sync
sudo -u youshi uv run alembic upgrade head
```

`.env` 关键项 (生产):

| 项 | 推荐值 | 说明 |
|---|---|---|
| `ENV` | `prod` | |
| `LOG_LEVEL` | `INFO` | |
| `DATABASE_URL` | `postgresql+asyncpg://youshi:PASS@HOST:5432/youshi_prod` | |
| `REDIS_URL` | `redis://localhost:6379/0` | **多 worker 必须设** |
| `ENCRYPTION_KEK` | 64 hex 字符 | `python -c "import secrets; print(secrets.token_hex(32))"` |
| `DEEPSEEK_API_KEY` | 真实 key | |
| `CORS_ORIGINS` | 留空 (同源 nginx 反代不需要) | |
| `RATE_LIMIT_PER_MINUTE` | `60` | 单用户/分钟。Redis 化后跨 worker 准确 |
| `DB_POOL_SIZE` | `20` | |
| `DB_MAX_OVERFLOW` | `30` | 总 50 / worker;4 worker = 200 总连接,留 spare |

## 4. 启动 uvicorn (systemd)

```bash
sudo cp deploy/uvicorn.service /etc/systemd/system/youshi.service
# 改 worker 数,按 CPU 核数:--workers N
sudo systemctl daemon-reload
sudo systemctl enable --now youshi
journalctl -u youshi -f
# 期望最后一行: "Application startup complete."
```

确认接口跑起来:
```bash
curl http://127.0.0.1:3101/api/health
# {"status":"ok",...}
```

## 5. 前端部署

```bash
cd /opt/youshi/frontend
sudo -u youshi npm ci
sudo -u youshi npm run build
# 结果在 /opt/youshi/frontend/dist
```

vite.config.ts 的 proxy 块只在 dev 生效,生产 nginx 直接路由,不冲突。

## 6. nginx

```bash
sudo cp deploy/nginx.conf /etc/nginx/sites-available/youshi
sudo ln -s /etc/nginx/sites-available/youshi /etc/nginx/sites-enabled/
# 改域名: 把 youshi.app 全局换成你的域名
sudo nginx -t && sudo systemctl reload nginx
```

申请证书:
```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d youshi.app -d www.youshi.app
```

## 7. 验收

跑这一套确认上线 OK:

```bash
# 1) 健康 + 配置
curl https://youshi.app/api/health
curl https://youshi.app/api/config

# 2) 静态资源 200 + 长 cache
curl -I https://youshi.app/assets/index-*.js | grep -i cache-control

# 3) SSE 长连接不被中断 — 手工开浏览器,聊一条长问题(>30s),
#    用 DevTools Network 看 EventStream tab 持续收 chunk 不被切

# 4) Redis 锁验证(多 worker)
#    跑 ab/wrk 压 /api/hepan/invite,看 Redis 监视器:
redis-cli MONITOR | grep -E "rl:|lock:"

# 5) PG 连接数
sudo -u postgres psql -c "SELECT count(*) FROM pg_stat_activity WHERE usename='youshi'"
# 期望 < workers × (pool_size + max_overflow)
```

## 8. 监控建议

最少装 3 件:

- **uptime 探活**: UptimeRobot / Pingdom 5 分钟探一次 `/api/health`
- **错误日志**: `journalctl -u youshi`,重要错误手动 grep "ERROR\|Traceback"
  (规模大了换 Sentry)
- **PG 慢查询**: `log_min_duration_statement = 500` 在 `postgresql.conf`,
  >500ms 的 query 写日志

## 9. 上线后扩容路径(留给将来)

按当前架构能扛 ~100 同时活跃用户、~15 同时聊天。再大要做的事:

1. **多机部署** — 起两台 backend,nginx 改 `upstream` 加多个 server,加 sticky session 或 shared Redis (已经是了)
2. **PG 读写分离** — pool 留两套,读走 replica
3. **SSE 释放 DB** — 真正 1000+ 同时聊天再做(refactor streaming 服务,
   见 `services/conversation_chat.py` 的注释)
4. **DeepSeek 上 multi-key** — 单 key 有 RPM 限制,加 key pool 轮询

## 10. 故障定位 cheat sheet

| 症状 | 第一步看哪 |
|---|---|
| 用户全部 503 | `journalctl -u youshi --since "5 min ago"` |
| 部分用户 503,部分正常 | nginx access log,找 5xx 集中在哪个 IP |
| SSE 30 秒断流 | 检查 nginx `proxy_read_timeout`(本配置已 300s) |
| `CONVERSATION_BUSY` 频繁 | 用户多标签发同 conv,或 Redis 锁泄露(`redis-cli KEYS 'lock:*'`) |
| `RATE_LIMITED` 频繁 | `redis-cli ZCARD rl:sess:...` 看实际打了多少 |
| DB pool 耗尽 | `pg_stat_activity` + 看是不是 SSE 连接堆积 |
