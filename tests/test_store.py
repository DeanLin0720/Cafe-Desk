"""商店：錢包、有簽章的購買紀錄、咖啡機升級、精品豆"""
import random

from cafe_desk import beans, stats, store
from cafe_desk.machines import MACHINES
from conftest import run_until_idle


def _earn(st, amount):
    st.record({"drink": "latte", "title": "拿鐵", "score": 90, "comment": "", "order": True, "price": amount,
               "tip": 0}, [])


def test_wallet_and_signed_purchase(cfg_path):
    s = stats.Stats()
    _earn(s, 20000)
    assert store.balance(s) == stats.START_FUNDS + 20000, "初始資金＋累積營業額"
    assert not s.record_purchase("compact_pid", stats.START_FUNDS + 20001), "餘額不夠"
    assert s.record_purchase("allinone_burr", 20000)
    assert store.balance(s) == stats.START_FUNDS and s.data["owned"] == ["allinone_burr"]
    assert s.data["revenue_total"] == 20000, "花錢不影響累積營業額（店鋪等級）"
    s.load()
    assert s.data["spent"] == 20000 and s.data["owned"] == ["allinone_burr"]
    s.db.execute("UPDATE events SET value='allinone_burr:1' WHERE kind='purchase'")   # 想改成只花 $1
    s.db.commit()
    s.load()
    assert s.tampered >= 1 and "allinone_burr" not in s.data["owned"]
    s.db.close()


def test_upgrades_change_traits():
    base = MACHINES["compact"].traits.temp_noise
    store.apply_upgrades(["compact_pid", "desk01_frother"])
    try:
        assert MACHINES["compact"].traits.temp_noise == 0.4
        assert MACHINES["desk01"].traits.frother_q == 0.72
        assert MACHINES["allinone"].traits.channel_add == type(MACHINES["allinone"]).traits.channel_add
        assert store.upgraded("compact", ["compact_pid"]) and not store.upgraded("lever", ["compact_pid"])
    finally:
        store.apply_upgrades([])
    assert MACHINES["compact"].traits.temp_noise == base


def test_buy_upgrade_from_desk(desk, unlocked):
    _earn(desk.stats, 30000)
    desk.set_machine("allinone")
    assert desk.buy_upgrade("allinone_burr")
    assert desk.machine.traits.channel_add == 0.0 and desk.wallet() == stats.START_FUNDS + 10000
    assert not desk.buy_upgrade("allinone_burr"), "買過不能再買"
    assert not desk.buy_upgrade("compact_pid"), "餘額不夠"
    assert desk.machine_actions["allinone"].text().endswith("★")


def test_upgrades_restored_on_start(qapp, cfg_path):
    from cafe_desk.desk import CafeDesk
    s = stats.Stats()
    _earn(s, 20000)
    s.record_purchase("lever_collar", 12000)
    s.db.close()
    store.apply_upgrades([])
    w = CafeDesk()
    try:
        assert MACHINES["lever"].traits.temp_noise == 0.2
    finally:
        w.timer.stop()
        w.stats.db.close()
        w.host.close()
        store.apply_upgrades([])


def test_random_bags_never_premium():
    rnd = random.Random(3)
    assert not any(beans.is_premium(beans.new_bag(None, rnd)) for _ in range(300))
    assert beans.is_premium(beans.new_bag("geisha")) and beans.valid_bag(beans.new_bag("kona"))


def test_buy_beans_and_premium_price(desk):
    w0 = desk.wallet()
    assert desk.buy_beans("bluemountain")
    assert desk.bean_stock("bluemountain") == 1 and desk.bag["origin"] != "bluemountain", "買了放進庫存，不會自動換上"
    assert desk.wallet() == w0 - beans.price_of("bluemountain")
    desk.stats.data["spent"] += desk.wallet() - 100              # 錢包只剩 100
    assert not desk.buy_beans("geisha") and desk.bean_stock("geisha") == 0, "餘額不夠"
    assert desk.request_bag("bluemountain") and desk.bag["origin"] == "bluemountain" and desk.bean_stock() == 0
    desk.set_order_mode(True)
    desk.new_order()
    o = desk.order
    from cafe_desk.orders import price_of
    from cafe_desk.orders import SIZE_PRICE
    assert o.price == round(price_of(o.drink) * beans.PREMIUM_PRICE_K) + SIZE_PRICE[o.size]


