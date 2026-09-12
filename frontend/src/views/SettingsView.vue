<script setup lang="ts">
import PageHero from '@/components/PageHero/index.vue';
import { onMounted, reactive, ref } from 'vue';
import { ElMessage, ElMessageBox } from 'element-plus';

import { api } from '@/api';

const loading = ref(false);
const saving = ref(false);

/* ---------- 记忆管理：长期记忆（授权写入，可查看/修改/删除；敏感信息带过期时间） ---------- */
const CAT_LABEL: Record<string, string> = {
  preference: '偏好',
  project: '常用项目',
  fact: '稳定信息',
};
const memItems = ref<any[]>([]);
const memStats = ref<any>({});
const memDialog = ref(false);
const memSaving = ref(false);
const memEditingId = ref<string | null>(null);
const memForm = reactive({
  content: '',
  category: '',
  authorized: true,
  expires_days: undefined as number | undefined,
});

const loadMemory = async () => {
  try {
    const [list, stats] = await Promise.all([api.listLongMemory(), api.memoryStats()]);
    memItems.value = list.items ?? [];
    memStats.value = stats;
  } catch (e: any) {
    ElMessage.error(e.message || '加载记忆失败');
  }
};

const openMemCreate = () => {
  memEditingId.value = null;
  Object.assign(memForm, { content: '', category: '', authorized: true, expires_days: undefined });
  memDialog.value = true;
};

const openMemEdit = (row: any) => {
  memEditingId.value = row.id;
  Object.assign(memForm, {
    content: row.content,
    category: row.category,
    authorized: row.authorized,
    expires_days: undefined,
  });
  memDialog.value = true;
};

const saveMemory = async () => {
  if (!memForm.content.trim()) {
    ElMessage.warning('请填写记忆内容');
    return;
  }
  memSaving.value = true;
  try {
    const payload = {
      content: memForm.content.trim(),
      category: memForm.category || undefined,
      authorized: memForm.authorized,
      expires_days: memForm.expires_days,
    };
    if (memEditingId.value) {
      await api.updateLongMemory(memEditingId.value, payload);
      ElMessage.success('记忆已更新');
    } else {
      await api.addLongMemory(payload);
      ElMessage.success(memForm.authorized ? '记忆已保存' : '已保存为待授权记忆（不会注入对话）');
    }
    memDialog.value = false;
    loadMemory();
  } catch (e: any) {
    ElMessage.error(e.message || '保存失败');
  } finally {
    memSaving.value = false;
  }
};

const authorizeMemory = async (row: any) => {
  try {
    await api.updateLongMemory(row.id, { authorized: true });
    ElMessage.success('已授权，该记忆将在对话中生效');
    loadMemory();
  } catch (e: any) {
    ElMessage.error(e.message || '授权失败');
  }
};

const removeMemory = async (row: any) => {
  try {
    await ElMessageBox.confirm('确定删除这条长期记忆？删除后不可恢复。', '删除记忆', {
      type: 'warning',
    });
    await api.deleteLongMemory(row.id);
    ElMessage.success('已删除');
    loadMemory();
  } catch {
    /* 取消 */
  }
};

const CAT_TAG: Record<string, string> = { preference: 'success', project: 'primary', fact: 'info' };

const fmtExpire = (iso: string) => {
  const d = new Date(iso);
  return d.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
};

const form = reactive({
  llm_model: '',
  llm_base_url: '',
  embed_model: '',
  rerank_model: '',
  comfyui_base_url: '',
  top_k: 10,
  final_k: 4,
  min_score: 0.25,
  chunk_size: 500,
  chunk_overlap: 80,
});

const load = async () => {
  loading.value = true;
  try {
    const s = await api.getSettings();
    Object.assign(form, {
      llm_model: s.model.llm_model,
      llm_base_url: s.model.llm_base_url,
      embed_model: s.model.embed_model,
      rerank_model: s.model.rerank_model,
      comfyui_base_url: s.model.comfyui_base_url,
      top_k: s.retrieval.top_k,
      final_k: s.retrieval.final_k,
      min_score: s.retrieval.min_score,
      chunk_size: s.chunking.chunk_size,
      chunk_overlap: s.chunking.chunk_overlap,
    });
  } catch (e: any) {
    ElMessage.error(e.message || '加载设置失败');
  } finally {
    loading.value = false;
  }
};
onMounted(() => {
  load();
  loadMemory();
});

