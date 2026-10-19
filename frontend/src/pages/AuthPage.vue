<script setup lang="ts">
import { ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { api, session } from "../api";
import Brand from "../components/Brand.vue";
import Icon from "../components/Icon.vue";
const route = useRoute(),
  router = useRouter();
const registering = ref(false),
  username = ref(""),
  password = ref(""),
  busy = ref(false),
  error = ref("");
async function submit() {
  busy.value = true;
  error.value = "";
  try {
    session.value = await api(
      `/auth/${registering.value ? "register" : "login"}`,
      { username: username.value, password: password.value },
    );
    const target =
      typeof route.query.redirect === "string"
        ? route.query.redirect
        : "/dashboard";
    await router.push(
      target.startsWith("/") && !target.startsWith("//") && target !== "/login"
        ? target
        : "/dashboard",
    );
  } catch (e) {
    error.value = (e as Error).message;
  } finally {
    busy.value = false;
  }
}
</script>
<template>
  <div class="auth-page">
    <section class="auth-story">
      <Brand />
      <div class="story-main">
        <span class="eyebrow light">GOOD QUESTIONS. REAL CONNECTIONS.</span>
        <h1>每一个好问题，<br />都有真实的回响。</h1>
        <p>从好奇出发，把零散的想法，<br />汇成值得倾听的声音。</p>
        <div class="story-art" aria-hidden="true">
          <div class="art-orbit" />
          <div class="art-card art-card-one">
            <span>一份好奇</span><i /><i /><b>01</b>
          </div>
          <div class="art-card art-card-two">
            <Icon name="leaf" :size="42" /><span>无限可能</span>
          </div>
          <div class="art-star">✳</div>
        </div>
      </div>
      <span class="story-footer"
        >拾问 FIELDNOTE <span>让想法生根，让声音被听见。</span></span
      >
    </section>
    <section class="auth-form-panel">
      <div class="auth-form-wrap">
        <span class="eyebrow">YOUR NEXT QUESTION STARTS HERE</span>
        <h2>
          {{ registering ? "开启你的好奇心" : "欢迎回来"
          }}<span class="green-dot">.</span>
        </h2>
        <p class="muted">
          {{
            registering
              ? "创建账号，开始收集有意义的回答。"
              : "登录拾问，继续你的下一次探索。"
          }}
        </p>
        <div class="auth-switch">
          <button
            :class="{ active: !registering }"
            @click="
              registering = false;
              error = '';
            "
          >
            登录账号</button
          ><button
            :class="{ active: registering }"
            @click="
              registering = true;
              error = '';
            "
          >
            注册账号
          </button>
        </div>
        <form @submit.prevent="submit">
          <label class="field-label" for="username">用户名</label
          ><input
            id="username"
            v-model="username"
            class="form-input"
            autocomplete="username"
            required
            minlength="3"
            maxlength="32"
            placeholder="你的用户名"
          />
          <label class="field-label" for="password">密码</label
          ><input
            id="password"
            v-model="password"
            class="form-input"
            :autocomplete="registering ? 'new-password' : 'current-password'"
            type="password"
            required
            minlength="8"
            maxlength="128"
            placeholder="至少 8 位字符"
          />
          <p
            v-if="error || route.query.unavailable"
            role="alert"
            class="error-message"
          >
            {{
              error ||
              "暂时无法连接服务器，请确认后端与 MongoDB 正在运行后重试。"
            }}
          </p>
          <button
            class="button primary auth-submit"
            :disabled="busy"
            type="submit"
          >
            {{ busy ? "正在连接…" : registering ? "创建账号" : "登录工作空间"
            }}<Icon name="arrow" :size="18" />
          </button>
        </form>
        <p class="auth-bottom">
          <Icon name="shield" :size="16" /> 账号密码经过加密哈希存储
        </p>
      </div>
      <div class="auth-copyright">
        © {{ new Date().getFullYear() }} 拾问 Fieldnote · 好问题，有回响。
      </div>
    </section>
  </div>
</template>