def test_store_tab_buy_refreshes(desk):
    from cafe_desk.records import RecordsDialog
    _earn(desk.stats, 20000)
    dlg = RecordsDialog(desk, "shop")
    assert dlg.windowTitle() == "商店" and dlg.tabs.count() == 1
    dlg.buy(desk.buy_upgrade, "desk01_frother")
    assert "desk01_frother" in desk.stats.data["owned"] and dlg.tabs.currentIndex() == 0
    dlg.grab()
    dlg.close()
    store.apply_upgrades([])


def test_reset_progress(desk, tmp_path):
    """重新遊玩：紀錄、成就、等級、錢包、升級、清潔計數、豆子、冰滴歸零；參數與音樂清單保留"""
    from cafe_desk import config
    _earn(desk.stats, 30000)
    desk.buy_upgrade("compact_pid")
    assert desk.buy_beans("kenya") and desk.bean_stock("kenya") == 1
    desk.maint["backflush"] = 20
    desk.params.grind_um = 260.0
    desk.music.add([str(tmp_path / "a.mp3")])
    desk.set_order_mode(True)
    desk.new_order()
    assert desk.stats.data["total"] == 1 and desk.stats.unlocked("first_cup")
    assert desk.reset_progress()
    st = desk.stats.data
    assert st["total"] == 0 and st["revenue_total"] == 0 and st["spent"] == 0 and not st["achievements"]
    assert desk.wallet() == stats.START_FUNDS and desk.shop_level() == 1 and MACHINES["compact"].traits.temp_noise == 1.4
    assert desk.bean_stock() == 0
    assert all(v["backflush"] == 0 for v in desk.maint_all.values())
    assert not desk.order_mode and desk.order is None and desk.report_card is None, "直接關營業，不出日報"
    assert desk.bag["origin"] == "house" and desk.bag["left"] == beans.BAG_G and desk.cold is None
    assert desk.params.grind_um == 260.0 and len(desk.music.files) == 1
    cfg = config.load()
    assert cfg["growth_seen"] == {"level": 1, "rank": 0} and cfg["order_no"] == 0
    desk.stats.load()
    assert desk.stats.data["total"] == 0, "資料庫真的清空了"


def test_reset_refused_while_busy(desk):
    assert desk.start_session("espresso", False)
    assert not desk.reset_progress()


def test_about_has_reset_button(desk):
    from PySide6.QtWidgets import QPushButton
    desk.open_about()
    labels = [b.text() for b in desk.about_dlg.findChildren(QPushButton)]
    assert "重新遊玩…" in labels
    desk.about_dlg.close()


def test_reset_toast_is_not_achievement_style(desk):
    """重新遊玩的通知是一般樣式（沒有獎盃）；成就、店鋪升級才用獎盃樣式"""
    assert desk.reset_progress()
    assert desk.toasts[-1][3] == "info"
    desk.announce(["first_cup"])
    assert desk.toasts[-1][3] == "trophy"
    desk.toasts[0] = (desk.toasts[0][0], 0.0, 10 ** 9, "info")
    desk.host.grab()


def test_grinder_upgrades():
    """平刀盤：三台用獨立磨豆機的咖啡機通道效應都降低（一體機不受影響）；鬼齒刀盤：沖煮台更乾淨、更甜"""
    from cafe_desk import brew
    from cafe_desk.drinks import DrinkParams
    base = {k: m.traits.channel_add for k, m in MACHINES.items()}
    before = brew.simulate_pourover(DrinkParams(), "中焙", 10, "house").score
    store.apply_upgrades(["grinder_flat", "station_ghost"])
    try:
        for k in store.EXTERNAL:
            assert MACHINES[k].traits.channel_add == base[k] - 0.04
        assert MACHINES["allinone"].traits.channel_add == base["allinone"]
        assert brew.FINES_K < 1 and brew.CLARITY > 0
        assert brew.simulate_pourover(DrinkParams(), "中焙", 10, "house").score > before + 2
        assert store.upgrade_names("lever", ["grinder_flat"]) == ["平刀盤"]
        assert store.target_name("station_ghost") == "手沖用磨豆機"
    finally:
        store.apply_upgrades([])
    assert brew.FINES_K == 1.0 and brew.CLARITY == 0.0


