"""发票信息解析核心：从任意文本中抽取发票号码与金额等字段。

设计原则：
1. 先按"标签锚定"精确查找（发票号码 / 价税合计 / 小写 …），命中率最高；
2. 再按格式兜底（20 位或 8 位纯数字、带 ¥ 的金额）；
3. 每个字段记录命中的位置，供界面高亮提示；
4. 解析结果附带置信度与警告，方便人工复核。

本模块不依赖 Qt。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import config
from core.models import InvoiceRecord
from core.textutil import compact, normalize, parse_cn_amount, to_float

Span = Tuple[int, int]

# --------------------------------------------------------------------------
# 正则集合
# --------------------------------------------------------------------------
_MONEY = r"[¥￥]?\s*(\d{1,3}(?:,\d{3})+(?:\.\d{1,2})?|\d+(?:\.\d{1,2})?)"

# 发票号码标签：容忍 OCR 常见混淆（号→亏/呺/号，码→马/玛）
# 注意：这里也包含"票号"，但"电子客票号"会由后顾断言排除，
# 因此提取时按"发票号码标签优先 / 电子客票号兜底"的顺序处理（见 extract_number）。
NUM_LABEL = (
    r"发\s*票\s*[号虧呺亏]\s*[码馬玛马]?"
    r"|发票号码"
    r"|(?<!客)票号"
    r"|发\s*票\s*N\s*[oO0]"
    r"|Invoice\s*No\.?"
)
NUM_VALUE = r"[:：]?\s*(?:No\.?\s*)?([0-9]{6,24})"
NUM_LABEL_RE = re.compile(rf"(?:{NUM_LABEL})\s*{NUM_VALUE}", re.I)
NUM_LINE_RE = re.compile(r"(?:No\.?|N0\.?)\s*[:：]?\s*([0-9]{6,24})", re.I)
NUM_20_RE = re.compile(r"(?<!\d)(\d{20})(?!\d)")
NUM_8_RE = re.compile(r"(?<!\d)(\d{8})(?!\d)")

CODE_LABEL = r"发\s*票\s*代\s*[码馬玛]"
CODE_LABEL_RE = re.compile(rf"{CODE_LABEL}\s*[:：]?\s*([0-9]{{10,14}})")
CODE_BARE_RE = re.compile(r"(?<!\d)(\d{12})(?!\d)")

DATE_RE = re.compile(r"(?:开\s*票\s*日\s*期|日\s*期)\s*[:：]?\s*(\d{4}\s*[-/年.]\s*\d{1,2}\s*[-/月.]\s*\d{1,2})")
DATE_FORMATS = (
    re.compile(r"(\d{4})\s*[-/.年]\s*(\d{1,2})\s*[-/.月]\s*(\d{1,2})"),
)

SELLER_SECTION = r"销\s*售\s*方(?:\s*信\s*息)?|销\s*方"
BUYER_SECTION = r"购\s*买\s*方(?:\s*信\s*息)?|购\s*方|购\s*货\s*方|\b客\s*户"
NAME_AFTER = r"名\s*称"
NAME_RE = re.compile(rf"{NAME_AFTER}\s*[:：]?\s*([^\s:：][^\n]{{1,60}})")
NAME_LOOSE_RE = re.compile(rf"称\s*[:：]\s*([^\s:：][^\n]{{1,60}})")

TOTAL_LABEL = r"(?:价\s*税\s*合\s*计|合\s*计\s*金\s*额|应\s*付\s*(?:金额|合计)|总\s*金\s*额|价\s*税\s*合\s*计\s*\(?\s*小\s*写\s*\)?)"
TOTAL_LABEL_RE = re.compile(rf"{TOTAL_LABEL}\s*(?:\(?\s*小写\s*\)?)?\s*[:：]?\s*{_MONEY}")
AMOUNT_LABEL_RE = re.compile(rf"(?:金\s*额|不\s*含\s*税\s*金\s*额|合\s*计\s*金\s*额)\s*[:：]?\s*{_MONEY}")
TAX_LABEL_RE = re.compile(rf"(?:税\s*额|税\s*金)\s*[:：]?\s*{_MONEY}")
AMOUNT_TAX_RE = re.compile(rf"(?:金\s*额)\s*[:：]?\s*{_MONEY}\s*(?:税\s*额|税\s*金)\s*[:：]?\s*{_MONEY}")
XIAOXIE_RE = re.compile(rf"小\s*写\s*\)?\s*[:：]?\s*{_MONEY}")
ANY_MONEY_RE = re.compile(_MONEY)

CN_AMOUNT_RE = re.compile(r"[零壹贰叁肆伍陆柒捌玖拾佰仟万亿]{1,12}(?:元|圆|块)[零壹贰叁肆伍陆柒捌玖角分整正]{0,6}")

# 不是号码的字段：出现这些词附近就不要误抓
CODE_HINT = re.compile(r"代\s*码|code", re.I)


@dataclass
class ParseContext:
    """一次解析的中间状态。"""

    text: str = ""
    compact_text: str = ""
    page: str = ""
    source: str = ""
    source_path: str = ""
    warnings: List[str] = field(default_factory=list)
    highlights: List[Dict[str, Any]] = field(default_factory=list)


# --------------------------------------------------------------------------
# 工具
# --------------------------------------------------------------------------
def _add_highlight(ctx: ParseContext, field_name: str, span: Span, label: str) -> None:
    if span and span[0] >= 0:
        ctx.highlights.append({"field": field_name, "start": span[0], "end": span[1], "label": label})


def _search_window(text: str, span: Span, before: int = 80, after: int = 220) -> str:
    if not span or span[0] < 0:
        return ""
    start = max(0, span[0] - before)
    end = min(len(text), span[1] + after)
    return text[start:end]


def _money_in(text: str) -> Optional[float]:
    match = ANY_MONEY_RE.search(text or "")
    return to_float(match.group(1)) if match else None


def _first_group(regex: re.Pattern, text: str) -> Optional[Tuple[str, Span]]:
    match = regex.search(text or "")
    if not match:
        return None
    group = 1
    return match.group(group), match.span(group)


def _label_near(text: str, label_re: str, window: int = 120) -> bool:
    """判断标签是否出现在可接受的窗口内（用于防误判）。"""
    return bool(re.search(label_re, text or ""))


# --------------------------------------------------------------------------
# 各字段抽取
# --------------------------------------------------------------------------
def extract_number(ctx: ParseContext) -> Tuple[str, float]:
    text = ctx.text

    # 1) "发票号码 / 票号 / No." 标签锚定（最高优先级）
    match = NUM_LABEL_RE.search(text)
    if match:
        number = match.group(match.lastindex or 1)
        number = re.sub(r"\D", "", number)
        _add_highlight(ctx, "number", match.span(match.lastindex or 1), "发票号码")
        return number, 0.98

    # 2) 铁路电子客票：只有"电子客票号"时用它当票据唯一标识（无独立发票号码）
    eticket = ETICKET_RE.search(text)
    if eticket and not re.search(NUM_LABEL, text):
        _add_highlight(ctx, "number", eticket.span(1), "电子客票号")
        return eticket.group(1), 0.85

    # 2) 裸 20 位数字（数电票），但排除"电子客票号"里的数字
    eticket_spans = [m.span(1) for m in ETICKET_RE.finditer(text)]
    twentys = [
        m
        for m in NUM_20_RE.finditer(text)
        if not CODE_HINT.search(_search_window(text, m.span(), 12, 12))
        and not any(a <= m.start() and m.end() <= b for a, b in eticket_spans)
    ]
    if len(twentys) == 1:
        match = twentys[0]
        _add_highlight(ctx, "number", match.span(1), "20 位号码")
        return match.group(1), 0.85

    match = NUM_LINE_RE.search(text)
    if match:
        _add_highlight(ctx, "number", match.span(1), "No.")
        return re.sub(r"\D", "", match.group(1)), 0.8

    eights = [m for m in NUM_8_RE.finditer(text) if not CODE_HINT.search(_search_window(text, m.span(), 12, 12))]
    if len(eights) == 1:
        match = eights[0]
        _add_highlight(ctx, "number", match.span(1), "8 位号码")
        return match.group(1), 0.6

    if twentys:
        match = twentys[0]
        _add_highlight(ctx, "number", match.span(1), "20 位号码")
        return match.group(1), 0.6

    return "", 0.0


def extract_code(ctx: ParseContext) -> Tuple[str, float]:
    match = CODE_LABEL_RE.search(ctx.text)
    if match:
        _add_highlight(ctx, "code", match.span(1), "发票代码")
        return match.group(1), 0.95
    match = CODE_BARE_RE.search(ctx.text)
    if match:
        context = _search_window(ctx.text, match.span(1), 30, 30)
        if re.search(r"代\s*码", context):
            _add_highlight(ctx, "code", match.span(1), "12 位代码")
            return match.group(1), 0.7
    return "", 0.0


def extract_date(ctx: ParseContext) -> Tuple[str, float]:
    match = DATE_RE.search(ctx.text)
    if not match:
        return "", 0.0
    raw = match.group(1)
    parsed = None
    for regex in DATE_FORMATS:
        parsed = regex.match(raw.replace(" ", ""))
        if parsed:
            break
    if not parsed:
        return raw.strip(), 0.5
    year, month, day = (int(x) for x in parsed.groups())
    _add_highlight(ctx, "date", match.span(1), "开票日期")
    return f"{year:04d}-{month:02d}-{day:02d}", 0.9


def _extract_party(
    ctx: ParseContext, section_re: str, other_re: str, strict: bool = False
) -> Tuple[str, float]:
    text = ctx.text
    match = re.search(section_re, text)
    if match:
        window = text[match.end(): match.end() + 400]
        window_end = text.find("\n", match.end())
        # 优先取"名称：xxx"
        name_match = NAME_RE.search(window)
        if name_match:
            return _clean_name(name_match.group(1)), 0.85
        loose = NAME_LOOSE_RE.search(window)
        if loose:
            return _clean_name(loose.group(1)), 0.7
        if window_end > 0:
            return _clean_name(text[window_end + 1: window_end + 60]), 0.4

    if strict:
        # 调用方明确知道"必须有该字段标签"时，不做"取第一个名称"的兜底
        return "", 0.0

    names = list(NAME_RE.finditer(text))
    if names:
        name = names[0] if not re.search(other_re, text[: names[0].start()]) else names[-1]
        return _clean_name(name.group(1)), 0.35
    return "", 0.0


def _clean_name(value: str) -> str:
    value = re.split(r"\s{2,}|\t|\|", value or "")[0]
    value = re.sub(r"^[：:\s]+", "", value)
    value = re.sub(r"(纳税人识别号|税号|统一社会信用代码|地址|电话|开户行|账号).*$", "", value)
    value = value.strip(" :：-—·")
    return value.strip()


def extract_seller(ctx: ParseContext) -> Tuple[str, float]:
    # 铁路电子客票上没有"销售方"一栏，不要用购买方兜底
    strict = is_railway_invoice(ctx.text) and not re.search(SELLER_SECTION, ctx.text)
    return _extract_party(ctx, SELLER_SECTION, BUYER_SECTION, strict=strict)


def extract_eticket(ctx: ParseContext) -> Tuple[str, float]:
    """铁路电子客票的"电子客票号"（用于溯源，不属于发票号码）。"""
    match = ETICKET_RE.search(ctx.text)
    if match:
        _add_highlight(ctx, "note", match.span(1), "电子客票号")
        return match.group(1), 0.9
    return "", 0.0


def is_railway_invoice(text: str) -> bool:
    """判断是否为铁路电子客票（字段规则与普通发票不同）。"""
    return bool(
        re.search(r"铁路电子客票", text or "")
        or re.search(r"中国铁路", text or "")
        or re.search(r"电子客票号", text or "")
        or re.search(r"买票请到\s*12306", text or "")
        or re.search(r"发货请到\s*95306", text or "")
    )


def extract_buyer(ctx: ParseContext) -> Tuple[str, float]:
    match = re.search(BUYER_SECTION, ctx.text)
    if match:
        window = ctx.text[match.end(): match.end() + 400]
        name_match = NAME_RE.search(window)
        if name_match:
            return _clean_name(name_match.group(1)), 0.85
        loose = NAME_LOOSE_RE.search(window)
        if loose:
            return _clean_name(loose.group(1)), 0.7
    names = list(NAME_RE.finditer(ctx.text))
    if len(names) >= 2:
        return _clean_name(names[1].group(1)), 0.5
    return "", 0.0


SUMMARY_LINE_KEYWORD = re.compile(r"合\s*计|价\s*税\s*合\s*计|小\s*写|总\s*计")
SUMMARY_LABEL_RE = re.compile(rf"{TOTAL_LABEL}\s*(?:\(?\s*小写\s*\)?)?\s*[:：]?\s*{_MONEY}")
LINE_AMOUNT_TAX_RE = re.compile(rf"(?:金\s*额)\s*[:：]?\s*{_MONEY}\s*(?:\S{{0,6}}\s*)?(?:税\s*额|税\s*金)\s*[:：]?\s*{_MONEY}")
LINE_AMOUNT_RE = re.compile(rf"(?:金\s*额)\s*[:：]?\s*{_MONEY}")
LINE_TAX_RE = re.compile(rf"(?:税\s*额|税\s*金)\s*[:：]?\s*{_MONEY}")
MONEY_WITH_SYMBOL_RE = re.compile(rf"[¥￥]\s*{_MONEY}")
# 铁路电子客票：电子客票号 / 票价（金额可能与标签隔了几个字段，需要窗口内搜索）
ETICKET_RE = re.compile(r"电\s*子\s*客\s*票\s*号\s*[:：]?\s*([0-9]{15,30})")
TICKET_PRICE_RE = re.compile(r"票\s*价")
TICKET_PRICE_VALUE_RE = re.compile(rf"票\s*价\s*[:：]?\s*{_MONEY}")
CN_AMOUNT_LABEL_RE = re.compile(
    rf"(?:价\s*税\s*合\s*计|合\s*计)\s*(?:\(?\s*大\s*写\s*\)?)?\s*[:：]?\s*({CN_AMOUNT_RE.pattern})"
)


def _line_spans(text: str) -> List[Tuple[str, int]]:
    """返回 [(行文本, 行起始偏移)]。"""
    spans: List[Tuple[str, int]] = []
    offset = 0
    for line in (text or "").split("\n"):
        spans.append((line, offset))
        offset += len(line) + 1
    return spans


def _find_summary_line(text: str) -> Optional[Tuple[str, int]]:
    """找最合适的"合计"行：优先同时含"金额"和"税额"的行，最后出现的优先。"""
    best: Optional[Tuple[str, int]] = None
    best_pair = False
    for line, offset in _line_spans(text):
        if not SUMMARY_LINE_KEYWORD.search(line):
            continue
        has_pair = bool(LINE_AMOUNT_TAX_RE.search(line))
        if has_pair and not best_pair:
            best, best_pair = (line, offset), True
        elif best is None and (LINE_AMOUNT_RE.search(line) or MONEY_WITH_SYMBOL_RE.search(line)):
            best = (line, offset)
        elif best is not None and has_pair:
            best = (line, offset)
    return best


def extract_amounts(
    ctx: ParseContext, options: Optional[config.ExtractOptions] = None
) -> Tuple[Optional[float], Optional[float], Optional[float], float]:
    """抽取 (不含税金额, 税额, 价税合计, 置信度)。

    顺序很关键：发票明细行也含"金额/税额"字样，因此优先看"合计行"，
    再看标签锚定，最后才用兜底推断。
    """
    options = options or config.ExtractOptions()
    text = ctx.text
    amount = tax = total = None
    score = 0.0

    # 1) 合计行：同一行含"金额 xxx 税额 xxx"
    summary = _find_summary_line(text)
    if summary is not None:
        line, offset = summary
        pair = LINE_AMOUNT_TAX_RE.search(line)
        if pair:
            amount = to_float(pair.group(1))
            tax = to_float(pair.group(2))
            _add_highlight(ctx, "amount", (offset + pair.start(1), offset + pair.end(1)), "合计行金额")
            _add_highlight(ctx, "tax", (offset + pair.start(2), offset + pair.end(2)), "合计行税额")
            score = max(score, 0.92)
        else:
            match = LINE_AMOUNT_RE.search(line)
            if match:
                amount = to_float(match.group(1))
                _add_highlight(ctx, "amount", (offset + match.start(1), offset + match.end(1)), "合计行金额")
                score = max(score, 0.8)
            match = LINE_TAX_RE.search(line)
            if match:
                tax = to_float(match.group(1))
                _add_highlight(ctx, "tax", (offset + match.start(1), offset + match.end(1)), "合计行税额")
                score = max(score, 0.8)

    # 2) 价税合计（标签锚定，"价税合计（大写）… （小写）¥x" 也能命中）
    #    一页多票切分后，片段前部可能残留上一张票的合计，因此取最后一处匹配
    label_match = None
    for candidate in SUMMARY_LABEL_RE.finditer(text):
        label_match = candidate
    if label_match is not None:
        total = to_float(label_match.group(1))
        _add_highlight(ctx, "total", label_match.span(1), "价税合计")
        score = max(score, 0.95)

    # 3) 金额 / 税额成对出现（无合计行的简式发票）
    if amount is None or tax is None:
        pair = AMOUNT_TAX_RE.search(text)
        if pair:
            if amount is None:
                amount = to_float(pair.group(1))
                _add_highlight(ctx, "amount", pair.span(1), "金额")
            if tax is None:
                tax = to_float(pair.group(2))
                _add_highlight(ctx, "tax", pair.span(2), "税额")
            score = max(score, 0.85)

    # 4) 小写金额标签（同样取最后一处）
    if total is None:
        xiaoxie_match = None
        for candidate in XIAOXIE_RE.finditer(text):
            xiaoxie_match = candidate
        if xiaoxie_match is not None:
            total = to_float(xiaoxie_match.group(1))
            _add_highlight(ctx, "total", xiaoxie_match.span(1), "小写金额")
            score = max(score, 0.9)

    # 5) 标签与金额被 OCR 换行断开：在标签后的小窗口里找带 ¥ 的金额
    #    取窗口内最后一处"标签+金额"，避免切分时误抓上一张票的合计
    if total is None:
        label = None
        for candidate in re.finditer(TOTAL_LABEL, text):
            label = candidate
        window = _search_window(text, label.span(), 0, 160) if label else ""
        money = None
        for candidate in MONEY_WITH_SYMBOL_RE.finditer(window):
            money = candidate
        if label is not None and money is not None:
            total = to_float(money.group(1))
            _add_highlight(
                ctx, "total", (label.start() + money.start(1), label.start() + money.end(1)), "价税合计"
            )
            score = max(score, 0.8)

    # 6) 大写金额（汉字金额即价税合计）
    if total is None:
        label_match = CN_AMOUNT_LABEL_RE.search(text)
        if label_match:
            value = parse_cn_amount(label_match.group(1))
            span = label_match.span(1)
        else:
            plain_match = CN_AMOUNT_RE.search(text)
            value = parse_cn_amount(plain_match.group()) if plain_match else None
            span = plain_match.span() if plain_match else (-1, -1)
        if value:
            total = value
            _add_highlight(ctx, "total", span, "大写金额")
            score = max(score, 0.78)

    # 7) 单独出现的金额 / 税额（放最后，避免抓到明细行）
    if amount is None:
        match = AMOUNT_LABEL_RE.search(text)
        if match:
            amount = to_float(match.group(1))
            _add_highlight(ctx, "amount", match.span(1), "金额")
            score = max(score, 0.7)
    if tax is None:
        match = TAX_LABEL_RE.search(text)
        if match:
            tax = to_float(match.group(1))
            _add_highlight(ctx, "tax", match.span(1), "税额")
            score = max(score, 0.7)

    # 8) 合计行里的 ¥ 金额：既是价税合计，也可能是"金额 税额"两个数
    if summary is not None and (total is None or amount is None):
        line, offset = summary
        monies = [(to_float(m.group(1)), m) for m in MONEY_WITH_SYMBOL_RE.finditer(line)]
        monies = [(value, m) for value, m in monies if value is not None]
        if total is None and monies:
            value, match = monies[-1]
            total = value
            _add_highlight(ctx, "total", (offset + match.start(1), offset + match.end(1)), "合计金额")
            score = max(score, 0.85)
        if amount is None and len(monies) >= 2:
            value, match = monies[0]
            amount = value
            _add_highlight(ctx, "amount", (offset + match.start(1), offset + match.end(1)), "合计行金额")
            score = max(score, 0.85)

    # 8.5) 铁路电子客票：票价标签与金额常被其它字段隔开，取标签后窗口内最靠前的一处金额
    if total is None or amount is None:
        train_match = TICKET_PRICE_VALUE_RE.search(text)
        if train_match:
            price = to_float(train_match.group(1))
            span = train_match.span(1)
            source_label = "票价"
        else:
            label_match = TICKET_PRICE_RE.search(text)
            price = None
            span = (-1, -1)
            source_label = "票价(窗口)"
            if label_match:
                window = _search_window(text, label_match.span(), 0, 220)
                found = None
                for candidate in MONEY_WITH_SYMBOL_RE.finditer(window):
                    found = candidate
                    break
                if found is None:
                    for candidate in ANY_MONEY_RE.finditer(window):
                        found = candidate
                        break
                if found is not None:
                    price = to_float(found.group(1))
                    span = (label_match.start() + found.start(1), label_match.start() + found.end(1))
        if price is not None:
            if total is None:
                total = price
                _add_highlight(ctx, "total", span, source_label)
                score = max(score, 0.8)
            if amount is None and total is not None and tax is None:
                amount = price
                _add_highlight(ctx, "amount", span, source_label)
                score = max(score, 0.8)

    # 9) 兜底：文本里最大的金额当作价税合计
    if total is None and not options.strict_amount:
        candidates = [to_float(m.group(1)) for m in ANY_MONEY_RE.finditer(text)]
        candidates = [c for c in candidates if c is not None and c > 0]
        if candidates:
            total = max(candidates)
            score = max(score, 0.45)
            ctx.warnings.append("价税合计为兜底推断（取文本中最大金额），请人工复核")

    # 10) 一致性校验与互补推算
    if amount is not None and tax is not None and total is None:
        total = round(amount + tax, 2)
        score = max(score, 0.7)
        ctx.warnings.append("价税合计由 金额 + 税额 计算得出")
    if amount is not None and tax is not None and total is not None:
        if abs((amount + tax) - total) > config.AMOUNT_TOLERANCE:
            ctx.warnings.append(
                f"金额校验不符：{amount:.2f} + {tax:.2f} = {amount + tax:.2f}，与价税合计 {total:.2f} 不一致"
            )
            score = max(0.0, score - 0.15)
        else:
            score = min(1.0, score + 0.03)
    if amount is None and total is not None and tax is not None:
        amount = round(total - tax, 2)
    if tax is None and total is not None and amount is not None:
        tax = round(total - amount, 2)

    return amount, tax, total, round(score, 3)


# --------------------------------------------------------------------------
# 主入口
# --------------------------------------------------------------------------
def parse_invoice(
    text: str,
    *,
    source: str = "",
    source_path: str = "",
    page: str = "",
    options: Optional[config.ExtractOptions] = None,
    already_normalized: bool = False,
) -> InvoiceRecord:
    """从一段文本中解析出发票记录。"""
    normalized = (text or "") if already_normalized else normalize(text or "")
    ctx = ParseContext(
        text=normalized,
        compact_text=compact(normalized),
        page=str(page or ""),
        source=source,
        source_path=source_path,
    )

    number, s_number = extract_number(ctx)
    code, _s_code = extract_code(ctx)
    date, _s_date = extract_date(ctx)
    eticket, _s_eticket = extract_eticket(ctx)
    amount, tax, total, s_amount = extract_amounts(ctx, options)
    seller, _s_seller = extract_seller(ctx)
    buyer, _s_buyer = extract_buyer(ctx)
    is_railway = is_railway_invoice(normalized)

    confidence = round(0.6 * s_number + 0.4 * s_amount, 3)

    record = InvoiceRecord(
        number=number,
        code=code,
        date=date,
        amount=amount,
        tax=tax,
        total=total,
        seller=seller,
        buyer=buyer,
        page=str(page or ""),
        confidence=confidence,
        source=source,
        source_path=source_path,
        raw_text=normalized,
        highlights=ctx.highlights,
    )

    warnings = list(ctx.warnings)
    if not number:
        warnings.append("未识别到发票号码")
        confidence = max(0.0, confidence - 0.1)
    elif len(number) not in config.NUMBER_LENGTHS and not is_railway:
        warnings.append(f"发票号码长度为 {len(number)} 位，非常见的 {'/'.join(map(str, config.NUMBER_LENGTHS))} 位，请复核")
    if total is None and amount is None:
        warnings.append("未识别到任何金额")

    note_parts = list(warnings)
    if eticket:
        note_parts.append(f"电子客票号：{eticket}")

    record.warnings = warnings
    record.note = "；".join(note_parts)
    record.confidence = confidence
    return record


# 一页多票：以"发票号码"或"电子客票号"的出现次数切分
_NUM_ANCHOR = re.compile(rf"(?:{NUM_LABEL})")
_ETICKET_ANCHOR = re.compile(r"电\s*子\s*客\s*票\s*号")


def _find_anchors(text: str) -> List[Tuple[int, int]]:
    """返回所有分票锚点 [(起点, 终点)]，按位置排序并去掉重叠。

    规则（针对真实票据，避免同一张票被切成两条）：
    1. "发票号码:123…" 一定是新票的开始；
    2. "电子客票号:123…" 只有在它后面（同一份文件内）还跟着新的"发票号码"时才算新票，
       否则它只是当前这张铁路电子客票的溯源字段。
    """
    number_matches = list(NUM_LABEL_RE.finditer(text))
    spans: List[Tuple[int, int]] = [m.span() for m in number_matches]

    for match in ETICKET_RE.finditer(text):
        rest = text[match.end():]
        if NUM_LABEL_RE.search(rest) or _NUM_ANCHOR.search(rest):
            span = match.span()
            if not any(start <= span[0] < end for start, end in spans):
                spans.append(span)

    if not spans:
        # 只有"发票号码"字样但后面没跟数字时，退化为按标签位置切分
        spans = [m.span() for m in _NUM_ANCHOR.finditer(text)]

    spans.sort()
    merged: List[Tuple[int, int]] = []
    for start, end in spans:
        if merged and start < merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
            continue
        merged.append((start, end))
    return merged


def split_invoices(text: str, max_parts: int = 200, *, already_normalized: bool = False) -> List[Tuple[str, str]]:
    """把一份多票文本切成若干段，返回 [(序号, 片段文本)]。

    每段的起点落在锚点标签之前一点（保证不切入上一张票本体），
    终点是下一个锚点的起点。
    """
    normalized = (text or "") if already_normalized else normalize(text or "")
    anchors = _find_anchors(normalized)
    if len(anchors) <= 1:
        return [("1", normalized)]

    parts: List[Tuple[str, str]] = []
    for index in range(min(len(anchors), max_parts)):
        start_pos, _end_pos = anchors[index]
        previous_end = anchors[index - 1][1] if index > 0 else 0
        start = max(previous_end, max(0, start_pos - 260))
        end = anchors[index + 1][0] if index + 1 < len(anchors) else len(normalized)
        parts.append((str(index + 1), normalized[start:end]))
    return parts


def parse_text(
    text: str,
    *,
    source: str = "",
    source_path: str = "",
    options: Optional[config.ExtractOptions] = None,
    keep_empty: bool = False,
) -> List[InvoiceRecord]:
    """解析一份文本，返回 1~N 张发票记录。

    keep_empty=True 时，若完全没识别到有效字段，也会返回一行占位记录（便于人工校正）。
    """
    if not (text or "").strip():
        return []
    normalized = normalize(text)
    records: List[InvoiceRecord] = []
    for page_no, chunk in split_invoices(normalized, already_normalized=True):
        record = parse_invoice(
            chunk,
            source=source,
            source_path=source_path,
            page=page_no,
            options=options,
            already_normalized=True,
        )
        if record.is_empty:
            continue
        records.append(record)
    if not records and keep_empty:
        records.append(
            parse_invoice(
                normalized,
                source=source,
                source_path=source_path,
                page="1",
                options=options,
                already_normalized=True,
            )
        )
    return records
