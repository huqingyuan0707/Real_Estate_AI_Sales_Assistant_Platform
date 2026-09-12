<script setup lang="ts">
/**
 * AiButton —— 按钮业务封装层
 * 统一视觉口径：large=主CTA(44px) / default=常规(40px) / small=表格操作(32px)
 * 未来更换 UI 库时只改本层，业务代码不受影响。
 */
defineOptions({ inheritAttrs: false });
withDefaults(
  defineProps<{
    size?: 'large' | 'default' | 'small';
    type?: 'primary' | 'default' | 'text' | 'danger';
    customClass?: string;
  }>(),
  { size: 'default', type: 'default', customClass: '' }
);
</script>

<template>
  <el-button
    v-bind="$attrs"
    :type="type"
    :size="size"
    :class="['ai-button', `ai-button--${type}`, customClass]"
  >
    <slot />
  </el-button>
</template>

<style scoped>
.ai-button {
  letter-spacing: 0.2px;
}
.ai-button--primary {
  font-weight: 500;
}
</style>
