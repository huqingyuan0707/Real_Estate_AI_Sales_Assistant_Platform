<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import { documents as mockDocuments } from '@/mock';
import AiButton from '@/components/AiButton/index.vue';
import AiInput from '@/components/AiInput/index.vue';
import { api } from '@/api';

/* ---------------- 文档列表（真实 API：知识库生产数据） ---------------- */
const rows = ref<any[]>([]);
const searchKw = ref('');
const filtered = computed(() =>
  searchKw.value ? rows.value.filter(r => r.name.includes(searchKw.value)) : rows.value
);
const stats = ref<any>(null);
let pollTimer: number | undefined;
let batchAbort: AbortController | undefined;

async function loadDocs() {
  try {
    rows.value = await api.listDocuments();
  } catch {
    rows.value = mockDocuments.map(d => ({ ...d })); // 后端不可用时回退演示数据
  }
}
async function loadStats() {
  try {
    stats.value = await api.documentStats();
  } catch {
    stats.value = null;
  }
}

/* ---------------- 知识治理标签（上传时标注，决定检索阶段可见范围） ---------------- */
const govOptions = ref<any>({ security_levels: [], review_status: [], depts: [] });
const govForm = reactive({
  security_level: 'internal',
  dept_id: '',
  review_status: 'published',
  effective_at: '',
  expire_at: '',
});
const GOV_LEVEL_TAG: Record<string, { text: string; type: string }> = {
  public: { text: '公开', type: 'success' },
  internal: { text: '内部', type: 'info' },
  confidential: { text: '机密', type: 'danger' },
};
function govPayload() {
  return {
    security_level: govForm.security_level,
    dept_id: govForm.dept_id,
    review_status: govForm.review_status,
    effective_at: govForm.effective_at,
    expire_at: govForm.expire_at,
  };
}
async function loadGovernance() {
  try {
    govOptions.value = (await api.documentGovernance()).options ?? {};
  } catch {
    /* 后端不可用时忽略 */
  }
}

/* ---------------- 知识运营看板（反馈闭环 + RAG 可观测指标） ---------------- */
const ops = ref<any>(null);
const opsOpen = ref(false);
async function loadOps() {
  try {
    ops.value = await api.feedbackStats();
  } catch {
    ops.value = null;
  }
}

/* ---------------- 治理与运维：质量校验 / 索引版本 / 增量同步 / 审核 ---------------- */
const quality = ref<any>(null);
const indexInfo = ref<any>(null);
const infraBusy = ref('');
const ISSUE_LABEL: Record<string, string> = {
  empty: '空文档/解析失败',
  expired: '已过期',
  stale: '长期未更新',
  unpublished: '草稿未发布',
  duplicate: '内容重复',
  missing_gov: '治理标签缺失',
};

async function loadQuality() {
  try {
    quality.value = await api.documentQuality();
  } catch {
    quality.value = null;
  }
}
async function loadIndex() {
  try {
    indexInfo.value = await api.indexVersions();
  } catch {
    indexInfo.value = null;
  }
}
async function runSync() {
  infraBusy.value = 'sync';
  try {
    const r: any = await api.documentSync();
    ElMessage.success(
      `增量同步完成：新增 ${r.added?.length ?? 0}、更新 ${r.updated?.length ?? 0}、未变更 ${r.unchanged ?? 0}`
    );
    loadDocs();
    loadStats();
    loadQuality();
    loadIndex();
  } catch (e: any) {
    ElMessage.error(e.message || '同步失败');
  } finally {
    infraBusy.value = '';
  }
}
async function rebuildIndex() {
  try {
    const { value } = await ElMessageBox.prompt(
      '换嵌入模型重建索引（留空 = 用当前模型重建）。重建前会自动快照，可随时回滚。',
      '重建索引',
      {
        inputPlaceholder: '如 BAAI/bge-base-zh-v1.5',
        confirmButtonText: '开始重建',
        cancelButtonText: '取消',
      }
    );
    infraBusy.value = 'rebuild';
    const r: any = await api.indexRebuild(value?.trim() || undefined);
    ElMessage.success(
      `${r.rebuilt ? `已用 ${r.embed_model} 重建 ${r.rebuilt} 个分块（快照 ${r.backup}）` : r.message || '无需重建'}`
    );
    loadIndex();
    loadStats();
  } catch (e: any) {
    if (e !== 'cancel') ElMessage.error(e.message || '重建失败');
  } finally {
    infraBusy.value = '';
  }
}
async function rollbackIndex() {
  const backups: any[] = indexInfo.value?.backups ?? [];
  if (!backups.length) {
    ElMessage.warning('暂无可用快照，先执行一次入库或重建');
    return;
  }
  try {
    const { value } = await ElMessageBox.prompt(
      `输入快照文件名回滚（最近：${backups
        .slice(0, 2)
        .map(b => b.name)
        .join('、')}）`,
      '回滚索引',
      { confirmButtonText: '回滚', cancelButtonText: '取消' }
    );
    infraBusy.value = 'rollback';
    const r: any = await api.indexRollback(value.trim());
    ElMessage.success(`已回滚 ${r.restored} 个分块（模型 ${r.embed_model}）`);
    loadIndex();
    loadStats();
  } catch (e: any) {
    if (e !== 'cancel') ElMessage.error(e.message || '回滚失败');
  } finally {
    infraBusy.value = '';
  }
}
async function reviewDoc(row: any, action: 'approve' | 'reject' | 'archive') {
  try {
    await api.reviewDocument(row.id, action);
    ElMessage.success(
      action === 'approve'
        ? '已发布，立即参与检索'
        : action === 'reject'
          ? '已打回草稿，退出检索'
          : '已归档，退出检索'
    );
    loadDocs();
    loadQuality();
  } catch (e: any) {
    ElMessage.error(e.message || '审核失败');
  }
}

