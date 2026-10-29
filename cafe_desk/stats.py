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

from . import paths, ingredients
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
    ("art_trio", "拉花三連", "為客人拉出 3 種拉花圖案"),
    ("art_all", "拉花圖鑑", "為客人做出拉花收集的七種圖案"),
    ("all_drinks", "全品項", "客人點的每一種常態飲品都做過"),
    ("festival_all", "節日巡禮", "為客人做過每一款節日限定飲品"),
    ("all_machines", "機器收藏家", "每一台咖啡機都為客人沖過"),
    ("machines_90", "人機合一", "每一台咖啡機都為客人沖出 90 分"),
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
    ("bags_50", "咖啡豆大戶", "開過 50 包豆子"),
    ("bags_150", "豆子消耗大王", "開過 150 包豆子"),
    ("ing_30", "備料新手", "營業中用掉 30 份食材（牛奶、醬料、鮮奶油…）"),
    ("ing_150", "原料大戶", "營業中用掉 150 份食材"),
    ("ing_500", "食材消耗狂人", "營業中用掉 500 份食材"),
    ("ing_all", "吧台食材全制霸", "營業中用過每一種常態食材（鮮奶、三種植物奶、鮮奶油、巧克力醬、香草糖漿、焦糖醬、可可粉、冰淇淋、通寧水）"),
    ("dessert_10", "甜點上架", "營業中賣出 10 個甜點（客人加購）"),
    ("dessert_50", "甜點專賣店", "營業中賣出 50 個甜點"),
    ("dessert_200", "甜點大亨", "營業中賣出 200 個甜點"),
    ("dessert_all", "甜點全制霸", "可頌、蛋糕、馬芬、餅乾都賣出過"),
    ("dessert_full", "櫥窗滿滿", "櫥窗裡四種甜點同時都有庫存"),
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
    ("tips_500", "小費滿滿", "一天收到 $500 小費"),
    ("rush", "尖峰時刻", "排了 4 位客人時沒有人離開，一路做到隊伍清空"),
    ("duo_pair", "雙杯齊發", "用營業用雙頭機一次為兩位客人做好飲品"),
    ("to_go_20", "外帶達人", "為客人做了 20 杯外帶"),
    ("dine_in_50", "內用常客", "為內用的客人做了 50 杯"),
    ("size_l_20", "大杯滿足", "為客人做了 20 杯大杯"),
    ("party_3", "三五好友", "一張單三杯，一起做好、一起結帳"),
    ("seats_full", "座無虛席", "店裡的座位全部坐滿"),
    ("together", "一心二用", "職人的手藝：單頭咖啡機萃取的同時打奶，為客人做好一杯"),
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
    "bags": (("bags_10", 10), ("bags_50", 50), ("bags_150", 150)),         # 開過幾包豆子（消耗咖啡豆）
    "dessert": (("dessert_10", 10), ("dessert_50", 50), ("dessert_200", 200)),   # 營業中賣出幾個甜點
    "ing": (("ing_30", 30), ("ing_150", 150), ("ing_500", 500)),           # 營業中用掉幾份食材
    # 兩級的（2026-10-23 整理：原本是兩個單項成就）
    "festival": (("festival", 1), ("festival_all", 3)),                # 為客人做過幾款節日限定飲品（共 3 款）
    "art": (("art_trio", 3), ("art_all", 7)),                           # 為客人拉出幾種拉花圖案（ART_BOOK 7 種）
}
# 成就頁的分類：(標題, key…)；分級成就用組裡任一個 key
ACH_SECTIONS = (
    ("營業", ("first_cup", "ten_cups", "busy_day", "good_business", "no_walkout", "serve_30", "tips_500", "rush",
             "to_go_20", "dine_in_50", "size_l_20", "party_3", "seats_full", "duo_pair", "shop_3")),
    ("手藝", ("perfect", "streak", "regulars", "picky", "fresh", "rosetta", "art_trio", "machines_90", "together")),
    ("收集", ("all_drinks", "festival", "all_machines", "plant_milk", "world_3", "bags_10", "ing_30", "ing_all", "dessert_10", "dessert_all", "dessert_full")),
    ("沖煮方式", ("first_pourover", "pourover_90", "bloom", "cold_drip", "moka_85", "siphon_85", "all_methods")),
    ("日常", ("daily_7", "clean", "early_bird", "night_owl")),
)
TIER_OF = {key: (group, level) for group, tiers in TIER_GROUPS.items() for level, (key, _) in enumerate(tiers)}
TIER_ICONS = ("🥉", "🥈", "🥇")


