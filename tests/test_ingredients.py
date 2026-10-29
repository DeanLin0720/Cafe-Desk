"""食材：營業中每杯要用食材、庫存不夠客人就不點；商店買、自動補貨"""
import random

from cafe_desk import ingredients, orders, stats
from cafe_desk.drinks import DRINKS
from cafe_desk.i18n import EN


def _earn(st, amount):
    st.record({"drink": "latte", "title": "拿鐵", "score": 90, "comment": "", "order": True, "price": amount,
               "tip": 0}, [])


def test_texts_translated_and_every_ingredient_used():
    for key, (name, per, price, desc) in ingredients.ITEMS.items():
        assert name in EN and desc in EN and per > 0 and price > 0, key
    used = {k for d in DRINKS for k in ingredients.needs(d)} | {"oat", "soy", "almond"}
    assert used == set(ingredients.ITEMS), "每一種食材都有飲品用到"
    assert set(ingredients.START_STOCK) <= set(ingredients.ITEMS)


def test_needs_per_drink():
    n = ingredients.needs
    assert n("espresso") == {} and n("americano") == {} and n("pour_over") == {}, "只用咖啡豆與水的飲品不用食材"
    assert n("latte") == {"milk": 1} and n("iced_latte") == {"milk": 1}
    assert n("latte", [("milk", "oat")]) == {"oat": 1}, "換植物奶就用植物奶、不用鮮奶"
    assert n("mocha") == {"milk": 1, "choc": 1, "cream": 1, "cocoa": 1}
    assert n("mocha", [("whip", "no")]) == {"milk": 1, "choc": 1}, "不要鮮奶油也沒有可可粉"
    assert n("cappuccino") == {"milk": 1, "cocoa": 1} and n("cappuccino", [("cocoa", "no")]) == {"milk": 1}
    assert n("caramel_macchiato") == {"milk": 1, "vanilla": 1, "caramel": 1}
    assert n("affogato") == {"icecream": 1} and n("affogato", [("scoop", "big")]) == {"icecream": 2}
    assert n("espresso_tonic") == {"tonic": 1}
    assert n("pumpkin_latte") == {"milk": 1, "pumpkin": 1, "cream": 1, "cinnamon": 1}
    assert n("rose_latte") == {"milk": 1, "rose": 1}
    assert ingredients.available("latte", {"milk": 1}) and not ingredients.available("latte", {"milk": 0})


def test_signed_buy_and_use_survive_reload(cfg_path):
    s = stats.Stats()
    assert s.data["ing_stock"] == ingredients.START_STOCK, "開局送的庫存"
    w0 = s.wallet()
    assert s.record_ing_buy("oat") and s.wallet() == w0 - ingredients.price_of("oat")
    assert s.data["ing_stock"]["oat"] == ingredients.pack("oat")
    assert s.record_ing_use("oat", 3) and s.data["ing_stock"]["oat"] == ingredients.pack("oat") - 3
    assert not s.record_ing_use("rose") and not s.record_ing_use("milk", 99), "庫存不夠不能扣"
    assert not s.record_ing_buy("nonsense")
    spent, stock = s.data["spent"], dict(s.data["ing_stock"])
    s.load()                                                   # 重讀資料庫：一樣
    assert s.data["spent"] == spent and s.data["ing_stock"] == stock


def test_business_orders_follow_stock(desk, unlocked):
    desk.set_order_mode(True)
    desk.arrive_in = 1e9
    desk.stats.data["ing_stock"].update({k: 0 for k in ingredients.ITEMS})
    ex = desk.order_exclude()
    assert "latte" in ex and "mocha" in ex and "affogato" in ex and "espresso" not in ex and "americano" not in ex
    for i in range(60):                                         # 沒有任何食材：只會點不用食材的飲品
        desk.order, desk.queue = None, []
        desk.new_order()
        assert not ingredients.needs(desk.order.drink, desk.order.mods), desk.order.drink
    desk.stats.data["ing_stock"]["milk"] = 3
    assert "latte" not in desk.order_exclude() and "mocha" in desk.order_exclude(), "有鮮奶但沒巧克力醬"
    desk.set_order_mode(False)
    assert "latte" not in desk.order_exclude(), "手動、自動模式不看食材"


