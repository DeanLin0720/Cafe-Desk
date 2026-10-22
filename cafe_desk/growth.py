"""成長：店鋪等級（累積營業額）、咖啡師熟練度（總杯數）、小費罐、打烊日報的資料

等級與熟練度都從紀錄資料庫驗證過的列算出來（Stats.data 的 revenue_total、total），不另外存：
改設定檔加不了錢，舊紀錄也會往回算。設定檔只記「上次通知到哪一級」與「上次看過哪天的日報」。
"""
from .util import clamp

# (累積營業額門檻, 店名)；索引 0 是 Lv.1
LEVELS = ((0, "路邊小攤"), (3000, "巷口咖啡"), (8000, "街角小店"), (15000, "社區咖啡館"), (25000, "人氣小店"),
          (40000, "排隊名店"), (60000, "城市咖啡館"), (90000, "咖啡名所"), (130000, "傳說咖啡館"),
          (180000, "夢想咖啡館"))
MAX_LEVEL = len(LEVELS)

# (總杯數門檻, 稱號, 手感誤差倍率)
RANKS = ((0, "新手", 1.0), (50, "熟手", 0.85), (200, "老手", 0.7), (600, "職人", 0.6), (1500, "大師", 0.5))

ARRIVAL_K = 0.12            # Lv.10 時來客間隔縮短 12%（客人多約 14%）
PATIENCE_K = 0.25           # Lv.10 時客人耐心多 25%
WORK_K = 0.2                # Lv.10 時營業中出杯快 20%（客人變多，咖啡師也要跟得上，不然只是多了等太久離開的人）
JAR_FULL = 500              # 小費罐：今日小費到這個金額算滿（超過時紙鈔從罐口露出來）


# 設備依店鋪等級解鎖：Lv.1 只有 DESK·01 與義式，之後每升一級多一樣
MACHINE_LEVEL = {"desk01": 1, "lever": 3, "compact": 5, "allinone": 7}
METHOD_LEVEL = {"espresso": 1, "pourover": 2, "moka": 4, "colddrip": 6, "siphon": 8}


# 飲品依咖啡師稱號解鎖（稱號索引：0 新手、1 熟手、2 老手、3 職人）；沒列的（濃縮、美式、熱拿鐵、沖煮台的飲品）一開始就有，
# 沖煮台的飲品另外看店鋪等級（METHOD_LEVEL）
DRINK_RANK = {"doppio": 1, "iced_americano": 1, "iced_latte": 1, "cappuccino": 1,
              "ristretto": 2, "lungo": 2, "flat_white": 2, "cortado": 2, "macchiato": 2,
              "mocha": 3, "caramel_macchiato": 3, "espresso_tonic": 3, "affogato": 3}
FESTIVAL_RANK = 1           # 節日限定飲品（加醬的拿鐵）


def drink_rank(key):
    """這杯飲品要哪個稱號才解鎖"""
    from .drinks import DRINKS
    return FESTIVAL_RANK if DRINKS[key].get("festival") else DRINK_RANK.get(key, 0)


def drinks_at_rank(rank):
    """剛好在這個稱號解鎖的飲品（不含節日限定）"""
    return [k for k, r in DRINK_RANK.items() if r == rank]


def machine_open(key, level):
    return level >= MACHINE_LEVEL.get(key, 1)


def method_open(method, level):
    return level >= METHOD_LEVEL.get(method, 1)


def unlocked_at(level):
    """剛好在這一級解鎖的 (種類, key)：種類是 machine／method"""
    return ([("machine", k) for k, lv in MACHINE_LEVEL.items() if lv == level]
            + [("method", k) for k, lv in METHOD_LEVEL.items() if lv == level])


def level_of(revenue):
    """累積營業額 → 等級（1–10）"""
    return sum(1 for need, _ in LEVELS if revenue >= need)


def level_name(level):
    return LEVELS[level - 1][1]


