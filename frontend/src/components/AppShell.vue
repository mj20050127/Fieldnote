<script setup lang="ts">
import { useRouter, useRoute } from "vue-router";
import { ElMessage } from "element-plus";
import { api, session } from "../api";
import Brand from "./Brand.vue";
import Icon from "./Icon.vue";
const router = useRouter(),
  route = useRoute();
defineProps<{ title?: string }>();
async function logout() {
  try {
    await api("/auth/logout", {});
    session.value = null;
    router.push("/login");
  } catch (error) {
    ElMessage.error((error as Error).message);
  }
}
</script>
<template>
  <div class="app-layout">
    <aside class="sidebar">
      <RouterLink to="/dashboard" class="brand-link"><Brand /></RouterLink>
      <div class="workspace-label">个人工作空间</div>
      <nav>
        <RouterLink
          to="/dashboard"
          :class="{ active: route.path === '/dashboard' }"
          ><Icon name="grid" /> 我的问卷 <span class="nav-dot"
        /></RouterLink>
      </nav>
      <div class="sidebar-note">
        <Icon name="leaf" :size="25" />
        <p>从一个好问题开始，<br />收集真实的想法。</p>
        <span>MAKE ROOM FOR VOICES</span>
      </div>
      <div class="sidebar-bottom">
        <span class="avatar">{{
          session?.username.slice(0, 1).toUpperCase()
        }}</span>
        <div>
          <strong>{{ session?.username }}</strong
          ><small>个人账号</small>
        </div>
        <button class="icon-button" title="退出登录" @click="logout">
          <Icon name="logout" :size="18" />
        </button>
      </div>
    </aside>
    <div class="main-column">
      <header class="topbar">
        <div class="breadcrumb">
          <span>工作空间</span><Icon name="chevron" :size="13" /><strong>{{
            title || "我的问卷"
          }}</strong>
        </div>
        <span class="topbar-note"
          ><span class="live-dot" /> 让每一种声音被看见</span
        >
      </header>
      <main class="main-content"><slot /></main>
      <footer class="app-footer">
        <span>拾问 Fieldnote</span><span>好问题，有回响。</span>
      </footer>
    </div>
  </div>
</template>