onMounted(() => {
  loadDocs();
  loadStats();
  loadGovernance();
  loadOps();
  loadQuality();
  loadIndex();
});
onUnmounted(() => {
  pollTimer && clearInterval(pollTimer);
  batchAbort?.abort();
});

const statusMap: Record<string, { text: string; cls: string }> = {
  active: { text: '生效中', cls: 'st-active' },
  processing: { text: '处理中', cls: 'st-processing' },
  inactive: { text: '已失效', cls: 'st-inactive' },
};

function viewDoc(row: { name: string }) {
  ElMessage.info(`查看《${row.name}》（预览开发中）`);
}
function disableDoc(row: { name: string; status: string }) {
  ElMessageBox.confirm(`停用后《${row.name}》将不可被 AI 检索引用，确认停用？`, '停用文档', {
    type: 'warning',
    confirmButtonText: '停用',
    cancelButtonText: '取消',
  })
    .then(() => {
      row.status = 'inactive';
      ElMessage.success('已停用');
    })
    .catch(() => {});
}
/** 按源文件删除：删除 Chroma 全部向量块 + 注册表记录 */
async function deleteDoc(row: { name: string; chunks?: number }) {
  await ElMessageBox.confirm(
    `删除后《${row.name}》${row.chunks ? `（${row.chunks} 个向量块）` : ''}将从向量索引中移除且不可恢复，确认删除？`,
    '删除文档',
    { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' }
  )
    .then(async () => {
      try {
        await api.deleteDocument(row.name);
        rows.value = rows.value.filter(r => r.name !== row.name);
        loadStats();
        ElMessage.success('已删除');
      } catch (e: any) {
        ElMessage.error(e.message || '删除失败');
      }
    })
    .catch(() => {});
}

/* ---------------- 上传弹窗（规范 5.3：640×480，真实入库链） ---------------- */
const uploadVisible = ref(false);
const dragOver = ref(false);
const uploadList = reactive<{ name: string; size: string; state: string; file?: File }[]>([]);
const conflictDocName = ref('');
const fileInput = ref<HTMLInputElement>();

function openUpload() {
  uploadVisible.value = true;
}
function triggerPick() {
  fileInput.value?.click();
}
function onPick(e: Event) {
  const input = e.target as HTMLInputElement;
  if (input.files?.length) addFiles(Array.from(input.files));
  input.value = '';
}
function onDrop(e: DragEvent) {
  dragOver.value = false;
  const files = Array.from(e.dataTransfer?.files ?? []);
  if (files.length) addFiles(files);
}
function addFiles(files: File[]) {
  for (const f of files) {
    if (rows.value.some(r => r.name === f.name)) {
      conflictDocName.value = f.name;
      return;
    }
    uploadList.push({
      name: f.name,
      size: `${(f.size / 1024 / 1024).toFixed(1)} MB`,
      state: '等待上传',
      file: f,
    });
  }
}
async function doUpload() {
  const files = uploadList.filter(f => f.file).map(f => f.file!);
  // 多文件 → 批量导入异步任务（对齐技术方案 5.2 /documents/batch-import + 11.1 任务中心 SSE）
  if (files.length >= 2) {
    await doBatchImport(files);
    return;
  }
  for (const f of uploadList) {
    f.state = '上传入库中...';
    try {
      const res = await api.uploadDocument(f.file!, govPayload());
      if (res?.status === 'version_conflict') {
        conflictDocName.value = f.name;
        f.state = '⚠️ 同名冲突';
        continue;
      }
      if (res?.status === 'unsupported') {
        f.state = `❌ 不支持该格式`;
        continue;
      }
      f.state = '✅ 已提交解析';
    } catch (e: any) {
      f.state = `❌ ${e.message || '上传失败'}`;
    }
  }
  ElMessage.success('上传完成，文档正在解析入库（bge 向量化）');
  uploadVisible.value = false;
  loadDocs();
  // 轮询直到所有 processing 文档就绪
  let n = 0;
  pollTimer = window.setInterval(async () => {
    await loadDocs();
    if (!rows.value.some(r => r.status === 'processing') || ++n >= 12) {
      clearInterval(pollTimer);
      loadStats();
    }
  }, 5000);
}

/** 批量导入：一次提交异步任务，SSE 订阅 /tasks/{task_id}/stream 更新行内进度 */
async function doBatchImport(files: File[]) {
  uploadList.forEach(f => (f.state = '⏳ 已加入批量导入队列'));
  try {
    const res = await api.batchImport(files, govPayload());
    ElMessage.success(
      `批量导入任务已创建（共 ${res.total ?? files.length} 个文档，预计 ${res.estimated_seconds ?? files.length * 3}s）`
    );
    subscribeBatch(res.task_id);
  } catch (e: any) {
    uploadList.forEach(f => (f.state = `❌ ${e.message || '提交失败'}`));
    ElMessage.error(e.message || '批量导入提交失败');
  }
}

function subscribeBatch(taskId: string) {
  batchAbort?.abort();
  batchAbort = new AbortController();
  const signal = batchAbort.signal;
  (async () => {
    try {
      const res = await api.taskStream(taskId);
      const reader = res.body?.getReader();
      if (!reader) return;
      const dec = new TextDecoder();
      let buf = '';
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });
        const frames = buf.split('\n\n');
        buf = frames.pop() ?? '';
        for (const fr of frames) {
          const ev = /event: (.+)/.exec(fr)?.[1]?.trim();
          const data = /data: (.+)/.exec(fr)?.[1];
          if (!ev) continue;
          let payload: any = {};
          try {
            payload = data ? JSON.parse(data) : {};
          } catch {
            /* 非 JSON 帧忽略 */
          }
          if (ev === 'progress' && signal.aborted === false) {
            const pct = payload.progress ?? 0;
            uploadList.forEach(f => {
              if (!f.state.startsWith('✅') && !f.state.startsWith('❌'))
                f.state = `⚙️ 导入中 ${pct}%（${payload.phase ?? ''}）`;
            });
          } else if (ev === 'complete') {
            // 结果明细：items=成功清单 fail_items=失败清单
            const okItems: any[] = payload.result?.items ?? [];
            const badItems: any[] = payload.result?.fail_items ?? [];
            uploadList.forEach(f => {
              const ok1 = okItems.find((i: any) => i.name === f.name);
              const bad1 = badItems.find((i: any) => i.name === f.name);
              if (ok1) f.state = `✅ ${ok1.version} · ${ok1.chunks} 块`;
              else if (bad1) f.state = `❌ ${bad1.error}`;
              else f.state = '✅ 完成';
            });
            const s = payload.result?.success ?? 0;
            const fl = payload.result?.failed ?? 0;
            fl
              ? ElMessage.warning(`批量导入完成：成功 ${s} 个，失败 ${fl} 个`)
              : ElMessage.success(`批量导入完成：成功 ${s} 个文档`);
            uploadVisible.value = false;
            loadDocs();
            loadStats();
            return;
          } else if (ev === 'error') {
            uploadList.forEach(f => {
              if (!f.state.startsWith('✅')) f.state = `❌ ${payload.msg || '任务异常'}`;
            });
            ElMessage.error(payload.msg || '批量导入任务异常');
            return;
          }
        }
      }
    } catch {
      /* 页面离开或网络中断，任务仍在服务端继续 */
    }
  })();
}

