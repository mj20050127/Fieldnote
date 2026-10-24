<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { onBeforeRouteLeave } from "vue-router";
import { ElDialog, ElMessage, ElMessageBox } from "element-plus";
import { api } from "../api";
import {
  blankContent,
  contentOf,
  type Bank,
  type Content,
  type LibraryQuestion,
  type Version,
} from "../library";
import QuestionContentEditor from "./QuestionContentEditor.vue";
const open = defineModel<boolean>({ required: true });
const props = defineProps<{
  initial?: Content;
  questionId?: string;
  parent?: string;
  fork?: boolean;
}>();
const emit = defineEmits<{ saved: [version: Version] }>();
const content = ref(blankContent()),
  banks = ref<Bank[]>([]),
  bankId = ref(""),
  bankName = ref(""),
  busy = ref(false),
  error = ref("");
let requestId = "",
  attempted = "",
  original = "";
watch(open, async (value) => {
  if (!value) return;
  content.value = props.initial ? contentOf(props.initial) : blankContent();
  original = JSON.stringify(content.value);
  error.value = "";
  requestId = crypto.randomUUID();
  attempted = "";
  try {
    banks.value = (await api<{ items: Bank[] }>("/question-banks")).items;
    bankId.value = banks.value[0]?.id || "";
  } catch (e) {
    error.value = (e as Error).message;
  }
});
async function createBank() {
  if (!bankName.value.trim()) return;
  busy.value = true;
  try {
    const bank = await api<Bank>("/question-banks", { name: bankName.value });
    banks.value.push(bank);
    bankId.value = bank.id;
    bankName.value = "";
  } catch (e) {
    error.value = (e as Error).message;
  } finally {
    busy.value = false;
  }
}
async function save() {
  if (busy.value) return;
  busy.value = true;
  error.value = "";
  try {
    const payload = {
      content: contentOf(content.value),
      ...(props.questionId && !props.fork
        ? { parent_version_id: props.parent }
        : { bank_id: bankId.value }),
      ...(props.fork ? { source_version_id: props.parent } : {}),
    };
    const serialized = JSON.stringify(payload);
    if (attempted && attempted !== serialized) requestId = crypto.randomUUID();
    attempted = serialized;
    const endpoint = props.questionId
      ? `/questions/${props.questionId}/${props.fork ? "fork" : "versions"}`
      : "/questions";
    const result = await api<LibraryQuestion | Version>(endpoint, {
      ...payload,
      request_id: requestId,
    });
    original = JSON.stringify(content.value);
    open.value = false;
    busy.value = false;
    await nextTick();
    emit("saved", "latest_version" in result ? result.latest_version : result);
    ElMessage.success("已保存到题库");
  } catch (e) {
    error.value = (e as Error).message;
  } finally {
    busy.value = false;
  }
}
async function beforeClose(done: () => void) {
  if (busy.value) return;
  if (JSON.stringify(content.value) !== original) {
    try {
      await ElMessageBox.confirm(
        "关闭后，这次未保存的题目修改将丢失。",
        "放弃修改？",
        { confirmButtonText: "放弃", cancelButtonText: "继续编辑" },
      );
    } catch {
      return;
    }
  }
  done();
}
function unload(event: BeforeUnloadEvent) {
  if (open.value && JSON.stringify(content.value) !== original) {
    event.preventDefault();
    event.returnValue = "";
  }
}
onMounted(() => window.addEventListener("beforeunload", unload));
onBeforeUnmount(() => window.removeEventListener("beforeunload", unload));
onBeforeRouteLeave(async () => {
  if (!open.value) return true;
  let leave = false;
  await beforeClose(() => {
    leave = true;
    open.value = false;
  });
  return leave;
});
</script>
<template>
  <el-dialog
    v-model="open"
    :title="
      questionId ? (fork ? '另存为我的题目' : '创建新版本') : '保存到题库'
    "
    width="700px"
    :before-close="beforeClose"
    :close-on-click-modal="false"
    destroy-on-close
  >
    <p class="muted">
      每次保存都会新增不可覆盖的版本。问卷跳转仍由各份问卷单独配置。
    </p>
    <template v-if="!questionId || fork">
      <label class="field-label"
        >存入题库<select
          class="form-input"
          v-model="bankId"
          aria-label="存入题库"
        >
          <option v-for="bank in banks" :key="bank.id" :value="bank.id">
            {{ bank.name }}
          </option>
        </select></label
      >
      <div class="button-row">
        <input
          class="form-input"
          v-model="bankName"
          placeholder="新题库名称"
          maxlength="100"
        /><button
          class="button"
          :disabled="busy || !bankName.trim()"
          @click="createBank"
        >
          新建题库
        </button>
      </div>
    </template>
    <QuestionContentEditor v-model="content" :readonly="busy" />
    <p v-if="error" role="alert" class="error-banner">{{ error }}</p>
    <template #footer
      ><button
        class="button"
        :disabled="busy"
        @click="beforeClose(() => (open = false))"
      >
        取消</button
      ><button
        class="button primary"
        :disabled="busy || ((!questionId || fork) && !bankId)"
        @click="save"
      >
        保存题目
      </button></template
    >
  </el-dialog>
</template>
