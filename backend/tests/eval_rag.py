"""RAG 检索质量离线评估 + 发布门禁（对齐企业级 RAG 文档第七节）

指标：
- Recall@K    期望文档是否出现在最终片段中
- MRR         首个命中期望文档的排名倒数（越接近 1 越好）
- NDCG@K      按相关性折损的排序质量（本实现相关度取 0/1）
- 拒答准确率   应拒答的无关问题是否被拒答

用法（在 backend 目录下执行）：
    python tests/eval_rag.py                # 评估当前知识库（默认 admin 视角）
    python tests/eval_rag.py --seed         # 先入库 fixtures/kb_sample.md 再评估
    python tests/eval_rag.py --json         # 输出 JSON 报告
    python tests/eval_rag.py --no-gate      # 只报告不按门限退出

门禁：任一指标低于 rag_golden.json 的 min_metrics 时返回退出码 1（可接入 CI / 发布检查）。
"""
import argparse
import asyncio
import json
import math
import os
import sys
import time
from pathlib import Path

import httpx

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
os.chdir(BASE)  # Chroma / 上传目录是相对路径，必须在 backend 下运行

from app.services import governance, ingest, judge, rag  # noqa: E402

GOLDEN = Path(__file__).resolve().parent / "rag_golden.json"
SAMPLE = Path(__file__).resolve().parent / "fixtures" / "kb_sample.md"


def seed_sample() -> None:
    """把评估语料入库（幂等：同名会升版本并下线旧向量）"""
    ctx = {"tenant_id": "default", "username": "eval", "role": "admin", "dept": ""}
    rag.delete_by_source(SAMPLE.name)
    stat = ingest.ingest_file(str(SAMPLE), SAMPLE.name, "Markdown", ctx=ctx,
                              security_level="internal", review_status="published")
    print(f"[seed] 已入库 {SAMPLE.name}：{stat['chunks']} 个分块，密级={stat['security_level']}")


def dcg(gains: list[int]) -> float:
    return sum(g / math.log2(i + 2) for i, g in enumerate(gains))


def evaluate() -> dict:
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    ctx = {"tenant_id": "default", "username": "eval", "role": "admin", "dept": "", "levels": governance.LEVELS}

    rows, hit_cnt, mrr_sum, ndcg_sum, judged = [], 0, 0.0, 0.0, 0
    reject_ok, reject_total = 0, 0

    for case in golden["cases"]:
        q, expect = case["q"], case.get("expect_docs") or []
        t0 = time.time()
        hits, rejected, trace = rag.retrieve(q, ctx)
        elapsed = round((time.time() - t0) * 1000)
        got = [h["metadata"].get("source", "") for h in hits]

        if case.get("should_reject"):
            reject_total += 1
            ok = rejected
            reject_ok += 1 if ok else 0
            rows.append({"q": q, "expect_reject": True, "actual_reject": rejected,
                         "top_score": trace.get("top_score", 0.0), "elapsed_ms": elapsed, "pass": ok})
            continue

        judged += 1
        rank = next((i + 1 for i, s in enumerate(got) if s in expect), 0)
        hit = rank > 0
        hit_cnt += 1 if hit else 0
        mrr_sum += (1 / rank) if rank else 0.0
        # NDCG 按文档级去重：同一文档的多个片段不应重复计入相关性
        seen: set[str] = set()
        gains: list[int] = []
        for s in got:
            if s in seen:
                continue
            seen.add(s)
            gains.append(1 if s in expect else 0)
        ideal = dcg([1] * min(len(expect), max(1, len(gains))))
        ndcg_sum += (dcg(gains) / ideal) if ideal else 0.0
        rows.append({"q": q, "expect_docs": expect, "got": got, "rank": rank,
                     "recall": hit, "top_score": trace.get("top_score", 0.0),
                     "recall_detail": trace.get("recall", {}), "blocked": trace.get("blocked", 0),
                     "elapsed_ms": elapsed, "pass": hit})

    return {
        "kb_chunks": rag.kb_count(),
        "cases": len(golden["cases"]),
        "recall_at_k": round(hit_cnt / judged, 4) if judged else 0.0,
        "mrr": round(mrr_sum / judged, 4) if judged else 0.0,
        "ndcg_at_k": round(ndcg_sum / judged, 4) if judged else 0.0,
        "reject_accuracy": round(reject_ok / reject_total, 4) if reject_total else None,
        "min_metrics": golden.get("min_metrics", {}),
        "rows": rows,
    }