/* ---------------- 版本冲突弹窗（规范 5.4：480px） ---------------- */
const conflictVisible = computed({
  get: () => !!conflictDocName.value,
  set: (v: boolean) => {
    if (!v) conflictDocName.value = '';
  },
});
const conflictChoice = ref<'cover' | 'keep'>('cover');
function confirmConflict() {
  const name = conflictDocName.value;
  conflictDocName.value = '';
  const item = uploadList.find(f => f.name === name);
  if (item) item.state = '⚠️ 同名冲突（请在服务端处理版本策略后重命名上传）';
  ElMessage.warning('同名文档已存在，建议重命名后重新上传');
}

/* ---------------- 试搜一下（真实检索：向量召回 + Rerank） ---------------- */
const tried = ref(false);
const trying = ref(false);
const tryResults = ref<any[]>([]);
async function trySearch() {
  if (!searchKw.value.trim()) {
    ElMessage.warning('请输入检索关键词');
    return;
  }
  tried.value = true;
  trying.value = true;
  try {
    tryResults.value = await api.searchDocuments(searchKw.value);
  } catch {
    tryResults.value = [];
  } finally {
    trying.value = false;
  }
}
</script>

<template>
  <div class="kb-page">
    <!-- 顶部操作栏 -->
    <div class="kb-toolbar">
      <h2 class="kb-title">知识库</h2>
      <AiButton type="primary" class="upload-btn" round @click="openUpload"> 📤 上传文档 </AiButton>
    </div>

    <!-- 知识库统计条：生产数据概览 -->
    <div v-if="stats" class="kb-stats">
      <span
        >📚 已索引 <b>{{ stats.doc_count }}</b> 个源文件</span
      >
      <span
        >🧩 向量块 <b>{{ stats.kb_chunks }}</b></span
      >
      <span>🔗 检索链：向量 + BM25 双路 → RRF → 重排</span>
      <span v-if="stats.governance?.by_level">
        密级：
        <b v-for="(n, lv) in stats.governance.by_level" :key="lv" class="kb-level">
          {{ GOV_LEVEL_TAG[lv]?.text || lv }} {{ n }}
        </b>
      </span>
    </div>

    <!-- 试搜引导卡片：独立浅色卡区 -->
    <div class="try-card">
      <div class="try-card-head">
        <div>
          <div class="try-card-title">🔍 试搜一下</div>
          <div class="try-card-sub">输入关键词，验证 AI 能否从知识库中命中答案</div>
        </div>
        <div class="try-search">
          <AiInput
            v-model="searchKw"
            placeholder="如：南北通透"
            style="width: 260px"
            :prefix-icon="'Search'"
            @keyup.enter="trySearch"
          />
          <AiButton type="primary" style="margin-left: 8px" @click="trySearch"> 试搜 </AiButton>
        </div>
      </div>
      <!-- 试搜结果（真实：bge-small-zh 召回 + bge-reranker 重排） -->
      <div v-if="tried" v-loading="trying" class="try-result">
        <div class="try-title">
          检索结果（向量 + BM25 双路召回 → RRF 融合 → 重排；已按你的可见范围过滤）
        </div>
        <div v-for="(r, i) in tryResults" :key="i" class="try-item">
          <div class="try-doc">
            📄 {{ r.doc
            }}<template v-if="r.section && r.section !== r.doc"> · {{ r.section }} </template> ·
            第{{ r.page }}页
            <span class="try-score">相关度 {{ r.score }}%</span>
            <span v-if="r.routes > 1" class="try-badge">双路命中</span>
            <span class="try-badge level">{{
              GOV_LEVEL_TAG[r.security_level]?.text || r.security_level
            }}</span>
          </div>
          <div class="try-snip">
            {{ r.snippet }}
          </div>
        </div>
        <div v-if="!trying && !tryResults.length" class="try-empty">
          未命中相关内容 —— 请上传更多文档或调整检索关键词
        </div>
        <AiButton text size="small" @click="tried = false"> 收起 </AiButton>
      </div>
    </div>

    <!-- 知识运营看板：反馈闭环（采纳率 / 差评知识 / 知识缺口）+ RAG 可观测指标 -->
    <div v-if="ops" class="ops-card">
      <div class="ops-head" @click="opsOpen = !opsOpen">
        <div class="ops-title">📈 知识运营看板</div>
        <div class="ops-kpis">
          <span class="ops-kpi"
            >采纳率 {{ ((ops.feedback?.adoption_rate ?? 0) * 100).toFixed(0) }}%</span
          >
          <span class="ops-kpi">拒答率 {{ ((ops.rag?.reject_rate ?? 0) * 100).toFixed(0) }}%</span>
          <span class="ops-kpi">平均耗时 {{ ops.rag?.avg_elapsed_ms ?? 0 }}ms</span>
          <span class="ops-toggle">{{ opsOpen ? '收起 ▲' : '展开 ▼' }}</span>
        </div>
      </div>
      <div v-show="opsOpen" class="ops-body">
        <div class="ops-block">
          <div class="ops-block-title">在线质量与安全</div>
          <div class="ops-line">
            问答次数：{{ ops.rag?.total ?? 0 }}（采纳 {{ ops.feedback?.up ?? 0 }} / 不采纳
            {{ ops.feedback?.down ?? 0 }}）
          </div>
          <div class="ops-line">平均召回片段：{{ ops.rag?.avg_recall ?? 0 }}</div>
          <div class="ops-line">治理拦截（越权/失效）：{{ ops.rag?.blocked_total ?? 0 }} 次</div>
          <div class="ops-line">提示注入告警：{{ ops.rag?.injection_alerts ?? 0 }} 次</div>
          <div class="ops-line">
            平均可信度 {{ ops.rag?.avg_faithfulness ?? '-' }}（低可信
            {{ ops.rag?.low_faith_count ?? 0 }} 次）
          </div>
          <div class="ops-line">
            缓存命中率 {{ Math.round((ops.cache?.hit_rate ?? 0) * 100) }}% · 限流
            {{ ops.ratelimit?.limit_per_min ?? 0 }} 次/分
          </div>
          <div class="ops-line">
            Token 估算 {{ ops.rag?.total_tokens ?? 0 }} · 成本 {{ ops.rag?.total_cost ?? 0 }} 元
          </div>
        </div>
        <div class="ops-block">
          <div class="ops-block-title">低质量知识（被点踩）</div>
          <template v-if="ops.feedback?.low_quality_docs?.length">
            <div v-for="d in ops.feedback.low_quality_docs" :key="d.doc" class="ops-line">
              ⚠️ {{ d.doc }}（👍{{ d.up }} / 👎{{ d.down }}）
            </div>
          </template>
          <div v-else class="ops-line ops-muted">暂无差评记录</div>
        </div>
        <div class="ops-block">
          <div class="ops-block-title">知识缺口（差评 / 拒答问题）</div>
          <template v-if="ops.feedback?.gap_queries?.length">
            <div v-for="(g, i) in ops.feedback.gap_queries.slice(0, 6)" :key="i" class="ops-line">
              · [{{ g.reason }}] {{ g.query }}
            </div>
          </template>
          <div v-else class="ops-line ops-muted">暂无缺口，知识覆盖良好</div>
        </div>
        <div class="ops-block">
          <div class="ops-block-title">🔥 知识热度（被引用次数）</div>
          <template v-if="ops.rag?.doc_heat?.length">
            <div v-for="h in ops.rag.doc_heat.slice(0, 6)" :key="h.doc" class="ops-line">
              · {{ h.doc }} —— {{ h.hits }} 次
            </div>
          </template>
          <div v-else class="ops-line ops-muted">暂无引用记录</div>
        </div>
      </div>
    </div>

    <!-- 治理与运维：质量校验 / 索引版本 / 增量同步 / 重建回滚 -->
    <div class="gov-ops">
      <div class="ops-block">
        <div class="ops-block-title">🧪 知识质量校验</div>
        <template v-if="quality">
          <div class="ops-line">
            健康度 <b>{{ Math.round((quality.health_score ?? 0) * 100) }}%</b> · 文档
            {{ quality.doc_count }} · 问题 {{ quality.issue_count }}
          </div>
          <div
            v-for="(items, key) in quality.issues"
            v-show="items && items.length"
            :key="key"
            class="ops-line"
          >
            {{ ISSUE_LABEL[key] || key }}：{{
              items
                .slice(0, 3)
                .map((i: any) => i.name)
                .join('、')
            }}<span v-if="items.length > 3"> 等 {{ items.length }} 项</span>
          </div>
          <div v-if="!quality.issue_count" class="ops-line ops-muted">未发现质量问题</div>
        </template>
        <div v-else class="ops-line ops-muted">暂无数据（上传文档后自动校验）</div>
      </div>
      <div class="ops-block">
        <div class="ops-block-title">🗂 索引版本与增量同步</div>
        <div class="ops-line">
          当前模型：{{ indexInfo?.current?.embed_model || stats?.embed_model }}
        </div>
        <div class="ops-line">
          分块 {{ indexInfo?.current?.chunks ?? stats?.kb_chunks }} · 版本 r{{
            indexInfo?.current?.revision ?? 0
          }}
          · 快照 {{ indexInfo?.backups?.length ?? 0 }} 个
        </div>
        <div class="ops-actions">
          <el-button size="small" :loading="infraBusy === 'sync'" @click="runSync">
            增量同步
          </el-button>
          <el-button size="small" :loading="infraBusy === 'rebuild'" @click="rebuildIndex">
            换模型重建
          </el-button>
          <el-button size="small" :loading="infraBusy === 'rollback'" @click="rollbackIndex">
            回滚
          </el-button>
        </div>
        <div class="ops-line ops-muted" style="margin-top: 8px">
          增量同步按 SHA256 指纹跳过未变更文件；重建前自动快照，可原样回滚。
        </div>
      </div>
    </div>

    <!-- 文档卡片列表 -->
    <div class="doc-list">
      <div v-for="row in filtered" :key="row.id" class="doc-item">
        <span class="doc-icon">📄</span>
        <div class="doc-main">
          <div class="doc-name">
            {{ row.name }}
          </div>
          <div class="doc-meta">
            {{ row.type }} · {{ row.size }} · {{ row.uploader }}
            <span v-if="row.security_level" class="doc-gov">{{
              GOV_LEVEL_TAG[row.security_level]?.text || row.security_level
            }}</span>
            <span v-if="row.dept_id" class="doc-gov">{{ row.dept_id }}</span>
            <span v-if="row.review_status === 'draft'" class="doc-gov draft">草稿·不参与检索</span>
          </div>
        </div>
        <span class="doc-status" :class="row.status">
          <i v-if="row.status === 'processing'" class="spinner" />
          <i v-else class="dot" />
          {{ statusMap[row.status].text }}
        </span>
        <span class="doc-ver">{{ row.version }}</span>
        <div class="doc-ops">
          <AiButton
            v-if="row.review_status === 'draft'"
            text
            type="primary"
            size="small"
            @click="reviewDoc(row, 'approve')"
          >
            ✅ 发布
          </AiButton>
          <AiButton
            v-else-if="row.review_status === 'published'"
            text
            size="small"
            style="color: var(--reai-text-muted)"
            @click="reviewDoc(row, 'archive')"
          >
            📦 归档
          </AiButton>
          <AiButton text type="primary" size="small" @click="viewDoc(row)"> 👁 查看 </AiButton>
          <AiButton
            text
            size="small"
            style="color: var(--reai-text-muted)"
            :disabled="row.status === 'inactive'"
            @click="disableDoc(row)"
          >
            ⏸ 停用
          </AiButton>
          <AiButton
            text
            size="small"
            style="color: var(--reai-danger, #d66)"
            @click="deleteDoc(row)"
          >
            🗑 删除
          </AiButton>
        </div>
      </div>
      <div v-if="!filtered.length" class="table-empty">
        <div class="empty-icon-sm">📚</div>
        <div>暂无内容</div>
        <div class="empty-sub-sm">点击右上角"上传文档"建立知识库</div>
      </div>
    </div>

    <!-- 上传弹窗 640×480 -->
    <el-dialog
      v-model="uploadVisible"
      title="上传文档"
      width="640px"
      class="upload-dialog"
      @closed="uploadList.length = 0"
    >
      <div
        class="drop-zone"
        :class="{ over: dragOver }"
        @dragover.prevent="dragOver = true"
        @dragleave="dragOver = false"
        @drop.prevent="onDrop"
        @click="triggerPick"
      >
        <div class="drop-icon">☁️</div>
        <div class="drop-main">拖拽文件至此，或点击选择文件</div>
        <div class="drop-sub">
          支持 PDF、Word、Excel、TXT、MD（≤50MB）；多文件将自动批量导入并可在任务中心查看进度
        </div>
        <input ref="fileInput" type="file" multiple hidden @change="onPick" />
      </div>
      <!-- 治理标注：写入分块元数据，检索阶段据此做权限与时效过滤 -->
      <div class="gov-form">
        <div class="gov-title">知识治理标注</div>
        <div class="gov-grid">
          <label class="gov-field">
            <span>密级</span>
            <el-select v-model="govForm.security_level" size="small" style="width: 100%">
              <el-option
                v-for="o in govOptions.security_levels"
                :key="o.value"
                :label="o.label"
                :value="o.value"
              />
            </el-select>
          </label>
          <label class="gov-field">
            <span>归属部门</span>
            <el-select
              v-model="govForm.dept_id"
              size="small"
              clearable
              placeholder="全公司可见"
              style="width: 100%"
            >
              <el-option v-for="d in govOptions.depts" :key="d" :label="d" :value="d" />
            </el-select>
          </label>
          <label class="gov-field">
            <span>审核状态</span>
            <el-select v-model="govForm.review_status" size="small" style="width: 100%">
              <el-option
                v-for="o in govOptions.review_status"
                :key="o.value"
                :label="o.label"
                :value="o.value"
              />
            </el-select>
          </label>
          <label class="gov-field">
            <span>生效 / 失效</span>
            <div class="gov-dates">
              <el-date-picker
                v-model="govForm.effective_at"
                type="date"
                size="small"
                value-format="YYYY-MM-DD"
                placeholder="生效日期"
                style="width: 100%"
              />
              <el-date-picker
                v-model="govForm.expire_at"
                type="date"
                size="small"
                value-format="YYYY-MM-DD"
                placeholder="失效日期"
                style="width: 100%"
              />
            </div>
          </label>
        </div>
        <div class="gov-tip">
          密级「机密」仅管理员可见；归属部门留空 =
          全公司可见；审核状态为「草稿」时该文档不参与检索。
        </div>
      </div>

      <div v-if="uploadList.length" class="upload-list">
        <div v-for="f in uploadList" :key="f.name" class="upload-item">
          <span class="up-name">📄 {{ f.name }}</span>
          <span class="up-size">{{ f.size }}</span>
          <span class="up-state" :class="{ done: f.state.includes('完成') }">{{ f.state }}</span>
        </div>
      </div>
      <template #footer>
        <AiButton @click="uploadVisible = false"> 取消 </AiButton>
        <AiButton type="primary" :disabled="!uploadList.length" @click="doUpload">
          确认上传
        </AiButton>
      </template>
    </el-dialog>

    <!-- 版本冲突弹窗 480px（二级，优先级更高） -->
    <el-dialog
      v-model="conflictVisible"
      title="⚠️ 检测到同名文档"
      width="480px"
      append-to-body
      :close-on-click-modal="false"
    >
      <p class="conflict-text">已存在文档"{{ conflictDocName }}"，请选择处理方式：</p>
      <el-radio-group v-model="conflictChoice" class="conflict-radios">
        <el-radio value="cover">
          覆盖旧版本<span class="radio-sub">（旧文档归档，不可恢复）</span>
        </el-radio>
        <el-radio value="keep">
          作为独立新文档保留<span class="radio-sub">（两个版本并存）</span>
        </el-radio>
      </el-radio-group>
      <template #footer>
        <AiButton @click="conflictVisible = false"> 取消 </AiButton>
        <AiButton type="primary" @click="confirmConflict"> 确认上传 </AiButton>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.kb-page {
  padding: 4px 8px 16px;
}
.kb-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}
.kb-title {
  font-size: 22px;
  font-weight: 700;
  color: var(--reai-text-main);
  margin: 0;
}
.upload-btn {
  height: 40px;
  font-weight: 600;
}

