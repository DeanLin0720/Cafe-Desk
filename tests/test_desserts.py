"""甜點：商店進貨、櫥窗擺出有庫存的、客人加購（折價）、有貨內用客人變多"""
import random

from PySide6.QtGui import QImage, QPainter

from cafe_desk import ingredients, orders, stats
from cafe_desk.i18n import EN, money
from cafe_desk.render import shop


def _earn(st, amount):
    st.record({"drink": "latte", "title": "拿鐵", "score": 90, "comment": "", "order": True, "price": amount,
               "tip": 0}, [])


def _biz(desk, monkeypatch, stock):
    desk.set_order_mode(True)
    desk.arrive_in = 1e9
    desk.stats.data["ing_stock"].update({k: 99 for k in ingredients.ITEMS})
    desk.stats.data["ing_stock"].update({k: 0 for k in ingredients.DESSERTS})
    desk.stats.data["ing_stock"].update(stock)
    monkeypatch.setattr(orders, "PARTY_SIZES", ((1, 1.0),))
    monkeypatch.setattr(orders, "mod_pool", lambda drink: [])


def test_dessert_texts_and_prices():
    for key, (name, per, price, desc) in ingredients.DESSERTS.items():
        assert name in EN and desc in EN and per > 0 and price > 0, key
        assert ingredients.dessert_price(key) < ingredients.DESSERT_PRICE[key], "加購有折價"
        assert ingredients.dessert_price(key) * per > price, "賣完一盤有賺"
    assert not set(ingredients.DESSERTS) & set(ingredients.ITEMS)
    assert set(ingredients.ALL) == set(ingredients.ITEMS) | set(ingredients.DESSERTS)


def test_buy_dessert_tray_uses_signed_events(desk):
    _earn(desk.stats, 5000)
    w = desk.wallet()
    assert desk.ing_stock("croissant") == 0 and desk.dessert_stock() == {}, "開局櫥窗是空的"
    assert desk.buy_ingredient("croissant")
    assert desk.ing_stock("croissant") == ingredients.pack("croissant") and desk.wallet() == w - ingredients.price_of("croissant")
    assert desk.dessert_stock() == {"croissant": ingredients.pack("croissant")}
    assert desk.stats.db.execute("SELECT COUNT(*) FROM events WHERE kind='ing_buy'").fetchone()[0] == 1
    assert not desk.stats.record_ing_use("nothing", 1)


def test_case_layout_follows_stock():
    assert shop.dessert_layout({}, 18) == []
    assert shop.dessert_layout({"cake": 2}, 18) == ["cake", "cake"]
    full = shop.dessert_layout({"croissant": 50, "cake": 50, "muffin": 50, "cookie": 50}, 18)
    assert len(full) == 18 and set(full) == set(ingredients.DESSERTS), "超過格數也每種都有"
    assert shop.dessert_layout({"cake": 50}, 18) == ["cake"] * shop.DESSERT_SHOWN, "一種最多擺幾個"


def test_counter_paints_with_and_without_desserts(desk):
    for stock in ({}, {k: 5 for k in ingredients.DESSERTS}):
        desk.stats.data["ing_stock"].update({k: 0 for k in ingredients.DESSERTS})
        desk.stats.data["ing_stock"].update(stock)
        img = QImage(1100, 720, QImage.Format_ARGB32)
        img.fill(0)
        p = QPainter(img)
        desk.paint_counter(p)
        p.end()


def test_counter_layer_cache_redraws_when_shop_changes(desk):
    """櫃檯畫面的店面快取：沒變就重用同一張圖，甜點庫存、裝潢、語言變了就重畫"""
    desk.counter_view = True
    desk.stats.data["ing_stock"].update({k: 0 for k in ingredients.DESSERTS})
    frame = lambda: (desk.paintEvent(None), dict(desk._counter_layers))[1]
    a = frame()
    assert set(a) == {"room", "front"}
    b = frame()
    assert b["room"] is a["room"] and b["front"] is a["front"], "沒變就重用"
    desk.stats.data["ing_stock"]["cake"] = 5
    c = frame()
    assert c["front"] is not b["front"] and c["room"] is b["room"], "甜點進貨：只重畫前櫃檯"
    desk.cfg["decor"] = {"wall": "brick"}
    desk.stats.data["owned"].append("brick")
    d = frame()
    assert d["room"] is not c["room"] and d["front"] is not c["front"], "換裝潢：兩層都重畫"


