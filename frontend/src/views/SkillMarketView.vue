<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import { skills as mockSkills } from '@/mock';
import { api } from '@/api';
import AiButton from '@/components/AiButton/index.vue';

/* ---------------- 筛选 + 卡片网格（规范 6.1 / 6.2），数据接后端 Skill 市场接口 ---------------- */
const filter = ref<'all' | 'installed' | 'not'>('all');
const filterOptions = [
  { label: '全部', value: 'all' },
  { label: '已安装', value: 'installed' },
  { label: '未安装', value: 'not' },
];
const list = reactive<any[]>(mockSkills.map(s => ({ ...s, installing: false })));
const filtered = computed(() =>
  filter.value === 'all'
    ? list
    : list.filter(s => (filter.value === 'installed' ? s.installed : !s.installed))
);
const installedCount = computed(() => list.filter(s => s.installed).length);

function normalize(s: any) {
  return {
    id: s.id,
    name: s.name,
    icon: s.icon,
    desc: s.desc,
    version: s.version,
    openSource: s.open_source ?? s.openSource ?? false,
    installed: !!s.installed,
    installing: false,
  };
}

onMounted(async () => {
  try {
    const data: any[] = await api.listSkills();
    if (data?.length) list.splice(0, list.length, ...data.map(normalize));
  } catch {
    /* 后端不可达保持演示数据 */
  }
});

async function install(s: any) {
  s.installing = true;
  try {
    await api.installSkill(s.id);
    s.installed = true;
    ElMessage.success(`「${s.name}」安装成功`);
  } catch (e: any) {
    ElMessage.error(e?.message ?? '安装失败');
  } finally {
    s.installing = false;
  }
}

async function uninstall(s: any) {
  try {
    await ElMessageBox.confirm(`卸载后「${s.name}」将无法被 @ 调用，确认卸载？`, '卸载 Skill', {
      type: 'warning',
      confirmButtonText: '卸载',
      cancelButtonText: '取消',
    });
  } catch {
    return;
  }
  try {
    await api.uninstallSkill(s.id);
    s.installed = false;
    ElMessage.success('已卸载');
  } catch (e: any) {
    ElMessage.warning(e?.message ?? '卸载失败');
  }
}

/* ---------------- Skill 试运行（POST /skills/{id}/invoke，SSE 流式输出） ---------------- */
const invokeVisible = ref(false);
const invokeTarget = ref<any>(null);
const invokeInput = ref('');
const invokeOutput = ref('');
const invokePhase = ref('');
const invoking = ref(false);

function openInvoke(s: any) {
  invokeTarget.value = s;
  invokeInput.value = '滨江花园A户型，建面98㎡，三房两厅，南北通透，主卧朝南带飘窗，均价2.1万/㎡';
  invokeOutput.value = '';
  invokePhase.value = '';
  invokeVisible.value = true;
}

async function runInvoke() {
  const target = invokeTarget.value;
  if (!target || !invokeInput.value.trim() || invoking.value) return;
  invoking.value = true;
  invokeOutput.value = '';
  try {
    const res = await api.invokeSkill(target.id, invokeInput.value.trim());
    if (!res.body) throw new Error('无响应流');
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
        if (ev === 'phase') invokePhase.value = data;
        else if (ev === 'message') invokeOutput.value += data;
        else if (ev === 'error') {
          const err = JSON.parse(data);
          ElMessage.error(err.msg ?? '调用失败');
        } else if (ev === 'fail') ElMessage.error(data);
      }
    }
  } catch (e: any) {
    ElMessage.error(e?.message ?? '调用失败');
  } finally {
    invoking.value = false;
    invokePhase.value = '';
  }
}
</script>