/* 知识库统计条 */
.kb-stats {
  display: flex;
  gap: 20px;
  align-items: center;
  font-size: 12px;
  color: var(--reai-text-muted);
  background: var(--reai-card);
  border-radius: 12px;
  padding: 10px 20px;
  margin-bottom: 16px;
  box-shadow: var(--reai-shadow-sm);
}
.kb-stats b {
  color: var(--reai-primary);
  font-weight: 700;
}

/* 试搜引导卡片 */
.try-card {
  background: var(--reai-card);
  border-radius: 14px;
  box-shadow: var(--reai-shadow-md);
  padding: 18px 20px;
  margin-bottom: 16px;
}
.try-card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
}
.try-card-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--reai-text-main);
}
.try-card-sub {
  font-size: 12px;
  color: var(--reai-text-muted);
  margin-top: 4px;
}
.try-search {
  display: flex;
  align-items: center;
}

.try-result {
  margin-top: 14px;
  border-top: 1px dashed var(--reai-border);
  padding-top: 14px;
}
.try-title {
  font-size: 12px;
  color: var(--reai-text-muted);
  margin-bottom: 10px;
}
.try-item {
  padding: 10px 12px;
  border-radius: 10px;
  margin-bottom: 8px;
  background: var(--reai-bg-neutral);
}
.try-doc {
  font-size: 14px;
  font-weight: 500;
  color: var(--reai-text-main);
}
.try-score {
  font-size: 11px;
  color: var(--reai-primary);
  background: var(--reai-primary-soft);
  border-radius: 9999px;
  padding: 2px 8px;
  margin-left: 8px;
}
.try-snip {
  font-size: 13px;
  color: var(--reai-text-muted);
  margin-top: 4px;
}
.try-snip :deep(em) {
  color: var(--reai-primary);
  font-style: normal;
  font-weight: 600;
}

