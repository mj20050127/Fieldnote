<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { onBeforeRouteLeave, useRoute, useRouter } from "vue-router";
import {
  ElMessage,
  ElMessageBox,
  ElSwitch,
  ElInputNumber,
  ElSelect,
  ElOption,
  ElDialog,
  ElDatePicker,
} from "element-plus";
import {
  api,
  ApiError,
  definitionOf,
  formatDate,
  statusLabels,
  typeLabels,
  type DefinitionCheck,
  type Question,
  type Rule,
  type Survey,
} from "../api";
import AppShell from "../components/AppShell.vue";
import Icon from "../components/Icon.vue";
import QuestionInput from "../components/QuestionInput.vue";
import LibraryPicker from "../components/LibraryPicker.vue";
import LibrarySaveDialog from "../components/LibrarySaveDialog.vue";
import { api as libraryApi } from "../api";
import {
  applyVersion,
  instanceOf,
  type LibraryQuestion,
  type Version,
} from "../library";
const route = useRoute(),
  router = useRouter(),
  id = String(route.params.id);
const survey = ref<Survey>(),
  selected = ref(""),
  snapshot = ref(""),
  busy = ref(false),
  error = ref(""),
  checks = ref<DefinitionCheck>();
const previewValue = ref<unknown>(null),
  settingsTab = ref(false),
  deadlineDialog = ref(false),
  deadline = ref<Date | null>(null);
const q = computed(() =>
  survey.value?.questions.find((item) => item.id === selected.value),
);
const editable = computed(() => survey.value?.status === "draft");
const contentEditable = computed(() => editable.value && !q.value?.source);
const picker = ref(false),
  librarySave = ref(false),
  replaceVersion = ref(false),
  sourceQuestion = ref<LibraryQuestion>();
