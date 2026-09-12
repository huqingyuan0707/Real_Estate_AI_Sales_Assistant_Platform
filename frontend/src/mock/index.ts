/** 前端内置演示数据（与 backend/app/mock_data.py 镜像），页面设计阶段直接渲染。 */

export const sessions = [
  { threadId: 't-1001', title: '滨江花园 A户型 朋友圈文案', group: '今天', time: '10:30' },
  { threadId: 't-1002', title: '89平三房 户型优缺点分析', group: '今天', time: '09:12' },
  { threadId: 't-1003', title: '云顶湾 别墅 效果图渲染', group: '昨天', time: '16:45' },
  { threadId: 't-1004', title: '十月房贷新政解读', group: '昨天', time: '11:20' },
  { threadId: 't-1005', title: '学区房卖点提炼', group: '更早', time: '09-02' },
];

export const messages: Record<string, any[]> = {
  't-1001': [
    {
      id: 'm1',
      role: 'user',
      content: '@文案生成 帮我写一段滨江花园A户型的朋友圈文案，突出南北通透。',
      attachments: [],
      time: '10:28',
    },
    {
      id: 'm2',
      role: 'assistant',
      time: '10:30',
      skill: '文案生成',
      content:
        '🌟滨江花园A户型 | 建面98㎡ 三房两厅\n\n南北通透，双阳台对流设计，午后穿堂风轻拂整屋。主卧朝南带飘窗，四季阳光满屋。均价仅2.1万/㎡，本周到访送精装礼包！',
      references: [
        {
          doc: '滨江花园楼书2025.pdf',
          page: 12,
          snippet: '…主推A户型采用南北通透布局，客厅开间4.2米…',
        },
        { doc: 'A户型图.jpg', page: 1, snippet: '…A户型标准层平面示意…' },
      ],
      houseCard: true,
    },
  ],
  't-1002': [
    {
      id: 'm3',
      role: 'user',
      content: '帮我分析下这个89平三房的优缺点',
      attachments: ['89平户型图.jpg'],
      time: '09:12',
    },
    { id: 'm4', role: 'assistant', rejected: true, time: '09:13', content: '' },
  ],
};

export const installedSkills = ['文案生成', '户型解析', '效果图渲染', '政策问答'];

export const documents = [
  {
    id: 'd1',
    name: '滨江花园楼书2025.pdf',
    type: 'PDF',
    size: '18.2 MB',
    status: 'active',
    version: 'v3',
    updatedAt: '2026-09-05 14:20',
    uploader: '王敏',
  },
  {
    id: 'd2',
    name: '2025年房贷新政解读.docx',
    type: 'Word',
    size: '2.4 MB',
    status: 'processing',
    version: 'v1',
    updatedAt: '2026-09-06 10:02',
    uploader: '李强',
  },
  {
    id: 'd3',
    name: '云顶湾别墅手册.pdf',
    type: 'PDF',
    size: '32.6 MB',
    status: 'active',
    version: 'v2',
    updatedAt: '2026-08-28 09:30',
    uploader: '王敏',
  },
  {
    id: 'd4',
    name: '常见问题话术库.xlsx',
    type: 'Excel',
    size: '1.1 MB',
    status: 'active',
    version: 'v5',
    updatedAt: '2026-08-20 16:45',
    uploader: '张伟',
  },
  {
    id: 'd5',
    name: '旧版价格表2024.xlsx',
    type: 'Excel',
    size: '0.8 MB',
    status: 'inactive',
    version: 'v1',
    updatedAt: '2026-06-11 11:00',
    uploader: '张伟',
  },
];

export const searchResults = [
  {
    doc: '滨江花园楼书2025.pdf',
    page: 12,
    score: 87,
    snippet: '…主推A户型采用<em>南北通透</em>布局，客厅开间4.2米，双阳台设计…',
  },
  {
    doc: '常见问题话术库.xlsx',
    page: 3,
    score: 72,
    snippet: '…客户问通风采光时，强调<em>南北通透</em>+全明户型，冬暖夏凉…',
  },
  {
    doc: '云顶湾别墅手册.pdf',
    page: 8,
    score: 64,
    snippet: '…下沉式庭院配合<em>南北通透</em>的听风动线，夏季自然降温…',
  },
];