def level_progress(revenue):
    """(等級, 下一級門檻或 None, 到下一級的進度 0–1)"""
    lv = level_of(revenue)
    if lv >= MAX_LEVEL:
        return lv, None, 1.0
    lo, hi = LEVELS[lv - 1][0], LEVELS[lv][0]
    return lv, hi, clamp((revenue - lo) / (hi - lo), 0, 1)


def _t(level):
    return clamp((level - 1) / (MAX_LEVEL - 1), 0, 1)


def arrival_k(level):
    """來客間隔倍率：等級越高客人越多"""
    return 1 - ARRIVAL_K * _t(level)


def patience_k(level):
    """客人耐心倍率：名店大家願意等"""
    return 1 + PATIENCE_K * _t(level)


def work_k(level):
    """營業中做飲品的速度倍率：店鋪升級＝動線與設備更順手"""
    return 1 + WORK_K * _t(level)


def queue_max(level, base=4):
    """排隊上限（含正在點的這位）：Lv.5 多 1 位、Lv.8 再多 1 位"""
    return base + (level >= 5) + (level >= 8)


def rank_of(cups):
    """總杯數 → 稱號索引（0＝新手）"""
    return sum(1 for need, _, _ in RANKS if cups >= need) - 1


# 手藝決定分數上限：85 分以上的部分依稱號打折（新手 40% … 大師 100%）。同一杯實力 97 分：新手 89.8、老手 93.4、大師 97
SCORE_FROM = 85.0
SCORE_K = (0.4, 0.55, 0.7, 0.85, 1.0)     # 跟 RANKS 一一對應


def skill_score(raw, rank):
    """咖啡師稱號壓縮高分；85 分以下不變"""
    if raw <= SCORE_FROM:
        return raw
    return SCORE_FROM + (raw - SCORE_FROM) * SCORE_K[rank]


def rank_name(rank):
    return RANKS[rank][1]


def rank_next(cups):
    """下一個稱號還差幾杯（已經是最高時 None）"""
    r = rank_of(cups)
    return None if r + 1 >= len(RANKS) else RANKS[r + 1][0] - cups


def skill(cups):
    """咖啡師手感誤差倍率（1＝新手；越小越穩）"""
    return RANKS[rank_of(cups)][2]


# ───────────── 打烊日報 ─────────────
def report(stats, day, achievement_days=None):
    """某一天的日報內容；那天沒有接過單時回傳 None。
    stats 是 Stats；day 是 ISO 日期字串。比較對象是更早、最近一個有接單的營業日"""
    days = stats.data["days"]
    d = days.get(day)
    if not d or not d.get("orders"):
        return None
    prev = None
    for key in sorted(days, reverse=True):
        if key < day and days[key].get("orders"):
            prev = days[key]
            break
    before = sum(v.get("revenue", 0) for k, v in days.items() if k < day)
    after = before + d["revenue"]
    ach = achievement_days if achievement_days is not None else stats.data["achievements"]
    return {
        "day": day,
        "served": d["orders"],
        "walkouts": d["walkouts"],
        "revenue": d["revenue"],
        "tips": d["tips"],
        "avg": d["score_sum"] / d["cups"] if d["cups"] else 0.0,
        "wait": d["wait_sum"] / d["waited"] if d["waited"] else None,
        "best": d.get("best"),
        "change": (d["revenue"] - prev["revenue"]) / prev["revenue"] if prev and prev["revenue"] else None,
        "level": level_of(after),
        "level_from": level_of(before),
        "progress": level_progress(after),
        "need": max(0, level_progress(after)[1] - after) if level_of(after) < MAX_LEVEL else 0,
        "achievements": [k for k, v in ach.items() if v == day],
    }


def last_business_day(stats, before):
    """before（ISO 日期，不含）之前最近一個有接單的日子；沒有時 None"""
    keys = [k for k, v in stats.data["days"].items() if k < before and v.get("orders")]
    return max(keys) if keys else None

