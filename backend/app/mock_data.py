"""全量 Mock 数据：页面设计阶段为所有接口提供演示数据。
后续接入真实功能时，按 services/ 层替换即可，接口契约保持不变。
"""
from datetime import datetime, timedelta

NOW = datetime.now()


def _ago(hours: float) -> str:
    return (NOW - timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M")


# ---------------- 会话列表 ----------------
SESSIONS = [
    {"thread_id": "t-1001", "title": "滨江花园 A户型 朋友圈文案", "group": "今天", "time": "10:30", "updated_at": _ago(1)},
    {"thread_id": "t-1002", "title": "89平三房 户型优缺点分析", "group": "今天", "time": "09:12", "updated_at": _ago(3)},
    {"thread_id": "t-1003", "title": "云顶湾 别墅 效果图渲染", "group": "昨天", "time": "16:45", "updated_at": _ago(20)},
    {"thread_id": "t-1004", "title": "十月房贷新政解读", "group": "昨天", "time": "11:20", "updated_at": _ago(26)},
    {"thread_id": "t-1005", "title": "学区房卖点提炼", "group": "更早", "time": "09-02", "updated_at": _ago(96)},
]

# ---------------- 会话消息详情 ----------------
MESSAGES = {
    "t-1001": [
        {"id": "m1", "role": "user", "content": "@文案生成 帮我写一段滨江花园A户型的朋友圈文案，突出南北通透。", "attachments": [], "time": "10:28"},
        {"id": "m2", "role": "assistant", "content": "【AI生成 · 仅供参考，请专业复核】\n🌟滨江花园A户型 | 建面98㎡ 三房两厅\n南北通透，双阳台对流设计，午后穿堂风轻拂整屋……主卧朝南带飘窗，孩子写作业都沐浴阳光。均价仅 2.1 万/㎡，本周到访送精装礼包！",
         "skill": "文案生成", "references": [{"doc": "滨江花园楼书2025.pdf", "page": 12}, {"doc": "A户型图.jpg", "page": 1}],
         "house_card": {"title": "A户型结构化参数", "action": "打开户型编辑"}, "time": "10:30"},
    ],
    "t-1002": [
        {"id": "m3", "role": "user", "content": "帮我分析下这个89平三房的优缺点", "attachments": ["89平户型图.jpg"], "time": "09:12"},
        {"id": "m4", "role": "assistant", "content": "", "rejected": True, "time": "09:13"},
    ],
}

# ---------------- 知识库文档 ----------------
DOCUMENTS = [
    {"id": "d1", "name": "滨江花园楼书2025.pdf", "type": "PDF", "size": "18.2 MB", "status": "active", "version": "v3", "updated_at": "2026-09-05 14:20", "chunks": 128, "uploader": "王敏"},
    {"id": "d2", "name": "2025年房贷新政解读.docx", "type": "Word", "size": "2.4 MB", "status": "processing", "version": "v1", "updated_at": "2026-09-06 10:02", "chunks": 0, "uploader": "李强"},
    {"id": "d3", "name": "云顶湾别墅手册.pdf", "type": "PDF", "size": "32.6 MB", "status": "active", "version": "v2", "updated_at": "2026-08-28 09:30", "chunks": 245, "uploader": "王敏"},
    {"id": "d4", "name": "常见问题话术库.xlsx", "type": "Excel", "size": "1.1 MB", "status": "active", "version": "v5", "updated_at": "2026-08-20 16:45", "chunks": 86, "uploader": "张伟"},
    {"id": "d5", "name": "旧版价格表2024.xlsx", "type": "Excel", "size": "0.8 MB", "status": "inactive", "version": "v1", "updated_at": "2026-06-11 11:00", "chunks": 42, "uploader": "张伟"},
]

SEARCH_RESULTS = [
    {"doc": "滨江花园楼书2025.pdf", "page": 12, "score": 87, "snippet": "…主推A户型采用<em>南北通透</em>布局，客厅开间4.2米，双阳台设计…"},
    {"doc": "常见问题话术库.xlsx", "page": 3, "score": 72, "snippet": "…客户问通风采光时，强调<em>南北通透</em>+全明户型，冬暖夏凉…"},
    {"doc": "云顶湾别墅手册.pdf", "page": 8, "score": 64, "snippet": "…下沉式庭院配合<em>南北通透</em>的听风动线，夏季自然降温…"},
]

# ---------------- Skill 市场 ----------------
SKILLS = [
    {"id": "s1", "name": "文案生成", "icon": "✍️", "desc": "朋友圈/短视频脚本/销售话术多版本一键生成", "version": "v1.3.0", "open_source": True, "installed": True},
    {"id": "s2", "name": "户型解析", "icon": "📐", "desc": "从图片/DXF提取房间数、面积、朝向、门窗结构化参数", "version": "v2.1.0", "open_source": True, "installed": True},
    {"id": "s3", "name": "效果图渲染", "icon": "🎨", "desc": "调用第三方API生成室内空间效果图（营销素材）", "version": "v1.0.2", "open_source": False, "installed": True},
    {"id": "s4", "name": "政策问答", "icon": "📜", "desc": "基于知识库回答限购、贷款、税费等政策问题", "version": "v1.1.0", "open_source": True, "installed": True},
    {"id": "s5", "name": "风水分析", "icon": "🧭", "desc": "户型朝向与格局的传统风水参考分析", "version": "v0.9.1", "open_source": False, "installed": False},
    {"id": "s6", "name": "竞品对比", "icon": "⚖️", "desc": "多楼盘参数自动对比，生成对比表格与话术", "version": "v0.8.0", "open_source": True, "installed": False},
]

# ---------------- 任务中心 ----------------
TASKS = [
    {"id": "tk1", "name": "滨江花园A户型 效果图渲染", "submitted_at": "3分钟前", "progress": 65, "status": "running"},
    {"id": "tk2", "name": "批量导入房源信息(200条)", "submitted_at": "1小时前", "progress": 100, "status": "done", "result": {"success": 197, "failed": 3}},
    {"id": "tk3", "name": "云顶湾B户型 DXF解析", "submitted_at": "2小时前", "progress": 40, "status": "failed", "error": "图纸解析失败（错误码 3001）"},
    {"id": "tk4", "name": "10月朋友圈文案批量生成", "submitted_at": "5分钟前", "progress": 0, "status": "queued"},
]

# ---------------- 户型解析（HITL） ----------------
HOUSE_STRUCT = {
    "task_id": "house-8f3a2c",
    "status": "pending_human_confirm",
    "house_struct": {
        "name": "A户型（AI识别）",
        "project": "滨江花园",
        "area_gross": 98.5,
        "area_inner": 82.3,
        "rooms": 3,
        "halls": 2,
        "orientation": "南",
        "layout": "平层",
    },
}

# ---------------- 审计日志 ----------------
AUDIT_LOGS = [
    {"id": "a1", "time": "2026-09-06 10:30", "user": "王敏", "action": "skill_invoke", "skill": "文案生成", "cost": 0.12},
    {"id": "a2", "time": "2026-09-06 09:45", "user": "李强", "action": "upload", "skill": "-", "cost": 0.0},
    {"id": "a3", "time": "2026-09-06 09:12", "user": "张伟", "action": "house_confirm", "skill": "户型解析", "cost": 0.35},
    {"id": "a4", "time": "2026-09-05 17:20", "user": "王敏", "action": "login", "skill": "-", "cost": 0.0},
    {"id": "a5", "time": "2026-09-05 15:05", "user": "赵芳", "action": "skill_invoke", "skill": "效果图渲染", "cost": 2.80},
]

AUDIT_DETAIL_DIALOG = [
    {"role": "user", "content": "@文案生成 帮我写一段滨江花园A户型的朋友圈文案"},
    {"role": "assistant", "content": "【AI生成 · 仅供参考】🌟滨江花园A户型 | 建面98㎡ 三房两厅…（完整对话原文）"},
]

# ---------------- 费用看板 ----------------
COST_STATS = {
    "budget_used_percent": 80,
    "month_cost": 1284.60,
    "budget": 1600.00,
    "trend": [32, 45, 38, 52, 61, 48, 55, 70, 66, 58, 72, 80, 75, 69,
              84, 90, 78, 86, 95, 88, 102, 96, 110, 105, 98, 112, 108, 120, 115, 128],
    "top_skills": [
        {"name": "效果图渲染", "cost": 820.40, "percent": 64},
        {"name": "户型解析", "cost": 286.20, "percent": 22},
        {"name": "文案生成", "cost": 178.00, "percent": 14},
    ],
}

# ---------------- 用户管理 ----------------
USERS = [
    {"id": "u1", "name": "王敏", "username": "wangmin", "role": "admin", "workspace": "营销一部", "status": "active"},
    {"id": "u2", "name": "李强", "username": "liqiang", "role": "member", "workspace": "营销一部", "status": "active"},
    {"id": "u3", "name": "张伟", "username": "zhangwei", "role": "member", "workspace": "营销二部", "status": "active"},
    {"id": "u4", "name": "赵芳", "username": "zhaofang", "role": "member", "workspace": "渠道部", "status": "disabled"},
]

WORKSPACES = ["营销一部", "营销二部", "渠道部"]