/* 文档卡片列表：悬停浮起 */
.doc-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.doc-item {
  background: var(--reai-card);
  border-radius: 12px;
  padding: 14px 20px;
  display: flex;
  align-items: center;
  gap: 16px;
  box-shadow: var(--reai-shadow-sm);
  transition:
    box-shadow 0.2s,
    transform 0.2s;
}
.doc-item:hover {
  box-shadow: var(--reai-shadow-md);
  transform: translateY(-1px);
}
.doc-icon {
  font-size: 22px;
}
.doc-main {
  flex: 1;
  min-width: 0;
}
.doc-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--reai-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.doc-meta {
  font-size: 12px;
  color: var(--reai-text-muted);
  margin-top: 2px;
}

/* 状态：圆点+文字，无背景色 */
.doc-status {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  width: 76px;
  flex-shrink: 0;
}
.doc-status .dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  display: inline-block;
}
.doc-status.active {
  color: var(--st-active-fg);
}
.doc-status.active .dot {
  background: var(--reai-success);
}
.doc-status.processing {
  color: var(--st-warn-fg);
}
.doc-status.processing .dot {
  background: var(--reai-warning);
}
.doc-status.inactive {
  color: var(--st-off-fg);
}
.doc-status.inactive .dot {
  background: var(--reai-text-muted);
}
.doc-ver {
  font-size: 12px;
  color: var(--reai-text-muted);
  width: 32px;
  flex-shrink: 0;
}
.doc-ops {
  display: flex;
  align-items: center;
  flex-shrink: 0;
}
.spinner {
  width: 10px;
  height: 10px;
  border: 2px solid var(--reai-warning);
  border-top-color: transparent;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}
