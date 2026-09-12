<script setup lang="ts">
import { computed, reactive, ref } from 'vue';
import { ElMessage } from 'element-plus';
import AiButton from '@/components/AiButton/index.vue';
import { api } from '@/api';

/* ============================================================
 * AI 空间智能引擎 · 一键装修图
 * 上传毛坯照片 + 业主家具 + 墙色地面 → AI 三步生成效果图
 * （看懂空间 → 构思布局 → 渲染效果，后端流水线自动完成）
 * ============================================================ */
const STYLES = [
  { key: 'modern', name: '现代简约', emoji: '🛋️', desc: '干净利落，适合年轻客群' },
  { key: 'chinese', name: '新中式', emoji: '🫖', desc: '温润木质感，东方韵味' },
  { key: 'light', name: '轻奢风', emoji: '✨', desc: '金属点缀，改善客群首选' },
  { key: 'wood', name: '原木风', emoji: '🌿', desc: '自然温馨，育儿家庭偏好' },
];
const SCENES = [
  { key: 'living_room', label: '客厅' },
  { key: 'master_bedroom', label: '主卧' },
  { key: 'dining_room', label: '餐厅' },
] as const;
const styleKey = ref('modern');
const scene = ref('living_room');

/* ---- 毛坯房照片（图生图基准，结构保持） ---- */
const photoDataUrl = ref('');
const photoB64 = ref('');
const photoSize = reactive({ w: 0, h: 0 });
const photoName = ref('');
const fileInput = ref<HTMLInputElement | null>(null);

function pickPhoto() {
  fileInput.value?.click();
}
function onPhotoChange(e: Event) {
  const input = e.target as HTMLInputElement;
  const file = input.files?.[0];
  if (!file) return;
  if (file.size > 8 * 1024 * 1024) {
    ElMessage.warning('照片不能超过 8MB');
    input.value = '';
    return;
  }
  photoName.value = file.name;
  const reader = new FileReader();
  reader.onload = () => {
    const url = reader.result as string;
    photoDataUrl.value = url;
    photoB64.value = url.split(',')[1] ?? '';
    const img = new Image();
    img.onload = () => {
      photoSize.w = img.naturalWidth;
      photoSize.h = img.naturalHeight;
    };
    img.src = url;
  };
  reader.readAsDataURL(file);
}
function clearPhoto() {
  photoDataUrl.value = '';
  photoB64.value = '';
  photoName.value = '';
  if (fileInput.value) fileInput.value.value = '';
}

/* ---- 业主家具清单（摆进效果图的家具，按区域分组） ----
 * 数据源：后端家具清单库 GET /furniture/catalog（内置 5 分类 32 项 + 自定义项），
 * 与渲染层共用同一份数据，保证"勾选 → 提交 → 成图"名称一致。 */
interface FurnItem {
  id: string;
  name: string;
  en: string;
  category: string;
  aliases: string[];
  builtin: boolean;
}
interface FurnCategory {
  id: string;
  name: string;
  builtin: boolean;
}
const FURNITURE_GROUPS = ref<
  { group: string; groupId: string; items: { key: string; label: string }[] }[]
>([]);
const catalogLoaded = ref(false);
const pickedFurniture = ref<string[]>([]);
function toggleFurniture(key: string) {
  const i = pickedFurniture.value.indexOf(key);
  if (i >= 0) pickedFurniture.value.splice(i, 1);
  else pickedFurniture.value.push(key);
}

/* 加载清单库：按分类分组渲染 chips；失败时回退内置静态分组，保证页面可用 */
const FALLBACK_GROUPS: { group: string; items: { key: string; label: string }[] }[] = [
  {
    group: '客餐厅',
    items: [
      { key: 'corner_sofa', label: '转角沙发' },
      { key: 'sofa', label: '沙发' },
      { key: 'coffee_table', label: '茶几' },
      { key: 'dining_table', label: '餐桌' },
      { key: 'dining_chair', label: '餐椅' },
      { key: 'tv', label: '电视机' },
      { key: 'tv_cabinet', label: '电视柜' },
      { key: 'sideboard', label: '餐边柜' },
      { key: 'wine_cabinet', label: '酒柜' },
    ],
  },
  {
    group: '卧室',
    items: [
      { key: 'bed', label: '大床' },
      { key: 'bedside_table', label: '床头柜' },
      { key: 'wardrobe', label: '衣柜' },
      { key: 'dresser', label: '五斗柜' },
      { key: 'vanity', label: '梳妆台' },
      { key: 'baby_crib', label: '婴儿床' },
    ],
  },
  {
    group: '书房',
    items: [
      { key: 'bookshelf', label: '书架' },
      { key: 'desk', label: '书桌' },
      { key: 'office_chair', label: '人体工学椅' },
    ],
  },
  {
    group: '家电',
    items: [
      { key: 'fridge', label: '冰箱' },
      { key: 'ac', label: '空调' },
      { key: 'washer', label: '洗衣机' },
      { key: 'water_heater', label: '热水器' },
      { key: 'microwave', label: '微波炉' },
      { key: 'oven', label: '烤箱' },
      { key: 'dishwasher', label: '洗碗机' },
    ],
  },
  {
    group: '软装',
    items: [
      { key: 'carpet', label: '地毯' },
      { key: 'curtain', label: '窗帘' },
      { key: 'potted_plant', label: '盆栽' },
      { key: 'floor_lamp', label: '落地灯' },
      { key: 'wall_art', label: '装饰挂画' },
      { key: 'full_mirror', label: '全身镜' },
      { key: 'treadmill', label: '跑步机' },
    ],
  },
];
async function loadCatalog() {
  try {
    const data: any = await api.furnitureCatalog();
    const cats: FurnCategory[] = data.categories ?? [];
    const items: FurnItem[] = data.items ?? [];
    FURNITURE_GROUPS.value = cats
      .map(c => ({
        group: c.name,
        groupId: c.id,
        items: items.filter(i => i.category === c.id).map(i => ({ key: i.id, label: i.name })),
      }))
      .filter(g => g.items.length);
    catalogLoaded.value = true;
  } catch {
    FURNITURE_GROUPS.value = FALLBACK_GROUPS.map(g => ({ ...g, groupId: '' }));
  }
}
loadCatalog();

