<script setup lang="ts">
/**
 * PageSkeleton —— 页面加载骨架屏
 * variant: page（标题+3白卡）/ rows（列表行）/ table（表格行）
 * 配合路由切换 overlay 与内容区首屏加载使用
 */
withDefaults(
  defineProps<{
    variant?: 'page' | 'rows' | 'table';
    rows?: number;
  }>(),
  { variant: 'page', rows: 5 }
);
</script>

<template>
  <div class="page-skeleton" :class="`is-${variant}`">
    <el-skeleton animated :rows="rows" :loading="true">
      <template #template>
        <div v-if="variant === 'page'" class="sk-page">
          <div class="sk-hero">
            <el-skeleton-item variant="circle" style="width: 28px; height: 22px" />
            <el-skeleton-item variant="h3" style="width: 32%" />
            <el-skeleton-item variant="text" style="width: 12%" />
            <el-skeleton-item variant="text" style="width: 12%" />
          </div>
          <el-skeleton-item variant="rect" class="sk-card" />
          <el-skeleton-item variant="rect" class="sk-card" />
          <el-skeleton-item variant="rect" class="sk-card short" />
        </div>
        <div v-else-if="variant === 'table'" class="sk-table">
          <el-skeleton-item variant="h3" style="width: 100%; margin-bottom: 12px" />
          <el-skeleton-item v-for="i in rows" :key="i" variant="text" style="width: 100%" />
        </div>
        <div v-else class="sk-rows">
          <el-skeleton-item v-for="i in rows" :key="i" variant="rect" class="sk-row" />
        </div>
      </template>
    </el-skeleton>
  </div>
</template>

<style scoped>
.page-skeleton {
  width: 100%;
}
.sk-hero {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 16px;
}
.sk-card {
  width: 100%;
  height: 132px;
  border-radius: 16px;
  margin-bottom: 14px;
}
.sk-card.short {
  height: 88px;
}
.sk-table {
  background: #fff;
  border-radius: 16px;
  padding: 18px;
}
.sk-rows {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.sk-row {
  width: 100%;
  height: 64px;
  border-radius: 12px;
}
</style>
