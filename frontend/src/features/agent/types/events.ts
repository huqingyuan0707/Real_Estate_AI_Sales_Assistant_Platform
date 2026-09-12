export type AgentEvent =
  | { type: 'text'; content: string }
  | { type: 'tool_call'; name: string; args: Record<string, unknown> }
  | { type: 'tool_result'; name: string; result: unknown }
  | { type: 'approval'; action: string; args: Record<string, unknown> }
  | { type: 'error'; code: string; message: string }
  | { type: 'phase'; phase: string }
  | {
      type: 'done';
      trace_id: string;
      references?: Reference[];
      guard?: GuardInfo;
      faithfulness?: FaithfulnessInfo;
      model?: string;
    }
  | { type: 'rejected' };

export interface Reference {
  doc: string;
  page?: number;
  snippet: string;
  score?: number;
  security_level?: 'public' | 'internal' | 'confidential';
  section?: string;
}

export interface GuardInfo {
  blocked?: number;
  injection?: number;
  redacted?: number;
}

export interface FaithfulnessInfo {
  score: number;
  level: 'high' | 'medium' | 'low';
  warnings?: string[];
  invalid_refs?: string[];
}

export interface SSEOptions {
  onMessage?: (event: AgentEvent) => void;
  onError?: (error: Error) => void;
  onDone?: (traceId: string) => void;
  onPhase?: (phase: string) => void;
}

export interface RetryOptions {
  maxRetries?: number;
  retryDelay?: number;
  retryCondition?: (error: Error) => boolean;
}
