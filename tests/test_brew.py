"""手沖與冰滴：萃取模型、流程、冰滴背景批次（跨重啟）、沖煮方式與畫面、拉近、訂單、咖啡師調參"""
import random

import pytest

from cafe_desk import brew, orders
from cafe_desk.drinks import DrinkParams

from conftest import run_until_idle, until_making


def _dp(**kw):
    dp = DrinkParams()
    for k, v in kw.items():
        setattr(dp, k, v)
    return dp


def test_pourover_model_defaults_are_good():
    res = brew.simulate_pourover(_dp(), "中焙", 12, "colombia")
    assert res.score >= 80
    assert 150 <= res.time <= 210                         # 約 2:30–3:30
    assert brew.TDS_POUR[0] <= res.tds <= brew.TDS_POUR[1]


def test_pourover_model_responds_to_params():
    base = brew.simulate_pourover(_dp(), "中焙", 12, "")
    coarse = brew.simulate_pourover(_dp(po_grind=1000), "中焙", 12, "")
    fine = brew.simulate_pourover(_dp(po_grind=400), "中焙", 12, "")
    assert coarse.ey < base.ey < fine.ey
    assert coarse.time < base.time < fine.time
    assert fine.channeling > base.channeling              # 太細：堵住、萃取不均
    one_pour = brew.simulate_pourover(_dp(po_pulses=1), "中焙", 12, "")
    assert one_pour.score < base.score
    no_bloom = brew.simulate_pourover(_dp(po_bloom=0), "中焙", 3, "")
    assert no_bloom.score < brew.simulate_pourover(_dp(), "中焙", 3, "").score
    assert brew.bloom_ok(_dp()) and not brew.bloom_ok(_dp(po_pulses=1)) and not brew.bloom_ok(_dp(po_bloom=60))


def test_colddrip_model():
    res = brew.simulate_colddrip(_dp(), "中焙", 12, "")
    assert res.score >= 75
    slow = brew.simulate_colddrip(_dp(cd_rate=5), "中焙", 12, "")
    assert slow.time > res.time and slow.ey > res.ey


