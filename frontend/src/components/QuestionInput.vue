<script setup lang="ts">
import { computed } from "vue";
import type { Question } from "../api";
const props = defineProps<{
  question: Question;
  modelValue: unknown;
  disabled?: boolean;
}>();
const emit = defineEmits<{ "update:modelValue": [value: unknown] }>();
const textLength = computed(
  () => Array.from(String(props.modelValue ?? "").trim()).length,
);
function toggle(id: string) {
  const values = Array.isArray(props.modelValue) ? [...props.modelValue] : [];
  emit(
    "update:modelValue",
    values.includes(id) ? values.filter((v) => v !== id) : [...values, id],
  );
}
function numberInput(event: Event) {
  const value = (event.target as HTMLInputElement).value;
  emit("update:modelValue", value === "" ? null : Number(value));
}
</script>
<template>
  <div class="question-input">
    <div
      v-if="
        question.type === 'single_choice' || question.type === 'multiple_choice'
      "
      class="answer-options"
    >
      <label
        v-for="(option, index) in question.options"
        :key="option.id"
        class="answer-option"
        :class="{
          selected:
            question.type === 'single_choice'
              ? modelValue === option.id
              : Array.isArray(modelValue) && modelValue.includes(option.id),
        }"
      >
        <input
          v-if="question.type === 'single_choice'"
          type="radio"
          :name="question.id"
          :value="option.id"
          :checked="modelValue === option.id"
          :disabled="disabled"
          @change="emit('update:modelValue', option.id)"
        />
        <input
          v-else
          type="checkbox"
          :checked="Array.isArray(modelValue) && modelValue.includes(option.id)"
          :disabled="disabled"
          @change="toggle(option.id)"
        />
        <span class="option-letter">{{ String.fromCharCode(65 + index) }}</span
        ><span>{{ option.text }}</span>
      </label>
    </div>
    <textarea
      v-else-if="question.type === 'text'"
      class="text-answer"
      rows="5"
      :value="(modelValue as string) || ''"
      :disabled="disabled"
      placeholder="写下你的想法…"
      :aria-label="question.title"
      @input="
        emit('update:modelValue', ($event.target as HTMLTextAreaElement).value)
      "
    />
    <input
      v-else
      class="number-answer"
      type="number"
      :step="question.validation?.integer_only ? 1 : 'any'"
      :min="question.validation?.min_value ?? undefined"
      :max="question.validation?.max_value ?? undefined"
      :value="(modelValue as number) ?? ''"
      :disabled="disabled"
      placeholder="请输入数字"
      :aria-label="question.title"
      @input="numberInput"
    />
    <p
      v-if="question.type === 'text'"
      class="answer-count"
      :class="{
        danger: textLength > (question.validation.max_length ?? 10000),
      }"
    >
      {{ textLength }} / {{ question.validation.max_length ?? 10000 }} 字
    </p>
  </div>
</template>
