<script setup lang="ts">
import { ref, watch } from "vue";
import { ElDialog } from "element-plus";
import { api, typeLabels } from "../api";
import {
  type LibraryList,
  type LibraryQuestion,
  type Version,
  type Versions,
} from "../library";
const open = defineModel<boolean>({ required: true });
const props = defineProps<{ questionId?: string }>();
const emit = defineEmits<{ choose: [version: Version] }>();
const result = ref<LibraryList>(),
  selected = ref<LibraryQuestion>(),
  versions = ref<Version[]>([]),
  versionId = ref(""),
  scope = ref("mine"),
  query = ref(""),
  kind = ref(""),
  page = ref(1),
  error = ref(""),
  busy = ref(false),
  versionPage = ref(1),
  versionTotal = ref(0);
async function load() {
  busy.value = true;
  error.value = "";
  try {
    result.value = await api<LibraryList>(
      "/questions?" +
        new URLSearchParams({
          scope: scope.value,
          q: query.value,
          page: String(page.value),
          ...(kind.value ? { kind: kind.value } : {}),
        }),
    );
  } catch (e) {
    error.value = (e as Error).message;
  } finally {
    busy.value = false;
  }
}
async function choose(question: LibraryQuestion) {
  selected.value = question;
  versions.value = [];
  versionId.value = "";
  versionPage.value = 1;
  await loadVersions();
}
async function loadVersions() {
  if (!selected.value) return;
  busy.value = true;
  try {
    const data = await api<Versions>(
      `/questions/${selected.value.id}/versions?page=${versionPage.value}`,
    );
    versions.value = data.items;
    versionTotal.value = data.total;
    versionId.value = versions.value[0]?.id || "";
  } catch (e) {
    error.value = (e as Error).message;
  } finally {
    busy.value = false;
  }
}
function accept() {
  const v = versions.value.find((v) => v.id === versionId.value);
  if (v) {
    emit("choose", v);
    open.value = false;
  }
}
watch(open, async (value) => {
  if (!value) return;
  selected.value = undefined;
  versions.value = [];
  error.value = "";
  page.value = 1;
  if (props.questionId) {
    try {
      await choose(
        await api<LibraryQuestion>("/questions/" + props.questionId),
      );
    } catch (e) {
      error.value = (e as Error).message;
    }
  } else await load();
});
</script>
<template>
  <el-dialog
    v-model="open"
    title="从题库选择版本"
    width="760px"
    :close-on-click-modal="false"
  >
    <p class="muted">
      选中的版本将固定保存到问卷中。新加入的题目默认顺序进入下一题。
    </p>
    <template v-if="!questionId">
      <form
        class="library-toolbar"
        @submit.prevent="
          page = 1;
          load();
        "
      >
        <select
          v-model="scope"
          class="form-input"
          aria-label="题目范围"
          @change="
            page = 1;
            load();
          "
        >
          <option value="mine">我的题目</option>
          <option value="shared">共享给我</option>
        </select>
        <input class="form-input" v-model="query" placeholder="搜索题目" />
        <select v-model="kind" class="form-input" aria-label="题型筛选">
          <option value="">全部题型</option>
          <option v-for="(label, key) in typeLabels" :key="key" :value="key">
            {{ label }}
          </option></select
        ><button class="button" :disabled="busy">搜索</button>
      </form>
      <div class="library-pick-list">
        <button
          v-for="item in result?.items"
          :key="item.id"
          class="library-pick-item"
          :class="{ active: selected?.id === item.id }"
          :disabled="!item.available_for_reuse"
          @click="choose(item)"
        >
          {{ item.latest_version.content.title
          }}<small
            >{{ typeLabels[item.latest_version.content.type] }} · v{{
              item.latest_version.version_no
            }}
            · {{ item.owner_username }}</small
          >
        </button>
      </div>
      <p v-if="!busy && result?.total === 0" class="muted">
        暂无可用题目，可先到题库创建或请作者共享。
      </p>
      <div v-if="(result?.total || 0) > 20" class="library-pagination">
        <button
          :disabled="page <= 1 || busy"
          @click="
            page--;
            load();
          "
        >
          上一页</button
        ><span>第 {{ page }} 页</span
        ><button
          :disabled="page * 20 >= (result?.total || 0) || busy"
          @click="
            page++;
            load();
          "
        >
          下一页
        </button>
      </div>
    </template>
    <template v-if="selected"
      ><h3>{{ selected.latest_version.content.title }}</h3>
      <label class="field-label"
        >固定使用版本<select
          class="form-input"
          v-model="versionId"
          aria-label="固定使用版本"
        >
          <option v-for="v in versions" :key="v.id" :value="v.id">
            v{{ v.version_no }} · {{ v.content.title }}
          </option>
        </select></label
      >
      <div v-if="versionTotal > 20" class="library-pagination">
        <button
          :disabled="versionPage <= 1 || busy"
          @click="
            versionPage--;
            loadVersions();
          "
        >
          较新版本</button
        ><button
          :disabled="versionPage * 20 >= versionTotal || busy"
          @click="
            versionPage++;
            loadVersions();
          "
        >
          更早版本
        </button>
      </div>
      <p>{{ versions.find((v) => v.id === versionId)?.content.description }}</p>
    </template>
    <p v-if="error" role="alert" class="error-banner">{{ error }}</p>
    <template #footer
      ><button class="button" @click="open = false">取消</button
      ><button
        class="button primary"
        :disabled="!versionId || busy || !selected?.available_for_reuse"
        @click="accept"
      >
        采用此版本
      </button></template
    >
  </el-dialog>
</template>
