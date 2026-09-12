import { ref, type Ref } from 'vue';
import type { AgentEvent, SSEOptions, RetryOptions } from '../types/events';

export interface UseAgentStreamReturn {
  events: Ref<AgentEvent[]>;
  status: Ref<'idle' | 'streaming' | 'done' | 'error'>;
  error: Ref<Error | null>;
  start: (url: string, options?: RequestInit) => Promise<void>;
  stop: () => void;
  reconnect: () => Promise<void>;
}

export const useAgentStream = (
  options: SSEOptions = {},
  retryOptions: RetryOptions = {}
): UseAgentStreamReturn => {
  const events = ref<AgentEvent[]>([]);
  const status = ref<'idle' | 'streaming' | 'done' | 'error'>('idle');
  const error = ref<Error | null>(null);

  let eventSource: EventSource | null = null;
  let currentUrl = '';
  let currentOptions: RequestInit | undefined;
  let retryCount = 0;
  const maxRetries = retryOptions.maxRetries ?? 3;
  const retryDelay = retryOptions.retryDelay ?? 1000;
  const retryCondition = retryOptions.retryCondition ?? (() => true);

  const parseEvent = (data: string): AgentEvent | null => {
    try {
      const parsed = JSON.parse(data);
      return parsed as AgentEvent;
    } catch {
      return null;
    }
  };

  const handleMessage = (event: MessageEvent) => {
    const agentEvent = parseEvent(event.data);
    if (!agentEvent) return;

    events.value.push(agentEvent);
    options.onMessage?.(agentEvent);

    switch (agentEvent.type) {
      case 'phase':
        options.onPhase?.(agentEvent.phase);
        break;
      case 'done':
        status.value = 'done';
        options.onDone?.(agentEvent.trace_id);
        close();
        break;
      case 'error':
        status.value = 'error';
        error.value = new Error(agentEvent.message);
        options.onError?.(error.value);
        close();
        break;
      case 'rejected':
        status.value = 'done';
        close();
        break;
    }
  };

  const handleError = (_err: Event) => {
    status.value = 'error';
    const errObj = new Error('SSE connection error');
    error.value = errObj;
    options.onError?.(errObj);
    close();

    if (retryCount < maxRetries && retryCondition(errObj)) {
      retryCount++;
      setTimeout(() => {
        reconnect();
      }, retryDelay * retryCount);
    }
  };

  const close = () => {
    if (eventSource) {
      eventSource.onmessage = null;
      eventSource.onerror = null;
      eventSource.close();
      eventSource = null;
    }
  };

  const start = async (url: string, init?: RequestInit) => {
    if (status.value === 'streaming') return;

    currentUrl = url;
    currentOptions = init;
    retryCount = 0;
    events.value = [];
    status.value = 'streaming';
    error.value = null;

    eventSource = new EventSource(url);
    eventSource.onmessage = handleMessage;
    eventSource.onerror = handleError;
  };

  const stop = () => {
    close();
    status.value = 'idle';
  };

  const reconnect = async () => {
    if (!currentUrl || status.value !== 'error') return;
    await start(currentUrl, currentOptions);
  };

  return {
    events,
    status,
    error,
    start,
    stop,
    reconnect,
  };
};
