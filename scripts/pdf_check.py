"""PDF 解析回归测试：用真实票据验证文本层提取与字段解析。

用法（Windows PowerShell）：
    python scripts/pdf_check.py
默认读取 samples/pdf/*.pdf；没有样本时打印提示并跳过。
"""
from __future__ import annotations

import glob
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import config  # noqa: E402
from core.pdf import read_pdf_text  # noqa: E402
from core.reader import read_file  # noqa: E402

EXPECTED = {
    # 解析器会统一全角括号，因此期望值为半角
    "高铁发票1.pdf": {"number": "26329116804010371685", "total": 208.00, "buyer": "南栖仙策(南京)科技有限公司"},
    "高铁发票2.pdf": {"number": "26339132013001017271", "total": 208.00, "buyer": "南栖仙策(南京)科技有限公司"},
}


def main() -> int:
    files = sorted(glob.glob(os.path.join(ROOT, "samples", "pdf", "*.pdf")))
    if not files:
        print("samples/pdf 下没有 PDF 样本，跳过（把真实发票放进去即可启用本测试）")
        return 0

    failures = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        print(f"[{'PASS' if ok else 'FAIL'}] {name}{(' — ' + detail) if detail else ''}")
        if not ok:
            failures.append(name)

    for path in files:
        base = os.path.basename(path)
        expect = EXPECTED.get(base, {})

        text, engine, pages = read_pdf_text(path, config.ExtractOptions())
        check(f"{base} 文本层可读", bool(text.strip()), f"引擎 {engine}，{len(pages)} 页，{len(text)} 字")
        check(f"{base} 货币符号未丢失", "¥" in text, "文本中出现 ¥")

        result = read_file(path, config.ExtractOptions())
        check(f"{base} 状态正常", result.status in ("done", "ocr"), f"status={result.status} {result.error}")
        check(f"{base} 恰好 1 条记录", len(result.invoices) == 1, f"实际 {len(result.invoices)} 条")

        if result.invoices and expect:
            record = result.invoices[0]
            check(f"{base} 发票号码", record.number == expect["number"], f"{record.number!r}")
            check(f"{base} 价税合计", record.total == expect["total"], f"{record.total}")
            check(f"{base} 购买方", record.buyer == expect["buyer"], f"{record.buyer!r}")
            check(f"{base} 无待复核警告", not record.warnings, str(record.warnings))

    print(f"-- PDF 解析检查：{'全部通过' if not failures else '失败项 ' + str(failures)} --")
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
