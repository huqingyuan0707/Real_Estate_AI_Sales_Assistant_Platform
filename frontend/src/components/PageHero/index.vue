<script setup lang="ts">
/**
 * PageHero —— 页面英雄区（对标截图标题行）
 * 题号徽标 + 大标题 + 粉彩标签 + 副标题，右侧 slot 放操作按钮
 */
export interface HeroTag {
  text: string;
  kind?: 'blue' | 'yellow' | 'green' | 'purple' | 'red' | 'orange';
}
withDefaults(
  defineProps<{
    index: string;
    title: string;
    tags?: HeroTag[];
    sub?: string;
    compact?: boolean;
  }>(),
  { tags: () => [], sub: '', compact: false }
);
</script>

<template>
  <div class="page-hero" :class="{ compact }">
    <span class="q-badge">{{ index }}</span>
    <div class="hero-main">
      <div class="hero-title-row">
        <h2 class="hero-title">{{ title }}</h2>
        <span
          v-for="t in tags"
          :key="t.text"
          :class="['pastel-tag', `pastel-tag--${t.kind ?? 'blue'}`]"
        >
          {{ t.text }}
        </span>
      </div>
      <div v-if="sub" class="hero-sub">{{ sub }}</div>
    </div>
    <div v-if="$slots.default" class="hero-extra">
      <slot />
    </div>
  </div>
</template>

<style scoped>
.page-hero {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 16px;
}
.page-hero.compact {
  gap: 8px;
  margin-bottom: 12px;
}
.hero-main {
  flex: 1;
  min-width: 0;
}
.hero-title-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.hero-title {
  margin: 0;
  font-size: 20px;
  line-height: 28px;
  font-weight: 700;
  color: var(--reai-text-main);
}
.compact .hero-title {
  font-size: 16px;
  line-height: 24px;
}
.hero-sub {
  margin-top: 4px;
  font-size: 13px;
  line-height: 20px;
  color: var(--reai-text-muted);
}
.hero-extra {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 8px;
}
</style>
