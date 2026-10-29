"""熟客系統：幾位固定、有名字的客人（orders.CUSTOMERS），記得你做給他們的每一杯

不另外存資料：紀錄資料庫的每一杯訂單記著客人的名字（cups.customer），`Stats.data["customers"]` 從驗證過的列算出
每位客人的杯數、分數總和與點過的飲品，所以改設定檔變不出熟客、重新遊玩會一起清掉。
熟客等級看「累積杯數」與「平均分數」（兩個都要到）；之後做得不好平均掉下來，等級也會掉。
熟客會常回來、常點「老樣子」（最常點的飲品）、給更多小費、比較有耐心。
"""
import random

# (需要杯數, 需要平均分數, 稱號)；索引 0 是等級 1
LEVELS = ((3, 75.0, "熟面孔"), (8, 80.0, "熟客"), (15, 85.0, "老朋友"))
TIP_STEP = 0.25            # 每級小費多 25%
PATIENCE_STEP = 0.1        # 每級耐心多 10%
RETURN_P = 0.35            # 新客人是熟客（等級 1 以上）的機率，剩下的隨機挑
USUAL_P = 0.5              # 熟客點「老樣子」的機率
NOT_REGULAR = ("評鑑員",)  # 評鑑員不算客人名冊


def level_of(rec):
    """客人紀錄 {cups, score_sum, fav} → 熟客等級 0–3（沒有紀錄＝0）"""
    if not rec or not rec.get("cups"):
        return 0
    avg = rec["score_sum"] / rec["cups"]
    return sum(1 for need, score, _ in LEVELS if rec["cups"] >= need and avg >= score)


def level_name(level):
    return LEVELS[level - 1][2] if level else ""


def tip_k(level):
    return 1 + TIP_STEP * level


def patience_k(level):
    return 1 + PATIENCE_STEP * level


def favorite(rec):
    """最常點的飲品（同數量時取字母序在前的）；沒有時 None"""
    fav = (rec or {}).get("fav") or {}
    return min(fav, key=lambda k: (-fav[k], k)) if fav else None


def roster(customers):
    """熟客名冊：[(名字, 等級, 杯數, 平均分數, 最愛)]，等級高的在前（只列等級 1 以上）"""
    rows = [(n, level_of(r), r["cups"], r["score_sum"] / r["cups"], favorite(r)) for n, r in customers.items() if r.get("cups")]
    return sorted((x for x in rows if x[1] > 0), key=lambda x: (-x[1], -x[2], x[0]))


def pick_name(rnd, customers, pool, last_name=None):
    """下一位客人的名字：有熟客時 RETURN_P 的機率是熟客（等級越高越常來），否則從名單隨機挑（不連續同一位）"""
    regs = [(n, lv) for n, lv, *_ in roster(customers) if n != last_name and n in pool]
    if regs and rnd.random() < RETURN_P:
        return rnd.choices([n for n, _ in regs], weights=[lv for _, lv in regs])[0]
    return rnd.choice([n for n in pool if n != last_name])


def _top(counts, n=1):
    """次數最多的幾個 key（同次數時字母序在前）"""
    return sorted(counts, key=lambda k: (-counts[k], k))[:n]


def habits(rec):
    """客人的習慣（從每一杯統計）：{drinks: 最常點的兩種, size: 常點的杯型或 None, place: dine／to_go／None（偏好至少六成才算）,
    milk: 常用的奶（有加奶的飲品才有）, last: 最近一次來的日期, best: 他喝過最高的分數}"""
    rec = rec or {}
    dine, to_go = rec.get("dine", 0), rec.get("to_go", 0)
    place = None
    if dine + to_go >= 3:
        place = "dine" if dine >= 0.6 * (dine + to_go) else ("to_go" if to_go >= 0.6 * (dine + to_go) else None)
    size = _top(rec["size"])[0] if rec.get("size") else None
    milk = _top(rec["milk"])[0] if rec.get("milk") else None
    return {"drinks": _top(rec.get("fav", {}), 2), "size": size, "place": place, "milk": milk,
            "last": rec.get("last", ""), "best": rec.get("best", 0.0)}
