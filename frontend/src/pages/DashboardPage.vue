<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { ElMessage, ElPagination } from "element-plus";
import {
  api,
  formatDate,
  session,
  statusLabels,
  type Definition,
  type SurveyList,
} from "../api";
import AppShell from "../components/AppShell.vue";
import Icon from "../components/Icon.vue";
const router = useRouter();
const data = ref<SurveyList>({ items: [], total: 0, page: 1, page_size: 12 });
const summary = ref({
  total_surveys: 0,
  total_responses: 0,
  published: 0,
  draft: 0,
});
const status = ref(""),
  search = ref(""),
  page = ref(1),
  busy = ref(false),
  creating = ref(false),
  error = ref("");
const activeLabel = computed(() =>
  status.value ? statusLabels[status.value] : "全部问卷",
);
async function load() {
  busy.value = true;
  error.value = "";
  try {
    const params = new URLSearchParams({ page: String(page.value) });
    if (status.value) params.set("status", status.value);
    if (search.value.trim()) params.set("q", search.value.trim());
    const [list, totals] = await Promise.all([
      api<SurveyList>(`/surveys?${params}`),
      api<typeof summary.value>("/overview"),
    ]);
    data.value = list;
    summary.value = totals;
  } catch (e) {
    error.value = (e as Error).message;
  } finally {
    busy.value = false;
  }
}
async function create(example = false) {
  creating.value = true;
  try {
    const definition = example
      ? await api<Definition>("/templates/soccer")
      : {
          title: "未命名问卷",
          description: "",
          questions: [],
          settings: { allow_anonymous: true, allow_multiple: false },
        };
    const survey = await api<{ id: string }>("/surveys", definition);
    router.push(`/surveys/${survey.id}/edit`);
  } catch (e) {
    ElMessage.error((e as Error).message);
  } finally {
    creating.value = false;
  }
}
async function share(code: string) {
  try {
    await navigator.clipboard.writeText(`${location.origin}/survey/${code}`);
    ElMessage.success("问卷链接已复制");
  } catch {
    ElMessage.error("复制失败，请从编辑页打开问卷后复制网址");
  }
}
function filter(value: string) {
  status.value = value;
  page.value = 1;
  load();
}
onMounted(load);
</script>
<template>
  <AppShell>
    <section class="dashboard-heading">
      <div>
        <span class="eyebrow">A LITTLE CURIOSITY GOES A LONG WAY</span>
        <h1>
          你好，{{ session?.username }}<span class="greeting-mark">✳</span>
        </h1>
        <p class="muted">从一个好问题开始，发现更多真实的想法。</p>
      </div>
      <button class="button primary" :disabled="creating" @click="create()">
        <Icon name="plus" :size="18" /> 创建问卷
      </button>
    </section>
    <section class="dashboard-hero">
      <div>
        <span class="eyebrow">MAKE SPACE FOR EVERY VOICE</span>
        <h2>好奇心，是了解的开始。</h2>
        <p>设计你的问题，让每一份回答都有意义。</p>
        <button class="text-button" :disabled="creating" @click="create(true)">
          从示例问卷开始 <Icon name="arrow" :size="17" />
        </button>
      </div>
      <div class="hero-art" aria-hidden="true">
        <div class="hero-sheet">
          <div class="mini-logo">✳</div>
          <i /><i /><span><b />一个问题</span><span><b />一种可能</span>
        </div>
        <div class="hero-leaf"><Icon name="leaf" :size="50" /></div>
        <div class="hero-spark">✳</div>
        <span class="hero-caption">ASK. LISTEN. DISCOVER.</span>
      </div>
    </section>
    <section class="metric-grid">
      <div class="metric">
        <span class="metric-icon"><Icon name="file" /></span>
        <div>
          <span>问卷总数</span
          ><strong>{{ summary.total_surveys }}<small>份问卷</small></strong>
        </div>
      </div>
      <div class="metric">
        <span class="metric-icon olive"><Icon name="people" /></span>
        <div>
          <span>收集的回答</span
          ><strong>{{ summary.total_responses }}<small>份答卷</small></strong>
        </div>
      </div>
      <div class="metric">
        <span class="metric-icon mint"><Icon name="chart" /></span>
        <div>
          <span>正在收集中</span
          ><strong>{{ summary.published }}<small>份问卷</small></strong>
        </div>
      </div>
      <div class="metric">
        <span class="metric-icon sand"><Icon name="file" /></span>
        <div>
          <span>待完成草稿</span
          ><strong>{{ summary.draft }}<small>份问卷</small></strong>
        </div>
      </div>
    </section>
    <section class="survey-section">
      <div class="section-heading">
        <h2>
          我的问卷 <span>{{ data.total }}</span>
        </h2>
        <form
          class="search-box"
          @submit.prevent="
            page = 1;
            load();
          "
        >
          <Icon name="search" :size="17" /><input
            v-model="search"
            placeholder="搜索问卷名称"
            aria-label="搜索问卷名称"
          /><button type="submit" class="search-submit">搜索</button>
        </form>
      </div>
      <div class="tabs">
        <button
          v-for="(label, key) in {
            '': '全部问卷',
            published: '收集中',
            draft: '草稿',
            expired: '已截止',
            closed: '已关闭',
          }"
          :key="key"
          :class="{ active: status === key }"
          @click="filter(String(key))"
        >
          {{ label }}</button
        ><span class="tabs-hint">按创建时间排序</span>
      </div>
      <div v-if="error" class="empty-state" role="alert">
        <p>{{ error }}</p>
        <button class="button" @click="load">重试</button>
      </div>
      <div v-else-if="busy" class="loading-state">正在整理你的问卷…</div>
      <div v-else-if="!data.items.length" class="empty-state">
        <span class="empty-symbol"><Icon name="leaf" :size="34" /></span>
        <h3>
          {{ search ? "没有找到匹配的问卷" : `${activeLabel}里还没有内容` }}
        </h3>
        <p>把一个小小的好奇，变成你的第一份问卷。</p>
        <button class="button primary" @click="create()">创建第一份问卷</button>
      </div>
      <div v-else class="survey-grid">
        <article
          v-for="survey in data.items"
          :key="survey.id"
          class="survey-card"
        >
          <div class="card-top">
            <span class="survey-file-icon"><Icon name="file" :size="24" /></span
            ><span class="status-badge" :class="survey.effective_status"
              ><i />{{ statusLabels[survey.effective_status] }}</span
            >
          </div>
          <RouterLink :to="`/surveys/${survey.id}/edit`" class="survey-title">{{
            survey.title
          }}</RouterLink>
          <p class="survey-description">
            {{ survey.description || "好问题，正在酝酿中。" }}
          </p>
          <div class="survey-meta">
            <span
              ><Icon name="file" :size="14" />
              {{ survey.questions?.length || 0 }} 道题目</span
            ><span
              ><Icon name="people" :size="14" />
              {{ survey.response_count }} 份答卷</span
            >
          </div>
          <div class="card-divider" />
          <div class="card-actions">
            <span>{{ formatDate(survey.created_at) }}</span>
            <div>
              <button
                v-if="survey.status !== 'draft'"
                class="icon-button"
                title="复制分享链接"
                @click="share(survey.public_code)"
              >
                <Icon name="link" :size="17" /></button
              ><RouterLink
                :to="`/surveys/${survey.id}/statistics`"
                class="icon-button"
                title="查看统计"
                ><Icon name="chart" :size="17" /></RouterLink
              ><RouterLink :to="`/surveys/${survey.id}/edit`" class="card-open"
                >{{ survey.status === "draft" ? "继续编辑" : "管理问卷"
                }}<Icon name="arrow" :size="15"
              /></RouterLink>
            </div>
          </div>
        </article>
      </div>
      <el-pagination
        v-if="data.total > 12"
        background
        layout="prev, pager, next"
        :total="data.total"
        :page-size="12"
        :current-page="page"
        @current-change="
          (value: number) => {
            page = value;
            load();
          }
        "
      />
    </section>
  </AppShell>
</template>