/* ---- 业主清单 AI 解析：粘贴文字 / 拍照 → 结构化条目 → 自动勾选 ---- */
const parseDialog = ref(false);
const parseText = ref('');
const parsePhoto = ref<File | null>(null);
const parsePhotoUrl = ref('');
const parseLoading = ref(false);
const parseResult = ref<{
  source: string;
  ocr: boolean;
  note: string;
  items: { name: string; count: string; catalog_id: string; in_catalog: boolean }[];
} | null>(null);
const parsePhotoInput = ref<HTMLInputElement | null>(null);
function pickParsePhoto() {
  parsePhotoInput.value?.click();
}
function onParsePhotoChange(e: Event) {
  const input = e.target as HTMLInputElement;
  const file = input.files?.[0];
  if (!file) return;
  if (file.size > 8 * 1024 * 1024) {
    ElMessage.warning('清单照片不能超过 8MB');
    input.value = '';
    return;
  }
  parsePhoto.value = file;
  parsePhotoUrl.value = URL.createObjectURL(file);
}
function clearParsePhoto() {
  parsePhoto.value = null;
  parsePhotoUrl.value = '';
  if (parsePhotoInput.value) parsePhotoInput.value.value = '';
}
async function runParse() {
  if (!parseText.value.trim() && !parsePhoto.value) {
    ElMessage.warning('请粘贴清单文字或上传清单照片');
    return;
  }
  parseLoading.value = true;
  parseResult.value = null;
  try {
    const data: any = await api.furnitureParse(parseText.value, parsePhoto.value ?? undefined);
    parseResult.value = data;
    if (data?.note) ElMessage.info(data.note);
  } catch (e: any) {
    ElMessage.error(e?.message || '清单解析失败');
  } finally {
    parseLoading.value = false;
  }
}
function applyParse() {
  if (!parseResult.value) return;
  const hits = parseResult.value.items.filter(i => i.catalog_id && i.in_catalog);
  if (!hits.length) {
    ElMessage.warning('解析结果未命中清单库，请手动勾选家具');
    return;
  }
  hits.forEach(h => {
    if (!pickedFurniture.value.includes(h.catalog_id)) pickedFurniture.value.push(h.catalog_id);
  });
  parseDialog.value = false;
  ElMessage.success(`已勾选 ${hits.length} 件清单家具`);
}

/* ---- 自定义家具管理：新增 / 删除（内置项禁删） ---- */
const addDialog = ref(false);
const addName = ref('');
const addCategory = ref('');
const addEn = ref('');
const addAliases = ref('');
async function openAddDialog() {
  addName.value = '';
  addEn.value = '';
  addAliases.value = '';
  addCategory.value = FURNITURE_GROUPS.value[0]?.groupId ?? '';
  addDialog.value = true;
}
async function submitAddItem() {
  if (!addName.value.trim()) {
    ElMessage.warning('请输入家具名称');
    return;
  }
  if (!addCategory.value) {
    ElMessage.warning('请选择所属分类');
    return;
  }
  try {
    await api.furnitureAddItem({
      name: addName.value.trim(),
      category: addCategory.value,
      en: addEn.value.trim(),
      aliases: addAliases.value.split(/[,，、\s]+/).filter(Boolean),
    });
    ElMessage.success('家具已添加');
    addDialog.value = false;
    await loadCatalog();
  } catch (e: any) {
    ElMessage.error(e?.message || '添加失败');
  }
}
async function removeFurnitureItem(id: string) {
  try {
    await api.furnitureDeleteItem(id);
    ElMessage.success('家具已删除');
    pickedFurniture.value = pickedFurniture.value.filter(k => k !== id);
    await loadCatalog();
  } catch (e: any) {
    ElMessage.error(e?.message || '删除失败');
  }
}

/* ---- 墙面颜色色卡 ---- */
const WALL_COLORS = [
  { key: 'white', label: '奶白色', hex: '#F5F1E8' },
  { key: 'cream', label: '奶油色', hex: '#F0E4CE' },
  { key: 'beige', label: '大地米', hex: '#D9C7A7' },
  { key: 'gray', label: '高级灰', hex: '#9AA3AC' },
  { key: 'green', label: '复古绿', hex: '#5F7A61' },
  { key: 'blue', label: '雾霾蓝', hex: '#7C93A6' },
  { key: 'terracotta', label: '陶土橙', hex: '#C4703F' },
];
const wallKey = ref('cream');

/* ---- 地面材质 ---- */
const FLOORS = [
  { key: 'polished_tile', label: '抛光瓷砖' },
  { key: 'marble_tile', label: '大理石纹砖' },
  { key: 'oak_floor', label: '橡木地板' },
  { key: 'walnut_floor', label: '胡桃木地板' },
  { key: 'cement_tile', label: '水泥灰砖' },
];
const floorKey = ref('polished_tile');

