"""顧客點單：訂單產生、依訂單改參數、符合度與最後分數"""
import random
from types import SimpleNamespace

import pytest

from cafe_desk import orders
from cafe_desk.drinks import DRINKS, DrinkParams, DrinkResult
from cafe_desk.orders import Order, make_order, order_params, evaluate, finish, mod_pool, MOD_TEXT

from conftest import run_until_idle


def _session(temp=60, foam=30, art="heart", note=""):
    return SimpleNamespace(milk=SimpleNamespace(temp=temp, foam=foam, art=art, art_note=note))


def test_make_order_is_valid():
    rnd = random.Random(5)
    for no in range(300):
        o = make_order(no, rnd)
        assert o.drink in DRINKS
        assert len(o.mods) <= 2
        kinds = [k for k, _ in o.mods]
        assert len(kinds) == len(set(kinds)), "同一類要求只能有一個"
        for m in o.mods:
            assert m in MOD_TEXT
            assert m in mod_pool(o.drink)


def test_no_festival_drink_out_of_season():
    rnd = random.Random(1)
    assert all(not DRINKS[make_order(i, rnd).drink].get("festival") for i in range(300))


def test_order_params_follow_mods():
    rnd = random.Random(0)
    dp = DrinkParams()
    o = Order(1, "Amy", "latte", [("temp", "low"), ("milk", "oat")])
    temps = [order_params(o, dp, rnd).milk_temp for _ in range(200)]
    assert 50 < sum(temps) / len(temps) < 58               # 54 度附近，有手感誤差
    assert order_params(o, dp, rnd).milk_kind == "oat"
    assert dp.milk_temp == 60.0 and dp.milk_kind == "dairy", "不能改到使用者的設定"
    d = order_params(Order(2, "Ken", "affogato", [("scoop", "big")]), dp, rnd)
    assert d.scoop_g == 95.0
    d = order_params(Order(3, "Joe", "iced_latte", [("ice", "less")]), dp, rnd)
    assert d.ice == 2.0


def test_evaluate_match():
    o = Order(1, "Amy", "latte", [("temp", "low")])
    assert evaluate(o, _session(temp=56)) == (100.0, "")
    match, complaint = evaluate(o, _session(temp=68))
    assert match < 80 and complaint == "有點燙"

    o = Order(1, "Amy", "latte", [("art", "rosetta")])
    assert evaluate(o, _session(art="rosetta"))[0] == 100
    assert evaluate(o, _session(art="rosetta", note="糊"))[0] == 50
    assert evaluate(o, _session(art="heart"))[0] == 0

    assert evaluate(Order(1, "Amy", "espresso", []), SimpleNamespace(milk=None))[0] == 100


def test_finish_combines_scores():
    o = Order(1, "Amy", "latte", [("art", "heart")])
    finish(o, _session(art="tulip"), DrinkResult("latte", 90.0, ""))
    assert o.match == 0
    assert o.score == pytest.approx(orders.ORDER_WEIGHT_DRINK * 90)
    assert o.state == "done" and o.reaction and o.complaint


def test_order_flow_in_desk(desk):
    desk.order_mode = True
    desk.auto = True
    for _ in range(3):
        desk.order = None
        desk.new_order()
        o = desk.order
        desk.make_order()
        run_until_idle(desk)
        assert o.state in ("done", "leaving")
        assert 0 <= o.score <= 100 and o.reaction


def test_prices_cover_every_drink():
    for k in DRINKS:
        assert 50 <= orders.price_of(k) <= 200
    assert make_order(1, random.Random(2)).price == orders.price_of(make_order(1, random.Random(2)).drink)


