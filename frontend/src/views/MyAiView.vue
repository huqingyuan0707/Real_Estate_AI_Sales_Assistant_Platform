<script setup lang="ts">
import PageHero from '@/components/PageHero/index.vue';
/**
 * 我的 AI 服务：每个用户自行填写大模型 / 生图服务的 Base URL 与 API Key。
 * 保存即生效（仅对当前账号），无需改 .env 或重启后端；留空则回退系统默认。
 * 安全约定：Key 只写不读——页面永远不回显明文，留空表示"保持原值不变"。
 */
import { onMounted, reactive, ref } from 'vue';
import { ElMessage, ElMessageBox } from 'element-plus';

import { api } from '@/api';

const loading = ref(false);
const saving = ref(false);
const testing = ref('');
const info = ref<any>({});
const defaults = ref<any>({});
const eff = ref<any>({});

const form = reactive({
  llm_base_url: '',
  llm_api_key: '',
  llm_model: '',
  render_api_base: '',
  render_api_key: '',
  render_api_model: '',
});

const load = async () => {
  loading.value = true;
  try {
    const s: any = await api.getAiConfig();
    info.value = s.config ?? {};
    defaults.value = s.system_defaults ?? {};
    eff.value = s.effective ?? {};
    form.llm_base_url = s.config?.llm_base_url ?? '';
    form.llm_model = s.config?.llm_model ?? '';
    form.render_api_base = s.config?.render_api_base ?? '';
    form.render_api_model = s.config?.render_api_model ?? '';
    // Key 不回显：清空输入框，留空 = 不修改
    form.llm_api_key = '';
    form.render_api_key = '';
  } catch (e: any) {
    ElMessage.error(e.message || '加载我的 AI 配置失败');
  } finally {
    loading.value = false;
  }
};
onMounted(load);

const save = async () => {
  saving.value = true;
  try {
    const p: Record<string, string> = {
      llm_base_url: form.llm_base_url.trim(),
      llm_model: form.llm_model.trim(),
      render_api_base: form.render_api_base.trim(),
      render_api_model: form.render_api_model.trim(),
    };
    // 只提交本次新填的 Key；留空 = 保留原 Key（避免误清空）
    if (form.llm_api_key.trim()) p.llm_api_key = form.llm_api_key.trim();
    if (form.render_api_key.trim()) p.render_api_key = form.render_api_key.trim();
    await api.saveAiConfig(p);
    ElMessage.success('已保存，立即生效（仅对当前账号）');
    await load();
  } catch (e: any) {
    ElMessage.error(e.message || '保存失败');
  } finally {
    saving.value = false;
  }
};

const test = async (target: 'llm' | 'render') => {
  testing.value = target;
  try {
    const p: any = { target };
    if (target === 'llm') {
      if (form.llm_base_url.trim()) p.base_url = form.llm_base_url.trim();
      if (form.llm_api_key.trim()) p.api_key = form.llm_api_key.trim();
    } else {
      if (form.render_api_base.trim()) p.base_url = form.render_api_base.trim();
      if (form.render_api_key.trim()) p.api_key = form.render_api_key.trim();
    }
    const r: any = await api.testAiConfig(p);
    if (r.ok === true) ElMessage.success(r.message);
    else if (r.ok === null) ElMessage.warning(r.message);
    else ElMessage.error(r.message);
  } catch (e: any) {
    ElMessage.error(e.message || '测试失败');
  } finally {
    testing.value = '';
  }
};

const clearAll = async () => {
  try {
    await ElMessageBox.confirm(
      '将删除你保存的 AI 配置，改用系统默认（.env 中的配置）。确定吗？',
      '清除我的配置',
      { type: 'warning' }
    );
    await api.clearAiConfig();
    ElMessage.success('已清除，回退系统默认');
    await load();
  } catch {
    /* 取消 */
  }
};
</script>