def test_new_order_uses_ingredients_and_warns(desk, unlocked, monkeypatch):
    desk.set_order_mode(True)
    desk.arrive_in = 1e9
    desk.stats.data["ing_stock"].update({k: 0 for k in ingredients.ITEMS})
    desk.stats.data["ing_stock"]["milk"] = 1
    monkeypatch.setattr(orders, "mod_pool", lambda drink: [])
    monkeypatch.setattr(orders, "PARTY_SIZES", ((1, 1.0),))
    for _ in range(40):
        desk.order, desk.queue = None, []
        desk.new_order()
        if ingredients.needs(desk.order.drink, desk.order.mods):
            break
    else:
        raise AssertionError("有鮮奶時應該會有人點奶類飲品")
    assert ingredients.needs(desk.order.drink, desk.order.mods) == {"milk": 1}
    assert desk.ing_stock("milk") == 0, "點單時就扣掉"
    assert any("用完了" in t[0] for t in desk.toasts), "用完的那樣提醒"
    sig = desk.stats.db.execute("SELECT COUNT(*) FROM events WHERE kind='ing_use'").fetchone()[0]
    assert sig == 1


def test_manual_mode_does_not_use_ingredients(desk):
    before = dict(desk.stats.data["ing_stock"])
    assert desk.start_session("latte", False)
    assert desk.stats.data["ing_stock"] == before


def test_plant_milk_request_needs_that_milk():
    rnd = random.Random(1)
    stock = {k: 0 for k in ingredients.ITEMS}
    stock["milk"] = 50
    seen = set()
    for i in range(300):
        o = orders.make_order(1, random.Random(i), exclude=tuple(d for d in DRINKS if not ingredients.available(d, stock)),
                              avail=lambda d, m: ingredients.available(d, stock, m))
        seen.add(o.has("milk"))
    assert not ({"oat", "soy", "almond"} & seen), "沒有植物奶庫存，客人不會要求換"
    stock["oat"] = 5
    assert any(orders.make_order(1, random.Random(i), exclude=(), avail=lambda d, m: ingredients.available(d, stock, m)).has("milk") == "oat"
               for i in range(300))


def test_auto_restock(desk, unlocked):
    desk.set_order_mode(True)
    desk.arrive_in = 1e9
    _earn(desk.stats, 5000)
    desk.stats.data["ing_stock"]["milk"] = 0
    w = desk.wallet()
    desk.set_auto_ing("milk", True)
    assert desk.auto_ing == ["milk"] and desk.cfg.get("auto_buy_ingredients") == ["milk"]
    assert desk.ing_stock("milk") == ingredients.pack("milk") and desk.wallet() == w - ingredients.price_of("milk"), "勾選就先買一包"
    desk.restock_ingredients()
    assert desk.ing_stock("milk") == ingredients.pack("milk"), "還有庫存就不買"
    desk.stats.data["ing_stock"]["milk"] = 0
    desk.stats.data["spent"] = desk.stats.data["revenue_total"] + stats.START_FUNDS      # 沒錢
    desk.restock_ingredients()
    assert desk.ing_stock("milk") == 0 and any("自動補貨" in t[0] for t in desk.toasts)
    desk.set_auto_ing("milk", False)
    assert desk.auto_ing == []


def test_store_tab_and_menu(desk, qapp):
    from cafe_desk.records import RecordsDialog
    _earn(desk.stats, 20000)
    dlg = RecordsDialog(desk, "ingredients")
    assert dlg.windowTitle() == "商店" and dlg.store_sub.currentIndex() == 3
    w = desk.wallet()
    dlg.buy(desk.buy_ingredient, "oat")
    assert desk.ing_stock("oat") == ingredients.pack("oat") and desk.wallet() == w - ingredients.price_of("oat")
    assert dlg.store_sub.currentIndex() == 3, "買完留在食材分頁"
    dlg.grab()
    dlg.close()
    desk.fill_ing_menu()
    texts = [a.text() for a in desk.ing_menu.actions()]
    assert any("燕麥奶" in t and str(ingredients.pack("oat")) in t for t in texts)
    from cafe_desk.render.icons import ingredient_icon
    for k in ingredients.ITEMS:
        assert not ingredient_icon(k, 64, 1.0).isNull()


