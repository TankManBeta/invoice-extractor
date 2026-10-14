"""中文文本归一化与数字转换工具。"""
from __future__ import annotations

import re
from typing import Optional, Tuple

_FULL_TO_HALF = {ord(c) + 0xFEE0: ord(c) for c in "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"}
_FULL_TO_HALF.update({
    ord("（"): ord("("),
    ord("）"): ord(")"),
    ord("："): ord(":"),
    ord("，"): ord(","),
    ord("。"): ord("."),
    ord("；"): ord(";"),
    ord("％"): ord("%"),
    ord("－"): ord("-"),
    ord("＋"): ord("+"),
    ord("／"): ord("/"),
    ord("　"): ord(" "),
    ord("￥"): ord("¥"),
    ord("﹒"): ord("."),
})

_CURRENCY_RE = re.compile(r"(?:人民币|RMB|rmb|¥|￥|CNY)\s*")
_NUM_RE = re.compile(r"^-?\d{1,3}(?:,\d{3})+(?:\.\d+)?$|^-?\d+(?:\.\d+)?$")


def normalize(text: str) -> str:
    """全角转半角、统一符号、压缩空白。"""
    if not text:
        return ""
    text = text.translate(_FULL_TO_HALF)
    # 人民币符号可能以 ￥(全角 U+FFE5) / ¥(半角 U+00A5) / 元 等形式出现，统一成 ¥
    text = text.replace("\uffe5", "¥").replace("\u00a5", "¥").replace("\u5143", "元")
    text = text.replace("\u00a0", " ").replace("\u3000", " ")
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    return text.strip()


def compact(text: str) -> str:
    """去掉所有空白，用于正则匹配。"""
    return re.sub(r"\s+", "", text or "")


def to_float(value: str) -> Optional[float]:
    """把 '1,234.56' / '￥1234.5元' / '(123)' 转成 float。"""
    if value is None:
        return None
    s = _CURRENCY_RE.sub("", str(value))
    s = s.replace(",", "").replace("，", "").strip()
    s = re.sub(r"(元|圆|块|角|分|整|人民币)$", "", s)
    match = re.search(r"-?\d+(?:\.\d+)?", s)
    if not match:
        return None
    try:
        return round(float(match.group()), 2)
    except ValueError:
        return None


def first_number(text: str) -> Optional[float]:
    """在一段文本里找第一个像金额的数字。"""
    return to_float(text)


def looks_like_number(text: str) -> bool:
    return bool(_NUM_RE.match((text or "").strip()))


