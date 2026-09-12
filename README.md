# 房地产 AI 销售助手平台

面向房产销售场景的企业级 AI 助手平台，覆盖 **智能对话 / 企业级 RAG 知识问答 / 空间智能（户型解析与一键装修图）/ Agent 工程化** 四条主线。

前端 Vue 3 + Element Plus + Vite，后端 FastAPI。**不依赖外部数据库**：向量走 Chroma，业务数据落本地 JSON/JSONL，克隆即可运行。

## 技术栈

| 层 | 选型 |
|---|---|
| 前端 | Vue 3.5 · TypeScript 5.7 · Vite 6 · Element Plus 2.9 · Pinia · Vue Router 4 · ECharts |
| 后端 | FastAPI · Uvicorn · Pydantic v2 · python-multipart |
| 检索 | sentence-transformers（`bge-small-zh` 嵌入 + `bge-reranker-base` 重排）+ Chroma + 自实现 BM25 |
| 大模型 | 任意 OpenAI 兼容端点（默认 Ollama `qwen2.5`） |
| 生图 | 硅基流动 / 通义万相 / 本地 ComfyUI（均未配置时自动降级演示模式） |
| 存储 | Chroma 向量库 + 本地 JSON / JSONL（**无 Postgres / Redis / Celery 依赖**） |

## 环境要求

- Node ≥ 20（开发验证 22.18），包管理器 pnpm 12.3.4（与 `package.json#packageManager` 一致）
- Python ≥ 3.12（开发验证 3.14.5，依赖已装于 `backend/.venv`）
- 可选：Ollama（本地对话模型）、ComfyUI（本地生图）

## 快速开始

### 1. 后端（端口 8010）

```powershell
cd backend
.venv\Scripts\Activate.ps1
copy .env.example .env      # 按需修改 LLM_BASE_URL / LLM_MODEL / RENDER_API_KEY
uvicorn app.main:app --host 127.0.0.1 --port 8010
```

- 接口文档：http://127.0.0.1:8010/docs
- **为什么是 8010 而不是 8000**：本机 8000 长期被其他项目的 Docker 容器占用（请求会返回 401），后端固定使用 8010

### 2. 前端（端口 5173）

```powershell
cd frontend
pnpm install
pnpm dev
```

在 `frontend/.env.local` 指定后端地址：

```
VITE_API_PROXY_TARGET=http://127.0.0.1:8010
```

- 访问 http://localhost:5173 ，演示账号 `admin / 123456`
- Vite 代理目标优先级：命令行环境变量 > `.env.local` > `.env.development` > 默认 `http://127.0.0.1:8000`
- **注意**：不要在前端 `.env.development` 中硬编码 `VITE_API_PROXY_TARGET=8000`，它会盖住 `.env.local`，导致所有 `/api` 请求代理到错误端口报 500

## 核心能力

**智能对话**（`/chat`）
SSE 流式输出、意图识别、多轮会话记忆与 Query 改写、状态条四阶段（规划 → 执行 → 校验 → 生成回答）、引用页码回显、可信度标签、流式 PII 脱敏、用户级滑窗限流（429 / 错误码 2002）。

**企业级 RAG 治理**（依据 `企业级 RAG 知识智能问答.md`）
- 检索链：双路召回（向量 + 自实现中文 bigram BM25）→ RRF(k=60) 融合 → bge-reranker 重排 → 双阶段权限过滤 → 阈值拒答（**0.6**，经评估校准）
- 权限过滤：Chroma `where` 硬过滤（租户 / 审核态 / 密级）+ 应用层精过滤（部门 / 生效期）
- 治理元数据：`security_level`（public / internal / confidential）、`dept_id`、`review_status`、`owner`、`doc_version`、生效期、`section`
- 安全层：提示注入特征扫描 + system 最高优先级约束 + PII 脱敏
- 质量层：幻觉检测（引用覆盖率 / 数值一致性 / 越界引用）、LLM-as-judge 四维评分、知识热度
- 可观测：`data/rag_traces.jsonl`（耗时 / 召回 / 拦截 / 注入 / token 成本）、`data/feedback_events.jsonl`（采纳率 / 差评知识 / 知识缺口）

**知识库管理**（`/documents`、`/index-admin`）
PDF / Word / Excel / PPT / TXT / MD 上传解析 → 递归分块 → 向量化入库；按源文件删除、批量导入（异步任务）、同名文档版本升级（`v(n+1)` + 旧版 deprecated + 清旧向量）、文档审核（同步改写向量元数据）、质量校验、增量同步（按 SHA256）、索引管理（换嵌入模型重建 / 快照回滚）。

**空间智能引擎**（`/house`、`/furniture`、`/render`）
户型图纸解析、业主家具清单生成、AI 一键装修图（云端生图 API 优先，其次本机 ComfyUI，均不可用时降级演示模式模拟进度 + 风格色板占位图）。

**Agent 工程化门面**
Runtime 单次 run 闭环、工具注册表与执行器、策略引擎与人工审批、RAG 门面、离线评估。接口为 `/agent/chat`、`/agent/chat/stream`、`/tools`、`/tools/{name}/invoke`、`/knowledge/search`、`/knowledge/index`、`/admin/health|ready|usage`、`/eval/run`。这是一层**薄门面**，内部转发到 `app/services/*`，前端已在 `src/api/index.ts` 定义对应调用。

**平台能力**
Skill 市场、统一任务中心（`/tasks` status/stream/cancel/retry，错误码 4001/4002）、**我的 AI 服务**（每用户自填 LLM / 生图 Base URL、API Key、模型名，仅对本账号生效，缺项回退全局 `.env`）、记忆管理、反馈闭环、系统设置热更新。

