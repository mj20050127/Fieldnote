import { expect, test } from "@playwright/test";

test("library versions reuse local slots, preserve unsaved edits and published snapshots, and restore history", async ({
  page,
}) => {
  const account = await page.request.post("/api/auth/register", {
    data: { username: "lib_" + Date.now(), password: "Browser-test-2026!" },
  });
  expect(account.status()).toBe(201);
  const headers = { "X-CSRF-Token": (await account.json()).csrf_token };
  await page.goto("/library");
  await page
    .getByRole("button", { name: "新建题目", exact: true })
    .first()
    .click();
  let dialog = page.getByRole("dialog", { name: "保存到题库" });
  await dialog.getByPlaceholder("新题库名称").fill("个人常用题");
  await dialog.getByRole("button", { name: "新建题库", exact: true }).click();
  await dialog.getByLabel("题型", { exact: true }).selectOption("number");
  await dialog.getByLabel("题目标题", { exact: true }).fill("年龄（周岁）");
  const created = page.waitForResponse(
    (r) =>
      r.url().endsWith("/api/questions") && r.request().method() === "POST",
  );
  await dialog.getByRole("button", { name: "保存题目", exact: true }).click();
  const family = await (await created).json();
  await expect(page).toHaveURL(new RegExp("/library/questions/" + family.id));
  const draft = await (
    await page.request.post("/api/surveys", {
      headers,
      data: {
        title: "初始标题",
        settings: { allow_anonymous: true, allow_multiple: true },
      },
    })
  ).json();
  await page.goto("/surveys/" + draft.id + "/edit");
  await page.getByLabel("问卷标题", { exact: true }).fill("尚未保存的调查标题");
  for (let i = 0; i < 2; i++) {
    await page.getByRole("button", { name: "从题库添加", exact: true }).click();
    const picker = page.getByRole("dialog", { name: "从题库选择版本" });
    await picker.getByRole("button", { name: /年龄（周岁）/ }).click();
    await picker
      .getByRole("button", { name: "采用此版本", exact: true })
      .click();
  }
  await expect(page.getByLabel("题目标题", { exact: true })).toBeDisabled();
  await page.getByRole("button", { name: "问卷信息与设置" }).click();
  await expect(page.getByLabel("问卷标题", { exact: true })).toHaveValue(
    "尚未保存的调查标题",
  );
  await page.getByRole("button", { name: "保存草稿", exact: true }).click();
  await expect(page.getByText("草稿已保存", { exact: true })).toBeVisible();
  const stored = await (
    await page.request.get("/api/surveys/" + draft.id)
  ).json();
  expect(stored.questions).toHaveLength(2);
  expect(stored.questions[0].id).not.toBe(stored.questions[1].id);
  expect(stored.questions[0].source).toEqual(stored.questions[1].source);
  await page.getByRole("button", { name: "发布问卷", exact: true }).click();
  await page
    .getByRole("dialog", { name: "确认发布问卷" })
    .getByRole("button", { name: "发布问卷", exact: true })
    .click();
  await expect(
    page.getByText("问卷已发布，可以分享链接了", { exact: true }),
  ).toBeVisible();
  const published = await (
    await page.request.get("/api/surveys/" + draft.id)
  ).json();
  const submitted = await page.request.post(
    "/api/forms/" + published.public_code + "/responses",
    {
      headers,
      data: {
        request_id: crypto.randomUUID(),
        definition_version: 1,
        is_anonymous: true,
        answers: published.questions.map((q: any, i: number) => ({
          question_id: q.id,
          value: 10 + i * 10,
        })),
      },
    },
  );
  expect(submitted.status()).toBe(201);
  await page.goto("/library/questions/" + family.id);
  await page.getByRole("button", { name: "跨卷统计", exact: true }).click();
  await expect(
    page.getByText("均值 15 · 最小 10 · 最大 20", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "创建新版本", exact: true }).click();
  dialog = page.getByRole("dialog", { name: "创建新版本", exact: true });
  await dialog.getByLabel("题目标题", { exact: true }).fill("年龄（整数周岁）");
  const newVersion = page.waitForResponse(
    (r) => r.url().endsWith("/versions") && r.request().method() === "POST",
  );
  await dialog.getByRole("button", { name: "保存题目", exact: true }).click();
  const v2 = await (await newVersion).json();
  await expect(
    page
      .getByRole("heading", { name: "年龄（整数周岁）", exact: true })
      .first(),
  ).toBeVisible();
  expect(
    (await (await page.request.get("/api/surveys/" + draft.id)).json())
      .questions,
  ).toEqual(published.questions);
  const second = await (
    await page.request.post("/api/surveys", {
      headers,
      data: { title: "换版草稿", questions: [stored.questions[0]] },
    })
  ).json();
  await page.goto("/surveys/" + second.id + "/edit");
  await page.getByRole("button", { name: "更换版本", exact: true }).click();
  const picker = page.getByRole("dialog", { name: "从题库选择版本" });
  await picker.getByLabel("固定使用版本").selectOption(v2.id);
  await picker.getByRole("button", { name: "采用此版本", exact: true }).click();
  await page.getByRole("button", { name: "保存草稿", exact: true }).click();
  await expect(page.getByText("草稿已保存", { exact: true })).toBeVisible();
  const swapped = await (
    await page.request.get("/api/surveys/" + second.id)
  ).json();
  expect(swapped.questions[0].id).toBe(stored.questions[0].id);
  expect(swapped.questions[0].source.version_id).toBe(v2.id);
  await page.goto("/library/questions/" + family.id);
  await page.getByRole("button", { name: "版本历史", exact: true }).click();
  await page.getByRole("button", { name: /^v1 ·/ }).click();
  await page.getByRole("button", { name: "恢复选中版本", exact: true }).click();
  await page
    .getByRole("dialog", { name: "恢复历史版本" })
    .getByRole("button", { name: "确定", exact: true })
    .click();
  await expect(page.getByText(/最新可见版本 v3/)).toBeVisible();
  const versions = await (
    await page.request.get("/api/questions/" + family.id + "/versions")
  ).json();
  expect(versions.total).toBe(3);
  expect(versions.items[0].restored_from_version_id).toBe(
    family.latest_version.id,
  );
});

