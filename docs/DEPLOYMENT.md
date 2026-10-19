# 本地运行与答辩期间公网部署

## 先理解要准备什么

云服务器是远程运行项目的电脑，域名是指向它的网址。前端、后端、MongoDB 可以放在同一台服务器上。Compose 统一启动组件，Caddy 接收访问并管理 HTTPS。公网服务器费用和域名购买在确认供应商、租期及官方报价后由你决定；本项目没有代购或自动发布。

当前优先本地开发和演示，再上线到作业与答辩期间使用的服务器。本地不需要域名，打开 README 中的 localhost 地址即可。不要把 localhost 链接发给其他人当作公网链接。

## 当前验证范围

Windows 原生 MongoDB、独立 Python 虚拟环境、生产前端构建、本地服务及 Chromium 流程已实际验证。Compose 已通过配置解析；当前机器 Docker 引擎未运行，因此镜像构建、容器启动、云端 DNS、证书与远程重启恢复尚待部署环境验证。GitHub Actions 是提供的配置，还没有远程仓库运行记录。

## 云端上线步骤

1. 准备一台可 SSH 连接的 Ubuntu 24.04 服务器，默认规划 2 核 4GB；准备一个可解析到其公网地址的域名。只按答辩需要选择租期，先核对续费规则。
2. 按 [Docker 官方 Ubuntu 安装说明](https://docs.docker.com/engine/install/ubuntu/)安装 Docker Engine 和 Compose 插件，检查 `docker compose version`。
3. 上传项目源码，包含 frontend/package-lock.json、frontend/openapi.json 和 frontend/src/api.generated.ts；不上传 .env、.venv、node_modules、.local、截图或本地数据库。
4. 在服务器项目根目录复制 `deploy/production.env.example` 为 `.env`，把两个 example.com 地址换成真实域名。使用 `openssl rand -hex 24` 生成 48 位随机十六进制 MongoDB 密码并填入；不要保留占位值。
5. 将域名的 A 记录指向服务器公网 IPv4，放行 TCP 80、443；SSH 按云平台说明限制来源。不要开放 MongoDB 27017 或后端 8000。
6. 执行以下命令：

```bash
docker compose config --quiet
docker compose up -d --build
docker compose ps
docker compose logs --tail 100 app
docker compose logs --tail 100 gateway
```

7. 打开真实 HTTPS 域名，自己注册账号。生产不初始化 demo 账号。再用手机流量注册第二个账号，走完创建、发布、填写、统计、关闭及重复提交检查。
8. 执行 `docker compose restart` 后确认已有问卷和答卷仍在，记录云端验收结果，不能仅凭配置文件存在就写“公网部署成功”。

生产配置必须满足 APP_ENV=production、PUBLIC_ORIGIN 为实际 HTTPS 来源，浏览器请求来源与其一致。PUBLIC_ORIGIN 在 Compose 中由 COMPOSE_PUBLIC_ORIGIN 传入。不能把 production 改成 development 来绕过 Cookie 或来源问题，应检查域名、HTTPS 和配置是否一致。

生产入口用 80、443，MongoDB 只在 Compose 内部网络访问，数据与 Caddy 证书分别使用持久卷。普通停止用 `docker compose down`，不要执行 `down -v`。修改 `.env` 中的 MongoDB 初始密码不会自动修改已有数据库账号密码；初始化变量只在首次建卷生效。

## 本地备份与安全恢复

`scripts/backup.py` 保存 users、surveys、responses，不保存登录会话。使用 BSON Extended JSON 保留日期等类型，gzip 压缩并记录每集合数量和 SHA-256。备份含密码哈希与答卷，默认保存在 Git 忽略的 .local/backups。

为获得一致的备份，先暂停后端服务，保留 MongoDB 运行，再执行；不要在持续接收注册和答卷时声称获得跨集合一致快照。

```powershell
powershell -ExecutionPolicy Bypass -File scripts/stop-local.ps1 -KeepDatabase
.venv\Scripts\python.exe scripts/backup.py --output .local/backups/before-stage2
.venv\Scripts\python.exe scripts/backup.py --restore .local/backups/before-stage2 --target fieldnote_restore_stage1
```

恢复只允许以 `fieldnote_restore_` 开头的全新空库，拒绝覆盖。修改 `.env` 的 MONGO_DATABASE 指向新库，启动应用会重建 validator 与索引；验证数量、问卷、统计及登录后再决定是否采用。恢复不保留旧登录态，需要重新登录。

## 云端备份

云端可以使用 MongoDB 官方工具。先停止 app 以暂停业务写入，MongoDB 保持运行：

```bash
mkdir -p backups
docker compose stop app
docker compose exec -T mongo sh -c 'mongodump --username "$MONGO_INITDB_ROOT_USERNAME" --password "$MONGO_INITDB_ROOT_PASSWORD" --authenticationDatabase admin --db fieldnote --archive=/tmp/fieldnote-backup.gz --gzip'
docker compose cp mongo:/tmp/fieldnote-backup.gz ./backups/fieldnote-backup.gz
docker compose start app
```

若数据库名已改，应相应修改 `--db`。把备份复制到服务器之外保存。恢复时先在新库名执行 mongorestore 的命名空间映射，验证后再切换，避免使用 `--drop` 覆盖原库。云端备份恢复需要在实际服务器另做演练，本地 JSON 备份测试不能替代它。

## 更新和回退

上线前记录当前代码版本并备份数据，再构建新镜像。更新后检查健康、登录、填写、统计；失败时切回上一代码版本重新构建。第一阶段版本间没有数据迁移；第二阶段若修改数据结构，必须为每次迁移单独提供备份、兼容策略和恢复步骤，不能只回退代码而忽略数据变化。

等第一阶段经过你验收并建立 Git 仓库后，将这一版标记为 stage1。当前尚未替你创建远程仓库、推送代码、产生托管费用或创建发布标签。
