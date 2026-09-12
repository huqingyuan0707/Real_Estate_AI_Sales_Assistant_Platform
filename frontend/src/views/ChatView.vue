<script setup lang="ts">
import PageHero from '@/components/PageHero/index.vue';
import { computed, nextTick, onMounted, reactive, ref } from 'vue';
import { useRouter } from 'vue-router';
import { ElMessage, ElMessageBox } from 'element-plus';
// 图标需显式引入（ElementPlusResolver 不处理 @element-plus/icons-vue）
import {
  ArrowRight,
  Close,
  CloseBold,
  Delete,
  Edit,
  Paperclip,
  Select,
} from '@element-plus/icons-vue';
import { installedSkills, messages as mockMessages, sessions as mockSessions } from '@/mock';

import { api } from '@/api';

const router = useRouter();

/* ---------------- 会话列表（真实 API：/sessions，失败回退演示数据） ---------------- */
const sessions = reactive(mockSessions.map(s => ({ ...s })));
const activeId = ref('t-1001');
/** 已从后端恢复过历史的会话：续发消息走 /sessions/{id}/resume（断点续聊） */
const restoredIds = new Set<string>();
const grouped = computed(() => {
  const g: Record<string, typeof sessions> = {};
  for (const s of sessions) (g[s.group] ??= []).push(s);
  return g;
});

/** 本地新建、后端可能尚未落库的会话 id（首轮问答进行中的短暂空窗） */
const localOnlyIds = new Set<string>();

/** 拉取真实历史会话列表（后端不可用时保留现有列表 / mock 种子） */
const refreshSessions = async () => {
  if (streaming.value) return; // 生成中不打断当前会话
  try {
    const list = await api.listSessions();
    if (!Array.isArray(list) || !list.length) return;
    const mapped = list.map((s: any) => ({
      threadId: s.thread_id ?? s.threadId,
      title: s.title,
      group: s.group ?? '今天',
      time: s.time ?? '',
    }));
    const cur = activeId.value;
    if (mapped.some(s => s.threadId === cur)) {
      localOnlyIds.delete(cur);
    } else if (localOnlyIds.has(cur)) {
      // 刚发出的会话后端仍在写盘：先保留在顶部，避免"发完就从列表消失"
      const local = sessions.find(s => s.threadId === cur);
      if (local) mapped.unshift(local);
    }
    sessions.splice(0, sessions.length, ...mapped);
    if (!sessions.some(s => s.threadId === activeId.value)) {
      activeId.value = sessions[0]?.threadId ?? '';
      if (activeId.value) switchSession(activeId.value);
    }
  } catch {
    /* 后端不可用：保持 mock 种子 */
  }
};

onMounted(refreshSessions);

const selectSession = (id: string) => {
  activeId.value = id;
};
const renameSession = (s: { title: string }) => {
  ElMessageBox.prompt('修改会话名称', '重命名', {
    inputValue: s.title,
    confirmButtonText: '保存',
    cancelButtonText: '取消',
  })
    .then(({ value }) => {
      if (value?.trim()) s.title = value.trim();
    })
    .catch(() => {});
};
const removeSession = (id: string) => {
  ElMessageBox.confirm('删除后该会话不可恢复，确认删除？', '删除会话', {
    type: 'warning',
    confirmButtonText: '删除',
    cancelButtonText: '取消',
  })
    .then(async () => {
      try {
        // 必须同步删后端短期记忆，否则刷新后会话会"复活"
        await api.deleteSession(id);
      } catch {
        /* 后端无此会话（本地新建未落库）时按已删除处理 */
      }
      const i = sessions.findIndex(s => s.threadId === id);
      if (i > -1) sessions.splice(i, 1);
      localOnlyIds.delete(id);
      if (activeId.value === id) {
        activeId.value = sessions[0]?.threadId ?? '';
        if (activeId.value) switchSession(activeId.value);
        else threadMessages.value = [];
      }
      ElMessage.success('已删除');
    })
    .catch(() => {});
};
const newSession = () => {
  const id = `t-${Date.now()}`;
  localOnlyIds.add(id);
  sessions.unshift({ threadId: id, title: '新对话', group: '今天', time: '刚刚' });
  activeId.value = id;
  threadMessages.value = [];
};

