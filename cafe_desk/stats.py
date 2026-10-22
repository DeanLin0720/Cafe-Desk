"""每日紀錄、成就、收集冊：每做完一杯記一筆，存在設定檔旁的 SQLite 資料庫 *_records.db

資料表
    cups          每一杯（時間、飲品、分數、機器、牛奶、豆子、拉花、訂單…）
    events        其他事件（清潔保養、營業模式客人等太久離開）
    achievements  成就解鎖日期
防竄改：每一列都有 HMAC 簽章，而且串成鏈（這一列的簽章包含上一列的簽章）。
    改了某一列 → 那一列簽章不符，統計時忽略；刪掉中間的列 → 下一列的鏈接不上，視為被動過。
    發現時紀錄視窗會顯示提醒。注意：金鑰在程式裡，懂程式的人仍然可以重算簽章，
    這是「防止隨手用 SQLite 工具改數字」而不是密碼學等級的保護。
統計（每天、收集冊、連續好杯…）都是讀檔時從驗證過的列重新計算，不另外存。
舊版的 *_stats.json：第一次啟動時匯入成就，然後改名成 .bak。
"""
import datetime
import hashlib
import hmac
import json
import os
import sqlite3

from . import paths
from .festivals import today
from .growth import level_of

_KEY = hashlib.sha256(b"cafe-desk/records/v1:" + b"\x63\x61\x66\x65").digest()