/* ---- 装修自由度（img2img strength：越低越贴近毛坯原图结构，越高 AI 发挥越大） ---- */
const strength = ref(0.75);
const generating = ref(false);
const genProgress = ref(0);
const generated = ref(false);
const genPhaseText = ref('正在理解空间结构...');
const spaceResult = ref<any>(null); // ① 看懂空间：VLM 结构化识别结果
const layoutResult = ref<any>(null); // ② 构思布局：LLM 家具摆放方案
const renderMode = ref(''); // cloud / comfyui / simulate（后端自动判定）
const remotePalette = ref<string[]>([]);
const genImageUrl = ref(''); // 云端/ComfyUI 真实成图 URL
const GEN_PHASES = ['正在理解空间结构...', '正在布置灯光与材质...', '正在渲染高清效果图...'];
// 渲染效果：真实模式取后端色板，演示回退按风格本地映射
const RENDER_STYLE: Record<string, string> = {
  modern: 'linear-gradient(135deg,#dfe7ee 0%,#c3d0dc 45%,#eef2f6 100%)',
  chinese: 'linear-gradient(135deg,#efe3d3 0%,#d4b896 50%,#f4ece0 100%)',
  light: 'linear-gradient(135deg,#e8e4dc 0%,#cbb68f 45%,#f2eee6 100%)',
  wood: 'linear-gradient(135deg,#f0e8da 0%,#d9c4a3 50%,#f6f1e8 100%)',
};
const stageBg = computed(() => {
  const p = remotePalette.value;
  if (p?.length >= 3) return `linear-gradient(135deg,${p[0]} 0%,${p[1]} 50%,${p[2]} 100%)`;
  return RENDER_STYLE[styleKey.value];
});

function localSimulate() {
  generating.value = true;
  generated.value = false;
  genProgress.value = 0;
  const timer = setInterval(() => {
    genProgress.value += 2;
    if (genProgress.value >= 100) {
      clearInterval(timer);
      genProgress.value = 100;
      generating.value = false;
      generated.value = true;
    }
  }, 60);
}

async function generate() {
  if (generating.value) return;
  generating.value = true;
  generated.value = false;
  genProgress.value = 0;
  genPhaseText.value = GEN_PHASES[0];
  spaceResult.value = null;
  layoutResult.value = null;
  remotePalette.value = [];
  genImageUrl.value = '';
  try {
    // 主链路：multipart 表单提交（毛坯照片 + 家具/墙色/地面 → 图生图；无照片走文生图）
    const fd = new FormData();
    fd.append('house_task_id', 'local-demo');
    fd.append('layout_plan', 'normal');
    fd.append('style', styleKey.value);
    fd.append('scene', scene.value);
    fd.append('resolution', '2k');
    fd.append('furniture', JSON.stringify(pickedFurniture.value));
    fd.append('wall_color', wallKey.value);
    fd.append('floor_style', floorKey.value);
    fd.append('strength', String(strength.value));
    if (photoB64.value) {
      const bin = atob(photoB64.value);
      const bytes = new Uint8Array(bin.length);
      for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
      fd.append('photo', new Blob([bytes], { type: 'image/png' }), 'room.png');
      fd.append('photo_width', String(photoSize.w || 1280));
      fd.append('photo_height', String(photoSize.h || 960));
    }
    const data = await api.renderGenerate(fd);
    const poll = setInterval(async () => {
      try {
        const st = await api.renderStatus(data.task_id);
        renderMode.value = st.mode;
        genProgress.value = st.progress;
        if (st.phase) genPhaseText.value = st.phase;
        if (st.status === 'done') {
          clearInterval(poll);
          remotePalette.value = st.palette ?? [];
          spaceResult.value = st.space_result ?? null;
          layoutResult.value = st.layout_result ?? null;
          genImageUrl.value = st.image_url ?? '';
          generating.value = false;
          generated.value = true;
          if (!genImageUrl.value)
            ElMessage.info('当前为演示模式：配置生图 API Key 或启动 ComfyUI 可获得真实效果图');
        } else if (st.status === 'failed') {
          clearInterval(poll);
          generating.value = false;
          ElMessage.error('渲染失败，已回退本地演示');
          localSimulate();
        }
      } catch {
        clearInterval(poll);
        generating.value = false;
        localSimulate();
      }
    }, 400);
  } catch {
    localSimulate(); // 网络异常：本地模拟保底
  }
}
function download() {
  if (genImageUrl.value) {
    window.open(genImageUrl.value, '_blank');
    ElMessage.success('已打开原图，右键或浏览器下载按钮保存');
  } else {
    ElMessage.info('演示模式无实体文件：配置生图 API Key 或启动 ComfyUI 后可下载成图');
  }
}

/* ---------------- 生成历史（后端持久化，重启不丢） ---------------- */
const historyVisible = ref(false);
const historyLoading = ref(false);
const historyItems = ref<any[]>([]);
const historyTotal = ref(0);
const historyPage = ref(1);
const MODE_NAMES: Record<string, string> = { cloud: '云端', comfyui: 'ComfyUI', simulate: '演示' };

async function loadHistory(page = 1) {
  historyPage.value = page;
  historyLoading.value = true;
  try {
    const data: any = await api.renderHistory({ page, page_size: 12 });
    historyItems.value = data.items ?? [];
    historyTotal.value = data.total ?? 0;
  } catch (e: any) {
    ElMessage.error(e?.message || '历史记录加载失败');
  } finally {
    historyLoading.value = false;
  }
}
function openHistory() {
  historyVisible.value = true;
  loadHistory(1);
}
function viewImage(url: string) {
  window.open(url, '_blank');
}
async function removeHistory(taskId: string) {
  try {
    await api.renderDeleteHistory(taskId);
    ElMessage.success('记录已删除');
    loadHistory(historyPage.value);
  } catch (e: any) {
    ElMessage.error(e?.message || '删除失败');
  }
}
</script>