def test_wait_penalty_and_tip():
    o = Order(1, "Amy", "latte", [], price=120, patience=200)
    o.wait = 90
    assert orders.wait_penalty(o) == 0                  # 一半以內不扣
    o.wait = 150
    assert orders.wait_penalty(o) == pytest.approx(orders.WAIT_PENALTY / 2)
    o.wait = 300
    assert orders.wait_penalty(o) == orders.WAIT_PENALTY
    assert orders.wait_penalty(Order(1, "Amy", "latte", [], wait=999)) == 0, "一般點單不限時間"
    finish(o, _session(), DrinkResult("latte", 100.0, ""))
    assert o.score == pytest.approx(100 - orders.WAIT_PENALTY) and o.complaint == "等有點久"
    assert o.tip == 12 and o.revenue == 132              # 85 分：10% 小費


def test_business_queue_and_walkout(desk, unlocked, monkeypatch):
    monkeypatch.setattr(orders, "party_size", lambda rnd=None: 1)   # 一杯一張單：做完、結帳就記營業額
    desk.auto = True
    desk.set_order_mode(True)
    assert desk.business()
    random.seed(3)
    for _ in range(40):                                   # 先讓客人進來，但咖啡師不接單
        desk.busy = lambda: True
        desk.update_order(0.5, 0, 25.0)
    assert desk.order is not None
    assert desk.people() <= orders.QUEUE_MAX, "排隊上限算客人（點好幾杯的算一位）"
    assert desk.stats.day()["walkouts"] >= 1, "等到耐心用完要離開並記錄"
    assert any("先走了" in t[0] for t in desk.toasts), "做飲品中也要看得到有人離開（通知，不是狀態列）"
    del desk.busy
    o = desk.order
    while o.state == "leaving":                           # 正在離開的那位走掉，下一位上前
        desk.update_order(0.5, 0, 0.0)
        o = desk.order
    o.wait = 0.0
    desk.make_order()
    run_until_idle(desk)
    assert o.state in ("done", "leaving") and o.price > 0
    d = desk.stats.day()
    assert d["revenue"] >= o.price and d["waited"] >= 1      # 雙頭機解鎖時後面同類的客人會一起做


def test_leaving_order_mode_clears_queue(desk):
    desk.set_order_mode(True)
    desk.new_order()
    desk.order.state = "making"
    desk.new_order()
    desk.new_order()
    assert len(desk.queue) == 2
    desk.set_order_mode(False)
    assert desk.queue == [] and not desk.business()


def test_mode_menu_three_way(desk):
    """右鍵與系統匣：手動／自動／營業 三選一，勾選狀態同步；自動間隔只有自動時能選；不會偷偷還原成自動"""
    assert desk.mode() == "manual" and desk.mode_actions["manual"].isChecked()
    desk.mode_actions["auto"].trigger()
    assert desk.mode() == "auto" and desk.auto and desk.interval_menu.isEnabled()
    if desk.tray:
        assert desk.tray_mode_actions["auto"].isChecked()
    desk.set_mode("business")
    assert desk.business() and not desk.auto and not desk.interval_menu.isEnabled()
    assert desk.mode_actions["business"].isChecked() and not desk.mode_actions["auto"].isChecked()
    desk.set_mode("manual")
    assert desk.mode() == "manual" and not desk.auto, "離開營業是選的那個模式，不會自己變回自動"
    assert not desk.interval_menu.isEnabled()
    labels = [a.text() for a in desk.menu.actions()]
    i = labels.index(desk.mode_actions["manual"].text())
    assert labels[i + 3] == desk.interval_menu.title(), "自動間隔就在三選一下面"


def test_espresso_orders_use_random_machine(desk, unlocked, monkeypatch):
    """雙頭機還沒解鎖時，點義式隨機挑一台已解鎖的咖啡機（解鎖後一律用雙頭機，見 test_duo.py）"""
    from cafe_desk import growth
    from cafe_desk.machines import MACHINES
    from cafe_desk.render.shop import SIDE_W
    monkeypatch.setitem(growth.MACHINE_LEVEL, "duo", 99)
    desk.set_order_mode(True)
    random.seed(2)
    used = set()
    for _ in range(30):
        desk.order = Order(1, "Amy", "espresso", [])
        desk.make_order()
        used.add(desk.machine.key)
        assert desk.scene_dx() + desk.machine.scene_w + SIDE_W <= desk._scene_w, "營業模式多一段出杯台"
        run_until_idle(desk)
        if used == set(MACHINES) - {"duo"}:
            break
    assert used == set(MACHINES) - {"duo"}, "每一台解鎖的都會輪到"


