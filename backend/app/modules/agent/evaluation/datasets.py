"""评估数据集：黄金问答对 + 回放用例（发布门禁输入）。"""
import json
from pathlib import Path


def load_golden(path: str | None = None) -> list[dict]:
    candidates = [
        path,
        "backend/tests/rag_golden.json",
        "tests/rag_golden.json",
        str(Path(__file__).resolve().parents[4] / "tests" / "rag_golden.json"),
    ]
    for c in candidates:
        if not c:
            continue
        try:
            p = Path(c)
            if p.exists():
                return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
    return []