<template>
  <div class="engine-page">
    <!-- ============ AI 一键装修图 ============ -->

    <div class="step-body single">
      <div class="pane render-pane">
        <div class="render-head">
          <span class="edit-title">效果图预览</span>
          <div class="render-head-right">
            <span class="status-line">
              {{ SCENES.find(s => s.key === scene)?.label }} ·
              {{ STYLES.find(s => s.key === styleKey)?.name }} ·
              {{ WALL_COLORS.find(w => w.key === wallKey)?.label }}墙 ·
              {{ FLOORS.find(f => f.key === floorKey)?.label }}
              <template v-if="pickedFurniture.length">
                · 家具 {{ pickedFurniture.length }} 件</template
              >
              <template v-if="photoDataUrl"> · 图生图</template>
              <template v-if="renderMode">
                ·
                {{
                  renderMode === 'cloud'
                    ? '云端 AI 生成'
                    : renderMode === 'comfyui'
                      ? 'ComfyUI 真实渲染'
                      : '演示模式'
                }}</template
              >
            </span>
            <AiButton text type="primary" size="small" @click="openHistory"> 生成历史 </AiButton>
          </div>
        </div>

        <div
          class="render-stage"
          :style="{ background: generated && !genImageUrl ? stageBg : undefined }"
        >
          <template v-if="generating">
            <div class="gen-progress">
              <div class="gen-num">{{ genProgress }}%</div>
              <div class="gen-track">
                <div class="gen-fill" :style="{ width: genProgress + '%' }" />
              </div>
              <div class="gen-phase">
                {{ genPhaseText }}
              </div>
            </div>
          </template>
          <template v-else-if="generated && genImageUrl">
            <!-- 毛坯 → 装修后 对比 -->
            <div v-if="photoDataUrl" class="compare-wrap">
              <div class="compare-item">
                <img class="render-img compare-img" :src="photoDataUrl" alt="毛坯房原图" />
                <span class="compare-tag">毛坯房</span>
              </div>
              <span class="compare-arrow">→</span>
              <div class="compare-item">
                <img class="render-img compare-img" :src="genImageUrl" alt="AI 装修效果图" />
                <span class="compare-tag primary">AI 装修后</span>
              </div>
            </div>
            <img v-else class="render-img" :src="genImageUrl" alt="AI 装修效果图" />
          </template>
          <template v-else-if="generated">
            <div class="render-fake">
              <span class="render-emoji">{{ STYLES.find(s => s.key === styleKey)?.emoji }}</span>
              <div class="render-label">
                {{ STYLES.find(s => s.key === styleKey)?.name }} · {{ scene }} · 效果示意
              </div>
            </div>
          </template>
          <template v-else>
            <div class="render-empty">
              <template v-if="photoDataUrl">
                <img class="empty-photo" :src="photoDataUrl" alt="毛坯房" />
                <div class="render-label">毛坯房已就绪 · 配置家具/墙色/地面后点击"生成效果图"</div>
              </template>
              <template v-else>
                <span class="render-emoji">🖼️</span>
                <div class="render-label">上传毛坯房照片并配置参数后点击"生成效果图"</div>
              </template>
            </div>
          </template>
        </div>

        <div v-if="generated" class="render-ops">
          <AiButton type="primary" round @click="download"> 下载高清图（4K） </AiButton>
          <AiButton round @click="generated = false"> 换个风格再来 </AiButton>
        </div>

        <!-- AI 三步思考过程：看懂空间 → 构思布局 → 渲染效果（前两步产物透明化展示） -->
        <div v-if="generated && spaceResult" class="ai-thinking">
          <div class="at-title">AI 是如何装修的？</div>
          <div class="at-grid">
            <div class="at-card">
              <div class="at-step">① 看懂空间</div>
              <div class="at-room">
                {{ spaceResult.room_type
                }}{{ spaceResult.summary ? ' · ' + spaceResult.summary : '' }}
              </div>
              <div v-if="spaceResult.walls" class="at-line">墙面：{{ spaceResult.walls }}</div>
              <div v-if="spaceResult.floor" class="at-line">地面：{{ spaceResult.floor }}</div>
              <div v-if="spaceResult.windows_doors" class="at-line">
                门窗：{{ spaceResult.windows_doors }}
              </div>
              <div v-if="spaceResult.lighting" class="at-line">
                采光：{{ spaceResult.lighting }}
              </div>
            </div>
            <div v-if="layoutResult" class="at-card">
              <div class="at-step">② 构思布局</div>
              <div v-for="(a, i) in layoutResult.arrangement" :key="i" class="at-line">
                <b>{{ a.item }}</b> → {{ a.position }}
              </div>
              <div v-if="layoutResult.flow_notes" class="at-line">
                动线：{{ layoutResult.flow_notes }}
              </div>
            </div>
          </div>
          <div class="at-step3">③ 渲染效果：以上思考 + 你的定制参数 → 一键生成效果图</div>
        </div>

        <!-- 约束声明：负责任的产品设计 -->
        <div class="disclaimer">
          <div class="dc-title">重要说明</div>
          <div class="dc-item">
            1. AI
            方案是"草稿"，不是"施工图"——仅供营销展示与客户初步意向参考，最终方案需专业设计师复核。
          </div>
          <div class="dc-item">
            2. 效果图为"效果示意"，可能与实际交付存在材质、光线、尺寸差异，以项目实际交付标准为准。
          </div>
          <div class="dc-item">
            3.
            合规性校验（墙体闭合、面积逻辑）为辅助判断，不代表结构安全，建筑结构问题需专业设计院判断。
          </div>
        </div>
      </div>

      <div class="pane edit-pane">
        <div class="status-strip ok" />
        <div class="edit-title-row">
          <span class="edit-title">装修定制</span>
          <span class="status-line">毛坯照片 + 业主家具 + 墙色地面 = 一键装修</span>
        </div>
        <div class="edit-body">
          <div class="group-title">① 毛坯房照片（图生图基准，结构保持不变）</div>
          <div class="photo-zone">
            <div v-if="photoDataUrl" class="photo-preview">
              <img :src="photoDataUrl" alt="毛坯房照片" />
              <div class="photo-meta">
                <span>{{ photoName }} · {{ photoSize.w }}×{{ photoSize.h }}</span>
                <AiButton text size="small" style="color: #ef4444" @click="clearPhoto">
                  移除
                </AiButton>
              </div>
            </div>
            <div v-else class="photo-upload" @click="pickPhoto">
              <span class="upload-emoji">🏠</span>
              <div class="upload-label">点击上传毛坯房照片</div>
              <div class="upload-sub">jpg / png / webp，≤8MB；不传则走纯文生图</div>
            </div>
            <input
              ref="fileInput"
              type="file"
              accept="image/*"
              style="display: none"
              @change="onPhotoChange"
            />
          </div>

          <div class="group-title" style="margin-top: 18px">
            ② 业主家具清单<span class="title-count">已选 {{ pickedFurniture.length }} 件</span>
          </div>
          <div class="furn-toolbar">
            <AiButton text type="primary" size="small" @click="parseDialog = true">
              📋 粘贴/拍照解析清单
            </AiButton>
            <AiButton text size="small" @click="openAddDialog"> ＋ 添加家具 </AiButton>
          </div>
          <div class="furn-groups">
            <div v-for="g in FURNITURE_GROUPS" :key="g.group" class="furn-group">
              <span class="furn-group-name">{{ g.group }}</span>
              <div class="furn-grid">
                <button
                  v-for="f in g.items"
                  :key="f.key"
                  class="furn-chip"
                  :class="{ active: pickedFurniture.includes(f.key) }"
                  @click="toggleFurniture(f.key)"
                >
                  {{ f.label }}
                </button>
              </div>
            </div>
          </div>

          <div class="group-title" style="margin-top: 18px">③ 墙面颜色</div>
          <div class="wall-row">
            <div
              v-for="w in WALL_COLORS"
              :key="w.key"
              class="wall-swatch"
              :class="{ active: wallKey === w.key }"
              @click="wallKey = w.key"
            >
              <span class="swatch-dot" :style="{ background: w.hex }" />
              <span class="swatch-name">{{ w.label }}</span>
            </div>
          </div>

          <div class="group-title" style="margin-top: 18px">④ 地面材质</div>
          <div class="furn-grid">
            <button
              v-for="f in FLOORS"
              :key="f.key"
              class="furn-chip"
              :class="{ active: floorKey === f.key }"
              @click="floorKey = f.key"
            >
              {{ f.label }}
            </button>
          </div>

          <div class="group-title" style="margin-top: 18px">
            ⑤ 装修自由度<span class="title-count"
              >{{ strength.toFixed(2) }} · 越低越贴近原图结构</span
            >
          </div>
          <el-slider v-model="strength" :min="0.4" :max="0.9" :step="0.05" />

          <div class="group-title" style="margin-top: 18px">风格偏好</div>
          <div class="style-grid">
            <div
              v-for="s in STYLES"
              :key="s.key"
              class="style-card"
              :class="{ active: styleKey === s.key }"
              @click="styleKey = s.key"
            >
              <span class="style-emoji">{{ s.emoji }}</span>
              <div class="style-name">
                {{ s.name }}
              </div>
              <div class="style-desc">
                {{ s.desc }}
              </div>
            </div>
          </div>
          <div class="group-title" style="margin-top: 18px">生成场景</div>
          <div class="scene-row">
            <button
              v-for="sc in SCENES"
              :key="sc.key"
              class="scene-chip"
              :class="{ active: scene === sc.key }"
              @click="scene = sc.key"
            >
              {{ sc.label }}
            </button>
          </div>
          <div class="design-actions" style="margin-top: 28px">
            <AiButton type="primary" size="large" round :loading="generating" @click="generate">
              {{ generated ? '重新生成' : '生成效果图' }}
            </AiButton>
          </div>
        </div>
      </div>
    </div>

    <!-- 生成历史抽屉 -->
    <el-drawer v-model="historyVisible" title="AI 生图历史" size="720px">
      <div v-loading="historyLoading" class="history-wrap">
        <el-empty v-if="!historyLoading && !historyItems.length" description="暂无生成记录" />
        <el-row v-else :gutter="16">
          <el-col v-for="h in historyItems" :key="h.task_id" :span="8">
            <div class="history-card">
              <div class="history-thumb">
                <img v-if="h.image_url" :src="h.image_url" alt="成图" loading="lazy" />
                <span v-else class="history-fake"
                  >{{ MODE_NAMES[h.mode] ?? h.mode }} · 无实体图</span
                >
                <el-tag
                  class="history-mode"
                  :type="h.mode === 'cloud' ? 'success' : h.mode === 'comfyui' ? 'warning' : 'info'"
                  size="small"
                >
                  {{ MODE_NAMES[h.mode] ?? h.mode }}
                </el-tag>
              </div>
              <div class="history-meta">
                <div class="history-title">
                  {{ h.style_name }} · {{ h.scene_name }} · {{ h.resolution.toUpperCase() }}
                </div>
                <div class="history-sub">
                  {{ h.created_at }} · {{ h.duration_s }}s ·
                  {{ h.status === 'done' ? '成功' : '失败' }}
                </div>
                <div class="history-ops">
                  <AiButton
                    v-if="h.image_url"
                    text
                    type="primary"
                    size="small"
                    @click="viewImage(h.image_url)"
                  >
                    查看
                  </AiButton>
                  <AiButton
                    text
                    size="small"
                    style="color: #ef4444"
                    @click="removeHistory(h.task_id)"
                  >
                    删除
                  </AiButton>
                </div>
              </div>
            </div>
          </el-col>
        </el-row>
        <div v-if="historyTotal > 12" class="history-pager">
          <el-pagination
            layout="prev, pager, next"
            :total="historyTotal"
            :page-size="12"
            :current-page="historyPage"
            @current-change="loadHistory"
          />
        </div>
      </div>
    </el-drawer>

    <!-- 业主清单 AI 解析：粘贴文字 / 拍照 → 结构化条目 → 一键勾选 -->
    <el-dialog
      v-model="parseDialog"
      title="解析业主家具清单"
      width="560px"
      :close-on-click-modal="false"
    >
      <div class="parse-body">
        <div class="parse-label">① 粘贴清单文字（可留空，与照片二选一或并用）</div>
        <el-input
          v-model="parseText"
          type="textarea"
          :rows="4"
          placeholder="例如：转角沙发2张，电视柜，一张双人床 x1，书桌…"
        />
        <div class="parse-label" style="margin-top: 14px">
          ② 上传清单照片（手写/拍摄，jpg/png/webp ≤8MB）
        </div>
        <div class="parse-photo-zone">
          <div v-if="parsePhotoUrl" class="parse-photo-preview">
            <img :src="parsePhotoUrl" alt="清单照片" />
            <AiButton text size="small" style="color: #ef4444" @click="clearParsePhoto">
              移除
            </AiButton>
          </div>
          <div v-else class="parse-photo-upload" @click="pickParsePhoto">
            <span>📷</span>
            <span>点击上传清单照片</span>
          </div>
          <input
            ref="parsePhotoInput"
            type="file"
            accept="image/*"
            style="display: none"
            @change="onParsePhotoChange"
          />
        </div>
        <div class="parse-actions">
          <AiButton type="primary" :loading="parseLoading" @click="runParse"> 开始解析 </AiButton>
        </div>
        <div v-if="parseResult" class="parse-result">
          <div class="parse-result-title">
            解析结果（{{ parseResult.source === 'ai' ? 'AI 智能识别' : '规则切词'
            }}{{ parseResult.ocr ? ' · 含照片 OCR' : '' }}）
          </div>
          <div v-if="parseResult.note" class="parse-note">
            {{ parseResult.note }}
          </div>
          <div class="parse-items">
            <div
              v-for="(it, i) in parseResult.items"
              :key="i"
              class="parse-item"
              :class="{ hit: it.in_catalog }"
            >
              <span class="parse-item-name">{{ it.name }}</span>
              <span class="parse-item-count">×{{ it.count }}</span>
              <el-tag v-if="it.in_catalog" type="success" size="small"> 已匹配 </el-tag>
              <el-tag v-else type="info" size="small"> 未入库 </el-tag>
            </div>
          </div>
          <div class="parse-actions">
            <AiButton type="primary" @click="applyParse"> 勾选已匹配家具 </AiButton>
          </div>
        </div>
      </div>
    </el-dialog>

    <!-- 添加自定义家具 -->
    <el-dialog v-model="addDialog" title="添加家具" width="480px" :close-on-click-modal="false">
      <div class="add-body">
        <div class="add-row">
          <span class="add-label">家具名称 *</span>
          <el-input v-model="addName" placeholder="例如：双人学习桌" maxlength="40" />
        </div>
        <div class="add-row">
          <span class="add-label">所属分类 *</span>
          <el-select v-model="addCategory" placeholder="选择分类" style="width: 100%">
            <el-option
              v-for="g in FURNITURE_GROUPS"
              :key="g.groupId"
              :label="g.group"
              :value="g.groupId"
            />
          </el-select>
        </div>
        <div class="add-row">
          <span class="add-label">英文提示词</span>
          <el-input v-model="addEn" placeholder="渲染用英文描述，留空则用中文名" maxlength="80" />
        </div>
        <div class="add-row">
          <span class="add-label">业主叫法别名</span>
          <el-input v-model="addAliases" placeholder="逗号分隔，如：学习桌,双人桌（解析命中用）" />
        </div>
      </div>
      <template #footer>
        <AiButton @click="addDialog = false"> 取消 </AiButton>
        <AiButton type="primary" @click="submitAddItem"> 保存 </AiButton>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.engine-page {
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: 16px;
  gap: 16px;
  background: var(--reai-bg-neutral);
  overflow: auto;
}