def test_auto_mode_repeats_selected_drink(desk, unlocked):
    """自動模式：照設定重複做目前選的飲品，參數不被改"""
    desk.set_drink("cappuccino")
    before_p, before_dp = desk.params.copy(), desk.dp.copy()
    desk.auto = True
    for _ in range(3):
        desk.idle_since = -1e9
        desk.step(0.05, 0.05)
        assert desk.session is not None and desk.session.drink == "cappuccino"
        assert desk.session.dp == before_dp
        run_until_idle(desk)
    assert desk.params == before_p and desk.dp == before_dp


def test_order_mode_locks_menus(desk):
    desk.open_settings()
    desk.set_order_mode(True)
    for menu in (desk.method_menu, desk.machine_menu, desk.drink_menu, desk.art_menu,
                 desk.interval_menu, desk.maint_menu):
        assert not menu.isEnabled()
    assert desk.bean_menu.isEnabled(), "營業中也能換豆子（這杯做完才換）"
    assert not desk.settings_dlg.drink.isEnabled() and not desk.settings_dlg.art.isEnabled()
    desk.set_order_mode(False)
    for menu in (desk.method_menu, desk.machine_menu, desk.drink_menu, desk.art_menu, desk.bean_menu):
        assert menu.isEnabled()
    assert desk.settings_dlg.drink.isEnabled()


def test_switch_crossfades(desk):
    """換咖啡機、換沖煮方式：舊畫面淡出"""
    desk.host.grab()
    desk.set_machine("lever" if desk.machine.key != "lever" else "desk01")
    assert desk.fade_amount() is not None and desk.wanted_interval() == 16
    desk._fade = (desk._fade[0], desk._fade[1] - 1.0)
    assert desk.fade_amount() is None and desk._fade is None
    desk.host.grab()                                    # 換機器後重畫過才有畫面可以淡出
    desk.set_method("colddrip")
    assert desk._fade is not None
    desk.host.grab()


def test_business_cleans_before_next_order(desk):
    """營業中客人一直來也要清：做完一杯、接下一張單前，該清的先清"""
    desk.set_method("espresso")
    desk.set_order_mode(True)
    desk.maint["backflush"] = 40
    desk.new_order()
    for _ in range(10):
        desk.step(0.05, 0.05)
    assert desk.job is not None and desk.job.kind == "backflush", "接單前先逆洗"
    run_until_idle(desk)
    assert desk.maint["backflush"] < 25


def test_maintenance_is_per_machine(desk, cfg_path):
    """清潔保養每台各自計算：在拉桿機做的不算到 DESK·01；清了 A 台不影響 B 台；重開還在"""
    desk.set_machine("lever")
    desk.maint["backflush"] = 24
    desk.set_machine("desk01")
    assert desk.maint["backflush"] == 0
    desk.maint["backflush"] = 5
    desk.bag["left"] = 250
    desk.start_session("espresso", False)
    run_until_idle(desk)
    assert desk.maint_all["desk01"]["backflush"] == 6 and desk.maint_all["lever"]["backflush"] == 24
    desk.set_machine("lever")
    desk.start_job("backflush")
    run_until_idle(desk)
    assert desk.maint_all["lever"]["backflush"] == 0 and desk.maint_all["desk01"]["backflush"] == 6
    desk.save_config()
    from cafe_desk import config
    assert config.load()["maintenance"]["desk01"]["backflush"] == 6


