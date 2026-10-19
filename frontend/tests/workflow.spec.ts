import { expect, test } from "@playwright/test";

test("deadline changes preserve unsaved questions and settings until the draft is saved", async ({
  page,
}) => {
  const account = await page.request.post("/api/auth/register", {
    data: {
      username: `deadline_${Date.now()}`,
      password: "Browser-test-2026!",
    },
  });
  expect(account.status()).toBe(201);
  const headers = { "X-CSRF-Token": (await account.json()).csrf_token };
  const created = await page.request.post("/api/surveys", {
    headers,
    data: { title: "原始标题" },
  });
  expect(created.status()).toBe(201);
  const survey = await created.json();
  const endpoint = `/api/surveys/${survey.id}`;
  await page.goto(`/surveys/${survey.id}/edit`);
  await page.getByLabel("问卷标题", { exact: true }).fill("尚未保存的新标题");
  await page.getByLabel("问卷说明", { exact: true }).fill("尚未保存的新说明");
  await page
    .locator(".setting-row")
    .filter({ hasText: "允许多次填写" })
    .locator(".el-switch")
    .click();
  await page.getByRole("button", { name: "文本填空", exact: true }).click();
  await page.getByLabel("题目标题", { exact: true }).fill("尚未保存的新题目");
  await page.getByRole("button", { name: "问卷信息与设置" }).click();

  const deadlineSetting = page
    .locator(".setting-row")
    .filter({ hasText: "截止时间" });
  await deadlineSetting
    .getByRole("button", { name: "设置", exact: true })
    .click();
  const dialog = page.getByRole("dialog", { name: "设置截止时间" });
  const future = new Date(Date.now() + 7 * 86400000);
  const date = [
    future.getFullYear(),
    ...[future.getMonth() + 1, future.getDate()].map((value) =>
      String(value).padStart(2, "0"),
    ),
  ].join("-");
  const dateInput = dialog.getByPlaceholder("不限时间", { exact: true });
  await dateInput.fill(`${date} 12:00:00`);
  await dateInput.press("Tab");
  const updated = page.waitForResponse(
    (response) =>
      response.url().endsWith(endpoint) &&
      response.request().method() === "PATCH",
  );
  await dialog.getByRole("button", { name: "保存设置", exact: true }).click();
  expect((await updated).status()).toBe(200);
  await expect(dialog).not.toBeVisible();
  await expect(page.getByLabel("问卷标题", { exact: true })).toHaveValue(
    "尚未保存的新标题",
  );
  await expect(page.getByLabel("问卷说明", { exact: true })).toHaveValue(
    "尚未保存的新说明",
  );
  await expect(
    page.getByRole("button", { name: /尚未保存的新题目/ }),
  ).toBeVisible();
  await expect(page.getByText(/有未保存的更改/)).toBeVisible();
  const stored = await (await page.request.get(endpoint)).json();
  expect(stored.title).toBe("原始标题");
  expect(stored.questions).toEqual([]);
  expect(stored.settings.allow_multiple).toBe(false);
  expect(stored.deadline).not.toBeNull();
  expect(stored.revision).toBe(2);

  await deadlineSetting
    .getByRole("button", { name: "设置", exact: true })
    .click();
  await dateInput.fill("");
  await dateInput.press("Tab");
  await dialog.getByRole("button", { name: "保存设置", exact: true }).click();
  await expect(dialog).not.toBeVisible();
  await expect(page.getByText(/有未保存的更改/)).toBeVisible();
  const cleared = await (await page.request.get(endpoint)).json();
  expect(cleared.deadline).toBeNull();
  expect(cleared.revision).toBe(3);

  await page.getByRole("button", { name: "保存草稿", exact: true }).click();
  await expect(page.getByText("草稿已保存", { exact: true })).toBeVisible();
  const saved = await (await page.request.get(endpoint)).json();
  expect(saved.title).toBe("尚未保存的新标题");
  expect(saved.description).toBe("尚未保存的新说明");
  expect(saved.settings.allow_multiple).toBe(true);
  expect(saved.questions).toHaveLength(1);
  expect(saved.questions[0].title).toBe("尚未保存的新题目");
  expect(saved.revision).toBe(4);
  await page.reload();
  await expect(
    page.getByRole("heading", { name: "尚未保存的新标题", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: /尚未保存的新题目/ }),
  ).toBeVisible();
  await expect(page.getByText(/所有更改已保存/)).toBeVisible();
});

