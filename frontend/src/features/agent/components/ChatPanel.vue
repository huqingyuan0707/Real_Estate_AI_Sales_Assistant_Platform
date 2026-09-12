<template>
  <div class="chat-panel">
    <div ref="messagesEl" class="messages-area">
      <div v-if="!messages.length" class="empty-state">
        <div class="empty-icon">💬</div>
        <div class="empty-title">暂无内容</div>
        <div class="empty-sub">点击左上角"✨ 新建对话"，输入需求或 @ 调用技能开始</div>
      </div>

      <template v-for="msg in messages" :key="msg.id">
        <MessageItem :message="msg" @rate="handleRate" />
      </template>

      <AgentStatus v-if="streaming" :is-streaming="streaming" :phase-text="phaseText" />
    </div>

    <ChatInput
      v-model:draft="draft"
      v-model:attachments="attachments"
      :active-skill="activeSkill"
      :show-skill-menu="showSkillMenu"
      :streaming="streaming"
      :skills="availableSkills"
      @input="onInput"
      @pick-skill="pickSkill"
      @add-attachment="addAttachment"
      @remove-attachment="removeAttachment"
      @send="sendMessage"
      @clear-context="clearContext"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, nextTick } from 'vue';
import { useChat } from '../composables/useChat';
import { useSessionStore } from '../stores/session';
import MessageItem from './MessageItem.vue';
import AgentStatus from './AgentStatus.vue';
import ChatInput from './ChatInput.vue';

const sessionStore = useSessionStore();

const {
  draft,
  attachments,
  activeSkill,
  showSkillMenu,
  streaming,
  phaseText,
  onInput,
  pickSkill,
  addAttachment,
  removeAttachment,
  sendMessage,
  clearContext,
} = useChat();

const messages = computed(() => sessionStore.messages);
const availableSkills = computed(() => ['户型解析', '文案生成', '知识检索', '空间设计']);

const handleRate = (messageId: string, rating: 'up' | 'down') => {
  const msg = messages.value.find(m => m.id === messageId);
  if (msg) {
    msg.rating = rating;
  }
};

const messagesEl = ref<HTMLDivElement | null>(null);

const scrollBottom = () => {
  nextTick(() => {
    messagesEl.value?.scrollTo({ top: messagesEl.value.scrollHeight, behavior: 'smooth' });
  });
};

onMounted(() => {
  scrollBottom();
});
</script>

<style scoped>
.chat-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--reai-bg-neutral);
}
.messages-area {
  flex: 1;
  overflow-y: auto;
  padding: 16px 24px;
}
.messages-area > * {
  max-width: 800px;
  margin-left: auto;
  margin-right: auto;
}
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding-top: 20%;
}
.empty-icon {
  font-size: 64px;
}
.empty-title {
  font-size: 16px;
  color: var(--reai-text-main);
  margin-top: 16px;
  font-weight: 600;
}
.empty-sub {
  font-size: 14px;
  color: var(--reai-text-muted);
  margin-top: 8px;
}
</style>