<template>
  <div class="market-page">
    <!-- 页面头部 80px -->
    <div class="market-head">
      <div>
        <h2 class="market-title">Skill 市场</h2>
        <p class="market-desc">安装即用，扩展 AI 能力 · 已安装 {{ installedCount }} 个</p>
      </div>
      <el-segmented v-model="filter" :options="filterOptions" size="large" />
    </div>

    <!-- 卡片网格 4列 -->
    <div class="card-grid">
      <div v-for="s in filtered" :key="s.id" class="skill-card">
        <span class="os-tag"
          ><i class="mini-dot" :class="s.openSource ? 'd-open' : 'd-prop'" />{{
            s.openSource ? '开源' : '专有'
          }}</span
        >
        <div class="card-center">
          <div class="skill-icon">
            {{ s.icon }}
          </div>
          <div class="skill-name">
            {{ s.name }}
          </div>
          <div class="skill-desc">
            {{ s.desc }}
          </div>
          <div class="skill-ver">
            {{ s.version }}
          </div>
        </div>
        <div class="card-footer">
          <!-- 未安装 -->
          <AiButton
            v-if="!s.installed"
            class="install-btn"
            round
            :loading="s.installing"
            @click="install(s)"
          >
            {{ s.installing ? '安装中...' : '安装' }}
          </AiButton>
          <!-- 已安装 -->
          <template v-else>
            <span class="enabled-tag">✓ 已启用</span>
            <AiButton text type="primary" size="small" @click="openInvoke(s)"> 试运行 </AiButton>
            <AiButton text size="small" style="color: var(--reai-text-muted)" @click="uninstall(s)">
              卸载
            </AiButton>
          </template>
        </div>
      </div>
      <div v-if="!filtered.length" class="empty-state">
        <div class="empty-icon">🧩</div>
        <div class="empty-title">暂无内容</div>
        <div class="empty-sub">当前筛选条件下没有 Skill</div>
      </div>
    </div>

    <!-- 试运行弹窗：SSE 打字机输出 -->
    <el-dialog
      v-model="invokeVisible"
      :title="`试运行 · ${invokeTarget?.name ?? ''}`"
      width="640px"
    >
      <el-input
        v-model="invokeInput"
        type="textarea"
        :rows="3"
        placeholder="输入交给 Skill 处理的内容（房源信息 / 政策问题...）"
      />
      <div v-if="invokePhase" class="invoke-phase">
        {{ invokePhase }}
      </div>
      <div v-if="invokeOutput" class="invoke-output">
        {{ invokeOutput }}
      </div>
      <template #footer>
        <AiButton @click="invokeVisible = false"> 关闭 </AiButton>
        <AiButton type="primary" :loading="invoking" @click="runInvoke"> 运行 </AiButton>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.market-page {
  padding: 4px 8px 24px;
}
.market-head {
  min-height: 80px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}
.market-title {
  font-size: 22px;
  font-weight: 700;
  color: var(--reai-text-main);
  margin: 0;
}
.market-desc {
  font-size: 14px;
  color: var(--reai-text-muted);
  margin: 4px 0 0;
}

/* 两列大卡片，给每个 Skill 充足展示空间 */
.card-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 16px;
}
@media (max-width: 1120px) {
  .card-grid {
    grid-template-columns: 1fr;
  }
}

/* 克制的白卡：极淡阴影，悬停才浮起 */
.skill-card {
  background: var(--reai-card);
  border-radius: 16px;
  min-height: 200px;
  padding: 20px 24px;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  box-shadow: var(--reai-shadow-sm);
  position: relative;
  transition:
    box-shadow 0.25s,
    transform 0.25s;
}
.skill-card:hover {
  transform: translateY(-2px);
  box-shadow: var(--reai-shadow-md);
}

/* 极小圆点 + 文字 */
.os-tag {
  position: absolute;
  top: 16px;
  left: 16px;
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 10px;
  color: var(--reai-text-muted);
}
.mini-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  display: inline-block;
}
.d-open {
  background: var(--reai-success);
}
.d-prop {
  background: var(--reai-text-muted);
}

.card-center {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  padding-top: 24px;
}
/* 图标底色错落 */
.skill-icon {
  width: 48px;
  height: 48px;
  border-radius: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 24px;
  margin-bottom: 12px;
  background: var(--reai-primary-soft);
}
.skill-card:nth-child(4n + 2) .skill-icon {
  background: #ecfdf5;
}
.skill-card:nth-child(4n + 3) .skill-icon {
  background: #fff7ed;
}
.skill-card:nth-child(4n) .skill-icon {
  background: #fdf2f8;
}

.skill-name {
  font-size: 16px;
  font-weight: 600;
  color: var(--reai-text-main);
}
.skill-desc {
  font-size: 14px;
  color: var(--reai-text-muted);
  margin-top: 6px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.skill-ver {
  font-size: 12px;
  color: var(--reai-text-muted);
  margin-top: 6px;
}

.card-footer {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 32px;
  margin-top: 14px;
  gap: 10px;
}
.install-btn {
  width: 100%;
  height: 34px;
  font-weight: 500;
}
/* 已启用：绿色文字，替代色块 */
.enabled-tag {
  font-size: 12px;
  color: var(--reai-success);
  font-weight: 500;
}

.empty-state {
  grid-column: 1 / -1;
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

/* 试运行 */
.invoke-phase {
  font-size: 12px;
  color: var(--reai-primary);
  margin-top: 12px;
}
.invoke-output {
  margin-top: 12px;
  background: var(--reai-bg-gray);
  border-radius: 12px;
  padding: 14px 16px;
  font-size: 13px;
  line-height: 1.8;
  color: var(--reai-text-main);
  white-space: pre-wrap;
  max-height: 320px;
  overflow-y: auto;
}
</style>
