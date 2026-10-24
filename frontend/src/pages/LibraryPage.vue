<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { ElMessageBox } from "element-plus";
import { api, typeLabels } from "../api";
import { type Bank, type LibraryList, type Version } from "../library";
import AppShell from "../components/AppShell.vue";
import LibrarySaveDialog from "../components/LibrarySaveDialog.vue";
const router = useRouter();
const banks = ref<Bank[]>([]),
  result = ref<LibraryList>(),
  scope = ref("mine"),
  archived = ref(false),
  bankId = ref(""),
  query = ref(""),
  kind = ref(""),
  page = ref(1),
  error = ref(""),
  busy = ref(false),
  saveDialog = ref(false);
async function load() {
  error.value = "";
  busy.value = true;
  try {
    banks.value = (
      await api<{ items: Bank[] }>(`/question-banks?archived=${archived.value}`)
    ).items;
    result.value = await api<LibraryList>(
      "/questions?" +
        new URLSearchParams({
          scope: scope.value,
          archived: String(archived.value),
          q: query.value,
          page: String(page.value),
          ...(scope.value === "mine" && bankId.value
            ? { bank_id: bankId.value }
            : {}),
          ...(kind.value ? { kind: kind.value } : {}),
        }),
    );
  } catch (e) {
    error.value = (e as Error).message;
  } finally {
    busy.value = false;
  }
}
async function bankAction(bank?: Bank, archive = false) {
  try {
    if (archive && bank) {
      await ElMessageBox.confirm(
        "归档后保留历史引用，暂停新增引用。",
        bank.archived ? "恢复题库？" : "归档题库？",
      );
      await api(
        "/question-banks/" + bank.id,
        { expected_revision: bank.revision, archived: !bank.archived },
        "PATCH",
      );
    } else {
      const value = await ElMessageBox.prompt(
        "输入题库名称",
        bank ? "重命名题库" : "新建题库",
        {
          inputValue: bank?.name || "",
          inputValidator: (v) => !!v?.trim() || "名称不能为空",
        },
      );
      await api(
        "/question-banks" + (bank ? "/" + bank.id : ""),
        {
          name: value.value,
          ...(bank ? { expected_revision: bank.revision } : {}),
        },
        bank ? "PATCH" : "POST",
      );
    }
    bankId.value = "";
    await load();
  } catch (e) {
    if (e instanceof Error) error.value = e.message;
  }
}
function saved(version: Version) {
  router.push("/library/questions/" + version.question_id);
}
onMounted(load);
</script>
<template>
  <AppShell title="题库">
    <div class="page-heading">
      <div>
        <span class="eyebrow">A GOOD QUESTION CAN GO FURTHER</span>
        <h1>让好问题继续生长</h1>
        <p class="muted">独立管理题目、固定每个版本，在多份问卷中复用。</p>
      </div>
      <div class="button-row">
        <button class="button" @click="bankAction()">新建题库</button
        ><button class="button primary" @click="saveDialog = true">
          新建题目
        </button>
      </div>
    </div>
    <div class="library-layout">
      <aside class="library-banks">
        <button
          class="library-pick-item"
          :class="{ active: scope === 'mine' && !bankId }"
          @click="
            scope = 'mine';
            bankId = '';
            page = 1;
            load();
          "
        >
          我的全部题目
        </button>
        <button
          class="library-pick-item"
          :class="{ active: scope === 'shared' }"
          @click="
            scope = 'shared';
            bankId = '';
            page = 1;
            load();
          "
        >
          共享给我
        </button>
        <button
          class="library-pick-item"
          :class="{ active: scope === 'used' }"
          @click="
            scope = 'used';
            bankId = '';
            page = 1;
            load();
          "
        >
          我的问卷引用
        </button>
        <h3>我的题库</h3>
        <div v-for="bank in banks" :key="bank.id" class="library-bank-row">
          <button
            class="text-button"
            :class="{ active: bankId === bank.id }"
            @click="
              scope = 'mine';
              bankId = bank.id;
              page = 1;
              load();
            "
          >
            {{ bank.name }}
          </button>
          <div class="button-row">
            <button class="text-button small" @click="bankAction(bank)">
              改名</button
            ><button class="text-button small" @click="bankAction(bank, true)">
              {{ bank.archived ? "恢复" : "归档" }}
            </button>
          </div>
        </div>
        <label class="inline-label"
          ><input
            type="checkbox"
            v-model="archived"
            @change="
              bankId = '';
              page = 1;
              load();
            "
          />
          查看已归档</label
        >
      </aside>
      <section>
        <form
          class="library-toolbar"
          @submit.prevent="
            page = 1;
            load();
          "
        >
          <input
            class="form-input"
            v-model="query"
            placeholder="搜索题目标题"
          /><select v-model="kind" class="form-input" aria-label="题型筛选">
            <option value="">全部题型</option>
            <option v-for="(label, key) in typeLabels" :value="key" :key="key">
              {{ label }}
            </option></select
          ><button class="button" :disabled="busy">搜索</button>
        </form>
        <p v-if="error" class="error-banner" role="alert">{{ error }}</p>
        <p v-if="busy" class="muted">正在读取题库…</p>
        <div class="library-question-grid">
          <RouterLink
            v-for="item in result?.items"
            :key="item.id"
            :to="'/library/questions/' + item.id"
            class="library-question-card"
            ><div class="button-row">
              <span class="type-pill">{{
                typeLabels[item.latest_version.content.type]
              }}</span
              ><span class="muted">v{{ item.latest_version.version_no }}</span>
            </div>
            <h3>{{ item.latest_version.content.title }}</h3>
            <p class="muted">
              {{
                item.latest_version.content.description ||
                "查看内容、历史与跨卷统计"
              }}
            </p>
            <small
              >{{ item.owner_username }} ·
              {{
                item.access === "owner"
                  ? "我的题目"
                  : item.access === "shared"
                    ? "共享题目"
                    : "历史引用"
              }}{{
                !item.available_for_reuse ? " · 暂不可新增引用" : ""
              }}</small
            ></RouterLink
          >
        </div>
        <div v-if="!busy && result?.total === 0" class="library-empty">
          <h2>从一道好问题开始</h2>
          <p>创建第一道题目，或请其他作者按你的用户名共享。</p>
          <button class="button primary" @click="saveDialog = true">
            新建题目
          </button>
        </div>
        <div class="library-pagination" v-if="result">
          <span>共 {{ result.total }} 道题目</span
          ><button
            class="button"
            :disabled="page <= 1 || busy"
            @click="
              page--;
              load();
            "
          >
            上一页</button
          ><span>第 {{ page }} 页</span
          ><button
            class="button"
            :disabled="page * 20 >= result.total || busy"
            @click="
              page++;
              load();
            "
          >
            下一页
          </button>
        </div>
      </section>
    </div>
    <LibrarySaveDialog v-model="saveDialog" @saved="saved" />
  </AppShell>
</template>
