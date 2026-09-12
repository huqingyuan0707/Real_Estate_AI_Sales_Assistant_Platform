# 房地产 AI 销售助手平台

前端 Vue3 + Element Plus + Vite，后端 FastAPI。当前阶段为**页面设计稿实现**（无数据库依赖，内置演示数据，接口层已就绪可随时联调真实后端）。

## 环境要求

- Node ≥ 20（当前 22.18），包管理器 pnpm 12.3.4（与 `package.json#packageManager` 一致）
- Python ≥ 3.12（当前 3.14.5，依赖已装于 `backend/.venv`）

## 启动

### 后端（端口 8000）

```powershell
cd backend
.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload --port 8000
# 接口文档：http://127.0.0.1:8000/docs
```

### 前端（端口 5173，代理 /api → 8000）

```powershell
cd frontend
pnpm dev
# 或 Windows 符号链接受限时：node node_modules\vite\bin\vite.js
# 访问：http://localhost:5173（演示账号：admin / 123456）
```

## 目录结构

```
backend/           FastAPI（app/main.py + api/v1/endpoints/*，统一信封 {code,msg,data,trace_id}）
frontend/src/
  layouts/         MainLayout 全局框架（240px 深色导航 + 64px 顶栏）
  views/           Chat 对话工作台 / House 户型编辑器 / Knowledge 知识库
                   SkillMarket Skill市场 / TaskCenter 任务中心
  views/admin/     AuditLog 审计日志 / CostDashboard 费用看板 / UserManage 用户管理
  mock/            演示数据（与 backend/app/mock_data.py 镜像）
  api/             接口层（联调时切换调用）
```

## 设计规范

页面严格按 `UI设计稿绘制规范.md`（V1.0 画板/布局/交互）与 `设计系统规范文档.md`（色板/字阶/间距/组件）实现：

- 主色 `#2B5CF5`，中性色 Slate 系，4px 网格间距
- 消息气泡 15px/1.6，圆角 16px（用户右下 4px / AI 左下 4px）
- 状态条四阶段：🧠 规划中 → ⚙️ 执行中 → ✅ 校验中 → ✍️ 生成回答
- 异常态全覆盖：空状态、AI 拒答黄条、网络断连横幅、图纸解析失败态

## 已知说明

- Windows 下 pnpm 需要符号链接权限；若报 `ERR_PNPM_PACKAGE_MANAGER_SYMLINK_FAILED`，以管理员开启开发者模式，或直接 `node node_modules\vite\bin\vite.js` 运行
- `MainLayout.vue` 中 `netBroken = ref(true)` 可预览"网络断连"全局横幅
- `HouseEditorView.vue` 中 `loadFailed = ref(true)` 可预览"图纸解析失败"态