/* 生成历史抽屉 */
.render-head-right {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}
.history-wrap {
  min-height: 200px;
}
.history-card {
  background: var(--reai-card);
  border: 1px solid var(--reai-border);
  border-radius: 12px;
  overflow: hidden;
  margin-bottom: 16px;
}
.history-thumb {
  position: relative;
  height: 130px;
  background: var(--reai-bg-gray);
  display: flex;
  align-items: center;
  justify-content: center;
}
.history-thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  cursor: zoom-in;
}
.history-fake {
  color: var(--reai-text-muted);
  font-size: 12px;
}
.history-mode {
  position: absolute;
  top: 8px;
  right: 8px;
}
.history-meta {
  padding: 10px 12px;
}
.history-title {
  font-size: 13px;
  color: var(--reai-text-main);
  font-weight: 500;
}
.history-sub {
  font-size: 12px;
  color: var(--reai-text-muted);
  margin: 4px 0 6px;
}
.history-ops {
  display: flex;
  gap: 4px;
}
.history-pager {
  display: flex;
  justify-content: center;
  margin-top: 8px;
}

/* 页面主体 */
.step-body {
  flex: 1;
  display: flex;
  gap: 16px;
  min-height: 0;
}
.step-body.single {
  display: block;
  overflow-y: auto;
}
.step-body.single .pane {
  height: auto;
  margin-bottom: 0;
}

