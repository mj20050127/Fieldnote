# 第二阶段迁移、恢复与演示

## 升级步骤

先停止所有使用目标数据库的后端写入，保留 MongoDB 运行。不要在正在收集作答的数据库上直接升级。确认备份目录为本次新建目录，脚本不会覆盖已有备份。

```powershell
.venv\Scripts\python.exe scripts/backup.py --output .local/backups/before-stage2
.venv\Scripts\python.exe scripts/verify_stage2_migration.py .local/backups/before-stage2
.venv\Scripts\python.exe scripts/migrate_stage2.py --dry-run --report .local/migration-dry.json
.venv\Scripts\python.exe scripts/migrate_stage2.py --apply --maintenance --backup .local/backups/before-stage2 --report .local/migration-apply.json
```

verify_stage2_migration.py 恢复到新建的 fieldnote_restore_stage2_* 数据库，预演 dry-run、迁移与重跑，逐卷比较快照与统计，逐份答卷比较原始文档，并用原 request_id 重放历史提交。只清理自己创建的临时恢复库，不触碰原库。该脚本适用于首次从第一阶段升级的备份；已迁移后的普通恢复使用 verify_backup.py 或后端备份测试。

迁移 CLI 默认为 dry-run；正式写入必须同时提供 --apply、--maintenance、--backup。检查备份文件校验和、问卷身份集合，初始化新集合的 validator 与索引后再迁移。--maintenance 是操作者对维护状态的明确声明，脚本不会自动停止别的进程。--database 可指定独立恢复库，默认读取 .env 中的 MONGO_DATABASE。

每个旧题位用问卷 ID 和题位 ID 生成确定性逻辑题目和版本 ID，按所有者存入“第一阶段迁移题库”。不同问卷内相同题干仍是不同题。未完成内容原样保留并进入 skipped；原问卷中的跳转不进入题库版本。不修改历史答卷，补充来源的问卷递增 revision。中断后可按同命令续跑；若检测到并发修改或内容冲突，保持维护状态并检查原因。

## 失败恢复

保持后端关闭，从迁移前备份恢复到新的空库：

```powershell
.venv\Scripts\python.exe scripts/backup.py --restore .local/backups/before-stage2 --target fieldnote_restore_stage2_rollback
```

将 .env 的 MONGO_DATABASE 指向该恢复库，运行匹配的第一阶段代码并检查健康、登录、原分享链接、答卷数量与统计，再结束维护。不要把回退代码当作数据库回滚，也不要覆盖原库或删除它来重试。备份格式 v1 包含三个业务集合，v2 包含六个；会话排除，恢复后重新登录。

## 本次真实执行

2026-10-24：基线为 61 项后端、5 项浏览器测试。迁移前备份保存于 .local/backups/stage1-before-stage2-20261024；正式迁移前另存 .local/backups/stage2-formal-before-20261024。

真实第一阶段备份包含 users=6、surveys=9、responses=6。隔离恢复库预演生成 36 个题目和版本，6 次历史提交全部返回原回执；快照、答卷原文和统计不变。公开的去敏验收结果见 evidence/stage2-migration.json。

正式库 fieldnote 在后端未启动的维护窗口完成迁移：8 份包含题目的问卷补充 36 个来源，空问卷保持原状；随后重跑新增 0 个题目，已关联 36 个，无 skipped 或冲突。正式结果保存在 .local/stage2-formal-migration.json 与 .local/stage2-formal-rerun.json。上述本机备份含账号哈希和业务数据，不提交仓库。

## 演示链

1. 题库新建数字题 v1，并按另一账号用户名共享。
2. 接收者查看“共享给我”，复用原题或另存为自己的题目。
3. 创建两份问卷，从题库选择同一 v1；发布并收集 10、20、30。
4. 题目详情的跨卷统计显示均值 20，区分答卷份数和作答次数。
5. 原作者保存 v2，检查已发布的 v1 问卷与原统计不变。
6. 新草稿明确采用 v2；旧规则不兼容时定位并修复，才能发布。
7. 历史中选择 v1 并恢复，产生新版本；查看父版本、恢复来源和内容差异。
8. 查看本人引用问卷；撤销共享后验证已有快照及本人历史统计仍保留。