@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

.table-empty {
  padding: 32px 0;
}
.empty-icon-sm {
  font-size: 48px;
  margin-bottom: 8px;
}
.empty-sub-sm {
  font-size: 12px;
  color: var(--reai-text-muted);
  margin-top: 4px;
}

/* 上传弹窗 */
.drop-zone {
  border: 2px dashed var(--reai-border);
  border-radius: 14px;
  height: 240px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition:
    border-color 0.2s,
    background 0.2s;
}
.drop-zone.over {
  border-color: var(--reai-primary);
  background: var(--reai-primary-soft);
}
.drop-icon {
  font-size: 48px;
}
.drop-main {
  font-size: 16px;
  color: var(--reai-text-main);
  margin-top: 12px;
}
.drop-sub {
  font-size: 12px;
  color: var(--reai-text-muted);
  margin-top: 6px;
}
.upload-list {
  margin-top: 16px;
}
.upload-item {
  display: flex;
  align-items: center;
  height: 36px;
  font-size: 13px;
  gap: 12px;
}
.up-name {
  flex: 1;
  color: var(--reai-text-main);
}
.up-size {
  color: var(--reai-text-muted);
}
.up-state {
  color: var(--reai-text-muted);
}
.up-state.done {
  color: var(--reai-success);
}