.pane {
  background: var(--reai-card);
  border-radius: 16px;
  box-shadow: var(--reai-shadow-md);
  overflow: hidden;
}

.edit-pane {
  width: 40%;
  display: flex;
  flex-direction: column;
}
.status-strip {
  height: 4px;
  flex-shrink: 0;
}
.status-strip.ok {
  background: var(--reai-success);
}
.status-strip.bad {
  background: var(--reai-danger);
}
.edit-title-row {
  padding: 12px 32px 0;
}
.edit-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--reai-text-main);
}
.status-line {
  font-size: 12px;
  color: var(--reai-text-muted);
  display: block;
  margin-top: 2px;
}

.edit-body {
  flex: 1;
  overflow-y: auto;
  padding: 4px 32px 32px;
}
.group-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--reai-text-muted);
  letter-spacing: 0.5px;
  margin-bottom: 12px;
}

.design-actions {
  display: flex;
  gap: 12px;
}

/* 第三步：装修图 */
.render-pane {
  padding: 20px 32px 32px;
}
.render-head {
  display: flex;
  align-items: baseline;
  gap: 16px;
  margin-bottom: 16px;
}
.render-stage {
  min-height: 380px;
  border-radius: 14px;
  background: var(--reai-bg-gray);
  display: flex;
  align-items: center;
  justify-content: center;
}
.render-img {
  max-width: 100%;
  max-height: 520px;
  border-radius: 14px;
  object-fit: contain;
  box-shadow: var(--reai-shadow-md);
}
.render-fake,
.render-empty,
.gen-progress {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
}
.render-emoji {
  font-size: 56px;
}
.render-label {
  font-size: 14px;
  color: var(--reai-text-secondary);
}
.gen-num {
  font-size: 32px;
  font-weight: 600;
  color: var(--reai-primary);
}
.gen-track {
  width: 280px;
  height: 4px;
  background: rgba(26, 32, 44, 0.08);
  border-radius: 2px;
  overflow: hidden;
}
.gen-fill {
  height: 100%;
  background: var(--reai-primary);
  transition: width 0.1s;
}
.gen-phase {
  font-size: 12px;
  color: var(--reai-text-muted);
}
.render-ops {
  margin-top: 16px;
  display: flex;
  gap: 12px;
}

