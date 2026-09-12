/**
 * API 层：与后端 FastAPI（backend/app）一一对应，统一解包 {code,msg,data,trace_id}。
 * 页面设计阶段默认渲染 src/mock 的演示数据；联调时切换调用本文件即可。
 */
const BASE = '/api/v1';

interface Envelope<T = any> {
  code: number;
  msg: string;
  data: T;
  trace_id: string;
}

/** 知识治理标签：上传时填写，写入分块元数据并决定检索阶段的可见范围 */
export interface DocumentGovernance {
  security_level?: string; // public / internal / confidential
  dept_id?: string; // 归属部门，空 = 全公司可见
  review_status?: string; // draft 草稿（不入检索）/ published 已发布
  effective_at?: string; // 生效日期 YYYY-MM-DD
  expire_at?: string; // 失效日期 YYYY-MM-DD
}

const appendGov = (fd: FormData, gov?: DocumentGovernance) => {
  if (!gov) return;
  Object.entries(gov).forEach(([k, v]) => {
    if (v) fd.append(k, v);
  });
};

// 401 统一分流：token 过期/无效 → 清空登录态并回登录页（HTTP 401 与业务码 1002 双层命中）
const handle401 = () => {
  ['reai_token', 'reai_auth', 'reai_role', 'reai_username', 'reai_perms'].forEach(k => {
    sessionStorage.removeItem(k);
    localStorage.removeItem(k);
  });
  if (!location.pathname.startsWith('/login')) location.href = '/login';
};

export const request = async <T = any>(path: string, options: RequestInit = {}): Promise<T> => {
  const token = sessionStorage.getItem('reai_token') ?? '';
  // FormData（文件上传）必须交给浏览器自动生成 multipart 头，不能手工设 Content-Type
  const isForm = options.body instanceof FormData;
  const res = await fetch(`${BASE}${path}`, {
    ...options,
    headers: {
      ...(isForm ? {} : { 'Content-Type': 'application/json' }),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(options.headers ?? {}),
    },
  });
  let body: Envelope<T> | null;
  try {
    body = (await res.json()) as Envelope<T>;
  } catch {
    body = null;
  }
  if (res.status === 401 || body?.code === 1002) {
    handle401();
    throw Object.assign(new Error(body?.msg ?? '登录状态已失效，请重新登录'), { code: 1002 });
  }
  if (!body)
    throw Object.assign(new Error(`请求失败（HTTP ${res.status}）`), {
      code: res.status === 403 ? 1003 : 5000,
    });
  if (body.code !== 0)
    throw Object.assign(new Error(body.msg ?? `请求失败（业务码 ${body.code}）`), {
      code: body.code ?? 5000,
      trace_id: body.trace_id,
    });
  return body.data;
};