test("a deadline revision conflict keeps the unsaved draft and dialog", async ({
  page,
}) => {
  const account = await page.request.post("/api/auth/register", {
    data: {
      username: `conflict_${Date.now()}`,
      password: "Browser-test-2026!",
    },
  });
  expect(account.status()).toBe(201);
  const headers = { "X-CSRF-Token": (await account.json()).csrf_token };
  const created = await page.request.post("/api/surveys", {
    headers,
    data: { title: "服务器原始标题" },
  });
  expect(created.status()).toBe(201);
  const survey = await created.json();
  const endpoint = `/api/surveys/${survey.id}`;
  await page.goto(`/surveys/${survey.id}/edit`);
  await page
    .getByLabel("问卷标题", { exact: true })
    .fill("冲突时仍需保留的标题");
  await page
    .locator(".setting-row")
    .filter({ hasText: "截止时间" })
    .getByRole("button", { name: "设置", exact: true })
    .click();
  const concurrent = await page.request.patch(endpoint, {
    headers,
    data: {
      expected_revision: 1,
      deadline: new Date(Date.now() + 86400000).toISOString(),
    },
  });
  expect(concurrent.status()).toBe(200);
  const dialog = page.getByRole("dialog", { name: "设置截止时间" });
  await dialog.getByRole("button", { name: "保存设置", exact: true }).click();
  await expect(
    page.getByText("问卷已被修改或状态已变化，请重新加载后再操作", {
      exact: true,
    }),
  ).toBeVisible();
  await expect(dialog).toBeVisible();
  await expect(page.getByLabel("问卷标题", { exact: true })).toHaveValue(
    "冲突时仍需保留的标题",
  );
  await expect(page.getByText(/有未保存的更改/)).toBeVisible();
  await expect(
    dialog.getByRole("button", { name: "保存设置", exact: true }),
  ).toBeEnabled();
  const stored = await (await page.request.get(endpoint)).json();
  expect(stored.title).toBe("服务器原始标题");
  expect(stored.revision).toBe(2);
  expect(stored.deadline).not.toBeNull();
});

test("text limits count Unicode code points consistently", async ({ page }) => {
  const account = await page.request.post("/api/auth/register", {
    data: { username: `unicode_${Date.now()}`, password: "Browser-test-2026!" },
  });
  expect(account.status()).toBe(201);
  const csrf = (await account.json()).csrf_token;
  const headers = { "X-CSRF-Token": csrf };
  const created = await page.request.post("/api/surveys", {
    headers,
    data: {
      title: "Unicode 字数验证",
      questions: [
        {
          id: "text",
          type: "text",
          title: "两个码点",
          validation: { min_length: 2, max_length: 2 },
        },
      ],
    },
  });
  const survey = await created.json();
  expect(
    (
      await page.request.post(`/api/surveys/${survey.id}/publish`, {
        headers,
        data: { expected_revision: 1 },
      })
    ).status(),
  ).toBe(200);
  await page.goto(`/survey/${survey.public_code}`);
  await page.getByRole("button", { name: "开始填写", exact: true }).click();
  await page.getByLabel("两个码点", { exact: true }).fill("你🙂");
  await expect(page.locator(".answer-count")).toHaveText("2 / 2 字");
  await page.getByRole("button", { name: "下一步", exact: true }).click();
  await page.getByRole("button", { name: "确认提交", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "你的声音，已经被听见。" }),
  ).toBeVisible();
});

