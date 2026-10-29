"""每日／每週挑戰：每天開店給三個小目標、每週兩個大目標，完成蓋章，集點換稱號

進度從紀錄資料庫算出來的每日統計（Stats.data["days"]）取得，只有營業模式的訂單杯會累計，不增加任何操作。
挑戰清單（哪天出哪幾個）產生後存在設定檔 `challenge_set`，當天不會因為升級或解鎖而改變；
完成記錄是有簽章的 events（kind＝challenge），所以蓋章數不能靠改設定檔增加。
"""
import datetime
import random

from .i18n import T, money

DAILY_N = 3
WEEKLY_N = 2
WEEKLY_STAMPS = 3            # 每日挑戰蓋一個章、每週挑戰蓋三個
STAMPS_PER_CARD = 10         # 一張集點卡的格數
# (集滿的章數, 稱號)
TITLES = ((10, "小試身手"), (30, "挑戰常客"), (60, "挑戰達人"), (120, "店長之星"))

# kind → (基本目標, 說明樣板)；目標依店鋪等級放大（見 scale）
DAILY = {
    "orders": (8, "今天做 {n} 杯訂單"),
    "hi": (3, "今天 {n} 杯訂單拿到 90 分以上"),
    "hi_drink": (2, "今天 {n} 杯{drink} 90 分以上"),
    "clean": (8, "零離開：今天做滿 {n} 杯訂單，而且沒有客人等太久離開"),
    "revenue": (1000, "今天營業額達到 {n}"),
    "large": (3, "今天為客人做 {n} 杯大杯"),
    "to_go": (4, "今天做 {n} 杯外帶"),
    "dine": (4, "今天做 {n} 杯內用"),
    "festival": (1, "今天做一杯季節限定飲品"),
}
WEEKLY = {
    "w_orders": (50, "這週做 {n} 杯訂單"),
    "w_hi": (15, "這週 {n} 杯訂單拿到 90 分以上"),
    "w_days": (4, "這週有 {n} 天開店營業"),
    "w_revenue": (6000, "這週營業額達到 {n}"),
}
FIXED = ("festival", "w_days")        # 目標不隨店鋪等級放大
HI_SCORE = 90


def scale(level):
    """目標倍率：Lv.1 0.7 → Lv.10 1.6（客人多、手藝好，目標也跟著高）"""
    return 0.6 + 0.1 * level


def goal_of(kind, level):
    base = (DAILY.get(kind) or WEEKLY[kind])[0]
    if kind in FIXED:
        return base
    n = base * scale(level)
    return max(100, int(round(n, -2))) if "revenue" in kind else max(1, int(round(n)))


def week_start(day):
    d = datetime.date.fromisoformat(day)
    return (d - datetime.timedelta(days=d.weekday())).isoformat()


def week_days(day):
    s = datetime.date.fromisoformat(week_start(day))
    return [(s + datetime.timedelta(days=i)).isoformat() for i in range(7)]


def daily_set(day, level, drinks, festival_drink=None):
    """某天的每日挑戰：以日期當種子；drinks 是目前能點的義式飲品（hi_drink 從裡面挑）"""
    rnd = random.Random(f"daily-{day}")
    kinds = [k for k in DAILY if (k != "festival" or festival_drink) and (k != "hi_drink" or drinks)]
    items = []
    for i, kind in enumerate(rnd.sample(kinds, min(DAILY_N, len(kinds)))):
        it = {"id": f"d:{day}:{i}", "kind": kind, "goal": goal_of(kind, level)}
        if kind == "hi_drink":
            it["drink"] = rnd.choice(sorted(drinks))
        items.append(it)
    return items


def weekly_set(day, level):
    start = week_start(day)
    rnd = random.Random(f"weekly-{start}")
    return [{"id": f"w:{start}:{i}", "kind": kind, "goal": goal_of(kind, level)}
            for i, kind in enumerate(rnd.sample(list(WEEKLY), WEEKLY_N))]


def progress(item, stats, day):
    """(目前進度, 目標, 失敗了嗎)：失敗只有「零離開」，今天已經有客人離開就做不成了"""
    days = stats.data["days"]
    kind, goal = item["kind"], item["goal"]
    d = days.get(day, {})
    if kind.startswith("w_"):
        ds = [days[k] for k in week_days(day) if k in days]
        value = {"w_orders": sum(x.get("orders", 0) for x in ds),
                 "w_hi": sum(sum(x.get("hi", {}).values()) for x in ds),
                 "w_days": sum(1 for x in ds if x.get("orders")),
                 "w_revenue": sum(x.get("revenue", 0) for x in ds)}[kind]
        return min(value, goal), goal, False
    if kind == "clean":
        failed = d.get("walkouts", 0) > 0
        return (0 if failed else min(d.get("orders", 0), goal)), goal, failed
    value = {"orders": d.get("orders", 0), "hi": sum(d.get("hi", {}).values()),
             "hi_drink": d.get("hi", {}).get(item.get("drink"), 0), "revenue": d.get("revenue", 0),
             "large": d.get("large", 0), "to_go": d.get("to_go", 0), "dine": d.get("dine", 0),
             "festival": d.get("festival", 0)}[kind]
    return min(value, goal), goal, False


def done(item, stats, day):
    value, goal, failed = progress(item, stats, day)
    return not failed and value >= goal


def text_of(item, drink_name=lambda k: k):
    """說明文字（顯示時才 T，切換語言立即生效）"""
    tpl = (DAILY.get(item["kind"]) or WEEKLY[item["kind"]])[1]
    n = money(item["goal"]) if "revenue" in item["kind"] else item["goal"]
    return T(tpl, n=n, drink=T(drink_name(item.get("drink"))) if item.get("drink") else "")


def stamps_of(done_ids):
    """已完成的挑戰 id（d:…／w:…）→ 章數"""
    return sum(WEEKLY_STAMPS if i.startswith("w:") else 1 for i in done_ids)


def title_index(stamps):
    """目前稱號的索引（還沒有時 -1）"""
    return sum(1 for need, _ in TITLES if stamps >= need) - 1


def next_title(stamps):
    """(下一個稱號, 還差幾個章)；已經最高時 None"""
    for need, name in TITLES:
        if stamps < need:
            return name, need - stamps
    return None


def card_fill(stamps):
    """(目前這張集點卡蓋了幾格, 已集滿幾張)"""
    return stamps % STAMPS_PER_CARD, stamps // STAMPS_PER_CARD