/* ---------------- 消息流 ---------------- */
const threadMessages = ref<any[]>([...(mockMessages['t-1001'] ?? [])]);
const expandedRefs = ref<Set<string>>(new Set());

const streaming = ref(false);
const phase = ref(0);
const phaseText = ref('🧠 规划中...');
const PHASES = ['🧠 规划中...', '⚙️ 执行中...', '✅ 校验中...', '✍️ 生成回答'];

const toggleRefs = (id: string) => {
  const s = expandedRefs.value;
  s.has(id) ? s.delete(id) : s.add(id);
};

/** 密级中文化（引用与知识库一致） */
const LEVEL_TAG: Record<string, string> = {
  public: '公开',
  internal: '内部',
  confidential: '机密',
};

/* ---------------- 反馈闭环：采纳 / 不采纳 → 知识质量与缺口分析 ---------------- */
const rateMessage = async (m: any, rating: 'up' | 'down') => {
  const idx = threadMessages.value.findIndex(x => x.id === m.id);
  const prev = threadMessages.value[idx - 1];
  try {
    await api.submitFeedback({
      rating,
      thread_id: activeId.value,
      trace_id: m.traceId ?? '',
      query: prev?.role === 'user' ? prev.content : '',
      answer: m.content ?? '',
      docs: (m.references ?? []).map((r: any) => r.doc),
      rejected: !!m.rejected,
    });
    m.rating = rating;
    ElMessage.success(
      rating === 'up' ? '感谢认可，已计入采纳率' : '已记录，将用于知识质量与缺口分析'
    );
  } catch (e: any) {
    ElMessage.error(e.message || '反馈提交失败');
  }
};
/** 切换会话：优先从后端恢复历史（短期记忆/消息存储），失败回退 mock */
const switchSession = async (id: string) => {
  activeId.value = id;
  try {
    const detail = await api.getSession(id);
    const msgs = detail?.messages ?? [];
    threadMessages.value = msgs.map((m: any, i: number) => ({
      id: m.id ?? `m${i}`,
      role: m.role,
      content: m.content ?? '',
      attachments: m.attachments ?? [],
      skill: m.skill ?? '',
      references: (m.references ?? []).map((r: any) => ({ ...r, snippet: r.snippet ?? '' })),
      houseCard: !!m.house_card,
      time: m.time ?? '',
    }));
    restoredIds.add(id);
    return;
  } catch {
    /* 404 = 后端无此会话（如本地新建），回退演示 */
  }
  threadMessages.value = [...(mockMessages[id] ?? [])];
};
const openHouse = () => {
  router.push('/house');
};

// 流式演示：四阶段状态条 → 打字机输出 → 引用来源 + 户型卡片
const DEMO_REPLY =
  '🌟滨江花园A户型 | 建面98㎡ 三房两厅\n\n南北通透，双阳台对流设计，午后穿堂风轻拂整屋。' +
  '主卧朝南带飘窗，四季阳光满屋。U型厨房紧邻餐边区，动线高效。均价2.1万/㎡，本周到访享开盘额外98折！';