def test_dessert_add_on_discounted_and_uses_stock(desk, unlocked, monkeypatch):
    _biz(desk, monkeypatch, {"cake": 2})
    monkeypatch.setattr(ingredients, "DESSERT_P", 1.0)
    desk.order, desk.queue = None, []
    desk.new_order()
    o = desk.order
    assert o.dessert == "cake" and o.dessert_price == ingredients.dessert_price("cake")
    assert desk.ing_stock("cake") == 1
    base = o.price - o.dessert_price
    assert base > 0 and o.price == base + o.dessert_price
    desk.order, desk.queue = None, []
    desk.new_order()
    assert desk.ing_stock("cake") == 0 and any("賣完了" in t[0] for t in desk.toasts)
    desk.order, desk.queue = None, []
    desk.new_order()
    assert desk.order.dessert == "", "賣完了不會加購"


def test_no_dessert_without_stock_or_outside_business(desk, unlocked, monkeypatch):
    monkeypatch.setattr(ingredients, "DESSERT_P", 1.0)
    _biz(desk, monkeypatch, {})
    for _ in range(10):
        desk.order, desk.queue = None, []
        desk.new_order()
        assert desk.order.dessert == ""
    assert desk.pick_dessert() is None
    desk.set_order_mode(False)
    desk.stats.data["ing_stock"]["cake"] = 5
    assert desk.start_session("latte", False)
    assert desk.ing_stock("cake") == 5, "手動、自動模式不消耗甜點"


def test_stocked_case_means_more_dine_in(desk, unlocked, monkeypatch):
    monkeypatch.setattr(ingredients, "DESSERT_P", 0.0)

    def to_go_share(stock):
        _biz(desk, monkeypatch, stock)
        random.seed(3)
        n = 0
        for _ in range(300):
            desk.seated = []
            desk.order, desk.queue, desk.ready, desk.pending_deliveries = None, [], [], []
            desk.new_order()
            n += desk.order.to_go
        return n / 300
    empty = to_go_share({})
    stocked = to_go_share({"cake": 5})
    assert empty > 0.3 and stocked < empty - 0.05, (empty, stocked)
    assert ingredients.DESSERT_BUYER_TO_GO_P < ingredients.DESSERT_TO_GO_P < orders.TO_GO_P


def test_auto_restock_dessert(desk, unlocked):
    _earn(desk.stats, 5000)
    desk.set_auto_ing("cake", True)
    assert desk.auto_ing == ["cake"] and desk.cfg.get("auto_buy_ingredients") == ["cake"]
    desk.restock_ingredients()
    assert desk.ing_stock("cake") == ingredients.pack("cake")


def test_store_has_dessert_tab(desk, qapp):
    from cafe_desk.records import RecordsDialog
    _earn(desk.stats, 20000)
    dlg = RecordsDialog(desk, "shop")
    assert dlg.store_sub.tabText(4) == "甜點"
    desk.stats.data["ing_stock"]["muffin"] = 0
    dlg.store_sub.setCurrentIndex(4)
    dlg.buy(desk.buy_ingredient, "muffin")
    assert desk.ing_stock("muffin") == ingredients.pack("muffin")
    assert dlg.store_sub.currentIndex() == 4, "買完留在甜點分頁"


