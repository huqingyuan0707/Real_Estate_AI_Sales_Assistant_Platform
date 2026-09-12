<script setup lang="ts">
import { computed, onBeforeUnmount, reactive, ref } from 'vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import { tasks as mockTasks } from '@/mock';
import { api } from '@/api';
import AiButton from '@/components/AiButton/index.vue';

/* ---------------- 任务列表（后端统一异步任务中心：真实任务 + 演示种子） ---------------- */
const list = reactive<any[]>([]);
const loading = ref(false);

function normalize(t: any) {
  return {
    id: t.id,
    taskType: t.task_type ?? '',
    name: t.name,
    submittedAt: t.submitted_at ?? t.submittedAt ?? '',
    progress: t.progress ?? 0,
    status: t.status ?? 'queued',
    phase: t.phase ?? '',
    result: t.result ?? null,
    error: t.error ?? null,
    real: !!t.real,
  };
}

async function load() {
  loading.value = true;
  try {
    const data: any[] = await api.listTasks();
    list.splice(0, list.length, ...data.map(normalize));
  } catch {
    // 后端不可达：回退演示数据
    list.splice(0, list.length, ...mockTasks.map(t => ({ ...normalize(t), real: false })));
  } finally {
    loading.value = false;
  }
  subscribeRunning();
}

/* ---------------- 运行中任务 SSE 订阅（11.1.5 完成推送，替代被动轮询） ---------------- */
const streams = new Map<string, AbortController>();

function subscribeRunning() {
  for (const t of list) {
    if (t.real && (t.status === 'running' || t.status === 'queued') && !streams.has(t.id)) {
      watch(t.id);
    }
  }
}

async function watch(taskId: string) {
  const ctrl = new AbortController();
  streams.set(taskId, ctrl);
  try {
    const res = await api.taskStream(taskId);
    if (!res.body) return;
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buf = '';
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      const frames = buf.split('\n\n');
      buf = frames.pop() ?? '';
      for (const frame of frames) {
        const ev = /event: (.+)/.exec(frame)?.[1] ?? '';
        const data = /data: (.+)/.exec(frame)?.[1] ?? '';
        if (!data) continue;
        const payload = JSON.parse(data);
        if (ev === 'progress') {
          const row = list.find(x => x.id === taskId);
          if (row) {
            row.status = payload.status;
            row.progress = payload.progress;
            row.phase = payload.phase;
          }
        } else if (ev === 'complete') {
          ElMessage.success(`任务「${payload.name ?? taskId}」已完成`);
          streams.delete(taskId);
          load();
          return;
        } else if (ev === 'error') {
          ElMessage.warning(payload.msg ?? '任务推送中断');
          streams.delete(taskId);
          load();
          return;
        }
      }
    }
  } catch {
    /* 断连静默：下次 load 重挂 */
  } finally {
    streams.delete(taskId);
  }
}

onBeforeUnmount(() => streams.forEach(c => c.abort()));

/* ---------------- 统计卡片（规范 7.1） ---------------- */
const stats = computed(() => ({
  running: list.filter(t => t.status === 'running' || t.status === 'queued').length,
  done: list.filter(t => t.status === 'done').length,
  failed: list.filter(t => t.status === 'failed').length,
}));

const statusMeta: Record<string, { icon: string; text: string; cls: string }> = {
  running: { icon: '⏳', text: '执行中', cls: 'st-running' },
  queued: { icon: '⏳', text: '排队中', cls: 'st-running' },
  done: { icon: '✅', text: '已完成', cls: 'st-done' },
  failed: { icon: '❗', text: '失败', cls: 'st-failed' },
  cancelled: { icon: '🚫', text: '已取消', cls: 'st-cancelled' },
};

/* ---------------- 结果弹窗（规范 7.3：800px） ---------------- */
const resultVisible = ref(false);
const resultTask = ref<any>(null);
function viewResult(t: any) {
  resultTask.value = t;
  resultVisible.value = true;
}
function download(file: string) {
  ElMessage.success(`开始下载 ${file}（演示）`);
}

async function cancelTask(t: any) {
  try {
    await ElMessageBox.confirm('取消后任务停止执行且不可恢复，确认取消？', '取消任务', {
      type: 'warning',
      confirmButtonText: '取消任务',
      cancelButtonText: '返回',
    });
  } catch {
    return;
  }
  if (t.real) {
    try {
      await api.deleteTask(t.id);
      streams.get(t.id)?.abort();
      streams.delete(t.id);
      t.status = 'cancelled';
      ElMessage.success('任务已取消');
    } catch (e: any) {
      ElMessage.error(e?.message ?? '取消失败');
    }
  } else {
    list.splice(list.indexOf(t), 1);
    ElMessage.success('任务已取消');
  }
}

