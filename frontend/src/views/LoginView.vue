<script setup lang="ts">
import { reactive, ref } from 'vue';
import { useRouter } from 'vue-router';
import { ElMessage } from 'element-plus';

import AiInput from '@/components/AiInput/index.vue';
import { api } from '@/api';

const router = useRouter();
const activeTab = ref('local');
const loading = ref(false);

const form = reactive({ username: 'admin', password: '123456' });

const handleLogin = async () => {
  if (!form.username || !form.password) {
    ElMessage.warning('请输入账号和密码');
    return;
  }
  loading.value = true;
  try {
    const data: any = await api.login({
      username: form.username,
      password: form.password,
      mode: 'local',
    });
    sessionStorage.setItem('reai_auth', '1');
    sessionStorage.setItem('reai_token', data.token);
    sessionStorage.setItem('reai_role', data.role);
    sessionStorage.setItem('reai_username', data.name || data.username);
    sessionStorage.setItem('reai_perms', JSON.stringify(data.permissions ?? []));
    // 权限集同步落 localStorage：新标签页/重启浏览器后菜单不再丢（守卫与布局双层兜底读取）
    localStorage.setItem('reai_perms', JSON.stringify(data.permissions ?? []));
    ElMessage.success(`欢迎，${data.name || data.username}`);
    router.push('/chat');
  } catch (e: any) {
    ElMessage.error(e?.message || '登录失败，请稍后重试');
  } finally {
    loading.value = false;
  }
};
</script>

<template>
  <div class="login-page">
    <div class="login-card fashion-card">
      <div class="login-logo">
        <span class="logo-icon">🏠</span>
        <div>
          <div class="title">房地产AI销售助手平台</div>
          <div class="subtitle">AI辅助 · 人工兜底 · 私有化部署</div>
        </div>
      </div>

      <el-tabs v-model="activeTab" stretch>
        <el-tab-pane label="账号登录" name="local">
          <el-form @submit.prevent>
            <el-form-item>
              <AiInput
                v-model="form.username"
                placeholder="账号"
                size="large"
                :prefix-icon="'User'"
              />
            </el-form-item>
            <el-form-item>
              <AiInput
                v-model="form.password"
                type="password"
                placeholder="密码"
                size="large"
                show-password
                :prefix-icon="'Lock'"
              />
            </el-form-item>
            <el-button
              type="primary"
              size="large"
              style="width: 100%"
              :loading="loading"
              @click="handleLogin"
            >
              登 录
            </el-button>
          </el-form>
        </el-tab-pane>

        <el-tab-pane label="域账号登录 (LDAP)" name="ldap">
          <el-form @submit.prevent>
            <el-form-item>
              <AiInput
                placeholder="域账号 (如 CORP\\zhangsan)"
                size="large"
                :prefix-icon="'OfficeBuilding'"
              />
            </el-form-item>
            <el-form-item>
              <AiInput
                type="password"
                placeholder="域密码"
                size="large"
                show-password
                :prefix-icon="'Lock'"
              />
            </el-form-item>
            <el-button
              type="primary"
              size="large"
              style="width: 100%"
              :loading="loading"
              @click="handleLogin"
            >
              域账号登录
            </el-button>
          </el-form>
        </el-tab-pane>
      </el-tabs>

      <div class="login-footer">
        演示账号：admin/123456（管理员）· wangmin/123456（主管）· liqiang/123456（成员）
        <br />v0.1.0 设计演示 · 全链路私有化，数据不出域
      </div>
    </div>
  </div>
</template>

<style scoped>
.login-page {
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  background:
    radial-gradient(1200px 600px at 15% 10%, rgba(125, 211, 252, 0.35), transparent 60%),
    radial-gradient(1000px 700px at 85% 90%, rgba(167, 139, 250, 0.4), transparent 60%),
    linear-gradient(135deg, #1e1b4b 0%, #2b5cf5 55%, #7c3aed 100%);
}
.login-card {
  width: 420px;
  background: #fff;
  border-radius: 20px;
  padding: 40px 36px 24px;
  box-shadow: 0 24px 64px rgba(20, 26, 51, 0.4);
}
.login-logo {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 28px;
}
.logo-icon {
  font-size: 40px;
}
.title {
  font-size: 20px;
  font-weight: 700;
}
.subtitle {
  font-size: 12px;
  color: var(--reai-text-sub);
  margin-top: 2px;
}
.login-footer {
  text-align: center;
  color: var(--reai-text-sub);
  font-size: 12px;
  margin-top: 16px;
}
</style>