/* AI 三步思考过程 */
.ai-thinking {
  margin-top: 20px;
  background: var(--reai-bg-gray);
  border-radius: 14px;
  padding: 16px 18px;
}
.at-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--reai-text-main);
  margin-bottom: 12px;
}
.at-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}
@media (max-width: 900px) {
  .at-grid {
    grid-template-columns: 1fr;
  }
}
.at-card {
  background: #fff;
  border-radius: 10px;
  padding: 12px 14px;
}
.at-step {
  font-size: 13px;
  font-weight: 600;
  color: var(--reai-primary);
  margin-bottom: 6px;
}
.at-room {
  font-size: 13px;
  color: var(--reai-text-main);
  font-weight: 500;
  margin-bottom: 6px;
}
.at-line {
  font-size: 12px;
  color: var(--reai-text-secondary);
  line-height: 1.7;
}
.at-line b {
  color: var(--reai-text-main);
  font-weight: 600;
}
.at-step3 {
  margin-top: 12px;
  font-size: 12px;
  color: var(--reai-text-muted);
}

/* 约束声明 */
.disclaimer {
  margin-top: 20px;
  background: var(--reai-bg-gray);
  border-radius: 12px;
  padding: 14px 16px;
}
.dc-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--reai-text-secondary);
  margin-bottom: 6px;
}
.dc-item {
  font-size: 12px;
  line-height: 1.8;
  color: var(--reai-text-muted);
}

.style-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}
.style-card {
  background: var(--reai-card);
  border-radius: 12px;
  padding: 16px;
  box-shadow: var(--reai-shadow-sm);
  cursor: pointer;
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  transition: all 0.15s;
}
.style-card:hover {
  box-shadow: var(--reai-shadow-md);
}
.style-card.active {
  box-shadow: inset 0 0 0 1.5px var(--reai-primary);
}
.style-emoji {
  font-size: 28px;
}
.style-name {
  font-size: 14px;
  font-weight: 600;
  margin-top: 8px;
}
.style-desc {
  font-size: 12px;
  color: var(--reai-text-muted);
  margin-top: 4px;
}
.scene-row {
  display: flex;
  gap: 8px;
}
.scene-chip {
  height: 34px;
  padding: 0 18px;
  border: none;
  border-radius: 9999px;
  background: var(--reai-bg-gray);
  color: var(--reai-text-secondary);
  font-size: 13px;
  cursor: pointer;
}
.scene-chip.active {
  background: var(--reai-primary);
  color: #fff;
}

