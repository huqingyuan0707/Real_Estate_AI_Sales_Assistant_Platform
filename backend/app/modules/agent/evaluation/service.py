"""评估服务：数据集回放 + LLM-as-judge 打分 + 汇总（发布门禁）。"""
from app.modules.agent.evaluation.datasets import load_golden


class EvaluationService:
    async def run(self, dataset: list[dict] | None = None,
                  agent_version: str = "dev", judge=None) -> dict:
        dataset = dataset if dataset is not None else load_golden()
        results = []
        for case in dataset:
            output = await self._run_case(case)
            score = await self._judge(case, output, judge)
            results.append({"case": case.get("q", case.get("query", ""))[:40], "score": score})
        passed = sum(1 for r in results if r["score"] >= 0.6)
        return {"agent_version": agent_version, "total": len(results),
                "passed": passed, "pass_rate": (passed / len(results)) if results else 1.0,
                "results": results}

    async def _run_case(self, case: dict) -> str:
        try:
            from app.modules.agent.service import get_agent_service_singleton

            svc = get_agent_service_singleton()
            from app.modules.agent.schemas import ChatRequest

            out = await svc.chat(ChatRequest(query=case.get("q", case.get("query", ""))))
            return out.get("answer", "")
        except Exception as e:
            return f"ERROR: {e}"

    async def _judge(self, case: dict, output: str, judge) -> float:
        expected = case.get("a", case.get("expected", ""))
        if judge is not None:
            try:
                return float(await judge(case, output))
            except Exception:
                pass
        if not expected:
            return 1.0 if output and not output.startswith("ERROR") else 0.0
        # 轻量启发式：关键词命中率（无 LLM 时的离线门禁）
        keys = [w for w in str(expected).split() if len(w) > 1][:8] or [str(expected)[:4]]
        hits = sum(1 for k in keys if k in output)
        return hits / max(len(keys), 1)