const sendDemo = () => {
  if (streaming.value) return;
  const content = draft.value;
  if (!content.trim()) return;
  const uid = `u-${Date.now()}`;
  threadMessages.value.push({
    id: uid,
    role: 'user',
    content,
    attachments: [...attachments.value],
    time: '刚刚',
    skill: activeSkill.value,
  });
  const skill = activeSkill.value;
  const atts = [...attachments.value];
  draft.value = '';
  attachments.value = [];
  activeSkill.value = '';
  scrollBottom();

  streaming.value = true;
  phase.value = 0;
  phaseText.value = PHASES[0];

  let ai: any = null;
  const ensureAI = () => {
    if (!ai) {
      ai = reactive({
        id: `a-${Date.now()}`,
        role: 'assistant',
        content: '',
        references: [] as any[],
        houseCard: true,
        time: '刚刚',
      });
      threadMessages.value.push(ai);
    }
    return ai;
  };

  // 主链路：后端 SSE（Qwen2.5 真实推理，LLM 不可用时后端自动降级演示流）
  // 从后端恢复过的会话续发消息走 /sessions/{thread_id}/resume（断点续聊，5.2），新会话走 /chat
  const streamP = restoredIds.has(activeId.value)
    ? api.resumeSession(activeId.value, content)
    : api.chatStream({ thread_id: activeId.value, content, skill, attachments: atts });
  streamP
    .then(async res => {
      const ctype = res.headers.get('content-type') ?? '';
      if (!ctype.includes('text/event-stream')) {
        // 非流式 JSON = 非 0 响应（如 2001 知识库拒答）
        const body = await res.json();
        if (body.code === 2001) {
          threadMessages.value.push({
            id: `a-${Date.now()}`,
            role: 'assistant',
            rejected: true,
            time: '刚刚',
          });
          streaming.value = false;
          return;
        }
        throw new Error(body.msg || '请求失败');
      }
      const reader = res.body!.getReader();
      const decoder = new TextDecoder();
      let buf = '';
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        const parts = buf.split('\n\n');
        buf = parts.pop() ?? '';
        for (const part of parts) {
          if (!part.trim()) continue;
          const ev = /event: (.*)/.exec(part)?.[1]?.trim();
          const data = /data: (.*)/.exec(part)?.[1];
          if (!ev) continue;
          if (ev === 'phase') {
            phaseText.value = data ?? '';
          } else if (ev === 'message') {
            const m = ensureAI();
            m.content += data;
            scrollBottom();
          } else if (ev === 'done') {
            let refs: any[] = [];
            let payload: any = {};
            try {
              payload = JSON.parse(data ?? '{}');
              refs = payload.references ?? [];
            } catch {
              /* ignore */
            }
            const m = ensureAI();
            m.references = refs;
            m.traceId = payload.trace_id ?? '';
            m.guard = payload.guard ?? null;
            m.faith = payload.faithfulness ?? null;
            m.model = payload.model ?? '';
            streaming.value = false;
            refreshSessions(); // 问答落盘后刷新列表：标题变为首句、排序与时间即时更新
            return;
          }
        }
      }
      ensureAI().references = [];
      streaming.value = false;
    })
    .catch(() => simulateLocal(ensureAI)); // 客户端兜底：网络/后端异常时本地模拟
};

/** 客户端降级演示：本地模拟四阶段 + 打字机（与后端演示流观感一致） */
const simulateLocal = (ensureAI: () => any): Promise<void> => {
  return new Promise(resolve => {
    const timer = setInterval(() => {
      phase.value += 1;
      phaseText.value = PHASES[Math.min(phase.value, 3)];
      if (phase.value > 3) {
        clearInterval(timer);
        const m = ensureAI();
        let i = 0;
        const typer = setInterval(() => {
          m.content = DEMO_REPLY.slice(0, ++i);
          scrollBottom();
          if (i >= DEMO_REPLY.length) {
            clearInterval(typer);
            m.references = [
              {
                doc: '滨江花园楼书2025.pdf',
                page: 12,
                snippet: '…主推A户型采用南北通透布局，客厅开间4.2米…',
              },
              { doc: 'A户型图.jpg', page: 1, snippet: '…A户型标准层平面示意…' },
            ];
            streaming.value = false;
            resolve();
          }
        }, 18);
      }
    }, 700);
  });
};

const scrollBottom = () => {
  nextTick(() => {
    const el = document.querySelector('.msg-flow');
    el?.scrollTo({ top: el.scrollHeight, behavior: 'smooth' });
  });
};

/* ---------------- 输入区 ---------------- */
const draft = ref('');
const attachments = ref<string[]>([]);
const activeSkill = ref('');
const showSkillMenu = ref(false);
const canSend = computed(() => draft.value.trim().length > 0);

