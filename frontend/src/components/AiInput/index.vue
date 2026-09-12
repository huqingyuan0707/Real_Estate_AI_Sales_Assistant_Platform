<script setup lang="ts">
/**
 * AiInput —— 输入框业务封装层
 * 统一高度 40px / 圆角 8px / 聚焦灰蓝光晕（视觉由 element-override.css 全局生效）
 * prefix-icon / suffix-icon 既支持传组件对象，也兼容传图标名字符串（在此统一解析，
 * 避免各调用处重复 import；字符串形式在未全局注册图标时会渲染为空白）
 */
import { computed, type Component } from 'vue';
import { Lock, OfficeBuilding, Search, User } from '@element-plus/icons-vue';

defineOptions({ inheritAttrs: false });

const props = withDefaults(
  defineProps<{
    modelValue?: string;
    placeholder?: string;
    clearable?: boolean;
    customClass?: string;
    prefixIcon?: string | Component;
    suffixIcon?: string | Component;
  }>(),
  { modelValue: '', placeholder: '请输入', clearable: true, customClass: '' }
);
const emit = defineEmits<{ (e: 'update:modelValue', v: string): void }>();

/** 图标名 → 组件；未收录的名称回退 undefined，由 el-input 忽略该项 */
const ICON_MAP: Record<string, Component> = { Search, User, Lock, OfficeBuilding };
const resolveIcon = (icon?: string | Component) =>
  typeof icon === 'string' ? ICON_MAP[icon] : icon;
const prefixIconComp = computed(() => resolveIcon(props.prefixIcon));
const suffixIconComp = computed(() => resolveIcon(props.suffixIcon));
</script>

<template>
  <el-input
    :model-value="modelValue"
    :placeholder="placeholder"
    :clearable="clearable"
    :prefix-icon="prefixIconComp"
    :suffix-icon="suffixIconComp"
    :class="['ai-input', customClass]"
    v-bind="$attrs"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <template v-for="(_, name) in $slots" #[name]="slotProps">
      <slot :name="name" v-bind="slotProps ?? {}" />
    </template>
  </el-input>
</template>

<style scoped>
.ai-input {
  width: 100%;
}
</style>
