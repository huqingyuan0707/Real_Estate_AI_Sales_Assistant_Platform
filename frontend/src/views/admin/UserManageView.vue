<script setup lang="ts">
import PageHero from '@/components/PageHero/index.vue';
import { onMounted, reactive, ref } from 'vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import { api } from '@/api';

/* ---------------- 用户管理（RBAC：真实接口，admin/manager/member 三角色） ---------------- */
const rows = ref<any[]>([]);
const loaded = ref(false);
const workspaceOptions = ref<string[]>([]);
const dialogVisible = ref(false);
const editing = ref<any>(null);
const form = reactive({
  name: '',
  username: '',
  role: 'member',
  workspace: '',
  initial_password: '123456',
});

const ROLE_NAMES: Record<string, string> = { admin: '管理员', manager: '主管', member: '成员' };

const load = async () => {
  try {
    const data: any = await api.listUsers();
    rows.value = data.users ?? [];
    workspaceOptions.value = data.workspaces ?? [];
  } catch (e: any) {
    ElMessage.error(e?.message || '用户列表加载失败');
  } finally {
    loaded.value = true;
  }
};
onMounted(load);

const openCreate = () => {
  editing.value = null;
  Object.assign(form, {
    name: '',
    username: '',
    role: 'member',
    workspace: workspaceOptions.value[0] ?? '',
    initial_password: '123456',
  });
  dialogVisible.value = true;
};
const openEdit = (u: any) => {
  editing.value = u;
  Object.assign(form, {
    name: u.name,
    username: u.username,
    role: u.role,
    workspace: u.workspace,
    initial_password: '',
  });
  dialogVisible.value = true;
};
const submit = async () => {
  if (
    !editing.value &&
    (!form.name.trim() || !form.username.trim() || !form.initial_password.trim())
  ) {
    ElMessage.warning('姓名、账号与初始密码为必填项');
    return;
  }
  try {
    if (editing.value) {
      // 编辑仅允许调整角色（资料修改走个人设置）
      await api.updateUser(editing.value.username, { role: form.role });
      ElMessage.success('已保存');
    } else {
      await api.createUser({
        username: form.username,
        display_name: form.name,
        role: form.role,
        workspace: form.workspace,
        initial_password: form.initial_password,
      });
      ElMessage.success('用户已添加');
    }
    dialogVisible.value = false;
    await load();
  } catch (e: any) {
    ElMessage.error(e?.message || '操作失败');
  }
};
const resetPwd = (u: any) => {
  ElMessageBox.confirm(`确认将「${u.name}」的密码重置为初始密码 123456？`, '重置密码', {
    type: 'warning',
    confirmButtonText: '重置',
    cancelButtonText: '取消',
  })
    .then(async () => {
      await api.updateUser(u.username, { reset_password: true });
      ElMessage.success('密码已重置为 123456');
    })
    .catch(() => {});
};
const toggleStatus = (u: any) => {
  const disable = u.status === 'active';
  ElMessageBox.confirm(
    disable ? `禁用后「${u.name}」将无法登录，确认禁用？` : `确认恢复「${u.name}」的访问权限？`,
    disable ? '停用账号' : '启用账号',
    { type: 'warning', confirmButtonText: disable ? '停用' : '启用', cancelButtonText: '取消' }
  )
    .then(async () => {
      await api.updateUser(u.username, { status: disable ? 'disabled' : 'active' });
      ElMessage.success(disable ? '已停用' : '已启用');
      await load();
    })
    .catch(() => {});
};
const removeUser = (u: any) => {
  ElMessageBox.confirm(`确认删除用户「${u.name}」？该操作不可恢复。`, '删除用户', {
    type: 'warning',
    confirmButtonText: '删除',
    cancelButtonText: '取消',
  })
    .then(async () => {
      await api.deleteUser(u.username);
      ElMessage.success('用户已删除');
      await load();
    })
    .catch(() => {});
};
</script>

