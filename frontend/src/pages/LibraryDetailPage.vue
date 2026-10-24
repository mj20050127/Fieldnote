<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import { api, formatDate, typeLabels } from "../api";
import {
  contentOf,
  type Bank,
  type CrossStatistics,
  type LibraryQuestion,
  type Shares,
  type Usages,
  type Version,
  type Versions,
} from "../library";
import AppShell from "../components/AppShell.vue";
import LibrarySaveDialog from "../components/LibrarySaveDialog.vue";
const route = useRoute(),
  router = useRouter(),
  id = String(route.params.id),
  root = "/questions/" + id;
const question = ref<LibraryQuestion>(),
  versions = ref<Versions>(),
  selected = ref<Version>(),
  compare = ref<Version>(),
  shares = ref<Shares>(),
  usages = ref<Usages>(),
  banks = ref<Bank[]>([]),
  stats = ref<CrossStatistics>();
const tab = ref("content"),
  error = ref(""),
  busy = ref(false),
  dialog = ref(false),
  fork = ref(false),
  username = ref(""),
  bankId = ref(""),
  historyPage = ref(1),
  usagePage = ref(1),
  statsPage = ref(1),
  filterVersion = ref(""),
  filterSurvey = ref("");
const filterVersions = ref<Version[]>([]),
  filterUsages = ref<NonNullable<Usages>["items"]>([]);
const filterVersionPage = ref(1),
  filterUsagePage = ref(1);
