"""OCR 识别层：支持 Tesseract（pytesseract）与 PaddleOCR 两种引擎。

- 引擎按需懒加载，未安装时不影响程序启动；
- 可通过 config.ExtractOptions.ocr_engine 指定：auto / tesseract / paddle / off；
- get_engine_status() 供界面展示当前可用状态。
"""
from __future__ import annotations

import os
import shutil
from typing import Any, Dict, Optional

_TESSERACT_HINT = (
    "未检测到可用的 OCR 引擎，扫描件 / 图片将无法识别文字。\n"
    "方案 A（体积小）：安装 Tesseract-OCR 并勾选中文语言包，然后 pip install pytesseract pillow\n"
    "方案 B（中文更准）：pip install paddleocr paddlepaddle pillow"
)

_tesseract_checked = False
_tesseract_ok = False
_tesseract_error = ""
_paddle_engine: Any = None
_paddle_error = ""


def _find_tesseract() -> str:
    """查找 tesseract 可执行文件，支持常见的 Windows 安装路径。"""
    found = shutil.which("tesseract")
    if found:
        return found
    candidates = [
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe"),
        os.path.expandvars(r"%LOCALAPPDATA%\Tesseract-OCR\tesseract.exe"),
        "/usr/bin/tesseract",
        "/usr/local/bin/tesseract",
        "/opt/homebrew/bin/tesseract",
    ]
    for path in candidates:
        if path and os.path.isfile(path):
            return path
    return ""


def _ensure_tesseract() -> bool:
    global _tesseract_checked, _tesseract_ok, _tesseract_error
    if _tesseract_checked:
        return _tesseract_ok
    _tesseract_checked = True
    try:
        import pytesseract  # noqa: F401
    except Exception as exc:  # pragma: no cover - 取决于本机环境
        _tesseract_error = f"未安装 pytesseract（{exc}）"
        return False
    exe = _find_tesseract()
    if not exe:
        _tesseract_error = "未找到 tesseract 可执行文件"
        return False
    try:
        import pytesseract

        pytesseract.pytesseract.tesseract_cmd = exe
    except Exception as exc:  # pragma: no cover
        _tesseract_error = str(exc)
        return False
    _tesseract_ok = True
    return True


def _get_paddle() -> Any:
    global _paddle_engine, _paddle_error
    if _paddle_engine is not None:
        return _paddle_engine
    try:
        from paddleocr import PaddleOCR  # type: ignore
    except Exception as exc:  # pragma: no cover
        _paddle_error = f"未安装 paddleocr（{exc}）"
        return None
    try:
        _paddle_engine = PaddleOCR(use_angle_cls=True, lang="ch", show_log=False)
    except TypeError:
        try:
            _paddle_engine = PaddleOCR(lang="ch")
        except Exception as exc:  # pragma: no cover
            _paddle_error = str(exc)
            return None
    except Exception as exc:  # pragma: no cover
        _paddle_error = str(exc)
        return None
    return _paddle_engine


def get_engine_status() -> Dict[str, Dict[str, Any]]:
    """返回各引擎可用情况，供界面显示。"""
    tesseract_ok = _ensure_tesseract()
    paddle_ok = False
    paddle_note = _paddle_error or "未安装 paddleocr"
    try:
        import paddleocr  # noqa: F401

        paddle_ok = True
        paddle_note = "已安装（首次调用会下载模型）"
    except Exception:
        paddle_ok = False
    return {
        "tesseract": {"available": tesseract_ok, "note": "可用" if tesseract_ok else _tesseract_error},
        "paddle": {"available": paddle_ok, "note": paddle_note},
    }


def status_summary() -> str:
    status = get_engine_status()
    if status["tesseract"]["available"]:
        return "OCR：Tesseract 可用"
    if status["paddle"]["available"]:
        return "OCR：PaddleOCR 可用"
    return "OCR：未安装（扫描件不可识别）"


def ocr_hint() -> str:
    return _TESSERACT_HINT


def is_available(engine: str = "auto") -> bool:
    if engine == "off":
        return False
    status = get_engine_status()
    if engine == "tesseract":
        return status["tesseract"]["available"]
    if engine == "paddle":
        return status["paddle"]["available"]
    return status["tesseract"]["available"] or status["paddle"]["available"]


def ocr_image(image: Any, engine: str = "auto", lang: str = "chi_sim+eng") -> str:
    """对 PIL.Image 做 OCR，返回文本。失败时抛出 RuntimeError。"""
    if engine == "off":
        raise RuntimeError("OCR 已在设置中关闭")

    order = [engine] if engine in ("tesseract", "paddle") else ["tesseract", "paddle"]
    errors = []
    for name in order:
        if name == "tesseract" and _ensure_tesseract():
            try:
                import pytesseract

                return pytesseract.image_to_string(image, lang=lang)
            except Exception as exc:
                # 语言包缺失时退回默认语言
                try:
                    import pytesseract

                    return pytesseract.image_to_string(image)
                except Exception as exc2:
                    errors.append(f"Tesseract 失败：{exc2 or exc}")
        elif name == "paddle":
            paddle = _get_paddle()
            if paddle is not None:
                try:
                    import numpy as np

                    result = paddle.ocr(np.array(image), cls=True)
                    return _paddle_result_to_text(result)
                except Exception as exc:
                    errors.append(f"PaddleOCR 失败：{exc}")
    raise RuntimeError("；".join(errors) or _TESSERACT_HINT)


def _paddle_result_to_text(result: Any) -> str:
    lines = []
    if not result:
        return ""
    page = result[0] if isinstance(result, list) and result and isinstance(result[0], list) else result
    for item in page or []:
        try:
            if isinstance(item, (list, tuple)) and len(item) >= 2 and isinstance(item[1], (list, tuple)):
                lines.append(str(item[1][0]))
            elif isinstance(item, dict):
                lines.append(str(item.get("text", "")))
        except Exception:
            continue
    return "\n".join(line for line in lines if line)