<template>
  <div v-loading="loading" class="myai-page">
    <div class="page-toolbar">
      <PageHero
        index="06"
        title="我的 AI 服务"
        sub="在这里填写你自己的 API Key，保存后立即生效且仅对当前账号有效"
        :tags="[
          { text: '个人配置', kind: 'blue' },
          { text: '即时生效', kind: 'green' },
        ]"
      />
      <div class="toolbar-actions">
        <el-button type="primary" round :disabled="saving" @click="save">
          {{ saving ? '保存中...' : '保存我的配置' }}
        </el-button>
        <el-button plain @click="clearAll"> 清除 </el-button>
      </div>
    </div>

    <!-- 智能对话模型 -->
    <div class="set-card fashion-card">
      <div class="card-head">
        <div class="card-title">💬 智能对话模型</div>
        <div class="card-sub">
          OpenAI 兼容协议：Ollama / vLLM / LM Studio /
          云端服务均可（如硅基流动、DeepSeek、通义百炼）
        </div>
        <div class="eff-line">
          <el-tag
            :type="eff.llm?.source === 'user' ? 'success' : 'info'"
            size="small"
            effect="plain"
          >
            {{ eff.llm?.source === 'user' ? '我的配置生效中' : '系统默认生效中' }}
          </el-tag>
          <span class="eff-text">{{ eff.llm?.base_url }} · {{ eff.llm?.model }}</span>
        </div>
      </div>
      <div class="field-grid">
        <label class="field">
          <span class="field-label">服务地址（Base URL）</span>
          <el-input v-model="form.llm_base_url" :placeholder="defaults.llm_base_url" clearable />
          <span class="field-tip">留空使用系统默认：{{ defaults.llm_base_url }}</span>
        </label>
        <label class="field">
          <span class="field-label">API Key</span>
          <el-input
            v-model="form.llm_api_key"
            type="password"
            show-password
            clearable
            :placeholder="
              info.has_llm_key
                ? `已保存（${info.llm_api_key}），留空不修改`
                : 'sk-...（填写后立即生效）'
            "
          />
          <span class="field-tip">出于安全考虑不回显明文；留空表示保持原 Key 不变</span>
        </label>
        <label class="field">
          <span class="field-label">模型名称</span>
          <el-input v-model="form.llm_model" :placeholder="defaults.llm_model" clearable />
          <span class="field-tip">留空使用系统默认：{{ defaults.llm_model }}</span>
        </label>
        <div class="field field-action">
          <span class="field-label">连通性测试</span>
          <el-button :loading="testing === 'llm'" @click="test('llm')"> 测试对话连接 </el-button>
        </div>
      </div>
    </div>

    <!-- 生图与空间理解 -->
    <div class="set-card fashion-card">
      <div class="card-head">
        <div class="card-title">🎨 生图与空间理解</div>
        <div class="card-sub">
          一键装修图 / 空间分析 / 家具清单解析共用（硅基流动、通义万相等 OpenAI 兼容云服务）
        </div>
        <div class="eff-line">
          <el-tag
            :type="eff.render?.source === 'user' ? 'success' : 'info'"
            size="small"
            effect="plain"
          >
            {{ eff.render?.source === 'user' ? '我的配置生效中' : '系统默认生效中' }}
          </el-tag>
          <span class="eff-text"
            >{{ eff.render?.base_url }} · {{ eff.render?.model }}（{{
              eff.render?.provider
            }}）</span
          >
        </div>
      </div>
      <div class="field-grid">
        <label class="field">
          <span class="field-label">服务地址（Base URL）</span>
          <el-input
            v-model="form.render_api_base"
            :placeholder="defaults.render_api_base"
            clearable
          />
          <span class="field-tip">留空使用系统默认：{{ defaults.render_api_base }}</span>
        </label>
        <label class="field">
          <span class="field-label">API Key</span>
          <el-input
            v-model="form.render_api_key"
            type="password"
            show-password
            clearable
            :placeholder="
              info.has_render_key
                ? `已保存（${info.render_api_key}），留空不修改`
                : 'sk-...（填写后立即生效）'
            "
          />
          <span class="field-tip">填写后自动启用云端生图，未配置时自动降级演示模式</span>
        </label>
        <label class="field">
          <span class="field-label">生图模型</span>
          <el-input
            v-model="form.render_api_model"
            :placeholder="defaults.render_api_model"
            clearable
          />
          <span class="field-tip">留空使用系统默认：{{ defaults.render_api_model }}</span>
        </label>
        <div class="field field-action">
          <span class="field-label">连通性测试</span>
          <el-button :loading="testing === 'render'" @click="test('render')">
            测试生图连接
          </el-button>
        </div>
      </div>
    </div>

    <div class="tip-card">
      <div class="tip-title">说明</div>
      <ul class="tip-list">
        <li>配置按账号保存，互不影响；换账号登录看到的是各自的配置。</li>
        <li>保存后无需重启后端，下一次提问 / 生图立即使用新 Key。</li>
        <li>未配置或服务不可用时自动降级：对话走演示模式，生图走演示模式，页面功能不受影响。</li>
        <li>Key 仅在服务端用于发起调用，接口只返回掩码（如 sk-1***cdef）。</li>
      </ul>
    </div>
  </div>
</template>

<style scoped>
.myai-page {
  padding: 4px 8px 16px;
  max-width: 860px;
}
.page-toolbar {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 16px;
}
.page-title {
  font-size: 22px;
  font-weight: 700;
  color: var(--reai-text-main);
  margin: 0;
}
.page-sub {
  font-size: 12px;
  color: var(--reai-text-muted);
  margin-top: 6px;
  line-height: 1.7;
  max-width: 560px;
}
.toolbar-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-shrink: 0;
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

.eff-line {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 10px;
  flex-wrap: wrap;
}
.eff-text {
  font-size: 12px;
  color: var(--reai-text-secondary);
  word-break: break-all;
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
.field-action {
  justify-content: flex-end;
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

.tip-card {
  background: var(--reai-primary-soft);
  border-radius: 14px;
  padding: 16px 22px;
}
.tip-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--reai-text-main);
  margin-bottom: 8px;
}
.tip-list {
  margin: 0;
  padding-left: 18px;
  font-size: 12px;
  color: var(--reai-text-secondary);
  line-height: 1.9;
}

@media (max-width: 720px) {
  .field-grid {
    grid-template-columns: 1fr;
  }
  .page-toolbar {
    flex-direction: column;
  }
}
</style>