def test_cold_batch_progress():
    b = brew.new_cold_batch(_dp(), "中焙", 12, "kenya", now=1000.0)
    assert brew.valid_batch(b)
    assert brew.cold_progress(b, 1000.0) == 0
    assert brew.cold_progress(b, 1000.0 + b["dur"] / 2) == 0.5
    assert brew.cold_progress(b, 1e9) == 1
    assert brew.cold_remaining_min(b, 1000.0) == int(brew.COLD_DUR // 60)
    assert not brew.valid_batch({"start": "x"}) and not brew.valid_batch(None)


def test_pourover_scene_and_flow(desk):
    machine_w = desk.width()
    desk.bag["left"] = 250
    assert desk.start_session("pour_over", True)          # 自動切到手沖畫面；完整流程也不走把手備粉
    assert desk.method == "pourover" and desk.workflow is None
    assert desk.width() == machine_w, "手沖畫面跟咖啡機一樣大"
    run_until_idle(desk)
    dp = desk.dp
    assert desk.contents["water"] == dp.po_dose * (dp.po_ratio - brew.RETAIN_K)
    assert desk.bag["left"] == 250 - dp.po_dose
    assert desk.result.drink == "pour_over" and 0 <= desk.result.score <= 100
    assert "first_pourover" not in desk.stats.data["achievements"], "自己沖的不算成就（要為客人做）"
    desk.set_method("espresso")
    assert desk.width() == machine_w and desk.drink != "pour_over"
    assert desk.cup.CX == desk.machine.cup_cx, "回到咖啡機：杯子放回沖煮頭下"


def test_method_filters_drinks_and_menu(desk):
    desk.set_method("colddrip")
    assert desk.drink == "cold_drip"
    assert set(desk.drink_actions) == {"cold_drip"}
    assert not desk.machine_menu.isEnabled() and not desk.art_menu.isEnabled()
    desk.set_drink("latte")                               # 選義式飲品：切回咖啡機
    assert desk.method == "espresso" and "pour_over" not in desk.drink_actions
    assert desk.machine_menu.isEnabled()
    desk.set_method("pourover")
    assert desk.auto_drink() == "pour_over"
    desk.set_method("colddrip")
    desk.cold = brew.new_cold_batch(desk.dp, "中焙", 10, "kenya")
    assert desk.auto_drink() is None, "冰滴還在滴：自動模式等滴完"


def test_cold_drip_survives_restart(qapp, cfg_path, unlocked):
    from cafe_desk.desk import CafeDesk
    w = CafeDesk()
    w.show_window()
    assert w.start_session("cold_drip", False)
    run_until_idle(w)
    assert w.cold is not None and w.result is None
    w.cold["start"] -= w.cold["dur"] * 0.5
    w.save_config()
    w.timer.stop()
    w.stats.db.close()
    w.host.close()
    w2 = CafeDesk()
    w2.show_window()
    try:
        assert w2.cold is not None and not w2.cold["done"]
        assert w2.method == "colddrip" and w2.width() == w2.machine.scene_w * w2.scale_f
        assert w2.start_session("cold_drip", False) is False      # 還在滴
        w2.cold["start"] -= w2.cold["dur"]
        w2.step(0.05, 0.05)
        assert w2.cold["done"] and w2.cold["servings"] == brew.COLD_SERVINGS
        assert "cold_drip" in w2.stats.data["achievements"]
        for i in range(brew.COLD_SERVINGS):
            assert w2.start_session("cold_drip", False)
            run_until_idle(w2)
            assert w2.result.drink == "cold_drip"
        assert w2.cold is None, "倒完收起冰滴塔"
    finally:
        w2.timer.stop()
        w2.stats.db.close()
        w2.host.close()


def test_orders_exclude_cold_drip_until_ready(desk, unlocked):
    rnd = random.Random(1)
    assert all(orders.make_order(i, rnd, exclude=("cold_drip",)).drink != "cold_drip" for i in range(400))
    desk.set_method("colddrip")
    assert desk.order_exclude() == ("cold_drip",), "客人不分沖煮方式都能點，只有冰滴要等滴好"
    desk.cold = brew.new_cold_batch(desk.dp, "中焙", 10, "kenya")
    desk.cold.update(done=True, servings=1)
    assert desk.order_exclude() == ()
    desk.order = orders.Order(1, "Amy", "cold_drip", [])
    assert desk.order_exclude() == ("cold_drip",), "最後一杯已經被點走"
    assert ("ice", "less") in orders.mod_pool("cold_drip")


def test_zoom_in_while_brewing_and_out_to_pour(desk):
    desk.set_method("pourover")
    assert desk.brew_zoom == 0
    desk.bag["left"] = 250
    desk.start_session("pour_over", False)
    seen_zoom, pour_zoom = 0.0, None
    while desk.busy():
        desk.step(0.05, 0.05)
        ss = desk.session
        if ss and ss.stage_name == "pourover":
            seen_zoom = max(seen_zoom, desk.brew_zoom)
        if ss and ss.stage_name == "pour" and pour_zoom is None:
            pour_zoom = desk.brew_zoom
    assert seen_zoom == 1.0, "沖煮時拉近"
    assert pour_zoom == 0.0, "拉遠之後才倒進杯子"
    assert desk.cup_alpha() == 1.0
    desk.set_method("colddrip")
    desk.cold = brew.new_cold_batch(desk.dp, "中焙", 10, "kenya")
    for _ in range(40):
        desk.step(0.05, 0.05)
    assert desk.brew_zoom == 1.0, "冰滴在滴：近景"
    desk.cold["start"] -= desk.cold["dur"]
    for _ in range(40):
        desk.step(0.05, 0.05)
    assert desk.cold["done"] and desk.brew_zoom == 0.0, "滴完拉遠"


def test_brew_scene_hides_espresso_machine_effects(desk):
    desk.set_method("colddrip")
    desk.warming = True
    assert "°C" not in "".join(t for t, _ in desk.status_parts()), "不顯示咖啡機預熱溫度"
    desk.next_idle_event = 0
    desk.steam.clear()
    for _ in range(20):
        desk.step(0.05, 0.05)
    assert not desk.steam, "不從看不見的咖啡機放氣"
    assert desk.start_job("wand") is False and not desk.maint_menu.isEnabled()


def test_barista_dials_for_roast():
    import random as _r
    rnd = _r.Random(4)
    for roast, origin in (("淺焙", "kenya"), ("中焙", "colombia"), ("深焙", "brazil")):
        user = _dp()
        d = brew.barista_dial(user, roast, rnd)
        assert user.po_grind == 650 and user.po_temp == 93, "不寫回使用者設定"
        assert brew.simulate_pourover(d, roast, 10, origin).score >= 80, roast
        assert brew.simulate_colddrip(d, roast, 10, origin).score >= 80, roast
    assert brew.simulate_pourover(_dp(), "淺焙", 10, "kenya").score < 60, "手動照預設沖淺焙會偏酸（提示要調）"


def test_pourover_customers_are_patient():
    import random as _r
    assert orders.patience(_r.Random(1), "pourover") == pytest.approx(orders.patience(_r.Random(1)) * orders.PACE["pourover"])


def test_orders_switch_brew_method_automatically(desk):
    """客人隨機點，做的時候自動切到那杯的沖煮方式；切換不會把排隊的客人趕走"""
    desk.auto = True
    desk.set_order_mode(True)
    desk.set_method("espresso")
    desk.new_order()
    desk.order.drink, desk.order.mods = "pour_over", []
    desk.order.price = orders.price_of("pour_over")
    desk.new_order()
    assert len(desk.queue) == 1
    queued = desk.queue[0]
    o = desk.order
    desk.bag["left"] = 250
    desk.make_order()
    until_making(desk)
    assert desk.method == "pourover" and o.state == "making"
    assert desk.queue == [queued], "排隊的客人還在"
    run_until_idle(desk)
    assert o.state == "done" and desk.result.drink == "pour_over"


def test_full_flow_everywhere(desk):
    """完整流程不是選項了：手動、自動模式、營業中都備粉"""
    desk.set_method("espresso")
    desk.bag["left"] = 250
    desk.manual_brew()
    assert desk.session.stages[0].name in ("prep", "cool") and any(s.name == "prep" for s in desk.session.stages)
    run_until_idle(desk)
    desk.auto = True
    desk.set_order_mode(True)
    desk.new_order()
    o = desk.order
    o.drink, o.mods = "espresso", []
    desk.update_order(3.0, 0, 0.0)                          # 營業模式：咖啡師 2.5 秒後自己接單
    until_making(desk)
    assert desk.session is not None and any(s.name == "prep" for s in desk.session.stages)
