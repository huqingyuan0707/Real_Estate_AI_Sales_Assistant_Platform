"""错误码规范（对齐技术方案 5.4，五位数分段：1xxxx 通用 / 2xxxx RAG对话 / 3xxxx 户型Skill / 5xxxx 系统）"""


class ErrorCode:
    OK = 0
    PARAM_INVALID = 1001          # 400 参数校验失败
    UNAUTHORIZED = 1002           # 401 未认证 / Token 过期
    FORBIDDEN = 1003              # 403 权限不足（RBAC）
    NOT_FOUND = 1004              # 404 资源不存在
    NETWORK_UNSTABLE = 1005       # 504 请求超时
    RAG_REJECT = 2001             # 422 知识库召回置信度不足（拒答）
    RATE_LIMITED = 2002           # 429 限流触发
    HOUSE_PARSE_FAILED = 3001     # 422 户型解析失败
    RULE_VALIDATE_FAILED = 3002   # 422 规则校验失败
    THIRD_PARTY_TIMEOUT = 3003    # 504 第三方 API 超时/失败
    TASK_CONFLICT = 4001          # 409 异步任务冲突（重复提交）
    TASK_EXPIRED = 4002           # 410 异步任务已过期（结果被清理）
    INTERNAL_ERROR = 5000         # 500 系统内部错误
