<script setup lang="ts">
import PageHero from '@/components/PageHero/index.vue';
/**
 * 审计日志页：真实 RAG 审计（谁、何时、问了什么、看了哪些知识）+ 安全事件视图。
 * 数据源 /audit/logs（真实问答审计在前，演示历史数据在后）与 /audit/security（注入命中与越权拦截）。
 */
import { computed, onMounted, ref } from 'vue';
import { ElMessage } from 'element-plus';

import AiInput from '@/components/AiInput/index.vue';
import { api } from '@/api';

/* ---------------- 审计日志 ---------------- */
const logs = ref<any[]>([]);
const loading = ref(false);
const filterUser = ref('');
const keyword = ref('');
const userOptions = computed(
  () => [...new Set(logs.value.map(l => l.user).filter(Boolean))] as string[]
);

const loadLogs = async () => {
  loading.value = true;
  try {
    const rows = await api.auditLogs();
    logs.value = Array.isArray(rows) ? rows : [];
  } catch (e: any) {
    ElMessage.error(e.message || '加载审计日志失败');
  } finally {
    loading.value = false;
  }
};

const filtered = computed(() =>
  logs.value.filter(l => {
    if (filterUser.value && l.user !== filterUser.value) return false;
    const kw = keyword.value.trim();
    if (!kw) return true;
    return `${l.query || ''}${l.action || ''}${l.user || ''}`.includes(kw);
  })
);

/* ---------------- 安全事件：提示注入命中 / 越权与时效拦截 ---------------- */
const security = ref<any>({ total: 0, events: [] });
const securityOpen = ref(true);
const loadSecurity = async () => {
  try {
    security.value = await api.auditSecurity();
  } catch {
    /* 后端不可用时静默 */
  }
};
onMounted(() => {
  loadLogs();
  loadSecurity();
});

const blockedText = (row: any) => {
  const reasons = row.blocked_reasons || [];
  return reasons.length ? reasons.join('、') : `${row.blocked} 条`;
};
const injectionText = (flags: any[]) => {
  return (flags || [])
    .map(f => (f.flags || []).join('、'))
    .filter(Boolean)
    .join('；');
};

/* ---------------- 详情抽屉 ---------------- */
const drawerVisible = ref(false);
const currentLog = ref<any>(null);
const detail = ref<any>(null);
const openDetail = async (row: any) => {
  currentLog.value = row;
  detail.value = null;
  drawerVisible.value = true;
  try {
    detail.value = await api.auditDetail(row.id);
  } catch {
    /* 用列表行数据兜底渲染 */
  }
};
</script>