# (key, 名稱, 說明)；順序就是紀錄視窗的顯示順序
ACHIEVEMENTS = [
    ("first_cup", "第一杯", "為第一位客人做咖啡"),
    ("ten_cups", "上手了", "為客人做了 50 杯"),
    ("hundred_cups", "五百杯咖啡師", "為客人做了 500 杯"),
    ("cups_500", "兩千杯職人", "為客人做了 2000 杯"),
    ("busy_day", "忙碌的一天", "一天為客人做 40 杯"),
    ("busy_day_40", "排隊名店", "一天為客人做 80 杯"),
    ("busy_day_60", "全速運轉", "一天為客人做 150 杯"),
    ("daily_7", "每天一杯", "連續 7 天都有營業"),
    ("daily_30", "咖啡成癮", "連續 30 天都有營業"),
    ("daily_100", "百日修行", "連續 100 天都有營業"),
    ("perfect", "完美一杯", "為客人做出 95 分以上的一杯"),
    ("streak", "穩定發揮", "連續 10 張訂單 85 分以上"),
    ("streak_10", "手感正熱", "連續 30 張訂單 85 分以上"),
    ("streak_20", "職人水準", "連續 60 張訂單 85 分以上"),
    ("rosetta", "葉子拉成了", "為客人拉出一片漂亮的葉子"),
    ("art_trio", "拉花三連", "為客人拉出愛心、鬱金香、葉子"),
    ("art_all", "拉花圖鑑", "為客人做出拉花收集的七種圖案"),
    ("all_drinks", "全品項", "客人點的每一種常態飲品都做過"),
    ("festival_all", "節日巡禮", "為客人做過每一款節日限定飲品"),
    ("all_machines", "機器收藏家", "四台咖啡機都為客人沖過"),
    ("machines_90", "人機合一", "四台咖啡機都為客人沖出 90 分"),
    ("plant_milk", "植物奶玩家", "為客人用過燕麥奶、豆奶、杏仁奶"),
    ("regulars", "熟客滿意", "50 張訂單拿到 84 分以上"),
    ("regulars_50", "人氣咖啡師", "300 張訂單拿到 84 分以上"),
    ("regulars_200", "城裡最好喝", "1000 張訂單拿到 84 分以上"),
    ("picky", "搞定挑剔的客人", "兩個要求的訂單完全符合"),
    ("festival", "季節限定", "為客人做一杯節日限定飲品"),
    ("fresh", "賞味期", "用烘焙後 7–21 天的豆子為客人沖出 90 分"),
    ("world_3", "產地探索", "用 4 個產地的豆子為客人做過咖啡"),
    ("world", "環遊世界", "用 7 個產地的豆子為客人做過咖啡"),
    ("world_7", "全產地制霸", "用全部 10 個產地的豆子為客人做過咖啡（含精品豆）"),
    ("bags_10", "豆子愛好者", "開過 10 包豆子"),
    ("clean", "乾淨的吧台", "四種清潔保養都做過"),
    ("early_bird", "早起的咖啡師", "早上 5–7 點為客人做一杯咖啡"),
    ("night_owl", "夜貓子", "晚上 11 點到凌晨 4 點為客人做一杯咖啡"),
    ("first_pourover", "第一杯手沖", "為客人沖第一杯手沖咖啡"),
    ("pourover_90", "手沖職人", "為客人手沖出 90 分以上"),
    ("bloom", "悶蒸剛好", "悶蒸 30–45 秒、分 2 次以上注水，為客人沖出 85 分"),
    ("cold_drip", "慢慢等", "等一壺冰滴滴完"),
    ("moka_85", "爐火純青", "摩卡壺為客人沖出 85 分"),
    ("siphon_85", "虹吸達人", "虹吸壺為客人沖出 85 分"),
    ("all_methods", "沖煮方式全制霸", "義式、手沖、冰滴、摩卡壺、虹吸壺都為客人做過"),
    ("good_business", "生意興隆", "一天營業額達 $5,000"),
    ("biz_5000", "高朋滿座", "一天營業額達 $15,000"),
    ("biz_10000", "日進斗金", "一天營業額達 $30,000"),
    ("no_walkout", "沒人久等", "一天服務 20 位客人，沒有人等到離開"),
    ("no_walkout_30", "服務周到", "一天服務 50 位客人，沒有人等到離開"),
    ("no_walkout_50", "零客訴", "一天服務 100 位客人，沒有人等到離開"),
    ("serve_30", "一日店長", "營業模式一天服務 30 位客人"),
    ("tips_500", "小費罐滿了", "一天收到 $500 小費"),
    ("rush", "尖峰時刻", "排了 4 位客人時沒有人離開，一路做到隊伍清空"),
    ("shop_3", "小有名氣", "店鋪升到 Lv.3"),
    ("shop_6", "遠近馳名", "店鋪升到 Lv.6"),
    ("shop_10", "夢想成真", "店鋪升到 Lv.10"),
]
# 分級成就：同一組銅／銀／金三級，每一級是獨立的成就 key（已解鎖的舊 key 照樣有效）
# 組 → ((key, 門檻), …由低到高)；數值在 Stats.tier_values() 計算。key 是舊的名字，門檻 2026-10-22 調高過
TIER_GROUPS = {
    "cups": (("ten_cups", 50), ("hundred_cups", 500), ("cups_500", 2000)),
    "busy": (("busy_day", 40), ("busy_day_40", 80), ("busy_day_60", 150)),
    "daily": (("daily_7", 7), ("daily_30", 30), ("daily_100", 100)),
    "streak": (("streak", 10), ("streak_10", 30), ("streak_20", 60)),
    "regulars": (("regulars", 50), ("regulars_50", 300), ("regulars_200", 1000)),
    "world": (("world_3", 4), ("world", 7), ("world_7", 10)),
    "revenue": (("good_business", 5000), ("biz_5000", 15000), ("biz_10000", 30000)),
    "no_walkout": (("no_walkout", 20), ("no_walkout_30", 50), ("no_walkout_50", 100)),
    "shop": (("shop_3", 3), ("shop_6", 6), ("shop_10", 10)),
}
TIER_OF = {key: (group, level) for group, tiers in TIER_GROUPS.items() for level, (key, _) in enumerate(tiers)}
TIER_ICONS = ("🥉", "🥈", "🥇")
ART_BOOK = ("heart", "tulip", "rosetta", "dot", "mark", "whip", "blob")


def stamp():
    """紀錄的時間戳：日期跟 day 一樣用 today()（測試的 CAFE_DESK_DATE），時間用現在"""
    return datetime.datetime.combine(today(), datetime.datetime.now().time()).isoformat(timespec="seconds")


# 新欄位只能加在尾端（簽章依欄位順序計算）；CUP_FIELD_VERSIONS 記下每一版的欄位數，
# 舊版寫的列新欄位是 NULL，驗證時改用當時的欄位數重算簽章

CUP_FIELDS = ("ts", "day", "drink", "title", "score", "comment", "machine", "milk", "origin", "bean_age", "dose",
              "festival", "art", "art_q", "seed", "art_note", "is_order", "mods", "match",
              "price", "tip", "wait")                                           # 1.2：營業模式
