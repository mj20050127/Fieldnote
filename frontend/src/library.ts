import type { components } from "./api.generated";
import type { Question } from "./api";
export type Content = components["schemas"]["QuestionContent-Output"];
export type Bank = components["schemas"]["BankOut"];
export type LibraryQuestion = components["schemas"]["LibraryQuestionOut"];
export type LibraryList = components["schemas"]["LibraryQuestionList"];
export type Version = components["schemas"]["VersionOut"];
export type Versions = components["schemas"]["VersionList"];
export type Shares = components["schemas"]["SharesOut"];
export type Usages = components["schemas"]["UsageList"];
export type CrossStatistics = components["schemas"]["LibraryStatistics"];
export function contentOf(q: Content): Content {
  return structuredClone(
    JSON.parse(
      JSON.stringify({
        type: q.type,
        title: q.title,
        description: q.description,
        required: q.required,
        options: q.options,
        validation: q.validation,
      }),
    ),
  );
}
export function blankContent(): Content {
  return {
    type: "text",
    title: "",
    description: "",
    required: true,
    options: [],
    validation: {
      min_choices: null,
      max_choices: null,
      min_length: null,
      max_length: null,
      min_value: null,
      max_value: null,
      integer_only: false,
    },
  };
}
export function instanceOf(version: Version): Question {
  return {
    ...contentOf(version.content),
    id: "q_" + crypto.randomUUID().replaceAll("-", ""),
    source: { question_id: version.question_id, version_id: version.id },
    routing: { rules: [], default_target: "NEXT" },
  };
}
export function applyVersion(question: Question, version: Version) {
  // Preserve local identity and routes, including invalid conditions, for explicit repair.
  Object.assign(question, contentOf(version.content), {
    source: { question_id: version.question_id, version_id: version.id },
  });
}
