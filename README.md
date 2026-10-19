# 拾问 Fieldnote

基于 MongoDB 的在线问卷系统。创建问题、配置跳转、分享链接、收集回答，并查看实时统计。

## 已实现能力

- 注册、登录、退出、服务端会话、密码 Argon2 哈希与管理权限隔离。
- 草稿编辑、四种输入类型、题目增删和排序、填写限制、匿名与重复提交设置。
- 单选、多选、数字条件跳转，发布前检查，预览与提交共用规则引擎。
- 发布、截止时间、关闭、分享；发布后定义固定，并发保存使用 revision 控制。
- 移动端逐题填写、返回修改后清除旧路径、后端完整路径重放。
- 请求幂等、并发防重复、匿名字段过滤、单题和整卷 MongoDB 聚合统计。
- 原始答卷和文本数值回答分页、演示数据、备份恢复、Compose 部署和 CI 配置。

## Windows 快速启动

需要 Python 3.13、Node.js 22.12 或更新的 22.x、MongoDB 8.x，且 `mongod` 在 PATH 中。MongoDB 只绑定本机；默认使用 27017 和 8000 端口。

在项目根目录打开 PowerShell，首次运行：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/setup.ps1
powershell -ExecutionPolicy Bypass -File scripts/start-local.ps1
```

打开 **http://localhost:8000**。开发演示账号：**demo / Fieldnote2026!**。也可以自己注册。

演示包含三份问卷，其中学习空间问卷的三份答卷明确标记为示例。再次运行启动脚本不会覆盖已有 demo 账号或重复插入示例。生产模式拒绝运行演示初始化。

关闭由启动脚本创建的进程：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/stop-local.ps1
```

脚本仅停止已记录且路径匹配本项目的进程。若复用了原本正在运行的 MongoDB，则不会停止它。服务日志与本地 MongoDB 数据在 `.local/`，不要删除该目录来“重置项目”。

## 开发和测试

后端：

```powershell
.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

另一个终端运行前端热更新：

```powershell
npm.cmd --prefix frontend run dev
```

开发前端地址 http://localhost:5173，通过 Vite 代理访问 API。后端交互文档为 http://localhost:8000/api/docs。

```powershell
.venv\Scripts\python.exe -m pytest backend/tests -q -p no:cacheprovider
.venv\Scripts\python.exe scripts/export_openapi.py
npm.cmd --prefix frontend run generate:api
npm.cmd --prefix frontend run build
cd frontend
npx.cmd playwright install chromium
npm.cmd run test:e2e
```

API 模型变更后重新导出 OpenAPI 并生成类型。浏览器测试需要后端正在运行、前端已构建、MongoDB 可连接。后端测试创建独立的 `fieldnote_test_*` 数据库并在结束后清理；不使用模拟 MongoDB。浏览器测试在当前运行库中创建带 `browser_` / `mobile_` 前缀的测试账号，应连接开发实例。

## 项目结构

```text
backend/app/      接口、认证、业务、数据库、模型与纯规则引擎
backend/tests/    单元与真实 MongoDB 集成测试
frontend/src/    Vue 页面、组件、样式及生成的 API 类型
frontend/tests/  Chromium 端到端测试
scripts/         本地安装启停、演示初始化、OpenAPI 导出、备份恢复
deploy/          Caddy 与生产环境变量模板
docs/            设计、API、测试、部署、报告与 AI 日志
```

## 本地 Docker 复现

启动 Docker Desktop 引擎。复制 `.env.example` 为 `.env`，修改 MongoDB 密码，再执行：

```powershell
docker compose up -d --build
docker compose ps
```

访问 http://localhost:8080。Compose 默认仅绑定本机，不会自动公开网站，也不会创建演示账号。MongoDB 没有发布主机端口。普通停止使用 `docker compose down`，不要附加 `-v`，否则会删除数据库卷。

公网演示待服务器和域名准备后按 [部署说明](docs/DEPLOYMENT.md) 实施。当前提供可部署配置，不能将配置检查等同于已完成云端部署。

## 文档

- [第一阶段项目完成报告 PDF](output/pdf/Fieldnote_第一阶段项目完成报告_修订版.pdf)
- [系统与数据库设计](docs/DESIGN.md)
- [API 说明](docs/API.md)
- [测试步骤与实际结果](docs/TEST_REPORT.md)
- [部署和备份恢复](docs/DEPLOYMENT.md)
- [项目完成报告](docs/PROJECT_REPORT.md)
- [AI 使用记录](docs/AI_LOG.md)

第一阶段限制为向后跳转、当前题条件、发布定义不可修改；不保存填写中的草稿。日期保存为 UTC，列表按 Asia/Shanghai 显示，截止时间选择器使用浏览器本机时区。匿名是向问卷创建者隐藏账号，服务端仍保留关联用于限制重复提交。文本自身包含的姓名等内容不会自动脱敏。