**管理后台**（RBAC：`chat` / `house` / `kb` / `settings` / `cost` / `audit` / `user_manage` / `skill` / `task`）
审计日志、费用看板、用户管理、系统设置、合规自查报表（等保三级控制点对照）、OIDC / LDAP / TOTP / 密码策略。

## 目录结构

```
backend/
  app/main.py                应用入口（挂载 api_router）
  app/config.py              全部配置项 + settings 单例（真实配置源）
  app/api/v1/router.py       路由聚合与 RBAC 保护
  app/api/v1/endpoints/      业务端点（chat/sessions/documents/house/render/skills/tasks/...）
  app/services/              业务实现层：rag / llm / memory / guard / governance / faithfulness
                             cache / ratelimit / parents / query_expand / index_admin / judge
                             vector_store / keyword_store / ingest / ocr / render / furniture
                             ai_config / user_store / audit_chain / observability / tracing
                             oidc / ldap_auth / totp / password_policy / task_center
  app/modules/agent/         Agent 工程化门面（runtime / state / tools / policy / rag / memory / llm / evaluation）
  app/core/                  security / rbac / middleware / responses / user_context（ContextVar）
                             dependencies / events / exceptions / logging / config（文档兼容层）
  app/workers/               任务执行（Celery 未安装时自动降级为内存直跑）
  tests/                     单测 / 冒烟 / RAG 评估脚本
frontend/src/
  layouts/MainLayout.vue     全局框架（240px 深色导航 + 64px 顶栏）
  views/                     ChatView / HouseEditorView / KnowledgeView / MyAiView / SettingsView
                             SkillMarketView / TaskCenterView / LoginView
  views/admin/               AuditLogView / CostDashboardView / UserManageView
  api/                       接口层
  features/                 按功能域组织的组件与 composables（agent / chat 等）
  stores/  router/  styles/ 设计令牌与全局样式
skills/                      本项目自用 Skill（backend-code-style / frontend-code-style）
```

根目录 Markdown 文档：`需求文档.md`（需求与技术方案合订版）、`功能设计.md`、`技术方案.md`、`企业级 RAG 知识智能问答.md`、`设计系统规范文档.md`、`UI设计稿绘制规范.md`、`标准企业级项目文档.md`、`等保合规自查清单.md`。

## 配置说明

`backend/.env`（由 `.env.example` 复制）主要配置项：

| 变量 | 说明 |
|---|---|
| `LLM_BASE_URL` / `LLM_MODEL` / `LLM_API_KEY` / `LLM_ENABLED` | 对话模型（OpenAI 兼容协议），`LLM_ENABLED=false` 可纯演示运行 |
| `RENDER_PROVIDER` / `RENDER_API_BASE` / `RENDER_API_KEY` / `RENDER_API_MODEL` | 云端生图（填 Key 即启用，优先级最高） |
| `COMFYUI_BASE_URL` | 本机 ComfyUI（默认 `http://127.0.0.1:8188`） |
| `RAG_CHROMA_DIR` / `MEM_STORE_PATH` | 向量库与记忆存储路径（默认 `data/`） |

运行时热更新配置（会覆盖 `config.py` 默认值）保存在 `backend/data/.runtime_settings.json`，评估校准过的拒答阈值 0.6 即由此维护。

## 测试与评估

```powershell
# 后端单测（Agent 工程化：state / runtime / tools / policy）
cd backend; .\.venv\Scripts\python.exe -m pytest tests/test_agent_engineering.py -q

# RAG 评估门禁（Recall / MRR / NDCG / 拒答准确率，未达标退出码 1）
.\.venv\Scripts\python.exe tests/eval_rag.py            # 加 --seed 固定采样，--judge 启用 LLM 评分

# HTTP 冒烟（需后端已启动）
.\.venv\Scripts\python.exe tests/smoke_chat.py
.\.venv\Scripts\python.exe tests/smoke_apis_v23.py
.\.venv\Scripts\python.exe tests/smoke_enterprise.py

# 前端
cd frontend; pnpm test        # vitest
pnpm typecheck                # vue-tsc
pnpm build                    # vue-tsc + vite build
```

CI：`.github/workflows/ci.yml` 在 push / PR 时跑 ruff + mypy + `test_agent_engineering.py`。

## 设计规范

页面严格按 `UI设计稿绘制规范.md`（V1.0 画板 / 布局 / 交互）与 `设计系统规范文档.md`（色板 / 字阶 / 间距 / 组件）实现：

- 主色 `#2B5CF5`，中性色 Slate 系，4px 网格间距
- 消息气泡 15px / 1.6，圆角 16px（用户右下 4px / AI 左下 4px）
- 状态条四阶段：规划中 → 执行中 → 校验中 → 生成回答
- 异常态全覆盖：空状态、AI 拒答黄条、网络断连横幅、图纸解析失败态
- 图标必须显式 `import` 自 `@element-plus/icons-vue`（`unplugin-vue-components` 不会自动解析），输入框前缀统一走 `<AiInput>` 封装组件

## 已知说明

- **Windows pnpm 符号链接**：若报 `ERR_PNPM_PACKAGE_MANAGER_SYMLINK_FAILED`，开启开发者模式，或直接 `node node_modules\vite\bin\vite.js` 运行
- **调试开关**：`MainLayout.vue` 的 `netBroken = ref(true)` 可预览"网络断连"全局横幅；`HouseEditorView.vue` 的 `loadFailed = ref(true)` 可预览"图纸解析失败"态
- **首次加载模型**：`bge-small-zh` / `bge-reranker-base` 首次调用需联网下载（默认经 hf-mirror）
- **Agent 门面未接入 UI**：`app/modules/agent/*` 经 `/api/v1/agent|tools|knowledge|admin` 可达，但前端界面尚未使用，属预留能力
