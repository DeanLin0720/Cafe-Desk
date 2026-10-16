"""每日紀錄、成就、收集冊：每做完一杯記一筆，存在設定檔旁的 SQLite 資料庫 *_records.db

資料表
    cups          每一杯（時間、飲品、分數、機器、牛奶、豆子、拉花、訂單…）
    events        其他事件（清潔保養）
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

_KEY = hashlib.sha256(b"cafe-desk/records/v1:" + b"\x63\x61\x66\x65").digest()

# (key, 名稱, 說明)
ACHIEVEMENTS = [
    ("first_cup", "第一杯", "做出第一杯咖啡"),
    ("ten_cups", "上手了", "累積 10 杯"),
    ("hundred_cups", "百杯咖啡師", "累積 100 杯"),
    ("busy_day", "忙碌的一天", "一天做 20 杯"),
    ("perfect", "完美一杯", "單杯 95 分以上"),
    ("streak", "穩定發揮", "連續 5 杯 85 分以上"),
    ("rosetta", "葉子拉成了", "拉出一片漂亮的葉子"),
    ("art_trio", "拉花三連", "收集愛心、鬱金香、葉子"),
    ("all_drinks", "全品項", "每一種常態飲品都做過"),
    ("all_machines", "機器收藏家", "四台咖啡機都用過"),
    ("plant_milk", "植物奶玩家", "燕麥奶、豆奶、杏仁奶都用過"),
    ("regulars", "熟客滿意", "10 張訂單拿到 84 分以上"),
    ("picky", "搞定挑剔的客人", "兩個要求的訂單完全符合"),
    ("festival", "季節限定", "做出一杯節日限定飲品"),
    ("fresh", "賞味期", "用烘焙後 7–21 天的豆子沖出 90 分"),
    ("world", "環遊世界", "用過 5 個產地的豆子"),
    ("clean", "乾淨的吧台", "四種清潔保養都做過"),
]
ART_BOOK = ("heart", "tulip", "rosetta", "dot", "mark", "whip", "blob")

CUP_FIELDS = ("ts", "day", "drink", "title", "score", "comment", "machine", "milk", "origin", "bean_age", "dose",
              "festival", "art", "art_q", "seed", "art_note", "is_order", "mods", "match")


def db_path():
    base, _ = os.path.splitext(paths.CONFIG_PATH)
    return base + "_records.db"


def _old_json_path():
    base, ext = os.path.splitext(paths.CONFIG_PATH)
    return base + "_stats" + (ext or ".json")


def _sign(prev, values):
    msg = json.dumps([prev] + list(values), ensure_ascii=False, separators=(",", ":"), default=str)
    return hmac.new(_KEY, msg.encode("utf-8"), hashlib.sha256).hexdigest()


def _empty():
    return {"days": {}, "achievements": {}, "streak": 0, "total": 0, "orders_good": 0,
            "collection": {"art": {}, "drinks": {}, "machines": [], "milks": [], "origins": [], "cleaned": []}}


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
        cols = ", ".join(f"{c} {'REAL' if c in ('score', 'bean_age', 'dose', 'art_q', 'match') else 'TEXT'}"
                         for c in CUP_FIELDS)
        self.db.executescript(f"""
            CREATE TABLE IF NOT EXISTS cups (id INTEGER PRIMARY KEY AUTOINCREMENT, {cols}, prev TEXT, sig TEXT);
            CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, day TEXT, kind TEXT,
                                               value TEXT, prev TEXT, sig TEXT);
            CREATE TABLE IF NOT EXISTS achievements (key TEXT PRIMARY KEY, day TEXT, sig TEXT);
        """)
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

    def _verified(self, table, fields):
        """依序讀出簽章正確的列；簽章不符或鏈斷掉都算一次竄改"""
        rows = self.db.execute(f"SELECT {', '.join(fields)}, prev, sig FROM {table} ORDER BY id").fetchall()
        last = ""
        for row in rows:
            values, prev, sig = row[:-2], row[-2], row[-1]
            if not hmac.compare_digest(_sign(prev, values), sig or ""):
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
        for cup in self._verified("cups", CUP_FIELDS):
            self._apply(cup)
        for ev in self._verified("events", ("ts", "day", "kind", "value")):
            if ev["kind"] == "clean" and ev["value"] not in self.data["collection"]["cleaned"]:
                self.data["collection"]["cleaned"].append(ev["value"])
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
                                                   "orders": 0, "beans_g": 0.0})

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
            if score >= 84:
                self.data["orders_good"] += 1
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
        for key, value in (("machines", cup.get("machine")), ("milks", cup.get("milk")),
                           ("origins", cup.get("origin"))):
            if value and value not in col[key]:
                col[key].append(value)

    def record(self, cup, all_drinks):
        """記一杯；回傳這次新解鎖的成就 key 清單"""
        row = {k: None for k in CUP_FIELDS}
        row.update({k: v for k, v in cup.items() if k in row})
        row["ts"] = datetime.datetime.now().isoformat(timespec="seconds")
        row["day"] = today().isoformat()
        row["is_order"] = "1" if cup.get("order") else ""
        row["score"] = round(float(cup["score"]), 2)
        for k in ("art_q", "match", "bean_age", "dose"):
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
                         [datetime.datetime.now().isoformat(timespec="seconds"), today().isoformat(), "clean", kind])
        except sqlite3.Error:
            pass
        col = self.data["collection"]
        if kind not in col["cleaned"]:
            col["cleaned"].append(kind)
        return self.check(None, ())

    def recent(self, n=20):
        """最近幾杯（紀錄視窗用）"""
        if self.db is None:
            return []
        keep = self.tampered                # 只是讀取，不重複累計竄改筆數
        rows = list(self._verified("cups", CUP_FIELDS))
        self.tampered = keep
        return rows[-n:][::-1]

    def check(self, cup, all_drinks):
        col = self.data["collection"]
        conds = {
            "first_cup": self.data["total"] >= 1,
            "ten_cups": self.data["total"] >= 10,
            "hundred_cups": self.data["total"] >= 100,
            "busy_day": self.day()["cups"] >= 20,
            "perfect": bool(cup and cup["score"] >= 95),
            "streak": self.data["streak"] >= 5,
            "rosetta": bool(cup and cup.get("art") == "rosetta" and not cup.get("art_note")),
            "art_trio": all(a in col["art"] for a in ("heart", "tulip", "rosetta")),
            "all_drinks": bool(all_drinks) and all(k in col["drinks"] for k in all_drinks),
            "all_machines": len(col["machines"]) >= 4,
            "plant_milk": all(m in col["milks"] for m in ("oat", "soy", "almond")),
            "regulars": self.data["orders_good"] >= 10,
            "picky": bool(cup and cup.get("order") and cup.get("mods", 0) >= 2 and cup.get("match", 0) >= 99.9),
            "festival": bool(cup and cup.get("festival")),
            "fresh": bool(cup and 7 <= cup.get("bean_age", 0) <= 21 and cup["score"] >= 90),
            "world": len(col["origins"]) >= 5,
            "clean": len(col["cleaned"]) >= 4,
        }
        new = []
        for key, _, _ in ACHIEVEMENTS:
            if conds.get(key) and key not in self.data["achievements"]:
                day = today().isoformat()
                self.data["achievements"][key] = day
                try:
                    self._save_achievement(key, day)
                except sqlite3.Error:
                    pass
                new.append(key)
        return new