<template>
  <div class="audit-page">
    <PageHero
      index="08"
      title="审计日志"
      sub="全量对话追溯 · 安全事件告警 · 费用明细"
      :tags="[
        { text: '合规审计', kind: 'blue' },
        { text: '哈希存证', kind: 'purple' },
      ]"
    />
    <!-- 安全事件：注入命中与越权/时效拦截（越权检测与告警依据） -->
    <div v-if="security.total || security.events?.length" class="sec-card">
      <div class="sec-head" @click="securityOpen = !securityOpen">
        <span class="sec-title">🛡 安全事件（{{ security.total }}）</span>
        <span class="sec-toggle">{{ securityOpen ? '收起 ▲' : '展开 ▼' }}</span>
      </div>
      <div v-show="securityOpen" class="sec-body">
        <div v-if="!security.events?.length" class="sec-empty">未捕获提示注入或越权拦截事件</div>
        <div v-for="(e, i) in security.events" :key="i" class="sec-item">
          <span class="sec-time">{{ e.time }}</span>
          <span class="sec-user">{{ e.user }}</span>
          <span v-if="e.injection_flags?.length" class="sec-tag warn"
            >注入：{{ injectionText(e.injection_flags) }}</span
          >
          <span v-if="e.blocked" class="sec-tag">拦截：{{ blockedText(e) }}</span>
          <span class="sec-query">{{ e.query }}</span>
        </div>
      </div>
    </div>

    <!-- 筛选栏 -->
    <div class="filter-bar">
      <AiInput
        v-model="keyword"
        placeholder="按问题 / 操作 / 用户搜索"
        style="width: 260px"
        :prefix-icon="'Search'"
        clearable
      />
      <el-select v-model="filterUser" placeholder="全部用户" clearable style="width: 160px">
        <el-option v-for="u in userOptions" :key="u" :label="u" :value="u" />
      </el-select>
      <el-button type="primary" style="height: 40px" @click="loadLogs"> 刷新 </el-button>
      <span class="filter-tip">共 {{ filtered.length }} 条（真实问答审计在前，演示数据在后）</span>
    </div>

    <!-- 表格：首屏骨架，刷新时保留旧数据不闪 -->
    <div class="fashion-card" style="padding: 10px 10px 6px">
    <el-skeleton :loading="loading && !filtered.length" animated>
      <template #default>
    <el-table
      :data="filtered"
        class="audit-table"
        :header-cell-style="{
          background: '#F8FAFC',
          color: '#64748B',
          fontSize: '12px',
          height: '44px',
        }"
        :row-style="{ height: '52px', fontSize: '14px' }"
      >
        <el-table-column prop="time" label="操作时间" width="170" />
        <el-table-column prop="user" label="用户" width="100" />
        <el-table-column prop="action" label="操作类型" width="180" />
        <el-table-column prop="skill" label="关联 Skill" width="130" />
        <el-table-column label="问题 / 命中文档" min-width="260">
          <template #default="{ row }">
            <div v-if="row.query" class="cell-query">
              {{ row.query }}
            </div>
            <div v-if="row.docs?.length" class="cell-docs">📄 {{ row.docs.join('、') }}</div>
            <span v-if="!row.query" class="cell-muted">-</span>
          </template>
        </el-table-column>
        <el-table-column label="安全" width="120">
          <template #default="{ row }">
            <el-tag v-if="row.security" type="warning" size="small" effect="plain">
              拦截/告警
            </el-tag>
            <span v-else-if="row.rejected" class="cell-muted">拒答</span>
            <span v-else class="cell-muted">-</span>
          </template>
        </el-table-column>
        <el-table-column label="费用消耗(元)" width="120">
          <template #default="{ row }"> ¥{{ Number(row.cost || 0).toFixed(2) }} </template>
        </el-table-column>
        <el-table-column label="操作" width="100">
          <template #default="{ row }">
            <el-button text type="primary" size="small" @click="openDetail(row)">
              查看详情
            </el-button>
          </template>
        </el-table-column>
      </el-table>
      </template>
    </el-skeleton>
    </div>

    <!-- 详情抽屉 480px -->
    <el-drawer v-model="drawerVisible" title="操作详情" size="480px">
      <template v-if="currentLog">
        <div class="detail-meta">
          <div class="meta-row">
            <span class="meta-label">用户</span
            ><span
              >{{ currentLog.user
              }}<template v-if="currentLog.role">（{{ currentLog.role }}）</template></span
            >
          </div>
          <div class="meta-row">
            <span class="meta-label">时间</span><span>{{ currentLog.time }}</span>
          </div>
          <div class="meta-row">
            <span class="meta-label">操作</span
            ><span>{{ currentLog.action }} · {{ currentLog.skill }}</span>
          </div>
          <div v-if="currentLog.trace_id" class="meta-row">
            <span class="meta-label">Trace</span><span>{{ currentLog.trace_id }}</span>
          </div>
          <div v-if="currentLog.elapsed_ms" class="meta-row">
            <span class="meta-label">耗时</span><span>{{ currentLog.elapsed_ms }} ms</span>
          </div>
          <div class="meta-row">
            <span class="meta-label">费用</span
            ><span>¥{{ Number(currentLog.cost || 0).toFixed(2) }}</span>
          </div>
        </div>

        <div v-if="currentLog.query" class="raw-block">
          <div class="raw-label">用户提问</div>
          <div class="raw-content">
            {{ currentLog.query }}
          </div>
        </div>

        <div v-if="currentLog.docs?.length" class="raw-block">
          <div class="raw-label">命中知识（可追溯）</div>
          <template v-if="currentLog.hits?.length">
            <div v-for="(h, i) in currentLog.hits" :key="i" class="raw-content">
              · {{ h.doc }} 第{{ h.page }}页 · 相关度 {{ Math.round((h.score || 0) * 100) }}%
            </div>
          </template>
          <div v-else class="raw-content">
            {{ currentLog.docs.join('、') }}
          </div>
        </div>

        <div v-if="currentLog.blocked" class="raw-block">
          <div class="raw-label">治理拦截</div>
          <div class="raw-content">
            {{ blockedText(currentLog) }}
          </div>
        </div>

        <div v-if="currentLog.injection_flags?.length" class="raw-block">
          <div class="raw-label">提示注入告警</div>
          <div class="raw-content warn-text">
            {{ injectionText(currentLog.injection_flags) }}
          </div>
        </div>

        <div class="dialog-raw">
          <div v-for="(m, i) in detail?.dialog || []" :key="i" class="raw-item">
            <div class="raw-role">
              {{ m.role === 'user' ? '👤 用户' : '🤖 AI' }}
            </div>
            <div class="raw-content">
              {{ m.content }}
            </div>
          </div>
        </div>
      </template>
    </el-drawer>
  </div>