<template>
  <div class="user-page">
    <PageHero
      index="10"
      title="用户管理"
      sub="账号 · 角色 · 部门 · 启停，一个页面管完"
      :tags="[
        { text: '账号体系', kind: 'blue' },
        { text: 'RBAC', kind: 'purple' },
      ]"
    />
    <div class="user-toolbar">
      <el-button type="primary" style="height: 40px" @click="openCreate"> 添加用户 </el-button>
    </div>

    <div class="fashion-card" style="padding: 10px 10px 6px">
    <el-skeleton :loading="!loaded" animated>
      <template #default>
    <el-table
      :data="rows"
        class="user-table"
        :header-cell-style="{
          background: '#F8FAFC',
          color: '#64748B',
          fontSize: '12px',
          height: '44px',
        }"
        :row-style="{ height: '52px', fontSize: '14px' }"
      >
        <el-table-column prop="name" label="姓名" width="120" />
        <el-table-column prop="username" label="账号" width="140" />
        <el-table-column label="角色" width="110">
          <template #default="{ row }">
            <span class="role-tag" :class="`role-${row.role}`">{{
              ROLE_NAMES[row.role] ?? row.role
            }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="workspace" label="所属部门" width="140" />
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <span class="status-dot" :class="row.status === 'active' ? 'on' : 'off'" />
            {{ row.status === 'active' ? '启用' : '禁用' }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="260">
          <template #default="{ row }">
            <el-button text type="primary" size="small" @click="openEdit(row)"> 编辑 </el-button>
            <el-button text size="small" style="color: #64748b" @click="resetPwd(row)">
              重置密码
            </el-button>
            <el-button
              text
              size="small"
              :style="{ color: row.status === 'active' ? '#EF4444' : '#10B981' }"
              @click="toggleStatus(row)"
            >
              {{ row.status === 'active' ? '停用' : '启用' }}
            </el-button>
            <el-button text size="small" style="color: #ef4444" @click="removeUser(row)">
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>
      </template>
    </el-skeleton>
    </div>

    <!-- 添加/编辑弹窗（编辑模式仅允许调整角色） -->
    <el-dialog v-model="dialogVisible" :title="editing ? '编辑用户' : '添加用户'" width="480px">
      <el-form label-width="80px" label-position="left">
        <el-form-item label="姓名" required>
          <el-input v-model="form.name" placeholder="如：王敏" :disabled="!!editing" />
        </el-form-item>
        <el-form-item label="账号" required>
          <el-input v-model="form.username" placeholder="如：wangmin" :disabled="!!editing" />
        </el-form-item>
        <el-form-item v-if="!editing" label="初始密码" required>
          <el-input v-model="form.initial_password" placeholder="默认 123456" />
        </el-form-item>
        <el-form-item label="角色">
          <el-radio-group v-model="form.role">
            <el-radio value="admin"> 管理员 </el-radio>
            <el-radio value="manager"> 主管 </el-radio>
            <el-radio value="member"> 成员 </el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="所属部门">
          <el-select v-model="form.workspace" style="width: 100%" :disabled="!!editing">
            <el-option v-for="w in workspaceOptions" :key="w" :label="w" :value="w" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false"> 取消 </el-button>
        <el-button type="primary" @click="submit"> 保存 </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.user-page {
  padding: 0;
}
.user-toolbar {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 16px;
}
.user-table {
  width: 100%;
}
.user-table :deep(.el-table__row:hover > td) {
  background: var(--reai-bg-neutral) !important;
}

.role-tag {
  border-radius: 4px;
  padding: 2px 10px;
  font-size: 12px;
}
.role-admin {
  background: var(--reai-primary-50);
  color: var(--reai-primary);
}
.role-manager {
  background: #fef3c7;
  color: #b45309;
}
.role-member {
  background: var(--reai-bg-gray);
  color: var(--reai-text-muted);
}

.status-dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  margin-right: 6px;
}
.status-dot.on {
  background: var(--reai-success);
}
.status-dot.off {
  background: var(--reai-text-muted);
}
</style>