def test_station_grinder_needs_pourover(desk):
    """鬼齒刀盤要先解鎖手沖（Lv.2）才能買；平刀盤 Lv.1 就能買（DESK·01 用獨立磨豆機）"""
    _earn(desk.stats, 2000)                                   # 還在 Lv.1
    assert not desk.upgrade_open("station_ghost") and desk.upgrade_open("grinder_flat")
    _earn(desk.stats, 30000)
    assert desk.buy_upgrade("station_ghost") and desk.buy_upgrade("grinder_flat")
    assert desk.machine_actions["desk01"].text().endswith("★")


def test_beans_swap_after_current_drink(desk):
    """營業中（咖啡師在忙）開新豆子：這杯做完才換；庫存沒有的不能開；排好的可以被別種蓋掉"""
    assert desk.buy_beans("kona") and desk.buy_beans("kenya")
    assert desk.start_session("espresso", False)
    assert desk.request_bag("kona")
    assert desk.bag["origin"] != "kona" and desk.pending_bag == "kona" and desk.bean_stock("kona") == 1, "還沒開，庫存沒動"
    assert not desk.request_bag("geisha") and desk.pending_bag == "kona", "庫存沒有"
    run_until_idle(desk)
    desk.step(0.05, 0.05)
    assert desk.bag["origin"] == "kona" and desk.pending_bag is None and desk.bean_stock("kona") == 0
    assert desk.start_session("espresso", False)
    assert desk.request_bag("kenya") and desk.pending_bag == "kenya"
    run_until_idle(desk)
    desk.step(0.05, 0.05)
    assert desk.bag["origin"] == "kenya" and desk.bean_stock() == 0


def test_beans_open_now_when_idle(desk):
    assert desk.buy_beans("bluemountain") and desk.bean_stock("bluemountain") == 1
    assert desk.request_bag("bluemountain") and desk.bag["origin"] == "bluemountain" and desk.pending_bag is None
    assert desk.bean_stock("bluemountain") == 0


def test_bean_stock_is_signed_and_reloaded(desk):
    w0 = desk.wallet()
    assert desk.buy_beans("kenya") and desk.buy_beans("kenya") and desk.buy_beans("house")
    assert desk.bean_stock() == 3 and desk.wallet() == w0 - 2 * beans.price_of("kenya") - beans.price_of("house")
    assert desk.request_bag(None) and desk.bean_stock() == 2, "從庫存隨機開一包"
    desk.stats.load()
    assert desk.bean_stock() == 2 and desk.stats.tampered == 0
    desk.stats.db.execute("UPDATE events SET value='kenya:1' WHERE kind='bean_buy' AND value LIKE 'kenya:%'")   # 想改成只花 $1
    desk.stats.db.commit()
    desk.stats.load()
    assert desk.stats.tampered >= 1


def test_every_bean_has_a_price():
    for k in beans.ORIGINS:
        assert beans.price_of(k) > 0
    assert all(beans.price_of(k) < beans.price_of(p) for k in beans.REGULAR for p in beans.PREMIUM)


def test_no_beans_means_no_business(desk):
    """沒庫存、這包也用完：營業中咖啡師不接單、提醒去商店；買了豆子才動起來"""
    from cafe_desk.orders import Order
    desk.set_order_mode(True)
    desk.arrive_in = 1e9
    desk.bag["left"] = 3
    assert desk.out_of_beans()
    o = Order(1, "Amy", "espresso", [], price=70, patience=999)
    o.paid = True
    desk.order = o
    for _ in range(80):
        desk.step(0.05, 0.05)
    assert o.state == "waiting" and desk.session is None, "沒豆子：客人乾等"
    assert any("豆子用完" in t[0] for t in desk.toasts)
    assert desk.buy_beans("house")
    assert not desk.out_of_beans()
    for _ in range(800):
        desk.step(0.05, 0.05)
        if o.state != "waiting":
            break
    assert o.state != "waiting" and desk.bean_stock() == 0 and desk.bag["origin"] == "house" and desk.bag["left"] > 200


