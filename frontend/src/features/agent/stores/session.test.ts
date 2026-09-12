import { describe, it, expect, beforeEach } from 'vitest';
import { setActivePinia, createPinia } from 'pinia';
import { useSessionStore } from './session';
import type { Session, Message } from '../types/agent';

describe('useSessionStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia());
  });

  it('should initialize with empty state', () => {
    const store = useSessionStore();
    expect(store.sessions).toEqual([]);
    expect(store.currentId).toBeNull();
    expect(store.messages).toEqual([]);
  });

  it('should add a new session', () => {
    const store = useSessionStore();
    const session: Session = {
      threadId: 'test-1',
      title: 'Test Session',
      group: '今天',
      time: '刚刚',
    };
    store.addSession(session);
    expect(store.sessions).toHaveLength(1);
    expect(store.currentId).toBe('test-1');
    expect(store.messages).toEqual([]);
  });

  it('should remove a session', () => {
    const store = useSessionStore();
    const session: Session = {
      threadId: 'test-1',
      title: 'Test Session',
      group: '今天',
      time: '刚刚',
    };
    store.addSession(session);
    store.removeSession('test-1');
    expect(store.sessions).toHaveLength(0);
    expect(store.currentId).toBeNull();
  });

  it('should set messages', () => {
    const store = useSessionStore();
    const messages: Message[] = [
      { id: '1', role: 'user', content: 'Hello' },
      { id: '2', role: 'assistant', content: 'Hi there!' },
    ];
    store.setMessages(messages);
    expect(store.messages).toHaveLength(2);
  });

  it('should add a message', () => {
    const store = useSessionStore();
    const message: Message = { id: '1', role: 'user', content: 'Hello' };
    store.addMessage(message);
    expect(store.messages).toHaveLength(1);
    expect(store.messages[0]!.content).toBe('Hello');
  });

  it('should update a message', () => {
    const store = useSessionStore();
    const message: Message = { id: '1', role: 'user', content: 'Hello' };
    store.addMessage(message);
    store.updateMessage('1', { content: 'Hello World' });
    expect(store.messages[0]!.content).toBe('Hello World');
  });

  it('should mark session as restored', () => {
    const store = useSessionStore();
    store.markRestored('test-1');
    expect(store.isRestored('test-1')).toBe(true);
    expect(store.isRestored('test-2')).toBe(false);
  });

  it('should group sessions by group', () => {
    const store = useSessionStore();
    store.setSessions([
      { threadId: '1', title: 'A', group: '今天', time: '10:00' },
      { threadId: '2', title: 'B', group: '今天', time: '11:00' },
      { threadId: '3', title: 'C', group: '昨天', time: '09:00' },
    ]);
    const grouped = store.groupedSessions;
    expect(Object.keys(grouped)).toEqual(['今天', '昨天']);
    expect(grouped['今天']).toHaveLength(2);
    expect(grouped['昨天']).toHaveLength(1);
  });
});