let restoreOperation = { payload: "", requestId: "" };
const differences = computed(() => {
  if (!selected.value || !compare.value) return [];
  const labels: Record<string, string> = {
    type: "题型",
    title: "题目标题",
    description: "说明",
    required: "必答设置",
    options: "选项",
    validation: "校验规则",
  };
  const a = contentOf(compare.value.content),
    b = contentOf(selected.value.content);
  return (Object.keys(a) as (keyof typeof a)[])
    .filter((key) => JSON.stringify(a[key]) !== JSON.stringify(b[key]))
    .map((key) => ({
      field: labels[key],
      before: JSON.stringify(a[key]),
      after: JSON.stringify(b[key]),
    }));
});
async function loadHistory() {
  versions.value = await api<Versions>(
    root + "/versions?page=" + historyPage.value,
  );
}
async function loadUsages() {
  usages.value = await api<Usages>(root + "/usages?page=" + usagePage.value);
}
async function loadStats() {
  try {
    error.value = "";
    stats.value = await api<CrossStatistics>(
      root +
        "/statistics?" +
        new URLSearchParams({
          page: String(statsPage.value),
          ...(filterVersion.value ? { version_id: filterVersion.value } : {}),
          ...(filterSurvey.value ? { survey_ids: filterSurvey.value } : {}),
        }),
    );
  } catch (e) {
    error.value = (e as Error).message;
  }
}
async function load() {
  busy.value = true;
  error.value = "";
  try {
    question.value = await api<LibraryQuestion>(root);
    selected.value = question.value.latest_version;
    bankId.value = question.value.bank_id;
    await loadHistory();
    await loadUsages();
    filterVersions.value = versions.value!.items;
    filterUsages.value = usages.value!.items;
    filterVersionPage.value = 1;
    filterUsagePage.value = 1;
    if (question.value.access === "owner") {
      shares.value = await api<Shares>(root + "/shares");
      banks.value = (await api<{ items: Bank[] }>("/question-banks")).items;
    }
    await loadStats();
  } catch (e) {
    error.value = (e as Error).message;
  } finally {
    busy.value = false;
  }
}
async function chooseVersion(version: Version) {
  selected.value = version;
  compare.value = undefined;
  if (version.parent_version_id) {
    try {
      compare.value = await api<Version>(
        root + "/versions/" + version.parent_version_id,
      );
    } catch {
      /* An unshared parent need not be visible to a historical reader. */
    }
  }
}
async function mutate(action: () => Promise<unknown>) {
  if (busy.value) return;
  busy.value = true;
  error.value = "";
  try {
    await action();
    await load();
  } catch (e) {
    error.value = (e as Error).message;
  } finally {
    busy.value = false;
  }
}
async function restore() {
  if (!selected.value || !question.value) return;
  const target = selected.value,
    parent = question.value.latest_version;
  try {
    await ElMessageBox.confirm(
      `以 v${target.version_no} 的内容创建新版本，现有历史与问卷保持完整。`,
      "恢复历史版本",
    );
  } catch {
    return;
  }
  const payload = JSON.stringify([target.id, parent.id]);
  if (restoreOperation.payload !== payload)
    restoreOperation = { payload, requestId: crypto.randomUUID() };
  const requestId = restoreOperation.requestId;
  await mutate(() =>
    api(root + "/restore", {
      request_id: requestId,
      target_version_id: target.id,
      parent_version_id: parent.id,
    }),
  );
}
async function saved(version: Version) {
  if (version.question_id !== id) {
    router.push("/library/questions/" + version.question_id);
    return;
  }
  await load();
  tab.value = "history";
}
async function addShare() {
  if (!shares.value) return;
  await mutate(() =>
    api(root + "/shares", {
      expected_revision: shares.value!.revision,
      username: username.value,
    }),
  );
  username.value = "";
}
async function revoke(uid: string) {
  try {
    await ElMessageBox.confirm(
      "撤销后，对方已保存的问卷快照与历史统计仍保留，不能再新增引用。",
      "撤销共享？",
    );
  } catch {
    return;
  }
  await mutate(() =>
    api(
      root + "/shares/" + uid,
      { expected_revision: shares.value!.revision },
      "DELETE",
    ),
  );
}
async function archive() {
  if (!question.value) return;
  try {
    await ElMessageBox.confirm(
      "已有问卷和版本历史均会保留。",
      question.value.archived ? "恢复题目？" : "归档题目？",
    );
  } catch {
    return;
  }
  await mutate(() =>
    api(
      root,
      {
        expected_revision: question.value!.revision,
        archived: !question.value!.archived,
      },
      "PATCH",
    ),
  );
}
onMounted(load);
async function moreFilters(versionsOnly: boolean) {
  try {
    if (versionsOnly) {
      const data = await api<Versions>(
        root + "/versions?page=" + (filterVersionPage.value + 1),
      );
      filterVersions.value.push(...data.items);
      filterVersionPage.value++;
    } else {
      const data = await api<Usages>(
        root + "/usages?page=" + (filterUsagePage.value + 1),
      );
      filterUsages.value.push(...data.items);
      filterUsagePage.value++;
    }
  } catch (e) {
    error.value = (e as Error).message;
  }
}
</script>
<template>
  <AppShell title="题目详情">
    <RouterLink to="/library" class="text-button">← 返回题库</RouterLink>
    <p v-if="error" class="error-banner" role="alert">{{ error }}</p>
    <template v-if="question && selected">
      <div class="page-heading">
        <div>
          <span class="eyebrow">QUESTION LIBRARY</span>
          <h1>{{ question.latest_version.content.title }}</h1>
          <p class="muted">
            {{ question.owner_username }} · 最新可见版本 v{{
              question.latest_version.version_no
            }}
            · {{ typeLabels[question.latest_version.content.type] }}
          </p>
          <p v-if="question.derived_from" class="muted">
            派生自题目 {{ question.derived_from.question_id }} /
            {{ question.derived_from.version_id }}
          </p>
        </div>
        <div class="button-row">
          <button
            class="button primary"
            :disabled="busy || !question.available_for_reuse"
            @click="
              fork = question.access !== 'owner';
              dialog = true;
            "
          >
            {{ question.access === "owner" ? "创建新版本" : "另存为我的题目" }}
          </button>
          <button
            v-if="question.access === 'owner'"
            class="button"
            :disabled="busy"
            @click="archive"
          >
            {{ question.archived ? "恢复题目" : "归档题目" }}
          </button>
        </div>
      </div>
      <p v-if="!question.available_for_reuse" class="notice-bar">
        当前仅可查看历史内容与本人统计，新增引用需要有效授权且题目、题库未归档。
      </p>
      <nav class="library-tabs">
        <button
          v-for="item in [
            { id: 'content', name: '题目内容' },
            { id: 'history', name: '版本历史' },
            { id: 'usages', name: '引用问卷' },
            { id: 'stats', name: '跨卷统计' },
            ...(question.access === 'owner'
              ? [{ id: 'shares', name: '共享与归属' }]
              : []),
          ]"
          :key="item.id"
          :class="{ active: tab === item.id }"
          @click="tab = item.id"
        >
          {{ item.name }}
        </button>
      </nav>
      <section v-if="tab === 'content'" class="library-panel">
        <span class="type-pill"
          >v{{ selected.version_no }} ·
          {{ typeLabels[selected.content.type] }}</span
        >
        <h2>{{ selected.content.title }}</h2>
        <p>{{ selected.content.description }}</p>
        <p class="muted">
          {{ selected.content.required ? "必答题" : "选答题" }} · 创建于
          {{ formatDate(selected.created_at) }}
        </p>
        <ol v-if="selected.content.options.length">
          <li v-for="option in selected.content.options" :key="option.id">
            {{ option.text }}
          </li>
        </ol>
        <h3>校验规则</h3>
        <dl class="library-rules">
          <template
            v-for="(value, key) in selected.content.validation"
            :key="key"
            ><template v-if="value !== null && value !== false"
              ><dt>
                {{
                  {
                    min_choices: "最少选择",
                    max_choices: "最多选择",
                    min_length: "最少字数",
                    max_length: "最多字数",
                    min_value: "最小值",
                    max_value: "最大值",
                    integer_only: "仅允许整数",
                  }[key]
                }}
              </dt>
              <dd>{{ value }}</dd></template
            ></template
          >
        </dl>
      </section>
      <section v-if="tab === 'history'" class="library-panel">
        <p class="muted">
          版本只新增；父版本展示分支来源。点击版本可查看内容及与父版本的差异。
        </p>
        <div class="library-history">
          <button
            v-for="v in versions?.items"
            :key="v.id"
            class="library-pick-item"
            :class="{ active: selected.id === v.id }"
            @click="chooseVersion(v)"
          >
            <strong>v{{ v.version_no }} · {{ v.content.title }}</strong
            ><small
              >{{ formatDate(v.created_at) }} ·
              {{
                v.parent_version_id
                  ? "父版本 " + v.parent_version_id.slice(0, 8)
                  : "初始版本"
              }}{{
                v.restored_from_version_id
                  ? " · 恢复自 " + v.restored_from_version_id.slice(0, 8)
                  : ""
              }}</small
            >
          </button>
        </div>
        <div class="library-pagination">
          <button
            class="button"
            :disabled="historyPage <= 1"
            @click="
              historyPage--;
              loadHistory().catch((e) => (error = e.message));
            "
          >
            上一页</button
          ><span>共 {{ versions?.total }} 个版本 · 第 {{ historyPage }} 页</span
          ><button
            class="button"
            :disabled="historyPage * 20 >= (versions?.total || 0)"
            @click="
              historyPage++;
              loadHistory().catch((e) => (error = e.message));
            "
          >
            下一页
          </button>
        </div>
        <h3>选中 v{{ selected.version_no }}：{{ selected.content.title }}</h3>
        <p>{{ selected.content.description }}</p>
        <p v-for="option in selected.content.options" :key="option.id">
          {{ option.text }}
        </p>
        <template v-if="compare"
          ><h3>与父版本 v{{ compare.version_no }} 的差异</h3>
          <p v-if="!differences.length" class="muted">内容一致。</p>
          <div
            v-for="diff in differences"
            :key="diff.field"
            class="library-diff"
          >
            <strong>{{ diff.field }}</strong>
            <p>原内容：{{ diff.before }}</p>
            <p>新内容：{{ diff.after }}</p>
          </div></template
        >
        <div class="button-row">
          <button
            v-if="question.access === 'owner'"
            class="button"
            :disabled="busy || !question.available_for_reuse"
            @click="restore"
          >
            恢复选中版本</button
          ><button
            class="button"
            :disabled="busy || !question.available_for_reuse"
            @click="
              fork = true;
              dialog = true;
            "
          >
            将选中版本另存为我的题目
          </button>
        </div>
      </section>
      <section v-if="tab === 'usages'" class="library-panel">
        <h2>我的引用问卷</h2>
        <p class="muted">
          仅列出当前账号的问卷，不显示其他使用者的问卷与答卷。
        </p>
        <div
          v-for="usage in usages?.items"
          :key="usage.survey_id"
          class="library-usage"
        >
          <RouterLink :to="`/surveys/${usage.survey_id}/edit`"
            >{{ usage.title }} →</RouterLink
          ><small>{{ usage.status }} · {{ usage.slots.length }} 个题位</small
          ><code v-for="s in usage.slots" :key="s.instance_id"
            >{{ s.instance_id }} / {{ s.version_id.slice(0, 8) }}</code
          >
        </div>
        <p v-if="!usages?.total">尚未被本人的问卷引用。</p>
        <div class="library-pagination">
          <button
            class="button"
            :disabled="usagePage <= 1"
            @click="
              usagePage--;
              loadUsages().catch((e) => (error = e.message));
            "
          >
            上一页</button
          ><span>共 {{ usages?.total }} 份问卷</span
          ><button
            class="button"
            :disabled="usagePage * 20 >= (usages?.total || 0)"
            @click="
              usagePage++;
              loadUsages().catch((e) => (error = e.message));
            "
          >
            下一页
          </button>
        </div>
      </section>
      <section v-if="tab === 'shares' && shares" class="library-panel">
        <h2>共享设置</h2>
        <p class="muted">
          对方可以使用所有版本（包括以后新增版本），也可另存新题；原题修改权属于你。
        </p>
        <form class="library-toolbar" @submit.prevent="addShare">
          <input
            class="form-input"
            v-model="username"
            placeholder="输入对方用户名"
            minlength="3"
            maxlength="32"
            required
          /><button class="button primary" :disabled="busy">授权使用</button>
        </form>
        <div
          v-for="recipient in shares.items"
          :key="recipient.id"
          class="library-usage button-row"
        >
          <span>{{ recipient.username }}</span
          ><button
            class="text-button danger"
            :disabled="busy"
            @click="revoke(recipient.id)"
          >
            撤销共享
          </button>
        </div>
        <h3>所属题库</h3>
        <div class="button-row">
          <select class="form-input" v-model="bankId" aria-label="移动到题库">
            <option v-for="bank in banks" :key="bank.id" :value="bank.id">
              {{ bank.name }}
            </option></select
          ><button
            class="button"
            :disabled="busy || bankId === question.bank_id"
            @click="
              mutate(() =>
                api(
                  root,
                  { expected_revision: question!.revision, bank_id: bankId },
                  'PATCH',
                ),
              )
            "
          >
            移动题目
          </button>
        </div>
      </section>
      <section v-if="tab === 'stats'" class="library-panel">
        <h2>跨问卷统计</h2>
        <p class="muted">
          每个版本分别统计。同一份答卷多次遇到本题时，答卷份数与作答次数分别计数。
        </p>
        <form
          class="library-toolbar"
          @submit.prevent="
            statsPage = 1;
            loadStats();
          "
        >
          <select
            class="form-input"
            v-model="filterVersion"
            aria-label="统计版本"
          >
            <option value="">全部引用版本</option>
            <option
              v-for="version in filterVersions"
              :key="version.id"
              :value="version.id"
            >
              v{{ version.version_no }} · {{ version.content.title }}
            </option></select
          ><select
            class="form-input"
            v-model="filterSurvey"
            aria-label="统计问卷"
          >
            <option value="">本人全部问卷</option>
            <option
              v-for="usage in filterUsages"
              :key="usage.survey_id"
              :value="usage.survey_id"
            >
              {{ usage.title }}
            </option></select
          ><button class="button">应用筛选</button>
        </form>
        <div class="button-row">
          <button
            v-if="filterVersions.length < (versions?.total || 0)"
            class="text-button"
            @click="moreFilters(true)"
          >
            加载更多版本</button
          ><button
            v-if="filterUsages.length < (usages?.total || 0)"
            class="text-button"
            @click="moreFilters(false)"
          >
            加载更多问卷
          </button>
        </div>
        <article
          v-for="group in stats?.groups"
          :key="group.version.id"
          class="library-stat-group"
        >
          <h3>
            v{{ group.version.version_no }} · {{ group.version.content.title }}
          </h3>
          <button
            class="text-button small"
            @click="
              filterVersion = group.version.id;
              statsPage = 1;
              loadStats();
            "
          >
            仅查看此版本
          </button>
          <p>
            {{ group.survey_count }} 份问卷 · {{ group.response_count }} 份答卷
            · {{ group.occurrence_count }} 次题位机会
          </p>
          <div class="library-metrics">
            <span
              >有效作答 <strong>{{ group.answered_count }}</strong></span
            ><span
              >未到达 <strong>{{ group.skipped_count }}</strong></span
            ><span
              >到达未答 <strong>{{ group.unanswered_count }}</strong></span
            >
          </div>
          <p v-if="group.version.content.type === 'number'">
            均值 {{ group.average ?? "—" }} · 最小 {{ group.minimum ?? "—" }} ·
            最大 {{ group.maximum ?? "—" }}
          </p>
          <div
            v-for="option in group.options"
            :key="option.id"
            class="library-distribution"
          >
            <span>{{ option.text }}</span
            ><progress
              :value="option.count"
              :max="group.answered_count || 1"
            /><span>{{ option.count }} 次（{{ option.percentage }}%）</span>
          </div>
          <template v-if="group.version.content.type === 'number'"
            ><h3>数值频次分布（{{ group.frequency_total }} 个数值）</h3>
            <div
              v-for="frequency in group.frequencies"
              :key="frequency.value"
              class="library-distribution"
            >
              <span>{{ frequency.value }}</span
              ><progress
                :value="frequency.count"
                :max="group.answered_count || 1"
              /><span>{{ frequency.count }} 次</span>
            </div></template
          >
          <h3>作答记录 · 第 {{ statsPage }} 页</h3>
          <p
            v-for="(value, index) in group.values"
            :key="index"
            class="library-answer"
          >
            {{
              Array.isArray(value.value) ? value.value.join("、") : value.value
            }}
            <small>{{ formatDate(value.submitted_at) }}</small>
          </p>
        </article>
        <div class="library-pagination">
          <button
            class="button"
            :disabled="statsPage <= 1"
            @click="
              statsPage--;
              loadStats();
            "
          >
            上一页</button
          ><span>第 {{ statsPage }} 页，每页 20 条</span
          ><button
            class="button"
            :disabled="
              !stats?.groups.some(
                (g) =>
                  g.answered_count > statsPage * 20 ||
                  g.frequency_total > statsPage * 20,
              )
            "
            @click="
              statsPage++;
              loadStats();
            "
          >
            下一页
          </button>
        </div>
      </section>
      <LibrarySaveDialog
        v-model="dialog"
        :initial="selected.content"
        :question-id="id"
        :parent="selected.id"
        :fork="fork"
        @saved="saved"
      />
    </template>
  </AppShell>
</template>
