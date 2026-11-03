"""熟客系統：從紀錄算出等級、常回來、老樣子、小費與耐心"""
import random

import pytest

from cafe_desk import regulars, orders
from cafe_desk.i18n import EN

CUP = {"drink": "latte", "title": "拿鐵", "comment": "", "order": True, "price": 100, "tip": 0, "wait": 10.0, "size": "M"}


def test_levels_need_both_cups_and_average():
    rec = lambda n, avg, fav=None: {"cups": n, "score_sum": n * avg, "fav": fav or {}}
    assert regulars.level_of(None) == 0 and regulars.level_of(rec(2, 99)) == 0
    assert regulars.level_of(rec(3, 74)) == 0 and regulars.level_of(rec(3, 75)) == 1
    assert regulars.level_of(rec(8, 80)) == 2 and regulars.level_of(rec(15, 85)) == 3
    assert regulars.level_of(rec(30, 70)) == 0                    # 做得不好：掉回新客
    assert regulars.tip_k(0) == 1 and regulars.tip_k(3) == pytest.approx(1.75)
    assert regulars.favorite(rec(5, 80, {"latte": 2, "mocha": 3})) == "mocha"
    assert regulars.favorite(rec(5, 80, {"b": 2, "a": 2})) == "a"
    for _, _, name in regulars.LEVELS:
        assert name in EN


def test_roster_and_pick():
    custs = {"Amy": {"cups": 9, "score_sum": 9 * 90, "fav": {"latte": 9}}, "Ken": {"cups": 3, "score_sum": 3 * 80, "fav": {}},
             "Joe": {"cups": 1, "score_sum": 60, "fav": {}}}
    assert [r[0] for r in regulars.roster(custs)] == ["Amy", "Ken"]
    pool = ("Amy", "Ken", "Joe", "Mia")
    rnd = random.Random(1)
    names = [regulars.pick_name(rnd, custs, pool, "Amy") for _ in range(300)]
    assert "Amy" not in names and {"Ken", "Joe", "Mia"} <= set(names)    # 不連續同一位
    assert regulars.pick_name(random.Random(2), {}, pool) in pool
    names = [regulars.pick_name(random.Random(i), custs, pool) for i in range(300)]
    assert names.count("Amy") > 300 / 4                                  # 熟客比較常來


def test_usual_tip_and_patience():
    rnd = random.Random(3)
    o = orders.make_order(1, rnd, name="Amy", favorite="mocha")
    assert o.name == "Amy" and (o.drink == "mocha") == o.usual
    hits = [orders.make_order(1, random.Random(i), favorite="mocha").usual for i in range(200)]
    assert 60 < sum(hits) < 140                                          # 約一半
    assert not orders.make_order(1, rnd, favorite="mocha", exclude=("mocha",)).usual   # 點不到就不點
    o.score, o.price, o.regular = 95, 100, 0
    base = orders.tip(o)
    o.regular = 3
    assert orders.tip(o) == int(round(base * 1.75))


def test_customer_stats_from_records(desk):
    for score in (90, 80, 70):
        desk.stats.record(dict(CUP, score=score, customer="Amy"), [])
    desk.stats.record(dict(CUP, score=88, drink="mocha", customer="Amy", inspector=True), [])
    desk.stats.record(dict(CUP, score=50), [])                            # 沒有名字的不算
    c = desk.stats.data["customers"]
    assert list(c) == ["Amy"] and c["Amy"]["cups"] == 4 and c["Amy"]["fav"] == {"latte": 3, "mocha": 1}
    desk.stats.load()
    assert desk.stats.data["customers"]["Amy"]["cups"] == 4 and desk.stats.tampered == 0
    assert regulars.level_of(desk.stats.data["customers"]["Amy"]) == 1


def test_business_order_for_regular(desk, monkeypatch):
    for _ in range(9):
        desk.stats.record(dict(CUP, score=90, customer="Amy"), [])
    monkeypatch.setattr(regulars, "RETURN_P", 1.0)
    monkeypatch.setattr(regulars, "USUAL_P", 1.0)
    monkeypatch.setattr(orders, "party_size", lambda rnd=random: 1)
    desk.set_order_mode(True)
    desk.order, desk.queue = None, []
    desk.new_order()
    o = desk.order
    assert o.name == "Amy" and o.regular == 2 and o.usual and o.drink == "latte"
    assert o.patience > 0


