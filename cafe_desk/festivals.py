"""季節與節日：依今天的日期決定季節（影響自動模式／點單的飲品比例）與節日（季節限定飲品、狀態列小圖示）

只用國曆固定日期的節日（情人節、萬聖節、聖誕節），不需要農曆對照表，哪一年都適用。

測試時可以用環境變數 CAFE_DESK_DATE=2026-12-20 指定日期。
"""
import datetime
import os

# key：(名稱, 季節限定飲品, 狀態列圖示, 開始 (月, 日), 結束 (月, 日))
FESTIVALS = {
    "valentine": ("情人節", "rose_latte", "heart", (2, 7), (2, 14)),
    "halloween": ("萬聖節", "pumpkin_latte", "pumpkin", (10, 15), (10, 31)),
    "christmas": ("聖誕節", "gingerbread_latte", "tree", (12, 10), (12, 26)),
}


def today():
    s = os.environ.get("CAFE_DESK_DATE")
    if s:
        try:
            return datetime.date.fromisoformat(s)
        except ValueError:
            pass
    return datetime.date.today()


def season(d=None):
    m = (d or today()).month
    if m in (3, 4, 5):
        return "spring"
    if m in (6, 7, 8):
        return "summer"
    if m in (9, 10, 11):
        return "autumn"
    return "winter"


def festival(d=None):
    """今天的節日 key（沒有就回傳 None）"""
    d = d or today()
    for key, (_, _, _, start, end) in FESTIVALS.items():
        if datetime.date(d.year, *start) <= d <= datetime.date(d.year, *end):
            return key
    return None


def festival_drink(d=None):
    f = festival(d)
    return FESTIVALS[f][1] if f else None


def adjust_weights(weights, drinks, d=None):
    """依季節與節日調整隨機飲品的權重：夏天冰飲多、冬天熱飲多；節日飲品加入並提高比例；
    不是當季的節日飲品權重為 0"""
    d = d or today()
    s = season(d)
    fd = festival_drink(d)
    out = {}
    for k, w in weights.items():
        spec = drinks[k]
        if spec.get("festival") and k != fd:
            continue
        if s == "summer" and not spec["hot"]:
            w *= 2.0
        elif s == "winter" and spec["hot"]:
            w *= 1.4
        out[k] = w
    if fd:
        out[fd] = max(out.get(fd, 0.0), 0.18)
    return out
