import { ref, computed } from 'vue';
import { useSessionStore } from '../stores/session';
import { useAgentStateStore } from '../stores/agentState';
import { useSkillStore } from '../stores/skill';
import { useAgentStream } from './useAgentStream';
import { api } from '@/api';
import type { Message, Reference, MessageUpdate } from '../types/agent';
import ElMessage from 'element-plus/es/components/message';
import ElMessageBox from 'element-plus/es/components/message-box';

export function useChat() {
  const sessionStore = useSessionStore();
  const agentStateStore = useAgentStateStore();
  const skillStore = useSkillStore();

  const draft = ref('');
  const attachments = ref<string[]>([]);
  const canSend = ref(false);

  const { status } = useAgentStream({
    onPhase: phase => agentStateStore.setPhaseText(phase),
    onDone: traceId => {
      const lastMsg = sessionStore.messages[sessionStore.messages.length - 1];
      if (lastMsg && lastMsg.role === 'assistant') {
        lastMsg.traceId = traceId;
      }
    },
    onError: err => {
      ElMessage.error(err.message);
    },
  });

  const phaseText = computed(() => agentStateStore.status.phaseText);

  function updateCanSend() {
    canSend.value = draft.value.trim().length > 0;
  }

  function onInput() {
    skillStore.toggleSkillMenu(draft.value.endsWith('@'));
    if (!draft.value.includes('@')) {
      skillStore.clearActiveSkill();
    }
    updateCanSend();
  }

  function pickSkill(name: string) {
    skillStore.setActiveSkill(name);
    draft.value = draft.value.replace(/@$/, '');
    skillStore.toggleSkillMenu(false);
    draft.value += `${name} `;
    updateCanSend();
  }

  function addAttachment() {
    attachments.value.push(`attachment_${Date.now()}.jpg`);
  }

  function removeAttachment(index: number) {
    attachments.value.splice(index, 1);
  }

  async function sendMessage() {
    if (!canSend.value || status.value === 'streaming') return;

    const content = draft.value.trim();
    if (!content) return;

    const threadId = sessionStore.currentId;
    if (!threadId) return;

    const userMsg: Message = {
      id: `u-${Date.now()}`,
      role: 'user',
      content,
      attachments: [...attachments.value],
      skill: skillStore.activeSkill,
      time: '刚刚',
    };
    sessionStore.addMessage(userMsg);

    const aiMsg: Message = {
      id: `a-${Date.now()}`,
      role: 'assistant',
      content: '',
      time: '刚刚',
    };
    sessionStore.addMessage(aiMsg);

    draft.value = '';
    attachments.value = [];
    skillStore.clearActiveSkill();
    updateCanSend();

    agentStateStore.startStreaming();

    const isRestored = sessionStore.isRestored(threadId);
    const streamPromise = isRestored
      ? api.resumeSession(threadId, content)
      : api.chatStream({
          thread_id: threadId,
          content,
          skill: skillStore.activeSkill,
          attachments: attachments.value,
        });

    try {
      const response = await streamPromise;
      const contentType = response.headers.get('content-type') ?? '';

      if (!contentType.includes('text/event-stream')) {
        const body = await response.json();
        if (body.code === 2001) {
          sessionStore.updateMessage(aiMsg.id, { rejected: true });
          agentStateStore.finishStreaming();
          return;
        }
        throw new Error(body.msg || '请求失败');
      }

      const reader = response.body?.getReader();
      if (!reader) throw new Error('No response body');
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const parts = buffer.split('\n\n');
        buffer = parts.pop() ?? '';

        for (const part of parts) {
          if (!part.trim()) continue;
          const eventMatch = /event: (.*)/.exec(part);
          const dataMatch = /data: (.*)/.exec(part);
          if (!eventMatch) continue;

          const eventType = eventMatch[1]?.trim() ?? '';
          const data = dataMatch?.[1] ?? '';

          switch (eventType) {
            case 'phase':
              agentStateStore.setPhaseText(data ?? '');
              break;
            case 'message':
              sessionStore.updateMessage(aiMsg.id, {
                content: (aiMsg.content ?? '') + data,
              });
              break;
            case 'done': {
              let refs: Reference[] = [];
              let guard: Message['guard'] = undefined;
              let faithfulness: Message['faithfulness'] = undefined;
              let model: string = '';
              let traceId = '';
              try {
                const payload = JSON.parse(data ?? '{}');
                refs = payload.references ?? [];
                guard = payload.guard;
                faithfulness = payload.faithfulness;
                model = payload.model;
                traceId = payload?.trace_id ?? '';
              } catch {
                // ignore
              }
              const updatePatch: MessageUpdate = {
                references: refs,
                traceId,
                model,
              };
              if (guard !== undefined) updatePatch.guard = guard;
              if (faithfulness !== undefined) updatePatch.faithfulness = faithfulness;
              sessionStore.updateMessage(aiMsg.id, updatePatch);
              agentStateStore.finishStreaming();
              return;
            }
          }
        }
      }
    } catch (err) {
      console.error('Chat stream error:', err);
      ElMessage.error('发送失败，请重试');
      agentStateStore.setError();
    }
  }

  async function clearContext() {
    try {
      await ElMessageBox.confirm(
        '将清空本会话的短期记忆（多轮上下文），开始全新话题。长期记忆不受影响。',
        '清空上下文',
        {
          type: 'warning',
        }
      );
      await api.clearShortMemory(sessionStore.currentId ?? '');
      sessionStore.clearMessages();
      ElMessage.success('短期记忆已清空');
    } catch {
      // cancelled
    }
  }

  return {
    draft,
    attachments,
    canSend,
    activeSkill: skillStore.activeSkill,
    showSkillMenu: skillStore.showSkillMenu,
    onInput,
    pickSkill,
    addAttachment,
    removeAttachment,
    sendMessage,
    clearContext,
    streaming: status.value === 'streaming',
    phaseText,
  };
}