def test_premium_customer_asks_for_a_bean(desk):
    """約一成客人指定精品豆：店裡用的不一樣就扣符合度，一樣就滿分；他付精品豆的價錢"""
    import random as _r
    from cafe_desk import orders
    from cafe_desk.orders import Order, price_of
    o = orders.make_order(1, _r.Random(1), bean_p=1.0)
    assert o.has("bean") in beans.PREMIUM and len(o.mods) <= 2
    hits = sum(1 for i in range(400) if orders.make_order(1, _r.Random(i), bean_p=orders.BEAN_ASK_P).has("bean"))
    assert 15 < hits < 70
    assert not orders.make_order(1, _r.Random(2)).has("bean"), "一般點單不會指定豆子"
    sess = type("S", (), {"milk": None, "app": desk})()
    want = Order(1, "Amy", "espresso", [("bean", "geisha")], price=70)
    assert desk.bag["origin"] == "house"
    m, complaint = orders.evaluate(want, sess)
    assert m == 0.0 and complaint
    desk.bag["origin"] = "geisha"
    m, complaint = orders.evaluate(want, sess)
    assert m == 100.0 and not complaint
    desk.bag["origin"] = "house"
    desk.set_order_mode(True)
    desk.order, desk.queue = None, []
    desk.arrive_in = 1e9
    old, orders.BEAN_ASK_P = orders.BEAN_ASK_P, 1.0
    try:
        assert desk.bean_choices() == [], "右下櫥窗沒有精品豆：客人不會指定"
        desk.new_order()
        assert not desk.order.has("bean")
        desk.order, desk.queue = None, []
        desk.stats.data["bean_stock"]["kona"] = 1             # 櫥窗擺出一包可娜：客人只會點它
        assert desk.bean_choices() == ["kona"]
        desk.new_order()
    finally:
        orders.BEAN_ASK_P = old
    got = desk.order
    assert got.has("bean") == "kona" and got.price == round(price_of(got.drink) * beans.PREMIUM_PRICE_K) + orders.SIZE_PRICE[got.size]


def test_starting_funds(desk):
    assert stats.START_FUNDS == 5000 and desk.wallet() == 5000
    assert desk.stats.data["revenue_total"] == 0 and desk.shop_level() == 1, "初始資金不算營業額、不算店鋪等級"
    desk.stats.data["spent"] += 4500
    assert desk.wallet() == 500 and not desk.buy_beans("geisha"), "錢包就是這樣用掉的"


def test_bean_menu_lists_stock(desk):
    desk.fill_bean_menu()
    texts = [a.text() for a in desk.bean_menu.actions()]
    assert any("庫存 0" in t for t in texts)
    desk.buy_beans("kenya")
    desk.fill_bean_menu()
    sub = next(a for a in desk.bean_menu.actions() if a.menu() is not None).menu()
    enabled = [a.text() for a in sub.actions() if a.isEnabled()]
    assert len(enabled) == 1 and "庫存 1" in enabled[0]


def test_pending_bag_survives_restart(qapp, cfg_path):
    """還沒換上就關程式：下次開啟還排著，有庫存才會換上（不會憑空多一包）"""
    import json
    with open(cfg_path, "w", encoding="utf-8") as f:
        json.dump({"schema": 3, "pending_bag": "geisha"}, f)
    from cafe_desk.desk import CafeDesk
    w = CafeDesk()
    try:
        assert w.bag["origin"] == "house" and w.pending_bag == "geisha"
        w.step(0.05, 0.05)
        assert w.bag["origin"] == "house", "沒庫存：不會換上"
        assert w.buy_beans("geisha")
        w.step(0.05, 0.05)
        assert w.bag["origin"] == "geisha" and w.pending_bag is None and w.bean_stock() == 0
    finally:
        w.timer.stop()
        w.stats.db.close()
        w.host.close()



def test_duo_upgrades_stack():
    """雙頭機的四項升級疊加：通道效應兩項相加，其他照設定"""
    from cafe_desk.machines import MACHINES
    base = type(MACHINES["duo"]).traits
    try:
        store.apply_upgrades(["duo_burr", "duo_steam", "duo_preinfuse", "duo_boiler"])
        t = MACHINES["duo"].traits
        assert abs(t.channel_add - (base.channel_add - 0.06)) < 1e-9
        assert t.steam_power == 1.9 and t.sweet_add == 0.3 and t.boiler_heat == 1.0 and t.boiler_draw == 0.05
        assert MACHINES["allinone"].traits == type(MACHINES["allinone"]).traits, "只改雙頭機"
    finally:
        store.apply_upgrades([])