test("sharing UI permits recipient use and fork while retaining historical access after revocation", async ({
  page,
  browser,
  baseURL,
}) => {
  const owner = await (
    await page.request.post("/api/auth/register", {
      data: {
        username: "author_" + Date.now(),
        password: "Browser-test-2026!",
      },
    })
  ).json();
  const headers = { "X-CSRF-Token": owner.csrf_token };
  const bank = await (
    await page.request.post("/api/question-banks", {
      headers,
      data: { name: "共享题库" },
    })
  ).json();
  const family = await (
    await page.request.post("/api/questions", {
      headers,
      data: {
        request_id: crypto.randomUUID(),
        bank_id: bank.id,
        content: { type: "text", title: "对校园的建议" },
      },
    })
  ).json();
  const other = await browser.newContext({ baseURL });
  try {
    const b = await (
      await other.request.post("/api/auth/register", {
        data: {
          username: "reader_" + Date.now(),
          password: "Browser-test-2026!",
        },
      })
    ).json();
    await page.goto("/library/questions/" + family.id);
    await page.getByRole("button", { name: "共享与归属", exact: true }).click();
    await page.getByPlaceholder("输入对方用户名").fill(b.username);
    await page.getByRole("button", { name: "授权使用", exact: true }).click();
    await expect(page.getByText(b.username, { exact: true })).toBeVisible();
    const bp = await other.newPage();
    await bp.goto("/library");
    await bp.getByRole("button", { name: "共享给我", exact: true }).click();
    await bp.getByRole("link", { name: /对校园的建议/ }).click();
    await expect(
      bp.getByRole("button", { name: "创建新版本", exact: true }),
    ).toHaveCount(0);
    await bp
      .getByRole("button", { name: "另存为我的题目", exact: true })
      .click();
    const dialog = bp.getByRole("dialog", {
      name: "另存为我的题目",
      exact: true,
    });
    await dialog.getByPlaceholder("新题库名称").fill("我的收藏");
    await dialog.getByRole("button", { name: "新建题库", exact: true }).click();
    await dialog.getByLabel("题目标题", { exact: true }).fill("我自己的建议题");
    await dialog.getByRole("button", { name: "保存题目", exact: true }).click();
    await expect(
      bp.getByRole("heading", { name: "我自己的建议题", exact: true }).first(),
    ).toBeVisible();
    const draft = await (
      await other.request.post("/api/surveys", {
        headers: { "X-CSRF-Token": b.csrf_token },
        data: {
          questions: [
            {
              ...family.latest_version.content,
              id: "advice",
              source: {
                question_id: family.id,
                version_id: family.latest_version.id,
              },
            },
          ],
        },
      })
    ).json();
    expect(draft.id).toBeTruthy();
    await page.getByRole("button", { name: "撤销共享", exact: true }).click();
    await page
      .getByRole("dialog", { name: "撤销共享？" })
      .getByRole("button", { name: "确定", exact: true })
      .click();
    await expect(page.getByText(b.username, { exact: true })).toHaveCount(0);
    await bp.goto("/library/questions/" + family.id);
    await expect(bp.getByText(/当前仅可查看历史内容/)).toBeVisible();
    await expect(
      bp.getByRole("button", { name: "另存为我的题目", exact: true }),
    ).toBeDisabled();
    await bp.getByRole("button", { name: "引用问卷", exact: true }).click();
    await expect(
      bp.getByText("draft · 1 个题位", { exact: true }),
    ).toBeVisible();
  } finally {
    await other.close();
  }
});

