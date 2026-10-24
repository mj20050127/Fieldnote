# API 使用说明

当前契约版本为 2.0.0。第一阶段填写与提交协议保持兼容；第二阶段题库接口见文末。

开发环境交互文档：http://localhost:8000/api/docs；机器可读契约：frontend/openapi.json。前端 api.generated.ts 由该契约生成。

## 认证与错误

注册和登录传 JSON `{ "username": "你的用户名", "password": "至少8位密码" }`。响应含用户 ID、用户名和 csrf_token，Cookie 由浏览器保存。除注册、登录外，全部业务接口要求登录；写操作需要 `X-CSRF-Token` 请求头。退出会删除服务端会话。

业务错误为 `{ "error": { "code": "INVALID_ANSWER", "message": "…", "question_id": "…", "field": null } }`。未登录 401，CSRF 和来源问题 403，他人资源或不存在资源 404，状态、版本或提交冲突 409，输入或答案问题 422，过大请求 413，登录限流 429。未知 API 不返回前端 HTML。

## 接口清单

| 方法 | 路径 | 功能 |
|---|---|---|
| GET | /api/health | 数据库健康检查，无需登录 |
| POST | /api/auth/register | 注册并登录，201 |
| POST | /api/auth/login | 登录并轮换当前会话 |
| GET | /api/auth/me | 当前账号和 CSRF 信息 |
| POST | /api/auth/logout | 注销，204 |
| GET | /api/overview | 当前账号真实汇总 |
| GET | /api/templates/soccer | 可自建副本的足球示例定义 |
| GET / POST | /api/surveys | 分页列表 / 创建草稿 |
| GET / PATCH | /api/surveys/{id} | 所有者详情 / 修改截止时间 |
| PUT | /api/surveys/{id}/definition | 保存整个草稿，携带 expected_revision |
| POST | /api/surveys/{id}/validate | 发布检查，返回 errors 和 warnings |
| POST | /api/surveys/{id}/publish | 检查并发布，携带 expected_revision |
| POST | /api/surveys/{id}/close | 关闭，携带 expected_revision；已关闭时幂等返回 |
| POST | /api/surveys/{id}/preview | 所有者体验规则，不落答卷 |
| GET | /api/forms/{code} | 填写定义及可用状态，不包含 owner_id |
| POST | /api/forms/{code}/next | 重放路径前缀并返回下一题 |
| POST | /api/forms/{code}/responses | 最终提交，首次 201、幂等重试 200 |
| GET | /api/surveys/{id}/statistics | 整卷实时聚合 |
| GET | /api/surveys/{id}/questions/{qid}/statistics | 单题统计及分页原始值 |
| GET | /api/surveys/{id}/responses | 所有者分页答卷 |
| GET | /api/surveys/{id}/responses/{rid} | 所有者答卷详情 |

列表支持 page、page_size；问卷列表支持 q 标题搜索和 status=draft/published/expired/closed。问卷列表默认每页 12，原始值和答卷默认每页 20，最大每页 100。

## 定义和调用顺序

草稿字段为 title、description、settings、questions；题目字段和运算符详见 DESIGN.md 和 OpenAPI。新建返回 revision=1。保存提交完整定义及 expected_revision；以后每次写入使用上次返回的新 revision，冲突时重新加载，不盲目重试覆盖。

发布后冻结定义和 settings；修改截止时间使用 PATCH，body 为 `{ "expected_revision": 2, "deadline": "2026-10-24T12:00:00+08:00" }`；传 null 取消截止。时间必须带时区，并晚于服务端当前时刻。

下一步 body：

```json
{
  "current_question_id": "participate",
  "answers": [{ "question_id": "participate", "value": "no" }]
}
```

返回 visited_question_ids 和 next_question_id；END 表示进入确认提交页。不要将未经过题目的旧答案带入请求。

最终提交 body：

```json
{
  "request_id": "一次填写生成的至少16位随机编号",
  "definition_version": 1,
  "is_anonymous": true,
  "answers": [
    { "question_id": "participate", "value": "no" },
    { "question_id": "reason", "value": "没有合适的时间" }
  ]
}
```

填写者身份从服务端会话取得，不接受客户端身份。成功返回答卷 id、submitted_at、replayed。不要对网络重试生成新 request_id；相同编号更换答案会返回冲突。

## 第二阶段题库 API

所有接口均要求登录；写操作携带 CSRF。参数完整类型以生成的 OpenAPI 为准。题库与题目元数据修改携带 expected_revision。题目创建、另存、新版本和恢复携带稳定 request_id（16-100 位字母、数字、下划线或短横线），网络重试复用编号，改变内容另用编号。

| 方法 | 路径 | 功能 |
|---|---|---|
| GET / POST | /api/question-banks | 个人题库列表 / 创建 |
| PATCH | /api/question-banks/{bid} | 改名、说明、归档或恢复 |
| GET / POST | /api/questions | 分页列表 / 新建逻辑题目及 v1 |
| GET / PATCH | /api/questions/{qid} | 详情 / 移动题库、归档或恢复 |
| GET / POST | /api/questions/{qid}/versions | 分页历史 / 新增不可变版本 |
| GET | /api/questions/{qid}/versions/{vid} | 指定版本 |
| POST | /api/questions/{qid}/restore | 用历史内容新增版本 |
| POST | /api/questions/{qid}/fork | 另存为当前用户的新题，保留派生来源 |
| GET / POST | /api/questions/{qid}/shares | 查看共享名单 / 按用户名授权 |
| DELETE | /api/questions/{qid}/shares/{uid} | 撤销指定用户共享，body 为 expected_revision |
| GET | /api/questions/{qid}/usages | 本人引用问卷及题位、版本 |
| GET | /api/questions/{qid}/statistics | 本人跨问卷统计，按版本分组 |

题目列表 scope=mine/shared/used，分别为本人、共享给我、本人问卷引用；支持 bank_id（mine）、q、kind、archived。题库列表支持 archived。版本、引用问卷、题目列表支持 page/page_size，默认 20、最大 100。

创建题目 body 为 {request_id, bank_id, content}；content 与 QuestionContent 契约一致，没有题位 ID 与跳转。创建版本 body 为 {request_id, parent_version_id, content}；parent 必须属于同一逻辑题。另存 body 为 {request_id, bank_id, source_version_id, content}。恢复 body 为 {request_id, target_version_id, parent_version_id}，恢复来源和父版本分别记录。

问卷题目增加可选 source={question_id,version_id}。服务端要求内容与来源版本一致；不一致返回 SOURCE_MISMATCH；已有引用不能直接删 source（SOURCE_REQUIRED）。新增引用需有效授权且未归档；旧快照不受撤销影响。发布问卷沿用 DEFINITION_FROZEN。

共享 POST body 为 {expected_revision,username}，返回名单及新 revision。原作者拥有原题版本写入权；共享接收者无写入权，另存后成为新题所有者。未授权返回 404，归档暂停新增使用返回 409，同请求不同内容为 REQUEST_CONFLICT=409。

统计可传 version_id 和重复的 survey_ids，只在本人引用问卷内取交集。返回 groups，每组对应一个不可变版本：survey_count、response_count、occurrence_count（题位机会）、reached_count、answered_count（有效作答次数）、skipped_count、unanswered_count；数字 average/minimum/maximum、frequencies、frequency_total；选项 options；分页原始值 values。page/page_size 同时用于每组值与数值频次，版本分组不会合并。无值时均值和极值为 null。

撤销后若仍有本人问卷引用，access=historical，只返回已引用的版本，available_for_reuse=false；不暴露未引用的新版本内容，也不显示其他用户问卷的标题或答卷。