async function retryTask(t: any) {
  if (t.real) {
    try {
      await api.retryTask(t.id);
      ElMessage.info('已按原参数重新提交');
      load();
    } catch (e: any) {
      ElMessage.error(e?.message ?? '重试失败');
    }
  } else {
    t.status = 'running';
    t.progress = 5;
    ElMessage.info('已重新提交任务（演示）');
  }
}

load();
</script>

<template>
  <div class="task-page">
    <!-- 统计卡片 3列 -->
    <div class="stat-row">
      <div class="stat-card">
        <div class="stat-num">
          {{ stats.running }}
        </div>
        <div class="stat-label">进行中</div>
      </div>
      <div class="stat-card">
        <div class="stat-num" style="color: #059669">
          {{ stats.done }}
        </div>
        <div class="stat-label">已完成</div>
      </div>
      <div class="stat-card">
        <div class="stat-num" style="color: #ef4444">
          {{ stats.failed }}
        </div>
        <div class="stat-label">失败</div>
      </div>
    </div>

    <!-- 任务列表（卡片式） -->
    <div v-loading="loading" class="task-list">
      <div
        v-for="t in list"
        :key="t.id"
        class="task-row"
        :class="{ dim: t.status === 'cancelled' }"
      >
        <span class="task-status-icon" :class="statusMeta[t.status]?.cls">
          <span v-if="t.status === 'running'" class="spinner" />
          <template v-else>{{ statusMeta[t.status]?.icon }}</template>
        </span>
        <div class="task-main">
          <div class="task-name">
            {{ t.name }}
            <span v-if="t.taskType" class="task-type">{{ t.taskType }}</span>
          </div>
          <div v-if="t.error" class="task-error">
            {{ t.error }}
          </div>
          <div v-else-if="t.phase && t.status === 'running'" class="task-phase">
            {{ t.phase }}
          </div>
        </div>
        <span class="task-time">{{ t.submittedAt }}</span>
        <div class="task-progress">
          <div class="progress-track">
            <div class="progress-fill" :style="{ width: t.progress + '%' }" />
          </div>
          <span class="progress-text">{{ t.progress }}%</span>
        </div>
        <span class="task-status-text" :class="statusMeta[t.status]?.cls">{{
          statusMeta[t.status]?.text
        }}</span>
        <div class="task-ops">
          <AiButton
            v-if="t.status === 'running' || t.status === 'queued'"
            text
            size="small"
            style="color: #ef4444"
            @click="cancelTask(t)"
          >
            取消任务
          </AiButton>
          <AiButton
            v-if="t.status === 'done'"
            text
            type="primary"
            size="small"
            @click="viewResult(t)"
          >
            查看结果
          </AiButton>
          <AiButton
            v-if="t.status === 'failed'"
            text
            type="primary"
            size="small"
            @click="retryTask(t)"
          >
            🔄 重新尝试
          </AiButton>
        </div>
      </div>

      <!-- 空状态 -->
      <div v-if="!list.length && !loading" class="empty-state">
        <div class="empty-icon">⏳</div>
        <div class="empty-title">暂无内容</div>
        <div class="empty-sub">在对话中 @ 效果图渲染 或批量导入即可创建异步任务</div>
      </div>
    </div>

    <!-- 查看结果弹窗 800px -->
    <el-dialog v-model="resultVisible" title="任务结果" width="800px">
      <template v-if="resultTask">
        <!-- 效果图类结果（真实成图） -->
        <div v-if="resultTask.taskType === 'effect_render'" class="result-img-wrap">
          <img
            v-if="resultTask.result?.image_url"
            class="result-img"
            :src="resultTask.result.image_url"
            alt="效果图"
          />
          <div v-else class="demo-render">
            <span style="font-size: 48px">🖼️</span>
            <div style="color: #64748b; margin-top: 8px">演示模式无实体成图</div>
          </div>
          <div style="text-align: center; margin-top: 12px">
            <AiButton
              v-if="resultTask.result?.image_url"
              type="primary"
              @click="download(resultTask.result.image_url)"
            >
              下载高清图
            </AiButton>
          </div>
        </div>
        <!-- 批量导入类结果（真实汇总） -->
        <div v-else-if="resultTask.taskType === 'batch_import'" class="result-import">
          <div class="import-line">
            <span
              >✅ 成功导入
              <b style="color: #059669">{{ resultTask.result?.success ?? 0 }}</b> 份，</span
            >
            <span
              >❌ 失败 <b style="color: #ef4444">{{ resultTask.result?.failed ?? 0 }}</b> 份</span
            >
          </div>
          <div
            v-for="(f, i) in resultTask.result?.items ?? []"
            :key="'ok' + i"
            class="import-item ok"
          >
            {{ f.name }} · {{ f.version }} · {{ f.chunks }} 块
          </div>
          <div
            v-for="(f, i) in resultTask.result?.fail_items ?? []"
            :key="'bad' + i"
            class="import-item bad"
          >
            {{ f.name }} · {{ f.error }}
          </div>
        </div>
        <!-- 演示任务 -->
        <div v-else class="result-import">
          <div class="import-line">
            <span
              >✅ 成功导入
              <b style="color: #059669">{{ resultTask.result?.success ?? 0 }}</b> 条，</span
            >
            <span
              >❌ 失败 <b style="color: #ef4444">{{ resultTask.result?.failed ?? 0 }}</b> 条</span
            >
          </div>
          <AiButton type="primary" plain @click="download('失败明细.csv')">
            下载失败明细.csv
          </AiButton>
        </div>
      </template>
      <template #footer>
        <AiButton @click="resultVisible = false"> 关闭 </AiButton>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.task-page {
  padding: 4px 8px 24px;
}
/* 统计：三个数字+标签的极简组合，无卡片 */
.stat-row {
  display: flex;
  gap: 48px;
  margin-bottom: 24px;
}
.stat-card {
  background: transparent;
  border-radius: 0;
  padding: 0;
  box-shadow: none;
}
.stat-num {
  font-size: 24px;
  line-height: 32px;
  font-weight: 600;
  color: var(--reai-text-main);
}
.stat-label {
  font-size: 12px;
  color: var(--reai-text-muted);
  margin-top: 2px;
}

