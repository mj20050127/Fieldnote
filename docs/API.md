# API 使用说明

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
