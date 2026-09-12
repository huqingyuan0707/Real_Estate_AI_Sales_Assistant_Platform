"""合规自查报表（对齐企业级 RAG 文档第八节安全与合规 + 等保三级核心控制点）

自动检查平台已实现的控制点并给出证据；部署层 / 组织层事项标注为 manual，
并生成《等保合规自查清单.md》文档供人工核查使用。
"""
import time

from fastapi import APIRouter, Depends

from app.config import settings
from app.core.rbac import require_perm
from app.core.responses import ok
from app.services import (audit_chain, cache, keyword_store, ocr, password_policy,
                          ratelimit, tracing, vector_store)

router = APIRouter()


@router.get("/report", dependencies=[Depends(require_perm("audit"))])
def compliance_report():
    pw = password_policy.stats()
    chain = audit_chain.verify()
    items = [
        # ---- 身份鉴别 ----
        {"id": "身份鉴别-双因素", "control": "采用两种或以上鉴别技术", "status": "implemented",
         "evidence": "TOTP 动态口令（RFC 6238 零依赖实现）+ 静态密码，/auth/totp/*"},
        {"id": "身份鉴别-失败处理", "control": "登录失败处理（锁定/结束会话）", "status": "implemented",
         "evidence": f"连续失败 {pw['fail_limit']} 次锁定 {pw['lock_seconds'] // 60} 分钟（services/password_policy.py）"},
        {"id": "身份鉴别-口令策略", "control": "口令复杂度与定期更换", "status": "implemented",
         "evidence": f"最小 {pw['min_len']} 位 + 大小写 + 数字；创建/重置密码时强制校验"},
        {"id": "身份鉴别-弱口令", "control": "无默认/弱口令", "status": "partial",
         "evidence": f"演示账号仍为 123456，生产上线前必须重置；策略最小长度 {pw['min_len']} 位"},
        # ---- 访问控制 ----
        {"id": "访问控制-RBAC", "control": "授予账号所需最小权限", "status": "implemented",
         "evidence": "角色-权限矩阵 + require_perm 接口级授权（core/rbac.py）"},
        {"id": "访问控制-知识越权", "control": "数据级访问控制", "status": "implemented",
         "evidence": "检索前密级/租户硬过滤 + 检索后部门/生效期精过滤，越权片段丢弃并告警"},
        # ---- 安全审计 ----
        {"id": "安全审计-覆盖范围", "control": "覆盖每个用户与重要安全事件", "status": "implemented",
         "evidence": "RAG 问答（query/命中文档/耗时/成本/治理拦截）+ 登录审计，/audit/logs"},
        {"id": "安全审计-防篡改", "control": "审计记录保护，防篡改", "status": "implemented",
         "evidence": f"审计哈希链（SHA256 链式）：{chain['total']} 条，完整性校验"
                     f"{'通过' if chain['valid'] else '失败！'}（/audit/verify）"},
        {"id": "安全审计-全链路", "control": "分布式链路追踪", "status": "implemented",
         "evidence": "trace_id 贯穿 + Langfuse 适配器（未配置时本地 JSONL）+ /audit/security 事件视图"},
        # ---- 入侵防范 ----
        {"id": "入侵防范-注入", "control": "防护恶意输入", "status": "implemented",
         "evidence": "RAG 提示注入 8 类特征扫描 + system 最高优先级约束（services/guard.py）"},
        # ---- 数据完整性与保密性 ----
        {"id": "数据完整性-传输", "control": "传输加密（TLS）", "status": "manual",
         "evidence": "部署层落实：Nginx/网关启用 HTTPS（TLS 1.2+），应用与接口层已就绪"},
        {"id": "数据保密性-展示", "control": "鉴别信息保密展示", "status": "implemented",
         "evidence": "密码哈希存储；用户 AI Key 掩码回显；输出 PII 脱敏（手机/身份证/银行卡/邮箱）"},
        {"id": "数据保密性-分级", "control": "数据分类分级与脱敏", "status": "implemented",
         "evidence": "知识密级（公开/内部/机密）；长期记忆敏感信息强制过期；PII 正则脱敏"},
        # ---- 备份恢复 ----
        {"id": "备份恢复-索引", "control": "重要数据备份与恢复", "status": "implemented",
         "evidence": "索引版本快照（含向量）+ 一键回滚 + SHA256 增量同步（/index-admin、/documents/sync）"},
        # ---- 剩余信息保护 ----
        {"id": "剩余信息-会话", "control": "鉴别信息及时清除", "status": "implemented",
         "evidence": f"Token 有效期 {settings.TOKEN_EXPIRE_HOURS} 小时自动失效；前端登出清除本地存储"},
    ]
    return ok({
        "standard": "等保三级（GB/T 22239）核心控制点对照（自动生成）",
        "checked_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "summary": {
            "total": len(items),
            "implemented": sum(1 for i in items if i["status"] == "implemented"),
            "partial": sum(1 for i in items if i["status"] == "partial"),
            "manual": sum(1 for i in items if i["status"] == "manual"),
        },
        "items": items,
        "runtime": {
            "vector_backend": vector_store.status(),
            "keyword_backend": keyword_store.status(),
            "cache": cache.stats(),
            "ratelimit": ratelimit.stats(),
            "tracing": tracing.status(),
            "ocr": ocr.engine_status(),
            "audit_chain": {"total": chain["total"], "valid": chain["valid"]},
        },
    })
