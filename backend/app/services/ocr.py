"""OCR 适配器（对齐企业级 RAG 文档第二节：图片 / 扫描件解析）

全部为**可选依赖**，缺失时不影响其他格式解析，只对扫描件给出可操作的降级提示：
- pytesseract + Tesseract 可执行文件：图片 → 文本
- PyMuPDF(fitz)：把无文字层的 PDF 页面渲染成图片，再交给 OCR（扫描件 PDF）

status() 返回引擎可用性与安装指引，供诊断接口与前端提示使用。
"""
import shutil


def _has(module: str) -> bool:
    try:
        __import__(module)
        return True
    except Exception:
        return False


def engine_status() -> dict:
    """OCR 引擎可用性（tesseract 可执行文件 + pytesseract 两者齐备才可用）"""
    binary = shutil.which("tesseract")
    has_pt = _has("pytesseract")
    has_fitz = _has("fitz")
    ok = bool(binary and has_pt)
    hint = "" if ok else (
        "安装 OCR：pip install pytesseract pymupdf，并安装 Tesseract 可执行文件"
        "（Windows: winget install UB-Mannheim.TesseractOCR；Linux: apt install tesseract-ocr tesseract-ocr-chi-sim）"
    )
    return {
        "available": ok,
        "pytesseract": has_pt,
        "tesseract_binary": binary or "",
        "pymupdf": has_fitz,
        "lang": "chi_sim+eng",
        "hint": hint,
    }


def _configure(pytesseract) -> None:
    binary = shutil.which("tesseract")
    if binary:
        pytesseract.pytesseract.tesseract_cmd = binary


def image_to_text(path: str, lang: str = "chi_sim+eng") -> str:
    """图片 → 文本（未安装 OCR 时抛 RuntimeError，附安装指引）"""
    st = engine_status()
    if not st["available"]:
        raise RuntimeError(st["hint"])
    from PIL import Image
    import pytesseract

    _configure(pytesseract)
    with Image.open(path) as img:
        return pytesseract.image_to_string(img, lang=lang)


def pdf_scan_to_text(path: str, max_pages: int = 30, lang: str = "chi_sim+eng") -> list[tuple[str, int, str]]:
    """扫描件 PDF：逐页渲染为图片后 OCR，返回 [(文本, 页码, 章节)]"""
    st = engine_status()
    if not st["available"]:
        raise RuntimeError(st["hint"])
    if not st["pymupdf"]:
        raise RuntimeError("扫描件 PDF 需要 PyMuPDF 渲染页面：pip install pymupdf")

    import fitz
    import pytesseract
    from PIL import Image

    _configure(pytesseract)
    out: list[tuple[str, int, str]] = []
    with fitz.open(path) as doc:
        for i, page in enumerate(doc):
            if i >= max_pages:
                break
            pix = page.get_pixmap(dpi=200)
            img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            out.append((pytesseract.image_to_string(img, lang=lang), i + 1, f"第{i + 1}页(OCR)"))
    return out
