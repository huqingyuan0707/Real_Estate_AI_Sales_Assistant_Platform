<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { ElMessage } from 'element-plus';
// 导航图标：ElementPlusResolver 不解析 @element-plus/icons-vue，必须显式引入
import {
  Bell,
  ChatDotRound,
  Clock,
  Collection,
  Crop,
  DArrowLeft,
  Document,
  Grid,
  HomeFilled,
  Key,
  Setting,
  TrendCharts,
} from '@element-plus/icons-vue';
import AiButton from '@/components/AiButton/index.vue';
import AiInput from '@/components/AiInput/index.vue';
import { api } from '@/api';

const route = useRoute();
const router = useRouter();

const role = sessionStorage.getItem('reai_role') ?? 'member';
const username = sessionStorage.getItem('reai_username') ?? '演示管理员';
const ROLE_NAMES: Record<string, string> = { admin: '管理员', manager: '主管', member: '成员' };
const roleTag = computed(() => ROLE_NAMES[role] ?? '成员');
const perms = ref<string[]>([]);
// 双层读取：sessionStorage 优先，丢失（新标签页/重启浏览器）回退 localStorage
for (const store of [sessionStorage, localStorage]) {
  try {
    const parsed = JSON.parse(store.getItem('reai_perms') ?? '[]');
    if (Array.isArray(parsed) && parsed.length) {
      perms.value = parsed;
      break;
    }
  } catch {
    /* 损坏数据忽略，尝试下一层 */
  }
}
const has = (p: string) => perms.value.includes(p);

// 会话自愈：权限缓存为空但 token 还在时，按 token 重取权限集并写回双存储，菜单实时恢复
onMounted(async () => {
  if (perms.value.length || !sessionStorage.getItem('reai_token')) return;
  try {
    const me = await api.authMe();
    perms.value = me.permissions ?? [];
    sessionStorage.setItem('reai_perms', JSON.stringify(perms.value));
    localStorage.setItem('reai_perms', JSON.stringify(perms.value));
    if (me.role) {
      sessionStorage.setItem('reai_role', me.role);
      localStorage.setItem('reai_role', me.role);
    }
    if (me.name) sessionStorage.setItem('reai_username', me.name);
  } catch {
    /* token 失效时 request 层统一清登录态并跳登录页 */
  }
});
const pageTitle = computed(() => (route.meta.title as string) ?? '');
const isChatRoute = computed(() => route.name === 'chat');
const searchKw = ref('');
const pendingTaskCount = 2;
const netBroken = ref(false);
const collapsed = ref(true); // 原则一：导航默认收起为图标模式

function reconnect() {
  netBroken.value = false;
  ElMessage.success('网络已恢复');
}

function onUserCommand(cmd: string) {
  if (cmd === 'settings') router.push('/my-ai');
  else if (cmd === 'logout') {
    sessionStorage.clear();
    router.push('/login');
  }
}

function onSearch() {
  if (!searchKw.value.trim()) return;
  ElMessage.info(`全局搜索（演示）：${searchKw.value}`);
}

function goTasks() {
  router.push('/tasks');
}
</script>