# --------------------------------------------------------------------------
# 中文大写金额
# --------------------------------------------------------------------------
_DIGITS = {"零": 0, "壹": 1, "贰": 2, "叁": 3, "肆": 4, "伍": 5, "陆": 6, "柒": 7, "捌": 8, "玖": 9,
           "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
_UNITS = {"拾": 10, "十": 10, "佰": 100, "百": 100, "仟": 1000, "千": 1000}
_CN_NUM = re.compile(r"[零壹贰叁肆伍陆柒捌玖一二两三四五六七八九十拾佰百仟千万亿]+")
_CN_AMOUNT = re.compile(r"[零壹贰叁肆伍陆柒捌玖拾佰仟万亿]{1,12}(?:元|圆|块)[零壹贰叁肆伍陆柒捌玖角分整正]{0,6}")
_CN_DECIMAL_WORDS = {
    "元": "元", "圆": "元", "块": "元", "角": "角", "分": "分",
    "零": "0", "壹": "1", "贰": "2", "叁": "3", "肆": "4", "伍": "5",
    "陆": "6", "柒": "7", "捌": "8", "玖": "9",
}
_WORD_ORDER = {"元": 0, "角": 1, "分": 2}


def parse_cn_amount(text: str) -> Optional[float]:
    """解析中文大写金额，例如 '壹佰贰拾叁元肆角伍分' -> 123.45"""
    if not text:
        return None
    source = normalize(text).replace(" ", "")
    source = source.replace("正", "整")
    if "元" not in source and "圆" not in source and "块" not in source:
        return None

    # 逐位映射："壹贰叁元肆角伍分" -> 123.45
    buf = []
    for ch in source:
        if ch in _CN_DECIMAL_WORDS:
            buf.append(_CN_DECIMAL_WORDS[ch])
        elif ch == "整":
            buf.append("整")
        else:
            buf.append(ch)
    stream = "".join(buf)

    # 传统写法："壹佰贰拾叁元肆角伍分" -> 先算整数部分
    if "拾" in source or "佰" in source or "仟" in source or "十" in source or "百" in source or "千" in source:
        int_text = re.split(r"[元圆块]", source)[0]
        int_value = _parse_cn_integer(int_text)
        if int_value is None:
            return None
        tail = source.split("元")[-1] if "元" in source else source.split("圆")[-1]
        tail = tail.replace("整", "")
        jiao = re.search(r"([零壹贰叁肆伍陆柒捌玖])\s*角", tail)
        fen = re.search(r"([零壹贰叁肆伍陆柒捌玖])\s*分", tail)
        value = float(int_value)
        if jiao:
            value += _DIGITS.get(jiao.group(1), 0) / 10.0
        if fen:
            value += _DIGITS.get(fen.group(1), 0) / 100.0
        return round(value, 2)

    # 逐位写法："123元45分"
    match = re.match(r"^(\d*)元(?:(\d)角)?(?:(\d)分)?", stream)
    if not match:
        return None
    yuan = int(match.group(1)) if match.group(1) else 0
    value = float(yuan)
    if match.group(2):
        value += int(match.group(2)) / 10.0
    if match.group(3):
        value += int(match.group(3)) / 100.0
    return round(value, 2)


def _parse_cn_integer(text: str) -> Optional[int]:
    """解析中文整数部分，例如 '壹佰贰拾叁' -> 123"""
    if not text:
        return None
    total = 0
    section = 0
    number = 0
    for ch in text:
        if ch in _DIGITS:
            number = _DIGITS[ch]
        elif ch in _UNITS:
            section += (number or 1) * _UNITS[ch]
            number = 0
        elif ch == "万":
            section = (section + number) * 10000
            total += section
            section = 0
            number = 0
        elif ch == "亿":
            total = (total + section + number) * 100000000
            section = 0
            number = 0
        else:
            continue
    return total + section + number


def to_cn_words(value: Optional[float]) -> str:
    """把 123.45 写成 '壹佰贰拾叁元肆角伍分'，用于校对。"""
    if value is None:
        return ""
    units = "仟佰拾亿仟佰拾万仟佰拾元角分"
    digits = "零壹贰叁肆伍陆柒捌玖"
    text = f"{value:.2f}".replace(".", "")
    if abs(value - round(value)) < 0.005:
        text = f"{int(round(value))}00"
    text = text.rjust(len(units), "0")[-len(units):]
    result = []
    zero_pending = False
    for idx, ch in enumerate(text):
        digit = int(ch)
        unit = units[idx]
        if digit == 0:
            if result and unit in ("元", "万", "亿"):
                result.append(unit)
            elif result:
                zero_pending = True
            continue
        if zero_pending:
            result.append("零")
            zero_pending = False
        result.append(digits[digit] + unit)
    out = "".join(result).rstrip("零")
    if out.endswith("元"):
        out += "整"
    return out


def find_chinese_amount(text: str) -> Tuple[Optional[float], str, Tuple[int, int]]:
    """在文本中查找大写金额，返回 (数值, 原文, 位置)。"""
    for match in _CN_AMOUNT.finditer(text or ""):
        value = parse_cn_amount(match.group())
        if value is not None:
            return value, match.group(), match.span()
    return None, "", (-1, -1)
