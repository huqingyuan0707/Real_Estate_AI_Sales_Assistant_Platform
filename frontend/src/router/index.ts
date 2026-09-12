import { createRouter, createWebHistory } from 'vue-router';
import MainLayout from '@/layouts/MainLayout.vue';

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/login',
      name: 'login',
      component: () => import('@/views/LoginView.vue'),
      meta: { title: '登录' },
    },
    {
      path: '/',
      component: MainLayout,
      redirect: '/chat',
      children: [
        {
          path: 'chat',
          name: 'chat',
          component: () => import('@/views/ChatView.vue'),
          meta: { title: '智能对话', perm: 'chat' },
        },
        {
          path: 'house',
          name: 'house',
          component: () => import('@/views/HouseEditorView.vue'),
          meta: { title: '空间智能引擎', perm: 'house' },
        },
        {
          path: 'knowledge',
          name: 'knowledge',
          component: () => import('@/views/KnowledgeView.vue'),
          meta: { title: '知识库管理', perm: 'kb' },
        },
        // 我的 AI 服务：登录即可（不设 perm，任何角色都能配置自己的 Key）
        {
          path: 'my-ai',
          name: 'my-ai',
          component: () => import('@/views/MyAiView.vue'),
          meta: { title: '我的 AI 服务' },
        },
        {
          path: 'settings',
          name: 'settings',
          component: () => import('@/views/SettingsView.vue'),
          meta: { title: '系统设置', perm: 'settings' },
        },
        {
          path: 'skills',
          name: 'skills',
          component: () => import('@/views/SkillMarketView.vue'),
          meta: { title: 'Skill 市场', perm: 'skill' },
        },
        {
          path: 'tasks',
          name: 'tasks',
          component: () => import('@/views/TaskCenterView.vue'),
          meta: { title: '任务中心', perm: 'task' },
        },
        {
          path: 'admin/audit',
          name: 'audit',
          component: () => import('@/views/admin/AuditLogView.vue'),
          meta: { title: '审计日志', perm: 'audit' },
        },
        {
          path: 'admin/cost',
          name: 'cost',
          component: () => import('@/views/admin/CostDashboardView.vue'),
          meta: { title: '费用看板', perm: 'cost' },
        },
        {
          path: 'admin/users',
          name: 'users',
          component: () => import('@/views/admin/UserManageView.vue'),
          meta: { title: '用户管理', perm: 'user_manage' },
        },
      ],
    },
  ],
});

const BASE_PERM = 'chat'; // 所有角色都有的最低权限，作为无权限时的兜底落点

function currentPerms(): string[] {
  // 双层读取：sessionStorage 优先，丢失（新标签页/重启浏览器）时回退 localStorage
  for (const store of [sessionStorage, localStorage]) {
    try {
      const parsed = JSON.parse(store.getItem('reai_perms') ?? '[]');
      if (Array.isArray(parsed) && parsed.length) return parsed;
    } catch {
      /* 忽略损坏数据，继续下一层 */
    }
  }
  // 全部为空时兜底最低权限，避免把 /chat 也拦下造成守卫死循环（布局层会经 /auth/me 自愈补全）
  return [BASE_PERM];
}

// 登录 + RBAC 守卫：未登录跳登录页；无对应权限码回智能对话
router.beforeEach(to => {
  const authed = !!sessionStorage.getItem('reai_token');
  if (to.name !== 'login' && !authed) return { name: 'login' };
  if (to.name === 'login' && authed) return { name: BASE_PERM };
  if (to.meta.perm && !currentPerms().includes(to.meta.perm as string)) {
    // 目标就是兜底路由时直接放行，防止重定向自引用导致无限导航
    if (to.name === BASE_PERM) return true;
    return { name: BASE_PERM };
  }
  document.title = `${to.meta.title ?? ''} - 房地产AI销售助手平台`;
  return true;
});

export default router;
