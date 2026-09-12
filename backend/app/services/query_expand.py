"""Query 扩展（同义词 / 别名 / 缩写，对齐企业级 RAG 文档第四节）

同一概念在企业语料里常有多种说法（限购 / 购房资格 / 购房限制），只走向量召回容易漏召。
本模块维护领域同义词表，把查询扩展为多词串——**仅供 BM25 关键词路使用**，
向量召回与重排仍以原始问句为基准，避免语义漂移。

词表：backend/data/synonyms.json（不存在时使用内置房地产领域词表）
"""
import json
from pathlib import Path

_PATH = Path(__file__).resolve().parents[2] / "data" / "synonyms.json"

_BUILTIN: dict[str, list[str]] = {
    "限购": ["购房资格", "购房限制", "限购政策", "套数限制"],
    "限售": ["转让限制", "上市交易限制"],
    "得房率": ["套内使用率", "实用率", "套内面积占比"],
    "首付": ["首付款", "首付比例", "最低首付"],
    "契税": ["契税税率", "交易契税"],
    "增值税": ["增值税及附加", "营业税"],
    "个税": ["个人所得税", "转让所得税"],
    "公积金": ["住房公积金", "公积金贷款"],
    "商贷": ["商业贷款", "商业性个人住房贷款"],
    "LPR": ["贷款市场报价利率", "利率下限"],
    "公摊": ["公摊面积", "公用建筑面积"],
    "容积率": ["容积率指标", "建筑密度"],
    "绿化率": ["绿地率", "绿化覆盖"],
    "面积": ["建筑面积", "套内建筑面积"],
    "学区": ["学区房", "教育资源"],
    "朝向": ["坐向", "采光朝向"],
    "楼层": ["层高", "所在楼层"],
    "物业": ["物业管理", "物业服务费"],
}

_CACHE: dict[str, list[str]] | None = None


def _load() -> dict[str, list[str]]:
    global _CACHE
    if _CACHE is None:
        try:
            with open(_PATH, encoding="utf-8") as f:
                _CACHE = {**(_BUILTIN), **json.load(f)}
        except Exception:
            _CACHE = dict(_BUILTIN)
    return _CACHE


def expand(query: str) -> tuple[str, list[str]]:
    """返回 (扩展后的检索串, 命中的同义词列表)；无命中时原样返回"""
    data = _load()
    low = (query or "").lower()
    extra: list[str] = []
    for word, syns in data.items():
        if word.lower() in low:
            extra.extend(s for s in syns if s.lower() not in low)
    if not extra:
        return query, []
    uniq = list(dict.fromkeys(extra))
    return f"{query} {' '.join(uniq)}", uniq
