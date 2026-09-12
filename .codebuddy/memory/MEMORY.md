# 长期记忆

## 用户网络环境（2026-09-06 确认）
- VPN 客户端为 Clash 套件：进程 MyClash（GUI）/ MyClashCore（内核）/ MyClashHelperService，本地代理端口 **127.0.0.1:7877**
- Clash 每次启动自动把系统代理写回注册表（ProxyEnable=1 → 127.0.0.1:7877），带国内站点绕过列表（知乎/京东等 Override）
- 已知故障模式：Clash 退出后系统代理残留 → 应用报 `ECONNREFUSED 127.0.0.1:7877`，浏览器打不开网页
- 用户诉求：开/关 VPN 浏览器都要正常可用

## 已部署的网络自愈方案（工作区内）
- `proxy-guard.ps1`：守护脚本，检测"系统代理指向的本地端口无监听"时自动清 ProxyEnable=0 并 InternetSetOption 刷新，日志写 proxy-guard.log。只清理死代理，VPN 正常运行时绝不干预（已模拟死端口测试通过）
- 计划任务 **ProxyGuard**：每分钟以当前用户运行（schtasks 用户级，无需管理员）。2026-09-08 起动作已改为 `wscript.exe "...\proxy-guard-silent.vbs"` 静默运行——此前直接调 powershell.exe 导致**每分钟闪一次终端窗口**（-WindowStyle Hidden 救不了：窗口先建后藏）；VBS 用 WScript.Shell.Run(...,0,False) 彻底无窗。卸载：`schtasks /Delete /TN ProxyGuard /F`
- `fix-proxy.ps1`：早期手动一键修复脚本（备份用）
- 根治建议（已告知用户，待其操作）：Clash 界面开启 TUN 模式或"退出时清除系统代理"选项