def tier_rank(key):
    """分級成就這一級的獎牌（0 銅、1 銀、2 金）：兩級的組是銀、金"""
    group, level = TIER_OF[key]
    return level + 3 - len(TIER_GROUPS[group])
ART_BOOK = ("heart", "tulip", "rosetta", "dot", "mark", "whip", "blob")


def stamp():
    """紀錄的時間戳：日期跟 day 一樣用 today()（測試的 CAFE_DESK_DATE），時間用現在"""
    return datetime.datetime.combine(today(), datetime.datetime.now().time()).isoformat(timespec="seconds")


# 新欄位只能加在尾端（簽章依欄位順序計算）；CUP_FIELD_VERSIONS 記下每一版的欄位數，
# 舊版寫的列新欄位是 NULL，驗證時改用當時的欄位數重算簽章

CUP_FIELDS = ("ts", "day", "drink", "title", "score", "comment", "machine", "milk", "origin", "bean_age", "dose",
              "festival", "art", "art_q", "seed", "art_note", "is_order", "mods", "match",
              "price", "tip", "wait",                                           # 1.2：營業模式
              "to_go",                                                          # 收銀台：外帶（"1"）／內用（""）
              "size",                                                           # 大中小杯：S／M／L
              "inspector",                                                      # 評鑑員客人（"1"）：這杯在星級評鑑裡算兩倍
              "customer")                                                       # 客人的名字（熟客系統 regulars.py）
CUP_FIELD_VERSIONS = (19, 22, 23, 24, 25, 26)
REAL_FIELDS = ("score", "bean_age", "dose", "art_q", "match", "price", "tip", "wait")