CUP_FIELD_VERSIONS = (19, 22)
REAL_FIELDS = ("score", "bean_age", "dose", "art_q", "match", "price", "tip", "wait")


def db_path():
    base, _ = os.path.splitext(paths.CONFIG_PATH)
    return base + "_records.db"


def _old_json_path():
    base, ext = os.path.splitext(paths.CONFIG_PATH)
    return base + "_stats" + (ext or ".json")


def clock_hour():
    """現在幾點（早起、夜貓子成就用；測試會換掉）"""
    return datetime.datetime.now().hour


def _sign(prev, values):
    msg = json.dumps([prev] + list(values), ensure_ascii=False, separators=(",", ":"), default=str)
    return hmac.new(_KEY, msg.encode("utf-8"), hashlib.sha256).hexdigest()


def _empty():
    return {"days": {}, "achievements": {}, "streak": 0, "total": 0, "orders_good": 0, "revenue_total": 0,
            "order_total": 0, "order_streak": 0,     # 成就只算為客人做的杯子（訂單）
            "order_col": {"art": {}, "drinks": [], "machines": [], "milks": [], "origins": [], "machine_best": {}},
            "spent": 0, "owned": [],                 # 商店：花掉的錢、買過的一次性升級（store.py）
            "collection": {"art": {}, "drinks": {}, "machines": [], "milks": [], "origins": [], "cleaned": [],
                           "machine_best": {}, "bags": 0}}


