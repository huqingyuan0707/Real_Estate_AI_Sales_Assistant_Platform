import { defineStore } from 'pinia';
import { ref, computed } from 'vue';
import type { Session, Message, MessageUpdate } from '../types/agent';

export const useSessionStore = defineStore('session', () => {
  const sessions = ref<Session[]>([]);
  const currentId = ref<string | null>(null);
  const messages = ref<Message[]>([]);
  const restoredIds = new Set<string>();

  const currentSession = computed(() => sessions.value.find(s => s.threadId === currentId.value));

  const groupedSessions = computed(() => {
    const groups: Record<string, Session[]> = {};
    for (const s of sessions.value) {
      (groups[s.group] ??= []).push(s);
    }
    return groups;
  });

  function setSessions(list: Session[]) {
    sessions.value = list;
    if (list.length && !currentId.value) {
      currentId.value = list[0]!.threadId;
    }
  }

  function addSession(session: Session) {
    sessions.value.unshift(session);
    currentId.value = session.threadId;
    messages.value = [];
  }

  function removeSession(id: string) {
    const idx = sessions.value.findIndex(s => s.threadId === id);
    if (idx > -1) sessions.value.splice(idx, 1);
    if (currentId.value === id) {
      currentId.value = sessions.value[0]?.threadId ?? null;
      messages.value = [];
    }
  }

  function renameSession(id: string, title: string) {
    const s = sessions.value.find(s => s.threadId === id);
    if (s) s.title = title;
  }

  function setCurrentSession(id: string) {
    currentId.value = id;
  }

  function setMessages(msgs: Message[]) {
    messages.value = msgs;
  }

  function addMessage(
    msg: Partial<Message> & { id: string; role: 'user' | 'assistant' | 'system'; content: string }
  ) {
    messages.value.push(msg as Message);
  }

  function updateMessage(id: string, patch: MessageUpdate) {
    const idx = messages.value.findIndex(m => m.id === id);
    if (idx > -1) {
      const msg = messages.value[idx]!;
      if (patch.content !== undefined) msg.content = patch.content;
      if (patch.skill !== undefined) msg.skill = patch.skill;
      if (patch.attachments !== undefined) msg.attachments = patch.attachments;
      if (patch.references !== undefined) msg.references = patch.references;
      if (patch.houseCard !== undefined) msg.houseCard = patch.houseCard;
      if (patch.traceId !== undefined) msg.traceId = patch.traceId;
      if (patch.guard !== undefined) msg.guard = patch.guard;
      if (patch.faithfulness !== undefined) msg.faithfulness = patch.faithfulness;
      if (patch.model !== undefined) msg.model = patch.model;
      if (patch.rating !== undefined) msg.rating = patch.rating;
      if (patch.rejected !== undefined) msg.rejected = patch.rejected;
      if (patch.time !== undefined) msg.time = patch.time;
    }
  }

  function markRestored(id: string) {
    restoredIds.add(id);
  }

  function isRestored(id: string): boolean {
    return restoredIds.has(id);
  }

  function clearMessages() {
    messages.value = [];
  }

  return {
    sessions,
    currentId,
    messages,
    currentSession,
    groupedSessions,
    setSessions,
    addSession,
    removeSession,
    renameSession,
    setCurrentSession,
    setMessages,
    addMessage,
    updateMessage,
    markRestored,
    isRestored,
    clearMessages,
  };
});