test("library mobile layout and dialog cancel protect unsaved content", async ({
  page,
}) => {
  const account = await page.request.post("/api/auth/register", {
    data: { username: "libmob_" + Date.now(), password: "Browser-test-2026!" },
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/library");
  await page
    .getByRole("navigation", { name: "工作空间导航" })
    .getByRole("link", { name: "问卷", exact: true })
    .click();
  await expect(page).toHaveURL(/\/dashboard$/);
  await page
    .getByRole("navigation", { name: "工作空间导航" })
    .getByRole("link", { name: "题库", exact: true })
    .click();
  await expect(page).toHaveURL(/\/library$/);
  await page
    .getByRole("button", { name: "新建题目", exact: true })
    .first()
    .click();
  const dialog = page.getByRole("dialog", { name: "保存到题库" });
  await dialog.getByLabel("题目标题", { exact: true }).fill("尚未保存的内容");
  await dialog.getByRole("button", { name: "取消", exact: true }).click();
  await page
    .getByRole("dialog", { name: "放弃修改？" })
    .getByRole("button", { name: "继续编辑", exact: true })
    .click();
  await expect(dialog.getByLabel("题目标题", { exact: true })).toHaveValue(
    "尚未保存的内容",
  );
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBeTruthy();
  await dialog.getByRole("button", { name: "取消", exact: true }).click();
  await page
    .getByRole("dialog", { name: "放弃修改？" })
    .getByRole("button", { name: "放弃", exact: true })
    .click();
  await expect(dialog).not.toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBeTruthy();
  const headers = { "X-CSRF-Token": (await account.json()).csrf_token };
  const bank = await (
    await page.request.post("/api/question-banks", {
      headers,
      data: { name: "手机题库" },
    })
  ).json();
  const family = await (
    await page.request.post("/api/questions", {
      headers,
      data: {
        request_id: crypto.randomUUID(),
        bank_id: bank.id,
        content: { type: "number", title: "手机版本历史布局" },
      },
    })
  ).json();
  await page.goto("/library/questions/" + family.id);
  for (const tab of ["版本历史", "跨卷统计"]) {
    await page.getByRole("button", { name: tab, exact: true }).click();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBeTruthy();
  }
});