def test_switch_pauses_before_making(desk):
    """點單換了咖啡機：漸變完再停 0.5 秒才開始做；沒換就直接做"""
    from cafe_desk import desk as desk_mod
    desk.set_order_mode(True)
    desk.set_machine("lever")
    desk.order = Order(1, "Amy", "espresso", [])
    random.seed(0)
    while True:                                          # 找一個會換到別台的亂數
        state = random.getstate()
        if random.choice(list(desk_mod.MACHINES)) != "lever":
            break
    random.setstate(state)
    desk.make_order()
    assert desk.machine.key != "lever" and desk.session is None and desk.busy()
    steps = 0
    while desk.session is None:
        desk.step(0.05, 0.05)
        steps += 1
    assert steps * 0.05 == pytest.approx(desk_mod.FADE_T + desk_mod.SWITCH_PAUSE, abs=0.06)
    run_until_idle(desk)
    desk.order = Order(2, "Ken", "espresso", [])
    desk.order.state = "waiting"
    random.seed(1)
    while True:                                          # 這次抽到同一台：直接開始
        state = random.getstate()
        if random.choice(list(desk_mod.MACHINES)) == desk.machine.key:
            break
    random.setstate(state)
    desk.make_order()
    assert desk.session is not None


def test_leaving_business_hides_order_slip(desk):
    """營業中正在做的那杯切到手動：照樣做完記帳，但點單紙馬上不畫、做完就收掉"""
    from conftest import run_until_idle, until_making
    desk.set_mode("business")
    desk.arrive_in = 0
    desk.step(0.05, 0.05)
    desk.order.t = 3
    desk.step(0.05, 0.05)
    until_making(desk)
    desk.set_mode("manual")
    run_until_idle(desk)
    for _ in range(5):
        desk.step(0.05, 0.05)
    assert desk.order is None and desk.order_alpha == 0
    assert desk.stats.day()["orders"] == 1, "做完的那杯照樣算給客人"
    assert not desk.cards_left() > 4


def test_business_restores_my_setup(desk, unlocked):
    """營業不改你的設定：參數、咖啡機、飲品在離開營業、那杯做完後還原；營業中參數滑桿鎖住"""
    from conftest import run_until_idle
    desk.set_machine("lever")
    desk.set_drink("cappuccino")
    desk.params.grind_um = 300.0
    desk.open_settings()
    desk.set_mode("business")
    assert not desk.settings_dlg.sliders["grind_um"][0].isEnabled()
    desk.params.grind_um, desk.params.temp = 240.0, 96.0           # 咖啡師營業中調過參數
    desk.set_machine("compact")
    desk.set_drink("latte")
    desk.set_mode("manual")
    run_until_idle(desk)
    desk.step(0.05, 0.05)
    assert desk.params.grind_um == 300.0 and desk.params.temp != 96.0
    assert desk.machine.key == "lever" and desk.drink == "cappuccino" and desk.pre_biz is None


def test_business_setup_restored_after_restart(qapp, cfg_path):
    """營業中關程式、下次開啟又關掉營業：一樣還原（設定檔存著開營業前的設定）"""
    import json
    from cafe_desk.desk import CafeDesk
    with open(cfg_path, "w", encoding="utf-8") as f:
        json.dump({"schema": 3, "machine": "desk01", "drink": "latte", "order_mode": False,
                   "params": {"grind_um": 250.0},
                   "pre_business": {"params": {"grind_um": 310.0}, "machine": "desk01", "drink": "espresso"}}, f)
    w = CafeDesk()
    try:
        w.step(0.05, 0.05)
        assert w.params.grind_um == 310.0 and w.drink == "espresso" and w.pre_biz is None
    finally:
        w.timer.stop()
        w.stats.db.close()
        w.host.close()


def test_barista_sets_up_cold_drip_when_quiet(desk, unlocked):
    """營業中冰滴解鎖、沒有批次、沒有客人：咖啡師去架冰滴塔"""
    desk.set_mode("business")
    desk.arrive_in = 999
    desk.step(0.05, 0.05)
    assert desk.session is not None and desk.session.cold_setup
    from conftest import run_until_idle
    run_until_idle(desk)
    assert desk.cold is not None and not desk.cold.get("done")


def test_no_cold_setup_when_locked(desk):
    desk.set_mode("business")
    desk.arrive_in = 999
    desk.step(0.05, 0.05)
    assert desk.session is None, "Lv.1 冰滴還沒解鎖"
