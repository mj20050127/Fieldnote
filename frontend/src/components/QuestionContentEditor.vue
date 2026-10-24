<script setup lang="ts">
import { typeLabels } from "../api";
import { blankContent, type Content } from "../library";
const content = defineModel<Content>({ required: true });
defineProps<{ readonly?: boolean }>();
function changeType() {
  content.value.validation = blankContent().validation;
  content.value.options = content.value.type.includes("choice")
    ? [
        { id: "o_" + crypto.randomUUID(), text: "选项一" },
        { id: "o_" + crypto.randomUUID(), text: "选项二" },
      ]
    : [];
}
function number(event: Event) {
  const value = (event.target as HTMLInputElement).value;
  return value === "" ? null : Number(value);
}
function addOption() {
  content.value.options.push({ id: "o_" + crypto.randomUUID(), text: "" });
}
</script>
<template>
  <fieldset class="content-fields" :disabled="readonly">
    <label
      >题型<select
        v-model="content.type"
        class="form-input"
        aria-label="题型"
        @change="changeType"
      >
        <option v-for="(label, kind) in typeLabels" :key="kind" :value="kind">
          {{ label }}
        </option>
      </select></label
    >
    <label
      >题目标题<textarea
        v-model="content.title"
        class="form-input"
        rows="2"
        maxlength="500"
      />
    </label>
    <label
      >题目说明<textarea
        v-model="content.description"
        class="form-input"
        rows="2"
        maxlength="1000"
      />
    </label>
    <label class="inline-label"
      ><input type="checkbox" v-model="content.required" /> 必答题</label
    >
    <template v-if="content.type.includes('choice')">
      <div
        v-for="(option, index) in content.options"
        :key="option.id"
        class="button-row"
      >
        <input
          class="form-input"
          v-model="option.text"
          :aria-label="`选项 ${index + 1}`"
          maxlength="200"
        />
        <button
          v-if="!readonly"
          class="text-button danger"
          @click="content.options.splice(index, 1)"
        >
          删除
        </button>
      </div>
      <button
        v-if="!readonly"
        class="text-button"
        :disabled="content.options.length >= 50"
        @click="addOption"
      >
        添加选项
      </button>
    </template>
    <div class="library-columns" v-if="content.type === 'multiple_choice'">
      <label
        >最少选择<input
          class="form-input"
          type="number"
          min="0"
          :value="content.validation.min_choices"
          @input="content.validation.min_choices = number($event)"
      /></label>
      <label
        >最多选择<input
          class="form-input"
          type="number"
          min="0"
          :value="content.validation.max_choices"
          @input="content.validation.max_choices = number($event)"
      /></label>
    </div>
    <div class="library-columns" v-if="content.type === 'text'">
      <label
        >最少字数<input
          class="form-input"
          type="number"
          min="0"
          max="10000"
          :value="content.validation.min_length"
          @input="content.validation.min_length = number($event)"
      /></label>
      <label
        >最多字数<input
          class="form-input"
          type="number"
          min="0"
          max="10000"
          :value="content.validation.max_length"
          @input="content.validation.max_length = number($event)"
      /></label>
    </div>
    <template v-if="content.type === 'number'">
      <div class="library-columns">
        <label
          >最小值<input
            class="form-input"
            type="number"
            :value="content.validation.min_value"
            @input="content.validation.min_value = number($event)"
        /></label>
        <label
          >最大值<input
            class="form-input"
            type="number"
            :value="content.validation.max_value"
            @input="content.validation.max_value = number($event)"
        /></label>
      </div>
      <label class="inline-label"
        ><input type="checkbox" v-model="content.validation.integer_only" />
        仅允许整数</label
      >
    </template>
  </fieldset>
</template>
