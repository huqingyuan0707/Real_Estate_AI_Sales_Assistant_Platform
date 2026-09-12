<template>
  <div v-if="references?.length" class="citation-list">
    <div class="citation-toggle" @click="expanded = !expanded">
      <span>📎 引用 {{ references.length }} 篇资料</span>
      <span class="expand-icon">{{ expanded ? '▼' : '▶' }}</span>
      <span v-if="guard?.blocked" class="guard-chip">已拦截越权片段 {{ guard.blocked }}</span>
      <span v-if="guard?.injection" class="guard-chip warn">注入告警 {{ guard.injection }}</span>
    </div>
    <Transition name="slide">
      <div v-show="expanded" class="citation-items">
        <div v-for="(ref, i) in references" :key="i" class="citation-item">
          <div class="citation-header">
            <span class="citation-doc">📄 {{ ref.doc }}</span>
            <template v-if="ref.section && ref.section !== ref.doc">
              <span class="citation-section">· {{ ref.section }}</span>
            </template>
            <template v-if="ref.page">
              <span class="citation-page">第{{ ref.page }}页</span>
            </template>
            <template v-if="ref.score !== undefined">
              <span class="citation-score">相关度 {{ Math.round(ref.score * 100) }}%</span>
            </template>
            <template v-if="ref.security_level">
              <span :class="['citation-level', ref.security_level]">{{
                levelTag[ref.security_level]
              }}</span>
            </template>
          </div>
          <div class="citation-snippet">
            {{ ref.snippet }}
          </div>
        </div>
      </div>
    </Transition>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import type { Reference, GuardInfo } from '../types/agent';

interface Props {
  references: Reference[];
  guard?: GuardInfo | undefined;
}

defineProps<Props>();

const expanded = ref(false);

const levelTag: Record<string, string> = {
  public: '公开',
  internal: '内部',
  confidential: '机密',
};
</script>

<style scoped>
.citation-list {
  margin-top: 12px;
  border-top: 1px dashed var(--reai-border);
  padding-top: 8px;
}
.citation-toggle {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: var(--reai-primary);
  cursor: pointer;
}
.expand-icon {
  font-size: 12px;
  transition: transform 0.2s;
}
.citation-toggle:hover {
  text-decoration: underline;
}
.citation-items {
  margin-top: 8px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.citation-item {
  background: var(--reai-bg-neutral);
  border-radius: 8px;
  padding: 8px 12px;
}
.citation-header {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
  font-size: 12px;
  margin-bottom: 4px;
}
.citation-doc {
  font-weight: 500;
  color: var(--reai-text-main);
}
.citation-section,
.citation-page {
  color: var(--reai-text-muted);
}
.citation-score {
  color: var(--reai-primary);
  font-size: 11px;
}
.citation-level {
  font-size: 10px;
  border-radius: 9999px;
  padding: 1px 6px;
}
.citation-level.public {
  background: rgba(103, 194, 58, 0.14);
  color: var(--reai-success);
}
.citation-level.internal {
  background: var(--reai-primary-soft);
  color: var(--reai-primary);
}
.citation-level.confidential {
  background: rgba(245, 108, 108, 0.14);
  color: var(--reai-danger);
}
.citation-snippet {
  font-size: 12px;
  color: var(--reai-text-muted);
  line-height: 1.5;
}
.guard-chip {
  margin-left: 8px;
  font-size: 10px;
  color: var(--reai-text-muted);
  background: var(--reai-bg-gray);
  border-radius: 9999px;
  padding: 1px 6px;
}
.guard-chip.warn {
  color: var(--reai-warning);
  background: rgba(230, 162, 60, 0.14);
}
.slide-enter-active,
.slide-leave-active {
  transition: all 0.2s ease;
}
.slide-enter-from,
.slide-leave-to {
  opacity: 0;
  transform: translateY(-8px);
}
</style>