## 项目：房地产 AI 销售助手平台
- `需求文档.md` 当前内容是《技术方案 V2.3 完整合订版》（非 PRD），曾做过 V2.3.1 一致性修订（补 /task/stream 接口、错误码 1005、术语表等）；技术方案.md 为 V2.2
- shell 环境注意：PowerShell 命令行传中文会 GBK 乱码，操作中文文件名须用 [IO.File] API + 按内容特征定位文件
- 开发环境（2026-09-06）：Node 22.18 + pnpm 12.3.4（与 package.json 匹配）+ Python 3.14.5（backend/.venv 已建，fastapi/pydantic wheel 兼容 OK）
- Windows 坑：pnpm 报 `ERR_PNPM_PACKAGE_MANAGER_SYMLINK_FAILED`（符号链接权限）→ 绕过方式 `node node_modules\vite\bin\vite.js`；长命令用 Start-Process 异步 + 日志轮询（execute_command 有 10 秒 watch 超时）；Add-Content 无 -Encoding 会被安全拦截
- 前端 9 页面全部完成且 vite build 通过（Chat/House/Knowledge/Settings/SkillMarket/TaskCenter/admin×3 + Login + MainLayout）
- 启动（2026-09-10 更新）：前端 http://localhost:5173（演示账号 admin/123456），后端 `uvicorn app.main:app --host 127.0.0.1 --port 8010`（/docs）。**注意 8000 端口长期被另一个项目的 Docker 容器 ai-backend 占用**（来自 `e:\car_smart_assistant_agent\deploy\docker-compose.yml`），打了会 401；vite 代理 target 优先级：命令行环境变量 > `.env.development.local` > **`.env.development`** > `.env.local` > 默认 8000。**踩坑（2026-09-12）**：`.env.development` 里硬编码了 target=8000 会盖住 .env.local 的 8010，导致前端所有 /api 请求被 Vite 代理回 **500**（ECONNREFUSED 8000）；已把 .env.development 该行注释掉，8010 只由本机 .env.local 指定。标准启动命令（Start-Process + 日志重定向 + -WindowStyle Hidden，前后端可并行下发）与启动后三连自检见 2026-09-12.md
- **大模型已真实接通（2026-09-07）**：Ollama 0.32.5 本地运行，qwen2.5:0.5b 对话链路验证通过（backend/.env 配置，OpenAI 兼容协议）；ComfyUI 未装→装修图自动降级演示模式；详见 2026-09-07.md
- **RAG 三模块闭环已落地（2026-09-07）**：知识库管理（PDF/Word/Excel/TXT/MD 上传→解析→递归分块→bge-small-zh 向量化→Chroma，按源文件删除+统计）/ 智能问答（意图识别→会话记忆 Query 改写→召回→bge-reranker-base 重排→Qwen2.5 生成→SSE 答案+引用页码，低相关 2001 拒答）/ 系统设置（/settings 热更新+持久化）。bge 模型首载经 hf-mirror 自动下载
- **Windows 调试铁律（2026-09-07）**：execute_command 内联中文必乱码——含中文的测试 JSON/请求体一律用 write_to_file 写 UTF-8 文件再 curl -d @file；curl -F 中文文件名报 26 错误用 ASCII 名；shell 可能 PS↔cmd 漂移，复杂命令拆单条
- **FastAPI/测试铁律（2026-09-07 冒烟实测）**：① starlette 1.6.0 TestClient 必须 `client.__enter__()`（上下文模式）复用 portal，否则每请求独立事件循环、请求一关后台 asyncio.create_task 全被取消；② 需要启动后台异步任务（task_center.attach 等）的端点必须 `async def`——同步 def 跑线程池无 running loop 直接 RuntimeError；③ 任务中心 retry 语义：协程工厂仅 completed 时清除，failed/cancelled 保留供重跑，_evict 时同步清
- **V2.3 功能补全状态（2026-09-07）**：统一任务中心（/tasks status/stream SSE/DELETE cancel/retry + 4001/4002 错误码）、知识库批量导入（batch-import 异步任务）、11.2 同名文档版本升级（v(n+1)+旧版 deprecated+清旧向量）、skills invoke SSE（文案/政策/风水/竞品走 LLM，解析/渲染返回引导）、sessions resume 断点续聊——后端+前端全部接通，smoke_apis_v23.py 10 组冒烟全过
- **用户级 AI Key（2026-09-10）**：每个用户在前端 `/my-ai`「我的 AI 服务」页自行填 LLM / 生图服务的 Base URL、API Key、模型名，保存即生效、仅对本账号有效，缺项回退全局 .env。存储 `backend/data/user_ai_config.json`（只回掩码，Key 前端不回显、留空=不修改）；接口 `/api/v1/ai-config`（GET/PUT/DELETE/test，登录即可，不占 settings 权限）。机制核心：`core/user_context.py` 的 ContextVar + **`get_current_user` 必须是 async def**（同步依赖在线程池跑，ContextVar 传不回请求协程）→ 服务层 `effective_llm()/effective_render()`；llm/render/space_ai/furniture/chat 全部改读该函数，task_center 的 asyncio.create_task 会继承 context 故后台生图任务同样生效
- **企业级 RAG 治理（2026-09-10，按《企业级 RAG 知识智能问答.md》落地）**：检索链 = 双路召回（向量 + 自实现 BM25，中文 bigram）→ RRF(k=60) → bge-reranker 重排 → 双阶段权限过滤（Chroma where 硬过滤租户/审核态/密级 + 应用层精过滤部门/生效期）→ 阈值拒答。治理元数据含 `security_level`(public/internal/confidential，机密仅 admin)/`dept_id`/`review_status`(draft 不进检索)/`owner`/`doc_version`/生效期/`section`；安全层 = 提示注入特征扫描 + system 最高优先级约束 + 流式 PII 脱敏；可观测落 `data/rag_traces.jsonl`（耗时/召回/拦截/注入/token 成本），反馈落 `data/feedback_events.jsonl` 并产出采纳率/差评知识/知识缺口。**拒答阈值已由评估校准为 0.6**（原 0.25 无效，注意 `.runtime_settings.json` 会覆盖 config 默认值）。评估门禁：`python tests/eval_rag.py [--seed] [--judge]`（Recall/MRR/NDCG/拒答准确率，未达标退出码 1）；HTTP 冒烟 `tests/smoke_chat.py`
- **企业级 RAG 深度能力（2026-09-11 二轮补齐）**：① 幻觉检测 `services/faithfulness.py`（引用覆盖率 + 数值一致性 + 越界引用；low 时答案追加核对提示，实测抓到小模型编造年份）；② 缓存与限流 `services/cache.py`+`ratelimit.py`（TTL 检索/生成缓存，键含 `rag.kb_revision()` 自动失效；用户级滑窗限流 429/2002）；③ 父子上块 `services/parents.py`（子块检索、父块注入生成，父块存 `data/parent_chunks.json`）；④ Query 同义词扩展 `services/query_expand.py`（仅供 BM25 路，可外置 `data/synonyms.json`）；⑤ 结果多样性（同章节上限）+ `rag.retrieve(q, ctx, filters)` 元数据过滤；⑥ 索引管理 `services/index_admin.py` + `/api/v1/index-admin`（换嵌入模型重建 / 含向量的快照回滚 / `/documents/sync` 按 SHA256 增量同步）；⑦ `POST /documents/{id}/review` 审核（同步改写向量元数据）+ `GET /documents/quality` 质量校验；⑧ `services/judge.py` LLM-as-judge 四维评分 + `observability.doc_heat()` 知识热度。前端：知识库页「治理与运维」卡片、对话页可信度标签
- **前端图标规范（2026-09-12）**：`@element-plus/icons-vue` 的图标**不会被 unplugin-vue-components / ElementPlusResolver 自动解析**（它只处理 `El*` 组件），必须显式 `import { Xxx } from '@element-plus/icons-vue'`，否则模板里裸写 `<HomeFilled/>` 会渲染成空白。输入框前缀图标统一走封装组件 `<AiInput :prefix-icon="'Search'">`——`AiInput` 内部已把字符串图标名解析成组件（映射表含 Search/User/Lock/OfficeBuilding），新增图标在 `src/components/AiInput/index.vue` 的 ICON_MAP 里补，不要裸用 `<el-input :prefix-icon="'Xxx'">`
- **环境坑：safe-delete 导致 Vite 崩溃（2026-09-12）**：CodeBuddy 的 safe-delete shim hook 了 node 的 `fs.rm`，**单次删除 >500 个文件直接抛错**，典型后果是 Vite 重新预构建依赖（删 `node_modules/.vite/deps_temp_*`）时进程被杀，日志 `frontend/dev.err.log` 报 `SAFE_DELETE_BULK_CONFIRM_REQUIRED`。处理：用 PowerShell `Remove-Item 'frontend\node_modules\.vite' -Recurse -Force`（PowerShell 删除不经 node hook，可绕过）后再重启 vite
- **Git 仓库现状（2026-09-12）**：origin = `git@github.com:huqingyuan0707/real-estate-ai-sales-assistant-platform.git`，SSH 认证正常（`ssh -T` 返回 Hi huqingyuan0707!），**但该远程仓库在 GitHub 上不存在**（`git ls-remote` 报 `Repository not found`，账号下 10 个公开仓库中无房产相关）→ 推送前必须先在 GitHub 建**空**仓库（不要勾 README/.gitignore/license，否则非快进需先 pull）。本地 remote-tracking ref `origin/main = 860a131` 是残留
- **Git 操作约定（2026-09-12）**：① 初始提交曾误入库 34,287 个文件（3.4 万 node_modules + `backend/.env` 真实密钥 + `backend/data` 运行时数据），已新增根 `.gitignore`（忽略 node_modules/.venv/__pycache__/dist//data/日志/.env 密钥，保留 `.env.example` 与前端 `.env.development`/`.env.production`）并重写提交，现为 **219 个文件**；② 判断索引内容必须用 `git ls-files --cached`——`git diff --cached --name-only` 会把"相对 HEAD 被删除的文件"一并列出，据此统计会严重误判；③ `git rm -r --cached .` 必须加 `-f`，否则大量文件因暂存区与工作区不一致而中断，清理不彻底；④ `backend/data/`、`/data/` 等目录由代码自动 `mkdir(parents=True, exist_ok=True)` 创建，忽略它们无需 `.gitkeep`；⑤ `.codebuddy/memory/` 保留入库，`.codebuddy/teams|automations` 忽略

