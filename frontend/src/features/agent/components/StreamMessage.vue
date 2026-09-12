<template>
  <div class="stream-message">
    <div v-if="message.content" class="message-content" v-html="formatContent(message.content)" />
    <div v-else-if="isStreaming" class="message-content">
      <span class="cursor">▌</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { Message } from '../types/agent';

interface Props {
  message: Message;
  isStreaming?: boolean;
}

defineProps<Props>();

const formatContent = (content: string): string => {
  return content
    .replace(/\n/g, '<br>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    .replace(/`(.+?)`/g, '<code>$1</code>');
};
</script>

<style scoped>
.stream-message {
  line-height: 1.6;
}
.cursor {
  animation: blink 0.8s infinite;
  color: var(--reai-primary);
}
@keyframes blink {
  50% {
    opacity: 0;
  }
}
</style>
