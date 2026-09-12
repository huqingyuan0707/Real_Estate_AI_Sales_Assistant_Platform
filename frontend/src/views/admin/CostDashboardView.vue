<script setup lang="ts">
import PageHero from '@/components/PageHero/index.vue';
import * as echarts from 'echarts';
import { onMounted, onUnmounted, ref } from 'vue';
import { costStats } from '@/mock';

/* ---------------- 费用看板（规范 8.2：折线图70% + 预警横幅 + Top3榜单30%） ---------------- */
const chartEl = ref<HTMLElement>();
let chart: echarts.ECharts | null = null;

const maxTop = Math.max(...costStats.topSkills.map(s => s.cost));

onMounted(() => {
  if (!chartEl.value) return;
  chart = echarts.init(chartEl.value);
  const days = Array.from({ length: 30 }, (_, i) => `09-${String(i + 1).padStart(2, '0')}`);
  chart.setOption({
    grid: { top: 32, right: 16, bottom: 28, left: 48 },
    tooltip: { trigger: 'axis', valueFormatter: (v: number) => `¥${v.toFixed(2)}` },
    xAxis: {
      type: 'category',
      data: days,
      axisLine: { lineStyle: { color: '#E2E8F0' } },
      axisLabel: { color: '#64748B', fontSize: 11 },
    },
    yAxis: {
      type: 'value',
      name: '元',
      splitLine: { lineStyle: { color: '#F1F5F9' } },
      axisLabel: { color: '#64748B' },
    },
    series: [
      {
        type: 'line',
        data: costStats.trend,
        smooth: true,
        symbol: 'circle',
        symbolSize: 5,
        lineStyle: { color: '#6366F1', width: 2.5 },
        itemStyle: { color: '#6366F1' },
        areaStyle: {
          color: {
            type: 'linear',
            x: 0,
            y: 0,
            x2: 0,
            y2: 1,
            colorStops: [
              { offset: 0, color: 'rgba(99,102,241,0.16)' },
              { offset: 1, color: 'rgba(99,102,241,0)' },
            ],
          },
        },
      },
    ],
  });
  window.addEventListener('resize', resize);
});
const resize = () => {
  chart?.resize();
};
onUnmounted(() => {
  window.removeEventListener('resize', resize);
  chart?.dispose();
});
</script>

<template>
  <div class="cost-page">
    <PageHero
      index="09"
      title="费用看板"
      sub="Token 与第三方调用消耗 · 按工作空间归因"
      :tags="[
        { text: '用量统计', kind: 'blue' },
        { text: '成本归因', kind: 'yellow' },
      ]"
    />
    <!-- 预警细条：32px + 红点 -->
    <div v-if="costStats.budgetUsedPercent >= 80" class="alert-banner">
      <span class="alert-dot" />
      本月费用已达预算的 {{ costStats.budgetUsedPercent }}%（¥{{ costStats.monthCost.toFixed(1) }} /
      ¥{{ costStats.budget }}）
    </div>

    <div class="cost-body">
      <!-- 折线图 70% -->
      <div class="chart-card fashion-card">
        <div class="chart-title">近 30 日 Token 费用趋势</div>
        <div ref="chartEl" class="chart" />
      </div>

      <!-- 消耗榜单 30% -->
      <div class="rank-card fashion-card">
        <div class="chart-title">Skill 消耗榜单 Top 3</div>
        <div v-for="s in costStats.topSkills" :key="s.name" class="rank-item">
          <div class="rank-head">
            <span class="rank-name">{{ s.name }}</span>
            <span class="rank-cost">¥{{ s.cost.toFixed(1) }}</span>
          </div>
          <div class="rank-track">
            <div class="rank-fill" :style="{ width: (s.cost / maxTop) * 100 + '%' }" />
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.cost-page {
  padding: 0;
}
/* 预警细条：不占据过多空间 */
.alert-banner {
  height: 32px;
  display: flex;
  align-items: center;
  gap: 8px;
  background: #fef2f2;
  color: #b91c1c;
  border-radius: 8px;
  padding: 0 12px;
  font-size: 12px;
  margin-bottom: 16px;
}
.alert-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--reai-danger);
  flex-shrink: 0;
}
.cost-body {
  display: flex;
  gap: 16px;
}
.chart-card {
  width: 70%;
  background: var(--reai-card);
  border-radius: 12px;
  padding: 16px;
  box-shadow: var(--reai-shadow-sm);
}
.chart {
  height: 380px;
}
.chart-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--reai-text-main);
  margin-bottom: 12px;
}

.rank-card {
  width: 30%;
  background: var(--reai-card);
  border-radius: 12px;
  padding: 16px;
  box-shadow: var(--reai-shadow-sm);
}
.rank-item {
  margin-top: 20px;
}
.rank-head {
  display: flex;
  justify-content: space-between;
  font-size: 14px;
  color: var(--reai-text-main);
  margin-bottom: 8px;
}
.rank-cost {
  color: var(--reai-text-muted);
}
.rank-track {
  height: 10px;
  background: var(--reai-bg-gray);
  border-radius: 5px;
  overflow: hidden;
}
.rank-fill {
  height: 100%;
  background: var(--reai-primary);
  border-radius: 5px;
  transition: width 0.5s;
}
</style>