</template>

<style scoped>
.audit-page {
  padding: 0;
}

/* 安全事件卡片 */
.sec-card {
  background: #fff7ed;
  border: 1px solid #fed7aa;
  border-radius: 12px;
  margin-bottom: 16px;
  overflow: hidden;
}
.sec-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  cursor: pointer;
}
.sec-title {
  font-size: 14px;
  font-weight: 600;
  color: #9a3412;
}
.sec-toggle {
  font-size: 12px;
  color: #9a3412;
}
.sec-body {
  padding: 0 16px 12px;
}
.sec-empty {
  font-size: 12px;
  color: var(--reai-text-muted);
}
.sec-item {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 12px;
  padding: 6px 0;
  border-top: 1px dashed #fed7aa;
  flex-wrap: wrap;
}
.sec-time {
  color: var(--reai-text-muted);
}
.sec-user {
  color: var(--reai-text-main);
  font-weight: 500;
}
.sec-tag {
  background: #ffedd5;
  color: #9a3412;
  border-radius: 9999px;
  padding: 1px 8px;
}
.sec-tag.warn {
  background: #fee2e2;
  color: #991b1b;
}
.sec-query {
  color: var(--reai-text-secondary);
  word-break: break-all;
}

/* 筛选区 */
.filter-bar {
  display: flex;
  gap: 12px;
  align-items: center;
  background: var(--reai-bg-gray);
  border-radius: 12px;
  padding: 12px 16px;
  margin-bottom: 16px;
}
.filter-tip {
  font-size: 12px;
  color: var(--reai-text-muted);
  margin-left: auto;
}
.audit-table {
  width: 100%;
}
.audit-table :deep(.el-table__row:hover > td) {
  background: var(--reai-bg-neutral) !important;
}
.cell-query {
  font-size: 13px;
  color: var(--reai-text-main);
}
.cell-docs {
  font-size: 12px;
  color: var(--reai-text-muted);
  margin-top: 2px;
}
.cell-muted {
  font-size: 12px;
  color: var(--reai-text-muted);
}

.detail-meta {
  background: var(--reai-bg-neutral);
  border-radius: 8px;
  padding: 12px 16px;
  margin-bottom: 16px;
}
.meta-row {
  display: flex;
  font-size: 13px;
  padding: 4px 0;
  color: var(--reai-text-main);
}
.meta-label {
  width: 56px;
  color: var(--reai-text-muted);
}

.raw-block {
  background: var(--reai-bg-neutral);
  border-radius: 8px;
  padding: 12px 16px;
  margin-bottom: 12px;
}
.raw-label {
  font-size: 12px;
  color: var(--reai-text-muted);
  margin-bottom: 6px;
}
.raw-content {
  font-size: 13px;
  line-height: 1.7;
  color: var(--reai-text-main);
  white-space: pre-wrap;
  word-break: break-all;
}
.warn-text {
  color: #991b1b;
}

.dialog-raw {
  background: var(--reai-bg-neutral);
  border-radius: 8px;
  padding: 16px;
  font-family: Consolas, 'Courier New', monospace;
}
.raw-item {
  margin-bottom: 16px;
}
.raw-role {
  font-size: 12px;
  color: var(--reai-text-muted);
  margin-bottom: 6px;
}
</style>