def test_dessert_achievements_and_counts(desk):
    s = desk.stats
    _earn(s, 50000)
    assert not s.unlocked("dessert_full") and s.tier_values()["dessert"] == 0
    for k in ingredients.DESSERTS:                           # 四種都進貨：櫥窗滿滿
        assert desk.buy_ingredient(k)
    assert s.unlocked("dessert_full") and s.data["dessert_bought"]["cake"] == 1
    assert s.data["dessert_spent"] == sum(ingredients.price_of(k) for k in ingredients.DESSERTS)
    for k in ingredients.DESSERTS:                           # 每種賣一個：全制霸
        assert s.record_ing_use(k, 1)
    assert s.data["dessert_sold"] == {k: 1 for k in ingredients.DESSERTS} and s.tier_values()["dessert"] == 4
    assert "dessert_all" in s.check(None, ())
    assert not s.unlocked("dessert_10")
    s.data["dessert_sold"]["croissant"] = 10
    assert "dessert_10" in s.check(None, ())
    assert s.tier_values()["ing"] == 0, "甜點不算食材消耗"
    from cafe_desk.stats import ACHIEVEMENTS, ACH_SECTIONS
    keys = {a[0] for a in ACHIEVEMENTS}
    assert {"dessert_10", "dessert_50", "dessert_200", "dessert_all", "dessert_full"} <= keys
    for a in ACHIEVEMENTS:
        if a[0].startswith("dessert"):
            assert a[1] in EN and a[2] in EN


def test_store_dessert_tab_has_no_purchase_log(desk, qapp):
    """商店「甜點」分頁不再列購買紀錄"""
    from cafe_desk.records import RecordsDialog
    from PySide6.QtWidgets import QLabel
    _earn(desk.stats, 5000)
    desk.buy_ingredient("cake")
    dlg = RecordsDialog(desk, "shop")
    dlg.store_sub.setCurrentIndex(4)
    dlg.refresh_store()
    text = " ".join(lb.text() for lb in dlg.store_sub.currentWidget().widget().findChildren(QLabel))
    assert "購買紀錄" not in text and "進貨一盤" not in text
    dlg.close()


def test_recent_records_merge_dessert_into_its_cup(desk, qapp, monkeypatch):
    """近期紀錄：加購的甜點併進那一杯（品名「飲品 ＋ 甜點」，不另列、不寫甜點價格）；
    新紀錄的杯子本身記了甜點，舊紀錄（沒有 dessert 欄位）用時間對到之後的那杯點單；客人沒取餐退回的不算"""
    from cafe_desk.records import RecordsDialog
    from PySide6.QtWidgets import QLabel
    from cafe_desk import stats as stats_mod
    _earn(desk.stats, 5000)
    desk.buy_ingredient("cake")
    desk.buy_ingredient("cookie")
    clock = iter(f"2026-10-31T10:{m:02d}:00" for m in range(60))
    monkeypatch.setattr(stats_mod, "stamp", lambda: next(clock))
    desk.stats.record_ing_use("cake", 1)                 # 10:00 舊紀錄：杯子沒記甜點
    desk.stats.record({"drink": "latte", "score": 90, "order": True}, [])                      # 10:01
    desk.stats.record({"drink": "americano", "score": 80, "order": True}, [])                  # 10:02（沒加購）
    desk.stats.record_ing_use("cookie", 1)               # 10:03 新紀錄：杯子記了甜點
    desk.stats.record({"drink": "mocha", "score": 85, "order": True, "dessert": "cookie"}, [])  # 10:04
    desk.stats.record_ing_use("cake", 1)                 # 10:05 客人沒取餐
    desk.stats.record_ing_refund("cake", 1)              # 10:06
    desk.stats.record({"drink": "espresso", "score": 88, "order": True}, [])                   # 10:07
    got = [(c["drink"], c.get("dessert")) for c in desk.stats.recent_with_desserts(10)[:4]]
    assert got == [("espresso", None), ("mocha", "cookie"), ("americano", None), ("latte", "cake")]
    dlg = RecordsDialog(desk, None)
    text = " ".join(lb.text() for lb in dlg.findChildren(QLabel))
    assert "拿鐵 ＋ 蛋糕" in text and "摩卡 ＋ 餅乾" in text
    assert money(ingredients.dessert_price("cookie")) not in text
    dlg.close()