def test_reset_progress_restores_start_stock(desk):
    desk.stats.record_ing_use("milk", 2)
    assert desk.reset_progress()
    assert desk.stats.data["ing_stock"] == ingredients.START_STOCK


def test_consumption_achievements(cfg_path):
    s = stats.Stats()
    for _ in range(9):
        s.record_bag("kenya")
    assert not s.unlocked("bags_10")
    assert "bags_10" in s.record_bag("kenya") and not s.unlocked("bags_50")
    for _ in range(40):
        s.record_bag("kenya")
    assert s.unlocked("bags_50") and s.tier_values()["bags"] == 50, "第 50 包開的時候就解鎖"
    assert stats.TIER_OF["bags_150"] == ("bags", 2) and stats.TIER_OF["ing_500"] == ("ing", 2)

    def use(key, n):
        s.data["ing_stock"][key] = max(s.data["ing_stock"].get(key, 0), n)       # 補到夠用
        assert s.record_ing_use(key, n)
    use("milk", 29)
    assert not s.unlocked("ing_30")
    use("milk", 1)
    assert "ing_30" in s.check(None, ()) and s.tier_values()["ing"] == 30
    assert not s.unlocked("ing_all")
    for k in ingredients.COMMON:
        use(k, 1)
    assert "ing_all" in s.check(None, ()), "每一種常態食材都用過"
    s.load()                                                   # 重讀資料庫：累計與成就一樣
    assert s.tier_values()["ing"] == 30 + len(ingredients.COMMON) and s.unlocked("ing_all")


def test_new_order_announces_consumption_achievement(desk, unlocked):
    desk.set_order_mode(True)
    desk.arrive_in = 1e9
    desk.stats.data["ing_used_by"]["milk"] = 29                 # 差一份就 30
    desk.stats.data["ing_stock"]["milk"] = 8
    for _ in range(40):
        desk.order, desk.queue = None, []
        desk.new_order()
        if desk.stats.unlocked("ing_30"):
            break
    assert desk.stats.unlocked("ing_30"), "點了奶類飲品用掉一份：解鎖"
    assert any("備料新手" in t[0] for t in desk.toasts)


def test_book_has_subtabs_with_ingredients(desk, qapp):
    from cafe_desk.records import RecordsDialog
    from PySide6.QtWidgets import QLabel
    dlg = RecordsDialog(desk)
    names = [dlg.book_sub.tabText(i) for i in range(dlg.book_sub.count())]
    assert names == ["飲品", "設備", "牛奶", "豆子", "食材", "甜點", "店面裝潢"]
    page = dlg.book_sub.widget(names.index("食材"))
    texts = [lab.text() for lab in page.findChildren(QLabel)]
    total = len(ingredients.ITEMS)
    assert any(f"（0/{total}）" in t for t in texts) and sum(1 for t in texts if t == "？？？") == total, "還沒用過的是問號"
    desk.stats.record_ing_use("milk", 3)
    dlg2 = RecordsDialog(desk)
    page = dlg2.book_sub.widget(names.index("食材"))
    texts = [lab.text() for lab in page.findChildren(QLabel)]
    assert any(f"（1/{total}）" in t for t in texts) and "鮮奶" in texts and any("用掉 3 份" in t for t in texts)
    tips = [w.toolTip() for w in page.findChildren(QLabel)] + [w.toolTip() for w in page.findChildren(type(page.widget()))]
    assert any("用在" in t and "熱拿鐵" in t for t in tips)
    dlg.close()
    dlg2.close()


def test_rack_items_leave_the_shelf_while_in_use(desk, unlocked):
    """做飲品要用的配料從配料架上拿走：鮮奶油槍、可可粉篩網、醬料擠瓶、通寧水；用完放回去"""
    from cafe_desk import drinks
    from cafe_desk.render import shop
    desk.set_order_mode(True)
    assert desk.rack_in_use() == set()
    assert desk.start_session("mocha", False)
    seen = set()
    for _ in range(4000):
        desk.step(0.05, 0.05)
        seen |= desk.rack_in_use()
        if not desk.busy() and not desk.session:
            break
    assert {"choc", "cream", "cocoa"} <= seen, seen
    assert seen <= set(shop.RACK_KINDS)
    desk.counter_view = False
    desk.host.grab()                                            # 畫得出來
