"""季節與節日：依今天的日期決定季節（影響自動模式／點單的飲品比例）與節日（季節限定飲品、狀態列小圖示）

節日的日期有三種寫法（FESTIVALS 的開始、結束欄位）：
- 國曆固定日期：開始、結束都是 (月, 日)；開始比結束晚的（新年 12/30–1/2）是跨年的期間。
- 照規則推算：開始是規則名稱（RULES：母親節＝5 月第二個星期日、感恩節＝11 月第四個星期四、復活節＝計算公式），
  結束是 (往前幾天, 往後幾天)，期間是那一天前後幾天。
- 農曆：春節用 LUNAR_NEW_YEAR 對照表（正月初一的國曆日期），表外的年份就不過這個節日。
期間重疊時 PRIORITY 裡的節日優先（春節蓋過情人節、兒童節蓋過復活節），其他節日不會互相重疊（tests/test_festivals.py 逐日檢查）。

測試時可以用環境變數 CAFE_DESK_DATE=2026-12-20 指定日期。
"""
import datetime
import os

# key：(名稱, 季節限定飲品, 狀態列圖示, 開始, 結束)；開始與結束的寫法見上面
FESTIVALS = {
    "newyear": ("新年", "maple_latte", "firework", (12, 30), (1, 2)),
    "spring_festival": ("春節", "longan_latte", "lantern", "lunar_new_year", (2, 5)),      # 小年夜到初五
    "valentine": ("情人節", "rose_latte", "heart", (2, 7), (2, 14)),
    "white_day": ("白色情人節", "white_mocha", "white_heart", (3, 7), (3, 14)),
    "easter": ("復活節", "carrot_cake_latte", "egg", "easter", (6, 1)),                   # 復活節前一週到隔天
    "children": ("兒童節", "strawberry_milk", "balloon", (4, 1), (4, 4)),
    "mother": ("母親節", "lavender_latte", "carnation", "mother", (6, 0)),               # 母親節那一週（週一到週日）
    "father": ("父親節", "salted_caramel_latte", "tie", (8, 6), (8, 8)),
    "coffee_day": ("國際咖啡日", "honey_cinnamon_latte", "bean", (9, 25), (10, 1)),
    "halloween": ("萬聖節", "pumpkin_latte", "pumpkin", (10, 15), (10, 31)),
    "thanksgiving": ("感恩節", "apple_cinnamon_latte", "leaf", "thanksgiving", (3, 3)),
    "christmas": ("聖誕節", "gingerbread_latte", "tree", (12, 10), (12, 26)),
}
PRIORITY = ("spring_festival", "children")          # 期間重疊時優先的節日
# 不固定日期的節日在說明頁寫的規則（繁中原文，顯示時才 T()）
RULE_NOTE = {"lunar_new_year": "農曆小年夜到初五", "easter": "復活節前一週到隔天", "mother": "5 月第二個星期日那一週",
             "thanksgiving": "11 月第四個星期四前後三天"}

# 春節（正月初一）的國曆日期，2024–2050；每年 1/21–2/20 之間，相鄰兩年差 354／355 或 383／384 天（測試檢查）
LUNAR_NEW_YEAR = {
    2024: (2, 10), 2025: (1, 29), 2026: (2, 17), 2027: (2, 6), 2028: (1, 26), 2029: (2, 13), 2030: (2, 3),
    2031: (1, 23), 2032: (2, 11), 2033: (1, 31), 2034: (2, 19), 2035: (2, 8), 2036: (1, 28), 2037: (2, 15),
    2038: (2, 4), 2039: (1, 24), 2040: (2, 12), 2041: (2, 1), 2042: (1, 22), 2043: (2, 10), 2044: (1, 30),
    2045: (2, 17), 2046: (2, 6), 2047: (1, 26), 2048: (2, 14), 2049: (2, 2), 2050: (1, 23),
}


def nth_weekday(year, month, weekday, n):
    """某年某月第 n 個星期幾（weekday：星期一＝0 … 星期日＝6）"""
    d = datetime.date(year, month, 1)
    return d + datetime.timedelta(days=(weekday - d.weekday()) % 7 + 7 * (n - 1))


def easter(year):
    """復活節（西方教會）：匿名格里曆演算法"""
    a, b, c = year % 19, year // 100, year % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    m = (32 + 2 * e + 2 * i - h - k) % 7
    n = (a + 11 * h + 22 * m) // 451
    month = (h + m - 7 * n + 114) // 31
    return datetime.date(year, month, (h + m - 7 * n + 114) % 31 + 1)


def lunar_new_year(year):
    md = LUNAR_NEW_YEAR.get(year)
    return datetime.date(year, *md) if md else None


RULES = {"mother": lambda y: nth_weekday(y, 5, 6, 2), "thanksgiving": lambda y: nth_weekday(y, 11, 3, 4),
         "easter": easter, "lunar_new_year": lunar_new_year}


def spans(key, year):
    """這個節日在 year 年裡的期間 [(開始日, 結束日)]（跨年的固定日期拆成年初、年底兩段；對照表外的年份是空的）"""
    _, _, _, start, end = FESTIVALS[key]
    if isinstance(start, str):
        day = RULES[start](year)
        if day is None:
            return []
        return [(day - datetime.timedelta(days=end[0]), day + datetime.timedelta(days=end[1]))]
    if start <= end:
        return [(datetime.date(year, *start), datetime.date(year, *end))]
    return [(datetime.date(year, 1, 1), datetime.date(year, *end)), (datetime.date(year, *start), datetime.date(year, 12, 31))]


def festivals_on(d):
    """這一天在期間內的所有節日（沒處理重疊；一般用 festival()）"""
    return [k for k in FESTIVALS if any(a <= d <= b for a, b in spans(k, d.year))]


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
    """今天的節日 key（沒有就回傳 None）；重疊時 PRIORITY 的優先"""
    hits = festivals_on(d or today())
    return next((k for k in PRIORITY if k in hits), hits[0] if hits else None)


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