<template>
  <el-container class="layout">
    <!-- 左侧导航：白色悬浮，默认 64px 图标模式，可展开 220px -->
    <el-aside :width="collapsed ? '64px' : '220px'" class="sidebar" :class="{ collapsed }">
      <div class="logo" @click="collapsed = !collapsed">
        <span class="logo-icon">
          <el-icon :size="20" color="var(--reai-primary)"><HomeFilled /></el-icon>
        </span>
        <span v-if="!collapsed" class="logo-text">AI销售助手</span>
        <el-icon v-if="!collapsed" :size="14" class="fold-arrow" color="var(--reai-text-muted)">
          <DArrowLeft />
        </el-icon>
      </div>

      <el-menu
        class="menu"
        :default-active="route.path"
        router
        :collapse="collapsed"
        :collapse-transition="false"
      >
        <el-menu-item v-if="has('chat')" index="/chat">
          <el-icon><ChatDotRound /></el-icon><template #title> 智能对话 </template>
        </el-menu-item>
        <el-menu-item v-if="has('house')" index="/house">
          <el-icon><Crop /></el-icon><template #title> 空间智能引擎 </template>
        </el-menu-item>
        <el-menu-item v-if="has('kb')" index="/knowledge">
          <el-icon><Collection /></el-icon><template #title> 知识库管理 </template>
        </el-menu-item>
        <el-menu-item v-if="has('skill')" index="/skills">
          <el-icon><Grid /></el-icon><template #title> Skill 市场 </template>
        </el-menu-item>
        <el-menu-item v-if="has('task')" index="/tasks">
          <el-icon><Clock /></el-icon><template #title> 任务中心 </template>
        </el-menu-item>
        <el-menu-item index="/my-ai">
          <el-icon><Key /></el-icon><template #title> 我的 AI 服务 </template>
        </el-menu-item>
        <el-menu-item v-if="has('settings')" index="/settings">
          <el-icon><Setting /></el-icon><template #title> 系统设置 </template>
        </el-menu-item>
        <template v-if="has('audit') || has('cost') || has('user_manage')">
          <div class="menu-divider" />
          <el-menu-item v-if="has('audit')" index="/admin/audit">
            <el-icon><Document /></el-icon><template #title> 审计日志 </template>
          </el-menu-item>
          <el-menu-item v-if="has('cost')" index="/admin/cost">
            <el-icon><TrendCharts /></el-icon><template #title> 费用看板 </template>
          </el-menu-item>
          <el-menu-item v-if="has('user_manage')" index="/admin/users">
            <el-icon><Setting /></el-icon><template #title> 用户管理 </template>
          </el-menu-item>
        </template>
      </el-menu>
      <!-- 角标：collapse 模式下菜单文字隐藏，角标独立浮在任务中心图标上 -->
      <span
        v-if="pendingTaskCount"
        class="collapse-badge"
        :class="{ hidden: !collapsed }"
        @click="goTasks"
        >{{ pendingTaskCount }}</span
      >

      <div class="sidebar-user">
        <el-dropdown @command="onUserCommand">
          <div class="sidebar-user-inner" :class="{ center: collapsed }">
            <el-avatar :size="32" style="background: var(--reai-primary); flex-shrink: 0">
              {{ username.slice(0, 1) }}
            </el-avatar>
            <div v-if="!collapsed" class="sidebar-user-info">
              <div class="name">
                {{ username }}
              </div>
              <div class="role-tag">
                {{ roleTag }}
              </div>
            </div>
          </div>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="settings"> 我的 AI 服务 </el-dropdown-item>
              <el-dropdown-item command="logout" divided> 退出登录 </el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
    </el-aside>

    <el-container class="right-wrap">
      <div v-if="netBroken" class="net-banner">
        <span>网络已断开，请检查连接</span>
        <AiButton size="small" round @click="reconnect"> 重新连接 </AiButton>
      </div>

      <!-- 顶部状态栏 -->
      <el-header height="64px" class="topbar">
        <div class="topbar-title h1">
          {{ pageTitle }}
        </div>
        <div class="topbar-right">
          <AiInput
            v-model="searchKw"
            placeholder="搜索..."
            style="width: 240px"
            :prefix-icon="'Search'"
            round
            @keyup.enter="onSearch"
          />
          <el-badge :value="pendingTaskCount" :offset="[-4, 4]">
            <el-icon :size="20" class="topbar-icon" @click="goTasks">
              <Bell />
            </el-icon>
          </el-badge>
          <el-dropdown @command="onUserCommand">
            <el-avatar :size="32" style="background: var(--reai-primary); cursor: pointer">
              {{ username.slice(0, 1) }}
            </el-avatar>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="settings"> 我的 AI 服务 </el-dropdown-item>
                <el-dropdown-item command="logout" divided> 退出登录 </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </el-header>

      <el-main class="main" :class="{ 'main-flush': isChatRoute }">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<style scoped>