def test_customer_habits(desk, qapp):
    for drink, size, to_go, milk, day in (("latte", "L", True, "oat", "2026-08-01"), ("latte", "L", True, "oat", "2026-08-01"),
                                          ("mocha", "M", True, "dairy", "2026-08-01"), ("espresso", "L", False, None, "2026-08-01")):
        desk.stats.record(dict(CUP, score=88, drink=drink, size=size, to_go=to_go, milk=milk, customer="Amy"), [])
    h = regulars.habits(desk.stats.data["customers"]["Amy"])
    assert h["drinks"] == ["latte", "espresso"] and h["size"] == "L" and h["place"] == "to_go" and h["milk"] == "oat"
    assert h["last"] == "2026-08-01" and h["best"] == 88
    assert regulars.habits(None) == {"drinks": [], "size": None, "place": None, "milk": None, "last": "", "best": 0.0}
    desk.stats.load()                                          # 重讀資料庫：習慣一樣
    assert regulars.habits(desk.stats.data["customers"]["Amy"]) == h
    desk.open_records()
    dlg = desk.records_dlg
    names = [dlg.tabs.tabText(i) for i in range(dlg.tabs.count())]
    assert "營運紀錄" in names and "說明" not in names
    assert [dlg.ops_sub.tabText(i) for i in range(dlg.ops_sub.count())] == ["今天", "店鋪", "客人", "近期紀錄"]
    dlg.close()


def test_grinder_icon_has_no_knock_box(desk):
    """圖鑑的獨立磨豆機縮圖不畫敲渣盒（它在機身外一段距離，畫進去磨豆機會縮很小），畫完還原繪圖函式"""
    from cafe_desk.render import gear_icons
    calls = []
    orig = type(desk).paint_knock_box
    type(desk).paint_knock_box = lambda self, p, box: calls.append(1)
    try:
        gear_icons.grinder_icon(desk, 150, 104, False, 1.0)
    finally:
        type(desk).paint_knock_box = orig
    assert not calls and "paint_knock_box" not in desk.__dict__


def test_next_level_progress():
    """升下一級還差多少：杯數與平均分數；最高等級回傳 None"""
    from cafe_desk import regulars
    assert regulars.next_level({"cups": 1, "score_sum": 90.0})[:3] == ("熟面孔", 2, None)
    name, cups, avg, prog = regulars.next_level({"cups": 4, "score_sum": 4 * 70.0})
    assert (name, cups, avg, prog) == ("熟面孔", 0, 75.0, 0.95), "杯數夠了、平均還不到：停在 0.95"
    name, cups, avg, prog = regulars.next_level({"cups": 5, "score_sum": 5 * 78.0})
    assert name == "熟客" and cups == 3 and avg == 80.0 and abs(prog - 5 / 8) < 1e-9
    assert regulars.next_level({"cups": 20, "score_sum": 20 * 90.0}) is None


def test_customers_tab_cards(desk):
    """客人分頁：熟客名冊與其他客人分開，每位一張卡片"""
    from PySide6.QtWidgets import QFrame, QLabel
    from cafe_desk.records import RecordsDialog
    for i in range(4):
        desk.stats.record({"drink": "latte", "title": "拿鐵", "score": 88, "comment": "", "order": True, "price": 120,
                           "tip": 0, "customer": "Amy", "size": "L", "to_go": ""}, [])
    desk.stats.record({"drink": "espresso", "title": "濃縮", "score": 70, "comment": "", "order": True, "price": 70,
                       "tip": 0, "customer": "Ken", "size": "M", "to_go": "1"}, [])
    dlg = RecordsDialog(desk)
    tab = dlg.customers_tab()
    cards = [f for f in tab.findChildren(QFrame) if f.objectName() == "custcard"]
    texts = " ".join(lab.text() for lab in tab.findChildren(QLabel))
    assert len(cards) == 2
    assert "熟客名冊（1 位）" in texts and "其他客人（1 位）" in texts and "老樣子：熱拿鐵" in texts
    assert "升「熟客」" in texts and "升「熟面孔」：再 2 杯、平均要 75 分" in texts
    dlg.close()