const save = async () => {
  if (form.chunk_overlap >= form.chunk_size) {
    ElMessage.warning('分块重叠需小于分块长度');
    return;
  }
  saving.value = true;
  try {
    await api.updateSettings({
      llm_model: form.llm_model,
      rag_top_k: form.top_k,
      rag_final_k: form.final_k,
      rag_min_score: form.min_score,
      rag_chunk_size: form.chunk_size,
      rag_chunk_overlap: form.chunk_overlap,
    });
    ElMessage.success('参数已保存并立即生效（新上传文档将按新分块参数入库）');
  } catch (e: any) {
    ElMessage.error(e.message || '保存失败');
  } finally {
    saving.value = false;
  }
};
</script>

<template>
  <div v-loading="loading" class="settings-page">
    <div class="page-toolbar">
      <PageHero
        index="07"
        title="系统设置"
        sub="模型 · 检索 · 分块 · 记忆，保存后热更新生效"
        :tags="[
          { text: '平台配置', kind: 'blue' },
          { text: '热更新', kind: 'green' },
        ]"
      />
      <el-button type="primary" round :disabled="saving" @click="save">
        saving ? '保存中...' : '保存并生效' }}
      </el-button>
    </div>

    <!-- 模型参数 -->
    <div class="set-card fashion-card">
      <div class="card-head">
        <div class="card-title">🧠 模型参数</div>
        <div class="card-sub">智能问答生成模型与 RAG 检索模型（本地部署，改动对话即刻生效）</div>
      </div>
      <div class="field-grid">
        <label class="field">
          <span class="field-label">LLM 模型（Ollama）</span>
          <el-input v-model="form.llm_model" placeholder="如 qwen2.5:14b" />
          <span class="field-tip">拉取更大模型后在此填写：ollama pull qwen2.5:14b</span>
        </label>
        <label class="field">
          <span class="field-label">LLM 服务地址</span>
          <el-input v-model="form.llm_base_url" disabled />
        </label>
        <label class="field">
          <span class="field-label">Embedding 模型（只读）</span>
          <el-input v-model="form.embed_model" disabled />
        </label>
        <label class="field">
          <span class="field-label">Reranker 模型（只读）</span>
          <el-input v-model="form.rerank_model" disabled />
        </label>
        <label class="field">
          <span class="field-label">装修图渲染服务</span>
          <el-input v-model="form.comfyui_base_url" disabled />
          <span class="field-tip">ComfyUI 未启动时自动降级演示模式</span>
        </label>
      </div>
    </div>

    <!-- 检索参数 -->
    <div class="set-card fashion-card">
      <div class="card-head">
        <div class="card-title">🔍 检索参数</div>
        <div class="card-sub">向量召回与重排策略（热更新，下一次提问即生效）</div>
      </div>
      <div class="field-grid">
        <label class="field">
          <span class="field-label">召回数量 Top-K：{{ form.top_k }}</span>
          <el-slider v-model="form.top_k" :min="1" :max="30" show-input />
        </label>
        <label class="field">
          <span class="field-label">重排保留数 Final-K：{{ form.final_k }}</span>
          <el-slider v-model="form.final_k" :min="1" :max="15" show-input />
        </label>
        <label class="field">
          <span class="field-label">拒答阈值（相关度低于该值触发拒答）：{{ form.min_score }}</span>
          <el-slider v-model="form.min_score" :min="0" :max="1" :step="0.05" show-input />
        </label>
      </div>
    </div>

    <!-- 分块参数 -->
    <div class="set-card fashion-card">
      <div class="card-head">
        <div class="card-title">✂️ 分块参数</div>
        <div class="card-sub">离线入库链的递归分块策略（对之后上传的文档生效）</div>
      </div>
      <div class="field-grid">
        <label class="field">
          <span class="field-label">分块长度（字符）：{{ form.chunk_size }}</span>
          <el-slider v-model="form.chunk_size" :min="200" :max="1500" :step="50" show-input />
        </label>
        <label class="field">
          <span class="field-label">相邻块重叠：{{ form.chunk_overlap }}</span>
          <el-slider v-model="form.chunk_overlap" :min="0" :max="400" :step="20" show-input />
        </label>
      </div>
    </div>

    <!-- 记忆管理 -->
    <div class="set-card fashion-card">
      <div class="card-head">
        <div class="card-title">🧷 记忆管理</div>
        <div class="card-sub">
          短期记忆保存当前会话近期消息与任务状态（窗口 + 摘要 + Token
          预算）；长期记忆仅保存您明确授权的稳定信息（{{
            memStats.short?.active_sessions ?? 0
          }}
          个活跃会话 / 长期 {{ memStats.long?.total ?? 0 }} 条，待授权
          {{ memStats.long?.pending ?? 0 }}
          条）。楼盘价格、政策等业务事实实时由知识库检索获取，不写入记忆。
        </div>
      </div>
      <div class="mem-toolbar">
        <el-button type="primary" round size="small" @click="openMemCreate"> 新增记忆 </el-button>
      </div>
      <el-table
        :data="memItems"
        size="small"
        empty-text="暂无长期记忆（在对话中确认保存后出现在这里）"
      >
        <el-table-column label="内容" min-width="240">
          <template #default="{ row }">
            <span class="mem-content">{{ row.content }}</span>
            <el-tag v-if="row.sensitive" type="danger" size="small" effect="plain" class="mem-tag">
              敏感
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="分类" width="90">
          <template #default="{ row }">
            <el-tag
              :type="
                (CAT_TAG[row.category] || 'info') as
                  'primary' | 'success' | 'warning' | 'info' | 'danger'
              "
              size="small"
              effect="plain"
            >
              {{ CAT_LABEL[row.category] || row.category }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="row.authorized ? 'success' : 'warning'" size="small">
              {{ row.authorized ? '已授权' : '待授权' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="过期时间" width="170">
          <template #default="{ row }">
            <span v-if="row.expires_at" :class="{ 'mem-expired': row.sensitive }">{{
              fmtExpire(row.expires_at)
            }}</span>
            <span v-else class="mem-muted">长期有效</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="180" align="right">
          <template #default="{ row }">
            <el-button
              v-if="!row.authorized"
              link
              type="primary"
              size="small"
              @click="authorizeMemory(row)"
            >
              授权
            </el-button>
            <el-button link type="primary" size="small" @click="openMemEdit(row)"> 编辑 </el-button>
            <el-button link type="danger" size="small" @click="removeMemory(row)"> 删除 </el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 新增/编辑记忆 -->
    <el-dialog
      v-model="memDialog"
      :title="memEditingId ? '编辑长期记忆' : '新增长期记忆'"
      width="480px"
    >
      <div class="mem-form">
        <label class="field">
          <span class="field-label">记忆内容（稳定信息，如偏好、常用项目）</span>
          <el-input
            v-model="memForm.content"
            type="textarea"
            :rows="3"
            maxlength="500"
            show-word-limit
            placeholder="例：客户偏好南北通透户型，重点关注滨江花园项目"
          />
        </label>
        <div class="mem-form-row">
          <label class="field">
            <span class="field-label">分类</span>
            <el-select
              v-model="memForm.category"
              placeholder="自动识别"
              clearable
              style="width: 100%"
            >
              <el-option label="偏好" value="preference" />
              <el-option label="常用项目" value="project" />
              <el-option label="稳定信息" value="fact" />
            </el-select>
          </label>
          <label class="field">
            <span class="field-label">过期天数（敏感信息必填，如手机号）</span>
            <el-input-number
              v-model="memForm.expires_days"
              :min="1"
              :max="365"
              style="width: 100%"
              placeholder="不限"
            />
          </label>
        </div>
        <el-switch
          v-model="memForm.authorized"
          active-text="授权写入长期记忆"
          inactive-text="仅保存草稿（待授权）"
        />
        <div class="mem-note">
          未授权的记忆不会注入任何对话；含手机号/身份证/银行卡的内容必须设置过期时间。
        </div>
      </div>
      <template #footer>
        <el-button @click="memDialog = false"> 取消 </el-button>
        <el-button type="primary" round :disabled="memSaving" @click="saveMemory"> 保存 </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.settings-page {
  padding: 4px 8px 16px;
  max-width: 860px;
}
.page-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}
.page-title {
  font-size: 22px;
  font-weight: 700;
  color: var(--reai-text-main);
  margin: 0;
}

.set-card {
  background: var(--reai-card);
  border-radius: 14px;
  box-shadow: var(--reai-shadow-sm);
  padding: 18px 22px;
  margin-bottom: 14px;
  transition: box-shadow 0.2s;
}
.set-card:hover {
  box-shadow: var(--reai-shadow-md);
}
.card-head {
  margin-bottom: 14px;
}
.card-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--reai-text-main);
}
.card-sub {
  font-size: 12px;
  color: var(--reai-text-muted);
  margin-top: 4px;
}

.field-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px 24px;
}
.field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.field-label {
  font-size: 13px;
  color: var(--reai-text-secondary);
  font-weight: 500;
}
.field-tip {
  font-size: 11px;
  color: var(--reai-text-muted);
}

@media (max-width: 720px) {
  .field-grid {
    grid-template-columns: 1fr;
  }
}

.mem-toolbar {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 10px;
}
.mem-content {
  font-size: 13px;
  color: var(--reai-text-main);
}
.mem-tag {
  margin-left: 6px;
}
.mem-muted {
  color: var(--reai-text-muted);
  font-size: 12px;
}
.mem-expired {
  color: var(--el-color-danger, #f56c6c);
  font-size: 12px;
}
.mem-form {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.mem-form-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}
.mem-note {
  font-size: 11px;
  color: var(--reai-text-muted);
  line-height: 1.6;
}
</style>
