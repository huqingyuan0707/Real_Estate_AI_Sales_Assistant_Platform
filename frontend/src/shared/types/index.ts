export interface ApiResponse<T = unknown> {
  code: number;
  msg: string;
  data: T;
  trace_id: string;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface User {
  id: string;
  username: string;
  role: 'admin' | 'member';
  workspace_id: string;
  dept_id?: string;
  permissions: string[];
}

export interface Document {
  id: string;
  name: string;
  file_type: string;
  file_size: number;
  status: 'processing' | 'active' | 'failed' | 'archived';
  category?: string;
  security_level: 'public' | 'internal' | 'confidential';
  review_status: 'draft' | 'published' | 'rejected';
  dept_id?: string;
  owner: string;
  version: number;
  created_at: string;
  updated_at: string;
}

export interface Task {
  task_id: string;
  name: string;
  type: string;
  status: 'queued' | 'running' | 'done' | 'failed' | 'cancelled';
  progress: number;
  created_at: string;
  updated_at: string;
  result?: unknown;
  error?: string;
}
