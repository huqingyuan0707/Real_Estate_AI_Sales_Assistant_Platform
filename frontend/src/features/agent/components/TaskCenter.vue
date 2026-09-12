<template>
  <div class="task-center">
    <div class="task-header">
      <h3>任务中心</h3>
      <el-button text @click="loadTasks"> 刷新 </el-button>
    </div>

    <el-empty v-if="!loading && !tasks.length" description="暂无任务" />

    <div v-else class="task-list">
      <div v-for="task in tasks" :key="task.task_id" class="task-item">
        <div class="task-main">
          <div class="task-info">
            <div class="task-name">
              {{ task.name }}
            </div>
            <div class="task-meta">{{ task.type }} · {{ formatTime(task.created_at) }}</div>
          </div>
          <div class="task-progress">
            <el-progress :percentage="task.progress" :stroke-width="8" :show-text="false" />
          </div>
        </div>
        <div class="task-status">
          <el-tag :type="statusType(task.status)" size="small">
            {{ statusText(task.status) }}
          </el-tag>
        </div>
        <div class="task-actions">
          <el-button
            v-if="task.status === 'running' || task.status === 'queued'"
            size="small"
            type="danger"
            @click="cancelTask(task.task_id)"
          >
            取消
          </el-button>
          <el-button
            v-if="task.status === 'done' && task.result"
            size="small"
            type="primary"
            @click="viewResult(task)"
          >
            查看结果
          </el-button>
          <el-button v-if="task.status === 'failed'" size="small" @click="retryTask(task.task_id)">
            重试
          </el-button>
          <el-button
            v-if="task.status === 'done' || task.status === 'failed'"
            size="small"
            @click="deleteTask(task.task_id)"
          >
            删除
          </el-button>
        </div>
      </div>
    </div>

    <el-pagination
      v-if="total > 10"
      layout="prev, pager, next"
      :total="total"
      :page-size="10"
      :current-page="page"
      @current-change="loadTasks"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { api } from '@/api';
import type { Task } from '@/shared/types';

const tasks = ref<Task[]>([]);
const loading = ref(false);
const total = ref(0);
const page = ref(1);

const statusType = (status: string) => {
  switch (status) {
    case 'done':
      return 'success';
    case 'failed':
      return 'danger';
    case 'running':
      return 'primary';
    case 'queued':
      return 'info';
    case 'cancelled':
      return 'warning';
    default:
      return 'info';
  }
};

const statusText = (status: string) => {
  const map: Record<string, string> = {
    done: '已完成',
    failed: '失败',
    running: '执行中',
    queued: '排队中',
    cancelled: '已取消',
  };
  return map[status] ?? status;
};

const formatTime = (time: string) => {
  return new Date(time).toLocaleString();
};

const loadTasks = async (p: number | Event = 1) => {
  const pageNum = typeof p === 'number' ? p : 1;
  page.value = pageNum;
  loading.value = true;
  try {
    const data = await api.listTasks();
    tasks.value = data.items ?? [];
    total.value = data.total ?? 0;
  } catch (e) {
    console.error('Load tasks failed:', e);
  } finally {
    loading.value = false;
  }
};

const cancelTask = async (id: string) => {
  try {
    await api.cancelTask(id);
    await loadTasks(page.value);
  } catch (e) {
    console.error('Cancel task failed:', e);
  }
};

const retryTask = async (id: string) => {
  try {
    await api.retryTask(id);
    await loadTasks(page.value);
  } catch (e) {
    console.error('Retry task failed:', e);
  }
};

const deleteTask = async (id: string) => {
  try {
    await api.deleteTask(id);
    await loadTasks(page.value);
  } catch (e) {
    console.error('Delete task failed:', e);
  }
};

const viewResult = (task: Task) => {
  console.log('Task result:', task.result);
};

onMounted(() => {
  loadTasks();
});
</script>

<style scoped>
.task-center {
  padding: 16px;
}
.task-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}
.task-header h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
}
.task-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.task-item {
  background: var(--reai-card);
  border: 1px solid var(--reai-border);
  border-radius: 12px;
  padding: 16px;
}
.task-main {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 12px;
}
.task-info {
  flex: 1;
  min-width: 0;
}
.task-name {
  font-weight: 500;
  color: var(--reai-text-main);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.task-meta {
  font-size: 12px;
  color: var(--reai-text-muted);
  margin-top: 4px;
}
.task-progress {
  width: 200px;
  flex-shrink: 0;
}
.task-status {
  display: flex;
  align-items: center;
  gap: 12px;
}
.task-actions {
  display: flex;
  gap: 8px;
  margin-left: auto;
}
</style>