export const api = {
  // 认证
  login: (p: { username: string; password: string; mode: 'local' | 'ldap' }) =>
    request('/auth/login', { method: 'POST', body: JSON.stringify(p) }),
  // 会话自愈：权限缓存丢失时按 token 重取用户信息与权限集
  authMe: () => request('/auth/me'),
  // 会话
  listSessions: () => request('/sessions'),
  getSession: (threadId: string) => request(`/sessions/${threadId}`),
  deleteSession: (threadId: string) => request(`/sessions/${threadId}`, { method: 'DELETE' }),
  // 对话（SSE，返回原始 Response 供调用方按 event 流解析）
  chatStream: (p: {
    thread_id?: string;
    content: string;
    skill?: string;
    attachments?: string[];
  }) =>
    fetch(`${BASE}/chat`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${sessionStorage.getItem('reai_token') ?? ''}`,
      },
      body: JSON.stringify(p),
    }),
  // 知识库（生产数据）与系统设置（配置调优），与智能问答（消费数据）形成闭环
  listDocuments: () => request('/documents'),
  uploadDocument: (file: File, gov?: DocumentGovernance) => {
    const fd = new FormData();
    fd.append('file', file);
    appendGov(fd, gov);
    return request('/documents/upload', { method: 'POST', body: fd });
  },
  searchDocuments: (query: string) =>
    request('/documents/search', { method: 'POST', body: JSON.stringify({ query }) }),
  deleteDocument: (name: string) =>
    request(`/documents/${encodeURIComponent(name)}`, { method: 'DELETE' }),
  documentStats: () => request('/documents/stats'),
  // 治理总览：密级 / 部门 / 审核态分布 + 可选标签（上传表单与运营看板共用）
  documentGovernance: () => request('/documents/governance'),
  // 知识审核（生命周期：草稿 → 发布 / 驳回 → 归档），同步生效于检索过滤
  reviewDocument: (docId: string, action: 'approve' | 'reject' | 'archive', comment = '') =>
    request(`/documents/${encodeURIComponent(docId)}/review`, {
      method: 'POST',
      body: JSON.stringify({ action, comment }),
    }),
  // 知识质量校验：完整性 / 时效性 / 一致性 / 治理标签
  documentQuality: () => request('/documents/quality'),
  // 增量同步：按 SHA256 指纹只处理新增/变更文件
  documentSync: () => request('/documents/sync', { method: 'POST' }),
  // 索引版本管理：换嵌入模型整库重建 + 快照回滚
  indexVersions: () => request('/index-admin/versions'),
  indexRebuild: (embed_model?: string) =>
    request('/index-admin/rebuild', { method: 'POST', body: JSON.stringify({ embed_model }) }),
  indexRollback: (backup: string) =>
    request('/index-admin/rollback', { method: 'POST', body: JSON.stringify({ backup }) }),
  // 反馈闭环：采纳/不采纳 → 差评知识排行与知识缺口分析
  submitFeedback: (p: {
    rating: 'up' | 'down';
    thread_id?: string;
    trace_id?: string;
    query?: string;
    answer?: string;
    docs?: string[];
    comment?: string;
    correction?: string;
    rejected?: boolean;
  }) => request('/feedback', { method: 'POST', body: JSON.stringify(p) }),
  feedbackStats: () => request('/feedback/stats'),
  // 检索可解释性：召回片段、双路来源与治理拦截明细（不含生成）
  retrievalPreview: (q: string) => request(`/chat/retrieval-preview?q=${encodeURIComponent(q)}`),
  // 系统设置：模型 / 检索 / 分块参数（热更新）
  getSettings: () => request('/settings'),
  updateSettings: (p: {
    llm_model?: string;
    rag_top_k?: number;
    rag_final_k?: number;
    rag_min_score?: number;
    rag_chunk_size?: number;
    rag_chunk_overlap?: number;
  }) => request('/settings', { method: 'PUT', body: JSON.stringify(p) }),
  // 我的 AI 服务：每个用户在前端自行填写 Key，保存后立即生效（无需改 .env / 重启后端）
  getAiConfig: () => request('/ai-config'),
  saveAiConfig: (p: {
    llm_base_url?: string;
    llm_api_key?: string;
    llm_model?: string;
    render_api_base?: string;
    render_api_key?: string;
    render_api_model?: string;
  }) => request('/ai-config', { method: 'PUT', body: JSON.stringify(p) }),
  clearAiConfig: () => request('/ai-config', { method: 'DELETE' }),
  testAiConfig: (p: { target: 'llm' | 'render'; base_url?: string; api_key?: string }) =>
    request('/ai-config/test', { method: 'POST', body: JSON.stringify(p) }),
  // 记忆管理：短期（会话内，窗口+摘要+Token预算）与长期（授权写入，可查看/修改/删除）
  getShortMemory: (threadId: string) => request(`/memory/short/${encodeURIComponent(threadId)}`),
  clearShortMemory: (threadId: string) =>
    request(`/memory/short/${encodeURIComponent(threadId)}`, { method: 'DELETE' }),
  memoryStats: () => request('/memory/stats'),
  listLongMemory: () => request('/memory/long'),
  addLongMemory: (p: {
    content: string;
    category?: string;
    authorized?: boolean;
    expires_days?: number;
  }) => request('/memory/long', { method: 'POST', body: JSON.stringify(p) }),
  updateLongMemory: (
    id: string,
    p: { content?: string; category?: string; authorized?: boolean; expires_days?: number }
  ) => request(`/memory/long/${id}`, { method: 'PUT', body: JSON.stringify(p) }),
  deleteLongMemory: (id: string) => request(`/memory/long/${id}`, { method: 'DELETE' }),
  // Skill 市场
  listSkills: () => request('/skills'),
  installSkill: (id: string) => request(`/skills/${id}/install`, { method: 'POST' }),
  uninstallSkill: (id: string) => request(`/skills/${id}/install`, { method: 'DELETE' }),
  // 户型（HITL）
  parseHouse: () => request('/house/parse', { method: 'POST' }),
  confirmHouse: (taskId: string, houseStruct: object) =>
    request(`/house/parse/${taskId}/confirm`, {
      method: 'POST',
      body: JSON.stringify({ house_struct: houseStruct }),
    }),
  // 任务中心（统一异步任务：11.1 status/stream/cancel）
  listTasks: () => request('/tasks'),
  taskStatus: (id: string) => request(`/tasks/${id}/status`),
  // SSE 任务完成推送（fetch 携带 token，调用方按 event 流解析）
  taskStream: (id: string) =>
    fetch(`${BASE}/tasks/${id}/stream`, {
      headers: { Authorization: `Bearer ${sessionStorage.getItem('reai_token') ?? ''}` },
    }),
  deleteTask: (id: string) => request(`/tasks/${id}`, { method: 'DELETE' }),
  cancelTask: (id: string) => request(`/tasks/${id}/cancel`, { method: 'POST' }),
  retryTask: (id: string) => request(`/tasks/${id}/retry`, { method: 'POST' }),
  // 知识库批量导入（异步任务，返回 task_id + poll_url）
  batchImport: (files: File[], gov?: DocumentGovernance) => {
    const fd = new FormData();
    files.forEach(f => fd.append('files', f));
    appendGov(fd, gov);
    return request('/documents/batch-import', { method: 'POST', body: fd });
  },
  // Skill 调用（SSE 流式）
  invokeSkill: (id: string, input: string) =>
    fetch(`${BASE}/skills/${id}/invoke`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${sessionStorage.getItem('reai_token') ?? ''}`,
      },
      body: JSON.stringify({ input }),
    }),
  // 断点续聊恢复（SSE，与 chat 同协议）
  resumeSession: (threadId: string, content: string) =>
    fetch(`${BASE}/sessions/${threadId}/resume`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${sessionStorage.getItem('reai_token') ?? ''}`,
      },
      body: JSON.stringify({ content }),
    }),
  // AI 空间智能引擎 · 一键装修图：multipart 表单（毛坯房照片 + 家具/墙色/地面 → 图生图；不传照片走文生图）
  renderGenerate: (form: FormData) => request('/render/generate', { method: 'POST', body: form }),
  renderStatus: (taskId: string) => request(`/render/${taskId}`),
  // 成图为二进制 PNG：必须走 fetch + blob，不能走统一 JSON 信封解析
  renderDownload: async (taskId: string): Promise<Blob> => {
    const res = await fetch(`${BASE}/render/${taskId}/download`, {
      headers: { Authorization: `Bearer ${sessionStorage.getItem('reai_token') ?? ''}` },
    });
    if (!res.ok) throw Object.assign(new Error(`下载失败（HTTP ${res.status}）`), { code: 5000 });
    return res.blob();
  },
  // 生图历史记录（持久化，支持分页与风格/模式过滤）
  renderHistory: (p?: { page?: number; page_size?: number; style?: string; mode?: string }) => {
    const q = new URLSearchParams(
      Object.entries(p ?? {}).filter(([, v]) => v != null && v !== '') as [string, string][]
    );
    return request(`/render/history${q.size ? `?${q}` : ''}`);
  },
  renderDeleteHistory: (taskId: string) =>
    request(`/render/history/${taskId}`, { method: 'DELETE' }),
  // 业主家具清单库：分类/条目 CRUD + 粘贴/拍照 AI 解析（数据源与渲染层一致）
  furnitureCatalog: () => request('/furniture/catalog'),
  furnitureAddCategory: (name: string) =>
    request('/furniture/categories', { method: 'POST', body: JSON.stringify({ name }) }),
  furnitureDeleteCategory: (id: string) =>
    request(`/furniture/categories/${id}`, { method: 'DELETE' }),
  furnitureAddItem: (p: { name: string; category: string; en?: string; aliases?: string[] }) =>
    request('/furniture/items', { method: 'POST', body: JSON.stringify(p) }),
  furnitureUpdateItem: (
    id: string,
    p: { name?: string; en?: string; aliases?: string[]; category?: string }
  ) => request(`/furniture/items/${id}`, { method: 'PUT', body: JSON.stringify(p) }),
  furnitureDeleteItem: (id: string) => request(`/furniture/items/${id}`, { method: 'DELETE' }),
  furnitureParse: (text: string, photo?: File) => {
    const fd = new FormData();
    fd.append('text', text);
    if (photo) fd.append('photo', photo);
    return request('/furniture/parse', { method: 'POST', body: fd });
  },
  // 管理端
  costStats: () => request('/cost/stats'),
  auditLogs: () => request('/audit/logs'),
  auditDetail: (id: string) => request(`/audit/logs/${id}/detail`),
  // 安全事件：提示注入命中与越权/时效拦截的问答（越权检测与告警依据）
  auditSecurity: () => request('/audit/security'),
  listUsers: () => request('/users'),
  createUser: (p: object) => request('/users', { method: 'POST', body: JSON.stringify(p) }),
  updateUser: (username: string, p: { role?: string; status?: string; reset_password?: boolean }) =>
    request(`/users/${encodeURIComponent(username)}`, { method: 'PUT', body: JSON.stringify(p) }),
  deleteUser: (username: string) =>
    request(`/users/${encodeURIComponent(username)}`, { method: 'DELETE' }),
  // Agent 工程化门面（后端 modules/agent）：统一事件协议 text/tool_call/tool_result/approval/error/done
  agentChat: (p: { query: string; session_id?: string }) =>
    request<{ answer: string; trace_id: string }>('/agent/chat', {
      method: 'POST',
      body: JSON.stringify({ session_id: 'default', ...p }),
    }),
  // Agent 流式（SSE，调用方按 event 流解析；与 chatStream 同源不同协议）
  agentChatStream: (p: { query: string; session_id?: string }) =>
    fetch(`${BASE}/agent/chat/stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${sessionStorage.getItem('reai_token') ?? ''}`,
      },
      body: JSON.stringify({ session_id: 'default', ...p }),
    }),
  // 工具注册中心：按当前用户权限过滤后返回可用工具
  listTools: () => request('/tools'),
  invokeTool: (name: string, args: object = {}, idempotency_key?: string) =>
    request(`/tools/${encodeURIComponent(name)}/invoke`, {
      method: 'POST',
      body: JSON.stringify({ args, idempotency_key }),
    }),
  // 知识检索/索引（RAG 独立服务门面；文档上传仍走 documents/upload）
  knowledgeSearch: (query: string, top_k = 5) =>
    request('/knowledge/search', { method: 'POST', body: JSON.stringify({ query, top_k }) }),
  knowledgeIndex: (doc_id: string, content = '') =>
    request('/knowledge/index', { method: 'POST', body: JSON.stringify({ doc_id, content }) }),
  // 人机协同审批（敏感工具调用暂停后，管理员批准/驳回）
  approveApproval: (id: string, modified_args?: object) =>
    request(`/approvals/${id}/approve`, {
      method: 'POST',
      body: JSON.stringify({ modified_args }),
    }),
  rejectApproval: (id: string) => request(`/approvals/${id}/reject`, { method: 'POST' }),
  // 评估门禁（黄金数据集回放 + 通过率）
  evalRun: (agent_version = 'dev') =>
    request('/eval/run', { method: 'POST', body: JSON.stringify({ agent_version }) }),
  // 治理视角：就绪检查与模型用量
  adminReady: () => request('/admin/ready'),
  adminUsage: () => request('/admin/usage'),
};
