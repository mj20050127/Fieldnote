<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRoute } from "vue-router";
import { ElMessage, ElPagination, ElDrawer } from "element-plus";
import {
  api,
  formatDate,
  typeLabels,
  type QuestionStatistics,
  type ResponseItem,
  type ResponseList,
  type Statistics,
  type Survey,
} from "../api";
import AppShell from "../components/AppShell.vue";
import Icon from "../components/Icon.vue";
const id = String(useRoute().params.id);
const survey = ref<Survey>(),
  stats = ref<Statistics>(),
  details = ref<QuestionStatistics>(),
  responses = ref<ResponseList>();
const tab = ref("questions"),
  selected = ref(""),
  valuePage = ref(1),
  responsePage = ref(1),
  busy = ref(false),
  error = ref(""),
  detailError = ref("");
const inspected = ref<ResponseItem>(),
  drawer = ref(false);
const current = computed(() =>
  stats.value?.questions.find((q) => q.question_id === selected.value),
);
async function load() {
  busy.value = true;
  error.value = "";
  try {
    const [definition, summary] = await Promise.all([
      api<Survey>(`/surveys/${id}`),
      api<Statistics>(`/surveys/${id}/statistics`),
    ]);
    survey.value = definition;
    stats.value = summary;
    if (!selected.value)
      selected.value = summary.questions[0]?.question_id || "";
    await Promise.all([loadDetails(), loadResponses()]);
  } catch (e) {
    error.value = (e as Error).message;
  } finally {
    busy.value = false;
  }
}
async function loadDetails() {
  if (!selected.value) return;
  detailError.value = "";
  details.value = undefined;
  try {
    const value = await api<QuestionStatistics>(
      `/surveys/${id}/questions/${selected.value}/statistics?page=${valuePage.value}`,
    );
    if (value.question_id === selected.value) details.value = value;
  } catch (e) {
    detailError.value = (e as Error).message;
  }
}
async function loadResponses() {
  responses.value = await api<ResponseList>(
    `/surveys/${id}/responses?page=${responsePage.value}`,
  );
}
function select(qid: string) {
  selected.value = qid;
  valuePage.value = 1;
  loadDetails();
}
async function changeResponsePage(value: number) {
  responsePage.value = value;
  try {
    await loadResponses();
  } catch (e) {
    ElMessage.error((e as Error).message);
  }
}
function formatValue(qid: string, value: unknown) {
  const q = survey.value?.questions.find((q) => q.id === qid);
  if (q?.type === "single_choice")
    return q.options.find((o) => o.id === value)?.text || String(value);
  if (Array.isArray(value))
    return value
      .map((id) => q?.options.find((o) => o.id === id)?.text || id)
      .join("、");
  return value == null ? "未填写" : String(value);
}
async function inspect(responseId: string) {
  try {
    inspected.value = await api<ResponseItem>(
      `/surveys/${id}/responses/${responseId}`,
    );
    drawer.value = true;
  } catch (e) {
    ElMessage.error((e as Error).message);
  }
}
async function share() {
  try {
    await navigator.clipboard.writeText(
      `${location.origin}/survey/${survey.value?.public_code}`,
    );
    ElMessage.success("分享链接已复制");
  } catch {
    ElMessage.error("复制失败，请从管理页打开填写页面");
  }
}
onMounted(load);
</script>
<template>
  <AppShell title="结果统计"
    ><div v-if="error" class="empty-state" role="alert">
      <p>{{ error }}</p>
      <button class="button" @click="load">重试</button>
    </div>
    <div v-else-if="!survey || !stats" class="loading-state">
      正在整理每一份回答…
    </div>
    <template v-else
      ><div class="editor-heading">
        <div>
          <RouterLink :to="`/surveys/${id}/edit`" class="back-link"
            ><Icon name="back" :size="16" /> 管理问卷</RouterLink
          ><span class="eyebrow">LISTEN TO WHAT THE ANSWERS SAY</span>
          <h1>{{ survey.title }}</h1>
          <p class="muted">把回答连成洞察，让下一步更有依据。</p>
        </div>
        <div class="button-row">
          <button class="button" :disabled="busy" @click="load">
            <Icon name="chart" :size="17" /> 刷新统计</button
          ><button
            v-if="survey.status !== 'draft'"
            class="button primary"
            @click="share"
          >
            <Icon name="link" :size="17" /> 分享问卷
          </button>
        </div>
      </div>
      <div class="statistics-overview">
        <div>
          <span>收到的答卷</span
          ><strong>{{ stats.total_responses }}<small>份</small></strong>
        </div>
        <div>
          <span>问卷题目</span
          ><strong>{{ survey.questions.length }}<small>道</small></strong>
        </div>
        <p>
          <Icon name="shield" :size="21" /><span
            >统计按已提交答卷计算。<br />匿名答卷始终隐藏账号身份。</span
          >
        </p>
      </div>
      <div class="tabs statistics-tabs">
        <button
          :class="{ active: tab === 'questions' }"
          @click="tab = 'questions'"
        >
          题目分析</button
        ><button
          :class="{ active: tab === 'responses' }"
          @click="tab = 'responses'"
        >
          原始答卷 <span>{{ stats.total_responses }}</span>
        </button>
      </div>
      <div v-if="!survey.questions.length" class="empty-state">
        <h3>先添加一些好问题</h3>
        <RouterLink :to="`/surveys/${id}/edit`" class="button primary"
          >返回编辑器</RouterLink
        >
      </div>
      <div v-else-if="tab === 'questions'" class="statistics-workspace">
        <aside class="statistics-question-list">
          <button
            v-for="(q, index) in stats.questions"
            :key="q.question_id"
            :class="{ active: selected === q.question_id }"
            @click="select(q.question_id)"
          >
            <span>{{ String(index + 1).padStart(2, "0") }}</span>
            <div>
              <strong>{{ q.title }}</strong
              ><small
                >{{ typeLabels[q.type] }} ·
                {{ q.answered_count }} 份有效回答</small
              >
            </div>
          </button>
        </aside>
        <section v-if="current" class="question-analysis">
          <div class="analysis-heading">
            <span class="type-pill">{{ typeLabels[current.type] }}</span>
            <h2>{{ current.title }}</h2>
            <div class="analysis-counts">
              <span
                >有效回答 <b>{{ current.answered_count }}</b></span
              ><span
                >跳过 <b>{{ current.skipped_count }}</b></span
              ><span
                >到达但未填写 <b>{{ current.unanswered_count }}</b></span
              >
            </div>
          </div>
          <div v-if="current.options.length" class="bar-chart">
            <div
              v-for="option in current.options"
              :key="option.id"
              class="bar-chart-row"
            >
              <div>
                <span>{{ option.text }}</span
                ><strong
                  >{{ option.count }}
                  <small>份 · {{ option.percentage }}%</small></strong
                >
              </div>
              <div class="bar-track">
                <span :style="{ width: `${option.percentage}%` }" />
              </div>
            </div>
            <p class="chart-note">
              占比以本题有效回答数为分母。{{
                current.type === "multiple_choice"
                  ? "多选题各选项占比之和可以超过 100%。"
                  : ""
              }}
            </p>
          </div>
          <div v-else>
            <div v-if="current.type === 'number'" class="number-summary">
              <span>有效数值平均值</span
              ><strong>{{
                current.average == null
                  ? "—"
                  : Number(current.average.toFixed(4))
              }}</strong
              ><small>{{
                current.average == null
                  ? "暂无有效数字回答"
                  : `由 ${current.answered_count} 份有效回答计算`
              }}</small>
            </div>
            <div class="answer-values">
              <h3>
                {{ current.type === "number" ? "原始数值" : "填写内容"
                }}<span>{{ current.answered_count }}</span>
              </h3>
              <p v-if="detailError" class="error-message">{{ detailError }}</p>
              <div v-else-if="!details" class="loading-state">
                正在读取回答…
              </div>
              <p v-else-if="!details.values.length" class="muted">
                这里还没有回答。分享问卷，邀请第一位参与者吧。
              </p>
              <article
                v-for="(row, index) in details?.values || []"
                :key="index"
              >
                <p>{{ String(row.value) }}</p>
                <span>{{ formatDate(row.submitted_at) }}</span>
              </article>
              <el-pagination
                v-if="details && details.total > 20"
                background
                layout="prev, pager, next"
                :total="details.total"
                :page-size="20"
                :current-page="valuePage"
                @current-change="
                  (value: number) => {
                    valuePage = value;
                    loadDetails();
                  }
                "
              />
            </div>
          </div>
        </section>
      </div>
      <section v-else class="response-table-wrap">
        <div v-if="!responses?.items.length" class="empty-state">
          <span class="empty-symbol"><Icon name="people" :size="32" /></span>
          <h3>等待第一份回响</h3>
          <p>分享问卷链接，让大家的声音在这里汇集。</p>
        </div>
        <table v-else class="response-table">
          <thead>
            <tr>
              <th>答卷编号</th>
              <th>填写者</th>
              <th>回答题数</th>
              <th>提交时间</th>
              <th />
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in responses.items" :key="row.id">
              <td>
                <code>{{ row.id.slice(0, 12) }}</code>
              </td>
              <td>
                <span v-if="row.is_anonymous" class="anonymous-badge"
                  ><Icon name="shield" :size="13" /> 匿名填写</span
                ><span v-else>{{ row.respondent }}</span>
              </td>
              <td>{{ row.answers.length }}</td>
              <td>{{ formatDate(row.submitted_at) }}</td>
              <td>
                <button class="text-button" @click="inspect(row.id)">
                  查看答卷 <Icon name="arrow" :size="15" />
                </button>
              </td>
            </tr>
          </tbody>
        </table>
        <el-pagination
          v-if="responses && responses.total > 20"
          background
          layout="prev, pager, next"
          :total="responses.total"
          :page-size="20"
          :current-page="responsePage"
          @current-change="changeResponsePage"
        />
      </section> </template
    ><el-drawer v-model="drawer" title="答卷详情" size="min(560px, 94vw)"
      ><template v-if="inspected"
        ><div class="response-detail-meta">
          <span>{{
            inspected.is_anonymous ? "匿名填写" : inspected.respondent
          }}</span
          ><span>{{ formatDate(inspected.submitted_at) }}</span>
        </div>
        <div
          v-for="qid in inspected.visited_question_ids"
          :key="qid"
          class="response-detail-answer"
        >
          <h3>{{ survey?.questions.find((q) => q.id === qid)?.title }}</h3>
          <p>
            {{
              formatValue(
                qid,
                inspected.answers.find((a) => a.question_id === qid)?.value,
              )
            }}
          </p>
        </div>
        <p class="muted small">仅展示实际经过的题目。</p></template
      ></el-drawer
    ></AppShell
  >
</template>
