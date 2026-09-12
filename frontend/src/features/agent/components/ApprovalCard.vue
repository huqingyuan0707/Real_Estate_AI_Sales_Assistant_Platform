<template>
  <div class="approval-card">
    <div class="approval-header">
      <span class="approval-icon">🔔</span>
      <div class="approval-info">
        <div class="approval-title">
          {{ action }}
        </div>
        <div class="approval-desc">
          {{ description }}
        </div>
      </div>
      <el-tag type="warning" size="small"> 待确认 </el-tag>
    </div>
    <div v-if="args && Object.keys(args).length" class="approval-args">
      <div class="args-label">参数详情</div>
      <div v-for="(value, key) in args" :key="key" class="arg-row">
        <span class="arg-key">{{ key }}</span>
        <span class="arg-value">{{ formatValue(value) }}</span>
      </div>
    </div>
    <div class="approval-actions">
      <el-button variant="text" @click="$emit('reject')"> 拒绝 </el-button>
      <el-button type="primary" @click="$emit('approve', args)"> 批准 </el-button>
      <el-button @click="$emit('modify')"> 修改参数 </el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
interface Props {
  action: string;
  description: string;
  args: Record<string, unknown>;
}

defineProps<Props>();

const emit = defineEmits<{
  approve: [args: Record<string, unknown>];
  reject: [];
  modify: [];
}>();

const formatValue = (value: unknown): string => {
  if (typeof value === 'object') {
    return JSON.stringify(value, null, 2);
  }
  return String(value);
};
</script>

<style scoped>
.approval-card {
  background: var(--st-warn-bg);
  border: 1px solid var(--st-warn-border);
  border-radius: 10px;
  padding: 12px 16px;
  margin: 8px 0;
}
.approval-header {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  margin-bottom: 10px;
}
.approval-icon {
  font-size: 18px;
  flex-shrink: 0;
}
.approval-info {
  flex: 1;
}
.approval-title {
  font-weight: 600;
  color: var(--reai-text-main);
  font-size: 14px;
}
.approval-desc {
  font-size: 12px;
  color: var(--reai-text-secondary);
  margin-top: 2px;
}
.approval-args {
  background: var(--reai-card);
  border-radius: 8px;
  padding: 10px;
  margin-bottom: 10px;
}
.args-label {
  font-size: 11px;
  color: var(--reai-text-muted);
  margin-bottom: 6px;
}
.arg-row {
  display: flex;
  gap: 8px;
  font-size: 12px;
  padding: 2px 0;
}
.arg-key {
  color: var(--reai-text-secondary);
  min-width: 80px;
}
.arg-value {
  color: var(--reai-text-main);
  word-break: break-all;
  flex: 1;
  font-family: monospace;
}
.approval-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
</style>