test("create → edit → publish → branch → submit → statistics", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/login");
  await page.getByRole("button", { name: "注册账号", exact: true }).click();
  await page
    .getByLabel("用户名", { exact: true })
    .fill(`browser_${Date.now()}`);
  await page.getByLabel("密码", { exact: true }).fill("Browser-test-2026!");
  await page.getByRole("button", { name: "创建账号", exact: true }).click();
  await expect(page.getByRole("heading", { name: "我的问卷" })).toBeVisible();
  await page.getByRole("button", { name: "从示例问卷开始" }).click();
  await expect(
    page.getByRole("button", { name: "发布问卷", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "问卷信息与设置" }).click();
  await page
    .getByLabel("问卷标题", { exact: true })
    .fill("浏览器端到端验证问卷");
  await page.getByRole("button", { name: "保存草稿", exact: true }).click();
  await expect(page.getByText("草稿已保存", { exact: true })).toBeVisible();
  const editorUrl = page.url();
  await page.getByRole("button", { name: "预览", exact: true }).click();
  await page.getByRole("button", { name: "开始填写", exact: true }).click();
  await page.getByText("暂时没有参加", { exact: true }).click();
  await page.getByRole("button", { name: "下一步", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "是什么让你还没有参加？" }),
  ).toBeVisible();
  await page.getByRole("link", { name: "返回编辑器", exact: true }).click();
  await page.getByRole("button", { name: "发布问卷", exact: true }).click();
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "发布问卷", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "分享问卷", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "问卷信息与设置" }).click();
  const publicPath = await page
    .getByRole("link", { name: "打开填写页" })
    .getAttribute("href");
  await page.goto(publicPath!);
  await page.getByRole("button", { name: "开始填写", exact: true }).click();
  await page.getByRole("button", { name: "下一步", exact: true }).click();
  await expect(
    page.getByRole("alert").filter({ hasText: "必答题" }),
  ).toBeVisible();
  await page.getByText("暂时没有参加", { exact: true }).click();
  await page.getByRole("button", { name: "下一步", exact: true }).click();
  await page
    .getByLabel("是什么让你还没有参加？", { exact: true })
    .fill("课业时间冲突");
  await page.getByRole("button", { name: "下一步", exact: true }).click();
  await page.getByRole("button", { name: "下一步", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "谢谢，现在确认一下。" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "确认提交", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "你的声音，已经被听见。" }),
  ).toBeVisible();
  await page.goto(editorUrl.replace("/edit", "/statistics"));
  await page.getByRole("button", { name: /原始答卷/ }).click();
  await expect(page.getByText("匿名填写", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "查看答卷" }).click();
  await expect(page.getByText("课业时间冲突", { exact: true })).toBeVisible();
  expect(errors).toEqual([]);
});

test("changing an earlier answer clears the old branch; mobile layout fits", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/login");
  await page.getByRole("button", { name: "注册账号", exact: true }).click();
  await page.getByLabel("用户名", { exact: true }).fill(`mobile_${Date.now()}`);
  await page.getByLabel("密码", { exact: true }).fill("Browser-test-2026!");
  await page.getByRole("button", { name: "创建账号", exact: true }).click();
  await page.getByRole("button", { name: "从示例问卷开始" }).click();
  await page.getByRole("button", { name: "预览", exact: true }).click();
  await page.getByRole("button", { name: "开始填写", exact: true }).click();
  await page.getByText("参加，经常在球场见！", { exact: true }).click();
  await page.getByRole("button", { name: "下一步", exact: true }).click();
  await page.getByLabel("你每周大约踢几次球？", { exact: true }).fill("3");
  await page.getByRole("button", { name: "下一步", exact: true }).click();
  await page.getByText("校园比赛", { exact: true }).click();
  await page.getByRole("button", { name: "下一步", exact: true }).click();
  await page.getByRole("button", { name: "上一步", exact: true }).click();
  await page.getByRole("button", { name: "上一步", exact: true }).click();
  await page.getByRole("button", { name: "上一步", exact: true }).click();
  await page.getByText("暂时没有参加", { exact: true }).click();
  await page.getByRole("button", { name: "下一步", exact: true }).click();
  await page
    .getByLabel("是什么让你还没有参加？", { exact: true })
    .fill("没有找到伙伴");
  await page.getByRole("button", { name: "下一步", exact: true }).click();
  await page.getByRole("button", { name: "下一步", exact: true }).click();
  await expect(page.getByText("没有找到伙伴", { exact: true })).toBeVisible();
  await expect(page.locator(".review-answers")).not.toContainText("校园比赛");
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBeTruthy();
  await page.getByRole("button", { name: "完成预览", exact: true }).click();
  await expect(page.getByRole("heading", { name: "预览完成" })).toBeVisible();
});
