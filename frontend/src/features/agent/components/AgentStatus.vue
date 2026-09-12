<template>
  <div v-if="isStreaming" class="agent-status">
    <div class="status-pill">
      <span class="dots">
        <span class="dot" />
        <span class="dot" />
        <span class="dot" />
      </span>
      <span class="status-text">{{ phaseText }}</span>
    </div>
    <div v-if="currentTool" class="current-tool">
      <span class="tool-label">正在调用:</span>
      <span class="tool-name">{{ currentTool }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
interface Props {
  isStreaming: boolean;
  phaseText: string;
  currentTool?: string;
}

defineProps<Props>();
</script>

<style scoped>
.agent-status {
  margin: 8px 0;
  padding: 8px 12px;
  background: var(--reai-bg-neutral);
  border-radius: 8px;
}
.status-pill {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: var(--reai-text-muted);
}
.dots {
  display: flex;
  gap: 3px;
}
.dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--reai-primary);
  animation: jump 1s infinite ease-in-out;
}
.dot:nth-child(2) {
  animation-delay: 0.15s;
}
.dot:nth-child(3) {
  animation-delay: 0.3s;
}
@keyframes jump {
  0%,
  100% {
    transform: translateY(0);
  }
  40% {
    transform: translateY(-4px);
  }
}
.status-text {
  font-weight: 500;
}
.current-tool {
  margin-top: 6px;
  font-size: 11px;
  color: var(--reai-text-secondary);
}
.tool-label {
  color: var(--reai-text-muted);
}
.tool-name {
  color: var(--reai-primary);
  font-weight: 500;
}
</style>
