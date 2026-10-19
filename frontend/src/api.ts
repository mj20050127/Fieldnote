import { ref } from "vue";
import type { components } from "./api.generated";

export type Definition = components["schemas"]["Definition-Output"];
export type Survey = components["schemas"]["SurveyOut"];
export type Question = components["schemas"]["Question-Output"];
export type Rule = components["schemas"]["Rule"];
export type SurveyList = components["schemas"]["SurveyList"];
export type Statistics = components["schemas"]["Statistics"];
export type QuestionStatistics = components["schemas"]["QuestionStatistics"];
export type ResponseList = components["schemas"]["ResponseList"];
export type ResponseItem = components["schemas"]["ResponseOut"];
export type DefinitionCheck = components["schemas"]["DefinitionCheck"];
export type Form = components["schemas"]["FormOut"];
export type EvaluateResult = components["schemas"]["EvaluateOut"];
export type Receipt = components["schemas"]["Receipt"];
type Session = components["schemas"]["UserMe"];
export const session = ref<Session | null>(null);

export class ApiError extends Error {
  constructor(
    public code: string,
    message: string,
    public questionId?: string,
    public status?: number,
  ) {
    super(message);
  }
}

export async function api<T>(
  path: string,
  body?: unknown,
  method?: string,
): Promise<T> {
  const response = await fetch(`/api${path}`, {
    method: method || (body === undefined ? "GET" : "POST"),
    credentials: "same-origin",
    headers: {
      ...(body === undefined ? {} : { "Content-Type": "application/json" }),
      ...(session.value ? { "X-CSRF-Token": session.value.csrf_token } : {}),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) {
    const value = await response.json().catch(() => ({}));
    if (response.status === 401 && !path.startsWith("/auth/")) {
      session.value = null;
      window.dispatchEvent(new Event("fieldnote:unauthorized"));
    }
    throw new ApiError(
      value.error?.code || "NETWORK_ERROR",
      value.error?.message || "网络请求失败，请稍后重试",
      value.error?.question_id,
      response.status,
    );
  }
  if (response.status === 204) return undefined as T;
  return response.json();
}

export async function restoreSession() {
  if (session.value) return true;
  try {
    session.value = await api<Session>("/auth/me");
    return true;
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) return false;
    throw error;
  }
}

export function formatDate(value?: string | null) {
  return value
    ? new Intl.DateTimeFormat("zh-CN", {
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
        timeZone: "Asia/Shanghai",
      }).format(new Date(value))
    : "不限时间";
}
export const typeLabels: Record<string, string> = {
  single_choice: "单选题",
  multiple_choice: "多选题",
  text: "文本填空",
  number: "数字填空",
};
export const statusLabels: Record<string, string> = {
  draft: "草稿",
  published: "收集中",
  closed: "已关闭",
  expired: "已截止",
};
export function definitionOf(value: Definition): Definition {
  return {
    title: value.title,
    description: value.description,
    settings: JSON.parse(JSON.stringify(value.settings)),
    questions: JSON.parse(JSON.stringify(value.questions)),
  };
}