def test_book_has_dessert_page(desk, qapp):
    from cafe_desk.records import RecordsDialog
    from PySide6.QtWidgets import QLabel
    dlg = RecordsDialog(desk, "collection")
    names = [dlg.book_sub.tabText(i) for i in range(dlg.book_sub.count())]
    assert "甜點" in names and names.index("甜點") == names.index("食材") + 1
    texts = lambda: " ".join(lb.text() for lb in dlg.book_sub.widget(names.index("甜點")).widget().findChildren(QLabel))
    assert "（0/4）" in texts() and "？？？" in texts()
    dlg.close()
    desk.stats.data["ing_stock"]["cake"] = 3
    assert desk.stats.record_ing_use("cake", 1)
    dlg = RecordsDialog(desk, "collection")
    page = dlg.book_sub.widget(names.index("甜點")).widget()
    t = " ".join(lb.text() for lb in page.findChildren(QLabel))
    assert "（1/4）" in t and "蛋糕" in t and "賣出 1 個" in t
    dlg.close()


def test_walkout_refunds_dessert_and_ingredients(desk, unlocked, monkeypatch):
    """客人等太久離開：下單時扣的食材與加購的甜點退回庫存，賣出量與用掉量減回去（也不算進成就的累計）"""
    _biz(desk, monkeypatch, {"cake": 3})
    monkeypatch.setattr(ingredients, "DESSERT_P", 1.0)
    desk.order, desk.queue = None, []
    before_ing = dict(desk.stats.data["ing_stock"])
    desk.new_order()
    o = desk.order
    assert o.dessert == "cake" and desk.ing_stock("cake") == 2
    assert desk.stats.data["dessert_sold"]["cake"] == 1
    used = ingredients.needs(o.drink, o.mods)
    assert all(desk.ing_stock(k) == before_ing[k] - n for k, n in used.items())
    desk.walk_out(o)
    assert desk.ing_stock("cake") == 3 and desk.stats.data["dessert_sold"].get("cake", 0) == 0
    assert all(desk.ing_stock(k) == before_ing[k] for k in used)
    assert sum(desk.stats.data["ing_used_by"].values()) == 0
    assert o.dessert == "" and o.refunded
    desk.refund_order(o)                                     # 只退一次
    assert desk.ing_stock("cake") == 3


def test_refund_survives_reload(desk, qapp):
    st = desk.stats
    st.data["ing_stock"]["cake"] = 5
    assert st.record_ing_use("cake", 2) and st.record_ing_refund("cake", 2)
    assert st.data["ing_stock"]["cake"] == 5 and st.data["dessert_sold"]["cake"] == 0
    assert not st.record_ing_refund("nothing", 1) and not st.record_ing_refund("cake", 0)
    st.load()
    assert st.data["dessert_sold"].get("cake", 0) == 0 and st.tampered == 0


def test_closing_and_switching_mode_refund_waiting_orders(desk, unlocked, monkeypatch):
    _biz(desk, monkeypatch, {"cake": 3})
    monkeypatch.setattr(ingredients, "DESSERT_P", 1.0)
    desk.order, desk.queue = None, []
    desk.new_order()
    assert desk.ing_stock("cake") == 2
    desk.set_order_mode(False)                               # 打烊／切回練習：還沒做的單中止，庫存退回
    assert desk.ing_stock("cake") == 3 and desk.stats.data["dessert_sold"].get("cake", 0) == 0


def test_every_dessert_has_realistic_art(qapp):
    """每種甜點都有寫實圖（render/dessert_art.py）；圖鑑還沒賣過的是剪影，跟賣過的不一樣"""
    from cafe_desk.render.dessert_art import DESSERT_ART
    from cafe_desk.render.icons import dessert_icon
    assert set(ingredients.DESSERTS) <= set(DESSERT_ART)
    for k in ingredients.DESSERTS:
        a, b = dessert_icon(k, 64).toImage(), dessert_icon(k, 64, ok=False).toImage()
        assert a != b
