import { createApp } from "vue";
import { createRouter, createWebHistory } from "vue-router";
import "element-plus/dist/index.css";
import "./style.css";
import App from "./App.vue";
import { restoreSession } from "./api";

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/", redirect: "/dashboard" },
    { path: "/login", component: () => import("./pages/AuthPage.vue") },
    { path: "/library", component: () => import("./pages/LibraryPage.vue") },
    {
      path: "/library/questions/:id",
      component: () => import("./pages/LibraryDetailPage.vue"),
    },
    {
      path: "/dashboard",
      component: () => import("./pages/DashboardPage.vue"),
    },
    {
      path: "/surveys/:id/edit",
      component: () => import("./pages/EditorPage.vue"),
    },
    {
      path: "/surveys/:id/statistics",
      component: () => import("./pages/StatisticsPage.vue"),
    },
    {
      path: "/surveys/:id/preview",
      component: () => import("./pages/FormPage.vue"),
      props: { preview: true },
    },
    { path: "/survey/:code", component: () => import("./pages/FormPage.vue") },
    { path: "/:pathMatch(.*)*", redirect: "/dashboard" },
  ],
});
router.beforeEach(async (to) => {
  if (to.path === "/login") return true;
  try {
    if (await restoreSession()) return true;
  } catch {
    return {
      path: "/login",
      query: { redirect: to.fullPath, unavailable: "1" },
    };
  }
  return { path: "/login", query: { redirect: to.fullPath } };
});
window.addEventListener("fieldnote:unauthorized", () => {
  if (router.currentRoute.value.path !== "/login")
    router.push({
      path: "/login",
      query: { redirect: router.currentRoute.value.fullPath },
    });
});
createApp(App).use(router).mount("#app");