const onInput = () => {
  showSkillMenu.value = draft.value.endsWith('@');
  if (!draft.value.includes('@')) activeSkill.value = '';
};
const pickSkill = (name: string) => {
  activeSkill.value = name;
  draft.value = draft.value.replace(/@$/, '');
  showSkillMenu.value = false;
  draft.value += `${name} `;
};
const addAttachment = () => {
  attachments.value.push(`户型图${attachments.value.length + 1}.jpg`);
};
const clearContext = async () => {
  try {
    await ElMessageBox.confirm(
      '将清空本会话的短期记忆（多轮上下文），开始全新话题。长期记忆不受影响。',
      '清空上下文',
      { type: 'warning' }
    );
    await api.clearShortMemory(activeId.value);
    ElMessage.success('短期记忆已清空');
  } catch {
    /* 取消 */
  }
};
const onKeydown = (e: KeyboardEvent) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    if (canSend.value) sendDemo();
  }
};
</script>

<template>
  <div class="chat-page">
    <!-- 左侧会话列表：悬浮卡片式 -->
    <aside class="session-panel fashion-card">
      <PageHero
        index="01"
        title="智能对话"
        compact
        :tags="[
          { text: 'AI 问答', kind: 'blue' },
          { text: 'SSE 实时', kind: 'green' },
        ]"
      />
      <div class="session-head">
        <el-button type="primary" class="new-btn" round @click="newSession"> ✨ 新建对话 </el-button>
      </div>
      <div class="session-list">
        <template v-for="(list, group) in grouped" :key="group">
          <div class="group-title">
            {{ group }}
          </div>
          <div
            v-for="s in list"
            :key="s.threadId"
            class="session-item"
            :class="{ active: s.threadId === activeId }"
            @click="
              selectSession(s.threadId);
              switchSession(s.threadId);
            "
          >
            <span class="session-title">{{ s.title }}</span>
            <span class="session-time">{{ s.time }}</span>
            <span class="session-ops" @click.stop>
              <el-icon :size="14" @click="renameSession(s)"><Edit /></el-icon>
              <el-icon :size="14" color="#EF4444" @click="removeSession(s.threadId)"
                ><Delete
              /></el-icon>
            </span>
          </div>
        </template>
        <div v-if="!sessions.length" class="empty-mini">暂无历史会话</div>
      </div>
    </aside>

    <!-- 右侧对话区：冷灰底 + 悬浮气泡 -->
    <section class="chat-main">
      <div class="msg-flow">
        <div v-if="!threadMessages.length" class="empty-state">
          <div class="empty-icon">💬</div>
          <div class="empty-title">暂无内容</div>
          <div class="empty-sub">点击左上角"✨ 新建对话"，输入需求或 @ 调用技能开始</div>
        </div>

        <template v-for="m in threadMessages" :key="m.id">
          <!-- 用户气泡 -->
          <div v-if="m.role === 'user'" class="row row-user">
            <div class="bubble bubble-user">
              <div v-if="m.skill" class="skill-chip">⚡ {{ m.skill }}</div>
              <div class="bubble-text">
                {{ m.content }}
              </div>
              <div v-if="m.attachments?.length" class="attach-row">
                <span v-for="a in m.attachments" :key="a" class="attach-tag">📎 {{ a }}</span>
              </div>
            </div>
          </div>

          <!-- AI 气泡：白卡浮起 -->
          <div v-else class="row row-ai">
            <div class="ai-wrap">
              <span class="ai-tag">AI生成 仅供参考</span>
              <!-- 拒答态 -->
              <div v-if="m.rejected" class="bubble bubble-ai rejected">
                <div class="refuse-bar">
                  <span class="refuse-text">⚠️ 知识库暂无相关内容</span>
                  <el-button text type="primary" size="small" @click="router.push('/knowledge')">
                    📤 去上传资料
                  </el-button>
                </div>
              </div>
              <div v-else class="bubble bubble-ai">
                <div class="bubble-text">
                  {{ m.content }}<span v-if="streaming && !m.content" class="cursor">▌</span>
                </div>
                <!-- 户型卡片 -->
                <div v-if="m.houseCard && m.content" class="house-card" @click="openHouse">
                  <span class="house-icon">📐</span>
                  <div class="house-info">
                    <div class="house-name">A户型（AI解析）· 滨江花园</div>
                    <div class="house-sub">
                      3室2厅 · 98.5㎡ · 朝南 · 解析看懂 / 设计想象 /
                      效果图心动，点击进入空间智能引擎
                    </div>
                  </div>
                  <el-icon color="var(--reai-primary)">
                    <ArrowRight />
                  </el-icon>
                </div>
                <!-- 引用折叠：可定位到「文件 > 章节 > 页码」，并标注密级与安全事件 -->
                <template v-if="m.references?.length">
                  <div class="ref-divider" />
                  <div class="ref-link" @click="toggleRefs(m.id)">
                    📎 引用 {{ m.references.length }} 篇资料
                    <span v-if="m.guard?.blocked" class="guard-chip"
                      >已拦截越权片段 {{ m.guard.blocked }}</span
                    >
                    <span v-if="m.guard?.injection" class="guard-chip warn"
                      >注入告警 {{ m.guard.injection }}</span
                    >
                  </div>
                  <div v-if="expandedRefs.has(m.id)" class="ref-list">
                    <div v-for="(r, i) in m.references" :key="i" class="ref-item">
                      <div class="ref-doc">
                        📄 {{ r.doc
                        }}<template v-if="r.section && r.section !== r.doc">
                          · {{ r.section }}
                        </template>
                        <span class="ref-page">第{{ r.page }}页</span>
                        <span v-if="r.score" class="ref-score">相关度 {{ r.score }}%</span>
                        <span v-if="r.security_level" class="ref-level">{{
                          LEVEL_TAG[r.security_level] || r.security_level
                        }}</span>
                      </div>
                      <div class="ref-snip">
                        {{ r.snippet }}
                      </div>
                    </div>
                  </div>
                </template>
                <!-- 反馈闭环：采纳 / 不采纳 + 幻觉检测可信度 -->
                <div v-if="m.content" class="fb-row">
                  <span class="fb-label">{{
                    m.rating ? '已反馈，感谢' : '这个回答有帮助吗？'
                  }}</span>
                  <el-icon
                    :size="16"
                    class="fb-icon"
                    :class="{ on: m.rating === 'up' }"
                    @click="rateMessage(m, 'up')"
                  >
                    <Select />
                  </el-icon>
                  <el-icon
                    :size="16"
                    class="fb-icon"
                    :class="{ on: m.rating === 'down' }"
                    @click="rateMessage(m, 'down')"
                  >
                    <CloseBold />
                  </el-icon>
                  <span
                    v-if="m.faith"
                    class="faith-chip"
                    :class="m.faith.level"
                    :title="(m.faith.warnings || []).join('；') || '引用与数值一致性校验通过'"
                  >
                    可信度 {{ Math.round((m.faith.score ?? 0) * 100) }}%<template
                      v-if="m.faith.invalid_refs?.length"
                    >
                      · 引用异常</template
                    >
                  </span>
                  <span v-if="m.guard?.redacted" class="fb-tip"
                    >已脱敏 {{ m.guard.redacted }} 处</span
                  >
                  <span v-else-if="m.guard?.blocked" class="fb-tip"
                    >拦截 {{ m.guard.blocked }} 条越权片段</span
                  >
                  <span v-else-if="m.model" class="fb-tip">{{ m.model }}</span>
                </div>
              </div>
            </div>
          </div>
        </template>

        <!-- 流式状态条 -->
        <div v-if="streaming" class="row row-ai">
          <div class="status-pill">
            <span class="dot" /><span class="dot d2" /><span class="dot d3" />
            <span>{{ phaseText }}</span>
          </div>
        </div>
      </div>

      <!-- 输入区：悬浮圆角卡 -->
      <div class="input-area">
        <div v-if="attachments.length || activeSkill" class="input-tags">
          <span v-if="activeSkill" class="skill-tag-active"
            >⚡ {{ activeSkill }} <el-icon :size="12" @click="activeSkill = ''"><Close /></el-icon
          ></span>
          <span v-for="(a, i) in attachments" :key="a" class="attach-tag">
            📎 {{ a }}
            <el-icon :size="12" style="cursor: pointer" @click="attachments.splice(i, 1)"
              ><Close
            /></el-icon>
          </span>
        </div>
        <!-- 技能提示：极简占位文字 -->
        <div v-if="!activeSkill && !attachments.length" class="skill-hint">
          输入 <b>@</b> 调用技能 · 支持上传附件
        </div>
        <textarea
          v-model="draft"
          class="input-box"
          placeholder="输入需求，或 @ 调用技能，支持上传附件..."
          @input="onInput"
          @keydown="onKeydown"
        />
        <div class="input-toolbar">
          <div class="toolbar-left">
            <el-icon :size="20" class="tool-icon" @click="addAttachment">
              <Paperclip />
            </el-icon>
            <el-tooltip content="清空本会话短期记忆（长期记忆不受影响）" placement="top">
              <el-icon :size="20" class="tool-icon" @click="clearContext">
                <Delete />
              </el-icon>
            </el-tooltip>
          </div>
          <el-button
            type="primary"
            size="large"
            class="send-btn"
            round
            :disabled="!canSend || streaming"
            @click="sendDemo"
          >
            发送
          </el-button>
        </div>

        <!-- @ 技能浮层 -->
        <div v-if="showSkillMenu" class="skill-menu">
          <div class="skill-menu-title">选择已安装技能</div>
          <div v-for="s in installedSkills" :key="s" class="skill-menu-item" @click="pickSkill(s)">
            ⚡ {{ s }}
          </div>
        </div>
      </div>
    </section>
  </div>