def test_auto_buy_keeps_one_in_stock(desk):
    """自動購買：勾選就先買一包放著，開走一包馬上補一包；沒勾選的不會買"""
    desk.auto = False
    desk.bag["left"] = 3
    assert desk.start_session("espresso", False) is False, "沒勾選：照舊沒豆子"
    assert desk.bean_stock() == 0
    w0 = desk.wallet()
    desk.set_auto_buy("kenya", True)
    assert desk.bean_stock("kenya") == 1 and w0 - desk.wallet() == beans.price_of("kenya"), "勾選就買一包放著"
    desk.set_auto_buy("kenya", True)
    assert desk.bean_stock("kenya") == 1, "已經有庫存不重複買"
    assert desk.start_session("espresso", False)
    assert desk.bag["origin"] == "kenya" and desk.bean_stock("kenya") == 1, "開走一包，馬上補一包"
    assert any("自動購買" in t[0] for t in desk.toasts)
    run_until_idle(desk)
    desk.set_auto_buy("house", True)
    desk.save_config()
    assert sorted(desk.cfg["auto_buy_beans"]) == ["house", "kenya"]


def test_auto_buy_needs_money(desk):
    desk.stats.data["spent"] += desk.wallet() - 100                # 錢包只剩 100：買不起
    desk.set_auto_buy("kenya", True)
    assert desk.bean_stock() == 0, "買不起就不買"
    desk.bag["left"] = 3
    assert not desk.open_bag(None) and desk.out_of_beans()
    desk.stats.data["spent"] -= 1000                                # 有錢了
    assert not desk.out_of_beans(), "買得起：不算沒豆子"
    assert desk.open_bag(None) and desk.bag["origin"] == "kenya"


def test_auto_buy_keeps_business_running(desk):
    """營業中沒庫存也沒關係：自動購買讓咖啡師繼續接單"""
    from cafe_desk.orders import Order
    desk.set_order_mode(True)
    desk.arrive_in = 1e9
    desk.bag["left"] = 3
    desk.set_auto_buy("house", True)
    o = Order(1, "Amy", "espresso", [], price=70, patience=999)
    o.paid = True
    desk.order = o
    for _ in range(800):
        desk.step(0.05, 0.05)
        if o.state != "waiting":
            break
    assert o.state != "waiting" and desk.bag["origin"] == "house" and desk.bag["left"] > 200


def test_auto_buy_menu_and_restart(qapp, cfg_path):
    import json
    with open(cfg_path, "w", encoding="utf-8") as f:
        json.dump({"schema": 3, "auto_buy_beans": ["geisha", "nonsense"]}, f)
    from cafe_desk.desk import CafeDesk
    w = CafeDesk()
    try:
        assert w.auto_buy == ["geisha"], "讀檔時忽略不存在的豆子"
        w.fill_bean_menu()
        assert not any(a.menu() is not None and "自動購買" in a.text() for a in w.bean_menu.actions()), "自動購買改在商店"
        from cafe_desk.records import RecordsDialog
        from PySide6.QtWidgets import QCheckBox
        dlg = RecordsDialog(w, "shop")
        dlg.store_sub.setCurrentIndex(2)
        boxes = dlg.store_sub.currentWidget().findChildren(QCheckBox)
        assert sum(c.isChecked() for c in boxes) == 1
        next(c for c in boxes if not c.isChecked()).setChecked(True)
        assert len(w.auto_buy) == 2 and "geisha" in w.auto_buy
        dlg.close()
    finally:
        w.timer.stop()
        w.stats.db.close()
        w.host.close()


def test_store_has_subtabs_and_keeps_place(desk):
    """商店分成設備升級／店面裝潢／咖啡豆三個分頁；買東西後重畫，停在原本的分頁"""
    from cafe_desk.records import RecordsDialog
    _earn(desk.stats, 20000)
    dlg = RecordsDialog(desk, "shop")
    assert dlg.store_sub.count() == 5
    dlg.store_sub.setCurrentIndex(2)                       # 咖啡豆
    dlg.buy(desk.buy_beans, "kenya")
    assert desk.bean_stock("kenya") == 1 and dlg.store_sub.currentIndex() == 2
    dlg.store_sub.setCurrentIndex(1)                       # 店面裝潢
    dlg.buy(desk.buy_decor, "tile")
    assert dlg.store_sub.currentIndex() == 1
    dlg.grab()
    dlg.close()


