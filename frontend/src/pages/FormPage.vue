<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRoute } from "vue-router";
import { ElSwitch } from "element-plus";
import {
  api,
  ApiError,
  definitionOf,
  formatDate,
  session,
  type EvaluateResult,
  type Form,
  type Receipt,
  type Survey,
} from "../api";
import Brand from "../components/Brand.vue";
import Icon from "../components/Icon.vue";
import QuestionInput from "../components/QuestionInput.vue";
const props = defineProps<{ preview?: boolean }>();
const route = useRoute(),
  form = ref<Form>(),
  loadingError = ref(""),
  error = ref(""),
  busy = ref(false);
const started = ref(false),
  review = ref(false),
  finished = ref(false),
  history = ref<string[]>([]),
  index = ref(0);
const answers = ref<Record<string, unknown>>({}),
  anonymous = ref(true),
  receipt = ref<Receipt>();
const requestId = ref(crypto.randomUUID().replaceAll("-", "")),
  pendingBody = ref<unknown>();
const current = computed(() =>
  form.value?.questions.find((q) => q.id === history.value[index.value]),
);
const blocked = computed(
  () =>
    !props.preview &&
    form.value &&
    (form.value.effective_status !== "published" ||
      (form.value.already_submitted && !form.value.settings.allow_multiple)),
);
const root = computed(() =>
  props.preview
    ? `/surveys/${route.params.id}/preview`
    : `/forms/${route.params.code}/next`,
);
function reset() {
  started.value = false;
  review.value = false;
  finished.value = false;
  answers.value = {};
  index.value = 0;
  history.value = form.value?.questions[0] ? [form.value.questions[0].id] : [];
  requestId.value = crypto.randomUUID().replaceAll("-", "");
  receipt.value = undefined;
  pendingBody.value = undefined;
  error.value = "";
}
async function load() {
  loadingError.value = "";
  try {
    if (props.preview) {
      const value = await api<Survey>(`/surveys/${route.params.id}`);
      form.value = {
        ...definitionOf(value),
        public_code: value.public_code,
        definition_version: value.definition_version,
        deadline: value.deadline,
        effective_status: value.effective_status,
        already_submitted: false,
      };
    } else form.value = await api<Form>(`/forms/${route.params.code}`);
    anonymous.value = form.value.settings.allow_anonymous;
    reset();
  } catch (e) {
    loadingError.value = (e as Error).message;
  }
}
function updateAnswer(value: unknown) {
  const id = current.value?.id;
  if (!id) return;
  answers.value[id] = value;
  const keep = new Set(history.value.slice(0, index.value + 1));
  for (const key of Object.keys(answers.value))
    if (!keep.has(key)) delete answers.value[key];
  history.value = history.value.slice(0, index.value + 1);
  error.value = "";
}
function answerList(ids = history.value) {
  return ids
    .filter((id) => Object.hasOwn(answers.value, id))
    .map((id) => ({ question_id: id, value: answers.value[id] }));
}
async function next() {
  if (!current.value || busy.value) return;
  busy.value = true;
  error.value = "";
  try {
    const prefix = history.value.slice(0, index.value + 1);
    const value = await api<EvaluateResult>(root.value, {
      current_question_id: current.value.id,
      answers: answerList(prefix),
    });
    history.value = value.visited_question_ids;
    if (value.next_question_id === "END") review.value = true;
    else {
      history.value.push(value.next_question_id);
      index.value = history.value.length - 1;
    }
  } catch (e) {
    error.value = (e as Error).message;
  } finally {
    busy.value = false;
  }
}
function back() {
  error.value = "";
  if (review.value) {
    review.value = false;
    index.value = history.value.length - 1;
  } else if (index.value > 0) index.value--;
  else started.value = false;
}
async function submit() {
  if (!form.value || busy.value) return;
  if (props.preview) {
    finished.value = true;
    return;
  }
  busy.value = true;
  error.value = "";
  if (!pendingBody.value)
    pendingBody.value = {
      request_id: requestId.value,
      definition_version: form.value.definition_version,
      is_anonymous: anonymous.value,
      answers: answerList(),
    };
  try {
    receipt.value = await api<Receipt>(
      `/forms/${route.params.code}/responses`,
      pendingBody.value,
    );
    finished.value = true;
  } catch (e) {
    error.value = (e as Error).message;
    // A network failure can occur after persistence. Keep exactly the same payload for retry.
    if (e instanceof ApiError && e.status && e.status < 500)
      pendingBody.value = undefined;
  } finally {
    busy.value = false;
  }
}
function answerText(qid: string) {
  const question = form.value?.questions.find((q) => q.id === qid),
    value = answers.value[qid];
  if (
    value == null ||
    value === "" ||
    (Array.isArray(value) && value.length === 0)
  )
    return "未填写";
  if (question?.type === "single_choice")
    return question.options.find((o) => o.id === value)?.text || String(value);
  if (Array.isArray(value))
    return value
      .map((id) => question?.options.find((o) => o.id === id)?.text || id)
      .join("、");
  return String(value);
}
onMounted(load);
</script>
<template>
  <div class="public-form-page">
    <header class="public-header">
      <RouterLink to="/dashboard" class="brand-link"><Brand /></RouterLink
      ><RouterLink
        v-if="preview"
        :to="`/surveys/${route.params.id}/edit`"
        class="back-link"
        ><Icon name="back" :size="16" /> 返回编辑器</RouterLink
      ><span v-else class="public-account"
        >{{ session?.username
        }}<span class="avatar small-avatar">{{
          session?.username.slice(0, 1)
        }}</span></span
      >
    </header>
    <div v-if="preview" class="preview-banner">
      <Icon name="eye" :size="17" /> 预览模式 · 体验实际跳转，不会保存答卷
    </div>
    <main class="form-container">
      <div v-if="loadingError" class="form-paper empty-state" role="alert">
        <h2>暂时无法打开问卷</h2>
        <p>{{ loadingError }}</p>
        <button class="button" @click="load">重新加载</button>
      </div>
      <div v-else-if="!form" class="loading-state">正在打开一份好奇…</div>
      <div v-else-if="blocked" class="form-paper empty-state">
        <span class="completion-symbol"><Icon name="file" :size="36" /></span>
        <h2>
          {{
            form.already_submitted && !form.settings.allow_multiple
              ? "你已经完成这份问卷"
              : "这份问卷暂不接收回答"
          }}
        </h2>
        <p>
          {{
            form.already_submitted && !form.settings.allow_multiple
              ? "感谢分享，这份问卷每个账号只能提交一次。"
              : "问卷已关闭或截止，感谢你的关注。"
          }}
        </p>
        <RouterLink to="/dashboard" class="button">返回工作空间</RouterLink>
      </div>
      <div v-else-if="finished" class="form-paper complete-paper">
        <span class="completion-symbol"><Icon name="check" :size="40" /></span
        ><span class="eyebrow">EVERY VOICE MAKES A DIFFERENCE</span>
        <h1>{{ preview ? "预览完成" : "你的声音，已经被听见。" }}</h1>
        <p>
          {{
            preview
              ? "跳转与校验流程已体验完毕，没有保存任何答卷。"
              : "感谢你认真分享，让这份好奇有了真实的回响。"
          }}
        </p>
        <div v-if="receipt" class="receipt">
          <span>提交时间</span
          ><strong>{{ formatDate(receipt.submitted_at) }}</strong
          ><span>答卷编号</span><code>{{ receipt.id.slice(0, 16) }}</code>
        </div>
        <div class="button-row centered">
          <button
            v-if="preview || form.settings.allow_multiple"
            class="button"
            @click="reset"
          >
            {{ preview ? "再次预览" : "再填一份" }}</button
          ><RouterLink
            :to="preview ? `/surveys/${route.params.id}/edit` : '/dashboard'"
            class="button primary"
            >{{ preview ? "返回编辑器" : "返回工作空间"
            }}<Icon name="arrow" :size="17"
          /></RouterLink>
        </div>
      </div>
      <div v-else-if="!started" class="form-paper welcome-paper">
        <div class="form-cover-decoration">
          <Icon name="leaf" :size="42" /><span>AN INVITATION TO SHARE</span>
        </div>
        <span class="eyebrow">每一个回答，都有意义</span>
        <h1>{{ form.title }}</h1>
        <p class="form-description">
          {{ form.description || "欢迎分享你的想法，感谢你的认真填写。" }}
        </p>
        <div class="form-facts">
          <span
            ><Icon name="file" :size="16" /> 最多
            {{ form.questions.length }} 道题</span
          ><span
            ><Icon name="clock" :size="16" />
            {{
              form.deadline
                ? formatDate(form.deadline) + " 截止"
                : "不限填写时间"
            }}</span
          >
        </div>
        <div v-if="form.settings.allow_anonymous" class="anonymous-setting">
          <el-switch v-model="anonymous" />
          <div>
            <strong>匿名填写</strong>
            <p>
              开启后，创建者看不到你的账号；系统仍保留账号关联，用于限制重复提交。
            </p>
          </div>
        </div>
        <div v-else class="notice-bar">
          <Icon name="shield" :size="17" />
          此问卷为实名填写，创建者可查看你的用户名。
        </div>
        <button class="button primary form-start" @click="started = true">
          开始填写<Icon name="arrow" :size="18" />
        </button>
      </div>
      <div v-else-if="review" class="form-paper review-paper">
        <span class="eyebrow">ONE LAST LOOK</span>
        <h1>谢谢，现在确认一下。</h1>
        <p class="muted">以下是你在这条填写路径上的回答。</p>
        <div class="review-answers">
          <div v-for="(qid, i) in history" :key="qid">
            <span>{{ String(i + 1).padStart(2, "0") }}</span>
            <section>
              <h3>{{ form.questions.find((q) => q.id === qid)?.title }}</h3>
              <p>{{ answerText(qid) }}</p>
            </section>
          </div>
        </div>
        <p v-if="error" role="alert" class="error-message">{{ error }}</p>
        <div class="form-navigation">
          <button
            class="text-button"
            :disabled="busy || !!pendingBody"
            @click="back"
          >
            <Icon name="back" :size="17" /> 返回修改</button
          ><button class="button primary" :disabled="busy" @click="submit">
            {{
              busy
                ? "正在提交…"
                : preview
                  ? "完成预览"
                  : pendingBody
                    ? "重试提交"
                    : "确认提交"
            }}<Icon name="check" :size="18" />
          </button>
        </div>
      </div>
      <div v-else-if="current" class="form-paper active-question-paper">
        <div class="form-progress">
          <span>{{ form.title }}</span
          ><strong
            >问题 {{ String(index + 1).padStart(2, "0") }}
            <span>/ 最多 {{ form.questions.length }} 题</span></strong
          >
        </div>
        <div class="question-kicker">
          <span>{{ String(index + 1).padStart(2, "0") }}</span
          ><small
            >{{ current.required ? "必答" : "可选" }} ·
            {{
              current.type === "multiple_choice"
                ? "可选择多项"
                : current.type === "single_choice"
                  ? "请选择一项"
                  : "填写你的回答"
            }}</small
          >
        </div>
        <h1>{{ current.title }}</h1>
        <p v-if="current.description" class="form-description">
          {{ current.description }}
        </p>
        <p
          v-if="
            current.type === 'multiple_choice' &&
            (current.validation.min_choices != null ||
              current.validation.max_choices != null)
          "
          class="answer-hint"
        >
          {{
            current.validation.min_choices != null
              ? `至少选择 ${current.validation.min_choices} 项`
              : ""
          }}
          {{
            current.validation.max_choices != null
              ? `最多选择 ${current.validation.max_choices} 项`
              : ""
          }}
        </p>
        <QuestionInput
          :question="current"
          :model-value="answers[current.id]"
          :disabled="busy"
          @update:model-value="updateAnswer"
        />
        <p v-if="error" role="alert" class="error-message">{{ error }}</p>
        <div class="form-navigation">
          <button class="text-button" :disabled="busy" @click="back">
            <Icon name="back" :size="17" /> 上一步</button
          ><button class="button primary" :disabled="busy" @click="next">
            {{ busy ? "正在校验…" : "下一步" }}<Icon name="arrow" :size="18" />
          </button>
        </div>
      </div>
      <footer class="form-footer">
        <Brand /><span>好问题，有回响。</span>
      </footer>
    </main>
  </div>
</template>
