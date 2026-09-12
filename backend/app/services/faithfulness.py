"""幻觉检测与引用一致性校验（对齐企业级 RAG 文档第五节、第七节）

生成后对答案做三项一致性校验，产出可展示的「可信度」信号，作为"无依据不回答"的兜底：
1) 引用覆盖率：含 [片段N] 标注的结论句占比（长句无引用 = 可能无依据）
2) 数值一致性：答案中的数值能否在引用片段里找到（找不到 = 疑似编造）
3) 引用有效性：[片段N] 越界（超出实际提供的片段数）= 伪造出处

score ∈ [0,1]，level = high(≥0.85) / medium(≥RAG_FAITHFUL_MIN) / low；
low 时在回答末尾追加"建议核对原文"提示，并随 SSE done 事件回传，计入可观测指标。
"""
import re

from app.config import settings

_ARABIC_RE = re.compile(r"\d+(?:\.\d+)?")
_CN_RE = re.compile(r"[零一二两三四五六七八九十百千万]+(?:点[零一二三四五六七八九]+)?")
_CITE_RE = re.compile(r"\[\s*片段\s*(\d+)\s*\]")
_SENT_SPLIT = re.compile(r"[。！？!?\n]")
_TRIVIAL = re.compile(r"以上内容仅供|以官方口径为准|暂无相关资料")
_MIN_SENT_LEN = 12          # 短于此长度的句子不参与覆盖率统计（标题/过渡句）

_CN_DIGITS = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
              "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
_CN_UNITS = {"十": 10, "百": 100, "千": 1000, "万": 10000}


def _cn_int(text: str) -> int | None:
    if not text:
        return None
    total, section, num = 0, 0, 0
    for ch in text:
        if ch in _CN_DIGITS:
            num = _CN_DIGITS[ch]
        elif ch in _CN_UNITS:
            unit = _CN_UNITS[ch]
            if unit == 10000:
                section = (section + num) * unit
                total += section
                section = num = 0
            else:
                section += (num or 1) * unit
                num = 0
        else:
            return None
    return total + section + num


def _cn_to_number(text: str) -> str | None:
    """中文数字 → 阿拉伯字符串（支持 一~万 与 X点Y）"""
    if "点" in text:
        head, _, tail = text.partition("点")
        a, b = _cn_int(head), _cn_int(tail)
        return f"{a}.{b}" if a is not None and b is not None else None
    v = _cn_int(text)
    return str(v) if v is not None else None


def _numbers(text: str) -> set[str]:
    """抽取数值并归一（阿拉伯 + 中文），用于答案与上下文的一致性比对"""
    out: set[str] = set()
    for m in _ARABIC_RE.findall(text or ""):
        out.add(m.rstrip("0").rstrip(".") if "." in m else m)
    for m in _CN_RE.finditer(text or ""):
        v = _cn_to_number(m.group())
        if v:
            out.add(v)
    return out


def _significant(num: str) -> bool:
    """过滤噪音数值：1/2 多为序号或页码，不作为"编造"依据"""
    try:
        return float(num) not in (1.0, 2.0)
    except ValueError:
        return False


def evaluate(answer: str, hits: list[dict]) -> dict:
    """对答案做幻觉检测。hits 为本次提供给模型的检索片段（含 text）"""
    text = (answer or "").strip()
    if not text:
        return {"checked": False, "score": 0.0, "level": "low", "warnings": ["空回答"]}

    ctx_text = "\n".join(h.get("text", "") for h in hits)
    provided = len(hits)

    # 1) 引用有效性：越界的 [片段N]
    cites = [int(x) for x in _CITE_RE.findall(text)]
    invalid_refs = sorted({c for c in cites if c < 1 or c > provided})

    # 2) 引用覆盖率：结论句中有多少标注了来源
    sentences = [s.strip() for s in _SENT_SPLIT.split(text)
                 if len(s.strip()) >= _MIN_SENT_LEN and not _TRIVIAL.search(s)]
    cited = [s for s in sentences if _CITE_RE.search(s)]
    cited_ratio = round(len(cited) / len(sentences), 3) if sentences else 1.0

    # 3) 数值一致性：答案中的数值必须能在引用片段里找到
    unsupported = sorted(n for n in (_numbers(text) - _numbers(ctx_text)) if _significant(n))

    warnings: list[str] = []
    if invalid_refs:
        warnings.append(f"引用了不存在的片段编号：{invalid_refs}")
    if unsupported:
        warnings.append("以下数值未在引用资料中找到依据：" + "、".join(unsupported[:5]))
    if sentences and cited_ratio < 0.5:
        warnings.append(f"仅 {round(cited_ratio * 100)}% 的结论句标注了引用来源")

    score = 1.0
    score -= min(0.4, len(unsupported) * 0.12)
    score -= 0.35 if invalid_refs else 0.0
    if sentences and cited_ratio < 0.6:
        score -= min(0.3, (0.6 - cited_ratio) * 0.75)
    score = round(max(0.0, score), 3)

    low_th = float(getattr(settings, "RAG_FAITHFUL_MIN", 0.6) or 0.6)
    level = "high" if score >= 0.85 else ("medium" if score >= low_th else "low")

    return {
        "checked": True,
        "score": score,
        "level": level,
        "cited_ratio": cited_ratio,
        "sentences": len(sentences),
        "citations": len(cites),
        "invalid_refs": invalid_refs,
        "unsupported_numbers": unsupported[:8],
        "warnings": warnings,
    }


LOW_TRUST_NOTE = ("\n\n> ⚠️ 本次回答部分结论未能在引用资料中找到直接依据，"
                  "已标记为低可信，请核对原文后再对外使用。")
