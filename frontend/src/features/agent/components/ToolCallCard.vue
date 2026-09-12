<template>
  <div class="tool-call-card">
    <div class="tool-header">
      <span class="tool-icon">⚙️</span>
      <span class="tool-name">{{ name }}</span>
      <el-tag :type="statusType" size="small">
        {{ statusText }}
      </el-tag>
    </div>
    <div v-if="args && Object.keys(args).length" class="tool-args">
      <pre>{{ formattedArgs }}</pre>
    </div>
    <div v-if="result !== undefined" class="tool-result">
      <div class="result-label">返回结果</div>
      <pre>{{ formattedResult }}</pre>
    </div>
    <div v-if="error" class="tool-error">
      <span class="error-icon">❌</span>
      <span>{{ error }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';

interface Props {
  name: string;
  args?: Record<string, unknown>;
  result?: unknown;
  error?: string;
  status?: 'calling' | 'success' | 'failed';
}

const props = defineProps<Props>();

const statusType = computed(() => {
  switch (props.status) {
    case 'calling':
      return 'info';
    case 'success':
      return 'success';
    case 'failed':
      return 'danger';
    default:
      return 'info';
  }
});

const statusText = computed(() => {
  switch (props.status) {
    case 'calling':
      return '调用中...';
    case 'success':
      return '成功';
    case 'failed':
      return '失败';
    default:
      return '调用中...';
  }
});

const formattedArgs = computed(() => {
  if (!props.args) return '';
  try {
    return JSON.stringify(props.args, null, 2);
  } catch {
    return String(props.args);
  }
});

const formattedResult = computed(() => {
  if (props.result === undefined) return '';
  try {
    return JSON.stringify(props.result, null, 2);
  } catch {
    return String(props.result);
  }
});
</script>

<style scoped>
.tool-call-card {
  background: var(--reai-bg-neutral);
  border: 1px solid var(--reai-border);
  border-radius: 8px;
  padding: 10px 12px;
  margin: 8px 0;
  font-size: 12px;
}
.tool-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}
.tool-icon {
  font-size: 14px;
}
.tool-name {
  font-weight: 500;
  color: var(--reai-text-main);
  flex: 1;
}
.tool-args,
.tool-result {
  margin-top: 8px;
}
.tool-args pre,
.tool-result pre {
  background: var(--reai-card);
  border-radius: 6px;
  padding: 8px;
  overflow-x: auto;
  max-height: 200px;
  font-size: 11px;
  line-height: 1.5;
  color: var(--reai-text-secondary);
}
.result-label {
  font-size: 11px;
  color: var(--reai-text-muted);
  margin-bottom: 4px;
}
.tool-error {
  display: flex;
  align-items: center;
  gap: 6px;
  color: var(--reai-danger);
  margin-top: 8px;
  padding: 8px;
  background: rgba(245, 108, 108, 0.1);
  border-radius: 6px;
}
</style>
