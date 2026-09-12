"""在线问答冒烟（HTTP 层）：验证企业级 RAG 治理链路的端到端行为

覆盖：登录 → /chat SSE 协议（source/phase/message/done）→ 引用可定位与密级标注
     → 安全字段（注入告警 / 治理拦截 / 脱敏）→ 幻觉检测（引用覆盖率 / 数值一致性）
     → TTL 生成缓存（第二次相同提问命中缓存）→ 可观测事件落库

用法（需后端已启动）：
    python tests/smoke_chat.py                    # 默认 http://127.0.0.1:8010
    python tests/smoke_chat.py http://127.0.0.1:8010
"""
import json
import sys

import httpx

# Windows 控制台默认 GBK，中文/符号会抛 UnicodeEncodeError；统一按 UTF-8 输出
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8010") + "/api/v1"
QUESTION = "契税税率怎么计算？"


def ask(client: httpx.Client, headers: dict, question: str) -> tuple[str, dict, list[str]]:
    """一次 SSE 问答：返回 (答案, done 载荷, 事件序列)"""
    answer, done, events = "", {}, []
    with client.stream("POST", f"{BASE}/chat", headers=headers,
                       json={"content": question, "thread_id": "smoke-rag"}) as resp:
        ctype = resp.headers.get("content-type") or ""
        if "text/event-stream" not in ctype:
            raise RuntimeError(f"非流式响应 HTTP {resp.status_code}：{resp.read().decode()[:200]}")
        current = ""
        for line in resp.iter_lines():
            if line.startswith("event:"):
                current = line.split(":", 1)[1].strip()
                events.append(current)
            elif line.startswith("data:") and current == "message":
                answer += line[5:].strip()
            elif line.startswith("data:") and current == "done":
                done = json.loads(line[5:].strip() or "{}")
    return answer, done, events


def main() -> int:
    with httpx.Client(timeout=300, trust_env=False) as c:
        login = c.post(f"{BASE}/auth/login", json={"username": "admin", "password": "123456"})
        login.raise_for_status()
        headers = {"Authorization": f"Bearer {login.json()['data']['token']}"}

        print("=" * 68)
        print(f"提问：{QUESTION}")
        print("=" * 68)
        answer, done, events = ask(c, headers, QUESTION)
        print(f"事件序列：{' → '.join(dict.fromkeys(events))}")
        print(f"答案长度：{len(answer)} 字\n答案预览：{answer[:180]}...")

        refs = done.get("references") or []
        print(f"\n引用 {len(refs)} 条：")
        for rf in refs[:4]:
            loc = " > ".join(x for x in [rf.get("title"), rf.get("section"), f"第{rf.get('page')}页"] if x)
            print(f"  · 《{loc}》 相关度 {rf.get('score')}% 密级 {rf.get('security_level')}")

        print(f"\n治理与安全：{json.dumps(done.get('guard', {}), ensure_ascii=False)}")
        faith = done.get("faithfulness") or {}
        if faith.get("checked"):
            print(f"幻觉检测：可信度 {round((faith.get('score') or 0) * 100)}% [{faith.get('level')}]"
                  f" · 引用覆盖 {faith.get('cited_ratio')} · 越界引用 {len(faith.get('invalid_refs') or [])} 个")
            for w in faith.get("warnings") or []:
                print(f"  ⚠️ {w}")
        print(f"trace_id：{done.get('trace_id')} · 模型：{done.get('model')}")

        # TTL 生成缓存：相同提问第二次应命中缓存（知识库未变更时）
        answer2, done2, _ = ask(c, headers, QUESTION)
        cached = bool(done2.get("cached"))
        print(f"\n第二次相同提问 → 命中生成缓存：{cached}")

        stats = c.get(f"{BASE}/feedback/stats", headers=headers).json()["data"]
        rag, cache_info = stats["rag"], stats["cache"]
        print("\n可观测（累计）：")
        print(f"  问答 {rag['total']} 次 · 拒答率 {rag['reject_rate']} · 平均耗时 {rag['avg_elapsed_ms']}ms"
              f" · 平均召回 {rag['avg_recall']} · 拦截 {rag['blocked_total']} · 注入告警 {rag['injection_alerts']}")
        print(f"  平均可信度 {rag.get('avg_faithfulness')} · 低可信 {rag.get('low_faith_count')} 次"
              f" · 缓存命中率 {cache_info.get('hit_rate')}")

    ok = bool(answer) and bool(refs) and len(events) >= 3 and faith.get("checked") and cached
    print("\n[SMOKE PASSED]" if ok else "\n[SMOKE FAILED]")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