START_FUNDS = 5000          # 錢包的初始資金（不計入店鋪等級的累積營業額；舊存檔也有）


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
            "bean_stock": {},                        # 各種豆子庫存的包數（商店買的 bean_buy 減開包的 bean_use）
            "dessert_sold": {}, "dessert_bought": {}, "dessert_spent": 0,   # 甜點：各種賣出的個數、進貨的盤數、進貨花費（購買紀錄）
            "ing_used_by": {},                       # 各種食材營業中用掉的份數累計（圖鑑與消耗成就）
            "ing_stock": dict(ingredients.START_STOCK),   # 各種食材庫存的份數（開局送的＋商店買的 ing_buy 減營業用掉的 ing_use）
            "stamps_spent": 0,                       # 用掉的挑戰章數（裝潢的限定款，decor.py）
            "customers": {},                         # 客人名字 → {cups, score_sum, fav}（熟客系統）
            "challenges": [],                        # 完成過的挑戰 id（challenges.py）
            "order_to_go": 0,                        # 外帶的訂單杯數
            "order_dine": 0, "order_large": 0, "order_drinks": {},       # 內用、大杯的訂單杯數（有記大中小杯的新紀錄才算）
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
            elif ev["kind"] == "bean_buy":
                self._apply_bean_buy(ev["value"])
            elif ev["kind"] == "bean_use":
                self.data["bean_stock"][ev["value"]] = max(0, self.data["bean_stock"].get(ev["value"], 0) - 1)
            elif ev["kind"] == "ing_buy":
                self._apply_ing_buy(ev["value"])
            elif ev["kind"] == "ing_use":
                self._apply_ing_use(ev["value"])
            elif ev["kind"] == "decor_stamps":
                self._apply_stamp_purchase(ev["value"])
            elif ev["kind"] == "challenge" and ev["value"] not in self.data["challenges"]:
                self.data["challenges"].append(ev["value"])
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
        return self.data["days"].setdefault(key, {"cups": 0, "score_sum": 0.0, "best": None, "drinks": {}, "order_drinks": {},
                                                   "orders": 0, "beans_g": 0.0, "revenue": 0, "walkouts": 0,
                                                   "wait_sum": 0.0, "waited": 0, "tips": 0,
                                                   "rate_sum": 0.0, "rate_n": 0,
                                                   "hi": {}, "large": 0, "to_go": 0, "dine": 0, "festival": 0})   # 每日挑戰：90 分以上（依飲品）、大杯、外帶、內用、季節限定的訂單杯數        # 星級評鑑：訂單分數的加權總和與權重（評鑑員那杯算 2）

    def top_drinks(self, n=3):
        """熱賣前 n 名（為客人做的杯數）：(標題, [(飲品, 杯數)…])；今天不到 n 種就看累積的"""
        today_ = self.day().get("order_drinks", {})
        pick = today_ if len(today_) >= n else self.data.get("order_drinks", {})
        top = sorted(pick.items(), key=lambda kv: (-kv[1], kv[0]))[:n]
        return ("今日熱賣" if pick is today_ else "熱賣"), top

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
            name = cup.get("customer")
            if name:
                c = self.data["customers"].setdefault(name, {"cups": 0, "score_sum": 0.0, "fav": {}, "size": {}, "milk": {},
                                                             "to_go": 0, "dine": 0, "last": "", "best": 0.0})
                c["cups"] += 1
                c["score_sum"] += score
                c["fav"][cup["drink"]] = c["fav"].get(cup["drink"], 0) + 1
                if cup.get("size"):                       # 杯型、內用外帶：舊紀錄沒有，不算
                    c["size"][cup["size"]] = c["size"].get(cup["size"], 0) + 1
                    c["to_go" if cup.get("to_go") else "dine"] += 1
                if cup.get("milk") and cup.get("drink") in ("latte", "cappuccino", "flat_white", "cortado", "macchiato",
                                                           "mocha", "caramel_macchiato", "iced_latte"):
                    c["milk"][cup["milk"]] = c["milk"].get(cup["milk"], 0) + 1
                c["last"] = max(c["last"], cup["day"])
                c["best"] = max(c["best"], score)
            w = 2 if cup.get("inspector") else 1
            d["rate_sum"] += score * w
            d["rate_n"] += w
            if score >= 90:
                d["hi"][cup["drink"]] = d["hi"].get(cup["drink"], 0) + 1
            if cup.get("size") == "L":
                d["large"] += 1
            if cup.get("to_go"):
                d["to_go"] += 1
            elif cup.get("size"):
                d["dine"] += 1
            if cup.get("festival"):
                d["festival"] += 1
            d["order_drinks"][cup["drink"]] = d["order_drinks"].get(cup["drink"], 0) + 1      # 熱賣（櫃檯的 MENU 板）
            od = self.data.setdefault("order_drinks", {})
            od[cup["drink"]] = od.get(cup["drink"], 0) + 1
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
        if cup.get("to_go"):
            self.data["order_to_go"] += 1
        elif cup.get("size"):                        # 內用（舊紀錄沒有大中小杯，分不出內用外帶）
            self.data["order_dine"] += 1
        if cup.get("size") == "L":
            self.data["order_large"] += 1
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
        row["to_go"] = "1" if cup.get("to_go") else ""
        row["inspector"] = "1" if cup.get("inspector") else ""
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

    def wallet(self):
        """錢包餘額：初始資金＋累積營業額－花掉的錢"""
        return START_FUNDS + self.data["revenue_total"] - self.data["spent"]

    def _apply_bean_buy(self, value):
        """events 的 bean_buy 值是「產地:價格」：花錢、庫存加一包"""
        origin, _, price = str(value).rpartition(":")
        try:
            self.data["spent"] += int(price)
        except ValueError:
            return
        self.data["bean_stock"][origin] = self.data["bean_stock"].get(origin, 0) + 1

    def record_bean_buy(self, origin, price):
        """商店買一包豆子（有簽章）；餘額不夠時回傳 False"""
        if self.wallet() < price:
            return False
        value = f"{origin}:{int(price)}"
        try:
            self._insert("events", ("ts", "day", "kind", "value"), [stamp(), today().isoformat(), "bean_buy", value])
        except sqlite3.Error:
            pass
        self._apply_bean_buy(value)
        return True

    def record_bean_use(self, origin):
        """開一包庫存的豆子（有簽章）；沒有庫存時回傳 False"""
        if self.data["bean_stock"].get(origin, 0) <= 0:
            return False
        try:
            self._insert("events", ("ts", "day", "kind", "value"), [stamp(), today().isoformat(), "bean_use", origin])
        except sqlite3.Error:
            pass
        self.data["bean_stock"][origin] -= 1
        return True

    def _apply_ing_buy(self, value):
        """events 的 ing_buy 值是「食材:價格」：花錢、庫存加一包的份數"""
        key, _, price = str(value).rpartition(":")
        if key not in ingredients.ALL:
            return
        try:
            self.data["spent"] += int(price)
        except ValueError:
            return
        self.data["ing_stock"][key] = self.data["ing_stock"].get(key, 0) + ingredients.pack(key)
        if key in ingredients.DESSERTS:
            self.data["dessert_bought"][key] = self.data["dessert_bought"].get(key, 0) + 1
            self.data["dessert_spent"] += int(price)

    def _apply_ing_use(self, value):
        """events 的 ing_use 值是「食材:份數」：庫存減掉用掉的份數（不會低於 0）；份數是負的＝客人沒取餐、退回庫存
        （用掉量、賣出量跟著減回去，不會低於 0）"""
        key, _, n = str(value).rpartition(":")
        try:
            n = int(n)
        except ValueError:
            return
        self.data["ing_stock"][key] = max(0, self.data["ing_stock"].get(key, 0) - n)
        if key in ingredients.ITEMS:
            self.data["ing_used_by"][key] = max(0, self.data["ing_used_by"].get(key, 0) + n)
        elif key in ingredients.DESSERTS:
            self.data["dessert_sold"][key] = max(0, self.data["dessert_sold"].get(key, 0) + n)

    def dessert_log(self, limit=12):
        """甜點進貨紀錄（新的在前）：[(日期, 甜點 key, 價格)]"""
        if self.db is None:
            return []
        out = []
        try:
            rows = self.db.execute("SELECT day, value FROM events WHERE kind='ing_buy' ORDER BY id DESC").fetchall()
        except sqlite3.Error:                    # 資料庫已關閉（關程式時畫面才重畫）
            return []
        for day, value in rows:
            key, _, price = str(value).rpartition(":")
            if key in ingredients.DESSERTS:
                out.append((day, key, int(price) if price.isdigit() else 0))
                if len(out) >= limit:
                    break
        return out

    def record_ing_buy(self, key):
        """商店買一包食材（有簽章）；餘額不夠或沒這種食材時回傳 False"""
        if key not in ingredients.ALL or self.wallet() < ingredients.price_of(key):
            return False
        value = f"{key}:{ingredients.price_of(key)}"
        try:
            self._insert("events", ("ts", "day", "kind", "value"), [stamp(), today().isoformat(), "ing_buy", value])
        except sqlite3.Error:
            pass
        self._apply_ing_buy(value)
        return True

    def record_ing_use(self, key, n=1):
        """營業中用掉 n 份食材（有簽章）；庫存不夠時回傳 False（不扣）"""
        if key not in ingredients.ALL or self.data["ing_stock"].get(key, 0) < n:
            return False
        value = f"{key}:{n}"
        try:
            self._insert("events", ("ts", "day", "kind", "value"), [stamp(), today().isoformat(), "ing_use", value])
        except sqlite3.Error:
            pass
        self._apply_ing_use(value)
        return True

    def record_ing_refund(self, key, n=1):
        """客人沒取餐（等太久離開、打烊）：把先前扣掉的 n 份食材退回庫存（有簽章；事件是負的 ing_use）"""
        if key not in ingredients.ALL or n <= 0:
            return False
        value = f"{key}:{-n}"
        try:
            self._insert("events", ("ts", "day", "kind", "value"), [stamp(), today().isoformat(), "ing_use", value])
        except sqlite3.Error:
            pass
        self._apply_ing_use(value)
        return True

    def _apply_stamp_purchase(self, value):
        """events 的 decor_stamps 值是「品項:章數」"""
        key, _, n = str(value).rpartition(":")
        try:
            self.data["stamps_spent"] += int(n)
        except ValueError:
            return
        if key not in self.data["owned"]:
            self.data["owned"].append(key)

    def record_stamp_purchase(self, key, stamps, available):
        """用挑戰章數兌換限定的裝潢（有簽章）；章數不夠時回傳 False"""
        if available < stamps:
            return False
        value = f"{key}:{int(stamps)}"
        try:
            self._insert("events", ("ts", "day", "kind", "value"), [stamp(), today().isoformat(), "decor_stamps", value])
        except sqlite3.Error:
            pass
        self._apply_stamp_purchase(value)
        return True

    def record_challenge(self, cid):
        """完成一個每日／每週挑戰（有簽章；同一個挑戰只記一次）"""
        if cid in self.data["challenges"]:
            return False
        try:
            self._insert("events", ("ts", "day", "kind", "value"), [stamp(), today().isoformat(), "challenge", cid])
        except sqlite3.Error:
            pass
        self.data["challenges"].append(cid)
        return True

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
        if self.wallet() < price:
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
        from .drinks import FESTIVAL_DRINKS
        d, oc = self.day(), self.data["order_col"]          # 成就只算為客人做的杯子
        return {"cups": self.data["order_total"], "busy": d["orders"], "daily": self.day_streak("orders"),
                "streak": self.data["order_streak"], "regulars": self.data["orders_good"], "world": len(oc["origins"]),
                "revenue": d["revenue"], "no_walkout": d["waited"] if d["walkouts"] == 0 else 0,
                "shop": level_of(self.data["revenue_total"]), "bags": self.data["collection"]["bags"],
                "ing": sum(self.data["ing_used_by"].values()),
                "dessert": sum(self.data["dessert_sold"].values()),
                "festival": sum(1 for k in oc["drinks"] if k in FESTIVAL_DRINKS),
                "art": sum(1 for a in ART_BOOK if a in oc["art"])}

    def unlock(self, key):
        """不是由某一杯觸發的成就（例如冰滴滴完、尖峰時刻）；回傳新解鎖的 key 清單"""
        return self._grant([key])

    def check(self, cup, all_drinks):
        from .drinks import method_of
        from .brew import METHODS
        from .machines import MACHINES
        col, oc, d = self.data["collection"], self.data["order_col"], self.day()
        hour = clock_hour()
        best = oc["machine_best"]
        cup = cup if (cup and cup.get("order")) else None   # 跟杯子有關的成就只算為客人做的（保養、開豆子、冰滴照舊）
        conds = {
            "first_cup": self.data["order_total"] >= 1,
            "perfect": bool(cup and cup["score"] >= 95),
            "rosetta": bool(cup and cup.get("art") == "rosetta" and not cup.get("art_note")),
            "all_drinks": bool(all_drinks) and all(k in oc["drinks"] for k in all_drinks),
            "all_machines": len(oc["machines"]) >= len(MACHINES),
            "machines_90": len(best) >= len(MACHINES) and all(v >= 90 for v in best.values()),
            "plant_milk": all(m in oc["milks"] for m in ("oat", "soy", "almond")),
            "picky": bool(cup and cup.get("mods", 0) >= 2 and cup.get("match", 0) >= 99.9),
            "fresh": bool(cup and 7 <= cup.get("bean_age", 0) <= 21 and cup["score"] >= 90),
            "ing_all": all(self.data["ing_used_by"].get(k, 0) > 0 for k in ingredients.COMMON),
            "dessert_all": all(self.data["dessert_sold"].get(k, 0) > 0 for k in ingredients.DESSERTS),
            "dessert_full": all(self.data["ing_stock"].get(k, 0) > 0 for k in ingredients.DESSERTS),
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
            "to_go_20": self.data["order_to_go"] >= 20,
            "dine_in_50": self.data["order_dine"] >= 50,
            "size_l_20": self.data["order_large"] >= 20,
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