const sourceVersionNo = ref<number>();
async function refreshSource() {
  sourceQuestion.value = undefined;
  sourceVersionNo.value = undefined;
  const source = q.value?.source;
  if (source) {
    try {
      const detail = await libraryApi<LibraryQuestion>(
        "/questions/" + source.question_id,
      );
      const version = await libraryApi<Version>(
        `/questions/${source.question_id}/versions/${source.version_id}`,
      );
      if (q.value?.source?.version_id === source.version_id) {
        sourceQuestion.value = detail;
        sourceVersionNo.value = version.version_no;
      }
    } catch {
      /* Snapshot remains usable. */
    }
  }
}
function useLibraryVersion(version: Version) {
  if (!survey.value || !editable.value) return;
  if (replaceVersion.value && q.value) applyVersion(q.value, version);
  else {
    if (survey.value.questions.length >= 100) return;
    const item = instanceOf(version);
    survey.value.questions.push(item);
    select(item.id);
  }
  checks.value = undefined;
  refreshSource();
  ElMessage.success("已加入本地草稿，请保存并检查跳转配置");
}
const dirty = computed(
  () =>
    !!survey.value &&
    JSON.stringify(definitionOf(survey.value)) !== snapshot.value,
);
const position = computed(
  () =>
    survey.value?.questions.findIndex((item) => item.id === selected.value) ??
    -1,
);
const targets = computed(
  () => survey.value?.questions.slice(position.value + 1) || [],
);
const typeIcons: Record<string, string> = {
  single_choice: "circle",
  multiple_choice: "multi",
  text: "text",
  number: "number",
};
const operators = computed(() =>
  q.value?.type === "single_choice"
    ? [{ id: "eq", text: "等于" }]
    : q.value?.type === "multiple_choice"
      ? [
          { id: "contains_any", text: "包含任意一项" },
          { id: "contains_all", text: "包含全部选项" },
        ]
      : [
          { id: "eq", text: "等于" },
          { id: "gt", text: "大于" },
          { id: "gte", text: "大于等于" },
          { id: "lt", text: "小于" },
          { id: "lte", text: "小于等于" },
        ],
);
async function load() {
  error.value = "";
  try {
    survey.value = await api<Survey>(`/surveys/${id}`);
    snapshot.value = JSON.stringify(definitionOf(survey.value));
    selected.value = survey.value.questions[0]?.id || "";
    await refreshSource();
  } catch (e) {
    error.value = (e as Error).message;
  }
}
function select(qid: string) {
  selected.value = qid;
  settingsTab.value = false;
  previewValue.value = null;
  refreshSource();
}
function addQuestion(type: Question["type"]) {
  if (!survey.value || !editable.value) return;
  const question: Question = {
    id: `q_${crypto.randomUUID().replaceAll("-", "")}`,
    type,
    title: "",
    description: "",
    required: true,
    options: type.includes("choice")
      ? [
          { id: `o_${crypto.randomUUID()}`, text: "选项一" },
          { id: `o_${crypto.randomUUID()}`, text: "选项二" },
        ]
      : [],
    validation: {
      min_choices: null,
      max_choices: null,
      min_length: null,
      max_length: null,
      min_value: null,
      max_value: null,
      integer_only: false,
    },
    routing: { rules: [], default_target: "NEXT" },
    source: null,
  };
  survey.value.questions.push(question);
  select(question.id);
  checks.value = undefined;
}
function addOption() {
  q.value?.options.push({
    id: `o_${crypto.randomUUID()}`,
    text: `选项 ${q.value.options.length + 1}`,
  });
}
function move(index: number, delta: number) {
  if (!survey.value) return;
  const target = index + delta;
  if (target < 0 || target >= survey.value.questions.length) return;
  const [question] = survey.value.questions.splice(index, 1);
  survey.value.questions.splice(target, 0, question!);
  checks.value = undefined;
}
async function removeQuestion() {
  if (!survey.value || !q.value) return;
  try {
    await ElMessageBox.confirm(
      "删除后请检查其他题目的跳转目标。",
      "删除这道题？",
      { confirmButtonText: "删除", cancelButtonText: "保留", type: "warning" },
    );
  } catch {
    return;
  }
  survey.value.questions.splice(position.value, 1);
  selected.value = survey.value.questions[0]?.id || "";
  checks.value = undefined;
}
function addRule() {
  if (!q.value) return;
  q.value.routing.rules.push({
    operator: q.value.type === "multiple_choice" ? "contains_any" : "eq",
    value:
      q.value.type === "number"
        ? 0
        : q.value.type === "multiple_choice"
          ? []
          : q.value.options[0]?.id || "",
    target: "NEXT",
  });
}
async function save() {
  if (!survey.value || !editable.value) return false;
  busy.value = true;
  try {
    survey.value = await api<Survey>(
      `/surveys/${id}/definition`,
      {
        ...definitionOf(survey.value),
        expected_revision: survey.value.revision,
      },
      "PUT",
    );
    snapshot.value = JSON.stringify(definitionOf(survey.value));
    checks.value = undefined;
    ElMessage.success("草稿已保存");
    return true;
  } catch (e) {
    ElMessage.error((e as Error).message);
    return false;
  } finally {
    busy.value = false;
  }
}
async function validate() {
  if (dirty.value && !(await save())) return false;
  try {
    checks.value = await api<DefinitionCheck>(`/surveys/${id}/validate`, {});
    if (!checks.value.valid) {
      const first = checks.value.errors[0];
      if (first?.question_id) select(first.question_id);
      return false;
    }
    return true;
  } catch (e) {
    ElMessage.error((e as Error).message);
    return false;
  }
}
async function publish() {
  if (!survey.value || !(await validate())) return;
  try {
    await ElMessageBox.confirm(
      "发布后题目、跳转和填写设置将固定。你仍然可以调整截止时间或关闭问卷。",
      "确认发布问卷",
      { confirmButtonText: "发布问卷", cancelButtonText: "再检查一下" },
    );
  } catch {
    return;
  }
  busy.value = true;
  try {
    survey.value = await api<Survey>(`/surveys/${id}/publish`, {
      expected_revision: survey.value.revision,
    });
    snapshot.value = JSON.stringify(definitionOf(survey.value));
    ElMessage.success("问卷已发布，可以分享链接了");
  } catch (e) {
    ElMessage.error((e as Error).message);
  } finally {
    busy.value = false;
  }
}
async function preview() {
  if (await validate()) router.push(`/surveys/${id}/preview`);
}
async function close() {
  if (!survey.value) return;
  try {
    await ElMessageBox.confirm(
      "关闭后将停止接收新答卷，已有答卷和统计会保留。",
      "关闭问卷",
      {
        confirmButtonText: "关闭问卷",
        cancelButtonText: "取消",
        type: "warning",
      },
    );
  } catch {
    return;
  }
  try {
    survey.value = await api<Survey>(`/surveys/${id}/close`, {
      expected_revision: survey.value.revision,
    });
    ElMessage.success("问卷已关闭");
  } catch (e) {
    ElMessage.error((e as Error).message);
  }
}
async function updateDeadline() {
  if (!survey.value || busy.value) return;
  busy.value = true;
  try {
    const updated = await api<Survey>(
      `/surveys/${id}`,
      {
        expected_revision: survey.value.revision,
        deadline: deadline.value?.toISOString() || null,
      },
      "PATCH",
    );
    // Adopt server metadata while preserving the local definition and its unsaved state.
    survey.value = { ...updated, ...definitionOf(survey.value) };
    deadlineDialog.value = false;
    ElMessage.success("截止时间已更新");
  } catch (e) {
    ElMessage.error((e as Error).message);
  } finally {
    busy.value = false;
  }
}
async function share() {
  try {
    await navigator.clipboard.writeText(
      `${location.origin}/survey/${survey.value?.public_code}`,
    );
    ElMessage.success("分享链接已复制");
  } catch {
    ElMessage.error("复制失败，请打开填写页面后复制浏览器网址");
  }
}
function unload(event: BeforeUnloadEvent) {
  if (dirty.value) {
    event.preventDefault();
    event.returnValue = "";
  }
}
onBeforeRouteLeave(async () => {
  if (!dirty.value) return true;
  try {
    await ElMessageBox.confirm(
      "当前更改尚未保存，离开后会丢失。",
      "离开编辑器？",
      { confirmButtonText: "放弃并离开", cancelButtonText: "继续编辑" },
    );
    return true;
  } catch {
    return false;
  }
});
onMounted(() => {
  load();
  window.addEventListener("beforeunload", unload);
});
onBeforeUnmount(() => window.removeEventListener("beforeunload", unload));
</script>
<template>
  <AppShell title="问卷编辑器">
    <div v-if="error" class="empty-state" role="alert">
      <p>{{ error }}</p>
      <button class="button" @click="load">重试</button>
    </div>
    <div v-else-if="!survey" class="loading-state">正在打开编辑器…</div>
    <template v-else>
      <div class="editor-heading">
        <div>
          <RouterLink to="/dashboard" class="back-link"
            ><Icon name="back" :size="16" /> 我的问卷</RouterLink
          >
          <div class="editor-title">
            <h1>{{ survey.title }}</h1>
            <span class="status-badge" :class="survey.effective_status">{{
              statusLabels[survey.effective_status]
            }}</span>
          </div>
          <p class="muted small">
            {{ dirty ? "有未保存的更改" : "所有更改已保存" }} ·
            {{ survey.questions.length }} 道题目
          </p>
        </div>
        <div class="button-row">
          <button class="button" :disabled="busy" @click="preview">
            <Icon name="eye" :size="17" /> 预览</button
          ><button
            v-if="editable"
            class="button"
            :disabled="busy"
            @click="save"
          >
            保存草稿</button
          ><button
            v-if="editable"
            class="button primary"
            :disabled="busy"
            @click="publish"
          >
            <Icon name="send" :size="17" /> 发布问卷</button
          ><button v-else class="button primary" @click="share">
            <Icon name="link" :size="17" /> 分享问卷
          </button>
        </div>
      </div>
      <div v-if="!editable" class="notice-bar">
        <Icon name="shield" :size="18" /><span
          >问卷定义已固定，已有答卷会始终对应这一版本。</span
        ><RouterLink :to="`/surveys/${id}/statistics`">查看统计 →</RouterLink>
      </div>
      <div
        v-if="checks && (checks.errors.length || checks.warnings.length)"
        class="validation-list"
      >
        <button
          v-for="issue in [...checks.errors, ...checks.warnings]"
          :key="issue.code + issue.question_id + issue.message"
          @click="issue.question_id && select(issue.question_id)"
        >
          {{
            issue.question_id
              ? `题目 ${survey.questions.findIndex((v) => v.id === issue.question_id) + 1}：`
              : ""
          }}{{ issue.message }}
        </button>
      </div>
      <div class="editor-workspace" :class="{ saving: busy }">
        <aside class="question-sidebar">
          <div class="panel-title">
            问卷结构 <span>{{ survey.questions.length }}</span>
          </div>
          <button
            class="question-list-item"
            :class="{ active: settingsTab }"
            @click="settingsTab = true"
          >
            <Icon name="file" :size="18" /><span>问卷信息与设置</span>
          </button>
          <div class="question-list-divider" />
          <button
            v-for="(question, index) in survey.questions"
            :key="question.id"
            class="question-list-item"
            :class="{ active: selected === question.id && !settingsTab }"
            @click="select(question.id)"
          >
            <span class="question-index">{{
              String(index + 1).padStart(2, "0")
            }}</span
            ><span>{{ question.title || "未命名题目" }}</span
            ><Icon :name="typeIcons[question.type] || 'file'" :size="15" />
          </button>
          <div v-if="editable" class="add-questions">
            <button
              :disabled="survey.questions.length >= 100"
              @click="
                replaceVersion = false;
                picker = true;
              "
            >
              从题库添加
            </button>
            <span>添加题目</span
            ><button
              v-for="(label, type) in typeLabels"
              :key="type"
              :disabled="survey.questions.length >= 100"
              @click="addQuestion(type as Question['type'])"
            >
              <Icon :name="typeIcons[type] || 'file'" :size="17" />{{ label
              }}<Icon name="plus" :size="14" />
            </button>
          </div>
        </aside>
        <section class="editor-canvas">
          <div v-if="settingsTab || !q" class="definition-card">
            <span class="eyebrow">START WITH A GOOD QUESTION</span>
            <h2>问卷信息</h2>
            <label class="field-label" for="survey-title">问卷标题</label
            ><input
              id="survey-title"
              v-model="survey.title"
              class="form-input"
              maxlength="120"
              :disabled="!editable"
              placeholder="给你的问卷起一个名字"
            /><label class="field-label" for="survey-description"
              >问卷说明</label
            ><textarea
              id="survey-description"
              v-model="survey.description"
              rows="5"
              class="form-input"
              maxlength="3000"
              :disabled="!editable"
              placeholder="告诉填写者，这份问卷为什么重要…"
            />
            <div class="setting-row">
              <div>
                <strong>允许匿名填写</strong>
                <p>填写者仍需登录，创建者看不到匿名答卷的账号。</p>
              </div>
              <el-switch
                v-model="survey.settings.allow_anonymous"
                :disabled="!editable"
              />
            </div>
            <div class="setting-row">
              <div>
                <strong>允许多次填写</strong>
                <p>开启后，同一账号可主动提交多份答卷。</p>
              </div>
              <el-switch
                v-model="survey.settings.allow_multiple"
                :disabled="!editable"
              />
            </div>
            <div class="setting-row">
              <div>
                <strong>截止时间</strong>
                <p>{{ formatDate(survey.deadline) }}</p>
              </div>
              <button
                class="button small-button"
                :disabled="busy"
                @click="
                  deadline = survey.deadline ? new Date(survey.deadline) : null;
                  deadlineDialog = true;
                "
              >
                设置
              </button>
            </div>
            <div v-if="survey.status !== 'draft'" class="published-links">
              <RouterLink
                :to="`/survey/${survey.public_code}`"
                class="button"
                target="_blank"
                >打开填写页 <Icon name="arrow" :size="15" /></RouterLink
              ><button
                v-if="survey.status === 'published'"
                class="text-button danger"
                @click="close"
              >
                关闭问卷
              </button>
            </div>
          </div>
          <template v-else
            ><div class="canvas-caption">
              <span>QUESTION {{ String(position + 1).padStart(2, "0") }}</span
              ><span>{{ typeLabels[q.type] }}</span>
            </div>
            <div class="question-edit-card">
              <div class="library-source" v-if="q.source">
                <RouterLink :to="'/library/questions/' + q.source.question_id"
                  >题库来源 ·
                  {{
                    sourceVersionNo
                      ? "v" + sourceVersionNo
                      : q.source.version_id.slice(0, 8)
                  }}
                  →</RouterLink
                >
                <span v-if="sourceQuestion">{{
                  sourceQuestion.latest_version.id === q.source.version_id
                    ? "已使用最新可见版本"
                    : "存在其他可选版本（最新 v" +
                      sourceQuestion.latest_version.version_no +
                      "）"
                }}</span>
                <p>题目内容固定于所选版本，跳转规则由本问卷单独设置。</p>
                <div v-if="editable" class="button-row">
                  <button
                    class="text-button"
                    :disabled="!sourceQuestion?.available_for_reuse"
                    @click="
                      replaceVersion = true;
                      picker = true;
                    "
                  >
                    更换版本</button
                  ><button
                    class="text-button"
                    :disabled="!sourceQuestion?.available_for_reuse"
                    @click="librarySave = true"
                  >
                    {{
                      sourceQuestion?.access === "owner"
                        ? "编辑并生成新版本"
                        : "另存为我的题目"
                    }}
                  </button>
                </div>
              </div>
              <button
                v-else-if="editable"
                class="text-button"
                @click="librarySave = true"
              >
                保存到题库
              </button>
              <div class="question-edit-toolbar">
                <span class="type-pill"
                  ><Icon :name="typeIcons[q.type] || 'file'" :size="16" />{{
                    typeLabels[q.type]
                  }}</span
                >
                <div v-if="editable" class="button-row">
                  <button
                    class="icon-button"
                    :disabled="position === 0"
                    title="上移题目"
                    @click="move(position, -1)"
                  >
                    <Icon name="up" :size="17" /></button
                  ><button
                    class="icon-button"
                    :disabled="position === survey.questions.length - 1"
                    title="下移题目"
                    @click="move(position, 1)"
                  >
                    <Icon name="down" :size="17" /></button
                  ><button
                    class="icon-button danger"
                    title="删除题目"
                    @click="removeQuestion"
                  >
                    <Icon name="trash" :size="17" />
                  </button>
                </div>
              </div>
              <textarea
                v-model="q.title"
                class="question-title-input"
                rows="2"
                maxlength="500"
                :disabled="!contentEditable"
                placeholder="在这里写下你的问题…"
                aria-label="题目标题"
              /><input
                v-model="q.description"
                class="question-description-input"
                :disabled="!contentEditable"
                maxlength="1000"
                placeholder="添加说明（可选）"
                aria-label="题目说明"
              />
              <div v-if="q.type.includes('choice')" class="option-editor">
                <div
                  v-for="(option, index) in q.options"
                  :key="option.id"
                  class="option-edit-row"
                >
                  <span>{{ String.fromCharCode(65 + index) }}</span
                  ><input
                    v-model="option.text"
                    :aria-label="`选项 ${index + 1}`"
                    :disabled="!contentEditable"
                    maxlength="200"
                  /><button
                    v-if="contentEditable"
                    class="icon-button"
                    title="删除选项"
                    @click="q.options.splice(index, 1)"
                  >
                    <Icon name="trash" :size="15" />
                  </button>
                </div>
                <button
                  v-if="contentEditable"
                  class="text-button"
                  :disabled="q.options.length >= 50"
                  @click="addOption"
                >
                  <Icon name="plus" :size="16" /> 添加选项
                </button>
              </div>
              <div v-else class="input-preview">
                <QuestionInput
                  :question="q"
                  v-model="previewValue"
                  disabled
                /><span
                  >填写者将在这里输入{{
                    q.type === "number" ? "数字" : "文字"
                  }}</span
                >
              </div>
            </div>
            <p class="canvas-tip">
              <Icon name="leaf" :size="16" />
              简单清晰的问题，更容易得到真实的回答。
            </p></template
          >
        </section>
        <aside class="settings-panel">
          <template v-if="q && !settingsTab"
            ><div class="panel-title">题目设置</div>
            <div class="setting-toggle">
              <span>必答题</span
              ><el-switch v-model="q.required" :disabled="!contentEditable" />
            </div>
            <div class="config-section">
              <h3>回答限制</h3>
              <template v-if="q.type === 'multiple_choice'"
                ><label>最少选择</label
                ><el-input-number
                  v-model="q.validation.min_choices"
                  :min="0"
                  :max="q.options.length"
                  :disabled="!contentEditable"
                  controls-position="right"
                  placeholder="不限" /><label>最多选择</label
                ><el-input-number
                  v-model="q.validation.max_choices"
                  :min="0"
                  :max="q.options.length"
                  :disabled="!contentEditable"
                  controls-position="right"
                  placeholder="不限" /></template
              ><template v-else-if="q.type === 'text'"
                ><label>最少字数</label
                ><el-input-number
                  v-model="q.validation.min_length"
                  :min="0"
                  :max="10000"
                  :disabled="!contentEditable"
                  controls-position="right"
                  placeholder="不限" /><label>最多字数</label
                ><el-input-number
                  v-model="q.validation.max_length"
                  :min="0"
                  :max="10000"
                  :disabled="!contentEditable"
                  controls-position="right"
                  placeholder="不限" /></template
              ><template v-else-if="q.type === 'number'"
                ><label>最小值</label
                ><el-input-number
                  v-model="q.validation.min_value"
                  :disabled="!contentEditable"
                  controls-position="right"
                  placeholder="不限" /><label>最大值</label
                ><el-input-number
                  v-model="q.validation.max_value"
                  :disabled="!contentEditable"
                  controls-position="right"
                  placeholder="不限" />
                <div class="setting-toggle">
                  <span>仅允许整数</span
                  ><el-switch
                    v-model="q.validation.integer_only"
                    :disabled="!contentEditable"
                  /></div
              ></template>
              <p v-else class="muted small">填写者选择一个选项。</p>
            </div>
            <div class="config-section">
              <h3>题目跳转 <span class="tiny-label">按顺序首条匹配</span></h3>
              <div
                v-for="(rule, index) in q.routing.rules"
                :key="index"
                class="rule-card"
              >
                <div class="rule-heading">
                  <strong>条件 {{ index + 1 }}</strong
                  ><button
                    v-if="editable"
                    class="icon-button"
                    title="删除条件"
                    @click="q.routing.rules.splice(index, 1)"
                  >
                    <Icon name="trash" :size="14" />
                  </button>
                </div>
                <el-select
                  v-model="rule.operator"
                  :disabled="!editable"
                  aria-label="跳转运算符"
                  ><el-option
                    v-for="op in operators"
                    :key="op.id"
                    :label="op.text"
                    :value="op.id" /></el-select
                ><el-select
                  v-if="q.type === 'single_choice'"
                  :model-value="
                    typeof rule.value === 'string' ? rule.value : ''
                  "
                  @update:model-value="rule.value = $event"
                  :disabled="!editable"
                  placeholder="选择选项"
                  ><el-option
                    v-for="option in q.options"
                    :key="option.id"
                    :label="option.text"
                    :value="option.id" /></el-select
                ><el-select
                  v-else-if="q.type === 'multiple_choice'"
                  :model-value="Array.isArray(rule.value) ? rule.value : []"
                  @update:model-value="rule.value = $event"
                  multiple
                  :disabled="!editable"
                  placeholder="选择选项"
                  ><el-option
                    v-for="option in q.options"
                    :key="option.id"
                    :label="option.text"
                    :value="option.id" /></el-select
                ><el-input-number
                  v-else
                  :model-value="
                    typeof rule.value === 'number' ? rule.value : null
                  "
                  @update:model-value="rule.value = $event"
                  :disabled="!editable"
                  controls-position="right"
                /><label>则跳转到</label
                ><el-select v-model="rule.target" :disabled="!editable"
                  ><el-option label="下一题" value="NEXT" /><el-option
                    v-for="target in targets"
                    :key="target.id"
                    :label="target.title || '未命名题目'"
                    :value="target.id" /><el-option
                    label="结束问卷"
                    value="END"
                /></el-select>
                <div v-if="editable" class="rule-reorder">
                  <button
                    :disabled="index === 0"
                    @click="
                      [q.routing.rules[index - 1], q.routing.rules[index]] = [
                        q.routing.rules[index]!,
                        q.routing.rules[index - 1]!,
                      ]
                    "
                  >
                    上移</button
                  ><button
                    :disabled="index === q.routing.rules.length - 1"
                    @click="
                      [q.routing.rules[index + 1], q.routing.rules[index]] = [
                        q.routing.rules[index]!,
                        q.routing.rules[index + 1]!,
                      ]
                    "
                  >
                    下移
                  </button>
                </div>
              </div>
              <button
                v-if="editable && q.type !== 'text'"
                class="button full-width small-button"
                :disabled="q.routing.rules.length >= 20"
                @click="addRule"
              >
                <Icon name="plus" :size="15" /> 添加跳转条件</button
              ><label>未命中条件时</label
              ><el-select
                v-model="q.routing.default_target"
                :disabled="!editable"
                ><el-option label="下一题" value="NEXT" /><el-option
                  v-for="target in targets"
                  :key="target.id"
                  :label="target.title || '未命名题目'"
                  :value="target.id" /><el-option label="结束问卷" value="END"
              /></el-select></div></template
          ><template v-else
            ><div class="panel-title">小小提示</div>
            <div class="editor-help">
              <Icon name="leaf" :size="30" />
              <h3>让填写者了解你的初衷</h3>
              <p>一个清楚的标题和简短的说明，能让大家更愿意分享真实的想法。</p>
              <p>
                发布后，题目与填写设置会固定。发布之前，可以先预览完整的填写流程。
              </p>
            </div></template
          >
        </aside>
      </div>
    </template>
    <el-dialog
      v-model="deadlineDialog"
      title="设置截止时间"
      width="min(440px, 92vw)"
      ><p class="muted">
        按当前浏览器时区选择，服务端统一保存为 UTC。清空表示不限时间。
      </p>
      <el-date-picker
        v-model="deadline"
        type="datetime"
        :disabled="busy"
        placeholder="不限时间"
        style="width: 100%"
      /><template #footer
        ><button
          class="button"
          :disabled="busy"
          @click="deadlineDialog = false"
        >
          取消</button
        ><button
          class="button primary"
          :disabled="busy"
          @click="updateDeadline"
        >
          保存设置
        </button></template
      ></el-dialog
    >
    <LibraryPicker
      v-model="picker"
      :question-id="replaceVersion ? q?.source?.question_id : undefined"
      @choose="useLibraryVersion"
    />
    <LibrarySaveDialog
      v-if="q"
      v-model="librarySave"
      :initial="q"
      :question-id="q.source?.question_id"
      :parent="q.source?.version_id"
      :fork="!!q.source && sourceQuestion?.access !== 'owner'"
      @saved="
        (version) => {
          replaceVersion = true;
          useLibraryVersion(version);
        }
      "
    />
  </AppShell>
</template>