/* 第三步：毛坯照片 / 家具清单 / 墙色 / 地面 / 对比 */
.title-count {
  margin-left: 8px;
  color: var(--reai-primary);
  font-weight: 400;
}
.photo-zone {
  display: flex;
  flex-direction: column;
}
.photo-upload {
  border: 1.5px dashed var(--reai-border);
  border-radius: 12px;
  padding: 22px 16px;
  text-align: center;
  cursor: pointer;
  transition: all 0.15s;
  background: var(--reai-bg-neutral);
}
.photo-upload:hover {
  border-color: var(--reai-primary);
  background: var(--reai-primary-soft);
}
.upload-emoji {
  font-size: 30px;
}
.upload-label {
  font-size: 13px;
  font-weight: 500;
  color: var(--reai-text-main);
  margin-top: 6px;
}
.upload-sub {
  font-size: 12px;
  color: var(--reai-text-muted);
  margin-top: 2px;
}
.photo-preview img {
  width: 100%;
  max-height: 180px;
  object-fit: cover;
  border-radius: 10px;
  border: 1px solid var(--reai-border);
}
.photo-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 12px;
  color: var(--reai-text-muted);
  margin-top: 6px;
}
.furn-groups {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.furn-group {
  display: flex;
  align-items: flex-start;
  gap: 10px;
}
.furn-group-name {
  flex-shrink: 0;
  width: 42px;
  font-size: 12px;
  color: var(--reai-text-muted);
  line-height: 32px;
}
.furn-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.furn-chip {
  height: 32px;
  padding: 0 14px;
  border: 1px solid var(--reai-border);
  border-radius: 9999px;
  background: var(--reai-card);
  color: var(--reai-text-secondary);
  font-size: 13px;
  cursor: pointer;
  transition: all 0.15s;
}
.furn-chip:hover {
  border-color: var(--reai-primary);
  color: var(--reai-primary);
}
.furn-chip.active {
  background: var(--reai-primary);
  border-color: var(--reai-primary);
  color: #fff;
}
.wall-row {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}
.wall-swatch {
  display: flex;
  align-items: center;
  gap: 6px;
  border: 1px solid var(--reai-border);
  border-radius: 9999px;
  padding: 4px 12px 4px 4px;
  cursor: pointer;
  transition: all 0.15s;
}
.wall-swatch:hover {
  border-color: var(--reai-primary);
}
.wall-swatch.active {
  border-color: var(--reai-primary);
  box-shadow: 0 0 0 2px var(--reai-primary-soft);
}
.swatch-dot {
  width: 22px;
  height: 22px;
  border-radius: 50%;
  border: 1px solid rgba(0, 0, 0, 0.08);
}
.swatch-name {
  font-size: 12px;
  color: var(--reai-text-secondary);
}
.compare-wrap {
  display: flex;
  align-items: center;
  gap: 12px;
  max-width: 100%;
}
.compare-item {
  position: relative;
}
.compare-img {
  max-height: 400px;
}
.compare-tag {
  position: absolute;
  left: 10px;
  top: 10px;
  background: rgba(26, 32, 44, 0.72);
  color: #fff;
  font-size: 12px;
  border-radius: 9999px;
  padding: 3px 12px;
}
.compare-tag.primary {
  background: var(--reai-primary);
}
.compare-arrow {
  font-size: 22px;
  color: var(--reai-primary);
  flex-shrink: 0;
}
.empty-photo {
  max-width: 70%;
  max-height: 260px;
  object-fit: cover;
  border-radius: 12px;
  box-shadow: var(--reai-shadow-md);
}

/* 家具清单工具栏 */
.furn-toolbar {
  display: flex;
  gap: 8px;
  margin-bottom: 10px;
}

/* 清单解析对话框 */
.parse-body {
  display: flex;
  flex-direction: column;
}
.parse-label {
  font-size: 12px;
  color: var(--reai-text-muted);
  margin-bottom: 6px;
}
.parse-photo-zone {
  margin-bottom: 4px;
}
.parse-photo-upload {
  border: 1.5px dashed var(--reai-border);
  border-radius: 10px;
  padding: 18px;
  text-align: center;
  cursor: pointer;
  color: var(--reai-text-secondary);
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 13px;
}
.parse-photo-upload:hover {
  border-color: var(--reai-primary);
  color: var(--reai-primary);
}
.parse-photo-preview img {
  width: 100%;
  max-height: 180px;
  object-fit: cover;
  border-radius: 10px;
}
.parse-photo-preview {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.parse-actions {
  margin-top: 12px;
  display: flex;
  justify-content: flex-end;
}
.parse-result {
  margin-top: 16px;
  background: var(--reai-bg-gray);
  border-radius: 10px;
  padding: 12px 14px;
}
.parse-result-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--reai-text-main);
  margin-bottom: 6px;
}
.parse-note {
  font-size: 12px;
  color: var(--reai-text-muted);
  margin-bottom: 8px;
}
.parse-items {
  display: flex;
  flex-direction: column;
  gap: 6px;
  max-height: 220px;
  overflow-y: auto;
}
.parse-item {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}
.parse-item.hit {
  color: var(--reai-text-main);
}
.parse-item-name {
  flex: 1;
}
.parse-item-count {
  color: var(--reai-text-muted);
  font-size: 12px;
}

/* 添加家具对话框 */
.add-body {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.add-row {
  display: flex;
  align-items: center;
  gap: 10px;
}
.add-label {
  flex-shrink: 0;
  width: 88px;
  font-size: 13px;
  color: var(--reai-text-secondary);
}
</style>