.layout {
  height: 100%;
}

/* 白色悬浮侧栏，轻阴影无重边框 */
.sidebar {
  background: var(--reai-card);
  box-shadow: var(--reai-shadow-md);
  display: flex;
  flex-direction: column;
  transition: width 0.25s ease;
  position: relative;
  z-index: 5;
}
.logo {
  height: 60px;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0 14px;
  cursor: pointer;
  color: var(--reai-text-main);
  font-weight: 600;
  font-size: 16px;
  flex-shrink: 0;
}
.collapsed .logo {
  justify-content: center;
  padding: 0;
}
.logo-icon {
  width: 34px;
  height: 34px;
  border-radius: 10px;
  background: var(--reai-primary-soft);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.logo-text {
  white-space: nowrap;
  overflow: hidden;
}
.fold-arrow {
  margin-left: auto;
}

.menu {
  border-right: none;
  flex: 1;
  margin-top: 8px;
  padding: 0 8px;
  overflow: hidden;
}
.menu:not(.el-menu--collapse) {
  padding: 0 8px;
  width: 100%;
}
.menu :deep(.el-menu-item) {
  height: 42px;
  margin: 2px 0;
  border-radius: 10px;
  color: var(--reai-text-secondary);
  font-size: 14px;
}
.menu :deep(.el-menu-item:hover) {
  background: var(--reai-bg-gray);
  color: var(--reai-text-main);
}
.menu :deep(.el-menu-item.is-active) {
  background: var(--reai-primary-soft);
  color: var(--reai-primary);
  font-weight: 600;
}
.menu-divider {
  border-top: 1px solid var(--reai-border);
  margin: 8px 6px;
}

/* 折叠态任务角标 */
.collapse-badge {
  display: none;
  position: absolute;
  left: 44px;
  top: 266px;
  min-width: 15px;
  height: 15px;
  line-height: 15px;
  text-align: center;
  font-size: 10px;
  background: var(--reai-danger);
  color: #fff;
  border-radius: 9999px;
  padding: 0 4px;
  cursor: pointer;
  z-index: 6;
}
.collapse-badge.hidden {
  display: none;
}
.sidebar.collapsed .collapse-badge {
  display: block;
}

.sidebar-user {
  border-top: 1px solid var(--reai-border);
  padding: 8px;
  flex-shrink: 0;
}
.sidebar-user-inner {
  display: flex;
  align-items: center;
  gap: 10px;
  cursor: pointer;
  width: 100%;
  border-radius: 10px;
  padding: 4px;
}
.sidebar-user-inner.center {
  justify-content: center;
}
.sidebar-user-inner:hover {
  background: var(--reai-bg-gray);
}
.sidebar-user-info {
  white-space: nowrap;
  overflow: hidden;
}
.sidebar-user-info .name {
  color: var(--reai-text-main);
  font-size: 14px;
  font-weight: 500;
}
.sidebar-user-info .role-tag {
  color: var(--reai-text-muted);
  font-size: 12px;
}

.right-wrap {
  height: 100%;
  overflow: hidden;
  background: var(--reai-bg-neutral);
}
.net-banner {
  height: 40px;
  background: #fee2e2;
  color: #991b1b;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 16px;
  font-size: 14px;
}

.topbar {
  background: rgba(255, 255, 255, 0.85);
  backdrop-filter: blur(8px);
  border-bottom: 1px solid var(--reai-border);
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.topbar-title {
  color: var(--reai-text-main);
  letter-spacing: 0.2px;
}
.topbar-right {
  display: flex;
  align-items: center;
  gap: 20px;
}
.topbar-icon {
  cursor: pointer;
  color: var(--reai-text-secondary);
}
.topbar-icon:hover {
  color: var(--reai-primary);
}

.main {
  background: var(--reai-bg-neutral);
  padding: 24px;
  overflow: auto;
}
.main-flush {
  padding: 0;
  overflow: hidden;
}
</style>
