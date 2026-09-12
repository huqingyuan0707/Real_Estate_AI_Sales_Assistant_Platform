"""应用配置（Pydantic Settings，支持 .env 覆盖）

大模型接入约定（技术方案 5.2.1 / V2.2.1）：
- 智能对话：Qwen2.5 本地部署，经 OpenAI 兼容接口调用
  （Ollama 默认 http://127.0.0.1:11434/v1；vLLM/LM Studio 同理改 BASE_URL）
- 一键装修图：ComfyUI 工作流（ControlNet-MLSD + SDXL + 风格LoRA + RealESRGAN）
- 两项服务均不可用时自动降级为演示模式，页面功能不受影响
"""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    APP_NAME: str = "Real Estate AI Assistant Platform"
    APP_VERSION: str = "0.2.0-llm"
    API_V1_PREFIX: str = "/api/v1"
    CORS_ORIGINS: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    # ---- 智能对话：Qwen2.5（OpenAI 兼容协议）----
    LLM_BASE_URL: str = "http://127.0.0.1:11434/v1"  # Ollama 默认；vLLM: http://host:8000/v1
    LLM_MODEL: str = "qwen2.5:14b"                   # ollama pull qwen2.5:14b
    LLM_API_KEY: str = "ollama"                      # Ollama 不校验，占位即可
    LLM_TIMEOUT: float = 120.0                       # 流式总超时（秒）
    LLM_ENABLED: bool = True                         # False 可强制走演示模式

    # ---- AI 一键装修图：云端生图 API（优先）/ ComfyUI / 演示 ----
    RENDER_PROVIDER: str = "auto"                    # auto=按 Key/服务自动降级链；可强制 siliconflow/dashscope/comfyui/simulate
    RENDER_API_BASE: str = "https://api.siliconflow.cn/v1"   # 硅基流动；通义万相填 https://dashscope.aliyuncs.com/api/v1
    RENDER_API_KEY: str = ""                         # 填入后自动启用云端生图（auto 模式）
    RENDER_API_MODEL: str = "Kwai-Kolors/Kolors"     # 硅基流动：Kolors 快且支持图生图；Qwen/Qwen-Image 质量高
    RENDER_API_STEPS: int = 20                       # num_inference_steps
    RENDER_API_GUIDANCE: float = 7.5                 # guidance_scale（Qwen-Image 建议 4.0 左右）
    RENDER_API_TIMEOUT: float = 120.0                # 云端生成超时（秒）
    COMFYUI_BASE_URL: str = "http://127.0.0.1:8188"
    COMFYUI_WORKFLOW: str = ""                       # 可选：api 格式 workflow JSON 文件路径
    RENDER_SIM_SECONDS: float = 6.0                  # 演示模式：模拟渲染耗时

    # ---- 装修三步流水线：空间理解(VLM) + 布局规划(LLM)（复用 RENDER_API_KEY，硅基流动）----
    SPACE_AI_ENABLED: bool = True                    # False 强制关闭，直接走规则模板
    SPACE_VLM_MODEL: str = "Qwen/Qwen3-VL-32B-Instruct"      # 第一步：看懂空间（多模态；Qwen2.5-VL 已被硅基流动下架）
    SPACE_LLM_MODEL: str = "Qwen/Qwen3-30B-A3B-Instruct-2507"  # 第二步：构思布局（7B 输出 JSON 损坏率高）
    SPACE_AI_TIMEOUT: float = 60.0                   # 单步超时（秒），超时/失败自动降级

    # ---- 知识库 RAG（离线入库 + 在线问答）----
    RAG_EMBED_MODEL: str = "BAAI/bge-small-zh-v1.5"   # 向量化
    RAG_RERANK_MODEL: str = "BAAI/bge-reranker-base"  # 重排序
    RAG_CHROMA_DIR: str = "data/chroma"               # Chroma 持久化目录
    RAG_UPLOAD_DIR: str = "data/uploads"              # 原始文件落盘目录
    RAG_CHUNK_SIZE: int = 500                         # 分块目标长度（字符）
    RAG_CHUNK_OVERLAP: int = 80                       # 相邻块重叠
    RAG_TOP_K: int = 10                               # 向量召回数
    RAG_FINAL_K: int = 4                              # 重排后保留片段数
    # 拒答阈值（rerank sigmoid 后）：由 tests/eval_rag.py 评估校准——相关知识 ≈0.72、
    # 无关知识 ≈0.50，取 0.6 可有效分开；早期 0.25 几乎不过滤，拒答形同虚设
    RAG_MIN_SCORE: float = 0.6
    HF_ENDPOINT: str = "https://hf-mirror.com"        # HuggingFace 镜像（国内下载模型）
    RAG_RECALL_MULTIPLIER: int = 3                    # 双路召回时 Top-K 放大倍数（融合前候选池）
    RAG_RRF_K: int = 60                               # RRF 融合常数（越大越扁平）
    RAG_FAITHFUL_MIN: float = 0.6                     # 幻觉检测低可信阈值（低于则追加核对提示）
    RAG_CACHE_TTL: int = 300                          # 检索/生成缓存有效期（秒）
    RAG_RATE_LIMIT_PER_MIN: int = 30                  # 单用户每分钟问答上限（超出返回 2002 限流）
    # ---- 外部存储（可选：未安装/连不上时自动回退内置实现）----
    VECTOR_BACKEND: str = "chroma"                    # chroma（默认）/ milvus
    MILVUS_URI: str = "http://127.0.0.1:19530"
    MILVUS_COLLECTION: str = "reai_kb"
    KEYWORD_BACKEND: str = "builtin"                  # builtin（内置 BM25）/ elasticsearch
    ES_URL: str = "http://127.0.0.1:9200"
    ES_INDEX: str = "reai_kb"
    RAG_EMBED_DIM: int = 512                          # 向量维度（bge-small-zh-v1.5 = 512）

    # ---- 链路追踪（Langfuse，可选；未配置仅写本地 JSONL，不外发任何请求）----
    LANGFUSE_HOST: str = ""
    LANGFUSE_PUBLIC_KEY: str = ""
    LANGFUSE_SECRET_KEY: str = ""
    LANGFUSE_BATCH_SIZE: int = 10

    # ---- SSO/OIDC 单点登录（可选；标准授权码流程）----
    OIDC_ISSUER: str = ""
    OIDC_CLIENT_ID: str = ""
    OIDC_CLIENT_SECRET: str = ""
    OIDC_REDIRECT_URI: str = "http://localhost:5173/login"
    OIDC_SCOPES: str = "openid profile email"
    OIDC_AUTO_CREATE: bool = True                     # IdP 新用户自动创建为 member
    OIDC_MOCK: bool = False                           # 开发用内置 mock IdP（仅本地验证流程）

    # ---- LDAP 目录认证（可选；仅做身份鉴别，账号须在 users.json 存在）----
    LDAP_URI: str = ""
    LDAP_BASE_DN: str = ""
    LDAP_USER_TEMPLATE: str = "uid={username},ou=people,{base_dn}"

    # ---- 等保合规（身份鉴别 / 安全审计 / 数据完整性）----
    PASSWORD_MIN_LEN: int = 8
    LOGIN_FAIL_LIMIT: int = 5                         # 连续失败 N 次锁定
    LOGIN_LOCK_SECONDS: int = 900                     # 锁定 15 分钟

    RAG_PARENT_ENABLED: bool = True                   # 父子上块：小块检索、大块生成
    RAG_PARENT_MULTIPLIER: int = 4                    # 父块大小 ≈ 子块 × N
    RAG_PARENT_MAX_CHARS: int = 1600                  # 注入 Prompt 的父块最大字符数
    RAG_MAX_PER_SECTION: int = 2                      # 同一章节最多保留片段数（结果多样性）

    # ---- 可观测与成本归因 ----
    LLM_PRICE_PER_1K_TOKENS: float = 0.0              # 生成单价（元/千 token）；本地 Ollama 为 0
    SECURITY_ALERT_MARK: bool = True                  # 越权/注入事件是否在 trace 中标记

    # ---- 记忆管理 ----
    MEM_WINDOW: int = 12                              # 短期记忆滑动窗口（消息条数）
    MEM_TOKEN_BUDGET: int = 2000                      # 短期记忆 Token 预算（估算）
    MEM_SENSITIVE_TTL_DAYS: int = 30                  # 敏感长期记忆默认过期天数
    MEM_STORE_PATH: str = "data/memory_store.json"    # 长期记忆持久化文件

    # ---- 认证 / RBAC ----
    SECRET_KEY: str = "reai-demo-secret-change-in-prod"   # Token 签名密钥（生产用环境变量覆盖）
    TOKEN_EXPIRE_HOURS: int = 12                          # 登录 Token 有效期（小时）

    class Config:
        env_file = ".env"


settings = Settings()