export const skills = [
  {
    id: 's1',
    name: '文案生成',
    icon: '✍️',
    desc: '朋友圈/短视频脚本/销售话术多版本一键生成',
    version: 'v1.3.0',
    openSource: true,
    installed: true,
  },
  {
    id: 's2',
    name: '户型解析',
    icon: '📐',
    desc: '从图片/DXF提取房间数、面积、朝向、门窗结构化参数',
    version: 'v2.1.0',
    openSource: true,
    installed: true,
  },
  {
    id: 's3',
    name: '效果图渲染',
    icon: '🎨',
    desc: '调用第三方API生成室内空间效果图（营销素材）',
    version: 'v1.0.2',
    openSource: false,
    installed: true,
  },
  {
    id: 's4',
    name: '政策问答',
    icon: '📜',
    desc: '基于知识库回答限购、贷款、税费等政策问题',
    version: 'v1.1.0',
    openSource: true,
    installed: true,
  },
  {
    id: 's5',
    name: '风水分析',
    icon: '🧭',
    desc: '户型朝向与格局的传统风水参考分析',
    version: 'v0.9.1',
    openSource: false,
    installed: false,
  },
  {
    id: 's6',
    name: '竞品对比',
    icon: '⚖️',
    desc: '多楼盘参数自动对比，生成对比表格与话术',
    version: 'v0.8.0',
    openSource: true,
    installed: false,
  },
];

export const tasks = [
  {
    id: 'tk1',
    name: '滨江花园A户型 效果图渲染',
    submittedAt: '3分钟前',
    progress: 65,
    status: 'running',
  },
  {
    id: 'tk2',
    name: '批量导入房源信息(200条)',
    submittedAt: '1小时前',
    progress: 100,
    status: 'done',
    result: { success: 197, failed: 3 },
  },
  {
    id: 'tk3',
    name: '云顶湾B户型 DXF解析',
    submittedAt: '2小时前',
    progress: 40,
    status: 'failed',
    error: '图纸解析失败（错误码 3001）',
  },
  {
    id: 'tk4',
    name: '10月朋友圈文案批量生成',
    submittedAt: '5分钟前',
    progress: 0,
    status: 'queued',
  },
];

export const houseStruct = {
  taskId: 'house-8f3a2c',
  name: 'A户型（AI识别）',
  project: '滨江花园',
  areaGross: 98.5,
  areaInner: 82.3,
  rooms: 3,
  halls: 2,
  orientation: '南',
  layout: '平层',
};

export const auditLogs = [
  {
    id: 'a1',
    time: '2026-09-06 10:30',
    user: '王敏',
    action: '技能调用',
    skill: '文案生成',
    cost: 0.12,
  },
  { id: 'a2', time: '2026-09-06 09:45', user: '李强', action: '上传文档', skill: '-', cost: 0 },
  {
    id: 'a3',
    time: '2026-09-06 09:12',
    user: '张伟',
    action: '户型确认',
    skill: '户型解析',
    cost: 0.35,
  },
  { id: 'a4', time: '2026-09-05 17:20', user: '王敏', action: '登录', skill: '-', cost: 0 },
  {
    id: 'a5',
    time: '2026-09-05 15:05',
    user: '赵芳',
    action: '技能调用',
    skill: '效果图渲染',
    cost: 2.8,
  },
];

export const auditDetail = [
  { role: 'user', content: '@文案生成 帮我写一段滨江花园A户型的朋友圈文案' },
  {
    role: 'assistant',
    content:
      '【AI生成 · 仅供参考】🌟滨江花园A户型 | 建面98㎡ 三房两厅…（此处展示该次完整人机对话原文）',
  },
];

export const costStats = {
  budgetUsedPercent: 80,
  monthCost: 1284.6,
  budget: 1600,
  trend: [
    32, 45, 38, 52, 61, 48, 55, 70, 66, 58, 72, 80, 75, 69, 84, 90, 78, 86, 95, 88, 102, 96, 110,
    105, 98, 112, 108, 120, 115, 128,
  ],
  topSkills: [
    { name: '效果图渲染', cost: 820.4, percent: 64 },
    { name: '户型解析', cost: 286.2, percent: 22 },
    { name: '文案生成', cost: 178, percent: 14 },
  ],
};

export const users = [
  {
    id: 'u1',
    name: '王敏',
    username: 'wangmin',
    role: 'admin',
    workspace: '营销一部',
    status: 'active',
  },
  {
    id: 'u2',
    name: '李强',
    username: 'liqiang',
    role: 'member',
    workspace: '营销一部',
    status: 'active',
  },
  {
    id: 'u3',
    name: '张伟',
    username: 'zhangwei',
    role: 'member',
    workspace: '营销二部',
    status: 'active',
  },
  {
    id: 'u4',
    name: '赵芳',
    username: 'zhaofang',
    role: 'member',
    workspace: '渠道部',
    status: 'disabled',
  },
];

export const workspaces = ['营销一部', '营销二部', '渠道部'];
