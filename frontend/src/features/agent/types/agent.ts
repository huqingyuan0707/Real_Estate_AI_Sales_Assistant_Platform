export interface Message {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  skill?: string;
  attachments?: string[];
  references?: Reference[];
  houseCard?: boolean;
  traceId?: string;
  guard?: GuardInfo;
  faithfulness?: FaithfulnessInfo;
  model?: string;
  rating?: 'up' | 'down';
  rejected?: boolean;
  time?: string;
}

export interface MessageUpdate {
  id?: string;
  role?: 'user' | 'assistant' | 'system';
  content?: string;
  skill?: string;
  attachments?: string[];
  references?: Reference[] | undefined;
  houseCard?: boolean;
  traceId?: string;
  guard?: GuardInfo;
  faithfulness?: FaithfulnessInfo;
  model?: string;
  rating?: 'up' | 'down';
  rejected?: boolean;
  time?: string;
}

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

export interface Session {
  threadId: string;
  title: string;
  group: string;
  time: string;
}

export interface Skill {
  id: string;
  name: string;
  description: string;
  version: string;
  installed: boolean;
  is_open_source: boolean;
}

export type AgentPhase = 'planning' | 'executing' | 'validating' | 'summarizing' | 'done' | 'error';

export interface AgentStatus {
  phase: AgentPhase;
  phaseText: string;
  isStreaming: boolean;
}

export interface ChatRequest {
  thread_id?: string;
  content: string;
  skill?: string;
  attachments?: string[];
}
