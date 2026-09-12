<template>
  <div class="input-area">
    <div v-if="attachments.length || activeSkill" class="input-tags">
      <span v-if="activeSkill" class="skill-tag-active">
        ⚡ {{ activeSkill }}
        <el-icon :size="12" @click="$emit('pick-skill', '')"><Close /></el-icon>
      </span>
      <span v-for="(a, i) in attachments" :key="a" class="attach-tag">
        📎 {{ a }}
        <el-icon :size="12" style="cursor: pointer" @click="$emit('remove-attachment', i)"
          ><Close
        /></el-icon>
      </span>
    </div>

    <div v-if="!activeSkill && !attachments.length" class="skill-hint">
      输入 <b>@</b> 调用技能 · 支持上传附件
    </div>

    <textarea
      v-model="draft"
      class="input-box"
      placeholder="输入需求，或 @ 调用技能，支持上传附件..."
      @input="$emit('input')"
      @keydown="onKeydown"
    />

    <div class="input-toolbar">
      <div class="toolbar-left">
        <el-icon :size="20" class="tool-icon" @click="$emit('add-attachment')">
          <Paperclip />
        </el-icon>
        <el-tooltip content="清空本会话短期记忆（长期记忆不受影响）" placement="top">
          <el-icon :size="20" class="tool-icon" @click="$emit('clear-context')">
            <Delete />
          </el-icon>
        </el-tooltip>
      </div>
      <el-button
        type="primary"
        size="large"
        class="send-btn"
        round
        :disabled="!canSend || streaming"
        @click="$emit('send')"
      >
        {{ streaming ? '生成中...' : '发送' }}
      </el-button>
    </div>

    <div v-if="showSkillMenu" class="skill-menu">
      <div class="skill-menu-title">选择已安装技能</div>
      <div v-for="s in skills" :key="s" class="skill-menu-item" @click="$emit('pick-skill', s)">
        ⚡ {{ s }}
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { Paperclip, Delete, Close } from '@element-plus/icons-vue';

interface Props {
  draft: string;
  attachments: string[];
  activeSkill: string;
  showSkillMenu: boolean;
  streaming: boolean;
  skills: string[];
}

interface Emits {
  input: [];
  'pick-skill': [skill: string];
  'add-attachment': [];
  'remove-attachment': [index: number];
  send: [];
  'clear-context': [];
}

const props = defineProps<Props>();
const emit = defineEmits<Emits>();

const canSend = computed(() => props.draft.trim().length > 0);

const onKeydown = (e: KeyboardEvent) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    if (canSend.value) emit('send');
  }
};
</script>

<style scoped>
.input-area {
  background: var(--reai-card);
  border-radius: 16px;
  box-shadow: var(--reai-shadow-md);
  padding: 10px 18px 8px;
  margin: 0 12px 16px;
  position: relative;
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
}
.input-tags {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  padding-bottom: 4px;
}
.skill-tag-active,
.attach-tag {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  background: var(--reai-bg-gray);
  border-radius: 9999px;
  padding: 3px 10px;
  color: var(--reai-text-secondary);
}
.skill-tag-active {
  background: var(--reai-primary-soft);
  color: var(--reai-primary);
}
.skill-hint {
  font-size: 12px;
  color: var(--reai-text-muted);
  padding: 2px 2px 6px;
}
.input-box {
  flex: 1;
  border: none;
  outline: none;
  resize: none;
  min-height: 52px;
  max-height: 100px;
  font-size: 14px;
  line-height: 1.6;
  color: var(--reai-text-main);
  background: transparent;
  font-family: inherit;
}
.input-box::placeholder {
  color: var(--reai-text-muted);
}
.input-toolbar {
  height: 38px;
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.toolbar-left {
  display: flex;
  gap: 12px;
}
.tool-icon {
  cursor: pointer;
  color: var(--reai-text-secondary);
  padding: 4px;
  border-radius: 8px;
}
.tool-icon:hover {
  color: var(--reai-primary);
  background: var(--reai-primary-soft);
}
.send-btn {
  min-width: 80px;
  height: 36px;
  font-weight: 600;
}
.skill-menu {
  position: absolute;
  bottom: calc(100% + 8px);
  left: 0;
  width: 240px;
  background: var(--reai-card);
  border-radius: 14px;
  box-shadow: var(--reai-shadow-lg);
  padding: 8px;
  z-index: 10;
}
.skill-menu-title {
  font-size: 12px;
  color: var(--reai-text-muted);
  padding: 4px 8px 8px;
}
.skill-menu-item {
  padding: 8px 12px;
  border-radius: 10px;
  font-size: 14px;
  cursor: pointer;
  color: var(--reai-text-main);
}
.skill-menu-item:hover {
  background: var(--reai-primary-soft);
  color: var(--reai-primary);
}
</style>