def test_back_gear_follows_unlocks_and_setting(desk):
    """櫃檯畫面 POS 後方只擺解鎖了、沒被右鍵關掉的沖煮設備"""
    from cafe_desk import growth
    assert desk.back_gear_shown() == [k for k in ("pourover", "colddrip", "moka", "siphon") if desk.method_open(k)]
    old = dict(growth.METHOD_LEVEL)
    try:
        for k in growth.METHOD_LEVEL:
            growth.METHOD_LEVEL[k] = 1
        assert desk.back_gear_shown() == ["pourover", "colddrip", "moka", "siphon"]
        desk.set_back_gear("colddrip", False)
        assert "colddrip" not in desk.back_gear_shown() and desk.cfg["back_gear_off"] == ["colddrip"]
        desk.set_back_gear("colddrip", True)
        assert "colddrip" in desk.back_gear_shown()
        desk.set_machine("duo")
        desk.set_order_mode(True)
        desk.counter_view = True
        desk.host.grab()                                   # 畫得出來（含手沖磨豆機）
        assert set(desk.back_gear_images(desk.back_gear_shown())) >= {"pourover", "grinder", "colddrip", "moka", "siphon"}
    finally:
        growth.METHOD_LEVEL.update(old)


def test_bean_window_shows_stock(desk, qapp):
    """前板右下的展示窗：有庫存的豆子加上正在開的那包；畫得出來"""
    assert [k for k, _n, _c in desk.bean_window_items()] == ["house"], "只有開局免費那包"
    desk.stats.data["bean_stock"].update({"kenya": 2, "geisha": 1})
    items = desk.bean_window_items()
    assert {k for k, _n, _c in items} == {"house", "kenya", "geisha"} and dict((k, c) for k, _n, c in items)["house"]
    for k in beans.ORIGINS:
        desk.stats.data["bean_stock"][k] = 1
    assert len(desk.bean_window_items()) <= 10
    desk.set_order_mode(True)
    desk.counter_view = True
    desk.host.grab()


def test_switching_beans_keeps_the_rest_on_the_shelf(desk):
    """換豆子不浪費：開過還有剩的收起來，之後換回來接著用，不用再開新包"""
    desk.stats.data["bean_stock"].update({"kenya": 2, "brazil": 1})
    assert desk.open_bag("kenya")
    desk.bag["left"] = 120.0
    assert desk.open_bag("brazil")
    assert desk.shelf["kenya"]["left"] == 120.0 and desk.bean_stock("kenya") == 1, "剩的收進櫃子"
    desk.bag["left"] = 100.0
    assert desk.request_bag("kenya") and desk.bag["origin"] == "kenya" and desk.bag["left"] == 120.0
    assert desk.bean_stock("kenya") == 1, "換回已開的不花庫存"
    assert desk.shelf["brazil"]["left"] == 100.0 and "kenya" not in desk.shelf
    assert "kenya" not in desk.shelf
    desk.save_config()
    assert desk.cfg["bean_shelf"]["brazil"]["left"] == 100.0
    desk.bag["left"] = 5.0                                  # 太少的不留
    assert desk.open_bag("brazil") and "kenya" not in desk.shelf
    desk.bag["left"] = 10.0
    desk.stats.data["bean_stock"]["kenya"] = 1
    desk.request_bag("kenya")
    assert "brazil" not in desk.shelf or desk.shelf["brazil"]["left"] >= 21.0
    desk.fill_bean_menu()
    assert any("已開" in a.text() for m in desk.bean_menu.actions() if m.menu() for a in m.menu().actions()) or not desk.shelf


def test_business_resumes_shelf_beans_when_stock_is_empty(desk, unlocked):
    """庫存沒有了、目前這包也不夠：營業中咖啡師把開過還有剩的豆子倒回來用（不能卡住每個 tick 重試）"""
    desk.stats.data["bean_stock"].update({k: 0 for k in desk.stats.data["bean_stock"]})
    desk.shelf = {"kenya": {**beans.new_bag("kenya"), "left": 100.0}}
    desk.bag["left"] = 5.0
    assert desk.open_next_bag() and desk.bag["origin"] == "kenya" and desk.bag["left"] == 100.0
    assert desk.shelf == {} or "kenya" not in desk.shelf