</template>

<style scoped>
/* 整页冷灰底，左右两块白色悬浮卡 */
.chat-page {
  display: flex;
  height: 100%;
  gap: 16px;
  padding: 16px;
  background: var(--reai-bg-neutral);
}

/* 会话列表：悬浮白卡 */
.session-panel {
  width: 280px;
  flex-shrink: 0;
  background: var(--reai-card);
  border-radius: 16px;
  box-shadow: var(--reai-shadow-md);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.session-head {
  padding: 16px 14px 8px;
}
.new-btn {
  width: 100%;
  height: 40px;
  font-weight: 600;
}
.session-list {
  flex: 1;
  overflow-y: auto;
  padding: 0 10px 12px;
}
.group-title {
  font-size: 12px;
  color: var(--reai-text-muted);
  padding: 10px 6px 6px;
}
.session-item {
  height: 42px;
  border-radius: 10px;
  padding: 0 12px;
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  margin-bottom: 2px;
  transition: background 0.15s;
}
.session-item:hover {
  background: var(--reai-bg-gray);
}
.session-item:hover .session-ops {
  display: inline-flex;
}
.session-item.active {
  background: var(--reai-primary-soft);
  color: var(--reai-primary);
}
.session-title {
  flex: 1;
  font-size: 14px;
  color: inherit;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.session-time {
  font-size: 12px;
  color: var(--reai-text-muted);
  flex-shrink: 0;
}
.session-ops {
  display: none;
  gap: 6px;
  align-items: center;
  cursor: pointer;
}
.empty-mini {
  text-align: center;
  color: var(--reai-text-muted);
  font-size: 12px;
  padding: 24px 0;
}

/* 对话区：消息列居中，最大 800px */
.chat-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.msg-flow {
  flex: 1;
  overflow-y: auto;
  padding: 8px 24px 16px;
}
.msg-flow > * {
  max-width: 800px;
  margin-left: auto;
  margin-right: auto;
}
.row {
  display: flex;
  margin-bottom: 20px;
}
.row-user {
  justify-content: flex-end;
}
.row-ai {
  justify-content: flex-start;
}

.bubble {
  padding: 12px 16px;
  font-size: 15px;
  line-height: 1.6;
}
/* 用户消息：淡灰底深色文字，安静不抢戏 */
.bubble-user {
  background: var(--reai-bg-gray);
  color: var(--reai-text-main);
  border-radius: 16px 16px 4px 16px;
  max-width: 70%;
}
/* AI 消息：纯白 + 极淡阴影，浮起为视觉中心 */
.bubble-ai {
  background: var(--reai-card);
  color: var(--reai-text-main);
  border-radius: 16px 16px 16px 4px;
  max-width: 80%;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
}
.bubble-text {
  white-space: pre-wrap;
  word-break: break-word;
}
.skill-chip {
  display: inline-block;
  font-size: 12px;
  background: var(--reai-card);
  border-radius: 9999px;
  padding: 1px 10px;
  margin-bottom: 6px;
}
.attach-row {
  display: flex;
  gap: 6px;
  margin-top: 8px;
  flex-wrap: wrap;
}

.ai-wrap {
  max-width: 80%;
}
/* AI 标签：Tiny 透明底水印 */
.ai-tag {
  display: inline-block;
  font-size: 10px;
  line-height: 14px;
  color: var(--reai-text-muted);
  background: transparent;
  border-radius: 4px;
  padding: 2px 6px;
  margin-bottom: 4px;
}
.cursor {
  animation: blink 0.8s infinite;
}
@keyframes blink {
  50% {
    opacity: 0;
  }
}

/* 拒答黄条 */
.refuse-bar {
  background: var(--st-warn-bg);
  border-radius: 10px;
  padding: 12px 16px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.refuse-text {
  color: var(--st-warn-fg);
  font-size: 14px;
}

/* 户型卡片 */
.house-card {
  margin-top: 12px;
  background: var(--reai-bg-neutral);
  border-radius: 12px;
  padding: 12px 16px;
  display: flex;
  align-items: center;
  gap: 12px;
  cursor: pointer;
  transition:
    box-shadow 0.2s,
    background 0.2s;
}
.house-card:hover {
  box-shadow: var(--reai-shadow-md);
}
.house-icon {
  font-size: 28px;
}
.house-info {
  flex: 1;
}
.house-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--reai-text-main);
}
.house-sub {
  font-size: 12px;
  color: var(--reai-text-muted);
  margin-top: 2px;
}

/* 引用折叠 */
.ref-divider {
  border-top: 1px dashed var(--reai-border);
  margin: 12px 0 8px;
}
.ref-link {
  font-size: 14px;
  color: var(--reai-primary);
  cursor: pointer;
}
.ref-link:hover {
  text-decoration: underline;
}
.ref-list {
  margin-top: 8px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.ref-item {
  background: var(--reai-bg-neutral);
  border-radius: 10px;
  padding: 8px 12px;
}
.ref-doc {
  font-size: 13px;
  color: var(--reai-text-main);
  font-weight: 500;
}
.ref-page {
  font-size: 12px;
  color: var(--reai-text-muted);
  margin-left: 6px;
}
.ref-snip {
  font-size: 12px;
  color: var(--reai-text-muted);
  margin-top: 2px;
}
.ref-score {
  font-size: 11px;
  color: var(--reai-primary);
  margin-left: 6px;
}
.ref-level {
  font-size: 11px;
  color: var(--reai-primary);
  background: var(--reai-primary-soft);
  border-radius: 9999px;
  padding: 1px 8px;
  margin-left: 6px;
}
.guard-chip {
  margin-left: 8px;
  font-size: 11px;
  color: var(--reai-text-muted);
  background: var(--reai-bg-gray);
  border-radius: 9999px;
  padding: 1px 8px;
}
.guard-chip.warn {
  color: var(--reai-warning);
  background: rgba(230, 162, 60, 0.14);
}

/* 反馈闭环 */
.fb-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 10px;
  font-size: 12px;
  color: var(--reai-text-muted);
}
.fb-label {
  font-size: 12px;
  color: var(--reai-text-muted);
}
.fb-icon {
  cursor: pointer;
  color: var(--reai-text-muted);
  transition: color 0.15s;
}
.fb-icon:hover {
  color: var(--reai-primary);
}
.fb-icon.on {
  color: var(--reai-primary);
}
.fb-tip {
  margin-left: auto;
  font-size: 11px;
  color: var(--reai-text-muted);
}
.faith-chip {
  font-size: 11px;
  border-radius: 9999px;
  padding: 1px 8px;
  cursor: help;
  color: var(--reai-text-secondary);
  background: var(--reai-bg-gray);
}
.faith-chip.high {
  color: var(--reai-success);
  background: rgba(103, 194, 58, 0.14);
}
.faith-chip.medium {
  color: var(--reai-warning);
  background: rgba(230, 162, 60, 0.14);
}
.faith-chip.low {
  color: var(--reai-danger, #d66);
  background: rgba(245, 108, 108, 0.14);
}

/* 流式状态：极简进度点 */
.status-pill {
  background: transparent;
  height: 28px;
  border-radius: 9999px;
  padding: 4px 8px;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: var(--reai-text-muted);
}
.dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--reai-primary);
  animation: jump 1s infinite;
}
.d2 {
  animation-delay: 0.15s;
}
.d3 {
  animation-delay: 0.3s;
}
@keyframes jump {
  0%,
  100% {
    transform: translateY(0);
  }
  40% {
    transform: translateY(-4px);
  }
}