/* 版本冲突 */
.conflict-text {
  font-size: 14px;
  color: var(--reai-text-main);
}
.conflict-radios {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.radio-sub {
  color: var(--reai-text-muted);
  font-size: 12px;
}

/* 治理标签 */
.kb-level {
  margin-right: 6px;
}
.doc-gov {
  display: inline-block;
  margin-left: 6px;
  font-size: 11px;
  padding: 1px 8px;
  color: var(--reai-primary);
  background: var(--reai-primary-soft);
  border-radius: 9999px;
}
.doc-gov.draft {
  color: var(--reai-warning);
  background: rgba(230, 162, 60, 0.14);
}
.try-badge {
  font-size: 11px;
  color: var(--reai-text-secondary);
  background: var(--reai-bg-gray);
  border-radius: 9999px;
  padding: 2px 8px;
  margin-left: 6px;
}
.try-badge.level {
  color: var(--reai-primary);
  background: var(--reai-primary-soft);
}

/* 知识运营看板 */
.ops-card {
  background: var(--reai-card);
  border-radius: 14px;
  box-shadow: var(--reai-shadow-sm);
  margin-bottom: 16px;
  overflow: hidden;
}
.ops-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 20px;
  cursor: pointer;
}
.ops-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--reai-text-main);
}
.ops-kpis {
  display: flex;
  align-items: center;
  gap: 14px;
  flex-wrap: wrap;
}
.ops-kpi {
  font-size: 12px;
  color: var(--reai-text-secondary);
}
.ops-toggle {
  font-size: 12px;
  color: var(--reai-primary);
}
.ops-body {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  padding: 0 20px 16px;
}
.ops-block {
  background: var(--reai-bg-neutral);
  border-radius: 10px;
  padding: 12px 14px;
}
.ops-block-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--reai-text-main);
  margin-bottom: 8px;
}
.ops-line {
  font-size: 12px;
  color: var(--reai-text-secondary);
  line-height: 1.9;
  word-break: break-all;
}
.ops-muted {
  color: var(--reai-text-muted);
}
@media (max-width: 900px) {
  .ops-body {
    grid-template-columns: 1fr;
  }
}

/* 治理与运维 */
.gov-ops {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  margin-bottom: 16px;
}
.gov-ops .ops-block {
  background: var(--reai-card);
  box-shadow: var(--reai-shadow-sm);
}
.ops-actions {
  display: flex;
  gap: 8px;
  margin-top: 10px;
  flex-wrap: wrap;
}
@media (max-width: 900px) {
  .gov-ops {
    grid-template-columns: 1fr;
  }
}

/* 上传弹窗内的治理标注 */
.gov-form {
  margin-top: 16px;
  border-top: 1px dashed var(--reai-border);
  padding-top: 14px;
}
.gov-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--reai-text-main);
  margin-bottom: 10px;
}
.gov-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px 16px;
}
.gov-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.gov-field > span {
  font-size: 12px;
  color: var(--reai-text-secondary);
}
.gov-dates {
  display: flex;
  gap: 8px;
}
.gov-tip {
  font-size: 11px;
  color: var(--reai-text-muted);
  margin-top: 10px;
  line-height: 1.7;
}
</style>
