<template>
  <div class="feedback-row">
    <span class="feedback-label">{{ message.rating ? '已反馈，感谢' : '这个回答有帮助吗？' }}</span>
    <el-icon
      :size="16"
      class="fb-icon"
      :class="{ on: message.rating === 'up' }"
      @click="handleRate('up')"
    >
      <Select />
    </el-icon>
    <el-icon
      :size="16"
      class="fb-icon"
      :class="{ on: message.rating === 'down' }"
      @click="handleRate('down')"
    >
      <CloseBold />
    </el-icon>
    <span
      v-if="message.faithfulness"
      class="faith-chip"
      :class="message.faithfulness.level"
      :title="(message.faithfulness.warnings || []).join('；') || '引用与数值一致性校验通过'"
    >
      可信度 {{ Math.round((message.faithfulness.score ?? 0) * 100) }}%
      <template v-if="message.faithfulness.invalid_refs?.length"> · 引用异常</template>
    </span>
    <span v-if="message.guard?.redacted" class="fb-tip"
      >已脱敏 {{ message.guard.redacted }} 处</span
    >
    <span v-else-if="message.guard?.blocked" class="fb-tip"
      >拦截 {{ message.guard.blocked }} 条越权片段</span
    >
    <span v-else-if="message.model" class="fb-tip">{{ message.model }}</span>
  </div>
</template>

<script setup lang="ts">
import { Select, CloseBold } from '@element-plus/icons-vue';
import type { Message } from '../types/agent';

interface Props {
  message: Message;
}

const props = defineProps<Props>();

const emit = defineEmits<{
  rate: [messageId: string, rating: 'up' | 'down'];
}>();

const handleRate = (rating: 'up' | 'down') => {
  if (props.message.rating) return;
  emit('rate', props.message.id, rating);
};
</script>

<style scoped>
.feedback-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 10px;
  font-size: 12px;
  color: var(--reai-text-muted);
}
.feedback-label {
  font-size: 12px;
  color: var(--reai-text-muted);
}
.fb-icon {
  cursor: pointer;
  color: var(--reai-text-muted);
  transition: color 0.15s;
}
.fb-icon:hover {
  color: var(--reai-primary);
}
.fb-icon.on {
  color: var(--reai-primary);
}
.fb-tip {
  margin-left: auto;
  font-size: 11px;
  color: var(--reai-text-muted);
}
.faith-chip {
  font-size: 11px;
  border-radius: 9999px;
  padding: 1px 8px;
  cursor: help;
  color: var(--reai-text-secondary);
  background: var(--reai-bg-gray);
}
.faith-chip.high {
  color: var(--reai-success);
  background: rgba(103, 194, 58, 0.14);
}
.faith-chip.medium {
  color: var(--reai-warning);
  background: rgba(230, 162, 60, 0.14);
}
.faith-chip.low {
  color: var(--reai-danger, #d66);
  background: rgba(245, 108, 108, 0.14);
}
</style>
