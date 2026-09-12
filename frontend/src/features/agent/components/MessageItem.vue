<template>
  <div v-if="message.role === 'user'" class="row row-user">
    <div class="bubble bubble-user">
      <div v-if="message.skill" class="skill-chip">⚡ {{ message.skill }}</div>
      <div class="bubble-text" v-html="formatContent(message.content)" />
      <div v-if="message.attachments?.length" class="attach-row">
        <span v-for="a in message.attachments" :key="a" class="attach-tag">📎 {{ a }}</span>
      </div>
    </div>
  </div>

  <div v-else class="row row-ai">
    <div class="ai-wrap">
      <span class="ai-tag">AI生成 仅供参考</span>

      <div v-if="message.rejected" class="bubble bubble-ai rejected">
        <div class="refuse-bar">
          <span class="refuse-text">⚠️ 知识库暂无相关内容</span>
          <router-link to="/knowledge">
            <el-button text type="primary" size="small"> 📤 去上传资料 </el-button>
          </router-link>
        </div>
      </div>

      <div v-else class="bubble bubble-ai">
        <StreamMessage :message="message" :is-streaming="streaming" />

        <div
          v-if="message.houseCard && message.content"
          class="house-card"
          @click="$emit('open-house')"
        >
          <span class="house-icon">📐</span>
          <div class="house-info">
            <div class="house-name">户型卡片 · 点击进入空间智能引擎</div>
            <div class="house-sub">解析看懂 / 设计想象 / 效果图心动</div>
          </div>
          <el-icon color="var(--reai-primary)">
            <ArrowRight />
          </el-icon>
        </div>

        <CitationList :references="message.references ?? []" :guard="message.guard" />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ArrowRight } from '@element-plus/icons-vue';
import StreamMessage from './StreamMessage.vue';
import CitationList from './CitationList.vue';
import type { Message } from '../types/agent';

interface Props {
  message: Message;
  streaming?: boolean;
}

const emit = defineEmits<{
  rate: [messageId: string, rating: 'up' | 'down'];
  'open-house': [];
}>();

const formatContent = (content: string): string => {
  return content
    .replace(/\n/g, '<br>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    .replace(/`(.+?)`/g, '<code>$1</code>');
};

defineProps<Props>();
</script>

<style scoped>
.row {
  display: flex;
  margin-bottom: 20px;
}
.row-user {
  justify-content: flex-end;
}
.row-ai {
  justify-content: flex-start;
}
.bubble {
  padding: 12px 16px;
  font-size: 15px;
  line-height: 1.6;
}
.bubble-user {
  background: var(--reai-bg-gray);
  color: var(--reai-text-main);
  border-radius: 16px 16px 4px 16px;
  max-width: 70%;
}
.bubble-ai {
  background: var(--reai-card);
  color: var(--reai-text-main);
  border-radius: 16px 16px 16px 4px;
  max-width: 80%;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
}
.bubble-text {
  white-space: pre-wrap;
  word-break: break-word;
}
.skill-chip {
  display: inline-block;
  font-size: 12px;
  background: var(--reai-card);
  border-radius: 9999px;
  padding: 1px 10px;
  margin-bottom: 6px;
}
.attach-row {
  display: flex;
  gap: 6px;
  margin-top: 8px;
  flex-wrap: wrap;
}
.attach-tag {
  font-size: 12px;
  background: var(--reai-bg-neutral);
  border-radius: 9999px;
  padding: 2px 8px;
  color: var(--reai-text-secondary);
}
.ai-wrap {
  max-width: 80%;
}
.ai-tag {
  display: inline-block;
  font-size: 10px;
  line-height: 14px;
  color: var(--reai-text-muted);
  background: transparent;
  border-radius: 4px;
  padding: 2px 6px;
  margin-bottom: 4px;
}
.refuse-bar {
  background: var(--st-warn-bg);
  border-radius: 10px;
  padding: 12px 16px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.refuse-text {
  color: var(--st-warn-fg);
  font-size: 14px;
}
.house-card {
  margin-top: 12px;
  background: var(--reai-bg-neutral);
  border-radius: 12px;
  padding: 12px 16px;
  display: flex;
  align-items: center;
  gap: 12px;
  cursor: pointer;
  transition:
    box-shadow 0.2s,
    background 0.2s;
}
.house-card:hover {
  box-shadow: var(--reai-shadow-md);
}
.house-icon {
  font-size: 28px;
}
.house-info {
  flex: 1;
}
.house-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--reai-text-main);
}
.house-sub {
  font-size: 12px;
  color: var(--reai-text-muted);
  margin-top: 2px;
}
</style>