/* 任务条目：浅色背景区分，无边框无阴影 */
.task-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-height: 120px;
}
.task-row {
  background: var(--reai-bg-gray);
  border-radius: 12px;
  padding: 14px 20px;
  display: flex;
  align-items: center;
  gap: 16px;
  transition: background 0.2s;
}
.task-row:hover {
  background: #ecf0f6;
}
.task-row.dim {
  opacity: 0.55;
}
.task-status-icon {
  width: 18px;
  display: flex;
  justify-content: center;
  font-size: 13px;
  flex-shrink: 0;
}
.task-main {
  flex: 1;
  min-width: 0;
}
.task-name {
  font-size: 16px;
  color: var(--reai-text-main);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.task-type {
  font-size: 11px;
  color: var(--reai-text-muted);
  background: rgba(26, 32, 44, 0.06);
  border-radius: 6px;
  padding: 1px 8px;
  margin-left: 8px;
}
.task-error {
  font-size: 12px;
  color: var(--reai-danger);
  margin-top: 2px;
}
.task-phase {
  font-size: 12px;
  color: var(--reai-text-muted);
  margin-top: 2px;
}
.task-time {
  font-size: 14px;
  color: var(--reai-text-muted);
  flex-shrink: 0;
  width: 110px;
}
.task-progress {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 240px;
  flex-shrink: 0;
}
.progress-track {
  flex: 1;
  height: 4px;
  background: rgba(26, 32, 44, 0.08);
  border-radius: 2px;
  overflow: hidden;
}
.progress-fill {
  height: 100%;
  background: var(--reai-primary);
  border-radius: 3px;
  transition: width 0.4s;
}
.progress-text {
  font-size: 12px;
  color: var(--reai-text-muted);
  width: 34px;
  text-align: right;
}
.task-status-text {
  font-size: 14px;
  width: 56px;
  flex-shrink: 0;
}
.st-running {
  color: var(--reai-primary);
}
.st-done {
  color: #059669;
}
.st-failed {
  color: var(--reai-danger);
}
.st-cancelled {
  color: var(--reai-text-muted);
}
.task-ops {
  width: 100px;
  display: flex;
  justify-content: flex-end;
  flex-shrink: 0;
}

.spinner {
  width: 12px;
  height: 12px;
  border: 2px solid var(--reai-primary);
  border-top-color: transparent;
  border-radius: 50%;
  display: inline-block;
  animation: spin 0.8s linear infinite;
}
@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 60px 0;
}
.empty-icon {
  font-size: 64px;
}
.empty-title {
  font-size: 16px;
  color: var(--reai-text-main);
  margin-top: 16px;
  font-weight: 600;
}
.empty-sub {
  font-size: 14px;
  color: var(--reai-text-muted);
  margin-top: 8px;
}

/* 结果弹窗 */
.result-img-wrap {
  text-align: center;
}
.result-img {
  max-width: 100%;
  max-height: 420px;
  border-radius: 12px;
  box-shadow: var(--reai-shadow-md);
}
.demo-render {
  max-height: 400px;
  background: var(--reai-bg-neutral);
  border-radius: 12px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 48px 0;
}
.result-import {
  text-align: center;
  padding: 16px 0;
}
.import-line {
  font-size: 15px;
  color: var(--reai-text-main);
  margin-bottom: 12px;
}
.import-item {
  font-size: 12px;
  padding: 4px 10px;
  border-radius: 8px;
  margin: 2px auto;
  max-width: 640px;
  text-align: left;
}
.import-item.ok {
  background: #ecfdf5;
  color: #047857;
}
.import-item.bad {
  background: #fef2f2;
  color: #b91c1c;
}
</style>