def collect_answer(question: str, base: str) -> dict:
    """通过生产 HTTP 链路取一次真实回答（含引用摘要），供 LLM-as-judge 评分"""
    b = f"{base}/api/v1"
    with httpx.Client(timeout=300, trust_env=False) as c:
        login = c.post(f"{b}/auth/login", json={"username": "admin", "password": "123456"})
        token = login.json()["data"]["token"]
        headers = {"Authorization": f"Bearer {token}"}
        answer, refs = "", []
        with c.stream("POST", f"{b}/chat", headers=headers, json={"content": question}) as resp:
            current = ""
            for line in resp.iter_lines():
                if line.startswith("event:"):
                    current = line.split(":", 1)[1].strip()
                elif line.startswith("data:") and current == "message":
                    answer += line[5:].strip()
                elif line.startswith("data:") and current == "done":
                    refs = json.loads(line[5:].strip() or "{}").get("references", [])
    return {"answer": answer, "references": refs}


def run_judge(report: dict, base: str) -> None:
    """LLM-as-judge：用生产链路的真实答案做质量评分（对齐文档第七节）"""
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    print("\n" + "=" * 68)
    print("LLM-as-judge 答案质量评分（1~5 分，取自生产 HTTP 链路）")
    print("=" * 68)
    scores: list[float] = []
    for case in golden["cases"]:
        if case.get("should_reject"):
            continue
        got = collect_answer(case["q"], base)
        hits = [{"text": r.get("snippet") or ""} for r in got.get("references") or []]
        res = asyncio.run(judge.score(case["q"], got["answer"], hits))
        if not res.get("available"):
            print(f"[SKIP] {case['q']} :: {res.get('reason')}")
            continue
        dims = res.get("dimensions") or {}
        scores.append(float(res["overall"] or 0))
        print(f"[{res['overall']}] 相关={dims.get('relevance')} 依据={dims.get('groundedness')} "
              f"完整={dims.get('completeness')} 可读={dims.get('clarity')} :: {case['q']}")
        print(f"      理由：{res.get('reason')}")
    if scores:
        report["judge_avg"] = round(sum(scores) / len(scores), 2)
        report["judge_cases"] = len(scores)
        print(f"\n平均分：{report['judge_avg']} / 5（{len(scores)} 条）")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", action="store_true", help="先入库 fixtures/kb_sample.md")
    ap.add_argument("--json", action="store_true", help="输出 JSON 报告")
    ap.add_argument("--no-gate", action="store_true", help="不做门禁判定")
    ap.add_argument("--judge", action="store_true", help="对真实链路答案做 LLM-as-judge 自动评分（需后端在运行）")
    ap.add_argument("--base", default="http://127.0.0.1:8010", help="--judge 使用的后端地址")
    args = ap.parse_args()

    if args.seed:
        seed_sample()

    report = evaluate()
    if args.judge:
        run_judge(report, args.base)
    m = report["min_metrics"]

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print("=" * 68)
        print(f"RAG 评估报告 | 知识库分块 {report['kb_chunks']} | 用例 {report['cases']}")
        print("=" * 68)
        for r in report["rows"]:
            mark = "PASS" if r["pass"] else "FAIL"
            if r.get("expect_reject"):
                print(f"[{mark}] 拒答用例 score={r['top_score']} reject={r['actual_reject']} :: {r['q']}")
            else:
                print(f"[{mark}] rank={r['rank']} score={r['top_score']} "
                      f"召回(向量/关键词)={r['recall_detail']} 拦截={r['blocked']} :: {r['q']}")
                if not r["pass"]:
                    print(f"        期望 {r['expect_docs']} 实际命中 {r['got']}")
        print("-" * 68)
        print(f"Recall@K={report['recall_at_k']} (门限 {m.get('recall_at_k')})")
        print(f"MRR     ={report['mrr']} (门限 {m.get('mrr')})")
        print(f"NDCG@K  ={report['ndcg_at_k']}")
        print(f"拒答准确率={report['reject_accuracy']} (门限 {m.get('reject_accuracy')})")

    if args.no_gate:
        return 0

    failures = []
    if report["recall_at_k"] < m.get("recall_at_k", 0):
        failures.append(f"Recall@K {report['recall_at_k']} < {m['recall_at_k']}")
    if report["mrr"] < m.get("mrr", 0):
        failures.append(f"MRR {report['mrr']} < {m['mrr']}")
    if report["reject_accuracy"] is not None and report["reject_accuracy"] < m.get("reject_accuracy", 0):
        failures.append(f"拒答准确率 {report['reject_accuracy']} < {m['reject_accuracy']}")

    if failures:
        print("\n[GATE FAILED] 未达发布门限：")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("\n[GATE PASSED] 全部指标达标，可发布")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