class Stats:
    def __init__(self):
        self.data = _empty()
        self.tampered = 0                   # 驗證失敗（被修改或刪除）的筆數
        self.db = None
        try:
            self.db = sqlite3.connect(db_path())
            self._create()
            self._migrate_json()
            self.load()
        except sqlite3.Error:
            self.db = None                  # 資料庫打不開：只在記憶體裡統計

    # ───────────── 資料庫 ─────────────
    def _create(self):
        cols = ", ".join(f"{c} {'REAL' if c in REAL_FIELDS else 'TEXT'}" for c in CUP_FIELDS)
        self.db.executescript(f"""
            CREATE TABLE IF NOT EXISTS cups (id INTEGER PRIMARY KEY AUTOINCREMENT, {cols}, prev TEXT, sig TEXT);
            CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, day TEXT, kind TEXT,
                                               value TEXT, prev TEXT, sig TEXT);
            CREATE TABLE IF NOT EXISTS achievements (key TEXT PRIMARY KEY, day TEXT, sig TEXT);
        """)
        have = {row[1] for row in self.db.execute("PRAGMA table_info(cups)")}
        for c in CUP_FIELDS:                # 舊版資料庫：補上新欄位（舊列是 NULL）
            if c not in have:
                self.db.execute(f"ALTER TABLE cups ADD COLUMN {c} {'REAL' if c in REAL_FIELDS else 'TEXT'}")
        self.db.commit()

    def _last_sig(self, table):
        row = self.db.execute(f"SELECT sig FROM {table} ORDER BY id DESC LIMIT 1").fetchone()
        return row[0] if row else ""

    def _insert(self, table, fields, values):
        if self.db is None:
            return
        prev = self._last_sig(table)
        sig = _sign(prev, values)
        names = ", ".join(fields)
        marks = ", ".join("?" for _ in range(len(fields) + 2))
        self.db.execute(f"INSERT INTO {table} ({names}, prev, sig) VALUES ({marks})", list(values) + [prev, sig])
        self.db.commit()

    @staticmethod
    def _sig_ok(prev, values, sig, versions):
        """簽章正確？舊版寫的列（後面新加的欄位都是 NULL）用當時的欄位數驗證"""
        if hmac.compare_digest(_sign(prev, values), sig or ""):
            return True
        return any(n < len(values) and all(v is None for v in values[n:])
                   and hmac.compare_digest(_sign(prev, values[:n]), sig or "") for n in versions)

    def _verified(self, table, fields, versions=()):
        """依序讀出簽章正確的列；簽章不符或鏈斷掉都算一次竄改"""
        rows = self.db.execute(f"SELECT {', '.join(fields)}, prev, sig FROM {table} ORDER BY id").fetchall()
        last = ""
        for row in rows:
            values, prev, sig = row[:-2], row[-2], row[-1]
            if not self._sig_ok(prev, values, sig, versions):
                self.tampered += 1          # 這一列被改過：不計入
                last = sig or ""
                continue
            if prev != last:
                self.tampered += 1          # 前面有列被刪掉
            last = sig
            yield dict(zip(fields, values))

    def _migrate_json(self):
        """v7 的 JSON 紀錄：匯入成就後改名成 .bak"""
        old = _old_json_path()
        if not os.path.exists(old):
            return
        try:
            with open(old, encoding="utf-8") as f:
                d = json.load(f)
            for key, day in d.get("achievements", {}).items():
                self._save_achievement(key, day)
            os.replace(old, old + ".bak")
        except Exception:
            pass

    def _save_achievement(self, key, day):
        if self.db is None:
            return
        self.db.execute("INSERT OR IGNORE INTO achievements (key, day, sig) VALUES (?, ?, ?)",
                        (key, day, _sign("ach", (key, day))))
        self.db.commit()

    def load(self):
        """從驗證過的列重新算出所有統計"""
        self.data = _empty()
        self.tampered = 0
        if self.db is None:
            return
        for cup in self._verified("cups", CUP_FIELDS, CUP_FIELD_VERSIONS):
            self._apply(cup)
        for ev in self._verified("events", ("ts", "day", "kind", "value")):
            if ev["kind"] == "clean" and ev["value"] not in self.data["collection"]["cleaned"]:
                self.data["collection"]["cleaned"].append(ev["value"])
            elif ev["kind"] == "bag":
                self.data["collection"]["bags"] += 1
            elif ev["kind"] == "walkout":
                self.day(ev["day"])["walkouts"] += 1
            elif ev["kind"] == "purchase":
                self._apply_purchase(ev["value"])
        for key, day, sig in self.db.execute("SELECT key, day, sig FROM achievements"):
            if hmac.compare_digest(_sign("ach", (key, day)), sig or ""):
                self.data["achievements"][key] = day
            else:
                self.tampered += 1

    def save(self):
        """每筆資料寫入時就已存檔；保留這個介面給呼叫端"""

    # ───────────── 查詢 ─────────────
    def day(self, date=None):
        key = date.isoformat() if isinstance(date, datetime.date) else (date or today().isoformat())
        return self.data["days"].setdefault(key, {"cups": 0, "score_sum": 0.0, "best": None, "drinks": {},
                                                   "orders": 0, "beans_g": 0.0, "revenue": 0, "walkouts": 0,
                                                   "wait_sum": 0.0, "waited": 0, "tips": 0})

    def day_streak(self, key="cups"):
        """連續幾天都有做咖啡（key="orders"：都有營業）；算到今天，今天還沒有就算到昨天"""
        days = self.data["days"]
        d = today()
        if not days.get(d.isoformat(), {}).get(key):
            d -= datetime.timedelta(days=1)
        n = 0
        while days.get(d.isoformat(), {}).get(key):
            n += 1
            d -= datetime.timedelta(days=1)
        return n

    def unlocked(self, key):
        return key in self.data["achievements"]

    # ───────────── 記錄 ─────────────
    def _apply(self, cup):
        """把一杯加進統計（讀檔重算與新增共用）"""
        d = self.day(cup["day"])
        col = self.data["collection"]
        score = float(cup["score"] or 0)
        d["cups"] += 1
        d["score_sum"] += score
        d["drinks"][cup["drink"]] = d["drinks"].get(cup["drink"], 0) + 1
        d["beans_g"] += float(cup.get("dose") or 0)
        if cup.get("is_order"):
            d["orders"] += 1
            self._apply_order(cup, score)
            if score >= 84:
                self.data["orders_good"] += 1
            rev = int(round(float(cup.get("price") or 0) + float(cup.get("tip") or 0)))
            d["revenue"] += rev
            self.data["revenue_total"] += rev           # 店鋪等級（growth.level_of）
            d["tips"] += int(round(float(cup.get("tip") or 0)))
        if cup.get("wait") is not None:          # 營業模式的訂單才有等待時間
            d["wait_sum"] += float(cup["wait"])
            d["waited"] += 1
        if d["best"] is None or score > d["best"]["score"]:
            d["best"] = {"drink": cup["drink"], "title": cup["title"], "score": score, "comment": cup["comment"]}
        self.data["total"] += 1
        self.data["streak"] = self.data["streak"] + 1 if score >= 85 else 0
        dr = col["drinks"].setdefault(cup["drink"], {"count": 0, "best": 0.0})
        dr["count"] += 1
        dr["best"] = max(dr["best"], round(score, 1))
        art = cup.get("art")
        if art:
            prev = col["art"].get(art)
            q = float(cup.get("art_q") or 0)
            if prev is None or q > prev["q"]:
                col["art"][art] = {"q": round(q, 3), "seed": int(cup.get("seed") or 1), "date": cup["day"],
                                   "drink": cup["drink"]}
        mach = cup.get("machine")
        if mach:
            col["machine_best"][mach] = max(col["machine_best"].get(mach, 0.0), round(score, 1))
        for key, value in (("machines", cup.get("machine")), ("milks", cup.get("milk")),
                           ("origins", cup.get("origin"))):
            if value and value not in col[key]:
                col[key].append(value)

    def _apply_order(self, cup, score):
        """為客人做的杯子另外收一份（成就用）；拉花收集與圖鑑照樣顯示每一杯"""
        oc = self.data["order_col"]
        self.data["order_total"] += 1
        self.data["order_streak"] = self.data["order_streak"] + 1 if score >= 85 else 0
        if cup.get("drink") and cup["drink"] not in oc["drinks"]:
            oc["drinks"].append(cup["drink"])
        art = cup.get("art")
        if art and art not in oc["art"]:
            oc["art"][art] = True
        mach = cup.get("machine")
        if mach:
            oc["machine_best"][mach] = max(oc["machine_best"].get(mach, 0.0), round(score, 1))
        for key, value in (("machines", mach), ("milks", cup.get("milk")), ("origins", cup.get("origin"))):
            if value and value not in oc[key]:
                oc[key].append(value)

    def record(self, cup, all_drinks):
        """記一杯；回傳這次新解鎖的成就 key 清單"""
        row = {k: None for k in CUP_FIELDS}
        row.update({k: v for k, v in cup.items() if k in row})
        row["ts"] = stamp()
        row["day"] = today().isoformat()
        row["is_order"] = "1" if cup.get("order") else ""
        row["score"] = round(float(cup["score"]), 2)
        for k in ("art_q", "match", "bean_age", "dose", "price", "tip", "wait"):   # REAL 欄位：簽章與讀回的值要一致
            if row[k] is not None:
                row[k] = round(float(row[k]), 3)
        for k in ("seed", "mods"):
            if row[k] is not None:
                row[k] = str(row[k])
        values = [row[k] for k in CUP_FIELDS]
        try:
            self._insert("cups", CUP_FIELDS, values)
        except sqlite3.Error:
            pass
        self._apply(dict(zip(CUP_FIELDS, values)))
        return self.check(cup, all_drinks)

    def record_clean(self, kind):
        try:
            self._insert("events", ("ts", "day", "kind", "value"),
                         [stamp(), today().isoformat(), "clean", kind])
        except sqlite3.Error:
            pass
        col = self.data["collection"]
        if kind not in col["cleaned"]:
            col["cleaned"].append(kind)
        return self.check(None, ())

    def record_walkout(self, drink):
        """營業模式：客人等太久離開（不是一杯，記在 events）"""
        try:
            self._insert("events", ("ts", "day", "kind", "value"),
                         [stamp(), today().isoformat(), "walkout", drink])
        except sqlite3.Error:
            pass
        self.day()["walkouts"] += 1
        return self.check(None, ())

    def _apply_purchase(self, value):
        """events 的 purchase 值是「品項:價格」"""
        key, _, price = str(value).rpartition(":")
        try:
            self.data["spent"] += int(price)
        except ValueError:
            return
        if key not in self.data["owned"]:
            self.data["owned"].append(key)

    def record_purchase(self, key, price):
        """商店買東西（有簽章）；餘額不夠時回傳 False"""
        if self.data["revenue_total"] - self.data["spent"] < price:
            return False
        value = f"{key}:{int(price)}"
        try:
            self._insert("events", ("ts", "day", "kind", "value"), [stamp(), today().isoformat(), "purchase", value])
        except sqlite3.Error:
            pass
        self._apply_purchase(value)
        return True

    def recent(self, n=20):
        """最近幾杯（紀錄視窗用）"""
        if self.db is None:
            return []
        keep = self.tampered                # 只是讀取，不重複累計竄改筆數
        rows = list(self._verified("cups", CUP_FIELDS, CUP_FIELD_VERSIONS))
        self.tampered = keep
        return rows[-n:][::-1]

    def record_bag(self, origin):
        """開了一包新豆子"""
        try:
            self._insert("events", ("ts", "day", "kind", "value"),
                         [stamp(), today().isoformat(), "bag", origin])
        except sqlite3.Error:
            pass
        self.data["collection"]["bags"] += 1
        return self.check(None, ())

    def tier_values(self):
        """分級成就各組目前的數值"""
        d, oc = self.day(), self.data["order_col"]          # 成就只算為客人做的杯子
        return {"cups": self.data["order_total"], "busy": d["orders"], "daily": self.day_streak("orders"),
                "streak": self.data["order_streak"], "regulars": self.data["orders_good"], "world": len(oc["origins"]),
                "revenue": d["revenue"], "no_walkout": d["waited"] if d["walkouts"] == 0 else 0,
                "shop": level_of(self.data["revenue_total"])}

    def unlock(self, key):
        """不是由某一杯觸發的成就（例如冰滴滴完、尖峰時刻）；回傳新解鎖的 key 清單"""
        return self._grant([key])

    def check(self, cup, all_drinks):
        from .drinks import FESTIVAL_DRINKS, method_of
        from .brew import METHODS
        col, oc, d = self.data["collection"], self.data["order_col"], self.day()
        hour = clock_hour()
        best = oc["machine_best"]
        cup = cup if (cup and cup.get("order")) else None   # 跟杯子有關的成就只算為客人做的（保養、開豆子、冰滴照舊）
        conds = {
            "first_cup": self.data["order_total"] >= 1,
            "perfect": bool(cup and cup["score"] >= 95),
            "rosetta": bool(cup and cup.get("art") == "rosetta" and not cup.get("art_note")),
            "art_trio": all(a in oc["art"] for a in ("heart", "tulip", "rosetta")),
            "art_all": all(a in oc["art"] for a in ART_BOOK),
            "all_drinks": bool(all_drinks) and all(k in oc["drinks"] for k in all_drinks),
            "festival_all": all(k in oc["drinks"] for k in FESTIVAL_DRINKS),
            "all_machines": len(oc["machines"]) >= 4,
            "machines_90": len(best) >= 4 and all(v >= 90 for v in best.values()),
            "plant_milk": all(m in oc["milks"] for m in ("oat", "soy", "almond")),
            "picky": bool(cup and cup.get("mods", 0) >= 2 and cup.get("match", 0) >= 99.9),
            "festival": bool(cup and cup.get("festival")),
            "fresh": bool(cup and 7 <= cup.get("bean_age", 0) <= 21 and cup["score"] >= 90),
            "bags_10": col["bags"] >= 10,
            "clean": len(col["cleaned"]) >= 4,
            "early_bird": bool(cup) and 5 <= hour < 7,
            "night_owl": bool(cup) and (hour >= 23 or hour < 4),
            "first_pourover": bool(cup and cup["drink"] == "pour_over"),
            "pourover_90": bool(cup and cup["drink"] == "pour_over" and cup["score"] >= 90),
            "bloom": bool(cup and cup.get("bloom_ok") and cup["score"] >= 85),
            "moka_85": bool(cup and cup["drink"] == "moka_pot" and cup["score"] >= 85),
            "siphon_85": bool(cup and cup["drink"] == "siphon" and cup["score"] >= 85),
            "all_methods": {method_of(k) for k in oc["drinks"]} >= set(METHODS),
            "serve_30": d["waited"] >= 30,
            "tips_500": d["tips"] >= 500,
        }
        values = self.tier_values()
        for group, tiers in TIER_GROUPS.items():
            for key, need in tiers:
                conds[key] = values[group] >= need
        return self._grant([key for key, _, _ in ACHIEVEMENTS if conds.get(key)])

    def _grant(self, keys):
        new = []
        for key in keys:
            if key not in self.data["achievements"]:
                day = today().isoformat()
                self.data["achievements"][key] = day
                try:
                    self._save_achievement(key, day)
                except sqlite3.Error:
                    pass
                new.append(key)
        return new