/* 空状态 */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding-top: 18%;
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

/* 输入区：悬浮圆角卡 */
.input-area {
  background: var(--reai-card);
  border-radius: 16px;
  box-shadow: var(--reai-shadow-md);
  padding: 10px 18px 8px;
  margin: 0 12px 16px;
  position: relative;
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
}
.input-tags {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  padding-bottom: 4px;
}
.skill-tag-active,
.attach-tag {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  background: var(--reai-bg-gray);
  border-radius: 9999px;
  padding: 3px 10px;
  color: var(--reai-text-secondary);
}
.skill-tag-active {
  background: var(--reai-primary-soft);
  color: var(--reai-primary);
}
/* 技能提示：极简占位文字 */
.skill-hint {
  font-size: 12px;
  color: var(--reai-text-muted);
  padding: 2px 2px 6px;
}
.input-box {
  flex: 1;
  border: none;
  outline: none;
  resize: none;
  min-height: 52px;
  max-height: 100px;
  font-size: 14px;
  line-height: 1.6;
  color: var(--reai-text-main);
  background: transparent;
  font-family: inherit;
}
.input-box::placeholder {
  color: var(--reai-text-muted);
}
.input-toolbar {
  height: 38px;
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.toolbar-left {
  display: flex;
  gap: 12px;
}
.tool-icon {
  cursor: pointer;
  color: var(--reai-text-secondary);
  padding: 4px;
  border-radius: 8px;
}
.tool-icon:hover {
  color: var(--reai-primary);
  background: var(--reai-primary-soft);
}
.send-btn {
  min-width: 80px;
  height: 36px;
  font-weight: 600;
}

/* @ 技能浮层 */
.skill-menu {
  position: absolute;
  bottom: calc(100% + 8px);
  left: 0;
  width: 240px;
  background: var(--reai-card);
  border-radius: 14px;
  box-shadow: var(--reai-shadow-lg);
  padding: 8px;
  z-index: 10;
}
.skill-menu-title {
  font-size: 12px;
  color: var(--reai-text-muted);
  padding: 4px 8px 8px;
}
.skill-menu-item {
  padding: 8px 12px;
  border-radius: 10px;
  font-size: 14px;
  cursor: pointer;
  color: var(--reai-text-main);
}
.skill-menu-item:hover {
  background: var(--reai-primary-soft);
  color: var(--reai-primary);
}
</style>
